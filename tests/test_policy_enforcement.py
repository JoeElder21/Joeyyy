"""The single policy-enforcement point must actually enforce.

Record: docs/REPO_OPTIMIZATION_2026-07-25.md, Tier 2 #5 (Cedar absorption).

The consolidation is only worth anything if every rule genuinely fires. The
first draft of this module sourced lifecycle stage and connector policy from
`load_roster`, which reads `.codex/agents/*.toml` — files that carry neither
field. Both rules silently returned "no objection" for every agent: no error, no
failure, the checks simply never ran. That is exactly the fail-open-by-omission
the enforcement point exists to eliminate, and it survived until the module was
actually executed.

`test_no_rule_silently_no_ops` exists so it cannot come back.
"""

import dataclasses
import datetime
import json
import re
import tempfile
import unittest
from pathlib import Path

from runtime.writer_lease import LeaseRegistry
from scripts import policy_enforcement  # noqa: E402
from scripts.agent_runtime import AuditLedger
from scripts.policy_enforcement import (
    AUTHORIZATION_SCHEMAS,
    BRAIN_NEUTRAL_PREFIXES,
    CHIEF,
    HIGH_IMPACT_ACTIONS,
    HIGH_IMPACT_VERBS,
    MUTATING_ACTION_VERBS,
    NON_EXECUTING_STAGES,
    PACKET_ONLY,
    Decision,
    PolicyDenied,
    PolicyEnforcementPoint,
    ToolRequest,
    _action_tokens,
    enforce,
)
from scripts.trusted_launcher import _sign

ROOT = Path(__file__).resolve().parents[1]
SPECIALIST = "apex_war_architect"
JEOS_SPECIALIST = "jeos_reflection_forge"
# The suite's "current instant", taken from the real clock ONCE at import.
#
# This was the literal `datetime(2026, 7, 25, 12, 0)`, and it was a time bomb
# that went off. `registry_and_lease()` issues its fixture lease at this instant
# with the registry's 24-hour maximum TTL, and `PacketGuard` checks lease expiry
# against `datetime.now(UTC)` with no injectable clock -- so every lease-bearing
# test passed until 2026-07-26 12:00Z and failed from then on. CI's last green
# run finished at 11:54Z, six minutes before the cliff, and nothing in the diff
# had changed.
#
# Two clocks, one decision: the enforcement point ran on a frozen clock while the
# guard it delegates to ran on the real one. Fixed by making the frozen clock
# track the real one, because the guard's is the one that cannot be injected.
#
# Read once at import rather than per call, so a single test run still sees a
# stable instant -- the determinism the frozen constant was for -- while never
# drifting more than one run's duration from the guard's clock. Every use is
# RELATIVE (`NOW + delta`, `NOW - delta`); no test asserts this literal date, which
# is what makes deriving it safe. `test_the_fixture_lease_is_live_against_real_time`
# fails if it is ever re-frozen.
NOW = datetime.datetime.now(datetime.UTC).replace(microsecond=0)


def registry_and_lease(**overrides):
    """A registry plus the lease it actually issued.

    The enforcement point now verifies lease ids against the issuing registry,
    so a test lease must come from a registry the point can see. That is the
    point of the check: a lease nobody issued authorizes nothing.
    """
    registry = LeaseRegistry()
    fields = {
        "mission_id": "m-001",
        "owner_brain": "APEX",
        "writer_agent": CHIEF,
        "write_target": "APEX/Strategy-Campaigns",
        "resource_id": "campaign-alpha",
        "expected_state": "campaign record absent",
        "rollback": "delete created record",
        "now": NOW,
    }
    fields.update(overrides)
    return registry, dict(registry.issue(**fields))


def instruction_grant(action, resource, key_path, minutes=30):
    """A genuine signed instruction, built with the launcher's own primitive.

    Signed here rather than stubbed: a test that fabricates its own signature
    format proves the rule agrees with the test, not that it agrees with the
    launcher.
    """
    payload = {
        "action": action,
        "resource": resource,
        "issued_at": NOW.timestamp(),
        "expires_at": (NOW + datetime.timedelta(minutes=minutes)).timestamp(),
        "nonce": "n-0001",
    }
    return {**payload, "sig": _sign(key_path.read_bytes(), payload)}


def real_lease(**overrides):
    """A genuine lease from the registry, not a stub.

    Tests that hand-build lease-shaped dicts prove only that the checks read
    those two fields. Issuing a real lease and then breaking exactly one thing
    proves the check fires against what the runtime actually produces.
    """
    fields = {
        "mission_id": "m-001",
        "owner_brain": "APEX",
        "writer_agent": CHIEF,
        "write_target": "APEX/Strategy-Campaigns",
        "resource_id": "campaign-alpha",
        "expected_state": "campaign record absent",
        "rollback": "delete created record",
        "now": NOW,
    }
    fields.update(overrides)
    return dict(LeaseRegistry().issue(**fields))


class RuleCoverageTests(unittest.TestCase):
    """Every declared rule must be reachable and capable of denying."""

    def setUp(self):
        self.pep = PolicyEnforcementPoint(ROOT)

    def test_no_rule_silently_no_ops(self):
        # Regression guard for the fail-open bug described in this module's
        # docstring. Each rule must be able to produce at least one denial on
        # some request; a rule that can never fire is decoration.
        firing = {
            "agent_registered": ToolRequest(agent="ghost", action="read", resource="x"),
            "brain_lock": ToolRequest(
                agent=SPECIALIST, action="read", resource="x", owner_brain="JEOS"
            ),
            "writer_lease": ToolRequest(
                agent=CHIEF,
                action="write",
                resource="APEX/Strategy-Campaigns",
                owner_brain="APEX",
                mutating=True,
                packet=None,
            ),
            "lifecycle_stage": ToolRequest(
                agent=SPECIALIST,
                action="write",
                resource="APEX/Strategy-Campaigns",
                owner_brain="APEX",
                mutating=True,
            ),
            "high_impact_boundary": ToolRequest(
                agent=CHIEF, action="financial_transaction", resource="account"
            ),
            "launch_grant": ToolRequest(
                agent=CHIEF, action="write", resource="mount:civil3d", mutating=True
            ),
        }
        for rule, request in firing.items():
            with self.subTest(rule=rule):
                decision = self.pep.evaluate(request)
                self.assertFalse(decision.allowed, f"{rule} never denies anything")

    def test_lifecycle_stage_reads_a_real_status(self):
        # The specific field whose absence caused the fail-open.
        spec = self.pep._spec(SPECIALIST)
        self.assertIn("status", spec)
        self.assertIn(spec["status"], NON_EXECUTING_STAGES | {"active", "value-proven"})

    def test_connector_policy_reads_a_real_policy(self):
        spec = self.pep._spec(SPECIALIST)
        self.assertEqual(spec.get("connector_policy"), PACKET_ONLY)

    def test_every_check_runs_on_every_request(self):
        decision = self.pep.evaluate(
            ToolRequest(
                agent=SPECIALIST, action="read", resource="docs/README.md", owner_brain="APEX"
            )
        )
        self.assertEqual(len(decision.checks_run), 8)
        self.assertIn("brain_lock", decision.checks_run)
        self.assertIn("lifecycle_stage", decision.checks_run)


class DenialTests(unittest.TestCase):
    def setUp(self):
        self.registry, self.lease = registry_and_lease()
        self.pep = PolicyEnforcementPoint(ROOT, registry=self.registry, clock=lambda: NOW)

    def test_unregistered_agent_is_denied(self):
        decision = self.pep.evaluate(ToolRequest(agent="rogue", action="read", resource="x"))
        self.assertFalse(decision.allowed)
        self.assertIn("not in the deployed roster", decision.reasons[0])

    def test_cross_brain_request_is_denied(self):
        decision = self.pep.evaluate(
            ToolRequest(agent=SPECIALIST, action="read", resource="JEOS/Weekly", owner_brain="JEOS")
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(any("brain lock" in reason for reason in decision.reasons))

    def test_jeos_specialist_cannot_claim_apex(self):
        decision = self.pep.evaluate(
            ToolRequest(agent=JEOS_SPECIALIST, action="read", resource="APEX/x", owner_brain="APEX")
        )
        self.assertFalse(decision.allowed)

    def test_shadow_specialist_cannot_mutate(self):
        decision = self.pep.evaluate(
            ToolRequest(
                agent=SPECIALIST,
                action="write",
                resource="APEX/Strategy-Campaigns",
                owner_brain="APEX",
                mutating=True,
            )
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(any("shadow" in reason for reason in decision.reasons))

    def test_every_high_impact_action_requires_a_signed_instruction(self):
        # Exercised at the rule rather than through evaluate(): high-impact
        # actions are now also classified as mutations, so a full evaluation
        # additionally demands a lease. That is correct -- publishing or
        # transacting is a mutation -- but it is a different rule's business,
        # and folding it in here would stop this test from testing this rule.
        with tempfile.TemporaryDirectory() as tmp:
            key_path = Path(tmp) / "launch_key"
            key_path.write_bytes(b"test-signing-key")
            key_path.chmod(0o600)
            for action in sorted(HIGH_IMPACT_ACTIONS):
                with self.subTest(action=action):
                    pep = PolicyEnforcementPoint(ROOT, launch_key_path=key_path, clock=lambda: NOW)
                    without = ToolRequest(agent=CHIEF, action=action, resource="target")
                    self.assertTrue(pep._high_impact_boundary(without))
                    signed = ToolRequest(
                        agent=CHIEF,
                        action=action,
                        resource="target",
                        instruction_grant=instruction_grant(action, "target", key_path),
                    )
                    self.assertEqual(pep._high_impact_boundary(signed), [])

    def test_asserting_an_instruction_without_signing_it_authorizes_nothing(self):
        # The defect: `explicit_instruction=True` was a caller-set boolean, so
        # a caller could sanction the very actions AGENTS.md reserves for Joe.
        # This is the same shape as `mutating` and `launch_grant_verified`, two
        # rounds apart, and the one with the worst blast radius.
        self.assertFalse(
            hasattr(ToolRequest(agent=CHIEF, action="x", resource="y"), "explicit_instruction")
        )
        reasons = self.pep._high_impact_boundary(
            ToolRequest(
                agent=CHIEF,
                action="financial_transaction",
                resource="target",
                instruction_grant={"action": "financial_transaction", "resource": "target"},
            )
        )
        self.assertTrue(reasons)

    def test_an_instruction_cannot_be_replayed_against_another_action_or_target(self):
        # A grant is bound to one boundary action on one resource. Without that
        # binding, an instruction to publish one document would authorize a
        # financial transaction against anything.
        with tempfile.TemporaryDirectory() as tmp:
            key_path = Path(tmp) / "launch_key"
            key_path.write_bytes(b"test-signing-key")
            key_path.chmod(0o600)
            pep = PolicyEnforcementPoint(ROOT, launch_key_path=key_path, clock=lambda: NOW)
            grant = instruction_grant("public_publication", "APEX/Post", key_path)
            wrong_action = pep._high_impact_boundary(
                ToolRequest(
                    agent=CHIEF,
                    action="financial_transaction",
                    resource="APEX/Post",
                    instruction_grant=grant,
                )
            )
            self.assertTrue(any("authorizes" in reason for reason in wrong_action))
            wrong_target = pep._high_impact_boundary(
                ToolRequest(
                    agent=CHIEF,
                    action="public_publication",
                    resource="APEX/Other",
                    instruction_grant=grant,
                )
            )
            self.assertTrue(any("scoped to" in reason for reason in wrong_target))

    def test_a_forged_instruction_signature_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_path = Path(tmp) / "launch_key"
            key_path.write_bytes(b"test-signing-key")
            key_path.chmod(0o600)
            pep = PolicyEnforcementPoint(ROOT, launch_key_path=key_path, clock=lambda: NOW)
            grant = instruction_grant("public_publication", "APEX/Post", key_path)
            grant["sig"] = "0" * 64
            reasons = pep._high_impact_boundary(
                ToolRequest(
                    agent=CHIEF,
                    action="public_publication",
                    resource="APEX/Post",
                    instruction_grant=grant,
                )
            )
            self.assertTrue(any("signature is invalid" in reason for reason in reasons))

    def test_high_impact_actions_are_treated_as_mutations(self):
        # Signing, transacting, or publishing changes the world; classifying them
        # as reads would skip the lease and lifecycle rules entirely.
        for action in sorted(HIGH_IMPACT_ACTIONS):
            with self.subTest(action=action):
                self.assertTrue(
                    self.pep._is_mutating(
                        ToolRequest(agent=CHIEF, action=action, resource="target")
                    )
                )

    def test_a_write_action_is_mutating_even_if_the_caller_says_otherwise(self):
        # The bypass: leaving the flag at its default skipped every mutation
        # control. The flag may add strictness, never remove it.
        request = ToolRequest(
            agent=SPECIALIST,
            action="write",
            resource="APEX/Strategy-Campaigns",
            owner_brain="APEX",
        )
        self.assertTrue(self.pep._is_mutating(request))
        decision = self.pep.evaluate(request)
        self.assertFalse(decision.allowed)
        self.assertTrue(any("lease" in reason for reason in decision.reasons))

    def test_a_lease_no_registry_issued_authorizes_nothing(self):
        # A fully-populated, schema-valid, fabricated lease.
        fabricated = dict(self.lease)
        fabricated["lease_id"] = "fabricated-0001"
        reasons = self.pep._writer_lease(self._mutating(lease=fabricated))
        self.assertTrue(any("does not match the registered" in reason for reason in reasons))

    def test_without_a_registry_no_mutation_can_be_authorized(self):
        pep = PolicyEnforcementPoint(ROOT)  # no registry
        reasons = pep._writer_lease(self._mutating(lease=self.lease))
        self.assertTrue(any("cannot be verified as issued" in reason for reason in reasons))

    def test_a_packet_addressed_to_another_agent_does_not_authorize(self):
        reasons = self.pep._packet_scope_errors(
            ToolRequest(
                agent="apex_intelligence_forge",
                action="read",
                resource="x",
                owner_brain="APEX",
                packet={"agent": SPECIALIST, "owner_brain": "APEX"},
            )
        )
        self.assertTrue(any("addresses" in reason for reason in reasons))

    def test_mutation_without_a_lease_is_denied(self):
        decision = self.pep.evaluate(
            ToolRequest(
                agent=CHIEF,
                action="write",
                resource="APEX/Strategy-Campaigns",
                owner_brain="APEX",
                mutating=True,
            )
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(any("writer lease" in reason for reason in decision.reasons))

    def test_a_forged_lease_dict_is_rejected_before_any_field_is_trusted(self):
        # The hole this closes: a caller minting its own authorization out of two
        # matching strings. It must fail as a *lease*, not merely mismatch.
        forged = {"writer_agent": CHIEF, "write_target": "APEX/Strategy-Campaigns"}
        reasons = self.pep._writer_lease(
            ToolRequest(
                agent=CHIEF,
                action="write",
                resource="APEX/Strategy-Campaigns",
                owner_brain="APEX",
                mutating=True,
                lease=forged,
            )
        )
        self.assertTrue(reasons)
        # Rejected for *un-issuance*, which now fires before schema validation:
        # a lease nobody issued fails whether or not its shape is right. The
        # assertion is on the property, not on which message wins the race.
        self.assertTrue(
            any(
                phrase in reason
                for reason in reasons
                for phrase in ("cannot be verified as issued", "cannot be keyed", "lease rejected")
            )
        )

    def test_a_genuine_registry_lease_is_accepted(self):
        # The accept path matters as much as the reject path: a rule that denies
        # everything is not enforcement, it is an outage.
        reasons = self.pep._writer_lease(
            self._mutating(lease=self.lease, resource_id="campaign-alpha")
        )
        self.assertEqual(reasons, [])

    def test_lease_held_by_another_agent_is_denied(self):
        # Reversed direction, deliberately. The original issued the lease TO the
        # specialist and had the chief present it; that scenario is now caught
        # one rule earlier -- the guard's own "writer is not eligible for the
        # target at the deployed lifecycle stage" -- because reconciling the
        # 2.1-vs-2.0 defect finally lets the guard's lease semantics run against
        # a registry lease at all. They never had before: the schema error
        # short-circuited every one of them.
        #
        # So the holder comparison is exercised the way it is actually
        # reachable: a genuine lease issued to the chief, presented by a
        # specialist. The chief is always an eligible writer, so eligibility
        # passes and the holder mismatch is what denies.
        registry, lease = registry_and_lease()
        pep = PolicyEnforcementPoint(ROOT, registry=registry, clock=lambda: NOW)
        reasons = pep._writer_lease(
            ToolRequest(
                agent=SPECIALIST,
                action="write",
                resource=lease["write_target"],
                owner_brain=lease["owner_brain"],
                mutating=True,
                lease=lease,
                resource_id=lease["resource_id"],
            )
        )
        self.assertTrue(any("held by" in reason for reason in reasons), reasons)

    def test_an_ineligible_writer_cannot_hold_a_lease_at_all(self):
        # The scenario the test above used to cover, kept and asserted on its
        # real grounds. A shadow specialist is not an eligible writer for the
        # target, so a lease naming it authorizes nothing regardless of who
        # presents it.
        registry, lease = registry_and_lease(writer_agent=SPECIALIST)
        pep = PolicyEnforcementPoint(ROOT, registry=registry, clock=lambda: NOW)
        reasons = pep._writer_lease(self._mutating(lease=lease))
        self.assertTrue(any("not eligible" in reason for reason in reasons), reasons)

    def test_lease_does_not_stretch_to_another_target(self):
        reasons = self.pep._writer_lease(
            self._mutating(lease=self.lease, resource="APEX/Decision-Log")
        )
        self.assertTrue(any("does not cover" in reason for reason in reasons))

    def test_expired_lease_is_denied(self):
        # Expiry must be judged from the registry's lease, so this advances the
        # clock rather than editing the caller's copy. Editing the copy is now
        # correctly ignored -- which is the point of the registry fix, and the
        # reason the earlier version of this test was testing nothing real.
        later = NOW + datetime.timedelta(days=2)
        aged = PolicyEnforcementPoint(ROOT, registry=self.registry, clock=lambda: later)
        reasons = aged._writer_lease(
            ToolRequest(
                agent=CHIEF,
                action="write",
                resource="APEX/Strategy-Campaigns",
                owner_brain="APEX",
                mutating=True,
                lease=self.lease,
            )
        )
        self.assertTrue(
            any("expired" in reason or "no active lease" in reason for reason in reasons)
        )

    def test_tampering_with_the_caller_copy_changes_nothing(self):
        # The attack the registry fix closes: copy a genuine active lease and
        # rewrite the authorization-relevant fields. Every check now reads the
        # registry's object, so the tampering is simply not consulted.
        tampered = dict(self.lease)
        tampered["expires_at"] = "2099-01-01T00:00:00+00:00"
        tampered["status"] = "active"
        reasons = self.pep._writer_lease(
            self._mutating(lease=tampered, resource_id="campaign-alpha")
        )
        self.assertEqual(reasons, [])

    def test_closed_lease_authorizes_nothing_further(self):
        # Close it in the registry -- the authoritative place -- not in the copy.
        self.registry.release(self.lease["lease_id"], readback_confirmed=True)
        reasons = self.pep._writer_lease(
            self._mutating(lease=self.lease, resource_id="campaign-alpha")
        )
        self.assertTrue(reasons)

    def test_lease_for_another_resource_id_is_denied(self):
        reasons = self.pep._writer_lease(
            self._mutating(lease=self.lease, resource_id="campaign-beta")
        )
        self.assertTrue(any("resource" in reason for reason in reasons))

    def test_write_capable_mount_requires_a_launch_grant(self):
        request = ToolRequest(
            agent=CHIEF,
            action="write",
            resource="mount:civil3d",
            owner_brain="APEX",
            mutating=True,
            lease=registry_and_lease(write_target="mount:civil3d")[1],
        )
        self.assertFalse(self.pep.evaluate(request).allowed)

    def _mutating(self, *, lease, resource="APEX/Strategy-Campaigns", resource_id=None):
        return ToolRequest(
            agent=CHIEF,
            action="write",
            resource=resource,
            owner_brain="APEX",
            mutating=True,
            lease=lease,
            resource_id=resource_id,
        )

    def test_all_reasons_are_reported_not_just_the_first(self):
        # A caller fixing a denial should see every reason at once.
        decision = self.pep.evaluate(
            ToolRequest(
                agent=SPECIALIST,
                action="write",
                resource="APEX/Strategy-Campaigns",
                owner_brain="APEX",
                mutating=True,
            )
        )
        self.assertGreater(len(decision.reasons), 1)


class EnforceTests(unittest.TestCase):
    def test_enforce_raises_on_denial(self):
        with self.assertRaises(PolicyDenied):
            enforce(ToolRequest(agent="rogue", action="read", resource="x"))

    def test_enforce_returns_decision_on_allow(self):
        # The chief, because a specialist reading a canonical resource now needs
        # a delegation behind it -- the packetless path is confined to
        # current-message text.
        decision = enforce(
            ToolRequest(agent=CHIEF, action="read", resource="docs/README.md", owner_brain="APEX")
        )
        self.assertTrue(decision.allowed, decision.reasons)

    def test_denial_carries_the_request_and_reasons(self):
        try:
            enforce(ToolRequest(agent="rogue", action="read", resource="x"))
        except PolicyDenied as denial:
            self.assertEqual(denial.request.agent, "rogue")
            self.assertTrue(denial.reasons)
        else:  # pragma: no cover
            self.fail("expected PolicyDenied")

    def test_decision_is_falsy_when_denied(self):
        # So `if not enforce(...)` reads correctly even though enforce raises.
        self.assertFalse(bool(Decision(allowed=False, reasons=("x",))))
        self.assertTrue(bool(Decision(allowed=True)))

    def test_ledger_records_the_derived_status_not_the_submitted_one(self):
        # The audit trail has to agree with the decision it records. Logging the
        # caller's object described an inferred mutation as `mutating: false`,
        # so incident review would read that the lease and lifecycle rules had
        # not applied when in fact they had.
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AuditLedger(Path(tmp) / "audit.jsonl")
            with self.assertRaises(PolicyDenied):
                enforce(
                    ToolRequest(
                        agent=SPECIALIST,
                        action="WRITE",  # neither lowercase nor flagged
                        resource="APEX/Strategy-Campaigns",
                        owner_brain="APEX",
                    ),
                    ledger=ledger,
                )
            entry = json.loads(ledger.path.read_text(encoding="utf-8").splitlines()[-1])
            payload = entry["detail"]
            self.assertEqual(entry["event"], "policy_denied")
            self.assertTrue(payload["mutating"], "derived mutation must reach the ledger")
            self.assertTrue(payload["mutation_derived"])
            self.assertEqual(payload["action"], "write")
            self.assertEqual(payload["action_as_submitted"], "WRITE")


class NormalizationTests(unittest.TestCase):
    """Round 4: three bypasses that all lived in "which form of the request?"."""

    def setUp(self):
        self.registry, self.lease = registry_and_lease()
        self.pep = PolicyEnforcementPoint(ROOT, registry=self.registry, clock=lambda: NOW)

    def test_action_casing_cannot_bypass_the_high_impact_boundary(self):
        # `_is_mutating` lowercased; `_high_impact_boundary` did not. An action
        # spelled FINANCIAL_TRANSACTION was therefore treated as a mutation and
        # still walked past the explicit-instruction requirement.
        for spelling in (
            "FINANCIAL_TRANSACTION",
            "Financial_Transaction",
            " financial_transaction ",
        ):
            with self.subTest(spelling=spelling):
                decision = self.pep.evaluate(
                    ToolRequest(agent=CHIEF, action=spelling, resource="account")
                )
                self.assertFalse(decision.allowed)
                self.assertTrue(
                    any("high-impact boundary" in reason for reason in decision.reasons),
                    f"{spelling!r} evaded the boundary: {decision.reasons}",
                )

    def test_every_high_impact_action_resists_casing(self):
        # The whole set, not the one example that was reported.
        for action in sorted(HIGH_IMPACT_ACTIONS):
            with self.subTest(action=action):
                request = ToolRequest(agent=CHIEF, action=action.upper(), resource="target")
                normalized, _ = self.pep.normalize(request)
                self.assertEqual(self.pep._high_impact_boundary(normalized).__len__(), 1)

    def test_the_clock_cannot_be_set_from_the_request(self):
        # Expiry was compared against `ToolRequest.now`, supplied by the same
        # caller asking for authorization -- so a genuinely signed instruction
        # that expired years ago could be replayed by backdating the request.
        # The field is gone; the clock lives on the enforcement point.
        self.assertFalse(
            hasattr(ToolRequest(agent=CHIEF, action="read", resource="x"), "now"),
            "a caller-settable clock makes every expiry check advisory",
        )
        expired = NOW - datetime.timedelta(days=365)
        with tempfile.TemporaryDirectory() as tmp:
            key_path = Path(tmp) / "launch_key"
            key_path.write_bytes(b"test-signing-key")
            key_path.chmod(0o600)
            stale = instruction_grant("public_publication", "APEX/Post", key_path, minutes=-1)
            # Backdating is not available: the PEP's own clock decides.
            pep = PolicyEnforcementPoint(ROOT, launch_key_path=key_path, clock=lambda: NOW)
            reasons = pep._high_impact_boundary(
                ToolRequest(
                    agent=CHIEF,
                    action="public_publication",
                    resource="APEX/Post",
                    instruction_grant=stale,
                )
            )
            self.assertTrue(any("expired" in r for r in reasons), reasons)
            self.assertIsInstance(expired, datetime.datetime)

    def test_an_aware_clock_raises_no_clock_objection(self):
        # The naive-clock denial has to be about the clock, not about the
        # request being unauthorized for some other reason anyway. Same request,
        # aware clock: the lease rule is satisfied and no clock reason appears.
        request = ToolRequest(
            agent=CHIEF,
            action="write",
            resource="APEX/Strategy-Campaigns",
            owner_brain="APEX",
            mutating=True,
            lease=self.lease,
            resource_id="campaign-alpha",
        )
        decision = self.pep.evaluate(request)
        self.assertFalse(any("timezone-naive" in reason for reason in decision.reasons))
        self.assertEqual(self.pep._writer_lease(request), [])

    def test_the_decision_carries_the_request_the_rules_saw(self):
        decision = self.pep.evaluate(
            ToolRequest(agent=CHIEF, action="WRITE", resource="x", owner_brain="APEX")
        )
        self.assertIsNotNone(decision.request)
        self.assertEqual(decision.request.action, "write")
        self.assertTrue(decision.request.mutating)


class ScopeTests(unittest.TestCase):
    """Round 4: authorizations that stretched further than they were issued."""

    def setUp(self):
        self.registry, self.lease = registry_and_lease()
        self.pep = PolicyEnforcementPoint(ROOT, registry=self.registry, clock=lambda: NOW)

    def test_a_lease_does_not_stretch_to_a_prefix_sibling(self):
        # `startswith` widened every lease to its own prefix family, so a lease
        # for APEX/Strategy-Campaigns covered APEX/Strategy-Campaigns-Evil and
        # any other target reachable by appending characters.
        reasons = self.pep._writer_lease(
            ToolRequest(
                agent=CHIEF,
                action="write",
                resource="APEX/Strategy-Campaigns-Evil",
                owner_brain="APEX",
                mutating=True,
                lease=self.lease,
                resource_id="campaign-alpha",
            )
        )
        self.assertTrue(any("does not cover" in reason for reason in reasons), reasons)

    def test_a_non_authorization_schema_cannot_admit_a_request(self):
        # `packet_schema` is caller-supplied. Pointing it at writer_lease
        # satisfied admission with an object that authorizes nothing.
        reasons = self.pep._packet_admission(
            ToolRequest(
                agent=CHIEF,
                action="write",
                resource="APEX/Strategy-Campaigns",
                owner_brain="APEX",
                mutating=True,
                packet=dict(self.lease),
                packet_schema="writer_lease.schema.json",
            )
        )
        self.assertTrue(any("does not authorize" in reason for reason in reasons), reasons)

    def test_every_non_authorization_schema_is_refused(self):
        # The property, not the one schema that was reported. Any schema in
        # schemas/ that is not a delegation or handoff must be refused.
        for schema in sorted(p.name for p in (ROOT / "schemas").glob("*.json")):
            with self.subTest(schema=schema):
                reasons = self.pep._packet_admission(
                    ToolRequest(
                        agent=CHIEF,
                        action="read",
                        resource="x",
                        owner_brain="APEX",
                        packet_schema=schema,
                    )
                )
                if schema in AUTHORIZATION_SCHEMAS:
                    self.assertEqual(reasons, [])
                else:
                    self.assertTrue(reasons, f"{schema} was accepted as an authorization")

    def test_a_specialist_cannot_read_a_connector_directly(self):
        # `packet_only_no_direct_connectors` is a statement about reads too.
        # Only mutations were guarded, so a direct mount read was allowed.
        # Both must be REGISTERED mounts, so the denial proves the connector
        # policy fired rather than the registration check.
        for resource in ("mount:gdrive", "mount:github"):
            with self.subTest(resource=resource):
                decision = self.pep.evaluate(
                    ToolRequest(
                        agent=SPECIALIST, action="read", resource=resource, owner_brain="APEX"
                    )
                )
                self.assertFalse(decision.allowed)
                self.assertTrue(
                    any("may not touch connector" in reason for reason in decision.reasons),
                    decision.reasons,
                )

    def test_an_unresolvable_resource_is_refused_not_waved_through(self):
        # Ownership resolution returning None was treated as "no objection", so
        # the brain lock held only over resources whose names happened to match
        # a manifest prefix. Anything else passed on the caller's declaration.
        decision = self.pep.evaluate(
            ToolRequest(
                agent=SPECIALIST, action="read", resource="somewhere/else", owner_brain="APEX"
            )
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(any("cannot resolve which brain owns" in r for r in decision.reasons))

    def test_a_brain_owned_repository_path_resolves_to_its_brain(self):
        # The reported case: brains/jeos/agents.toml is plainly JEOS material
        # but carries none of the declared namespace prefixes, so it resolved to
        # nothing and an APEX specialist reading it passed.
        self.assertEqual(self.pep._resource_owner("brains/jeos/agents.toml"), "JEOS")
        self.assertEqual(self.pep._resource_owner("brains/apex/agents.toml"), "APEX")
        decision = self.pep.evaluate(
            ToolRequest(
                agent=SPECIALIST,
                action="read",
                resource="brains/jeos/agents.toml",
                owner_brain="APEX",
            )
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(any("belongs to 'JEOS'" in r for r in decision.reasons))

    def test_shared_repository_surfaces_stay_readable(self):
        # Fail-closed on unresolvable ownership is only safe because the neutral
        # set is declared. Without it, a specialist could not read the contract
        # that defines the classification it is being held to.
        for prefix in BRAIN_NEUTRAL_PREFIXES:
            with self.subTest(prefix=prefix):
                self.assertEqual(
                    self.pep._brain_lock(
                        ToolRequest(
                            agent=SPECIALIST, action="read", resource=prefix, owner_brain="APEX"
                        )
                    ),
                    [],
                )

    def test_mutation_classification_is_an_allowlist_not_a_denylist(self):
        # The defect's shape: MUTATING_ACTION_VERBS was a denylist, so any verb
        # nobody enumerated read as a read. `edit_file` and `move_file` are
        # tools the configured filesystem mount actually exposes, and neither
        # `edit` nor `move` was listed -- so they skipped every mutation
        # control. Extending the list by two would fix the instance and leave
        # the class, so the classification is inverted instead.
        for action in ("edit_file", "move_file", "rename_thing", "frobnicate", "chmod", "exec"):
            with self.subTest(action=action):
                self.assertTrue(
                    self.pep._is_mutating(
                        ToolRequest(agent=CHIEF, action=action, resource="APEX/Strategy-Campaigns")
                    ),
                    f"{action!r} was classified as a read",
                )

    def test_every_documented_mutating_verb_still_classifies_as_mutating(self):
        for verb in MUTATING_ACTION_VERBS:
            with self.subTest(verb=verb):
                self.assertTrue(
                    self.pep._is_mutating(
                        ToolRequest(agent=CHIEF, action=f"{verb}_thing", resource="x")
                    )
                )

    def test_genuine_reads_are_still_reads(self):
        # The inversion must not classify everything as a mutation; a rule that
        # denies every request is an outage, not enforcement.
        for action in ("read_text_file", "list_directory", "get_file_info", "search_files"):
            with self.subTest(action=action):
                self.assertFalse(
                    self.pep._is_mutating(
                        ToolRequest(agent=CHIEF, action=action, resource="docs/README.md")
                    )
                )

    def test_path_traversal_cannot_launder_a_brain_owned_resource(self):
        # `scripts/../brains/jeos/agents.toml` matched the `scripts/` neutral
        # prefix while a filesystem executor resolving it opens the JEOS
        # manifest. The policy and the executor disagreed about what the
        # resource was, which makes every prefix comparison meaningless.
        laundered = "scripts/../brains/jeos/agents.toml"
        self.assertEqual(self.pep._resource_owner(laundered), "JEOS")
        self.assertFalse(self.pep._is_brain_neutral(laundered))
        decision = self.pep.evaluate(
            ToolRequest(agent=SPECIALIST, action="read", resource=laundered, owner_brain="APEX")
        )
        self.assertFalse(decision.allowed)

    def test_a_resource_escaping_the_repository_is_refused(self):
        for resource in ("../../etc/passwd", "docs/../../outside", "/etc/passwd"):
            with self.subTest(resource=resource):
                self.assertTrue(self.pep._escapes_the_tree(resource))
                decision = self.pep.evaluate(
                    ToolRequest(
                        agent=SPECIALIST, action="read", resource=resource, owner_brain="APEX"
                    )
                )
                self.assertFalse(decision.allowed)

    def test_connector_handles_are_not_treated_as_paths(self):
        # `mount:filesystem` must not be normpath'd into something else.
        self.assertEqual(self.pep._canonical_resource("mount:filesystem"), "mount:filesystem")
        self.assertFalse(self.pep._escapes_the_tree("mount:filesystem"))

    def test_a_canonical_read_requires_a_delegation(self):
        # AGENTS.md confines packetless direct invocation to current-message
        # text. Reading another specialist's canonical source is not that.
        #
        # `docs/README.md` used to be in this list and has been moved to
        # `test_brain_neutral_reads_have_a_lawful_path`: requiring a delegation
        # for a brain-neutral surface was a deadlock rather than a control,
        # because no schema-valid packet can name a repository path.
        for resource in ("APEX/Strategy-Campaigns", "APEX/Intel-Sources"):
            with self.subTest(resource=resource):
                decision = self.pep.evaluate(
                    ToolRequest(
                        agent=SPECIALIST, action="read", resource=resource, owner_brain="APEX"
                    )
                )
                self.assertFalse(decision.allowed, f"{resource} was readable with no delegation")
                self.assertTrue(
                    any("requires a validated delegation" in r for r in decision.reasons),
                    decision.reasons,
                )

    def test_brain_neutral_reads_have_a_lawful_path(self):
        # All three branches denied before this: no packet -> "requires a
        # validated delegation"; a valid delegation -> "packet does not
        # authorize"; a delegation naming the path -> PacketGuard rejects the
        # namespace as outside private memory and roundtable. A specialist could
        # not read AGENTS.md, the contract defining its own behaviour.
        for resource in ("docs/README.md", "AGENTS.md", "config/mcp_mounts.toml", "schemas/"):
            with self.subTest(resource=resource):
                decision = self.pep.evaluate(
                    ToolRequest(
                        agent=SPECIALIST, action="read", resource=resource, owner_brain="APEX"
                    )
                )
                self.assertTrue(decision.allowed, f"{resource}: {decision.reasons}")

    def test_the_neutral_exemption_does_not_reach_past_the_neutral_set(self):
        # The exemption is the narrow kind: declared neutral prefixes, matched
        # after normalization, on reads only. A traversal that resolves into a
        # brain's material is not neutral however it is spelled, and a connector
        # handle is not a repository path.
        for resource in (
            "scripts/../brains/jeos/agents.toml",
            "mount:gdrive",
            "connector:unregistered",
            "JEOS/Weekly",
            "../../etc/passwd",
        ):
            with self.subTest(resource=resource):
                decision = self.pep.evaluate(
                    ToolRequest(
                        agent=SPECIALIST, action="read", resource=resource, owner_brain="APEX"
                    )
                )
                self.assertFalse(decision.allowed, f"{resource} was readable with no delegation")

    def test_a_neutral_write_is_not_exempt(self):
        # The exemption is for reads. A mutation of a neutral surface still
        # needs a packet and a lease like any other.
        decision = self.pep.evaluate(
            ToolRequest(
                agent=SPECIALIST,
                action="write",
                resource="docs/README.md",
                owner_brain="APEX",
                mutating=True,
            )
        )
        self.assertFalse(decision.allowed)

    def test_the_chief_reads_canonical_resources_without_a_delegation(self):
        # It issues them; requiring one of itself would deadlock the corps.
        self.assertEqual(
            self.pep._packet_admission(
                ToolRequest(
                    agent=CHIEF,
                    action="read",
                    resource="APEX/Strategy-Campaigns",
                    owner_brain="APEX",
                )
            ),
            [],
        )

    def test_a_read_word_inside_a_mutating_action_does_not_make_it_a_read(self):
        # The round-7 fix inverted the list and kept substring matching, which
        # fails open just as badly in the other direction. `delete_thread`
        # contains "read". So does `spreadsheet_update`. `update_status`
        # contains "status"; `remove_from_list` contains "list". All four
        # classified as reads and skipped every mutation control.
        for action in (
            "delete_thread",
            "spreadsheet_update",
            "update_status",
            "remove_from_list",
            "list_purge",
        ):
            with self.subTest(action=action):
                self.assertTrue(
                    self.pep._is_mutating(
                        ToolRequest(agent=CHIEF, action=action, resource="mount:filesystem")
                    ),
                    f"{action!r} classified as a read",
                )

    def test_a_self_signed_instruction_is_not_an_instruction(self):
        # `launch_key_path` was caller-controlled, so a caller could write its
        # own key, sign a financial_transaction with it, point the request at
        # it, and be believed. Verifying a signature against a key the signer
        # chose proves only that the signer can sign.
        with tempfile.TemporaryDirectory() as tmp:
            attacker_key = Path(tmp) / "attacker_key"
            attacker_key.write_bytes(b"attacker-controlled")
            forged = instruction_grant("financial_transaction", "account", attacker_key)
            self.assertFalse(
                hasattr(
                    ToolRequest(agent=CHIEF, action="x", resource="y"),
                    "launch_key_path",
                ),
                "the trust anchor must not be settable from the request",
            )
            # A PEP anchored to a *different* key must refuse it.
            trusted_key = Path(tmp) / "trusted_key"
            trusted_key.write_bytes(b"the-real-key")
            pep = PolicyEnforcementPoint(ROOT, launch_key_path=trusted_key, clock=lambda: NOW)
            reasons = pep._high_impact_boundary(
                ToolRequest(
                    agent=CHIEF,
                    action="financial_transaction",
                    resource="account",
                    instruction_grant=forged,
                )
            )
            self.assertTrue(any("signature is invalid" in r for r in reasons), reasons)

    def test_a_mutation_without_a_resource_id_is_denied(self):
        # A lease and packet issued for record A authorized writing record B
        # under the same write target, because omitting the identifier skipped
        # record-level matching in both places. An optional field the checks
        # only honour when supplied is an opt-out.
        reasons = self.pep._writer_lease(
            ToolRequest(
                agent=CHIEF,
                action="write",
                resource="APEX/Strategy-Campaigns",
                owner_brain="APEX",
                mutating=True,
                lease=self.lease,
                resource_id=None,
            )
        )
        self.assertTrue(any("declares no resource_id" in r for r in reasons), reasons)

    def test_a_delegation_does_not_authorize_a_resource_it_does_not_name(self):
        # Requiring a packet for canonical reads stopped packetless access but
        # accepted any valid same-brain packet, so a delegation scoped to
        # Strategy-Campaigns authorized reading another specialist's
        # Intel-Sources. Holding any delegation would be holding all of them.
        scoped = {
            "agent": SPECIALIST,
            "owner_brain": "APEX",
            "allowed_read_namespaces": ["APEX::Strategy-Campaigns::apex_war_architect"],
        }
        reasons = self.pep._packet_scope_errors(
            ToolRequest(
                agent=SPECIALIST,
                action="read",
                resource="APEX/Intel-Sources",
                owner_brain="APEX",
                packet=scoped,
            )
        )
        self.assertTrue(any("does not authorize" in r for r in reasons), reasons)

    def test_a_delegation_authorizes_the_resource_it_does_name(self):
        # The accept path: scope binding must not deny the assignment itself.
        #
        # The resource here used to be `APEX/Strategy-Campaigns` -- the PARENT
        # of the namespace the scope names, not the namespace itself. It passed
        # only through a reverse-prefix branch that let a declared scope
        # authorize any ancestor of itself, so this test was asserting the
        # widening rather than the accept path. The resource it does name is
        # the one the scope names.
        scoped = {
            "agent": SPECIALIST,
            "owner_brain": "APEX",
            "allowed_read_namespaces": ["APEX::Strategy-Campaigns::apex_war_architect"],
        }
        self.assertEqual(
            self.pep._packet_scope_errors(
                ToolRequest(
                    agent=SPECIALIST,
                    action="read",
                    resource="APEX/Strategy-Campaigns/apex_war_architect",
                    owner_brain="APEX",
                    packet=scoped,
                )
            ),
            [],
        )

    def test_the_chief_may_execute_a_specialist_packet_while_holding_the_lease(self):
        # The deadlock: every valid packet names the specialist, the specialist
        # is blocked by _lifecycle_stage, and requiring the chief to be the
        # addressee blocked the only actor permitted to execute. Authority comes
        # from the lease, which the registry verifies.
        # A realistic handoff: it proposes the write it is asking to have
        # executed, which is what binds it to this target.
        packet = {
            "agent": SPECIALIST,
            "owner_brain": "APEX",
            "writer_agent": CHIEF,
            # `target`, per the handoff schema. This fixture said `write_target`,
            # so the scope check never saw a proposed write and the test passed
            # for a different reason than it claimed.
            "proposed_writes": [{"target": "APEX/Strategy-Campaigns", "operation": "append"}],
        }
        self.assertEqual(
            self.pep._packet_scope_errors(
                ToolRequest(
                    agent=CHIEF,
                    action="write",
                    resource="APEX/Strategy-Campaigns",
                    owner_brain="APEX",
                    mutating=True,
                    packet=packet,
                    lease=self.lease,
                    resource_id="campaign-alpha",
                    operation="append",
                )
            ),
            [],
        )

    def test_a_packet_proposing_append_does_not_authorize_replace(self):
        # Target, resource id, brain, and lease can all match while the
        # executed operation is strictly more destructive than the one the
        # validated packet proposed. Binding everything about *where* a write
        # lands and nothing about *what it does* is not a bound authorization.
        packet = {
            "agent": SPECIALIST,
            "owner_brain": "APEX",
            "writer_agent": CHIEF,
            # `target`, per the handoff schema. This fixture said `write_target`,
            # so the scope check never saw a proposed write and the test passed
            # for a different reason than it claimed.
            "proposed_writes": [{"target": "APEX/Strategy-Campaigns", "operation": "append"}],
        }
        reasons = self.pep._packet_scope_errors(
            ToolRequest(
                agent=CHIEF,
                action="write",
                resource="APEX/Strategy-Campaigns",
                owner_brain="APEX",
                mutating=True,
                packet=packet,
                lease=self.lease,
                resource_id="campaign-alpha",
                operation="replace",
            )
        )
        self.assertTrue(any("proposes" in r for r in reasons), reasons)

    def test_a_read_only_delegation_does_not_authorize_a_write(self):
        # The two allow-lists were unioned, so a delegation granting only
        # allowed_read_namespaces conferred write authority when paired with a
        # genuine lease. The lease proves exclusive execution; it does not
        # prove the bounded assignment permitted a write.
        read_only = {
            "agent": SPECIALIST,
            "owner_brain": "APEX",
            "writer_agent": CHIEF,
            "allowed_read_namespaces": ["APEX::Strategy-Campaigns::apex_war_architect"],
            "allowed_write_targets": [],
        }
        reasons = self.pep._packet_scope_errors(
            ToolRequest(
                agent=CHIEF,
                action="write",
                resource="APEX/Strategy-Campaigns",
                owner_brain="APEX",
                mutating=True,
                packet=read_only,
                lease=self.lease,
                resource_id="campaign-alpha",
            )
        )
        self.assertTrue(any("no scope permitting a write" in r for r in reasons), reasons)

    def test_an_unscoped_handoff_does_not_authorize_any_same_brain_resource(self):
        # "Declares no scope" was reaching an unconditional success path, so a
        # read-only handoff authorized any same-brain canonical resource.
        bare = {"agent": SPECIALIST, "owner_brain": "APEX"}
        reasons = self.pep._packet_scope_errors(
            ToolRequest(
                agent=SPECIALIST,
                action="read",
                resource="APEX/Intel-Sources",
                owner_brain="APEX",
                packet=bare,
            )
        )
        self.assertTrue(any("absent scope is not unrestricted" in r for r in reasons), reasons)

    def test_a_handoff_is_bound_to_its_own_memory_namespace(self):
        # Same correction as the delegation accept path above: bound to its own
        # namespace means that namespace, not the collection containing it.
        scoped = {
            "agent": SPECIALIST,
            "owner_brain": "APEX",
            "memory_namespace": "APEX::Strategy-Campaigns::apex_war_architect",
        }
        self.assertEqual(
            self.pep._packet_scope_errors(
                ToolRequest(
                    agent=SPECIALIST,
                    action="read",
                    resource="APEX/Strategy-Campaigns/apex_war_architect",
                    owner_brain="APEX",
                    packet=scoped,
                )
            ),
            [],
        )

    def test_the_chief_may_not_execute_a_packet_it_holds_no_lease_for(self):
        # The exemption is the lease, not the identity. Without one, the
        # addressee check applies to the chief like anyone else.
        packet = {"agent": SPECIALIST, "owner_brain": "APEX", "writer_agent": SPECIALIST}
        reasons = self.pep._packet_scope_errors(
            ToolRequest(
                agent=CHIEF,
                action="read",
                resource="APEX/Strategy-Campaigns",
                owner_brain="APEX",
                packet=packet,
            )
        )
        self.assertTrue(any("addresses" in r for r in reasons), reasons)

    def test_a_chief_mutation_must_state_its_brain(self):
        # `_brain_lock` exempts the chief as the sole cross-brain agent, which
        # left both brain comparisons conditional on a field the chief could
        # omit. A JEOS handoff paired with a genuine APEX lease for the same
        # resource_id then authorized an APEX write -- cross-brain leakage
        # through the one agent permitted to see both sides.
        reasons = self.pep._writer_lease(
            ToolRequest(
                agent=CHIEF,
                action="write",
                resource="APEX/Strategy-Campaigns",
                owner_brain=None,
                mutating=True,
                lease=self.lease,
                resource_id="campaign-alpha",
            )
        )
        self.assertTrue(any("no owner_brain" in r for r in reasons), reasons)

    def test_an_opposite_brain_packet_cannot_ride_an_unstated_brain(self):
        reasons = self.pep._packet_scope_errors(
            ToolRequest(
                agent=CHIEF,
                action="write",
                resource="APEX/Strategy-Campaigns",
                owner_brain=None,
                mutating=True,
                packet={"agent": SPECIALIST, "owner_brain": "JEOS", "writer_agent": CHIEF},
                lease=self.lease,
                resource_id="campaign-alpha",
            )
        )
        self.assertTrue(any("cannot be matched" in r for r in reasons), reasons)

    def test_a_genuine_registry_lease_survives_packet_admission(self):
        # The fail-shut break. Deriving the guard's lease ledger from the
        # registry started feeding it real `schema_version: "2.1"` leases, whose
        # schema pins "2.0" -- so admission rejected EVERY mutation backed by
        # the real LeaseRegistry, and `_writer_lease`'s later tolerance cannot
        # lift an error raised at admission. A gate that denies all legitimate
        # work is as broken as one that permits illegitimate work.
        from scripts.packet_guard import PacketGuard

        raw = PacketGuard(ROOT).validate_lease_ledger([self.lease])
        self.assertTrue(
            any("expected const '2.0'" in error for error in raw),
            "this test assumes the 2.1-vs-2.0 mismatch is still present upstream",
        )
        errors = self.pep._packet_admission(
            ToolRequest(
                agent=CHIEF,
                action="read",
                resource="APEX/Strategy-Campaigns",
                owner_brain="APEX",
            )
        )
        self.assertFalse(
            any("expected const '2.0'" in error for error in errors),
            f"the registry's own lease must not fail admission: {errors}",
        )

    def test_a_read_only_handoff_does_not_authorize_a_write(self):
        # Two bugs in one line, both mine: the field is `target`, not
        # `write_target`, so no proposed write was ever found -- and the
        # mutating path then fell through to `memory_namespace`, which is where
        # a specialist READS. A read-only handoff plus a genuine lease
        # authorized a replace.
        read_only = {
            "agent": SPECIALIST,
            "owner_brain": "APEX",
            "writer_agent": CHIEF,
            "memory_namespace": "APEX::Strategy-Campaigns::apex_war_architect",
        }
        reasons = self.pep._packet_scope_errors(
            ToolRequest(
                agent=CHIEF,
                action="write",
                resource="APEX/Strategy-Campaigns",
                owner_brain="APEX",
                mutating=True,
                packet=read_only,
                lease=self.lease,
                resource_id="campaign-alpha",
                operation="replace",
            )
        )
        self.assertTrue(any("no scope permitting a write" in r for r in reasons), reasons)

    def test_a_handoff_proposing_a_write_uses_the_schema_field_name(self):
        # `target` is what the handoff schema requires. Reading `write_target`
        # meant proposed writes were invisible.
        proposing = {
            "agent": SPECIALIST,
            "owner_brain": "APEX",
            "writer_agent": CHIEF,
            "memory_namespace": "APEX::Strategy-Campaigns::apex_war_architect",
            "proposed_writes": [{"target": "APEX/Strategy-Campaigns", "operation": "replace"}],
        }
        self.assertEqual(
            self.pep._packet_scope_errors(
                ToolRequest(
                    agent=CHIEF,
                    action="write",
                    resource="APEX/Strategy-Campaigns",
                    owner_brain="APEX",
                    mutating=True,
                    packet=proposing,
                    lease=self.lease,
                    resource_id="campaign-alpha",
                    operation="replace",
                )
            ),
            [],
        )

    def test_a_scalar_grant_denies_rather_than_raising(self):
        # The packet path was type-checked one round earlier and both grant
        # paths were left alone. `.get()` on a truthy scalar raises.
        for field_name in ("instruction_grant", "launch_grant"):
            with self.subTest(field=field_name):
                request = ToolRequest(
                    agent=CHIEF,
                    action="financial_transaction",
                    resource="mount:civil3d",
                    owner_brain="APEX",
                    mutating=True,
                    **{field_name: 1},
                )
                decision = self.pep.evaluate(request)  # must not raise
                self.assertFalse(decision.allowed)
                self.assertTrue(
                    any("must be an object" in r for r in decision.reasons), decision.reasons
                )

    def test_a_semantic_packet_defect_survives_the_lease_version_tolerance(self):
        # The worst defect in this change set, and it was introduced by the
        # previous round's own repair. PacketGuard returns the lease-ledger
        # error and SHORT-CIRCUITS, so a delegation carrying another
        # specialist's memory namespace produced exactly one error -- the
        # version mismatch -- which the tolerance filter then deleted. The
        # fail-shut fix had become a fail-open bypass.
        from copy import deepcopy

        from tests.test_packet_contracts import PacketContractTests

        PacketContractTests.setUpClass()
        instance = PacketContractTests(
            "test_valid_delegation_and_handoff_are_bound_to_lease_and_origin"
        )
        delegation, _ = instance.v21_readonly_pair()
        tampered = deepcopy(delegation)
        tampered["memory_namespace"] = "JEOS::Weekly::jeos_reflection_forge"

        errors = self.pep._guard_errors(
            ToolRequest(
                agent=SPECIALIST,
                action="read",
                resource="APEX/Strategy-Campaigns",
                owner_brain="APEX",
                packet=tampered,
            )
        )
        self.assertTrue(
            any("memory namespace" in error for error in errors),
            f"a semantic defect was suppressed by the version tolerance: {errors}",
        )

    def test_an_explicit_empty_operation_allowlist_authorizes_nothing(self):
        packet = {
            "agent": SPECIALIST,
            "owner_brain": "APEX",
            "writer_agent": CHIEF,
            "allowed_write_targets": ["APEX/Strategy-Campaigns"],
            "mutation_contract": {"allowed_operations": []},
        }
        for operation in ("replace", "disable", "destroy"):
            with self.subTest(operation=operation):
                reasons = self.pep._packet_scope_errors(
                    ToolRequest(
                        agent=CHIEF,
                        action="write",
                        resource="APEX/Strategy-Campaigns",
                        owner_brain="APEX",
                        mutating=True,
                        packet=packet,
                        lease=self.lease,
                        resource_id="campaign-alpha",
                        operation=operation,
                    )
                )
                self.assertTrue(
                    any("authorizes\nno mutation" in r or "authorizes " in r for r in reasons),
                    reasons,
                )

    def test_an_unregistered_mount_handle_is_refused_for_every_principal(self):
        # The chief exemption returned before checking registration, so handles
        # naming nothing in config/mcp_mounts.toml were allowed outright.
        for resource in ("mount:shadow_it_server", "connector:unregistered"):
            for agent in (CHIEF, SPECIALIST):
                with self.subTest(resource=resource, agent=agent):
                    decision = self.pep.evaluate(
                        ToolRequest(
                            agent=agent, action="read", resource=resource, owner_brain="APEX"
                        )
                    )
                    self.assertFalse(decision.allowed)
                    self.assertTrue(
                        any("names no mount registered" in r for r in decision.reasons),
                        decision.reasons,
                    )

    def test_the_registry_cannot_be_rewritten_through_what_it_returns(self):
        # `issue()` and `active_lease()` handed out the stored object, so the
        # authoritative source policy enforcement consults could be edited by
        # anyone holding an issued lease.
        from runtime.writer_lease import canonical_key

        key = canonical_key("APEX", "APEX/Strategy-Campaigns", "campaign-alpha")
        issued = self.registry.active_lease(key)
        issued["writer_agent"] = "impostor"
        issued["status"] = "forged"
        fresh = self.registry.active_lease(key)
        self.assertEqual(fresh["writer_agent"], CHIEF)
        self.assertEqual(fresh["status"], "active")

    def test_a_lawful_write_bearing_packet_is_not_denied_by_the_semantic_pass(self):
        # The third alternation in one area. Round 11 made registry leases fail
        # admission (shut); round 12 suppressed the guard's short-circuit and
        # let semantic defects through (open); round 12's two-pass repair then
        # retained "write-bearing packet requires the active writer-lease
        # ledger" from the deliberately ledger-free pass -- so NO governed
        # mutation could pass at all (shut again).
        #
        # This test itself then encoded the FOURTH state. It named
        # `writer_lease_id = "lease-1"`, an id no registry ever issued, and
        # asserted that packet must not be denied -- which held only because the
        # bound pass short-circuited before `_lease_match_errors` could compare
        # the packet against the ledger. It was asserting the fail-open. The
        # fixture now names the lease the registry actually issued, so the test
        # means what its name says: a LAWFUL packet passes.
        from copy import deepcopy

        from tests.test_packet_contracts import PacketContractTests

        PacketContractTests.setUpClass()
        instance = PacketContractTests(
            "test_valid_delegation_and_handoff_are_bound_to_lease_and_origin"
        )
        delegation, _ = instance.v21_readonly_pair()
        write_bearing = deepcopy(delegation)
        write_bearing.update(
            {
                "approval_level": "L2",
                "allowed_write_targets": [self.lease["write_target"]],
                "writer_agent": self.lease["writer_agent"],
                "writer_lease_id": self.lease["lease_id"],
                "mission_id": self.lease["mission_id"],
                "resource_id": self.lease["resource_id"],
                "owner_brain": self.lease["owner_brain"],
                "mutation_contract": {
                    "allowed_operations": ["upsert"],
                    "require_expected_version": True,
                    "require_idempotency_key": True,
                },
            }
        )
        errors = self.pep._guard_errors(
            ToolRequest(
                agent=SPECIALIST,
                action="read",
                resource="APEX/Strategy-Campaigns",
                owner_brain="APEX",
                packet=write_bearing,
            )
        )
        self.assertEqual(errors, [], "a lawful write-bearing packet must not be denied")

    def test_the_governance_mounts_inspection_tools_are_reads(self):
        # Three of that mount's five tools were classified as mutations and
        # denied for lacking a packet, lease, and launch grant -- on the one
        # mount that is deliberately grant-free and open to every agent.
        for action in ("validate_packet", "validate_handoff_return", "verify_audit_ledger"):
            with self.subTest(action=action):
                self.assertFalse(
                    self.pep._is_mutating(
                        ToolRequest(agent=CHIEF, action=action, resource="mount:governance")
                    )
                )

    def test_admitting_a_delegation_is_still_a_mutation(self):
        # The accept path must not swallow the one governance tool that does
        # change state.
        self.assertTrue(
            self.pep._is_mutating(
                ToolRequest(
                    agent=CHIEF, action="admit_delegation_packet", resource="mount:governance"
                )
            )
        )

    def test_the_chief_still_reaches_connectors(self):
        # The sole cross-brain agent performs connector work on the corps'
        # behalf; denying it too would be an outage, not a control.
        self.assertEqual(
            self.pep._connector_policy(
                ToolRequest(agent=CHIEF, action="read", resource="mount:gdrive")
            ),
            [],
        )


class BoundaryDataTests(unittest.TestCase):
    """The boundary list must match the contract it claims to implement."""

    def test_high_impact_list_matches_agents_md(self):
        # Fragments from section 9 of the JOEYYY constitution, which explicitly
        # superseded the earlier six-item list: "Section 9's live-approval list
        # supersedes the prior six-item explicit-instruction list." The wording
        # moved with it -- "credential or access-control change" became
        # "access-control or credential changes" -- so matching the old phrasing
        # failed against a contract that had grown STRICTER, not weaker.
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8").lower()
        for fragment in (
            "irreversible bulk deletion",
            "financial transaction",
            "access-control or credential change",
            "signing, sealing, or certifying",
            "binding legal commitment",
            "public publication",
            "permit or agency submission",
            "scheduled-task creation or deletion",
            "separation governance",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, text)
        self.assertEqual(len(HIGH_IMPACT_ACTIONS), 9)


class FifteenthPassRegressionTests(unittest.TestCase):
    """The two fail-opens the fifteenth review pass found, both reproduced first."""

    def setUp(self):
        self.registry, self.lease = registry_and_lease()
        self.pep = PolicyEnforcementPoint(ROOT, registry=self.registry, clock=lambda: NOW)

    def _write_bearing_delegation(self, **overrides):
        """A schema-valid 2.1 delegation that carries a write."""
        from tests.test_packet_contracts import PacketContractTests

        PacketContractTests.setUpClass()
        packet, _ = PacketContractTests().v21_readonly_pair()
        packet = json.loads(json.dumps(packet))  # deep copy without the import
        packet["mutation_contract"]["allowed_operations"] = ["upsert"]
        packet.update(
            {
                "writer_lease_id": self.lease["lease_id"],
                "mission_id": self.lease["mission_id"],
                "resource_id": self.lease["resource_id"],
                "owner_brain": self.lease["owner_brain"],
                "writer_agent": self.lease["writer_agent"],
                "allowed_write_targets": [self.lease["write_target"]],
            }
        )
        packet.update(overrides)
        return packet

    def _request(self, packet):
        return ToolRequest(
            agent=CHIEF,
            action="write",
            resource=self.lease["write_target"],
            owner_brain=self.lease["owner_brain"],
            mutating=True,
            packet=packet,
            packet_schema="delegation_packet.schema.json",
            lease=self.lease,
            resource_id=self.lease["resource_id"],
        )

    def test_a_forged_writer_lease_id_is_refused(self):
        # The fail-open: PacketGuard.validate() returns at the first lease-ledger
        # error, so feeding it a genuine 2.1 lease against a schema pinned to
        # 2.0 meant `_lease_match_errors` -- the check that binds THIS packet to
        # THAT lease -- never ran, and the suppression rule then deleted the one
        # error that had been produced. A packet naming a lease that was never
        # issued was admitted.
        packet = self._write_bearing_delegation(writer_lease_id="never-issued")
        errors = self.pep._guard_errors(self._request(packet))
        self.assertTrue(
            any("not uniquely active" in error for error in errors),
            f"a packet naming an unissued lease must be refused: {errors}",
        )

    def test_a_foreign_mission_id_is_refused(self):
        # Same hole, different field: the packet claimed a mission the lease
        # does not cover, and target/resource/brain/writer all matched, so
        # `_writer_lease` had no objection either.
        packet = self._write_bearing_delegation(mission_id="mission-the-lease-excludes")
        errors = self.pep._guard_errors(self._request(packet))
        self.assertTrue(errors, "a packet bound to a foreign mission must be refused")

    def test_a_genuine_lease_and_matching_packet_still_pass(self):
        # The other direction, asserted in the same class as the fix. Every
        # previous repair here broke this or its opposite; a test that only
        # proves the gate shuts cannot tell a fix from a lockout.
        request = self._request(self._write_bearing_delegation())
        self.assertEqual(self.pep._guard_errors(request), [])
        self.assertEqual(self.pep._writer_lease(request), [])

    def test_reconciliation_covers_only_the_version_the_registry_issues(self):
        # Strictly narrower than the error filter it replaces: that filter
        # dropped "expected const '2.0'" whatever the offending value was, so a
        # lease claiming any version at all was tolerated.
        self.assertEqual(
            self.pep._reconciled_lease(self.lease)["schema_version"],
            "2.0",
        )
        invented = dict(self.lease, schema_version="9.9")
        self.assertEqual(self.pep._reconciled_lease(invented)["schema_version"], "9.9")
        # And it still fails the schema, so leaving it alone means denial rather
        # than a value that merely passes through unchanged.
        self.assertTrue(self.pep.guard.validate("writer_lease.schema.json", invented))

    def test_an_unissued_version_in_the_ledger_is_not_reconciled(self):
        # Asserted through the ledger rather than through `_writer_lease`: that
        # rule looks the lease up and reads the REGISTRY's copy, so a version a
        # caller invents never reaches validation there at all. The ledger is
        # where a stored lease's own version is consulted.
        tampered = dict(self.lease, schema_version="9.9")
        self.assertTrue(
            self.pep.guard.validate_lease_ledger([self.pep._reconciled_lease(tampered)]),
            "only the version the registry issues is reconciled; any other still fails",
        )
        self.assertEqual(
            self.pep.guard.validate_lease_ledger([self.pep._reconciled_lease(self.lease)]),
            [],
            "the registry's own lease must validate once reconciled",
        )

    def test_reconciliation_does_not_mutate_the_registry_copy(self):
        before = self.lease["schema_version"]
        self.pep._reconciled_lease(self.lease)
        self.assertEqual(self.lease["schema_version"], before)


class TargetlessRequestTests(unittest.TestCase):
    """A request that names nothing describes no decision, so nothing is allowed."""

    def setUp(self):
        self.pep = PolicyEnforcementPoint(ROOT, clock=lambda: NOW)

    def test_a_chief_read_with_no_resource_is_refused(self):
        # Reproduced exactly as reported: allowed=True with an EMPTY reason
        # tuple. `_brain_lock` and `_packet_admission` both exempt the chief,
        # and every remaining rule reads the resource -- so a blank one matched
        # no prefix and drew no objection from anything. The gate reported
        # approval having checked neither ownership nor mount registration.
        for blank in ("", "   ", "\t"):
            with self.subTest(resource=blank):
                decision = self.pep.evaluate(
                    ToolRequest(agent=CHIEF, action="read", resource=blank)
                )
                self.assertFalse(decision.allowed)
                self.assertTrue(any("declares no resource" in r for r in decision.reasons))

    def test_a_blank_action_is_refused_on_its_own_terms(self):
        # It was already denied, but only by accident: a blank action is
        # classified as mutating, so the lease rules happened to fire. Accident
        # is not enforcement, and the accident disappears the moment the
        # mutation classifier changes.
        decision = self.pep.evaluate(
            ToolRequest(agent=CHIEF, action="", resource="APEX/Strategy-Campaigns")
        )
        self.assertTrue(any("declares no action" in r for r in decision.reasons))

    def test_a_blank_agent_is_refused(self):
        decision = self.pep.evaluate(ToolRequest(agent="   ", action="read", resource="docs/"))
        self.assertTrue(any("declares no agent" in r for r in decision.reasons))

    def test_the_check_precedes_every_exemption(self):
        # Stated as its own property because the defect was not "a rule missed
        # this" but "every rule that could have caught it exempts the chief".
        # Ordering is the fix, so ordering is what is asserted.
        decision = self.pep.evaluate(ToolRequest(agent=CHIEF, action="read", resource=""))
        self.assertEqual(len(decision.reasons), 1)

    def test_a_fully_stated_chief_read_is_still_allowed(self):
        decision = self.pep.evaluate(
            ToolRequest(agent=CHIEF, action="read", resource="docs/README.md")
        )
        self.assertTrue(decision.allowed, decision.reasons)


class SixteenthPassRegressionTests(unittest.TestCase):
    """Findings from the sixteenth pass, each reproduced before it was fixed."""

    def _expired_registry(self):
        """A registry holding a lease that lapsed in REAL wall-clock time.

        Real time matters: PacketGuard compares against `datetime.now(UTC)`,
        not this point's injected clock, so a fixture expiring relative to the
        test clock does not reproduce the defect. The first attempt at this
        test did exactly that and proved nothing.
        """
        registry = LeaseRegistry()
        past = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=5)
        lease = registry.issue(
            mission_id="m-001",
            owner_brain="APEX",
            writer_agent=CHIEF,
            write_target="APEX/Strategy-Campaigns",
            resource_id="campaign-alpha",
            expected_state="One campaign row.",
            rollback="Delete by mission ID.",
            now=past,
            hours=1,
        )
        return registry, dict(lease)

    def test_a_lapsed_lease_does_not_deny_unrelated_work(self):
        # LeaseRegistry._expire() runs only inside issue(), so a lapsed lease
        # sits in _active until some unrelated issuance sweeps it. Feeding that
        # record to the guard made it report `active writer lease is expired`
        # for the LEDGER -- and validate() returns at the first ledger error, so
        # one stale lease denied every packet-backed operation in the corps.
        from scripts.packet_guard import PacketGuard

        registry, lease = self._expired_registry()
        self.assertTrue(
            PacketGuard(ROOT).validate_lease_ledger([dict(lease, schema_version="2.0")]),
            "this test assumes the lease is genuinely expired in real time",
        )
        pep = PolicyEnforcementPoint(ROOT, registry=registry)
        request = ToolRequest(
            agent=CHIEF, action="read", resource="docs/README.md", owner_brain="APEX"
        )
        self.assertEqual(pep._lease_ledger(request), [])
        self.assertEqual(PacketGuard(ROOT).validate_lease_ledger(pep._lease_ledger(request)), [])

    def test_a_lapsed_lease_still_authorizes_no_mutation(self):
        # The other direction. Dropping it from the ledger must not become a way
        # to write with it: _writer_lease checks expiry independently.
        registry, lease = self._expired_registry()
        pep = PolicyEnforcementPoint(ROOT, registry=registry)
        reasons = pep._writer_lease(
            ToolRequest(
                agent=CHIEF,
                action="write",
                resource="APEX/Strategy-Campaigns",
                owner_brain="APEX",
                mutating=True,
                lease=lease,
                resource_id="campaign-alpha",
            )
        )
        self.assertTrue(any("expired" in reason for reason in reasons), reasons)

    def test_a_live_lease_is_not_filtered_out(self):
        registry, live = registry_and_lease()
        pep = PolicyEnforcementPoint(ROOT, registry=registry, clock=lambda: NOW)
        ledger = pep._lease_ledger(
            ToolRequest(agent=CHIEF, action="read", resource="docs/", owner_brain="APEX")
        )
        self.assertEqual([entry["lease_id"] for entry in ledger], [live["lease_id"]])

    def test_a_malformed_expiry_is_kept_so_the_guard_rejects_it(self):
        # Dropping an unparseable expiry would hide a malformed lease; keeping
        # it lets the schema refuse it, which is the fail-closed outcome.
        pep = PolicyEnforcementPoint(ROOT, clock=lambda: NOW)
        self.assertFalse(pep._has_lapsed({"expires_at": "whenever"}))
        self.assertFalse(pep._has_lapsed({}))

    def _delegation(self, **overrides):
        from tests.test_packet_contracts import PacketContractTests

        PacketContractTests.setUpClass()
        packet, _ = PacketContractTests().v21_readonly_pair()
        packet = json.loads(json.dumps(packet))
        packet.update(overrides)
        return packet

    def _admit(self, packet, pep=None):
        # `resource_id` supplied: a packet-backed canonical read must name the
        # record it reads, or the packet's own `resource_id` cannot be matched
        # against anything. These fixtures omitted it and passed, which is what
        # made the omission an opt-out rather than an oversight.
        return (pep or self.pep)._packet_admission(
            ToolRequest(
                agent=SPECIALIST,
                action="read",
                resource="APEX/Strategy-Campaigns/apex_war_architect",
                owner_brain="APEX",
                packet=packet,
                packet_schema="delegation_packet.schema.json",
                resource_id=packet.get("resource_id"),
            )
        )

    def setUp(self):
        self.registry, self.lease = registry_and_lease()
        self.pep = PolicyEnforcementPoint(ROOT, registry=self.registry)

    def test_an_expired_delegation_deadline_is_refused(self):
        # `deadline` is declared in the schema and nothing parsed it -- not
        # PacketGuard, not this module -- so a time-bounded assignment stayed
        # reusable indefinitely.
        errors = self._admit(self._delegation(deadline="2020-01-01T00:00:00Z"))
        self.assertTrue(any("no longer live" in error for error in errors), errors)

    def test_an_unparseable_deadline_is_refused(self):
        errors = self._admit(self._delegation(deadline="not-a-date"))
        self.assertTrue(any("not a parseable timestamp" in error for error in errors), errors)

    def test_a_null_deadline_is_an_unbounded_assignment_not_a_defect(self):
        # The schema declares the field nullable. Treating absence as expiry
        # would deny every delegation that does not state a bound.
        self.assertEqual(self._admit(self._delegation(deadline=None)), [])

    def test_a_future_deadline_is_admitted(self):
        ahead = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)
        deadline = ahead.isoformat().replace("+00:00", "Z")
        self.assertEqual(self._admit(self._delegation(deadline=deadline)), [])

    def test_a_scope_matches_in_either_spelling(self):
        # Only the DECLARED entry was normalized, so a resource named in
        # namespace form could never match a scope that authorized it -- and the
        # denial printed two strings that looked identical, because the
        # difference was the separator being compared.
        packet = self._delegation()
        for resource in (
            "APEX::Strategy-Campaigns::apex_war_architect",
            "APEX/Strategy-Campaigns/apex_war_architect",
        ):
            with self.subTest(resource=resource):
                errors = self.pep._packet_admission(
                    ToolRequest(
                        agent=SPECIALIST,
                        action="read",
                        resource=resource,
                        owner_brain="APEX",
                        packet=packet,
                        packet_schema="delegation_packet.schema.json",
                        resource_id=packet.get("resource_id"),
                    )
                )
                self.assertEqual(errors, [], f"{resource}: {errors}")

    def test_spelling_symmetry_does_not_widen_scope(self):
        # Accepting both spellings must not make a scope cover a namespace it
        # does not name.
        packet = self._delegation()
        for resource in (
            "APEX::Strategy-Campaigns::apex_intelligence_forge",
            "APEX/Intel-Sources",
        ):
            with self.subTest(resource=resource):
                errors = self.pep._packet_admission(
                    ToolRequest(
                        agent=SPECIALIST,
                        action="read",
                        resource=resource,
                        owner_brain="APEX",
                        packet=packet,
                        packet_schema="delegation_packet.schema.json",
                    )
                )
                self.assertTrue(errors, f"{resource} was authorized by a scope not naming it")


class SeventeenthPassRegressionTests(unittest.TestCase):
    """Three scope-widening defects and a control that could not fire."""

    def setUp(self):
        self.registry, self.lease = registry_and_lease()
        self.pep = PolicyEnforcementPoint(ROOT, registry=self.registry, clock=lambda: NOW)

    def test_a_named_neutral_file_does_not_match_its_siblings(self):
        # BRAIN_NEUTRAL_PREFIXES holds both directories and named files, and
        # prefix matching was applied to both -- so `AGENTS.md` also matched
        # `AGENTS.md.private`, `README.md.jeos`, and `CLAUDE.md-secrets`.
        # Since the previous round made a neutral read an EXEMPTION from packet
        # admission rather than only a classification, that let a specialist
        # read those files packetlessly.
        for sibling in ("AGENTS.md.private", "README.md.jeos", "CLAUDE.md-secrets", "AGENTS.mdx"):
            with self.subTest(resource=sibling):
                self.assertFalse(self.pep._is_brain_neutral(sibling))
                decision = self.pep.evaluate(
                    ToolRequest(
                        agent=SPECIALIST, action="read", resource=sibling, owner_brain="APEX"
                    )
                )
                self.assertFalse(decision.allowed, f"{sibling}: {decision.reasons}")

    def test_the_named_neutral_files_themselves_still_resolve(self):
        # The other direction: tightening file matching must not deny the files
        # the neutral set exists to permit.
        for neutral in ("AGENTS.md", "README.md", "CLAUDE.md"):
            with self.subTest(resource=neutral):
                self.assertTrue(self.pep._is_brain_neutral(neutral))

    def test_neutral_directories_still_match_their_contents(self):
        for neutral in ("docs/", "docs/README.md", "schemas/writer_lease.schema.json", "config/"):
            with self.subTest(resource=neutral):
                self.assertTrue(self.pep._is_brain_neutral(neutral))
        # ...and a directory-shaped near-miss still does not.
        self.assertFalse(self.pep._is_brain_neutral("docsomething/x"))

    def _scoped_packet(self):
        return {
            "agent": SPECIALIST,
            "owner_brain": "APEX",
            "allowed_read_namespaces": ["APEX::Strategy-Campaigns::apex_war_architect"],
        }

    def test_a_child_scope_does_not_authorize_its_parent(self):
        # The reverse-prefix branch accepted a declared scope that is a
        # DESCENDANT of the request, so a delegation naming one specialist's
        # namespace authorized the parent collection holding every
        # specialist's. On a collection-backed store that is the difference
        # between one agent's records and all of them.
        reasons = self.pep._packet_scope_errors(
            ToolRequest(
                agent=SPECIALIST,
                action="read",
                resource="APEX/Strategy-Campaigns",
                owner_brain="APEX",
                packet=self._scoped_packet(),
            )
        )
        self.assertTrue(any("does not authorize" in reason for reason in reasons), reasons)

    def test_the_named_scope_and_its_descendants_are_still_authorized(self):
        for resource in (
            "APEX/Strategy-Campaigns/apex_war_architect",
            "APEX::Strategy-Campaigns::apex_war_architect",
            "APEX/Strategy-Campaigns/apex_war_architect/record-1",
        ):
            with self.subTest(resource=resource):
                self.assertEqual(
                    self.pep._packet_scope_errors(
                        ToolRequest(
                            agent=SPECIALIST,
                            action="read",
                            resource=resource,
                            owner_brain="APEX",
                            packet=self._scoped_packet(),
                        )
                    ),
                    [],
                )

    def _mutation(self, **overrides):
        fields = {
            "agent": CHIEF,
            "action": "write",
            "resource": "APEX/Strategy-Campaigns",
            "owner_brain": "APEX",
            "mutating": True,
            "lease": self.lease,
            "resource_id": "campaign-alpha",
        }
        fields.update(overrides)
        return ToolRequest(**fields)

    def test_a_mount_dispatched_mutation_requires_its_grant(self):
        # The rule keyed off `resource.startswith("mount:")`, but a mutation
        # dispatched through a mount must name its canonical write target in
        # `resource` -- that is what the packet and lease scope checks compare
        # against. The two requirements were mutually exclusive, so a fully
        # authorized canonical mutation was allowed with no grant at all.
        reasons = self.pep._launch_grant(self._mutation(mount="filesystem"))
        self.assertTrue(any("launch grant" in reason for reason in reasons), reasons)

    def test_the_mount_handle_spelling_still_requires_its_grant(self):
        reasons = self.pep._launch_grant(self._mutation(resource="mount:filesystem"))
        self.assertTrue(any("launch grant" in reason for reason in reasons), reasons)

    def test_a_read_through_a_mount_needs_no_launch_grant(self):
        # The grant governs write-capable launches. Requiring it for reads
        # would deny the governance mount, which is deliberately grant-free.
        self.assertEqual(
            self.pep._launch_grant(
                ToolRequest(
                    agent=CHIEF,
                    action="read",
                    resource="APEX/Strategy-Campaigns",
                    owner_brain="APEX",
                    mount="governance",
                )
            ),
            [],
        )

    def test_declaring_a_mount_can_only_add_the_requirement(self):
        # This field is caller-supplied, which this module has three times
        # learned to distrust. It is a different shape: it can oblige, never
        # permit. Setting it must never turn a denial into an approval.
        without = self.pep._launch_grant(self._mutation())
        with_mount = self.pep._launch_grant(self._mutation(mount="filesystem"))
        self.assertGreaterEqual(len(with_mount), len(without))


class EighteenthPassRegressionTests(unittest.TestCase):
    """Two P1s in code added by the previous two rounds, plus one scope leak."""

    def setUp(self):
        self.registry, self.lease = registry_and_lease()
        self.pep = PolicyEnforcementPoint(ROOT, registry=self.registry, clock=lambda: NOW)

    def _delegation(self, **overrides):
        from tests.test_packet_contracts import PacketContractTests

        PacketContractTests.setUpClass()
        packet, _ = PacketContractTests().v21_readonly_pair()
        packet = json.loads(json.dumps(packet))
        packet.update(overrides)
        return packet

    def _handoff(self, **overrides):
        from tests.test_packet_contracts import PacketContractTests

        PacketContractTests.setUpClass()
        _, packet = PacketContractTests().v21_readonly_pair()
        packet = json.loads(json.dumps(packet))
        packet.update(overrides)
        return packet

    RESOURCE = "APEX/Strategy-Campaigns/apex_war_architect"

    def test_a_specialist_may_not_dispatch_through_a_mount(self):
        # `ToolRequest.mount` was added one round earlier and wired only into
        # the launch-grant rule, so a packet-only specialist could name its own
        # memory namespace in `resource`, set `mount="gdrive"`, and be allowed.
        # Adding a field that names a connector without teaching the connector
        # rule to read it moved the boundary instead of widening it on purpose.
        decision = self.pep.evaluate(
            ToolRequest(
                agent=SPECIALIST,
                action="read",
                resource=self.RESOURCE,
                owner_brain="APEX",
                packet=self._delegation(),
                mount="gdrive",
            )
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(any("may not dispatch through" in r for r in decision.reasons))

    def test_an_unregistered_mount_field_is_refused_for_the_chief_too(self):
        # Registration is checked before the chief exemption, for the declared
        # mount as well as the resource spelling.
        decision = self.pep.evaluate(
            ToolRequest(
                agent=CHIEF,
                action="read",
                resource="docs/README.md",
                owner_brain="APEX",
                mount="shadow_it_server",
            )
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(any("names no mount registered" in r for r in decision.reasons))

    def test_the_chief_may_still_dispatch_through_a_registered_mount(self):
        # The other direction: the chief performs connector work on the corps'
        # behalf, so this must not become a blanket refusal.
        decision = self.pep.evaluate(
            ToolRequest(
                agent=CHIEF,
                action="read",
                resource="docs/README.md",
                owner_brain="APEX",
                mount="gdrive",
            )
        )
        self.assertTrue(decision.allowed, decision.reasons)

    def test_an_expired_originating_delegation_denies_its_handoff(self):
        # A handoff carries no `deadline` -- the field lives on the delegation
        # that commissioned it -- so the previous round's check ran against a
        # packet that could never fail it. A return cannot outlive its
        # commission.
        errors = self.pep._packet_admission(
            ToolRequest(
                agent=SPECIALIST,
                action="read",
                resource=self.RESOURCE,
                owner_brain="APEX",
                packet=self._handoff(),
                packet_schema="handoff_packet.schema.json",
                delegations=[self._delegation(deadline="2020-01-01T00:00:00Z")],
            )
        )
        self.assertTrue(any("originating delegation" in error for error in errors), errors)

    def test_a_live_originating_delegation_still_admits_its_handoff(self):
        ahead = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)
        for deadline in (None, ahead.isoformat().replace("+00:00", "Z")):
            with self.subTest(deadline=deadline):
                self.assertEqual(
                    self.pep._packet_admission(
                        ToolRequest(
                            agent=SPECIALIST,
                            action="read",
                            resource=self.RESOURCE,
                            owner_brain="APEX",
                            packet=self._handoff(),
                            packet_schema="handoff_packet.schema.json",
                            delegations=[self._delegation(deadline=deadline)],
                            resource_id=self._handoff().get("resource_id"),
                        )
                    ),
                    [],
                )

    def test_a_direct_read_only_handoff_authorizes_no_canonical_read(self):
        # That mode is the packetless path written down: no delegation
        # commissioned it, and the schema confines it to current-message text.
        # Treating its memory_namespace as a scope let a specialist mint its own
        # authority through the one packet kind that needs no issuer.
        self.assertIsNone(
            self.pep._handoff_scope(
                {
                    "invocation_mode": "direct_read_only",
                    "memory_namespace": "APEX::Strategy-Campaigns::apex_war_architect",
                },
                mutating=False,
            )
        )

    def test_a_delegated_handoff_is_still_bound_to_its_namespace(self):
        self.assertEqual(
            self.pep._handoff_scope(
                {
                    "invocation_mode": "delegated",
                    "memory_namespace": "APEX::Strategy-Campaigns::apex_war_architect",
                },
                mutating=False,
            ),
            ["APEX::Strategy-Campaigns::apex_war_architect"],
        )


class NineteenthPassRegressionTests(unittest.TestCase):
    """Two fail-opens the chief exemption hid, one deadlock, one wrapped artifact."""

    def setUp(self):
        self.registry, self.lease = registry_and_lease()
        self.pep = PolicyEnforcementPoint(ROOT, registry=self.registry, clock=lambda: NOW)

    def test_the_chief_cannot_read_outside_the_repository(self):
        # The exemption returned before `_escapes_the_tree` ran, so the chief
        # was allowed `/etc/shadow` with an EMPTY reason tuple. Being the sole
        # cross-brain agent permits acting for either brain; it does not put the
        # filesystem in scope, and no brain owns a path outside the tree.
        for resource in ("../outside-secret", "/etc/shadow", "docs/../../.ssh/id_rsa", ".."):
            with self.subTest(resource=resource):
                decision = self.pep.evaluate(
                    ToolRequest(agent=CHIEF, action="read", resource=resource, owner_brain="APEX")
                )
                self.assertFalse(decision.allowed, f"{resource}: {decision.reasons}")
                self.assertTrue(any("escapes the repository" in r for r in decision.reasons))

    def test_the_chief_still_reads_inside_the_repository(self):
        decision = self.pep.evaluate(
            ToolRequest(agent=CHIEF, action="read", resource="docs/README.md", owner_brain="APEX")
        )
        self.assertTrue(decision.allowed, decision.reasons)

    def test_the_current_message_sentinel_has_a_lawful_path(self):
        # docs/SPECIALIST_CORPS_PROTOCOL.md confines direct invocation to
        # current-message text, and packet admission already treats it as
        # non-canonical -- but the brain lock classified it as an unresolvable
        # resource, so the documented direct path was denied by exactly one
        # rule. Third deadlock of this shape in this change set.
        #
        # This originally omitted `owner_brain`, and passed -- because the
        # exemption was an early return that skipped the whole rule, including
        # the principal's brain declaration. So the test asserting the sentinel
        # has a lawful path was simultaneously asserting that the sentinel
        # waives the brain lock. Fourth test in this change set found encoding
        # the defect it was written to prevent. A lawful direct invocation
        # declares its brain like any other.
        decision = self.pep.evaluate(
            ToolRequest(
                agent=SPECIALIST, action="read", resource="current-message", owner_brain="APEX"
            )
        )
        self.assertTrue(decision.allowed, decision.reasons)

    def test_the_sentinel_is_matched_exactly(self):
        # Equality, not prefix. The sibling-matching defect one round earlier is
        # exactly why: `current-message-secrets` is a resource like any other.
        decision = self.pep.evaluate(
            ToolRequest(
                agent=SPECIALIST,
                action="read",
                resource="current-message-secrets",
                owner_brain="APEX",
            )
        )
        self.assertFalse(decision.allowed)

    def test_concrete_boundary_verbs_require_an_instruction(self):
        # The comparison was exact against abstract category names, so the
        # boundary fired only when a caller volunteered `public_publication` as
        # its action -- the same "ask the caller to incriminate itself" shape as
        # the three caller-set booleans removed earlier.
        for action in ("publish", "send", "post", "transfer", "sign", "purge", "revoke"):
            with self.subTest(action=action):
                reasons = self.pep._high_impact_boundary(
                    ToolRequest(
                        agent=CHIEF,
                        action=action,
                        resource="APEX/Strategy-Campaigns",
                        owner_brain="APEX",
                        mutating=True,
                    )
                )
                self.assertTrue(any("high-impact boundary" in r for r in reasons), reasons)

    def test_ordinary_verbs_do_not_require_an_instruction(self):
        # The opposite error would demand Joe's signature for routine work.
        for action in ("read", "analyze", "propose", "append", "upsert", "list"):
            with self.subTest(action=action):
                self.assertEqual(
                    self.pep._high_impact_boundary(
                        ToolRequest(
                            agent=CHIEF,
                            action=action,
                            resource="APEX/Strategy-Campaigns",
                            owner_brain="APEX",
                            mutating=True,
                        )
                    ),
                    [],
                )

    def test_every_mapped_verb_names_a_real_boundary_category(self):
        # A typo here would silently map a verb to nothing.
        self.assertTrue(set(HIGH_IMPACT_VERBS.values()) <= set(HIGH_IMPACT_ACTIONS))

    def test_the_ledger_artifact_is_recognised_when_wrapped(self):
        # PacketGuard re-emits a delegation's inner errors as
        # `originating delegation invalid: <error>`, so on a write-bearing
        # handoff the artifact arrived wrapped and survived an exact-equality
        # filter -- denying a lawful handoff even with its genuine registry
        # lease. The fix to a fail-shut was itself fail-shut, one nesting level
        # down.
        from scripts.policy_enforcement import LEDGER_ABSENT_ARTIFACT, _is_ledger_artifact

        self.assertTrue(_is_ledger_artifact(LEDGER_ABSENT_ARTIFACT))
        self.assertTrue(
            _is_ledger_artifact(f"originating delegation invalid: {LEDGER_ABSENT_ARTIFACT}")
        )

    def test_the_artifact_filter_removes_nothing_else(self):
        # The standing rule: a suppression must not remove a finding it was not
        # written for. Only the exact tail qualifies.
        from scripts.policy_enforcement import LEDGER_ABSENT_ARTIFACT, _is_ledger_artifact

        for finding in (
            "writer lease 'x' is not uniquely active",
            "agent must use memory namespace APEX::Strategy-Campaigns::apex_war_architect",
            f"{LEDGER_ABSENT_ARTIFACT} and a second problem",
        ):
            with self.subTest(finding=finding):
                self.assertFalse(_is_ledger_artifact(finding))


class TwentiethPassRegressionTests(unittest.TestCase):
    """Three gaps in the previous round's fixes, all reached the same way."""

    def setUp(self):
        self.registry, self.lease = registry_and_lease()
        self.pep = PolicyEnforcementPoint(ROOT, registry=self.registry, clock=lambda: NOW)

    def _boundary(self, action):
        return self.pep._high_impact_boundary(
            ToolRequest(
                agent=CHIEF,
                action=action,
                resource="APEX/Strategy-Campaigns",
                owner_brain="APEX",
                mutating=True,
            )
        )

    def test_compound_boundary_actions_require_an_instruction(self):
        # The previous round replaced exact matching against abstract category
        # names with a verb map, then looked the WHOLE action up in it -- and
        # the comment introducing that map named `delete_all` as its own example
        # of a real invocation, which the map did not cover. The fix contained
        # the class it was fixing.
        for action in (
            "delete_all",
            "bulk_delete",
            "delete_everything",
            "mass_erase",
            "publish_report",
            "send_email",
            "rotate_credentials",
        ):
            with self.subTest(action=action):
                self.assertTrue(self._boundary(action), f"{action} escaped the boundary")

    def test_compound_ordinary_actions_still_do_not(self):
        # Token EQUALITY, not substring: `design` does not contain the token
        # `sign`, `publications` is not `publish`, and a single-record
        # `delete_row` is an ordinary mutation the writer lease governs.
        for action in (
            "delete_row",
            "design_review",
            "list_transfers",
            "read_publications",
            "assign_owner",
            "validate_packet",
            "append_record",
        ):
            with self.subTest(action=action):
                self.assertEqual(self._boundary(action), [], f"{action} was over-classified")

    def test_a_destructive_verb_alone_is_not_a_bulk_deletion(self):
        # `delete` is governed by the lease; `delete_all` is one of the six
        # actions AGENTS.md reserves for Joe. Neither token means that alone.
        self.assertEqual(self._boundary("delete"), [])
        self.assertTrue(self._boundary("delete_all"))

    def test_windows_drive_paths_are_escapes(self):
        # `_canonical_resource` treated anything with a colon before the first
        # slash as an opaque handle. `C:\Users\Joe\secret.txt` has no slash at
        # all, so the whole string was its own first segment: normalization
        # never ran and the escape check added the round before was never
        # reached. The chief could read it with no denial reasons -- on the one
        # platform the workstation actually runs.
        for resource in (
            r"C:\Users\Joe\secret.txt",
            "D:/private/keys.txt",
            r"\\server\share\secret",
            "//server/share/secret",
        ):
            with self.subTest(resource=resource):
                self.assertTrue(self.pep._escapes_the_tree(resource))
                decision = self.pep.evaluate(
                    ToolRequest(agent=CHIEF, action="read", resource=resource, owner_brain="APEX")
                )
                self.assertFalse(decision.allowed, f"{resource}: {decision.reasons}")

    def test_a_colon_does_not_hide_a_traversal(self):
        # Found by mutation-testing the fix rather than by the review: reverting
        # the opacity rule alone still passed every test, because the
        # drive-letter regex catches `C:\...` even unnormalized. That meant the
        # narrowing looked unmotivated -- and the thing it actually protects was
        # untested.
        #
        # The old rule made ANY resource opaque whose first segment contained a
        # colon, so `docs:notes/../../etc/passwd` was never normalized and read
        # as safe. Normalized it is `../etc/passwd`. Opacity has to be reserved
        # for real handle syntax, or it becomes a way to smuggle traversal past
        # every prefix comparison downstream.
        for resource in ("docs:notes/../../etc/passwd", "a:b/../../../secret"):
            with self.subTest(resource=resource):
                self.assertTrue(
                    self.pep._escapes_the_tree(resource),
                    f"{resource} normalizes outside the tree but was treated as opaque",
                )

    def test_handles_and_namespaces_are_still_opaque(self):
        # The other direction: narrowing opacity must not start normalizing the
        # things it exists to protect.
        self.assertEqual(self.pep._canonical_resource("mount:filesystem"), "mount:filesystem")
        self.assertEqual(
            self.pep._canonical_resource("APEX::Strategy-Campaigns::apex_war_architect"),
            "APEX::Strategy-Campaigns::apex_war_architect",
        )
        for resource in ("mount:filesystem", "connector:gdrive", "APEX::Strategy-Campaigns::a"):
            with self.subTest(resource=resource):
                self.assertFalse(self.pep._escapes_the_tree(resource))

    def test_ordinary_repository_paths_are_not_escapes(self):
        for resource in ("docs/README.md", "scripts/policy_enforcement.py", "docs/"):
            with self.subTest(resource=resource):
                self.assertFalse(self.pep._escapes_the_tree(resource))


class TwentySecondPassRegressionTests(unittest.TestCase):
    """Two fail-opens, each inside a fix from the previous two rounds."""

    def setUp(self):
        self.registry, self.lease = registry_and_lease()
        self.pep = PolicyEnforcementPoint(ROOT, registry=self.registry, clock=lambda: NOW)

    def test_the_sentinel_does_not_waive_the_principals_brain(self):
        # The exemption was an early return, so it skipped the comparison of the
        # caller's declared brain against its registered one. A JEOS specialist
        # reading `current-message` while declaring APEX -- or omitting the
        # field -- was allowed, so APEX message content could be routed through
        # a JEOS specialist with no objection. An exemption has to name what it
        # waives: here, resource ownership, and nothing about the principal.
        for agent, declared in (
            (JEOS_SPECIALIST, "APEX"),
            (JEOS_SPECIALIST, None),
            (SPECIALIST, "JEOS"),
        ):
            with self.subTest(agent=agent, declared=declared):
                decision = self.pep.evaluate(
                    ToolRequest(
                        agent=agent,
                        action="read",
                        resource="current-message",
                        owner_brain=declared,
                    )
                )
                self.assertFalse(decision.allowed, f"{agent}/{declared}: {decision.reasons}")

    def test_a_matching_brain_still_reads_the_sentinel(self):
        # The other direction: the documented direct-invocation path must stay
        # open for the specialist whose brain it is.
        for agent, declared in ((SPECIALIST, "APEX"), (JEOS_SPECIALIST, "JEOS"), (CHIEF, "APEX")):
            with self.subTest(agent=agent, declared=declared):
                decision = self.pep.evaluate(
                    ToolRequest(
                        agent=agent,
                        action="read",
                        resource="current-message",
                        owner_brain=declared,
                    )
                )
                self.assertTrue(decision.allowed, f"{agent}/{declared}: {decision.reasons}")

    def test_a_double_colon_does_not_make_a_path_opaque(self):
        # The previous round narrowed opacity from "a colon before the first
        # slash" to "a connector prefix OR contains `::`" -- and the `::` clause
        # carried the same defect the narrowing removed. Any path-shaped string
        # containing `::` skipped normalization, so `scripts/../../outside::secret`
        # matched the `scripts/` neutral prefix on its RAW text and was readable
        # packetlessly, while a filesystem executor resolves it outside the
        # repository.
        for resource in (
            "scripts/../../outside::secret",
            "docs/../../etc/passwd::x",
            "config/../../../root/.ssh::id",
        ):
            with self.subTest(resource=resource):
                self.assertTrue(self.pep._escapes_the_tree(resource))
                self.assertFalse(self.pep._is_brain_neutral(resource))
                decision = self.pep.evaluate(
                    ToolRequest(
                        agent=SPECIALIST, action="read", resource=resource, owner_brain="APEX"
                    )
                )
                self.assertFalse(decision.allowed, f"{resource}: {decision.reasons}")

    def test_real_namespaces_are_still_opaque(self):
        # Opacity must survive for the syntax it exists to protect, in either
        # case, since the manifests spell brains uppercase and the harness
        # lowercase.
        for resource in (
            "APEX::Strategy-Campaigns::apex_war_architect",
            "JEOS::Roundtable",
            "jeos::Weekly",
        ):
            with self.subTest(resource=resource):
                self.assertEqual(self.pep._canonical_resource(resource), resource)
                self.assertFalse(self.pep._escapes_the_tree(resource))


class TwentyFourthPassRegressionTests(unittest.TestCase):
    """Two scope fail-opens and a crash where a denial belonged."""

    RESOURCE = "APEX/Strategy-Campaigns/apex_war_architect"

    def setUp(self):
        self.registry, self.lease = registry_and_lease()
        self.pep = PolicyEnforcementPoint(ROOT, registry=self.registry, clock=lambda: NOW)

    def _pair(self):
        from tests.test_packet_contracts import PacketContractTests

        PacketContractTests.setUpClass()
        delegation, handoff = PacketContractTests().v21_readonly_pair()
        return json.loads(json.dumps(delegation)), json.loads(json.dumps(handoff))

    def test_a_non_string_packet_schema_denies_rather_than_raises(self):
        # A frozenset lookup on an unhashable value raises TypeError, so a
        # caller supplying a list unwound the enforcement call instead of
        # receiving a denial. A gate that raises on caller-controlled input is a
        # denial of service on every other caller in the process. The non-dict
        # packet check two rules down was fixed for this exact reason and this
        # one was left -- the untouched sibling again.
        for schema in ([], {}, 42, None, ["delegation_packet.schema.json"]):
            with self.subTest(schema=type(schema).__name__):
                errors = self.pep._packet_admission(
                    ToolRequest(
                        agent=SPECIALIST,
                        action="read",
                        resource="docs/README.md",
                        owner_brain="APEX",
                        packet={},
                        packet_schema=schema,
                    )
                )
                self.assertTrue(errors)

    def test_a_packet_backed_read_must_name_its_record(self):
        # An optional identifier honoured only when supplied is an opt-out: a
        # delegation for `resource-1` denied a request naming `resource-2` and
        # ALLOWED one that named nothing, so any record under the authorized
        # namespace was reachable by leaving the field out. `_writer_lease`
        # already required it for mutations; reads were the untouched sibling.
        delegation, _ = self._pair()
        errors = self.pep._packet_admission(
            ToolRequest(
                agent=SPECIALIST,
                action="read",
                resource=self.RESOURCE,
                owner_brain="APEX",
                packet=delegation,
                packet_schema="delegation_packet.schema.json",
            )
        )
        self.assertTrue(any("names none" in error for error in errors), errors)

    def test_a_matching_record_identity_is_still_admitted(self):
        delegation, _ = self._pair()
        self.assertEqual(
            self.pep._packet_admission(
                ToolRequest(
                    agent=SPECIALIST,
                    action="read",
                    resource=self.RESOURCE,
                    owner_brain="APEX",
                    packet=delegation,
                    packet_schema="delegation_packet.schema.json",
                    resource_id=delegation["resource_id"],
                )
            ),
            [],
        )

    def test_a_handoff_cannot_read_past_its_commission(self):
        # The fallback read the handoff's own mandatory `memory_namespace` and
        # never consulted the delegation that authorized the work, so a handoff
        # commissioned only for `APEX::Roundtable` could read a specialist's
        # canonical namespace. A return packet cannot widen the assignment it
        # answers.
        delegation, handoff = self._pair()
        delegation["allowed_read_namespaces"] = ["APEX::Roundtable"]
        errors = self.pep._packet_scope_errors(
            ToolRequest(
                agent=SPECIALIST,
                action="read",
                resource=self.RESOURCE,
                owner_brain="APEX",
                packet=handoff,
                packet_schema="handoff_packet.schema.json",
                delegations=[delegation],
                resource_id=handoff["resource_id"],
            )
        )
        self.assertTrue(errors, "a handoff read beyond its commission was allowed")

    def test_a_handoff_may_read_what_its_commission_granted(self):
        # The other direction: bounding by the delegation must not deny the
        # namespace the commission actually names.
        delegation, handoff = self._pair()
        self.assertEqual(
            self.pep._packet_scope_errors(
                ToolRequest(
                    agent=SPECIALIST,
                    action="read",
                    resource=self.RESOURCE,
                    owner_brain="APEX",
                    packet=handoff,
                    packet_schema="handoff_packet.schema.json",
                    delegations=[delegation],
                    resource_id=handoff["resource_id"],
                )
            ),
            [],
        )


class TwentyFifthPassRegressionTests(unittest.TestCase):
    """A camelCase bypass of the boundary, and a prohibition nothing consulted."""

    RESOURCE = "APEX/Strategy-Campaigns/apex_war_architect"

    def setUp(self):
        self.registry, self.lease = registry_and_lease()
        self.pep = PolicyEnforcementPoint(ROOT, registry=self.registry, clock=lambda: NOW)

    def _pair(self):
        from tests.test_packet_contracts import PacketContractTests

        PacketContractTests.setUpClass()
        delegation, handoff = PacketContractTests().v21_readonly_pair()
        return json.loads(json.dumps(delegation)), json.loads(json.dumps(handoff))

    def _boundary(self, action):
        return self.pep._high_impact_boundary(
            ToolRequest(
                agent=CHIEF,
                action=action,
                resource="APEX/Strategy-Campaigns",
                owner_brain="APEX",
                mutating=True,
            )
        )

    def test_camel_case_actions_reach_the_boundary(self):
        # The tokenizer folded case BEFORE splitting, so `deleteAll` became one
        # token `deleteall` -- matching no verb, qualified by nothing, and
        # passing the boundary without an instruction. Every dispatcher that
        # names actions in camelCase, which is most of them, was outside the
        # control. The snake_case sibling was fixed five rounds ago; this is the
        # same class reached by a different naming convention.
        for action in (
            "deleteAll",
            "DeleteAll",
            "bulkDelete",
            "publishReport",
            "sendEmail",
            "rotateCredentials",
        ):
            with self.subTest(action=action):
                self.assertTrue(
                    self._boundary(action),
                    f"{action} passed the high-impact boundary with no instruction",
                )

    def test_ordinary_camel_case_actions_are_not_over_classified(self):
        # The other direction. Over-classification costs a signature request on
        # work that never needed one, and a boundary that fires on every write
        # is one Joe learns to wave through.
        for action in (
            "readRow",
            "listTransfers",
            "designReview",
            "appendRecord",
            "validatePacket",
            "assignOwner",
        ):
            with self.subTest(action=action):
                self.assertEqual(self._boundary(action), [])

    def test_the_tokenizer_keeps_the_first_letter_of_each_segment(self):
        # An unreported fail-open the shared tokenizer closed. The old regex
        # split on `[^a-z]+`, which CONSUMED the capital starting each camel
        # segment: `listPurge` tokenized to ['list', 'urge'], so it read as a
        # list operation and skipped every mutation control -- classified as the
        # opposite of what it is. Asserted on the tokens rather than on a
        # verdict, because the defect is in the tokenizer and the verdict is
        # only where it surfaced.
        self.assertEqual(_action_tokens("listPurge"), ["list", "purge"])
        self.assertEqual(_action_tokens("GetInfo"), ["get", "info"])
        self.assertEqual(_action_tokens("rotateAPIKey"), ["rotate", "api", "key"])
        self.assertEqual(_action_tokens("delete_all"), ["delete", "all"])

    def test_a_delegation_cannot_authorize_what_it_prohibits(self):
        # `prohibited_scope` is a required field of the delegation schema and
        # nothing read it. A packet whose prohibition named its own authorized
        # namespace granted access to exactly that namespace: the packet
        # contradicted itself and the contradiction resolved toward access.
        delegation, _ = self._pair()
        for entry in (self.RESOURCE, "APEX/Strategy-Campaigns"):
            with self.subTest(entry=entry):
                prohibiting = json.loads(json.dumps(delegation))
                prohibiting["prohibited_scope"] = [entry]
                errors = self.pep._packet_admission(
                    ToolRequest(
                        agent=SPECIALIST,
                        action="read",
                        resource=self.RESOURCE,
                        owner_brain="APEX",
                        packet=prohibiting,
                        packet_schema="delegation_packet.schema.json",
                        resource_id=prohibiting["resource_id"],
                    )
                )
                self.assertTrue(
                    any("prohibits" in error for error in errors),
                    f"prohibited_scope {entry!r} did not deny the resource it covers",
                )

    def test_prose_prohibitions_do_not_deny_unrelated_work(self):
        # `prohibited_scope` also carries prose no comparison here can
        # adjudicate. Guessing at it would deny lawful work on a string match,
        # so entries naming no resource are left to the role-adherence judge --
        # and a prohibition on a DIFFERENT namespace must not bite either.
        delegation, _ = self._pair()
        for entries in (["JEOS", "binding commitments"], ["APEX::Roundtable"]):
            with self.subTest(entries=entries):
                permitting = json.loads(json.dumps(delegation))
                permitting["prohibited_scope"] = entries
                self.assertEqual(
                    self.pep._packet_admission(
                        ToolRequest(
                            agent=SPECIALIST,
                            action="read",
                            resource=self.RESOURCE,
                            owner_brain="APEX",
                            packet=permitting,
                            packet_schema="delegation_packet.schema.json",
                            resource_id=permitting["resource_id"],
                        )
                    ),
                    [],
                )

    def test_the_prohibition_denies_what_the_allowlist_admits(self):
        # A prohibition that only takes effect where the allowlist already
        # denies is not a prohibition, so the ordering is the substance of the
        # fix. Asserted as the property rather than by reading the call order:
        # the SAME request without the prohibition is admitted, which is what
        # makes the denial attributable to the prohibition and nothing else.
        # An earlier version of this test hand-built an allowlist to force the
        # situation and tripped the private-memory rule instead -- proving the
        # ordering with a request that was never lawful proves nothing.
        delegation, _ = self._pair()
        request = ToolRequest(
            agent=SPECIALIST,
            action="read",
            resource=self.RESOURCE,
            owner_brain="APEX",
            packet=delegation,
            packet_schema="delegation_packet.schema.json",
            resource_id=delegation["resource_id"],
        )
        self.assertEqual(self.pep._packet_admission(request), [])

        prohibiting = json.loads(json.dumps(delegation))
        prohibiting["prohibited_scope"] = [self.RESOURCE]
        errors = self.pep._packet_admission(
            ToolRequest(
                agent=SPECIALIST,
                action="read",
                resource=self.RESOURCE,
                owner_brain="APEX",
                packet=prohibiting,
                packet_schema="delegation_packet.schema.json",
                resource_id=prohibiting["resource_id"],
            )
        )
        self.assertTrue(any("prohibits" in error for error in errors), errors)


class TwentySixthPassRegressionTests(unittest.TestCase):
    """The previous round's fix worked on the rule and not on the path.

    `evaluate()` normalizes the action before any rule runs, and normalization
    folded case without splitting camelCase -- so `deleteAll` reached the
    boundary as the single token `deleteall`. The rule denied when called
    directly and the enforcement point allowed. The round-25 regression test
    called the rule directly, which is exactly why it passed.
    """

    RESOURCE = "APEX/Strategy-Campaigns"

    SPELLINGS = (
        "deleteAll",
        "DeleteAll",
        "delete_all",
        "DELETE_ALL",
        "delete-all",
        "bulkDelete",
        "publishReport",
        "sendEmail",
        "rotateCredentials",
        "listPurge",
        "readRow",
        "listTransfers",
        "designReview",
        "appendRecord",
        "validatePacket",
        "GetInfo",
        # Separator variants of the CATEGORY names. Added after mutation
        # testing: removing the rule's own canonicalization was MISSED because
        # every spelling above happens to resolve the same way with or without
        # it. These do not -- `"Public Publication"` folds to
        # `public publication`, which is in no set, so the boundary went quiet.
        "Public Publication",
        "public-publication",
        "FINANCIAL TRANSACTION",
        "credential or access change",
    )

    def setUp(self):
        self.registry, self.lease = registry_and_lease()
        self.pep = PolicyEnforcementPoint(ROOT, registry=self.registry, clock=lambda: NOW)

    def _request(self, action=None, **overrides):
        fields = {
            "agent": CHIEF,
            "action": "read",
            "resource": self.RESOURCE,
            "owner_brain": "APEX",
            "mutating": True,
        }
        if action is not None:
            fields["action"] = action
        # Overrides last, so a test may replace the action with a malformed
        # value without colliding with the positional form.
        fields.update(overrides)
        return ToolRequest(**fields)

    @staticmethod
    def _boundary_denied(decision):
        return any("high-impact boundary" in reason for reason in decision.reasons)

    def test_camel_case_is_denied_through_the_public_entry_point(self):
        # The assertion the previous round should have made. Through
        # `evaluate()`, not through the private rule: a control is only as good
        # as the entry point the system actually uses, and these four returned
        # allowed=True from the enforcement point while the rule denied them.
        for action in ("deleteAll", "publishReport", "sendEmail", "rotateCredentials"):
            with self.subTest(action=action):
                self.assertTrue(
                    self._boundary_denied(self.pep.evaluate(self._request(action))),
                    f"evaluate() allowed {action} with no signed instruction",
                )

    def test_the_rule_and_the_entry_point_cannot_disagree(self):
        # The class, not the instance. Any future normalization that changes
        # what a rule receives fails here rather than silently disarming the
        # boundary for one spelling convention -- which is what happened, for
        # the whole camelCase convention, for a full round.
        for action in self.SPELLINGS:
            with self.subTest(action=action):
                request = self._request(action)
                self.assertEqual(
                    bool(self.pep._high_impact_boundary(request)),
                    self._boundary_denied(self.pep.evaluate(request)),
                    f"{action}: the rule and the enforcement point disagree",
                )

    def test_every_category_name_is_denied_however_it_is_separated(self):
        # `HIGH_IMPACT_ACTIONS` members are snake_case category names. A caller
        # spelling one with spaces or hyphens produced a string in no set, and
        # the boundary said nothing -- the same "controls that depend on the
        # caller's spelling" shape as the camelCase bypass, one level up.
        for category in HIGH_IMPACT_ACTIONS:
            for spelling in (
                category,
                category.replace("_", " "),
                category.replace("_", "-"),
                category.replace("_", " ").title(),
                category.upper(),
            ):
                with self.subTest(spelling=spelling):
                    request = self._request(spelling)
                    self.assertTrue(
                        self._boundary_denied(self.pep.evaluate(request)),
                        f"evaluate() allowed the boundary spelled {spelling!r}",
                    )
                    self.assertTrue(
                        self.pep._high_impact_boundary(request),
                        f"the rule allowed the boundary spelled {spelling!r}",
                    )

    def test_every_spelling_of_one_action_canonicalizes_together(self):
        # `deleteAll`, `DELETE_ALL`, and `delete-all` are the same action, and
        # no rule should be able to tell which the caller used.
        canonical = {
            self.pep.normalize(self._request(action))[0].action
            for action in ("deleteAll", "DeleteAll", "delete_all", "DELETE_ALL", "delete-all")
        }
        self.assertEqual(canonical, {"delete_all"})

    def test_a_malformed_field_is_refused_rather_than_raising(self):
        # `resource=["docs/x"]` from malformed deserialized data reached
        # `.strip()` and raised AttributeError before any rule could deny or
        # any audit event could be written. A gate that unwinds on
        # caller-controlled input is a denial of service on every other caller
        # in the process. `packet_schema` was type-checked two rounds ago and
        # every other string field was left alone -- the whole class is covered
        # here rather than the one field that was reported.
        for field, value in (
            ("agent", 42),
            ("action", {"a": 1}),
            ("resource", ["docs/x"]),
            ("owner_brain", 7),
            ("resource_id", object()),
            ("operation", [1]),
            ("mount", ["m"]),
            ("packet_schema", [1]),
        ):
            with self.subTest(field=field):
                decision = self.pep.evaluate(self._request(**{field: value}))
                self.assertFalse(decision.allowed)
                self.assertTrue(decision.reasons)

    def test_a_malformed_field_does_not_stop_the_remaining_rules(self):
        # Blanked rather than aborted, for the same reason the naive-clock fix
        # drops the clock instead of returning early: the other rules still
        # have objections worth recording, and an audit event that lists one
        # reason where seven applied understates what was wrong.
        decision = self.pep.evaluate(self._request("delete_all", resource=["x"]))
        self.assertFalse(decision.allowed)
        self.assertEqual(len(decision.checks_run), 8)


class TwentySeventhPassRegressionTests(unittest.TestCase):
    """A prohibition a return packet escaped, and the collection-field sibling."""

    RESOURCE = "APEX/Strategy-Campaigns/apex_war_architect"

    def setUp(self):
        self.registry, self.lease = registry_and_lease()
        self.pep = PolicyEnforcementPoint(ROOT, registry=self.registry, clock=lambda: NOW)

    def _pair(self):
        from tests.test_packet_contracts import PacketContractTests

        PacketContractTests.setUpClass()
        delegation, handoff = PacketContractTests().v21_readonly_pair()
        return json.loads(json.dumps(delegation)), json.loads(json.dumps(handoff))

    def _handoff_read(self, delegation, handoff):
        return ToolRequest(
            agent=SPECIALIST,
            action="read",
            resource=self.RESOURCE,
            owner_brain="APEX",
            packet=handoff,
            packet_schema="handoff_packet.schema.json",
            delegations=[delegation],
            resource_id=handoff.get("resource_id"),
        )

    def test_the_control_admits_the_same_read_without_a_prohibition(self):
        # The control the reproduction needs. Without it, "the prohibited read
        # was denied" proves nothing -- it could have been denied for any of
        # eight other reasons, and an earlier attempt at this reproduction did
        # exactly that by building a request whose agent was None.
        delegation, handoff = self._pair()
        self.assertEqual(self.pep._packet_scope_errors(self._handoff_read(delegation, handoff)), [])

    def test_a_handoff_cannot_escape_its_commission_prohibition(self):
        # The handoff schema defines no `prohibited_scope`, so checking only the
        # submitted packet meant a return packet was bound by no prohibition at
        # all. `_packet_namespace_errors` beside it already derived its ALLOWLIST
        # from the originating delegation: permission taken from the commission,
        # prohibition taken from the return packet, and the looser of the two won.
        delegation, handoff = self._pair()
        for entry in (self.RESOURCE, "APEX/Strategy-Campaigns"):
            with self.subTest(entry=entry):
                origin = json.loads(json.dumps(delegation))
                origin["prohibited_scope"] = [entry]
                errors = self.pep._packet_scope_errors(self._handoff_read(origin, handoff))
                self.assertTrue(
                    any("prohibits" in error for error in errors),
                    f"handoff read past a commission prohibiting {entry!r}",
                )

    def test_an_unrelated_commission_prohibition_still_admits_the_read(self):
        # The other direction: inheriting the commission's prohibitions must not
        # deny work the commission never forbade.
        delegation, handoff = self._pair()
        delegation["prohibited_scope"] = ["JEOS", "binding commitments"]
        self.assertEqual(self.pep._packet_scope_errors(self._handoff_read(delegation, handoff)), [])

    def test_a_malformed_collection_field_is_refused_rather_than_raising(self):
        # `list(7)` raises TypeError inside `_packet_admission`, before any
        # denial or audit event -- the same unwinding the string fields were
        # type-checked for one round earlier. That fix covered the string
        # fields and stopped, so these were the untouched sibling of a fix
        # written for this exact property.
        #
        # `str` and `dict` are in the matrix deliberately: neither raises.
        # `list("abc")` and `list({"a": 1})` both succeed and silently yield
        # something the caller did not mean, which is worse than a crash
        # because nothing reports it.
        delegation, handoff = self._pair()
        for field in ("delegations", "constraint_packets", "private_constraint_packets"):
            for bad in (7, None, "x", {"a": 1}):
                with self.subTest(field=field, bad=type(bad).__name__):
                    fields = {
                        "agent": SPECIALIST,
                        "action": "read",
                        "resource": self.RESOURCE,
                        "owner_brain": "APEX",
                        "packet": handoff,
                        "packet_schema": "handoff_packet.schema.json",
                        "resource_id": handoff.get("resource_id"),
                        "delegations": [delegation],
                    }
                    fields[field] = bad
                    decision = self.pep.evaluate(ToolRequest(**fields))
                    self.assertFalse(decision.allowed)
                    self.assertTrue(
                        any("must be a list or tuple" in reason for reason in decision.reasons),
                        decision.reasons,
                    )

    def test_a_well_formed_request_is_still_admitted(self):
        # The control for the type check: the lawful pair must still evaluate
        # cleanly, or the check above would be passing by denying everything.
        delegation, handoff = self._pair()
        self.assertTrue(self.pep.evaluate(self._handoff_read(delegation, handoff)).allowed)


class TwentyNinthPassRegressionTests(unittest.TestCase):
    """Containment in one direction, a drive-relative escape, and a fourth ledger."""

    PARENT = "APEX/Strategy-Campaigns"
    CHILD = "APEX/Strategy-Campaigns/apex_war_architect"

    def setUp(self):
        self.registry, self.lease = registry_and_lease()
        self.pep = PolicyEnforcementPoint(ROOT, registry=self.registry, clock=lambda: NOW)

    def _pair(self):
        from tests.test_packet_contracts import PacketContractTests

        PacketContractTests.setUpClass()
        delegation, handoff = PacketContractTests().v21_readonly_pair()
        return json.loads(json.dumps(delegation)), json.loads(json.dumps(handoff))

    def _prohibiting(self, entries, resource):
        delegation, _ = self._pair()
        delegation["prohibited_scope"] = entries
        return self.pep._prohibited_scope_errors(
            ToolRequest(
                agent=SPECIALIST,
                action="read",
                resource=resource,
                owner_brain="APEX",
                packet=delegation,
                packet_schema="delegation_packet.schema.json",
            ),
            delegation,
        )

    def test_a_parent_read_is_denied_when_a_descendant_is_prohibited(self):
        # Containment was checked one way only: whether the prohibition covers
        # the request. A commission allowing the parent while prohibiting one
        # child therefore authorized a read of the whole collection -- which
        # serves the withheld record along with everything else. The prohibition
        # was satisfied by asking for strictly MORE than it forbade.
        errors = self._prohibiting([self.CHILD], self.PARENT)
        self.assertTrue(errors, "a collection read served a record the commission withheld")
        self.assertTrue(any("contained by" in error for error in errors), errors)

    def test_the_original_direction_still_denies(self):
        # The round-25/27 property, re-asserted: adding the reverse check must
        # not displace the one already there.
        self.assertTrue(self._prohibiting([self.PARENT], self.CHILD))

    def test_containment_does_not_deny_unrelated_or_merely_similar_scopes(self):
        # Both controls. `APEX/Strategy-CampaignsX` shares a textual prefix with
        # the request and contains nothing of it -- a naive `startswith` without
        # the separator would deny it, which is over-denial dressed as rigour.
        for entries in (["JEOS/Other"], ["APEX/Strategy-CampaignsX"], ["binding commitments"]):
            with self.subTest(entries=entries):
                self.assertEqual(self._prohibiting(entries, self.PARENT), [])

    def test_drive_relative_paths_are_escapes(self):
        # `C:..\\secret.txt` normalizes to `C:../secret.txt`, matching neither
        # the drive-ABSOLUTE pattern (which required a separator after the
        # colon) nor the leading-`../` check. Windows resolves it against that
        # drive's current directory, so a chief read returned allowed=True with
        # an EMPTY reason tuple for a path outside the governed tree.
        for resource in ("C:..\\secret.txt", "C:../secret.txt", "C:secret.txt", "c:x/y"):
            with self.subTest(resource=resource):
                decision = self.pep.evaluate(
                    ToolRequest(agent=CHIEF, action="read", resource=resource, owner_brain="APEX")
                )
                self.assertFalse(decision.allowed, f"{resource} was allowed out of the tree")
                self.assertTrue(decision.reasons)

    def test_ordinary_resources_are_not_read_as_drive_paths(self):
        # The other direction: a brain namespace and a repository path must not
        # be swept up by a widened drive pattern. `APEX::Roundtable` has no
        # colon in second position, which is what keeps it out.
        for resource in ("docs/README.md", self.PARENT, "APEX::Roundtable"):
            with self.subTest(resource=resource):
                self.assertFalse(PolicyEnforcementPoint._escapes_the_tree(resource))

    def test_every_collection_field_is_type_checked(self):
        # Derived from the dataclass rather than enumerated. The previous round
        # hand-listed three ledgers and missed `active_leases`, which then still
        # raised TypeError out of `_usable_leases` on the no-registry path. A
        # hand-written list is exactly how a fourth field gets missed, so this
        # asserts the property over every tuple-typed field the request carries.
        import dataclasses

        collection_fields = [
            field.name
            for field in dataclasses.fields(ToolRequest)
            if isinstance(
                getattr(ToolRequest(agent="a", action="read", resource="r"), field.name), tuple
            )
        ]
        self.assertIn("active_leases", collection_fields)
        delegation, handoff = self._pair()
        # registry=None is the path that reaches `_usable_leases`; with a
        # registry the ledger comes from the registry and never touches the
        # caller's copy, which is why the first reproduction of this found
        # nothing and had to be re-run against the right construction.
        pep = PolicyEnforcementPoint(ROOT, registry=None, clock=lambda: NOW)
        base = {
            "agent": SPECIALIST,
            "action": "read",
            "resource": self.CHILD,
            "owner_brain": "APEX",
            "packet": handoff,
            "packet_schema": "handoff_packet.schema.json",
            "delegations": [delegation],
            "resource_id": handoff.get("resource_id"),
        }
        self.assertTrue(pep.evaluate(ToolRequest(**base)).allowed, "control must be admitted")
        for name in collection_fields:
            for bad in (7, None, "x", {"a": 1}):
                with self.subTest(field=name, bad=type(bad).__name__):
                    decision = pep.evaluate(ToolRequest(**{**base, name: bad}))
                    self.assertFalse(decision.allowed)
                    self.assertTrue(
                        any("must be a list or tuple" in reason for reason in decision.reasons),
                        decision.reasons,
                    )


class ThirtySecondPassRegressionTests(unittest.TestCase):
    """A declared operation that outranked its action, and an empty category."""

    def setUp(self):
        self.registry, self.lease = registry_and_lease()
        self.pep = PolicyEnforcementPoint(ROOT, registry=self.registry, clock=lambda: NOW)

    def _request(self, action, operation=None):
        return ToolRequest(
            agent=CHIEF,
            action=action,
            resource="APEX/Strategy-Campaigns",
            owner_brain="APEX",
            operation=operation,
        )

    def test_a_declared_write_operation_is_a_mutation(self):
        # `operation` is documented as the verb the executor actually performs,
        # and the packet and lease rules already consulted it -- while the
        # mutation classification looked only at the action name. So
        # `action="read_record", operation="replace"` evaluated as a read and
        # skipped the lease, lifecycle, packet and launch-grant controls with
        # nothing presented. Where the two disagree, the more dangerous reading
        # has to win.
        for action, operation in (
            ("read_record", "replace"),
            ("read_record", "append"),
            ("list_rows", "delete"),
            ("get_row", "overwrite"),
        ):
            with self.subTest(action=action, operation=operation):
                normalized, _ = PolicyEnforcementPoint.normalize(self._request(action, operation))
                self.assertTrue(normalized.mutating)
                self.assertFalse(self.pep.evaluate(self._request(action, operation)).allowed)

    def test_a_read_operation_does_not_make_a_read_a_mutation(self):
        # The control. Without it this passes by classifying everything as a
        # mutation, which would deny every lawful read.
        for action, operation in (
            ("read_record", None),
            ("read_record", "read"),
            ("list_rows", "list"),
        ):
            with self.subTest(action=action, operation=operation):
                normalized, _ = PolicyEnforcementPoint.normalize(self._request(action, operation))
                self.assertFalse(normalized.mutating)
                self.assertTrue(self.pep.evaluate(self._request(action, operation)).allowed)

    def test_binding_legal_commitment_has_reachable_verbs(self):
        # The category shipped in HIGH_IMPACT_ACTIONS with NO verb mapped to it,
        # so it fired only when a caller volunteered the category name as its
        # own action -- a control that asks the caller to incriminate itself.
        for action in (
            "accept_contract",
            "execute_agreement",
            "agree_to_terms",
            "countersign_deed",
            "ratify_agreement",
            "acceptContract",
            "enter_into_agreement",
        ):
            with self.subTest(action=action):
                self.assertEqual(
                    PolicyEnforcementPoint._boundary_category(action),
                    "binding_legal_commitment",
                )

    def test_legal_verbs_alone_do_not_gate_ordinary_work(self):
        # The first fix mapped the bare verbs and gated `execute_query`,
        # `commit_message` and `accept_row` -- database, git and data work. The
        # verb carries no legal meaning; the OBJECT does, so both are required.
        for action in (
            "accept_row",
            "commit_message",
            "execute_query",
            "execute_report",
            "create_record",
        ):
            with self.subTest(action=action):
                self.assertNotIn(
                    PolicyEnforcementPoint._boundary_category(action), HIGH_IMPACT_ACTIONS
                )

    def test_every_boundary_category_is_reachable_from_some_verb(self):
        # The class, not the instance. A category with no concrete spelling that
        # resolves to it never fires, and nothing said so -- which is how
        # `binding_legal_commitment` sat inert since it was written. Derived
        # from the frozenset, so a category added later without a mapping fails
        # here rather than being discovered by a reviewer.
        probes = {
            "irreversible_bulk_deletion": "delete_all",
            "financial_transaction": "transfer_funds",
            "credential_or_access_change": "rotate_credentials",
            "sign_or_certify_professional_work": "sign_drawing",
            "binding_legal_commitment": "accept_contract",
            "public_publication": "publish_report",
            "final_submission": "submit_permit",
            "scheduled_task_change": "create_scheduled_task",
            "governance_or_master_change": "modify_separation_governance",
        }
        self.assertEqual(set(probes), set(HIGH_IMPACT_ACTIONS), "a category has no probe")
        for category, action in sorted(probes.items()):
            with self.subTest(category=category):
                self.assertEqual(PolicyEnforcementPoint._boundary_category(action), category)


class GovernanceMountAdmissionTests(unittest.TestCase):
    """A deferred gap, recorded as a tripwire rather than left to be rediscovered.

    `admit_delegation_packet` starts with the unrecognized verb `admit`, so it
    classifies as a mutation. Full evaluation then demands a writer lease and a
    packet whose write target covers `mount:governance` -- and `PacketGuard`
    requires a write target registered to a brain unit, which a mount handle can
    never be. A lease and a signed grant CAN both be minted for the mount; the
    packet layer is what makes the path impossible.

    Its real side effect is an append to a hash-chained audit ledger, not a
    mutation of a canonical brain record, and modelling it as the latter is what
    produces the dead end. Closing it means introducing an append-only audit
    authorization path -- a new category of permitted action in the governance
    model, which is Joe's decision and not a mechanical edit. `enforce()` has no
    call sites, so nothing is broken today; the moment it is wired, this mount
    bricks.

    These tests assert the CURRENT state deliberately. That is not the
    "asserting the defect it was written to prevent" pattern this record warns
    about: nothing here claims the behaviour is correct. It is a tripwire, so
    that adding the audit path fails loudly and forces this class and the record
    to be updated together, instead of the gap being rediscovered by a
    twenty-ninth review.
    """

    MOUNT = "mount:governance"

    def setUp(self):
        self.registry, self.lease = registry_and_lease()
        self.pep = PolicyEnforcementPoint(ROOT, registry=self.registry, clock=lambda: NOW)

    def test_the_admission_verb_still_classifies_as_a_mutation(self):
        self.assertTrue(
            PolicyEnforcementPoint._is_mutating(
                ToolRequest(agent=CHIEF, action="admit_delegation_packet", resource=self.MOUNT)
            )
        )

    def test_a_read_only_governance_tool_is_still_reachable(self):
        # The control. Without it, "admission is denied" says nothing about the
        # mount -- it could be denied because the mount is unreachable for every
        # tool, which would be a different and larger problem.
        decision = self.pep.evaluate(
            ToolRequest(
                agent=CHIEF, action="validate_packet", resource=self.MOUNT, owner_brain="APEX"
            )
        )
        self.assertTrue(decision.allowed, decision.reasons)

    def test_admission_is_denied_for_want_of_an_audit_authorization_path(self):
        decision = self.pep.evaluate(
            ToolRequest(
                agent=CHIEF,
                action="admit_delegation_packet",
                resource=self.MOUNT,
                owner_brain="APEX",
            )
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(
            any("writer lease" in reason for reason in decision.reasons),
            "if this no longer demands a lease, the audit path was added -- update "
            "this class and the record in docs/REPO_OPTIMIZATION_2026-07-25.md",
        )


class ThirtyThirdPassRegressionTests(unittest.TestCase):
    """The packet's own concurrency controls, which nothing read.

    `require_expected_version` and `require_idempotency_key` are REQUIRED fields
    of the delegation schema, so every validated write-bearing packet states a
    position on both, and no rule consulted either. A packet setting both to
    `true` admitted a mutating request that supplied neither.

    Every case here varies ONE thing against a control that differs only in
    that thing, because the reproduction for this finding first appeared to
    deny for the flag when it was actually denying for an unnamed operation --
    two variables, one conclusion, and the conclusion was wrong.
    """

    def setUp(self):
        self.registry, self.lease = registry_and_lease()
        self.pep = PolicyEnforcementPoint(ROOT, registry=self.registry, clock=lambda: NOW)
        self.helper = FifteenthPassRegressionTests("setUp")
        self.helper.registry, self.helper.lease = self.registry, self.lease
        self.helper.pep = self.pep

    def _packet(self, **contract_overrides):
        packet = self.helper._write_bearing_delegation()
        packet["mutation_contract"].update(contract_overrides)
        return packet

    def _request(self, packet, **overrides):
        request = self.helper._request(packet)
        # The lawful operation, always. Omitting it denies for a DIFFERENT
        # reason, which is how the first reproduction of this finding misread
        # itself.
        return dataclasses.replace(request, operation="upsert", **overrides)

    def test_a_demanded_expected_version_must_be_supplied(self):
        decision = self.pep.evaluate(self._request(self._packet(), idempotency_key="key-1"))
        self.assertFalse(decision.allowed)
        self.assertTrue(
            any("no expected_version" in reason for reason in decision.reasons),
            decision.reasons,
        )

    def test_a_demanded_idempotency_key_must_be_supplied(self):
        decision = self.pep.evaluate(self._request(self._packet(), expected_version="rev-7"))
        self.assertFalse(decision.allowed)
        self.assertTrue(
            any("no idempotency_key" in reason for reason in decision.reasons),
            decision.reasons,
        )

    def test_carrying_both_controls_is_allowed(self):
        # The control for the two above. Without it, "denied" could mean the
        # write path is denied for every request, in which case the controls
        # above are proving nothing.
        decision = self.pep.evaluate(
            self._request(self._packet(), expected_version="rev-7", idempotency_key="key-1")
        )
        self.assertTrue(decision.allowed, decision.reasons)

    def test_a_packet_that_waives_both_needs_neither(self):
        # The reverse direction. A fix that demanded these controls
        # unconditionally would deny lawful appends to append-only records,
        # where no version exists to compare against -- fail-shut instead of
        # fail-open, and just as broken. This case differs from
        # `test_a_demanded_expected_version_must_be_supplied` in the FLAGS
        # alone.
        decision = self.pep.evaluate(
            self._request(
                self._packet(require_expected_version=False, require_idempotency_key=False)
            )
        )
        self.assertTrue(decision.allowed, decision.reasons)

    def test_a_blank_control_is_not_a_supplied_one(self):
        # `expected_version=""` satisfies a presence check and carries nothing
        # to compare against. The whitespace form is the one a template
        # substitution produces.
        decision = self.pep.evaluate(
            self._request(self._packet(), expected_version="   ", idempotency_key="key-1")
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(
            any("no expected_version" in reason for reason in decision.reasons),
            decision.reasons,
        )

    def test_a_malformed_flag_does_not_waive_the_control(self):
        # The schema rejects a non-boolean flag before this rule sees it, so
        # this exercises the rule directly: it must not be the schema alone
        # standing between `"false"` -- truthy in Python -- and a disabled
        # control.
        # Both spellings, because they fail differently. `"false"` is truthy, so
        # a plain `if not demanded: continue` happens to hold the line against
        # it -- which is why the truthiness mutant SURVIVED against that case
        # alone. `0` is falsy, and under truthiness it silently waives the
        # control. Only the second case makes "only `False` and absence waive"
        # an enforced claim rather than a comment.
        for malformed in ("false", 0, "", []):
            with self.subTest(flag=malformed):
                errors = self.pep._packet_concurrency_errors(
                    self._request(self._packet(), idempotency_key="key-1"),
                    self._packet(require_expected_version=malformed),
                )
                self.assertTrue(any("no expected_version" in error for error in errors), errors)

    def test_a_malformed_contract_is_refused_rather_than_raising(self):
        errors = self.pep._packet_concurrency_errors(
            self._request(self._packet()), {"mutation_contract": ["append"]}
        )
        self.assertTrue(any("must be an object" in error for error in errors), errors)

    def test_a_read_carries_no_such_obligation(self):
        # The controls bind writes. Demanding them of a read would deny every
        # governed read issued under a write-bearing delegation.
        errors = self.pep._packet_concurrency_errors(
            dataclasses.replace(self._request(self._packet()), mutating=False, operation=None),
            self._packet(),
        )
        self.assertEqual(errors, [])

    def test_every_schema_declared_control_is_enforced(self):
        # The hand-enumerated-list defect: a third control added to
        # `mutation_contract` would be a required schema field that no rule
        # reads, which is the exact finding this class closes. Comparing
        # against the schema means the omission fails here rather than in a
        # review round.
        schema = json.loads(
            (ROOT / "schemas" / "delegation_packet.schema.json").read_text(encoding="utf-8")
        )
        declared = {
            name
            for name in schema["properties"]["mutation_contract"]["required"]
            if name.startswith("require_")
        }
        enforced = {flag for flag, _field, _why in PolicyEnforcementPoint._CONCURRENCY_CONTROLS}
        self.assertEqual(
            declared,
            enforced,
            "the schema requires a control this gate does not read, or vice versa",
        )

    def test_the_obliged_request_fields_exist(self):
        # `getattr(request, field_name)` would raise AttributeError inside the
        # enforcement point if a control named a field `ToolRequest` does not
        # carry -- a crash where a denial belongs.
        names = {f.name for f in dataclasses.fields(ToolRequest)}
        for _flag, field_name, _why in PolicyEnforcementPoint._CONCURRENCY_CONTROLS:
            with self.subTest(field=field_name):
                self.assertIn(field_name, names)

    def test_a_non_string_control_is_refused_by_normalization(self):
        # Same class as every other caller-supplied field: a list reaching
        # `.strip()` must be reported and blanked, not raised.
        _normalized, errors = PolicyEnforcementPoint.normalize(
            ToolRequest(
                agent=CHIEF,
                action="write",
                resource="APEX/Strategy-Campaigns",
                expected_version=["rev-7"],
            )
        )
        self.assertTrue(
            any("expected_version must be a string" in error for error in errors), errors
        )


class ThirtyFifthPassRegressionTests(unittest.TestCase):
    """`scheduled_task_change` gated ordinary task work and missed real schedules.

    `task` was in the noun set, so `create_task` and `delete_task` -- ordinary
    task-registry writes -- demanded Joe's personally signed instruction.
    AGENTS.md reserves "scheduled-task creation or deletion"; a bare task is not
    a schedule, and a boundary that fires on ordinary work is one an operator
    learns to wave through.

    Removing `task` exposed the opposite defect in the same rule, and fixing
    that introduced a third: see the two `MUST_NOT` read cases below. Every
    round of this rule has over- or under-gated in one direction while being
    correct in the other, which is why both lists are exhaustive rather than
    sampled.
    """

    # Genuine scheduled-task changes. Spellings a real dispatcher produces:
    # snake, camel, verb-led, and the un-/re- forms.
    MUST_GATE = (
        "create_scheduled_task",
        "delete_scheduled_task",
        "create_cron_job",
        "delete_cron",
        "delete_crontab",
        "add_schedule",
        "remove_schedule",
        "register_cron",
        "unregister_scheduled_task",
        "remove_timer",
        "schedule_task",
        "scheduleTask",
        "scheduleReport",
        "unschedule_report",
        "reschedule_job",
        "rescheduleMission",
        "createScheduledTask",
        "delete_cron_task",
    )
    # Ordinary work that must NOT need Joe's signature. The `task` group is the
    # finding; the READ group is the defect the first fix introduced, where
    # `schedule` counted as its own verb anywhere in the name and gated
    # `read_schedule`.
    MUST_NOT_GATE = (
        "create_task",
        "delete_task",
        "add_task",
        "remove_task",
        "register_task",
        "createTask",
        "read_task",
        "list_tasks",
        "update_task",
        "complete_task",
        "read_schedule",
        "view_schedule",
        "get_cron",
        "export_schedule",
        "list_cron_jobs",
        "scheduler_status",
        "inspect_crontab",
        "create_record",
        "create_document",
        "multitasking_report",
    )

    def setUp(self):
        self.pep = PolicyEnforcementPoint(ROOT, clock=lambda: NOW)

    def test_real_schedule_changes_are_gated(self):
        for action in self.MUST_GATE:
            with self.subTest(action=action):
                self.assertEqual(
                    PolicyEnforcementPoint._boundary_category(action),
                    "scheduled_task_change",
                    f"{action} changes a schedule and must reach the boundary",
                )

    def test_ordinary_work_is_not_gated(self):
        for action in self.MUST_NOT_GATE:
            with self.subTest(action=action):
                self.assertNotEqual(
                    PolicyEnforcementPoint._boundary_category(action),
                    "scheduled_task_change",
                    f"{action} is not a schedule change; gating it demands Joe's "
                    "signature for ordinary work",
                )

    def test_the_gating_is_visible_through_the_public_entry_point(self):
        # `_boundary_category` is private and the previous round learned that a
        # control is only as good as the entry point the system uses: an earlier
        # fix passed when the rule was called directly and failed through
        # `evaluate()`. One case each way, end to end.
        gated = self.pep.evaluate(
            ToolRequest(
                agent=CHIEF,
                action="delete_scheduled_task",
                resource="APEX/Strategy-Campaigns",
                owner_brain="APEX",
            )
        )
        self.assertFalse(gated.allowed)
        self.assertTrue(
            any("scheduled_task_change" in reason for reason in gated.reasons),
            gated.reasons,
        )
        ungated = self.pep.evaluate(
            ToolRequest(
                agent=CHIEF,
                action="create_task",
                resource="APEX/Strategy-Campaigns",
                owner_brain="APEX",
            )
        )
        self.assertFalse(
            any("scheduled_task_change" in reason for reason in ungated.reasons),
            f"an ordinary task write reached the schedule boundary: {ungated.reasons}",
        )

    def test_a_marker_matches_a_token_not_the_whole_action(self):
        # Substring matching against the whole action is what made `delete_thread`
        # a read in round 7. `multitasking` must not acquire a scheduling marker,
        # and `unschedule` must keep one.
        from scripts.policy_enforcement import _is_schedule_marker

        for token in ("schedule", "scheduled", "unschedule", "rescheduled", "cron", "crontab"):
            with self.subTest(carries=token):
                self.assertTrue(_is_schedule_marker(token))
        for token in ("task", "tasks", "multitasking", "record", "document"):
            with self.subTest(lacks=token):
                self.assertFalse(_is_schedule_marker(token))

    def test_a_scheduling_verb_counts_only_in_leading_position(self):
        # The rule that keeps `read_schedule` out. If this ever holds anywhere in
        # the name again, every read of a schedule is gated.
        from scripts.policy_enforcement import _changes_a_schedule

        self.assertTrue(_changes_a_schedule(("schedule", "task")))
        self.assertFalse(_changes_a_schedule(("read", "schedule")))
        self.assertFalse(_changes_a_schedule(("task", "schedule")))

    def test_the_boundary_category_is_still_one_of_the_declared_nine(self):
        # A category returned by the classifier but absent from
        # HIGH_IMPACT_ACTIONS is a gate that never fires -- the round-32 finding.
        self.assertIn("scheduled_task_change", HIGH_IMPACT_ACTIONS)


if __name__ == "__main__":
    unittest.main()


class ThirtySixthPassRegressionTests(unittest.TestCase):
    """Four classifier findings and the delegation action allowlist.

    Two of the four are consequences of the previous round's own narrowing, and
    one is the general case of a defect that round fixed only for schedules.
    """

    # F1: credential and access-control changes. Only `revoke`, `grant`,
    # `rotate` and `authorize` were mapped, so the spellings a dispatcher emits
    # required no instruction at all.
    CREDENTIAL_GATED = (
        "reset_password",
        "change_credentials",
        "update_access_control",
        "delete_api_key",
        "set_permissions",
        "disable_mfa",
        "add_collaborator",
        "change_password",
        "update_acl",
        "regenerate_secret",
        "remove_role",
        "issue_credentials",
        "enable_2fa",
        "replace_keypair",
        "resetPassword",
        "deleteApiKey",
    )
    # The reverse direction. These verbs are the most generic in the vocabulary,
    # so a bare-verb map would have gated most of the repository's mutations.
    CREDENTIAL_UNGATED = (
        "read_password",
        "view_permissions",
        "list_roles",
        "get_token",
        "inspect_acl",
        "describe_access",
        "update_record",
        "create_document",
        "generate_report",
        "update_title",
        "set_status",
        "add_comment",
        "remove_draft",
    )
    # F4: destructive schedule vocabulary, missing because the PREVIOUS round
    # narrowed this rule without re-reading its verb list.
    SCHEDULE_GATED = (
        "destroy_schedule",
        "erase_cron",
        "cancel_scheduled_task",
        "disable_cron",
        "clear_timer",
        "cancel_cron",
        "purge_crontab",
        "drop_schedule",
        "wipe_scheduled_task",
        "cancelScheduledTask",
    )
    SCHEDULE_UNGATED = ("cancel_task", "disable_agent", "clear_cache", "cancel_meeting")
    # F6: reading a high-impact NOUN is not the act. `post`, `purchase`,
    # `invoice` and `transfer` are nouns sitting in a map named for verbs.
    READ_UNGATED = (
        "read_invoice",
        "view_post",
        "get_purchase",
        "inspect_transfer",
        "list_transfers",
        "show_invoice",
        "describe_post",
        "find_purchase",
        "count_invoices",
        "summarize_transfers",
        "fetch_post",
        "query_purchase",
    )
    # The fail-open a leading-token-only fix would have opened. Each of these
    # leads with a token in no map, or leads with a read verb while naming a
    # pure high-impact VERB later.
    STILL_GATED = (
        "publish_report",
        "post_update",
        "send_email",
        "transfer_funds",
        "pay_invoice",
        "purchase_license",
        "invoice_client",
        "read_and_publish_report",
        "read_then_send_email",
        # These two exist because two mutants survived without them.
        #
        # `transfer_and_get_receipt` separates "the LEADING token is a read verb"
        # from "a read verb appears anywhere": the act leads, and a read verb
        # follows. Matching anywhere exempts it and lets a funds transfer
        # through.
        "transfer_and_get_receipt",
        "post_and_list_updates",
        # And these separate ALL mapped tokens being noun-capable from ANY of
        # them being so. Both carry a noun-capable token AND a pure act verb, so
        # `any` grants the exemption while `all` correctly withholds it.
        "read_invoice_and_publish_it",
        "view_post_and_send_email",
        "force_publish",
        "admin_grant_access",
        "broadcast_notice",
        "sign_contract",
        "purge_originals",
    )

    def setUp(self):
        self.registry, self.lease = registry_and_lease()
        self.pep = PolicyEnforcementPoint(ROOT, registry=self.registry, clock=lambda: NOW)

    def _gated(self, action):
        return PolicyEnforcementPoint._boundary_category(action) in HIGH_IMPACT_ACTIONS

    def test_credential_and_access_changes_reach_the_boundary(self):
        for action in self.CREDENTIAL_GATED:
            with self.subTest(action=action):
                self.assertEqual(
                    PolicyEnforcementPoint._boundary_category(action),
                    "credential_or_access_change",
                    f"{action} changes credentials or access and AGENTS.md reserves it",
                )

    def test_ordinary_mutations_are_not_credential_changes(self):
        for action in self.CREDENTIAL_UNGATED:
            with self.subTest(action=action):
                self.assertFalse(
                    self._gated(action),
                    f"{action} is ordinary work; the credential verbs are generic enough "
                    "that a bare-verb map would gate most of this repository",
                )

    def test_destructive_schedule_vocabulary_is_recognised(self):
        for action in self.SCHEDULE_GATED:
            with self.subTest(action=action):
                self.assertEqual(
                    PolicyEnforcementPoint._boundary_category(action),
                    "scheduled_task_change",
                    f"{action} deletes a schedule under a different verb",
                )

    def test_destruction_without_a_schedule_marker_is_not_gated(self):
        for action in self.SCHEDULE_UNGATED:
            with self.subTest(action=action):
                self.assertNotEqual(
                    PolicyEnforcementPoint._boundary_category(action),
                    "scheduled_task_change",
                    f"{action} names no schedule",
                )

    def test_reading_a_high_impact_record_is_not_the_act(self):
        for action in self.READ_UNGATED:
            with self.subTest(action=action):
                self.assertFalse(
                    self._gated(action),
                    f"{action} inspects a record; requiring Joe's signature to LOOK at "
                    "an invoice is the over-gate this fixes",
                )

    def test_the_acts_themselves_are_still_gated(self):
        for action in self.STILL_GATED:
            with self.subTest(action=action):
                self.assertTrue(
                    self._gated(action),
                    f"{action} performs a reserved act; a leading-token-only exemption "
                    "would have waved it through",
                )

    def test_only_noun_capable_verbs_get_the_read_exemption(self):
        # The exemption's whole scope. If a pure verb ever joins this set, every
        # `read_*` spelling of that verb stops being gated.
        from scripts.policy_enforcement import NOUN_CAPABLE_HIGH_IMPACT

        self.assertEqual(NOUN_CAPABLE_HIGH_IMPACT, {"post", "purchase", "invoice", "transfer"})
        for verb in ("publish", "send", "pay", "revoke", "purge", "sign"):
            with self.subTest(verb=verb):
                self.assertNotIn(verb, NOUN_CAPABLE_HIGH_IMPACT)
                self.assertTrue(self._gated(f"read_{verb}_thing"))

    def test_every_mapped_category_is_a_declared_boundary(self):
        # A category the classifier can return but HIGH_IMPACT_ACTIONS does not
        # list is a gate that never fires -- the round-32 finding, re-asserted
        # because this round added a fifth compound rule.
        from scripts.policy_enforcement import HIGH_IMPACT_VERBS

        for category in set(HIGH_IMPACT_VERBS.values()) | {
            "credential_or_access_change",
            "scheduled_task_change",
        }:
            with self.subTest(category=category):
                self.assertIn(category, HIGH_IMPACT_ACTIONS)


class DelegationActionAllowlistTests(unittest.TestCase):
    """`allowed_actions` is required by the schema and no rule read it.

    The same shape as the concurrency controls two rounds earlier: the issuer
    states a bound and the gate ignores it.
    """

    def setUp(self):
        from tests.test_packet_contracts import PacketContractTests

        PacketContractTests.setUpClass()
        base, _ = PacketContractTests().v21_readonly_pair()
        self.base = json.loads(json.dumps(base))
        # Evidence emptied deliberately. `PacketGuard` requires
        # `read_packet_evidence` in `allowed_actions` whenever a delegation
        # carries evidence, so with evidence present the action cannot be
        # withheld and this rule has nothing to refuse. Establishing that was
        # the difference between a demonstrable control and dead code.
        self.base["allowed_evidence"] = []
        self.registry, self.lease = registry_and_lease()
        self.pep = PolicyEnforcementPoint(ROOT, registry=self.registry, clock=lambda: NOW)

    def _decide(self, allowed_actions, action="read_packet_evidence"):
        packet = json.loads(json.dumps(self.base))
        packet["allowed_actions"] = allowed_actions
        return self.pep.evaluate(
            ToolRequest(
                agent=self.base["agent"],
                action=action,
                resource=self.base["memory_namespace"],
                owner_brain=self.base["owner_brain"],
                packet=packet,
                resource_id=self.base["resource_id"],
            )
        )

    def test_a_withheld_delegation_action_is_refused(self):
        decision = self._decide(["analyze"])
        self.assertFalse(decision.allowed)
        self.assertTrue(any("withheld" in reason for reason in decision.reasons), decision.reasons)

    def test_a_granted_delegation_action_is_allowed(self):
        # The control. Differs from the case above in `allowed_actions` ALONE,
        # which is what attributes the denial to the action rule rather than to
        # the namespace, lease, or operation bindings that also run.
        decision = self._decide(["read_packet_evidence", "analyze"])
        self.assertTrue(decision.allowed, decision.reasons)

    def test_dispatcher_verbs_are_left_to_the_other_bindings(self):
        # A stricter rule -- deny anything not literally listed -- denies every
        # `read` and `write`, because no dispatcher verb is a member of the
        # schema's six-value enum. That is fail-shut on the whole lawful path.
        for action in ("read", "read_record", "list"):
            with self.subTest(action=action):
                decision = self._decide(["analyze"], action=action)
                self.assertFalse(
                    any("withheld" in reason for reason in decision.reasons),
                    f"{action} is dispatcher vocabulary, not a delegation action: "
                    f"{decision.reasons}",
                )

    def test_the_vocabulary_comes_from_the_schema(self):
        # Restating the enum here and in the schema is two enforceable answers
        # to one question. If the schema grows a seventh action, the rule must
        # see it without an edit.
        schema = json.loads(
            (ROOT / "schemas" / "delegation_packet.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            # Read through the enforcement point's ROOT, which is what the rule
            # itself now uses -- a staticmethod call here would test a different
            # source than the code does.
            self.pep._delegation_action_vocabulary(),
            frozenset(schema["properties"]["allowed_actions"]["items"]["enum"]),
        )


class LifecycleReloadTests(unittest.TestCase):
    """A demoted specialist must not keep authority in a running process.

    `__init__` read the brain manifests once, so a long-lived enforcement point
    kept whatever stage was current when it was constructed. A specialist
    demoted to `restricted` or `retired` in the canonical manifest went on being
    authorized as `active` by every already-running process -- authority
    surviving its own revocation, which is precisely what a lifecycle gate
    exists to prevent.
    """

    AGENT = "apex_war_architect"

    def setUp(self):
        import shutil
        import tempfile

        self.tmp = Path(tempfile.mkdtemp()) / "repo"
        # Only what construction reads: the roster, the brain manifests, the
        # schemas PacketGuard compiles, and the mount config. Copying the whole
        # tree pulled in node_modules and made this the slowest test in the
        # suite for no added coverage.
        self.tmp.mkdir(parents=True)
        for relative in (".codex", "brains", "schemas", "config"):
            source = ROOT / relative
            if source.exists():
                shutil.copytree(source, self.tmp / relative)
        self.manifest = self.tmp / "brains" / "apex" / "agents.toml"
        self.original = self.manifest.read_text(encoding="utf-8")
        self.pep = PolicyEnforcementPoint(self.tmp, clock=lambda: NOW)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp.parent, ignore_errors=True)

    def _set_status(self, status):
        lines, current = [], None
        for line in self.original.splitlines():
            match = re.match(r"\[agents\.([a-z0-9_]+)\]", line.strip())
            if match:
                current = match.group(1)
            if current == self.AGENT and line.strip().startswith("status"):
                line = f'status = "{status}"'
            lines.append(line)
        self.manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _mutating_request(self):
        return ToolRequest(
            agent=self.AGENT,
            action="write",
            resource="APEX/Strategy-Campaigns",
            owner_brain="APEX",
            mutating=True,
        )

    def test_a_promotion_after_construction_is_seen(self):
        # The direction that proves the reload is real rather than the cache
        # merely being cleared: an agent PROMOTED to active stops being refused
        # by the lifecycle rule. Without this, "still denied" would be
        # indistinguishable from "reload broken and everything denies".
        self._set_status("active")
        self.assertEqual(self.pep._spec(self.AGENT).get("status"), "active")
        self.assertEqual(self.pep._lifecycle_stage(self._mutating_request()), [])

    def test_a_demotion_after_construction_revokes_authority(self):
        self._set_status("active")
        self.assertEqual(self.pep._lifecycle_stage(self._mutating_request()), [])
        self._set_status("retired")
        reasons = self.pep._lifecycle_stage(self._mutating_request())
        self.assertTrue(reasons, "a retired specialist kept the authority it was demoted out of")
        self.assertIn("retired", reasons[0])

    def test_an_unreadable_manifest_does_not_preserve_authority(self):
        # Failure to reload must not mean "everyone keeps what they had". A
        # manifest that has become unparseable is not evidence of anyone's
        # stage, so the cache is dropped rather than retained.
        self._set_status("active")
        self.assertEqual(self.pep._lifecycle_stage(self._mutating_request()), [])
        self.manifest.write_text("this is not valid toml = = =\n", encoding="utf-8")
        self.assertTrue(
            self.pep._lifecycle_stage(self._mutating_request()),
            "an unreadable manifest left the previous 'active' stage in force",
        )

    def test_an_unchanged_manifest_is_not_reparsed(self):
        # The reload is keyed on a change signature so the hot path does not
        # re-parse two TOML files per authorization. If this ever reloads
        # unconditionally, the cost is paid on every call.
        calls = []
        original = policy_enforcement._load_brain_manifests

        def counted(root):
            calls.append(root)
            return original(root)

        policy_enforcement._load_brain_manifests = counted
        try:
            for _ in range(5):
                self.pep._spec(self.AGENT)
            self.assertEqual(calls, [], "unchanged manifests were re-parsed")
            self._set_status("active")
            self.pep._spec(self.AGENT)
            self.assertEqual(len(calls), 1, "a changed manifest was not re-parsed exactly once")
        finally:
            policy_enforcement._load_brain_manifests = original

    def test_the_signature_notices_a_same_size_edit(self):
        # mtime AND size, because either alone misses a case: a status swapped
        # between two equal-length words leaves the size identical.
        before = self.pep._manifest_signature()
        self._set_status("active")
        self.assertNotEqual(before, self.pep._manifest_signature())

    def test_an_agent_with_no_status_may_not_mutate(self):
        # The fail-open the reload test surfaced, asserted on its own terms
        # rather than only through the unreadable-manifest path. `None` is in no
        # frozenset, so a denylist of non-executing stages permitted it.
        # Drop the status line inside THIS agent's table only, so every other
        # agent keeps its stage and the denial is attributable to this one.
        lines, current, removed = [], None, 0
        for line in self.original.splitlines():
            match = re.match(r"\[agents\.([a-z0-9_]+)\]", line.strip())
            if match:
                current = match.group(1)
            if current == self.AGENT and line.strip().startswith("status"):
                removed += 1
                continue
            lines.append(line)
        self.assertEqual(removed, 1, "the fixture removed no status line, so it tests nothing")
        self.manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.assertIsNone(self.pep._spec(self.AGENT).get("status"))
        reasons = self.pep._lifecycle_stage(self._mutating_request())
        self.assertTrue(reasons, "an agent with no lifecycle stage was allowed to mutate")
        self.assertIn("unknown", reasons[0])

    def test_only_the_active_stage_executes(self):
        # Every stage the manifests can carry, plus the absent case. A denylist
        # would have to enumerate all of them; this asserts the allowlist.
        from scripts.policy_enforcement import NON_EXECUTING_STAGES

        executing = self.pep._executing_stages()
        self.assertTrue(executing, "the registry declared no executing stage")
        for stage in sorted(executing):
            with self.subTest(executing=stage):
                self._set_status(stage)
                self.assertEqual(self.pep._lifecycle_stage(self._mutating_request()), [])
        for stage in sorted(NON_EXECUTING_STAGES) + ["invented_stage", ""]:
            with self.subTest(stage=stage):
                self._set_status(stage)
                self.assertTrue(
                    self.pep._lifecycle_stage(self._mutating_request()),
                    f"stage {stage!r} is not a declared executing stage",
                )


class CrossBrainRegistryTests(unittest.TestCase):
    """A registry holding both rosters is not shared reading.

    `config/` was a brain-neutral prefix, and `config/specialist_corps.toml`
    holds `apex_roster`, `jeos_roster`, both brain manifests, the mirrored
    mappings, and every namespace and write target. So an APEX specialist
    declaring `owner_brain: APEX` read the complete JEOS roster with
    `allowed=True` and no reasons.

    The first reproduction of this omitted `owner_brain` and denied for the
    brain-lock's own "state your brain" rule, which looked like a refutation. It
    was a faulty setup: with the field supplied, the read is allowed. A denial
    for the wrong reason is not evidence.
    """

    def setUp(self):
        self.registry, self.lease = registry_and_lease()
        self.pep = PolicyEnforcementPoint(ROOT, registry=self.registry, clock=lambda: NOW)

    def _read(self, agent, brain, resource):
        return self.pep.evaluate(
            ToolRequest(agent=agent, action="read", resource=resource, owner_brain=brain)
        )

    def test_a_specialist_cannot_read_the_cross_brain_registries(self):
        from scripts.policy_enforcement import CROSS_BRAIN_REGISTRIES

        for agent, brain in (("apex_war_architect", "APEX"), ("jeos_life_architect", "JEOS")):
            for registry in CROSS_BRAIN_REGISTRIES:
                with self.subTest(agent=agent, registry=registry):
                    decision = self._read(agent, brain, registry)
                    self.assertFalse(
                        decision.allowed,
                        f"{agent} read {registry}, which carries the other brain's roster",
                    )
                    self.assertTrue(
                        any("both brains" in reason for reason in decision.reasons),
                        decision.reasons,
                    )

    def test_the_chief_still_reads_them(self):
        # The control, and the point of the exemption: Agent 007 is the sole
        # cross-brain agent and routing work requires seeing both rosters.
        # Without this, "denied" could mean the files became unreadable to
        # everyone, which would break routing rather than isolate brains.
        from scripts.policy_enforcement import CROSS_BRAIN_REGISTRIES

        for registry in CROSS_BRAIN_REGISTRIES:
            with self.subTest(registry=registry):
                decision = self._read(CHIEF, "APEX", registry)
                self.assertTrue(decision.allowed, decision.reasons)

    def test_the_rest_of_config_stays_neutral(self):
        # The reverse direction. Revoking the whole `config/` exemption would
        # deny a specialist the mount list, mission catalog and value policy it
        # legitimately works under -- fail-shut, and the neutral set exists
        # precisely because the brain lock now denies anything it cannot classify.
        for resource in (
            "config/mcp_mounts.toml",
            "config/mission_catalog.toml",
            "config/value_policy.toml",
            "config/portfolio_policy.toml",
            "docs/AGENTS_INDEX.md",
            "schemas/delegation_packet.schema.json",
        ):
            with self.subTest(resource=resource):
                decision = self._read("apex_war_architect", "APEX", resource)
                self.assertTrue(decision.allowed, decision.reasons)

    def test_a_registry_is_matched_exactly_not_by_prefix(self):
        # `AGENTS.md` matching `AGENTS.md.private` was a real finding in the
        # neutral-prefix rule. This comparison must not repeat it in reverse: a
        # prefix rule here would silently reclassify sibling paths.
        self.assertEqual(
            PolicyEnforcementPoint._cross_brain_registry("config/specialist_corps.toml"),
            "config/specialist_corps.toml",
        )
        self.assertIsNone(
            PolicyEnforcementPoint._cross_brain_registry("config/specialist_corps.toml.bak")
        )

    def test_a_registry_is_never_brain_neutral(self):
        # Neutrality waives BOTH the ownership check and packet admission, so a
        # registry that reached the prefix loop would be exempted by the folder
        # it lives in. Asserted on the classifier directly, because the two
        # exemptions are read from this one predicate.
        from scripts.policy_enforcement import CROSS_BRAIN_REGISTRIES

        for registry in CROSS_BRAIN_REGISTRIES:
            with self.subTest(registry=registry):
                self.assertFalse(PolicyEnforcementPoint._is_brain_neutral(registry))
        self.assertTrue(PolicyEnforcementPoint._is_brain_neutral("config/mcp_mounts.toml"))

    def test_no_config_file_naming_both_brains_is_silently_neutral(self):
        # The hand-enumerated-list guard. A new cross-brain registry dropped
        # into `config/` would inherit the directory exemption, which is exactly
        # how this finding happened. Any file naming both brains must be either
        # a declared registry or in the reviewed-shared set below.
        from scripts.policy_enforcement import CROSS_BRAIN_REGISTRIES

        # Reviewed by hand and shared on purpose: these define missions, value
        # thresholds and mounts that BOTH brains work under. They name the brains
        # without enumerating the other brain's agents.
        reviewed_shared = {
            "config/mcp_mounts.toml",
            "config/mission_catalog.toml",
            "config/value_policy.toml",
        }
        for path in sorted((ROOT / "config").glob("*.toml")):
            relative = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8").lower()
            if "apex" not in text or "jeos" not in text:
                continue
            with self.subTest(config=relative):
                self.assertIn(
                    relative,
                    set(CROSS_BRAIN_REGISTRIES) | reviewed_shared,
                    f"{relative} names both brains but is neither a declared "
                    "cross-brain registry nor reviewed as shared; it currently "
                    "inherits the config/ neutral exemption",
                )


class MountRegistryReloadTests(unittest.TestCase):
    """The untouched sibling of the manifest cache.

    The previous round made the brain manifests reload when they change and left
    `_registered_mounts` caching for the life of the process. Removing a mount
    from `config/mcp_mounts.toml` -- which is what an emergency connector
    revocation IS -- therefore had no effect on any already-running enforcement
    point. Fixing the instance and not the class is how a fix becomes the next
    round's finding.
    """

    def setUp(self):
        import shutil
        import tempfile

        self.tmp = Path(tempfile.mkdtemp()) / "repo"
        self.tmp.mkdir(parents=True)
        for relative in (".codex", "brains", "schemas", "config"):
            source = ROOT / relative
            if source.exists():
                shutil.copytree(source, self.tmp / relative)
        self.mounts = self.tmp / "config" / "mcp_mounts.toml"
        self.registry, self.lease = registry_and_lease()
        self.pep = PolicyEnforcementPoint(self.tmp, registry=self.registry, clock=lambda: NOW)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp.parent, ignore_errors=True)

    def _revoke(self, name):
        text = self.mounts.read_text(encoding="utf-8")
        kept = re.sub(
            r'\[\[mounts\]\][^\[]*?name\s*=\s*"' + name + r'".*?(?=\[\[mounts\]\]|\Z)',
            "",
            text,
            flags=re.S,
        )
        self.assertNotEqual(kept, text, f"the fixture removed no {name} mount, so it tests nothing")
        self.mounts.write_text(kept, encoding="utf-8")

    def test_a_revoked_mount_stops_being_registered(self):
        self.assertIn("gdrive", self.pep._registered_mounts())
        self._revoke("gdrive")
        self.assertNotIn(
            "gdrive",
            self.pep._registered_mounts(),
            "a revoked mount stayed registered until the process restarted",
        )

    def test_the_surviving_mounts_are_still_registered(self):
        # The control: the reload must not empty the registry, which would deny
        # every mount and look like a successful revocation of one.
        self._revoke("gdrive")
        self.assertIn("governance", self.pep._registered_mounts())

    def test_an_unreadable_mount_list_registers_nothing(self):
        # Fail-closed here, unlike the lifecycle cache: an unregistered mount
        # name is refused, so clearing the cache denies rather than permits. The
        # direction was checked rather than assumed, because the same clearing
        # move in the lifecycle fix turned out to open a hole.
        self.assertIn("gdrive", self.pep._registered_mounts())
        self.mounts.write_text("not valid toml = = =\n", encoding="utf-8")
        self.assertEqual(self.pep._registered_mounts(), frozenset())

    def test_an_unchanged_file_is_not_reparsed(self):
        first = self.pep._registered_mounts()
        second = self.pep._registered_mounts()
        self.assertIs(first, second, "the mount list was re-read with nothing changed")

    def test_a_deleted_mount_file_registers_nothing(self):
        self.assertIn("gdrive", self.pep._registered_mounts())
        self.mounts.unlink()
        self.assertEqual(self.pep._registered_mounts(), frozenset())


class MalformedMountRegistryTests(unittest.TestCase):
    """Valid TOML with the wrong SHAPE must deny, not crash.

    The round-37 reload caught `OSError` and `TOMLDecodeError` and neither
    `TypeError` nor `AttributeError`. `mounts = 1` raised
    `'int' object is not iterable` and `mounts = ["gdrive"]` raised
    `'str' object has no attribute 'get'`, so an ordinary authorization UNWOUND
    out of `evaluate()` -- and because `enforce()` records its decision only
    after evaluation returns, the request got neither a fail-closed denial nor an
    audit event.

    The same class this module fixed for `ToolRequest` fields three times over:
    type-check before the typed operation. Here the untrusted input is a file on
    disk rather than a caller's argument.
    """

    SHAPES = (
        ("mounts = 1\n", "a scalar where the array belongs"),
        ('mounts = ["gdrive"]\n', "an array of strings, not tables"),
        ("mounts = {name = 'x'}\n", "a table where the array belongs"),
        ("[[mounts]]\nname = 42\n", "a non-string name"),
        ("[[mounts]]\nname = ''\n", "a blank name"),
        ("[[mounts]]\nother = 'x'\n", "an entry with no name at all"),
        ("nothing = true\n", "no mounts key"),
        ("= = broken\n", "not TOML at all"),
        ("", "an empty file"),
    )

    def setUp(self):
        import shutil
        import tempfile

        self.tmp = Path(tempfile.mkdtemp()) / "repo"
        self.tmp.mkdir(parents=True)
        for relative in (".codex", "brains", "schemas", "config"):
            source = ROOT / relative
            if source.exists():
                shutil.copytree(source, self.tmp / relative)
        self.mounts = self.tmp / "config" / "mcp_mounts.toml"
        self.registry, self.lease = registry_and_lease()
        self.pep = PolicyEnforcementPoint(self.tmp, registry=self.registry, clock=lambda: NOW)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp.parent, ignore_errors=True)

    def _read_a_mount(self):
        return self.pep.evaluate(
            ToolRequest(agent=CHIEF, action="read", resource="mount:gdrive", owner_brain="APEX")
        )

    def test_a_well_formed_registry_still_allows_a_mount_read(self):
        # The control. Without it, "denied for every shape" is indistinguishable
        # from "mount reads are denied outright", which would be an outage rather
        # than a guard.
        self.assertTrue(self._read_a_mount().allowed, "a lawful mount read must pass")

    def test_every_malformed_shape_denies_rather_than_raising(self):
        for content, description in self.SHAPES:
            with self.subTest(shape=description):
                self.mounts.write_text(content, encoding="utf-8")
                try:
                    decision = self._read_a_mount()
                except Exception as error:  # noqa: BLE001 - the defect IS the raise
                    self.fail(
                        f"{description} raised {type(error).__name__} out of evaluate(), so "
                        "the request got no denial and no audit event"
                    )
                self.assertFalse(
                    decision.allowed,
                    f"{description} was treated as a registry authorizing the mount",
                )
                self.assertTrue(decision.reasons, "a denial must say why")

    def test_the_shape_guard_yields_nothing_for_a_malformed_registry(self):
        # Asserted on the helper too, because the decision above could deny for
        # an unrelated reason and still look correct.
        from scripts.policy_enforcement import _mount_names

        for value in (
            1,
            "gdrive",
            None,
            [],
            {},
            {"mounts": 1},
            {"mounts": ["x"]},
            # A non-string and a whitespace-only name. These two are what
            # separate `isinstance(name, str) and name.strip()` from a bare
            # `if name:` -- the truthiness mutant survived until they were here,
            # because every other malformed shape denies under both spellings.
            {"mounts": [{"name": 42}]},
            {"mounts": [{"name": "   "}]},
            {"mounts": [{"name": True}]},
        ):
            with self.subTest(value=value):
                self.assertEqual(_mount_names(value), set())

    def test_the_shape_guard_reads_a_well_formed_registry(self):
        # And the reverse: a guard that returned an empty set unconditionally
        # would pass every test above while denying every mount.
        from scripts.policy_enforcement import _mount_names

        self.assertEqual(
            _mount_names({"mounts": [{"name": "gdrive"}, {"name": "governance"}]}),
            {"gdrive", "governance"},
        )


class ThirtyNinthPassRegressionTests(unittest.TestCase):
    """Four over- and under-gates, two of them inside earlier fixes of mine."""

    # AGENTS.md section 9 reserves "final PERMIT OR AGENCY submission". `final` and
    # `submission` were in the qualifier set, so ordinary internal work was gated.
    SUBMISSION_GATED = (
        "submit_permit",
        "submit_permit_application",
        "submit_to_agency",
        "submit_agency_filing",
        "submit_final_permit",
        "submit_regulatory_filing",
        "submitPermit",
        # Naming the category itself must still gate, via the folded fallback.
        "final_submission",
    )
    SUBMISSION_UNGATED = (
        "submit_final_report",
        "submit_final_draft",
        "submit_final_version",
        "submit_report",
        "submit_draft",
        "submit_form",
        "submit_timesheet",
    )
    # `send` was mapped bare, so a scheduled brief to Joe demanded a signed
    # instruction -- and the issuer refuses without a TTY, so the unattended path
    # could not be authorized at all.
    SEND_GATED = (
        "send_email",
        "send_report",
        "send_update",
        "send_newsletter",
        "send_report_to_client",
        "send_to_public",
        "send_press_release",
        # The bypass the absence requirement exists for: an internal marker does
        # not buy an exemption when an external one is also present.
        "send_report_to_joe_and_client",
        "sendEmail",
    )
    SEND_UNGATED = (
        "send_report_to_joe",
        "send_to_joe",
        "send_brief_to_joe",
        "send_internal_note",
        "send_to_roundtable",
        "send_to_self",
        "send_to_inbox",
    )

    def _gated(self, action):
        return PolicyEnforcementPoint._boundary_category(action) in HIGH_IMPACT_ACTIONS

    def test_permit_and_agency_submissions_are_gated(self):
        for action in self.SUBMISSION_GATED:
            with self.subTest(action=action):
                self.assertTrue(self._gated(action), f"{action} is a reserved submission")

    def test_an_internal_final_artifact_is_not_a_permit_submission(self):
        for action in self.SUBMISSION_UNGATED:
            with self.subTest(action=action):
                self.assertFalse(
                    self._gated(action),
                    f"{action} is ordinary internal work; 'final' is an adjective on the "
                    "artifact, not a statement about who receives it",
                )

    def test_external_sends_are_gated(self):
        for action in self.SEND_GATED:
            with self.subTest(action=action):
                self.assertEqual(
                    PolicyEnforcementPoint._boundary_category(action),
                    "public_publication",
                    f"{action} may leave the estate and must reach the boundary",
                )

    def test_internal_deliveries_are_not_publications(self):
        for action in self.SEND_UNGATED:
            with self.subTest(action=action):
                self.assertFalse(
                    self._gated(action),
                    f"{action} delivers internally; gating it makes the unattended "
                    "scheduled path unsatisfiable, because the issuer needs a TTY",
                )

    def test_an_unstated_destination_is_still_gated(self):
        # Absence of an external marker is not evidence of an internal
        # destination. `send_report` names neither and must gate.
        from scripts.policy_enforcement import _is_internal_delivery

        self.assertFalse(_is_internal_delivery(("send", "report")))
        self.assertTrue(_is_internal_delivery(("send", "report", "to", "joe")))
        self.assertFalse(_is_internal_delivery(("send", "to", "joe", "and", "client")))


class ExecutingStageTests(unittest.TestCase):
    """Promotion out of `active` must not revoke execution authority.

    Round 36 inverted this rule from a denylist to an allowlist -- correctly --
    and then hardcoded the allowlist as the single value `"active"`.
    `config/specialist_corps.toml` declares
    `connector_stages = ["active", "value-proven"]`, so a specialist promoted to
    the stage the whole lifecycle exists to reach lost the authority it had at
    the stage below. Inverting a denylist is exactly when its contents need
    re-reading against the source.
    """

    AGENT = "apex_war_architect"

    def setUp(self):
        import shutil
        import tempfile

        self.tmp = Path(tempfile.mkdtemp()) / "repo"
        self.tmp.mkdir(parents=True)
        for relative in (".codex", "brains", "schemas", "config"):
            source = ROOT / relative
            if source.exists():
                shutil.copytree(source, self.tmp / relative)
        self.manifest = self.tmp / "brains" / "apex" / "agents.toml"
        self.original = self.manifest.read_text(encoding="utf-8")
        self.registry, self.lease = registry_and_lease()
        self.pep = PolicyEnforcementPoint(self.tmp, registry=self.registry, clock=lambda: NOW)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp.parent, ignore_errors=True)

    def _set_status(self, status):
        lines, current = [], None
        for line in self.original.splitlines():
            match = re.match(r"\[agents\.([a-z0-9_]+)\]", line.strip())
            if match:
                current = match.group(1)
            if current == self.AGENT and line.strip().startswith("status"):
                line = f'status = "{status}"'
            lines.append(line)
        self.manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _request(self):
        return ToolRequest(
            agent=self.AGENT,
            action="write",
            resource="APEX/Strategy-Campaigns",
            owner_brain="APEX",
            mutating=True,
        )

    def test_the_executing_stages_come_from_the_registry(self):
        # Compared against the registry file itself, not a copied list. Two
        # readers of one governance key is how the launcher and this gate would
        # come to disagree about who may act.
        import tomllib

        with (ROOT / "config" / "specialist_corps.toml").open("rb") as handle:
            declared = tomllib.load(handle)["lifecycle"]["connector_stages"]
        self.assertEqual(self.pep._executing_stages(), frozenset(declared))

    def test_every_declared_executing_stage_may_mutate(self):
        for stage in sorted(self.pep._executing_stages()):
            with self.subTest(stage=stage):
                self._set_status(stage)
                self.assertEqual(
                    self.pep._lifecycle_stage(self._request()),
                    [],
                    f"{stage} is a declared executing stage and must be permitted",
                )

    def test_no_other_stage_may_mutate(self):
        from scripts.policy_enforcement import NON_EXECUTING_STAGES

        for stage in sorted(NON_EXECUTING_STAGES) + ["invented_stage", ""]:
            with self.subTest(stage=stage):
                self._set_status(stage)
                self.assertTrue(
                    self.pep._lifecycle_stage(self._request()),
                    f"{stage} is not a declared executing stage",
                )

    def test_an_unresolvable_registry_denies_rather_than_permits(self):
        # If the registry cannot say which stages may execute, none may. The
        # Chief is exempt earlier, so this degrades to "only Agent 007 writes"
        # -- the repository's own shadow posture -- not to an outage or a bypass.
        # Asserted by making the resolver itself fail, rather than by building a
        # new enforcement point against a broken registry -- that raises inside
        # the launcher's loader during construction, which is a different
        # (and also fail-closed) path.
        fresh = PolicyEnforcementPoint(self.tmp, registry=self.registry, clock=lambda: NOW)
        fresh._executing_stages = lambda: frozenset()
        self._set_status("active")
        self.assertTrue(
            fresh._lifecycle_stage(self._request()),
            "an unreadable registry left execution authority in force",
        )
        self.assertEqual(
            fresh._lifecycle_stage(
                ToolRequest(
                    agent=CHIEF,
                    action="write",
                    resource="APEX/Strategy-Campaigns",
                    owner_brain="APEX",
                    mutating=True,
                )
            ),
            [],
            "the Chief must still write when the registry is unreadable",
        )


class ActionVocabularyRootTests(unittest.TestCase):
    """The vocabulary must come from the root the packet is validated against.

    The previous round's fix cached it with `lru_cache(maxsize=1)` over the
    MODULE-level `ROOT`, while `PacketGuard(root)` validates against the
    constructed root. For an alternate checkout whose schema declares an extra
    action, the packet was validated against one schema and the allowlist check
    read another -- so the extra action fell outside the recognised vocabulary
    and `_packet_action_errors` skipped it.
    """

    def setUp(self):
        import shutil
        import tempfile

        self.tmp = Path(tempfile.mkdtemp()) / "repo"
        self.tmp.mkdir(parents=True)
        for relative in (".codex", "brains", "schemas", "config"):
            source = ROOT / relative
            if source.exists():
                shutil.copytree(source, self.tmp / relative)
        self.schema = self.tmp / "schemas" / "delegation_packet.schema.json"
        self.registry, self.lease = registry_and_lease()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp.parent, ignore_errors=True)

    def _pep(self, root):
        return PolicyEnforcementPoint(root, registry=self.registry, clock=lambda: NOW)

    def test_the_vocabulary_follows_the_constructed_root(self):
        document = json.loads(self.schema.read_text(encoding="utf-8"))
        document["properties"]["allowed_actions"]["items"]["enum"].append("novel_action")
        self.schema.write_text(json.dumps(document, indent=2), encoding="utf-8")

        self.assertIn("novel_action", self._pep(self.tmp)._delegation_action_vocabulary())
        # And the control: the module root must be unaffected, which is what
        # proves the cache is keyed rather than shared.
        self.assertNotIn("novel_action", self._pep(ROOT)._delegation_action_vocabulary())

    def test_two_roots_do_not_share_one_cached_answer(self):
        # Order-independent: the module root is read FIRST here, so a
        # `maxsize=1` cache keyed on nothing would return its answer for the
        # alternate root too.
        self._pep(ROOT)._delegation_action_vocabulary()
        document = json.loads(self.schema.read_text(encoding="utf-8"))
        document["properties"]["allowed_actions"]["items"]["enum"].append("second_action")
        self.schema.write_text(json.dumps(document, indent=2), encoding="utf-8")
        self.assertIn("second_action", self._pep(self.tmp)._delegation_action_vocabulary())

    def test_an_unreadable_schema_yields_an_empty_vocabulary(self):
        # Exercised on the reader directly. Constructing a PolicyEnforcementPoint
        # against a root with an unparseable schema raises inside PacketGuard,
        # which is the correct behaviour and is why this rule never runs alone:
        # `_guard_errors` has already denied by then. The empty set is defence in
        # depth, not the thing standing between a bad schema and an allow.
        self.schema.write_text("{ not json", encoding="utf-8")
        self.assertEqual(PolicyEnforcementPoint._action_vocabulary_for(self.tmp), frozenset())

    def test_a_schema_missing_the_enum_yields_an_empty_vocabulary(self):
        self.schema.write_text(json.dumps({"properties": {}}), encoding="utf-8")
        self.assertEqual(PolicyEnforcementPoint._action_vocabulary_for(self.tmp), frozenset())

    def test_a_missing_schema_file_yields_an_empty_vocabulary(self):
        self.schema.unlink()
        self.assertEqual(PolicyEnforcementPoint._action_vocabulary_for(self.tmp), frozenset())


class FixtureClockTests(unittest.TestCase):
    """The suite's clock must agree with the one PacketGuard cannot be given.

    `NOW` was the literal `datetime(2026, 7, 25, 12, 0)`. `registry_and_lease()`
    issues its fixture lease at that instant with the registry's 24-hour maximum
    TTL, and `PacketGuard` checks lease expiry against `datetime.now(UTC)` with no
    injectable clock -- so every lease-bearing test passed until 2026-07-26 12:00Z
    and failed from then on, with nothing in the diff having changed. CI's last
    green run finished at 11:54Z, six minutes before the cliff.

    Two clocks for one decision. The guard's is the one that cannot be injected,
    so the fixture clock is the one that has to track it.
    """

    def test_the_fixture_lease_is_live_against_real_time(self):
        # The assertion that would have caught it. Compared against the REAL
        # clock, deliberately, because the whole defect was that the fixture
        # agreed with itself and not with the guard.
        _registry, lease = registry_and_lease()
        expires = datetime.datetime.fromisoformat(lease["expires_at"])
        real_now = datetime.datetime.now(datetime.UTC)
        self.assertGreater(
            expires,
            real_now,
            "the fixture lease is already expired against the real clock, which is "
            "the clock PacketGuard uses; every lease-bearing test will fail",
        )
        # And not merely live by a second: a suite that takes minutes must not
        # cross the boundary mid-run.
        self.assertGreater(
            expires - real_now,
            datetime.timedelta(hours=1),
            "the fixture lease expires within the hour, so a slow run will "
            "straddle its expiry and fail unpredictably",
        )

    def test_the_fixture_clock_is_not_a_frozen_literal(self):
        # The direct guard against re-freezing. A constant date passes the test
        # above for exactly as long as its lease window, then rots -- which is
        # what happened.
        drift = abs(datetime.datetime.now(datetime.UTC) - NOW)
        self.assertLess(
            drift,
            datetime.timedelta(hours=1),
            "NOW has drifted from the real clock, so it has been pinned to a "
            "literal again; PacketGuard's expiry checks cannot be injected and "
            "will disagree with it",
        )

    def test_the_guard_really_uses_the_real_clock(self):
        # The premise, asserted rather than assumed. If PacketGuard ever gains an
        # injectable clock, the reasoning above stops applying and this class
        # should be revisited rather than silently kept.
        source = (ROOT / "scripts" / "packet_guard.py").read_text(encoding="utf-8")
        self.assertIn(
            "datetime.now(UTC)",
            source,
            "packet_guard no longer reads the real clock directly; re-examine "
            "whether NOW still needs to track it",
        )


class FortiethPassRegressionTests(unittest.TestCase):
    """`overwrite` was reserved for every overwrite, not for originals.

    AGENTS.md section 9 reserves "irreversible bulk deletion or overwrite **of
    originals**", and `overwrite` was mapped bare -- so `overwrite_draft` and
    `overwrite_cache_entry` demanded Joe's personally signed instruction. The
    fourth over-gate of this shape in three rounds: `final`, `send`, `task`, and
    now `overwrite`, each a verb whose reserved meaning lives in its object.
    """

    GATED = (
        "overwrite_originals",
        "overwrite_all_originals",
        "overwrite_original_record",
        "overwriteOriginals",
    )
    # Governance catches these earlier and under the category the contract names
    # for them, so they must still gate -- just not as bulk deletion.
    GATED_AS_GOVERNANCE = ("overwrite_master", "overwrite_canonical_snapshot")
    UNGATED = (
        "overwrite_draft",
        "overwrite_cache_entry",
        "overwrite_temp_file",
        "overwrite_field",
        "overwrite_row",
        "overwrite_config_value",
    )
    # `purge`, `truncate`, `drop`, `wipe` name destruction whatever the object is
    # and must stay bare. Narrowing `overwrite` must not narrow these.
    STILL_BARE = ("purge_records", "truncate_table", "drop_index", "wipe_disk")

    def _category(self, action):
        return PolicyEnforcementPoint._boundary_category(action)

    def test_overwriting_originals_is_gated(self):
        for action in self.GATED:
            with self.subTest(action=action):
                self.assertEqual(self._category(action), "irreversible_bulk_deletion")

    def test_overwriting_a_master_is_still_gated_as_governance(self):
        for action in self.GATED_AS_GOVERNANCE:
            with self.subTest(action=action):
                self.assertEqual(self._category(action), "governance_or_master_change")

    def test_an_ordinary_overwrite_is_not_reserved(self):
        for action in self.UNGATED:
            with self.subTest(action=action):
                self.assertNotIn(
                    self._category(action),
                    HIGH_IMPACT_ACTIONS,
                    f"{action} replaces something that is not an original",
                )

    def test_the_unconditionally_destructive_verbs_are_untouched(self):
        for action in self.STILL_BARE:
            with self.subTest(action=action):
                self.assertEqual(
                    self._category(action),
                    "irreversible_bulk_deletion",
                    f"{action} names destruction whatever its object is",
                )
