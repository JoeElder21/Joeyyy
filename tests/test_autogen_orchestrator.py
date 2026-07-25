from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
import importlib.util
import sys
import tomllib
import unittest

from runtime.autogen_orchestrator import (
    AutoGenMissionOrchestrator,
    MissionResult,
)
from tests import test_packet_contracts as packet_contracts


ROOT = Path(__file__).resolve().parents[1]


class FakeConversableAgent:
    constructed = []

    def __init__(self, **kwargs):
        self.name = kwargs["name"]
        self.system_message = kwargs["system_message"]
        self.kwargs = kwargs
        self.__class__.constructed.append(self)


class FakeGroupChat:
    constructed = []

    def __init__(self, **kwargs):
        self.agents = kwargs["agents"]
        self.messages = kwargs["messages"]
        self.max_round = kwargs["max_round"]
        self.speaker_selection_method = kwargs["speaker_selection_method"]
        self.allow_repeat_speaker = kwargs["allow_repeat_speaker"]
        self.__class__.constructed.append(self)


class FakeGroupChatManager:
    constructed = []

    def __init__(self, **kwargs):
        self.groupchat = kwargs["groupchat"]
        self.llm_config = kwargs["llm_config"]
        self.__class__.constructed.append(self)


class FakeIntegrator:
    def __init__(
        self,
        plan,
        *,
        complete=True,
        integration="integrated result",
        name=None,
    ):
        self.name = name or plan.integrator
        self.plan = plan
        self.complete = complete
        self.integration = integration
        self.calls = []
        self.integration_messages = None

    def initiate_chat(self, manager, **kwargs):
        self.calls.append("initiate_chat")
        manager.groupchat.messages.append(
            {"name": self.name, "content": kwargs["message"]}
        )
        participants = self.plan.speaker_order
        if not self.complete:
            participants = participants[:-1]
        manager.groupchat.messages.extend(
            {"name": name, "content": f"{name} handoff"}
            for name in participants
        )
        return "group result"

    def generate_reply(self, *, messages, sender):
        self.calls.append("generate_reply")
        self.integration_messages = messages
        self.integration_sender = sender
        return self.integration


class AutoGenMissionOrchestratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        packet_contracts.PacketContractTests.setUpClass()
        cls.orchestrator = AutoGenMissionOrchestrator(ROOT)

    def setUp(self):
        FakeConversableAgent.constructed.clear()
        FakeGroupChat.constructed.clear()
        FakeGroupChatManager.constructed.clear()
        self.fake_autogen = ModuleType("autogen")
        self.fake_autogen.ConversableAgent = FakeConversableAgent
        self.fake_autogen.GroupChat = FakeGroupChat
        self.fake_autogen.GroupChatManager = FakeGroupChatManager

    def readonly_delegation(self, agent, mode, artifact_type):
        packet, _ = packet_contracts.PacketContractTests().v21_readonly_pair()
        definition = self.orchestrator.corps["agents"][agent]
        packet.update(
            {
                "agent": agent,
                "owner_brain": "APEX",
                "memory_namespace": definition["memory_namespace"],
                "mode": mode,
                "required_artifact_types": [artifact_type],
                "allowed_read_namespaces": [definition["memory_namespace"]],
            }
        )
        return packet

    def daily_packets(self):
        return [
            self.readonly_delegation(
                "apex_intelligence_forge",
                "intake_normalization",
                "intelligence_brief",
            ),
            self.readonly_delegation(
                "apex_delivery_commander",
                "delivery_control",
                "delivery_board",
            ),
            self.readonly_delegation(
                "apex_deal_engine",
                "pipeline_triage",
                "opportunity_pipeline",
            ),
        ]

    def build_chat(self, plan=None, delegations=None):
        plan = plan or self.orchestrator.plan_cadence("APEX", "daily")
        delegations = self.daily_packets() if delegations is None else delegations
        with patch.dict(sys.modules, {"autogen": self.fake_autogen}):
            specialists, manager = self.orchestrator.build_group_chat(
                plan,
                delegations,
                llm_config=False,
                system_message_factory=lambda packet: f"base:{packet['agent']}",
            )
        return plan, specialists, manager

    def test_apex_daily_plan_uses_manifest_specialists_and_integrator(self):
        plan = self.orchestrator.plan_cadence("APEX", "daily")
        self.assertEqual(
            plan.participants,
            (
                "apex_intelligence_forge",
                "apex_delivery_commander",
                "apex_deal_engine",
            ),
        )
        self.assertEqual(plan.speaker_order, plan.participants)
        self.assertEqual(plan.integrator, "apex_chief_of_staff")
        self.assertIn(
            ("apex_delivery_commander", "apex_intelligence_forge"),
            plan.challenge_pairs,
        )

    def test_plan_rejects_unknown_brain_cadence_or_integrator_drift(self):
        with self.assertRaises(ValueError):
            self.orchestrator.plan_cadence("MIXED", "daily")
        with self.assertRaises(ValueError):
            self.orchestrator.plan_cadence("APEX", "hourly")

        manifest_path = ROOT / self.orchestrator.corps["apex_brain_manifest"]
        with manifest_path.open("rb") as source:
            manifest = tomllib.load(source)
        route = next(
            item for item in manifest["cadence_routes"] if item["cadence"] == "daily"
        )
        for invalid in ("rogue_integrator", None):
            changed = deepcopy(manifest)
            changed_route = next(
                item
                for item in changed["cadence_routes"]
                if item["cadence"] == "daily"
            )
            if invalid is None:
                changed_route.pop("integrator")
            else:
                changed_route["integrator"] = invalid
            with self.subTest(integrator=invalid):
                with patch(
                    "runtime.autogen_orchestrator.tomllib.load",
                    return_value=changed,
                ):
                    with self.assertRaisesRegex(ValueError, "integrator"):
                        self.orchestrator.plan_cadence("APEX", "daily")
        self.assertEqual(route["integrator"], "apex_chief_of_staff")

    def test_delegations_require_exact_unique_brain_matched_packets(self):
        plan = self.orchestrator.plan_cadence("APEX", "daily")
        packets = self.daily_packets()
        validated = self.orchestrator.validate_delegations(plan, packets)
        self.assertEqual(tuple(validated), plan.participants)

        with self.assertRaises(ValueError):
            self.orchestrator.validate_delegations(plan, packets[:-1])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.orchestrator.validate_delegations(
                plan,
                [*packets, deepcopy(packets[0])],
            )
        crossed = deepcopy(packets)
        crossed[0]["owner_brain"] = "JEOS"
        with self.assertRaises(ValueError):
            self.orchestrator.validate_delegations(plan, crossed)

    def test_build_materializes_generator_and_applies_challenge_policy(self):
        yielded = []

        def delegation_stream():
            for packet in self.daily_packets():
                yielded.append(packet["agent"])
                yield packet

        plan, specialists, manager = self.build_chat(
            delegations=delegation_stream()
        )
        self.assertEqual(tuple(specialists), plan.participants)
        self.assertEqual(tuple(yielded), plan.participants)
        self.assertEqual(
            [agent.name for agent in manager.groupchat.agents],
            list(plan.participants),
        )
        self.assertNotIn(plan.integrator, specialists)
        self.assertEqual(
            manager.groupchat.max_round,
            len(plan.participants) + 1,
        )
        for challenge in plan.challenges:
            manifest_order = ", ".join(challenge.agents)
            for agent in challenge.agents:
                with self.subTest(challenge=challenge.agents, agent=agent):
                    prompt = specialists[agent].system_message
                    self.assertIn("challenge", prompt.lower())
                    self.assertIn(manifest_order, prompt)
                    self.assertIn(challenge.purpose, prompt)

    def test_build_rejects_forged_plan_or_direct_tool_configuration(self):
        plan = self.orchestrator.plan_cadence("APEX", "daily")
        forged_plans = (
            replace(plan, integrator="rogue_integrator"),
            replace(plan, speaker_order=tuple(reversed(plan.speaker_order))),
            replace(plan, challenges=()),
        )
        for forged in forged_plans:
            with self.subTest(forged=forged):
                with self.assertRaisesRegex(ValueError, "current manifest"):
                    self.build_chat(plan=forged)

        with patch.dict(sys.modules, {"autogen": self.fake_autogen}):
            with self.assertRaisesRegex(ValueError, "functions or tools"):
                self.orchestrator.build_group_chat(
                    plan,
                    self.daily_packets(),
                    llm_config={
                        "config_list": [{"model": "verified-model"}],
                        "tools": [{"type": "function"}],
                    },
                    system_message_factory=lambda packet: packet["agent"],
                )

    def test_selector_ignores_non_specialists_and_terminates_deterministically(self):
        plan, specialists, manager = self.build_chat()
        groupchat = manager.groupchat
        selector = groupchat.speaker_selection_method
        last_speaker = type("Speaker", (), {"name": plan.integrator})()
        groupchat.messages.extend(
            [
                {"name": plan.integrator, "content": "mission"},
                {"role": "system", "content": "manager note"},
                {"name": "apex_groupchat_manager", "content": "routing note"},
            ]
        )

        selected = []
        for name in plan.speaker_order:
            agent = selector(last_speaker, groupchat)
            self.assertIs(agent, specialists[name])
            self.assertNotIsInstance(agent, str)
            selected.append(agent.name)
            groupchat.messages.append({"name": name, "content": "handoff"})
            last_speaker = agent
        self.assertEqual(tuple(selected), plan.speaker_order)
        self.assertIsNone(selector(last_speaker, groupchat))

    def test_selector_fails_closed_on_out_of_order_or_duplicate_specialist(self):
        plan, specialists, manager = self.build_chat()
        selector = manager.groupchat.speaker_selection_method
        last_speaker = type("Speaker", (), {"name": plan.integrator})()
        invalid_histories = (
            [{"name": plan.speaker_order[1], "content": "early"}],
            [
                {"name": plan.speaker_order[0], "content": "first"},
                {"name": plan.speaker_order[0], "content": "duplicate"},
            ],
        )
        for messages in invalid_histories:
            with self.subTest(messages=messages):
                manager.groupchat.messages[:] = messages
                with self.assertRaisesRegex(ValueError, "speaker order"):
                    selector(last_speaker, manager.groupchat)
        self.assertEqual(tuple(specialists), plan.speaker_order)

    def test_terminal_integrator_receives_complete_transcript(self):
        plan, _, manager = self.build_chat()
        agent_007 = FakeIntegrator(plan)
        result = self.orchestrator.initiate_chat(
            agent_007,
            manager,
            "Complete the governed mission",
            plan=plan,
        )

        self.assertIsInstance(result, MissionResult)
        self.assertEqual(result.group_chat_result, "group result")
        self.assertEqual(result.integration, "integrated result")
        self.assertEqual(agent_007.calls, ["initiate_chat", "generate_reply"])
        self.assertIs(agent_007.integration_sender, manager)
        self.assertEqual(
            tuple(
                message["name"]
                for message in result.transcript
                if message.get("name") in plan.participants
            ),
            plan.speaker_order,
        )
        self.assertEqual(
            [message["name"] for message in agent_007.integration_messages[:-1]],
            list(plan.speaker_order),
        )
        self.assertIn(
            "terminal integrator",
            agent_007.integration_messages[-1]["content"],
        )

    def test_terminal_integration_fails_closed(self):
        plan, _, manager = self.build_chat()
        wrong_agent = FakeIntegrator(plan, name="rogue_integrator")
        with self.assertRaisesRegex(ValueError, "integrator"):
            self.orchestrator.initiate_chat(
                wrong_agent,
                manager,
                "mission",
                plan=plan,
            )
        self.assertEqual(wrong_agent.calls, [])

        plan, _, manager = self.build_chat()
        incomplete = FakeIntegrator(plan, complete=False)
        with self.assertRaisesRegex(RuntimeError, "every specialist"):
            self.orchestrator.initiate_chat(
                incomplete,
                manager,
                "mission",
                plan=plan,
            )
        self.assertEqual(incomplete.calls, ["initiate_chat"])

        plan, _, manager = self.build_chat()
        no_integration = FakeIntegrator(plan, integration=None)
        with self.assertRaisesRegex(RuntimeError, "terminal integration"):
            self.orchestrator.initiate_chat(
                no_integration,
                manager,
                "mission",
                plan=plan,
            )
        self.assertEqual(
            no_integration.calls,
            ["initiate_chat", "generate_reply"],
        )

    @unittest.skipUnless(
        importlib.util.find_spec("autogen") is not None,
        "official AutoGen 0.2 runtime is not installed",
    )
    def test_official_autogen_runtime_completes_every_round(self):
        from autogen import ConversableAgent

        plan = self.orchestrator.plan_cadence("APEX", "daily")
        specialists, manager = self.orchestrator.build_group_chat(
            plan,
            (packet for packet in self.daily_packets()),
            llm_config=False,
            system_message_factory=lambda packet: f"base:{packet['agent']}",
        )
        for name, specialist in specialists.items():
            specialist._default_auto_reply = f"{name} synthetic handoff"
        agent_007 = ConversableAgent(
            name=plan.integrator,
            llm_config=False,
            human_input_mode="NEVER",
            code_execution_config=False,
            default_auto_reply="Agent 007 synthetic integration",
        )

        result = self.orchestrator.initiate_chat(
            agent_007,
            manager,
            "Synthetic no-model scheduling smoke test",
            plan=plan,
        )
        spoken = tuple(
            message.get("name")
            for message in result.transcript
            if message.get("name") in plan.participants
        )
        self.assertEqual(manager.groupchat.max_round, len(plan.participants) + 1)
        self.assertEqual(spoken, plan.speaker_order)
        self.assertEqual(result.integration, "Agent 007 synthetic integration")


if __name__ == "__main__":
    unittest.main()
