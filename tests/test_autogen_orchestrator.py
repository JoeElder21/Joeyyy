from copy import deepcopy
from pathlib import Path
import unittest

from runtime.autogen_orchestrator import AutoGenMissionOrchestrator
from tests.test_packet_contracts import PacketContractTests


ROOT = Path(__file__).resolve().parents[1]


class AutoGenMissionOrchestratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        PacketContractTests.setUpClass()
        cls.orchestrator = AutoGenMissionOrchestrator(ROOT)

    def readonly_delegation(self, agent, mode, artifact_type):
        packet, _ = PacketContractTests().v21_readonly_pair()
        definition = self.orchestrator.corps["agents"][agent]
        packet.update({
            "agent": agent,
            "owner_brain": "APEX",
            "memory_namespace": definition["memory_namespace"],
            "mode": mode,
            "required_artifact_types": [artifact_type],
            "allowed_read_namespaces": [definition["memory_namespace"]],
        })
        return packet

    def test_apex_daily_plan_is_manifest_ordered_and_same_brain(self):
        plan = self.orchestrator.plan_cadence("APEX", "daily")
        self.assertEqual(plan.participants, (
            "apex_intelligence_forge", "apex_delivery_commander", "apex_deal_engine",
        ))
        self.assertEqual(plan.speaker_order[-1], "apex_chief_of_staff")
        self.assertIn(
            ("apex_delivery_commander", "apex_intelligence_forge"),
            plan.challenge_pairs,
        )

    def test_plan_rejects_unknown_brain_or_cadence(self):
        with self.assertRaises(ValueError):
            self.orchestrator.plan_cadence("MIXED", "daily")
        with self.assertRaises(ValueError):
            self.orchestrator.plan_cadence("APEX", "hourly")

    def test_delegations_require_exact_participants_and_brain_matched_packets(self):
        plan = self.orchestrator.plan_cadence("APEX", "daily")
        packets = [
            self.readonly_delegation("apex_intelligence_forge", "intake_normalization", "intelligence_brief"),
            self.readonly_delegation("apex_delivery_commander", "delivery_control", "delivery_board"),
            self.readonly_delegation("apex_deal_engine", "pipeline_triage", "opportunity_pipeline"),
        ]
        self.orchestrator.validate_delegations(plan, packets)

        missing = packets[:-1]
        with self.assertRaises(ValueError):
            self.orchestrator.validate_delegations(plan, missing)
        crossed = deepcopy(packets)
        crossed[0]["owner_brain"] = "JEOS"
        with self.assertRaises(ValueError):
            self.orchestrator.validate_delegations(plan, crossed)


if __name__ == "__main__":
    unittest.main()
