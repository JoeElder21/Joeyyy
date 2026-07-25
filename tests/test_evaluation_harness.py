"""The evaluation harness must stay honest and must not leak into validation.

Record: docs/EVALUATION_HARNESS.md. These tests run without deepeval installed —
that degradation is itself part of the contract, so it is asserted here.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVALS = ROOT / "evals"
sys.path.insert(0, str(EVALS))

import harness  # noqa: E402 - path shim above is deliberate


class ModeInventoryTests(unittest.TestCase):
    """Modes are derived from the manifests, never restated."""

    def test_every_roster_mode_is_inventoried(self):
        modes = harness.load_modes()
        self.assertGreater(len(modes), 0)
        for brain in harness.BRAINS:
            with self.subTest(brain=brain):
                self.assertTrue(any(mode.brain == brain for mode in modes))

    def test_mode_keys_are_unique(self):
        keys = [mode.key for mode in harness.load_modes()]
        self.assertEqual(len(keys), len(set(keys)))

    def test_inventory_carries_the_fields_the_gate_needs(self):
        for mode in harness.load_modes():
            with self.subTest(mode=mode.key):
                self.assertTrue(mode.memory_namespace)
                self.assertTrue(mode.write_targets)
                self.assertTrue(mode.connector_policy)

    def test_promotion_readiness_requires_passed_runs_not_case_files(self):
        # The honesty property. An earlier version set promotion_ready from case
        # files existing, so authoring 39 JSON files would have reported the
        # corps promotable without one evaluation having run.
        coverage = harness.build_coverage()
        # Give every mode a case, and no mode a passing run.
        coverage.covered = {mode.key: Path("synthetic") for mode in coverage.modes}
        summary = coverage.summary()
        self.assertTrue(summary["cases_complete"], "inventory should read complete")
        self.assertFalse(
            summary["promotion_ready"],
            "case files are inventory; promotion needs recorded passing runs",
        )
        self.assertEqual(summary["modes_proven"], 0)
        self.assertTrue(summary["promotion_blockers"])

    def test_promotion_ready_only_when_every_mode_has_a_passing_run(self):
        coverage = harness.build_coverage()
        coverage.covered = {mode.key: Path("synthetic") for mode in coverage.modes}
        coverage.passed = {mode.key: "run-1" for mode in coverage.modes}
        self.assertTrue(coverage.summary()["promotion_ready"])
        # One mode losing its run is enough to block the whole corps.
        coverage.passed.pop(coverage.modes[0].key)
        self.assertFalse(coverage.summary()["promotion_ready"])

    def test_an_empty_corps_is_not_promotion_ready(self):
        # `not self.unproven` is vacuously true on an empty list; readiness must
        # not fall out of having nothing to prove.
        self.assertFalse(harness.Coverage().summary()["promotion_ready"])

    def test_a_new_mode_reads_as_uncovered_not_as_missing(self):
        # The whole point of deriving from the manifests: adding a mode must move
        # the denominator, so it cannot be silently skipped.
        coverage = harness.build_coverage()
        self.assertEqual(
            len(coverage.modes),
            len(coverage.covered) + len(coverage.uncovered),
        )


class CaseIntegrityTests(unittest.TestCase):
    """A case that does not trace to a real mode and a real gate is not evidence."""

    REQUIRED = (
        "mode_key",
        "title",
        "mission",
        "expected_artifacts",
        "expected_behaviors",
        "forbidden_behaviors",
        "provenance",
    )

    def test_cases_declare_every_required_field(self):
        for key, case in harness.load_cases().items():
            for field in self.REQUIRED:
                with self.subTest(case=key, field=field):
                    self.assertIn(field, case)
                    self.assertTrue(case[field])

    def test_cases_target_real_modes(self):
        # build_coverage raises if a case names a mode the roster does not define.
        harness.build_coverage()

    def test_case_metrics_are_mapped_to_recorded_criteria(self):
        for key, case in harness.load_cases().items():
            with self.subTest(case=key):
                metrics = harness.metrics_for(case)
                for name in harness.BASELINE_METRICS:
                    self.assertIn(name, metrics)
                for name in metrics:
                    self.assertIn(name, harness.METRIC_CONTRACT)

    def test_case_artifacts_exist_in_the_brain_manifest(self):
        # Two of the three seed cases originally named artifact types that no
        # manifest declares (`qa_findings`, `reflection_note`). PacketGuard would
        # have rejected any handoff emitting them, so those cases could never
        # have become lawful completed missions — the harness would have been
        # generating unpassable evidence requirements.
        #
        # The harness derives modes from the manifests precisely so they cannot
        # drift; artifacts were the one field still hand-written, and they drifted
        # immediately. Deriving is only safe where it is enforced.
        modes = {mode.key: mode for mode in harness.load_modes()}
        for key, case in harness.load_cases().items():
            registered = set(modes[key].artifact_types)
            for artifact in case.get("expected_artifacts", []):
                with self.subTest(case=key, artifact=artifact):
                    self.assertIn(
                        artifact,
                        registered,
                        f"{key}: {artifact!r} is not a registered artifact type "
                        f"({sorted(registered)})",
                    )

    def test_every_case_forbids_cross_brain_leakage(self):
        for key, case in harness.load_cases().items():
            forbidden = " ".join(case["forbidden_behaviors"]).lower()
            with self.subTest(case=key):
                self.assertIn("brain" if "brain" in forbidden else "namespace", forbidden)

    def test_case_files_are_valid_json_with_stable_keys(self):
        for path in sorted((EVALS / "cases").glob("*.json")):
            with self.subTest(path=path.name):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertIsInstance(payload, dict)


class PacketValidityMetricTests(unittest.TestCase):
    """The one metric that needs no model must actually work, in both directions.

    A metric that only ever returns 0 would fail every evaluation and look
    rigorous; one that only ever returns 1 would pass everything and look clean.
    Both directions are asserted against real packets built by the contract
    suite, so this metric is judged by the same fixtures the runtime is.
    """

    @classmethod
    def setUpClass(cls):
        from tests.test_packet_contracts import PacketContractTests

        PacketContractTests.setUpClass()
        cls.contracts = PacketContractTests
        instance = PacketContractTests(
            "test_valid_delegation_and_handoff_are_bound_to_lease_and_origin"
        )
        cls.delegation, cls.handoff = instance.v21_readonly_pair()

    def test_valid_packet_scores_one(self):
        from packet_validity import score_packet

        verdict = score_packet(self.handoff, delegations=[self.delegation])
        self.assertEqual(verdict.score, 1.0)
        self.assertTrue(verdict.passed)
        self.assertEqual(verdict.errors, ())

    def test_malformed_packet_scores_zero_with_reasons(self):
        from packet_validity import score_packet

        verdict = score_packet({"schema_version": "2.1"})
        self.assertEqual(verdict.score, 0.0)
        self.assertFalse(verdict.passed)
        self.assertTrue(verdict.errors)
        self.assertIn("PacketGuard", verdict.reason())

    def test_absent_packet_is_a_failure_not_an_error(self):
        # A specialist that emits nothing must score zero, not crash the run.
        from packet_validity import score_packet

        verdict = score_packet(None)
        self.assertEqual(verdict.score, 0.0)
        self.assertIn("no packet", verdict.reason())

    def test_legacy_schema_version_is_rejected(self):
        # v2.0 packets are refused by the runtime; the metric must agree with it
        # rather than keep its own opinion.
        from packet_validity import score_packet

        verdict = score_packet(self.contracts.handoff, active_leases=[self.contracts.lease])
        self.assertEqual(verdict.score, 0.0)

    def test_score_is_binary(self):
        # Validity is not a matter of degree: partial credit would let a
        # specialist average past a boundary the runtime enforces absolutely.
        from packet_validity import score_packet

        for packet in (None, {}, {"schema_version": "2.1"}, self.handoff):
            with self.subTest(packet=type(packet).__name__):
                score = score_packet(packet, delegations=[self.delegation]).score
                self.assertIn(score, (0.0, 1.0))

    def test_metric_builder_degrades_without_a_runtime(self):
        import packet_validity

        built = packet_validity.build_metric()
        if not harness.deepeval_available():
            self.assertIsNone(built)


class HonestyContractTests(unittest.TestCase):
    """The harness must refuse to produce evidence it does not have."""

    def test_harness_imports_without_an_evaluation_runtime(self):
        # If this test runs at all, harness imported. Assert the probe is honest
        # rather than hardcoded optimistic.
        self.assertIsInstance(harness.deepeval_available(), bool)

    def test_specialist_dispatch_is_not_stubbed_with_canned_output(self):
        # A stub returning fixed text would make every evaluation pass while
        # attesting to nothing. Assert the refusal is still in place.
        source = (EVALS / "test_specialist_modes.py").read_text(encoding="utf-8")
        self.assertIn("NotImplementedError", source)
        self.assertIn("_invoke_specialist", source)

    def test_dispatch_contract_supplies_observations_not_just_expectations(self):
        # packet_validity needs the emitted packet and tool_correctness needs the
        # observed trace. Supplying only expectations means neither metric can
        # ever fail, which is worse than not running them.
        source = (EVALS / "test_specialist_modes.py").read_text(encoding="utf-8")
        self.assertIn("tools_called=tools_called", source)
        self.assertIn('"packet": emitted_packet', source)

    def test_runner_documents_that_results_leave_the_repository(self):
        source = (EVALS / "run_evaluations.py").read_text(encoding="utf-8")
        self.assertIn("Evaluations", source)
        self.assertIn("gitignored", source)

    def test_output_directory_is_ignored(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("evals/output/", ignore)

    def test_evaluation_suite_is_outside_unittest_discovery(self):
        # `unittest discover -s tests` must never import deepeval.
        self.assertFalse((ROOT / "tests" / "test_specialist_modes.py").exists())
        self.assertTrue((EVALS / "test_specialist_modes.py").exists())


if __name__ == "__main__":
    unittest.main()
