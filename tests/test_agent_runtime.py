"""Runtime-bridge tests.

Stdlib-reachable behavior (roster, audit ledger, packet admission) is always
tested. Tests that need the openai-agents SDK skip cleanly when the package
is absent so the stdlib CI environment stays green.
"""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from scripts.agent_runtime import (
    CHIEF,
    AuditLedger,
    HandoffRejected,
    admit_delegation,
    load_roster,
    validate_specialist_return,
)
from scripts.packet_guard import PacketGuard
from tests.test_packet_contracts import PacketContractTests

ROOT = Path(__file__).resolve().parents[1]


def _sdk_available() -> bool:
    try:
        return importlib.util.find_spec("agents") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _v21_pair():
    """Reuse the canonical known-valid v2.1 delegation/handoff fixtures."""
    PacketContractTests.setUpClass()
    carrier = PacketContractTests("test_valid_delegation_and_handoff_are_bound_to_lease_and_origin")
    return carrier.v21_readonly_pair()


class AuditLedgerTests(unittest.TestCase):
    def test_chain_appends_verifies_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AuditLedger(Path(tmp) / "audit.jsonl")
            ledger.append("one", {"n": 1})
            ledger.append("two", {"n": 2})
            ledger.append("three", {"n": 3})
            self.assertEqual(ledger.verify(), [])

            lines = ledger.path.read_text(encoding="utf-8").splitlines()
            tampered = json.loads(lines[1])
            tampered["detail"]["n"] = 99
            lines[1] = json.dumps(tampered, sort_keys=True, separators=(",", ":"))
            ledger.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.assertTrue(any("chain broken" in item for item in ledger.verify()))


class RosterTests(unittest.TestCase):
    def test_roster_loads_all_native_agents_with_brains(self):
        roster = load_roster(ROOT)
        self.assertEqual(len(roster), 11)
        self.assertEqual(roster[CHIEF]["brain"], "cross-brain")
        apex = [n for n, meta in roster.items() if meta["brain"] == "APEX"]
        jeos = [n for n, meta in roster.items() if meta["brain"] == "JEOS"]
        self.assertEqual(len(apex), 5)
        self.assertEqual(len(jeos), 5)


class AdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = PacketGuard(ROOT)
        cls.roster = load_roster(ROOT)
        cls.delegation, cls.handoff_return = _v21_pair()

    def test_valid_packet_is_admitted_and_audited(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AuditLedger(Path(tmp) / "audit.jsonl")
            admit_delegation(
                deepcopy(self.delegation), "apex_war_architect",
                self.roster, self.guard, ledger,
            )
            self.assertEqual(ledger.verify(), [])
            entries = [
                json.loads(line)
                for line in ledger.path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(entries[-1]["event"], "handoff_admitted")

    def test_legacy_packet_is_rejected_fail_closed(self):
        legacy = deepcopy(self.delegation)
        legacy["schema_version"] = "2.0"
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AuditLedger(Path(tmp) / "audit.jsonl")
            with self.assertRaises(HandoffRejected) as caught:
                admit_delegation(
                    legacy, "apex_war_architect", self.roster, self.guard, ledger
                )
            self.assertTrue(any("legacy" in item for item in caught.exception.errors))
            entries = [
                json.loads(line)
                for line in ledger.path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(entries[-1]["event"], "handoff_rejected")

    def test_misaddressed_packet_cannot_transfer(self):
        with self.assertRaises(HandoffRejected) as caught:
            admit_delegation(
                deepcopy(self.delegation), "jeos_life_architect",
                self.roster, self.guard,
            )
        self.assertTrue(
            any("not 'jeos_life_architect'" in item for item in caught.exception.errors)
        )

    def test_specialist_return_validation_flags_unevidenced_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AuditLedger(Path(tmp) / "audit.jsonl")
            clean = validate_specialist_return(
                deepcopy(self.handoff_return), self.guard, ledger,
                delegations=[self.delegation],
            )
            self.assertEqual(clean, [])
            broken = deepcopy(self.handoff_return)
            broken["artifacts"][0]["records"][0]["source_refs"] = []
            errors = validate_specialist_return(
                broken, self.guard, ledger, delegations=[self.delegation]
            )
            self.assertTrue(any("source evidence" in item for item in errors))
            events = [
                json.loads(line)["event"]
                for line in ledger.path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(events, ["return_validated", "return_rejected"])


@unittest.skipUnless(_sdk_available(), "openai-agents SDK not installed")
class GovernedGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from scripts.agent_runtime import build_governed_graph

        cls.guard = PacketGuard(ROOT)
        cls.chief, cls.specialists = build_governed_graph(cls.guard)

    def test_topology_chief_to_all_specialists_and_back_only(self):
        self.assertEqual(len(self.chief.handoffs), 10)
        self.assertEqual(len(self.specialists), 10)
        for specialist in self.specialists.values():
            self.assertEqual([item.name for item in specialist.handoffs], [CHIEF])

    def test_handoffs_carry_typed_input_schema(self):
        for governed in self.chief.handoffs:
            schema = governed.input_json_schema
            self.assertIn("packet_json", json.dumps(schema))

    def test_on_handoff_rejects_legacy_packet_before_transfer(self):
        import asyncio

        from agents.run_context import RunContextWrapper

        delegation, _ = _v21_pair()
        legacy = deepcopy(delegation)
        legacy["schema_version"] = "2.0"
        governed = next(
            item for item in self.chief.handoffs if item.agent_name == "apex_war_architect"
        )
        payload = json.dumps({"packet_json": json.dumps(legacy)})
        with self.assertRaises(HandoffRejected):
            asyncio.run(
                governed.on_invoke_handoff(RunContextWrapper(context=None), payload)
            )

    def test_on_handoff_admits_valid_packet(self):
        import asyncio

        from agents.run_context import RunContextWrapper

        delegation, _ = _v21_pair()
        governed = next(
            item for item in self.chief.handoffs if item.agent_name == "apex_war_architect"
        )
        payload = json.dumps({"packet_json": json.dumps(delegation)})
        result = asyncio.run(
            governed.on_invoke_handoff(RunContextWrapper(context=None), payload)
        )
        self.assertEqual(result.name, "apex_war_architect")


if __name__ == "__main__":
    unittest.main()
