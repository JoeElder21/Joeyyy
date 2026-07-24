"""Tests for the graphiti memory-trial harness: honest blocking, no simulation."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime.memory_trial import TRIAL_GROUP, preconditions, run_trial  # noqa: E402


class MemoryTrialTests(unittest.TestCase):
    def test_preconditions_report_shape(self):
        checks = preconditions(db_host="127.0.0.1", db_port=1)  # nothing listens on 1
        self.assertIn("graphiti_core", checks)
        self.assertFalse(checks["graph_db"]["reachable"])
        self.assertEqual(checks["trial_group"], TRIAL_GROUP)
        self.assertTrue(TRIAL_GROUP.startswith("APEX::"), "trial is one APEX namespace")

    def test_blocked_trial_reports_blocked_and_lists_missing(self):
        report = run_trial(db_host="127.0.0.1", db_port=1)
        self.assertEqual(report["status"], "blocked")
        self.assertTrue(report["missing"])
        self.assertTrue(
            any("graph database" in item for item in report["missing"]),
            report["missing"],
        )
        # Honesty: a blocked trial never fabricates trial evidence.
        self.assertNotIn("episode_uuid", report)
        self.assertNotIn("readback_confirmed", report)


if __name__ == "__main__":
    unittest.main()
