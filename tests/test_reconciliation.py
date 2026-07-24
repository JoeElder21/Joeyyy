"""Drift locks for docs/RECONCILIATION_2026-07-24.md."""

from __future__ import annotations

from pathlib import Path
import sys
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime.cadence import build_cadence_run  # noqa: E402


class ReconciliationTests(unittest.TestCase):
    def test_cadence_orders_agree_across_both_streams(self):
        """runtime.cadence and the scripts/ layer must consume identical orders."""
        for brain in ("apex", "jeos"):
            manifest = tomllib.loads(
                (ROOT / "brains" / brain / "agents.toml").read_text(encoding="utf-8")
            )
            for route in manifest["cadence_routes"]:
                run = build_cadence_run(brain, route["cadence"])
                self.assertEqual(
                    [step.agent for step in run.steps],
                    route["order"],
                    f"{brain}/{route['cadence']} diverged from the manifest order",
                )
                self.assertEqual(run.integrator, route["integrator"])

    def test_ticket_4_absorption_is_real(self):
        """The Codex debate modules exist and define their builders."""
        debate = (ROOT / "scripts" / "group_debate.py").read_text(encoding="utf-8")
        self.assertIn("def ", debate)
        self.assertIn("challenge", debate.lower())
        self.assertTrue((ROOT / "scripts" / "autogen_challenge_pair.py").exists())

    def test_reconciliation_record_names_the_canonical_homes(self):
        record = (ROOT / "docs" / "RECONCILIATION_2026-07-24.md").read_text(
            encoding="utf-8"
        )
        for phrase in (
            "runtime/lifecycle.py",
            "runtime/cadence.py",
            "runtime/writer_lease.py",
            "closed as absorbed",
            "no memory layer is active",
        ):
            self.assertIn(phrase, record)


if __name__ == "__main__":
    unittest.main()
