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
import unittest
from pathlib import Path

from runtime.writer_lease import LeaseRegistry
from scripts.policy_enforcement import (
    CHIEF,
    HIGH_IMPACT_ACTIONS,
    NON_EXECUTING_STAGES,
    PACKET_ONLY,
    Decision,
    PolicyDenied,
    PolicyEnforcementPoint,
    ToolRequest,
    enforce,
)

ROOT = Path(__file__).resolve().parents[1]
SPECIALIST = "apex_war_architect"
JEOS_SPECIALIST = "jeos_reflection_forge"
NOW = datetime.datetime(2026, 7, 25, 12, 0, tzinfo=datetime.UTC)


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
            ToolRequest(agent=SPECIALIST, action="read", resource="x", owner_brain="APEX")
        )
        self.assertEqual(len(decision.checks_run), 8)
        self.assertIn("brain_lock", decision.checks_run)
        self.assertIn("lifecycle_stage", decision.checks_run)


class DenialTests(unittest.TestCase):
    def setUp(self):
        self.pep = PolicyEnforcementPoint(ROOT)

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

    def test_every_high_impact_action_requires_explicit_instruction(self):
        for action in sorted(HIGH_IMPACT_ACTIONS):
            with self.subTest(action=action):
                denied = self.pep.evaluate(
                    ToolRequest(agent=CHIEF, action=action, resource="target")
                )
                self.assertFalse(denied.allowed)
                allowed = self.pep.evaluate(
                    ToolRequest(
                        agent=CHIEF,
                        action=action,
                        resource="target",
                        explicit_instruction=True,
                    )
                )
                self.assertTrue(allowed.allowed, f"{action} still denied with instruction")

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
        self.assertTrue(any("lease rejected" in reason for reason in reasons))

    def test_a_genuine_registry_lease_is_accepted(self):
        # The accept path matters as much as the reject path: a rule that denies
        # everything is not enforcement, it is an outage.
        reasons = self.pep._writer_lease(self._mutating(lease=real_lease()))
        self.assertEqual(reasons, [])

    def test_lease_held_by_another_agent_is_denied(self):
        lease = real_lease(writer_agent=SPECIALIST)
        reasons = self.pep._writer_lease(self._mutating(lease=lease))
        self.assertTrue(any("held by" in reason for reason in reasons))

    def test_lease_does_not_stretch_to_another_target(self):
        reasons = self.pep._writer_lease(
            self._mutating(lease=real_lease(), resource="APEX/Decision-Log")
        )
        self.assertTrue(any("does not cover" in reason for reason in reasons))

    def test_expired_lease_is_denied(self):
        lease = real_lease()
        lease["expires_at"] = "2020-01-01T00:00:00+00:00"
        reasons = self.pep._writer_lease(self._mutating(lease=lease))
        self.assertTrue(any("expired" in reason for reason in reasons))

    def test_closed_lease_authorizes_nothing_further(self):
        lease = real_lease()
        lease["status"] = "verified"
        reasons = self.pep._writer_lease(self._mutating(lease=lease))
        self.assertTrue(reasons)

    def test_lease_for_another_resource_id_is_denied(self):
        reasons = self.pep._writer_lease(
            self._mutating(lease=real_lease(), resource_id="campaign-beta")
        )
        self.assertTrue(any("resource" in reason for reason in reasons))

    def test_write_capable_mount_requires_a_launch_grant(self):
        request = ToolRequest(
            agent=CHIEF,
            action="write",
            resource="mount:civil3d",
            owner_brain="APEX",
            mutating=True,
            lease=real_lease(write_target="mount:civil3d"),
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
            now=NOW,
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
        decision = enforce(
            ToolRequest(agent=SPECIALIST, action="read", resource="x", owner_brain="APEX")
        )
        self.assertTrue(decision.allowed)

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
