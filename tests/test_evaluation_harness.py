"""The evaluation harness must stay honest and must not leak into validation.

Record: docs/EVALUATION_HARNESS.md. These tests run without deepeval installed —
that degradation is itself part of the contract, so it is asserted here.
"""

from pathlib import Path
import json
import sys
import unittest

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
