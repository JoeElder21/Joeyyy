import unittest

from runtime.contracts import structural_errors
from runtime.orchestration import cadence_group_chat, lifecycle_transition_allowed


class RuntimeIntegrationTests(unittest.TestCase):
    def test_jsonschema_collects_multiple_failures(self):
        errors = structural_errors("delegation_packet.schema.json", {})
        self.assertGreater(len(errors), 2)

    def test_cadence_compiles_to_a_brain_locked_group_chat(self):
        plan = cadence_group_chat("APEX", "daily")
        self.assertEqual(plan.manager, "apex_chief_of_staff")
        self.assertEqual(plan.brain, "APEX")
        self.assertTrue(all(agent.startswith("apex_") for agent in plan.participants))

    def test_shadow_promotion_is_a_guarded_edge(self):
        self.assertFalse(lifecycle_transition_allowed("shadow", "active", False))
        self.assertTrue(lifecycle_transition_allowed("shadow", "active", True))
        self.assertFalse(lifecycle_transition_allowed("candidate", "active", True))


if __name__ == "__main__":
    unittest.main()
