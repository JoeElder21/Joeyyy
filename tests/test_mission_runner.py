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
        evidence=[
            EvidenceRecord(
                source_ref=SOURCE,
                source_type="connector_record",
                content="09:00-10:30 site walk; 13:00-14:00 review call",
                owner_brain="JEOS",
            )
        ],
        baseline_minutes=20,
        baseline_source="joe_declared",
        required_artifact_types=["capacity_map"],
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


# A qualifying mission must have had its result read back, so the default costs
# used by the happy-path tests include it.
COSTS = dict(
    agent_minutes=1.0,
    review_minutes=2.0,
    correction_minutes=0.0,
    maintenance_share_minutes=0.5,
    readback_performed=True,
    accepted_first_pass=True,
)


class RunnerHarness(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.runner = MissionRunner(
            ledger_path=Path(self._tmp.name) / "missions.jsonl",
            value_ledger_path=Path(self._tmp.name) / "value.jsonl",
        )


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
        # One prepare entry and one completion entry; value recording succeeds
        # and therefore emits no compensating entry.
        self.assertEqual(len(lines), 2)
        self.assertNotIn("value_record_failed", "".join(lines))

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


class ValueEvidenceCouplingTests(RunnerHarness):
    """Lifecycle evidence and value evidence must be written by the same call.

    The first version of the harness built a value observation and dropped it,
    so the runbook told Joe to read a file nothing ever wrote.
    """

    def test_completing_a_mission_persists_the_value_observation(self):
        from runtime.value_meter import ValuePolicy

        prepared = self.runner.prepare(spec())
        evidence = self.runner.complete(prepared, handoff_for(prepared), **COSTS)

        self.assertTrue(evidence.value_recorded)
        self.assertTrue(self.runner.value_ledger.path.exists())
        recorded = self.runner.value_ledger.observations(ValuePolicy.load())
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0].mode, MODE)
        self.assertEqual(recorded[0].baseline_minutes, 20)

    def test_the_reported_value_ledger_path_is_the_one_the_runbook_names(self):
        from runtime.mission_runner import DEFAULT_VALUE_LEDGER

        self.assertEqual(DEFAULT_VALUE_LEDGER.name, "value.jsonl")
        self.assertEqual(DEFAULT_VALUE_LEDGER.parent.name, "audit")

    def test_a_mission_whose_value_cannot_be_recorded_does_not_qualify(self):
        """Fail closed: no value record, no promotion credit."""
        prepared = self.runner.prepare(spec())
        evidence = self.runner.complete(
            prepared,
            handoff_for(prepared),
            agent_minutes=1.0,
            review_minutes=2.0,
            correction_minutes=0.0,
            maintenance_share_minutes=0.5,
            incident_minutes=-1.0,  # invalid: rejected by the value meter
        )
        self.assertFalse(evidence.value_recorded)
        self.assertFalse(evidence.qualifies_mode)
        self.assertTrue(any("value observation rejected" in e for e in evidence.errors))

    def test_observations_accumulate_across_missions(self):
        from runtime.value_meter import ValuePolicy

        for _ in range(3):
            prepared = self.runner.prepare(spec())
            self.runner.complete(prepared, handoff_for(prepared), **COSTS)
        recorded = self.runner.value_ledger.observations(ValuePolicy.load())
        self.assertEqual(len(recorded), 3)


class BrainSeparationLoaderTests(unittest.TestCase):
    def test_an_agent_in_both_manifests_is_a_hard_failure(self):
        """A duplicate agent id across brains is a separation breach, not a merge."""
        import runtime.mission_runner as module

        original = module.tomllib.loads
        apex_seen = {"done": False}

        def fake_loads(text):
            data = original(text)
            # Force the JEOS manifest to re-declare an APEX agent.
            if data.get("brain") == "JEOS":
                data["agents"]["apex_war_architect"] = dict(
                    next(iter(data["agents"].values()))
                )
            apex_seen["done"] = True
            return data

        module.tomllib.loads = fake_loads
        try:
            with self.assertRaises(module.MissionRejected) as caught:
                module.load_brain_roster()
            self.assertIn("both brain manifests", str(caught.exception))
        finally:
            module.tomllib.loads = original


class GateIntegrityTests(RunnerHarness):
    """Ways a mode could be marked covered without meeting the gate."""

    def test_a_mission_without_readback_does_not_qualify(self):
        """config/specialist_corps.toml names readback in the active gate."""
        prepared = self.runner.prepare(spec())
        costs = dict(COSTS)
        costs["readback_performed"] = False
        evidence = self.runner.complete(prepared, handoff_for(prepared), **costs)
        self.assertEqual(evidence.errors, [])
        self.assertFalse(evidence.readback_performed)
        self.assertFalse(evidence.qualifies_mode)
        self.assertEqual(self.runner.promotion_status([evidence])["covered_modes"], 0)

    def test_a_failed_mission_is_not_recorded_as_first_pass_accepted(self):
        """Otherwise five failing missions could still average to meets_threshold."""
        prepared = self.runner.prepare(spec())
        evidence = self.runner.complete(
            prepared, handoff_for(prepared, criterion_validation=[]), **COSTS
        )
        self.assertFalse(evidence.qualifies_mode)
        self.assertFalse(evidence.value_observation["accepted_first_pass"])
        self.assertTrue(evidence.value_observation["output_rejected"])

    def test_a_locator_cited_only_in_free_text_breaks_isolation(self):
        """Citations outside artifact records were previously unchecked."""
        prepared = self.runner.prepare(spec())
        sneaky = handoff_for(prepared)
        sneaky["findings"] = [
            "Cross-referenced gmail://thread/undelegated-1 for extra context."
        ]
        evidence = self.runner.complete(prepared, sneaky, **COSTS)
        self.assertFalse(evidence.connector_isolation_verified)
        self.assertFalse(evidence.qualifies_mode)
        self.assertTrue(any("free text" in e for e in evidence.errors))

    def test_non_first_modes_can_complete_a_mission(self):
        """technical_qa must not be forced to return a delivery_board."""
        prepared = self.runner.prepare(
            MissionSpec(
                agent="apex_delivery_commander",
                mode="technical_qa",
                objective="Review the supplied sheet set for grading risk.",
                definition_of_done=["Return one QA risk packet."],
                definition_of_done_ids=["qa-packet"],
                evidence=[
                    EvidenceRecord(
                        "fixture/apex/sheets-1",
                        "connector_record",
                        content="sheet set",
                        owner_brain="APEX",
                    )
                ],
                baseline_minutes=45,
                baseline_source="joe_declared",
                required_artifact_types=["qa_risk_packet"],
            )
        )
        self.assertEqual(
            prepared.delegation["required_artifact_types"], ["qa_risk_packet"]
        )

    def test_unregistered_artifact_type_is_refused(self):
        with self.assertRaises(MissionRejected):
            self.runner.prepare(spec(required_artifact_types=["not_a_type"]))

    def test_a_mission_that_names_no_artifact_type_is_refused(self):
        """The harness will not guess; a wrong guess fails every return."""
        with self.assertRaises(MissionRejected) as caught:
            self.runner.prepare(spec(required_artifact_types=[]))
        self.assertIn("artifact type", str(caught.exception))


class LedgerBackedPromotionTests(RunnerHarness):
    """The runbook's coverage command must see missions that actually ran."""

    def test_promotion_status_reads_the_ledger_when_given_nothing(self):
        prepared = self.runner.prepare(spec())
        self.runner.complete(prepared, handoff_for(prepared), **COSTS)

        report = self.runner.promotion_status()
        self.assertEqual(report["covered_modes"], 1)
        self.assertIn(MODE, report["agents"][AGENT]["covered_modes"])

    def test_an_empty_ledger_reports_no_coverage(self):
        self.assertEqual(self.runner.promotion_status()["covered_modes"], 0)

    def test_evidence_from_an_obsolete_contract_stops_covering_a_mode(self):
        prepared = self.runner.prepare(spec())
        evidence = self.runner.complete(prepared, handoff_for(prepared), **COSTS)
        self.assertTrue(evidence.qualifies_mode)

        evidence.contract_sha = "0000000000000000"
        report = self.runner.promotion_status([evidence])
        self.assertEqual(report["covered_modes"], 0)
        self.assertIn(f"{AGENT}:{MODE}", report["stale_contract_evidence"])


class RealMissionProvenanceTests(RunnerHarness):
    """A fixture must never satisfy a "controlled real mission" gate."""

    def test_synthetic_evidence_does_not_qualify_a_mode(self):
        prepared = self.runner.prepare(
            spec(evidence=[EvidenceRecord(SOURCE, "synthetic")])
        )
        evidence = self.runner.complete(prepared, handoff_for(prepared), **COSTS)
        self.assertEqual(evidence.errors, [])
        self.assertFalse(evidence.real_evidence)
        self.assertFalse(evidence.qualifies_mode)
        self.assertEqual(self.runner.promotion_status([evidence])["covered_modes"], 0)

    def test_real_connector_evidence_qualifies(self):
        prepared = self.runner.prepare(spec())
        evidence = self.runner.complete(prepared, handoff_for(prepared), **COSTS)
        self.assertTrue(evidence.real_evidence)
        self.assertTrue(evidence.qualifies_mode)

    def test_one_synthetic_record_taints_the_whole_mission(self):
        prepared = self.runner.prepare(
            spec(
                evidence=[
                    EvidenceRecord(
                        SOURCE, "connector_record", content="real", owner_brain="JEOS"
                    ),
                    EvidenceRecord("fixture/synthetic-1", "synthetic"),
                ]
            )
        )
        evidence = self.runner.complete(prepared, handoff_for(prepared), **COSTS)
        self.assertFalse(evidence.real_evidence)
        self.assertFalse(evidence.qualifies_mode)


class AcceptanceDefaultTests(RunnerHarness):
    def test_acceptance_defaults_to_false(self):
        """Never record acceptance Joe may not have given."""
        prepared = self.runner.prepare(spec())
        costs = {k: v for k, v in COSTS.items() if k != "accepted_first_pass"}
        evidence = self.runner.complete(prepared, handoff_for(prepared), **costs)
        self.assertFalse(evidence.value_observation["accepted_first_pass"])


class BaselineConsistencyTests(RunnerHarness):
    def test_a_mode_cannot_change_its_baseline_between_runs(self):
        """A moving baseline reaches 35% by inflation rather than by saving time."""
        prepared = self.runner.prepare(spec())
        self.runner.complete(prepared, handoff_for(prepared), **COSTS)

        with self.assertRaises(MissionRejected) as caught:
            self.runner.prepare(spec(baseline_minutes=200))
        self.assertIn("established baseline", str(caught.exception))

    def test_the_same_baseline_is_accepted_again(self):
        prepared = self.runner.prepare(spec())
        self.runner.complete(prepared, handoff_for(prepared), **COSTS)
        self.runner.prepare(spec())


class SuppliedEvidenceVerificationTests(RunnerHarness):
    def test_hand_constructed_evidence_does_not_grant_coverage(self):
        """A caller must not be able to fabricate promotion coverage."""
        from runtime.mission_runner import MissionEvidence

        forged = MissionEvidence(
            delegation_id="delegation:forged:0000",
            mission_id="mission:forged",
            agent=AGENT,
            mode=MODE,
            brain="JEOS",
            status="completed",
            typed_return_valid=True,
            connector_isolation_verified=True,
            readback_performed=True,
            errors=[],
            ledger_entry=None,
            value_observation=None,
            value_recorded=True,
            real_evidence=True,
            contract_sha=self.runner.contract_sha(AGENT),
        )
        self.assertTrue(forged.qualifies_mode)
        report = self.runner.promotion_status([forged])
        self.assertEqual(report["covered_modes"], 0)
        self.assertIn(f"{AGENT}:{MODE}", report["unrecorded_evidence"])


class LiveEvidenceRealismTests(RunnerHarness):
    """Real email and document evidence routinely contains links."""

    def test_a_url_inside_delegated_content_is_not_a_boundary_violation(self):
        """This blocked every realistic Gmail or Drive mission."""
        prepared = self.runner.prepare(
            spec(
                evidence=[
                    EvidenceRecord(
                        "gmail://thread/agency-1",
                        "connector_record",
                        content=(
                            "LFUCG review comments attached. Portal: "
                            "https://permits.example.gov/case/1234"
                        ),
                        owner_brain="JEOS",
                    )
                ]
            )
        )
        handoff = handoff_for(prepared)
        handoff["artifacts"][0]["records"][0]["source_refs"] = [
            "gmail://thread/agency-1"
        ]
        handoff["artifacts"][0]["records"][0]["source_locator"] = (
            "gmail://thread/agency-1"
        )
        handoff["evidence"] = prepared.delegation["allowed_evidence"]
        handoff["findings"] = [
            "Review portal link quoted from the delegated email: "
            "https://permits.example.gov/case/1234"
        ]
        evidence = self.runner.complete(prepared, handoff, **COSTS)
        self.assertTrue(evidence.connector_isolation_verified, evidence.errors)
        self.assertTrue(evidence.qualifies_mode, evidence.errors)

    def test_a_locator_not_present_in_the_content_still_fails(self):
        prepared = self.runner.prepare(
            spec(
                evidence=[
                    EvidenceRecord(
                        "gmail://thread/agency-1",
                        "connector_record",
                        content="No links in this excerpt.",
                        owner_brain="JEOS",
                    )
                ]
            )
        )
        handoff = handoff_for(prepared)
        handoff["artifacts"][0]["records"][0]["source_refs"] = [
            "gmail://thread/agency-1"
        ]
        handoff["artifacts"][0]["records"][0]["source_locator"] = (
            "gmail://thread/agency-1"
        )
        handoff["evidence"] = prepared.delegation["allowed_evidence"]
        handoff["findings"] = ["Also checked drive://file/undelegated-9"]
        evidence = self.runner.complete(prepared, handoff, **COSTS)
        self.assertFalse(evidence.connector_isolation_verified)


class FrozenIdentityTests(RunnerHarness):
    def test_mutating_the_spec_after_prepare_cannot_redirect_coverage(self):
        prepared = self.runner.prepare(spec())
        # The caller mutates the spec to a sibling mode of the same agent.
        prepared.spec.mode = "weekly_load"
        evidence = self.runner.complete(prepared, handoff_for(prepared), **COSTS)
        self.assertEqual(evidence.mode, MODE)
        self.assertEqual(evidence.value_observation["mode"], MODE)


class EvidenceOwnershipTests(RunnerHarness):
    """Ownership is verified at retrieval, never inferred from the recipient."""

    def test_real_evidence_without_declared_ownership_is_refused(self):
        with self.assertRaises(MissionRejected) as caught:
            self.runner.prepare(
                spec(
                    evidence=[
                        EvidenceRecord(SOURCE, "connector_record", content="x")
                    ]
                )
            )
        self.assertIn("owner_brain", str(caught.exception))

    def test_opposite_brain_evidence_cannot_be_relabelled(self):
        """An APEX email handed to a JEOS mission is a separation breach."""
        with self.assertRaises(MissionRejected) as caught:
            self.runner.prepare(
                spec(
                    evidence=[
                        EvidenceRecord(
                            "gmail://thread/client-1",
                            "connector_record",
                            content="Client scope change",
                            owner_brain="APEX",
                        )
                    ]
                )
            )
        self.assertIn("constraint packet", str(caught.exception))


class LedgerRootTests(unittest.TestCase):
    def test_default_ledgers_follow_the_runner_root(self):
        """A staged checkout must not write into this checkout's evidence."""
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp) / "checkout"
            staged.mkdir()
            for relative in ("brains/apex", "brains/jeos", "config", "schemas"):
                (staged / relative).mkdir(parents=True, exist_ok=True)
            real = Path(__file__).resolve().parents[1]
            for relative in (
                "brains/apex/agents.toml",
                "brains/jeos/agents.toml",
                "config/specialist_corps.toml",
                "config/value_policy.toml",
            ):
                (staged / relative).write_text(
                    (real / relative).read_text(encoding="utf-8"), encoding="utf-8"
                )
            for schema in (real / "schemas").glob("*.json"):
                (staged / "schemas" / schema.name).write_text(
                    schema.read_text(encoding="utf-8"), encoding="utf-8"
                )
            runner = MissionRunner(root=staged)
            self.assertTrue(str(runner.ledger.path).startswith(str(staged)))
            self.assertTrue(str(runner.value_ledger.path).startswith(str(staged)))
