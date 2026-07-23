import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "scripts" / "validate_specialist_corps.py"


class LocalSpecialistValidationTests(unittest.TestCase):
    def test_static_harness_is_executable_complete_and_honest(self):
        completed = subprocess.run(
            [sys.executable, str(HARNESS)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            completed.stdout + completed.stderr,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(
            set(result),
            {
                "valid",
                "validation_mode",
                "named_agents_invoked",
                "connectors_called",
                "real_missions_completed",
                "contract_packets_validated",
                "boundary_rejections_validated",
            },
        )
        self.assertTrue(result["valid"])
        self.assertEqual(
            result["validation_mode"],
            "static_contract_and_synthetic_packet",
        )
        self.assertFalse(result["named_agents_invoked"])
        self.assertFalse(result["connectors_called"])
        self.assertFalse(result["real_missions_completed"])
        self.assertEqual(result["contract_packets_validated"], 10)
        self.assertEqual(result["boundary_rejections_validated"], 10)


if __name__ == "__main__":
    unittest.main()
