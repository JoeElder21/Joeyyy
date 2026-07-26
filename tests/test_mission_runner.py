"""Behavioral tests for the controlled-mission harness.

The load-bearing tests here are the ones where a mission is *refused* or fails to
qualify. A harness that always produces a passing evidence record would let any
mode leave shadow, which is exactly the failure the lifecycle gate exists to stop.
"""

from pathlib import Path
import tempfile
import unittest

from runtime.mission_runner import (
    EvidenceRecord,
    MissionRejected,
    MissionRunner,
    MissionSpec,
)

AGENT = "jeos_energy_director"
MODE = "daily_capacity"
SOURCE = "fixture/jeos/calendar-2026-07-27"


def spec(**overrides) -> MissionSpec:
    base = dict(
        agent=AGENT,
        mode=MODE,
        objective="Produce one capacity map from the supplied calendar evidence.",
        definition_of_done=["Return one source-linked capacity map."],
        definition_of_done_ids=["capacity-map"],
        evidence=[EvidenceRecord(source_ref=SOURCE, source_type="synthetic")],
        baseline_minutes=20,
        baseline_source="joe_declared",
    )
    base.update(overrides)
    return MissionSpec(**base)


def handoff_for(prepared, **overrides) -> dict:
    delegation = prepared.delegation
    meta = prepared.meta
    record_id = "fixture:record-1"
    packet = {
        "schema_version": "2.1",
        "delegation_id": delegation["delegation_id"],
        "mission_id": delegation["mission_id"],
        "resource_id": delegation["resource_id"],
        "agent": delegation["agent"],
        "owner_brain": delegation["owner_brain"],
        "memory_namespace": delegation["memory_namespace"],
        "invocation_mode": "delegated",
        "external_actions_performed": False,
        "status": "completed",
        "findings": ["One capacity map produced from packet evidence."],
        "mode": delegation["mode"],
        "artifacts": [
            {
                "artifact_type": meta["artifact_types"][0],
                "records": [
                    {
                        "record_id": record_id,
                        "record_type": "capacity_record",
                        "source_refs": [SOURCE],
                        "as_of": None,
                        "source_locator": SOURCE,
                        "revision": "fixture-v1",
                        "content_hash": None,
                        "fields": {"windows": 2},
                        "confidence": "confirmed",
                    }
                ],
            }
        ],
        "evidence": delegation["allowed_evidence"],
        "tests": ["PacketGuard accepted the typed return."],
        "assumptions": [],
        "blockers": [],
        "challenges": [],
        "proposed_writes": [],
        "validation": ["Artifact is source-linked; no mutation proposed."],
        "criterion_validation": [
            {
                "criterion_id": "capacity-map",
                "status": "passed",
                "evidence_record_ids": [record_id],
                "note": "Structurally and relationally validated.",
            }
        ],
        "confidence": "confirmed",
        "sensitivity": "internal",
        "recommended_next_handoff": "apex_chief_of_staff",
    }
    packet.update(overrides)
    return packet


COSTS = dict(
    agent_minutes=1.0,
    review_minutes=2.0,
    correction_minutes=0.0,
    maintenance_share_minutes=0.5,
)


class RunnerHarness(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.runner = MissionRunner(ledger_path=Path(self._tmp.name) / "missions.jsonl")


class PrepareTests(RunnerHarness):
    def test_valid_mission_produces_a_packetguard_clean_delegation(self):
        prepared = self.runner.prepare(spec())
        self.assertTrue(prepared.delegation_id.startswith(f"delegation:{AGENT}:"))
        self.assertEqual(prepared.delegation["mode"], MODE)
        self.assertEqual(prepared.delegation["owner_brain"], "JEOS")
        # Shadow specialists never receive a write target.
        self.assertEqual(prepared.delegation["allowed_write_targets"], [])

    def test_unknown_agent_is_refused(self):
        with self.assertRaises(MissionRejected):
            self.runner.prepare(spec(agent="not_an_agent"))

    def test_unregistered_mode_is_refused(self):
        with self.assertRaises(MissionRejected) as caught:
            self.runner.prepare(spec(mode="invented_mode"))
        self.assertIn("not registered", str(caught.exception))

    def test_mission_without_evidence_is_refused(self):
        with self.assertRaises(MissionRejected) as caught:
            self.runner.prepare(spec(evidence=[]))
        self.assertIn("evidence", str(caught.exception))

    def test_agent_supplied_baseline_is_refused(self):
        with self.assertRaises(MissionRejected) as caught:
            self.runner.prepare(spec(baseline_source="agent_estimated"))
        self.assertIn("baseline_source", str(caught.exception))

    def test_unmatched_definition_of_done_ids_are_refused(self):
        with self.assertRaises(MissionRejected):
            self.runner.prepare(spec(definition_of_done_ids=["a", "b"]))


class CompleteTests(RunnerHarness):
    def test_clean_run_qualifies_the_mode_and_emits_a_value_observation(self):
        prepared = self.runner.prepare(spec())
        evidence = self.runner.complete(prepared, handoff_for(prepared), **COSTS)
        self.assertEqual(evidence.errors, [])
        self.assertTrue(evidence.typed_return_valid)
        self.assertTrue(evidence.connector_isolation_verified)
        self.assertTrue(evidence.qualifies_mode)
        observation = evidence.value_observation
        self.assertEqual(observation["baseline_minutes"], 20)
        self.assertEqual(observation["baseline_source"], "joe_declared")
        self.assertFalse(observation["boundary_incident"])

    def test_claimed_external_action_breaks_connector_isolation(self):
        prepared = self.runner.prepare(spec())
        evidence = self.runner.complete(
            prepared,
            handoff_for(prepared, external_actions_performed=True),
            **COSTS,
        )
        self.assertFalse(evidence.connector_isolation_verified)
        self.assertFalse(evidence.qualifies_mode)
        self.assertTrue(evidence.value_observation["boundary_incident"])

    def test_citing_a_source_outside_the_packet_breaks_isolation(self):
        """The specialist reached past its evidence — the exact thing packet-only forbids."""
        prepared = self.runner.prepare(spec())
        rogue = handoff_for(prepared)
        rogue["artifacts"][0]["records"][0]["source_refs"] = ["gmail://thread/not-in-packet"]
        evidence = self.runner.complete(prepared, rogue, **COSTS)
        self.assertFalse(evidence.connector_isolation_verified)
        self.assertFalse(evidence.qualifies_mode)
        self.assertTrue(
            any("reached past its evidence" in error for error in evidence.errors)
        )

    def test_missing_criterion_validation_fails_the_mission(self):
        prepared = self.runner.prepare(spec())
        evidence = self.runner.complete(
            prepared, handoff_for(prepared, criterion_validation=[]), **COSTS
        )
        self.assertFalse(evidence.qualifies_mode)
        self.assertTrue(any("definition of done" in error for error in evidence.errors))

    def test_boundary_blocked_return_does_not_qualify_the_mode(self):
        prepared = self.runner.prepare(spec())
        evidence = self.runner.complete(
            prepared,
            handoff_for(
                prepared,
                status="boundary_blocked",
                blockers=["BOUNDARY_SCOPE_REJECTED"],
                artifacts=[],
                criterion_validation=[],
            ),
            **COSTS,
        )
        self.assertFalse(evidence.qualifies_mode)

    def test_every_completion_is_recorded_on_an_intact_hash_chain(self):
        prepared = self.runner.prepare(spec())
        self.runner.complete(prepared, handoff_for(prepared), **COSTS)
        self.assertIsNotNone(prepared and self.runner.ledger.path)
        self.assertEqual(self.runner.ledger.verify(), [])
        lines = self.runner.ledger.path.read_text(encoding="utf-8").strip().splitlines()
        # One prepare entry and one completion entry.
        self.assertEqual(len(lines), 2)

    def test_rewriting_a_chained_entry_is_detected(self):
        prepared = self.runner.prepare(spec())
        self.runner.complete(prepared, handoff_for(prepared), **COSTS)
        path = self.runner.ledger.path
        # Rewrite the prepare entry, which a later entry chains to.
        text = path.read_text(encoding="utf-8").replace(
            "mission_prepared", "mission_tampered", 1
        )
        path.write_text(text, encoding="utf-8")
        self.assertNotEqual(self.runner.ledger.verify(), [])

    def test_tail_tampering_is_not_detected_and_survives_later_appends(self):
        """Documents a real limit of ``AuditLedger``, so nobody overclaims it.

        ``verify()`` proves that entries which *already had a successor* were not
        rewritten. It does not protect the newest entry, and — because
        ``_last_hash()`` re-reads the file at append time — a later append
        re-anchors the chain onto the tampered content instead of exposing it.

        Practical consequence: the ledger detects rewriting of history, not
        tampering of the most recent record by whoever holds the file between
        two appends. Treat it as tamper-evident for the past, not the present.
        """
        prepared = self.runner.prepare(spec())
        self.runner.complete(prepared, handoff_for(prepared), **COSTS)
        path = self.runner.ledger.path

        tampered = path.read_text(encoding="utf-8").replace(
            "mission_completed", "mission_edited__", 1
        )
        path.write_text(tampered, encoding="utf-8")
        self.assertEqual(self.runner.ledger.verify(), [], "tail tampering is undetected")

        second = self.runner.prepare(spec())
        self.runner.complete(second, handoff_for(second), **COSTS)
        self.assertEqual(
            self.runner.ledger.verify(),
            [],
            "later appends re-anchor onto the tampered entry rather than exposing it",
        )
        # The tampered content is still sitting in the ledger, unflagged.
        self.assertIn("mission_edited__", path.read_text(encoding="utf-8"))


class PromotionStatusTests(RunnerHarness):
    def test_uncovered_modes_are_reported_not_omitted(self):
        prepared = self.runner.prepare(spec())
        evidence = self.runner.complete(prepared, handoff_for(prepared), **COSTS)
        report = self.runner.promotion_status([evidence])

        entry = report["agents"][AGENT]
        self.assertIn(MODE, entry["covered_modes"])
        # The energy director has three modes; one mission covers exactly one.
        self.assertTrue(entry["uncovered_modes"])
        self.assertFalse(entry["all_modes_covered"])
        self.assertNotIn(AGENT, report["agents_fully_covered"])

    def test_one_passing_mode_never_qualifies_its_siblings(self):
        prepared = self.runner.prepare(spec())
        evidence = self.runner.complete(prepared, handoff_for(prepared), **COSTS)
        report = self.runner.promotion_status([evidence])
        self.assertEqual(report["covered_modes"], 1)
        self.assertEqual(report["total_modes"], 39)
        self.assertEqual(report["agents_fully_covered"], [])

    def test_a_failed_mission_covers_nothing(self):
        prepared = self.runner.prepare(spec())
        evidence = self.runner.complete(
            prepared, handoff_for(prepared, external_actions_performed=True), **COSTS
        )
        report = self.runner.promotion_status([evidence])
        self.assertEqual(report["covered_modes"], 0)

    def test_report_covers_every_registered_agent(self):
        report = self.runner.promotion_status([])
        self.assertEqual(len(report["agents"]), 10)
        self.assertEqual(report["covered_modes"], 0)
        self.assertEqual(report["total_modes"], 39)


if __name__ == "__main__":
    unittest.main()


class MissionCatalogTests(RunnerHarness):
    """The prepared Monday missions must be runnable, not aspirational."""

    def setUp(self):
        super().setUp()
        from runtime.mission_runner import load_mission_catalog

        self.catalog = load_mission_catalog()

    def test_catalog_is_not_empty(self):
        self.assertGreaterEqual(len(self.catalog), 7)

    def test_every_entry_names_a_registered_agent_and_mode(self):
        for key, entry in self.catalog.items():
            with self.subTest(mission=key):
                meta = self.runner.roster.get(entry.agent)
                self.assertIsNotNone(meta, f"{entry.agent} is not registered")
                self.assertIn(entry.mode, meta["modes"])

    def test_every_entry_produces_a_packetguard_clean_delegation(self):
        """A catalog entry that cannot actually be prepared is worthless on Monday."""
        for key, entry in self.catalog.items():
            with self.subTest(mission=key):
                prepared = self.runner.prepare(
                    entry.to_spec(
                        evidence=[
                            EvidenceRecord(
                                source_ref=f"fixture/{key}/source-1",
                                source_type="synthetic",
                            )
                        ],
                        baseline_minutes=30,
                    )
                )
                self.assertEqual(prepared.delegation["mode"], entry.mode)
                self.assertEqual(prepared.delegation["agent"], entry.agent)

    def test_definition_of_done_ids_line_up_with_criteria(self):
        for key, entry in self.catalog.items():
            with self.subTest(mission=key):
                self.assertEqual(
                    len(entry.definition_of_done), len(entry.definition_of_done_ids)
                )
                self.assertTrue(entry.baseline_prompt.strip())

    def test_catalog_covers_both_brains(self):
        brains = {self.runner.roster[e.agent]["brain"] for e in self.catalog.values()}
        self.assertEqual(brains, {"APEX", "JEOS"})
