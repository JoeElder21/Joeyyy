"""The command line: dry run, verify, render and write plans on a temporary store."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from terminal import cli

FIXTURE = Path(__file__).resolve().parents[1] / "terminal" / "fixtures" / "synthetic_inputs.json"


class CliTests(unittest.TestCase):
    def run_cli(self, *argv) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(list(argv))
        return code, out.getvalue()

    def test_dry_run_verify_render_and_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store"
            page = Path(tmp) / "page.html"
            code, out = self.run_cli(
                "dry-run", "--inputs", str(FIXTURE), "--store", str(store), "--render", str(page)
            )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["status"], "PUBLISHED")
            self.assertTrue((store / "run_report.json").exists())
            self.assertTrue(page.exists())
            code, out = self.run_cli("verify", "--store", str(store))
            self.assertEqual(code, 0)
            report = json.loads(out)
            self.assertTrue(report["ok"])
            self.assertEqual(report["schema_errors"], [])
            plan = Path(tmp) / "plan.json"
            code, out = self.run_cli("write-plan", "--store", str(store), "--out", str(plan))
            self.assertEqual(code, 0)
            batches = json.loads(plan.read_text(encoding="utf-8"))
            self.assertTrue(all(len(b) <= 50 for b in batches))
            self.assertEqual(sum(len(b) for b in batches), report["documents"])
            code, out = self.run_cli(
                "render", "--store", str(store), "--out", str(page), "--title", "Test Terminal"
            )
            self.assertEqual(code, 0)
            self.assertIn("<title>Test Terminal</title>", page.read_text(encoding="utf-8"))

    def test_blocked_dry_run_exits_non_zero_and_verify_flags_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store"
            code, out = self.run_cli(
                "dry-run",
                "--inputs",
                str(FIXTURE),
                "--store",
                str(store),
                "--inject",
                "critic-block",
            )
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(out)["status"], "BLOCKED")
            store2 = Path(tmp) / "store2"
            self.run_cli("dry-run", "--inputs", str(FIXTURE), "--store", str(store2))
            rec = next((store2 / "recommendations").glob("*.json"))
            doc = json.loads(rec.read_text(encoding="utf-8"))
            doc["stance"] = "SELL"
            rec.write_text(json.dumps(doc), encoding="utf-8")
            code, out = self.run_cli("verify", "--store", str(store2))
            self.assertEqual(code, 1)
            self.assertTrue(any("content hash" in e for e in json.loads(out)["schema_errors"]))


if __name__ == "__main__":
    unittest.main()
