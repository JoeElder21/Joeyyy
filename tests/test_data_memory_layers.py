"""Tests for the data and memory layers: governed memory gateway (stdlib),
evidence indexes (llama_index), and the crew bridge (crewAI). Heavy-dependency
tests skip cleanly so stdlib CI stays green."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import unittest

from scripts.agent_runtime import CHIEF, AuditLedger, load_roster
from scripts.memory_layer import (
    GovernedMemory,
    KeywordMemoryBackend,
    MemoryAccessDenied,
)
from scripts.packet_guard import PacketGuard
from tests.test_agent_runtime import _v21_pair
from tests.test_packet_contracts import PacketContractTests

ROOT = Path(__file__).resolve().parents[1]


def _available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _lease() -> dict:
    PacketContractTests.setUpClass()
    return deepcopy(PacketContractTests.lease)


class GovernedMemoryTests(unittest.TestCase):
    def _memory(self, tmp: str) -> GovernedMemory:
        return GovernedMemory(
            KeywordMemoryBackend(Path(tmp) / "memory.json"),
            load_roster(ROOT),
            PacketGuard(ROOT),
            AuditLedger(Path(tmp) / "audit.jsonl"),
        )

    def test_leased_namespace_write_and_brain_locked_read(self):
        lease = _lease()
        namespace = "APEX::Strategy-Campaigns::apex_chief_of_staff"
        with tempfile.TemporaryDirectory() as tmp:
            memory = self._memory(tmp)
            memory.add(
                "Campaign one targets permit throughput this quarter.",
                writer=CHIEF, agent_id=namespace, lease=lease,
            )
            hits = memory.search(
                "permit campaign", reader="apex_war_architect", agent_id=namespace
            )
            self.assertEqual(len(hits), 1)
            with self.assertRaises(MemoryAccessDenied):
                memory.search(
                    "permit campaign", reader="jeos_life_architect", agent_id=namespace
                )
            chief_hits = memory.search(
                "permit campaign", reader=CHIEF, agent_id=namespace
            )
            self.assertEqual(len(chief_hits), 1)

    def test_writes_require_owner_and_lease(self):
        lease = _lease()
        namespace = "APEX::Strategy-Campaigns::apex_chief_of_staff"
        with tempfile.TemporaryDirectory() as tmp:
            memory = self._memory(tmp)
            with self.assertRaises(MemoryAccessDenied):
                memory.add("x", writer="apex_war_architect",
                           agent_id=namespace, lease=lease)
            with self.assertRaises(MemoryAccessDenied):
                memory.add("x", writer=CHIEF, agent_id=namespace, lease=None)
            wrong_lease = deepcopy(lease)
            wrong_lease["writer_agent"] = "apex_war_architect"
            with self.assertRaises(MemoryAccessDenied):
                memory.add("x", writer=CHIEF, agent_id=namespace, lease=wrong_lease)

    def test_user_scope_writes_are_chief_only_and_duplicates_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = self._memory(tmp)
            memory.add("Joe prefers evidence-first briefs.", writer=CHIEF, user_id="joe")
            with self.assertRaises(MemoryAccessDenied):
                memory.add("Joe naps at noon.", writer="jeos_life_architect", user_id="joe")
            with self.assertRaises(MemoryAccessDenied):
                memory.add("Joe prefers evidence-first briefs.", writer=CHIEF, user_id="joe")
            hits = memory.search("evidence briefs", reader="jeos_life_architect", user_id="joe")
            self.assertEqual(len(hits), 1)


@unittest.skipUnless(_available("llama_index.core"), "llama-index-core not installed")
class EvidenceIndexTests(unittest.TestCase):
    def test_writer_lock_brain_lock_and_retrieval(self):
        from scripts.evidence_index import IndexAccessDenied, build_indexes

        roster = load_roster(ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            indexes = build_indexes(roster, AuditLedger(Path(tmp) / "audit.jsonl"))
            source = indexes["APEX/Source-Index"]
            source.add_document(
                "apex_intelligence_forge",
                "LFUCG comment letter three requires storm response revisions.",
                {"kind": "agency_letter"},
            )
            with self.assertRaises(IndexAccessDenied):
                source.add_document("apex_deal_engine", "not allowed")
            hits = source.retrieve("apex_delivery_commander", "storm revisions")
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0]["metadata"]["kind"], "agency_letter")
            with self.assertRaises(IndexAccessDenied):
                source.retrieve("jeos_reflection_forge", "storm revisions")
            self.assertEqual(len(source.retrieve(CHIEF, "storm revisions")), 1)


@unittest.skipUnless(_available("crewai"), "crewai not installed")
class CrewBridgeTests(unittest.TestCase):
    def test_roster_maps_to_crew_and_admission_is_fail_closed(self):
        from scripts.crew_bridge import build_brain_crew, crew_agent
        from scripts.agent_runtime import HandoffRejected

        roster = load_roster(ROOT)
        agent = crew_agent("apex_war_architect", roster["apex_war_architect"])
        self.assertEqual(agent.role, "apex_war_architect")
        self.assertTrue(agent.allow_delegation)

        delegation, _ = _v21_pair()
        crew = build_brain_crew("APEX", [deepcopy(delegation)])
        self.assertEqual(len(crew.agents), 5)
        self.assertEqual(len(crew.tasks), 1)
        self.assertIn("campaign_map", crew.tasks[0].expected_output)

        legacy = deepcopy(delegation)
        legacy["schema_version"] = "2.0"
        with self.assertRaises(HandoffRejected):
            build_brain_crew("APEX", [legacy])
        with self.assertRaises(HandoffRejected):
            build_brain_crew("JEOS", [deepcopy(delegation)])


if __name__ == "__main__":
    unittest.main()
