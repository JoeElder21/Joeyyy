from dataclasses import replace
import unittest

from runtime.autogen_groupchat import (
    load_manifest,
    plan_group_chat,
    validate_group_chat_plan,
)


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

    def test_cadence_plan_uses_configured_route_order(self):
        plan = plan_group_chat(
            "JEOS",
            ["jeos_life_architect", "jeos_reflection_forge", "jeos_energy_director"],
            cadence="weekly",
            manifest=self.manifest,
        )
        self.assertEqual(
            plan.speaker_order,
            ("jeos_reflection_forge", "jeos_energy_director", "jeos_life_architect"),
        )
        with self.assertRaisesRegex(ValueError, "excludes participants"):
            plan_group_chat(
                "JEOS",
                ["jeos_lifestyle_systems_builder"],
                cadence="daily",
                manifest=self.manifest,
            )

    def test_manually_constructed_plan_is_revalidated(self):
        plan = plan_group_chat(
            "APEX", ["apex_war_architect"], manifest=self.manifest
        )
        tampered = replace(plan, speaker_order=("jeos_life_architect",))
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_group_chat_plan(tampered, manifest=self.manifest)
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_group_chat_plan(replace(plan, manager="untrusted"), manifest=self.manifest)
