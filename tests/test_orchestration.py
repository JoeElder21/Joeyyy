"""Tests for the orchestration wave: LangGraph lifecycle/cadence/HITL graphs,
AutoGen debates and cadence chats, the JEOS knowledge graph, and the MCP
mount registry. Heavy-dependency tests skip cleanly for stdlib CI."""

from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path
import tempfile
import tomllib
import unittest

from scripts.agent_runtime import CHIEF, AuditLedger, load_roster
from scripts.jeos_knowledge import GraphAccessDenied, JeosKnowledgeGraph
from scripts.orchestration_graphs import ACTIVE_GATES, load_manifest

ROOT = Path(__file__).resolve().parents[1]


def _available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


@unittest.skipUnless(_available("langgraph"), "langgraph not installed")
class LifecycleGraphTests(unittest.TestCase):
    def test_shadow_advances_only_when_every_gate_holds(self):
        from scripts.orchestration_graphs import build_lifecycle_graph

        graph = build_lifecycle_graph()
        satisfied = graph.invoke({
            "agent": "apex_war_architect", "stage": "shadow",
            "gates": {gate: True for gate in ACTIVE_GATES},
        })
        self.assertEqual(satisfied["stage"], "active")

        missing = graph.invoke({
            "agent": "apex_war_architect", "stage": "shadow",
            "gates": {gate: True for gate in ACTIVE_GATES[:-1]},
        })
        self.assertEqual(missing["stage"], "shadow")
        self.assertTrue(any("unsatisfied" in line for line in missing["decision_log"]))

        violated = graph.invoke({
            "agent": "apex_war_architect", "stage": "active",
            "violation": "wrote outside its lease",
        })
        self.assertEqual(violated["stage"], "restricted")


@unittest.skipUnless(_available("langgraph"), "langgraph not installed")
class CadenceAndMissionGraphTests(unittest.TestCase):
    def test_cadence_graph_follows_manifest_order_with_integrator_last(self):
        from scripts.orchestration_graphs import build_cadence_graph

        manifest = load_manifest("apex", ROOT)
        route = next(r for r in manifest["cadence_routes"] if r["cadence"] == "daily")
        graph = build_cadence_graph(
            "apex", "daily", lambda agent, state: {"note": f"{agent} ran"}
        )
        outcome = graph.invoke({"cadence": "daily"})
        ran = [step["agent"] for step in outcome["steps"]]
        self.assertEqual(ran, list(route["order"]) + [route["integrator"]])
        self.assertEqual(ran[-1], "apex_chief_of_staff")

    def test_mission_graph_interrupts_before_irreversible_and_resumes(self):
        from scripts.orchestration_graphs import build_mission_graph

        graph = build_mission_graph()
        config = {"configurable": {"thread_id": "mission-1"}}
        paused = graph.invoke(
            {"mission": "file the submittal", "irreversible_action": "submit to LFUCG"},
            config,
        )
        self.assertEqual(
            paused["actions"], ["planned", "reversible work done"]
        )  # stopped before the irreversible node
        graph.update_state(config, {"approved_by_joe": True})
        resumed = graph.invoke(None, config)
        self.assertIn("irreversible executed: submit to LFUCG", resumed["actions"])


@unittest.skipUnless(
    _available("autogen_agentchat") and _available("autogen_ext"),
    "autogen not installed",
)
class GroupDebateTests(unittest.TestCase):
    def _client(self, turns: list[str]):
        from autogen_ext.models.replay import ReplayChatCompletionClient

        return ReplayChatCompletionClient(turns)

    def test_registered_challenge_pair_actually_debates(self):
        import asyncio

        from scripts.group_debate import build_challenge_debate

        team = build_challenge_debate(
            "APEX",
            ("apex_war_architect", "apex_intelligence_forge"),
            self._client([
                "Campaign two is the highest-leverage move this quarter.",
                "The source record does not support that: two of three cited "
                "opportunities are stale. TERMINATE",
            ]),
            max_turns=2,
        )
        result = asyncio.run(
            team.run(task="Debate: is campaign two the right focus?")
        )
        speakers = {message.source for message in result.messages}
        self.assertIn("apex_war_architect", speakers)
        self.assertIn("apex_intelligence_forge", speakers)

    def test_unregistered_and_cross_brain_pairs_are_refused(self):
        from scripts.group_debate import DebateRefused, build_challenge_debate

        with self.assertRaises(DebateRefused):
            build_challenge_debate(
                "APEX", ("apex_war_architect", "apex_delivery_commander")
                if not self._pair_registered("apex_war_architect", "apex_delivery_commander")
                else ("apex_deal_engine", "apex_systems_blacksmith"),
                self._client(["x"]),
            )
        with self.assertRaises(DebateRefused):
            build_challenge_debate(
                "APEX", ("apex_war_architect", "jeos_life_architect"),
                self._client(["x"]),
            )

    @staticmethod
    def _pair_registered(a: str, b: str) -> bool:
        manifest = load_manifest("apex", ROOT)
        return any(
            frozenset(item["agents"]) == frozenset((a, b))
            for item in manifest.get("challenge_pairs", [])
        )

    def test_cadence_chat_speaks_in_manifest_order(self):
        from scripts.group_debate import build_cadence_chat

        manifest = load_manifest("apex", ROOT)
        route = next(r for r in manifest["cadence_routes"] if r["cadence"] == "daily")
        team = build_cadence_chat(
            "APEX", "daily", self._client(["a", "b", "c", "d"])
        )
        names = [participant.name for participant in team._participants]
        self.assertEqual(names, list(route["order"]) + [route["integrator"]])


class GroupChatPlanTests(unittest.TestCase):
    """Planner is stdlib (no SDK needed) — ported from Codex PR #11."""

    def test_plan_uses_canonical_roster_order_and_subsets(self):
        from scripts.group_debate import plan_brain_chat

        plan = plan_brain_chat(
            "APEX", ["apex_intelligence_forge", "apex_deal_engine"]
        )
        self.assertEqual(
            plan.speaker_order, ("apex_deal_engine", "apex_intelligence_forge")
        )
        self.assertEqual(plan.manager, CHIEF)

    def test_plan_rejects_mixed_brain_unknown_and_empty(self):
        from scripts.group_debate import DebateRefused, plan_brain_chat

        with self.assertRaises(DebateRefused):
            plan_brain_chat("APEX", ["apex_war_architect", "jeos_life_architect"])
        with self.assertRaises(DebateRefused):
            plan_brain_chat("JEOS", ["not_registered"])
        with self.assertRaises(DebateRefused):
            plan_brain_chat("JEOS", [])


class JeosKnowledgeGraphTests(unittest.TestCase):
    def _graph(self, tmp: str) -> JeosKnowledgeGraph:
        return JeosKnowledgeGraph(
            Path(tmp) / "graph", load_roster(ROOT),
            AuditLedger(Path(tmp) / "audit.jsonl"),
        )

    def test_writer_lock_read_lock_and_tag_query_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = self._graph(tmp)
            graph.write_page(
                "jeos_reflection_forge", "JEOS/Pattern-Hypotheses",
                "Energy dips after late scope calls",
                "Three of four low-energy mornings followed evening scope calls.",
                tags=["pattern-hypothesis"], links=["Energy Ledger"],
            )
            graph.write_page(
                "jeos_reflection_forge", "JEOS/Pattern-Hypotheses",
                "Old hypothesis", "Stale entry.",
                tags=["pattern-hypothesis"],
                date=dt.date.today() - dt.timedelta(days=90),
            )
            with self.assertRaises(GraphAccessDenied):
                graph.write_page(
                    "jeos_momentum_engine", "JEOS/Pattern-Hypotheses", "x", "y"
                )
            with self.assertRaises(GraphAccessDenied):
                graph.query_by_tag("apex_intelligence_forge", "pattern-hypothesis")

            recent = graph.query_by_tag(
                "jeos_reflection_forge", "pattern-hypothesis", since_days=30
            )
            self.assertEqual(len(recent), 1)
            everything = graph.query_by_tag(CHIEF, "pattern-hypothesis")
            self.assertEqual(len(everything), 2)
            self.assertEqual(
                len(graph.backlinks(CHIEF, "Energy Ledger")), 1
            )

    def test_journal_appends_dated_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = self._graph(tmp)
            path = graph.journal("jeos_life_architect", "Weekly plan drafted.")
            self.assertIn("Weekly plan drafted.", path.read_text(encoding="utf-8"))
            with self.assertRaises(GraphAccessDenied):
                graph.journal("apex_deal_engine", "not allowed")


class McpMountRegistryTests(unittest.TestCase):
    def test_mounts_are_complete_and_policy_shaped(self):
        with (ROOT / "config" / "mcp_mounts.toml").open("rb") as source:
            mounts = tomllib.load(source)["mounts"]
        names = {mount["name"] for mount in mounts}
        self.assertIn("governance", names)
        self.assertIn("filesystem", names)
        self.assertIn("civil3d", names)
        for mount in mounts:
            self.assertTrue(mount["command"], mount["name"])
            self.assertTrue(mount["agents"], mount["name"])
            self.assertTrue(mount["purpose"], mount["name"])
            if not mount.get("verify_offline"):
                self.assertTrue(mount.get("activation"), mount["name"])


if __name__ == "__main__":
    unittest.main()
