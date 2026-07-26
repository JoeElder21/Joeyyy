from pathlib import Path
import unittest

from scripts.orchestration_contract import OrchestrationContract


ROOT = Path(__file__).resolve().parents[1]


class OrchestrationContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = OrchestrationContract(ROOT)

    def test_every_declared_cadence_is_brain_locked_and_agent_007_terminated(self):
        for brain in ("APEX", "JEOS"):
            for cadence in ("daily", "weekly", "monthly"):
                with self.subTest(brain=brain, cadence=cadence):
                    plan = self.contract.cadence_plan(brain, cadence)
                    self.assertEqual(plan.speakers[-1], "apex_chief_of_staff")
                    self.assertFalse(plan.checkpoint.required)
                    for agent in plan.speakers[:-1]:
                        self.assertEqual(self.contract.manifest["agents"][agent]["brain"], brain)

    def test_high_impact_actions_require_a_checkpoint(self):
        plan = self.contract.cadence_plan(
            "APEX", "weekly", requested_actions=("financial_transaction",)
        )
        self.assertTrue(plan.checkpoint.required)
        self.assertIn("financial_transaction", plan.checkpoint.reason)

    def test_shadow_to_active_requires_all_declared_gate_evidence(self):
        required = {
            "static_contracts",
            "typed_2_1_output",
            "controlled_real_mission_per_material_mode",
            "runtime_connector_isolation",
            "readback",
            "versioned_lifecycle_promotion",
        }
        self.assertFalse(self.contract.can_promote("shadow", "active", required - {"readback"}))
        self.assertTrue(self.contract.can_promote("shadow", "active", required))
        self.assertTrue(self.contract.can_promote("active", "restricted", set()))
        self.assertFalse(self.contract.can_promote("candidate", "value-proven", required))

    def test_unknown_brain_and_cadence_fail_closed(self):
        with self.assertRaises(ValueError):
            self.contract.cadence_plan("mixed", "daily")
        with self.assertRaises(ValueError):
            self.contract.cadence_plan("APEX", "hourly")


if __name__ == "__main__":
    unittest.main()
