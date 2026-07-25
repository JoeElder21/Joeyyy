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

import datetime
import json
import tempfile
import unittest
from pathlib import Path

from runtime.writer_lease import LeaseRegistry
from scripts.agent_runtime import AuditLedger
from scripts.policy_enforcement import (
    AUTHORIZATION_SCHEMAS,
    BRAIN_NEUTRAL_PREFIXES,
    CHIEF,
    HIGH_IMPACT_ACTIONS,
    MUTATING_ACTION_VERBS,
    NON_EXECUTING_STAGES,
    PACKET_ONLY,
    Decision,
    PolicyDenied,
    PolicyEnforcementPoint,
    ToolRequest,
    enforce,
)
from scripts.trusted_launcher import _sign

ROOT = Path(__file__).resolve().parents[1]
SPECIALIST = "apex_war_architect"
JEOS_SPECIALIST = "jeos_reflection_forge"
NOW = datetime.datetime(2026, 7, 25, 12, 0, tzinfo=datetime.UTC)


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
        registry, lease = registry_and_lease(writer_agent=SPECIALIST)
        pep = PolicyEnforcementPoint(ROOT, registry=registry)
        reasons = pep._writer_lease(self._mutating(lease=lease))
        self.assertTrue(any("held by" in reason for reason in reasons))

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
        for resource in ("mount:gdrive", "connector:aps"):
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
        for resource in ("APEX/Strategy-Campaigns", "APEX/Intel-Sources", "docs/README.md"):
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
                    resource="APEX/Strategy-Campaigns",
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
                    resource="APEX/Strategy-Campaigns",
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
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8").lower()
        for fragment in (
            "irreversible bulk deletion",
            "financial transaction",
            "credential or access-control change",
            "signing or certifying professional work",
            "binding legal commitment",
            "public publication",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, text)
        self.assertEqual(len(HIGH_IMPACT_ACTIONS), 6)


if __name__ == "__main__":
    unittest.main()
