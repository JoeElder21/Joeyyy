import unittest

from runtime.autogen_groupchat import load_manifest, plan_group_chat


class AutoGenGroupChatPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_manifest()

    def test_apex_plan_uses_canonical_roster_order(self):
        plan = plan_group_chat(
            "APEX",
            ["apex_delivery_commander", "apex_intelligence_forge"],
            manifest=self.manifest,
        )
        self.assertEqual(
            plan.speaker_order,
            ("apex_delivery_commander", "apex_intelligence_forge"),
        )
        self.assertEqual(plan.manager, "apex_chief_of_staff")

    def test_mixed_brain_participant_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "brain-private"):
            plan_group_chat(
                "APEX", ["apex_war_architect", "jeos_life_architect"], manifest=self.manifest
            )

    def test_unknown_or_empty_participants_are_rejected(self):
        with self.assertRaises(ValueError):
            plan_group_chat("JEOS", [], manifest=self.manifest)
        with self.assertRaises(ValueError):
            plan_group_chat("JEOS", ["not_registered"], manifest=self.manifest)
