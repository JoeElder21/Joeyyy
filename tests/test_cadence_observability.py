"""Tests for prefect cadence flows and OpenTelemetry mission observability.
Both skip cleanly when the runtime stack is absent."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import unittest

from scripts.agent_runtime import AuditLedger, load_roster
from scripts.orchestration_graphs import load_manifest
from scripts.packet_guard import PacketGuard
from tests.test_agent_runtime import _v21_pair

ROOT = Path(__file__).resolve().parents[1]


def _available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


@unittest.skipUnless(_available("prefect"), "prefect not installed")
class CadenceFlowTests(unittest.TestCase):
    def test_flow_runs_manifest_order_and_logs_steps(self):
        from scripts.cadence_flows import build_cadence_flow

        manifest = load_manifest("apex", ROOT)
        route = next(r for r in manifest["cadence_routes"] if r["cadence"] == "daily")
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AuditLedger(Path(tmp) / "audit.jsonl")
            flow = build_cadence_flow(
                "apex", "daily", lambda agent, state: {"note": "ran"}, ledger
            )
            outcome = flow()
            ran = [step["agent"] for step in outcome["steps"]]
            self.assertEqual(ran, list(route["order"]) + [route["integrator"]])
            self.assertEqual(ledger.verify(), [])

    def test_deployment_specs_cover_every_manifest_route(self):
        from scripts.cadence_flows import deployment_specs

        specs = deployment_specs(ROOT)
        flows = {spec["flow"] for spec in specs}
        self.assertIn("apex-daily-cadence", flows)
        self.assertIn("jeos-weekly-cadence", flows)
        for spec in specs:
            self.assertTrue(spec["cron"], spec["flow"])
            self.assertTrue(spec["order"], spec["flow"])
            self.assertTrue(spec["order"][-1].endswith("chief_of_staff"), spec["flow"])


@unittest.skipUnless(_available("opentelemetry.sdk"), "opentelemetry not installed")
class ObservabilityTests(unittest.TestCase):
    def test_admission_and_return_produce_reviewable_spans(self):
        from scripts.observability import MissionTracer

        guard = PacketGuard(ROOT)
        roster = load_roster(ROOT)
        delegation, handoff_return = _v21_pair()
        with tempfile.TemporaryDirectory() as tmp:
            tracer = MissionTracer(AuditLedger(Path(tmp) / "audit.jsonl"))
            tracer.traced_admission(deepcopy(delegation), "apex_war_architect", roster, guard)
            legacy = deepcopy(delegation)
            legacy["schema_version"] = "2.0"
            from scripts.agent_runtime import HandoffRejected

            with self.assertRaises(HandoffRejected):
                tracer.traced_admission(legacy, "apex_war_architect", roster, guard)
            errors = tracer.traced_return(
                deepcopy(handoff_return), guard, delegations=[delegation]
            )
            self.assertEqual(errors, [])

            review = tracer.weekly_review()
            self.assertEqual(review["total_spans"], 3)
            self.assertEqual(review["by_outcome"]["delegation.admission:admitted"], 1)
            self.assertEqual(review["by_outcome"]["delegation.admission:rejected"], 1)
            self.assertEqual(review["by_outcome"]["specialist.return:valid"], 1)
            self.assertEqual(len(review["rejections"]), 1)
            self.assertIn("legacy", review["rejections"][0]["errors"])


if __name__ == "__main__":
    unittest.main()
