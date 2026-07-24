"""Tests for the cadence engine (stdlib) and Prefect flows (skipped without prefect)."""

from __future__ import annotations

import datetime
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime.cadence import (  # noqa: E402
    INTEGRATOR,
    build_cadence_run,
    run_hygiene_sweep,
    status_line,
)

ALL_ROUTES = [
    ("apex", "daily"),
    ("apex", "weekly"),
    ("apex", "monthly"),
    ("jeos", "daily"),
    ("jeos", "weekly"),
    ("jeos", "monthly"),
]


class CadenceEngineTests(unittest.TestCase):
    def test_every_manifest_route_builds_a_valid_plan(self):
        for brain, cadence in ALL_ROUTES:
            run = build_cadence_run(brain, cadence)
            self.assertEqual(run.integrator, INTEGRATOR)
            self.assertGreaterEqual(len(run.steps), 3)
            for step in run.steps:
                self.assertTrue(step.agent.startswith(f"{brain}_"))
                self.assertTrue(step.registered_modes, f"{step.agent} has no modes")
                self.assertFalse(step.executed)

    def test_weekly_apex_order_matches_the_runbook(self):
        run = build_cadence_run("apex", "weekly")
        self.assertEqual(
            [step.agent for step in run.steps],
            [
                "apex_intelligence_forge",
                "apex_delivery_commander",
                "apex_deal_engine",
                "apex_war_architect",
                "apex_systems_blacksmith",
            ],
        )

    def test_unexecuted_specialist_steps_report_partial_never_complete(self):
        run = build_cadence_run("apex", "weekly")
        self.assertEqual(run.status, "partial")
        for step in run.steps:
            step.executed = True
        self.assertEqual(run.status, "complete")

    def test_single_mode_selection_rejects_unregistered_modes(self):
        run = build_cadence_run("apex", "weekly")
        delivery = next(s for s in run.steps if s.agent == "apex_delivery_commander")
        delivery.select_mode(delivery.registered_modes[0])
        with self.assertRaises(ValueError):
            delivery.select_mode("not_a_registered_mode")

    def test_unknown_cadence_fails_closed(self):
        with self.assertRaises(ValueError):
            build_cadence_run("apex", "hourly")

    def test_hygiene_sweep_appends_exactly_one_dated_line_and_reports_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "cadence-log.md"
            checks = (
                ("ok", (sys.executable, "-c", "pass")),
                ("bad", (sys.executable, "-c", "raise SystemExit(1)")),
            )
            today = datetime.date(2026, 7, 24)
            results = run_hygiene_sweep(checks=checks, log_path=log, today=today)
            self.assertEqual(results, {"ok": True, "bad": False})
            lines = log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines, ["- 2026-07-24: ok=pass bad=FAIL"])

            run_hygiene_sweep(checks=checks[:1], log_path=log, today=today)
            lines = log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2, "log must be append-only, one line per run")
            self.assertEqual(lines[0], "- 2026-07-24: ok=pass bad=FAIL")

    def test_status_line_is_honest_about_partial_runs(self):
        run = build_cadence_run("jeos", "weekly")
        run.hygiene_results = {"unittest": True}
        line = status_line(run)
        self.assertIn("jeos/weekly: partial", line)
        self.assertIn("0/5 specialist steps executed", line)
        self.assertIn("unittest=pass", line)


@unittest.skipUnless(
    importlib.util.find_spec("prefect") is not None, "prefect not installed"
)
class CadenceFlowTests(unittest.TestCase):
    def test_cadence_flow_builds_plan_and_reports_partial(self):
        from prefect.testing.utilities import prefect_test_harness

        from runtime.cadence_flow import build_flows

        flows = build_flows()
        with prefect_test_harness():
            line = flows["cadence_flow"]("apex", "weekly", with_hygiene=False)
        self.assertIn("apex/weekly: partial", line)
        self.assertIn("5 specialist steps", line)


if __name__ == "__main__":
    unittest.main()
