"""Offline safety checks for the APS validation-gate command surface."""

import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "connectors" / "aps" / "src" / "gate.mjs"
EVIDENCE = ROOT / "connectors" / "aps" / "evidence"


class ApsGateSafetyTests(unittest.TestCase):
    def run_gate(self, *args):
        env = os.environ.copy()
        env.pop("APS_CLIENT_ID", None)
        env.pop("APS_CLIENT_SECRET", None)
        return subprocess.run(
            ["node", str(GATE), *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_missing_credentials_fail_closed_before_evidence_or_network_work(self):
        before = set(EVIDENCE.glob("*.json")) if EVIDENCE.exists() else set()
        result = self.run_gate()
        after = set(EVIDENCE.glob("*.json")) if EVIDENCE.exists() else set()

        self.assertEqual(result.returncode, 2)
        self.assertIn("GATE BLOCKED (fail closed)", result.stderr)
        self.assertEqual(after, before)

    def test_write_steps_cannot_be_run_individually(self):
        result = self.run_gate("--step", "4")

        self.assertEqual(result.returncode, 2)
        self.assertIn("steps 4 and 5 always run together", result.stderr)

    def test_harness_does_not_accept_project_data_redirects(self):
        source = GATE.read_text(encoding="utf-8")

        self.assertNotIn("APS_TEST_MODEL", source)
        self.assertNotIn("APS_TEST_BUCKET", source)
        self.assertNotIn("APS_TEST_URN", source)
        self.assertIn("randomUUID", source)
        self.assertIn("deleteBucket", source)


if __name__ == "__main__":
    unittest.main()
