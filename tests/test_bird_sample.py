"""Bird sample must stay keyless, gated, and v2.1-roster-safe."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIRD = ROOT / "connectors" / "bird"


class BirdSampleContractTests(unittest.TestCase):
    def _read(self, relative: str) -> str:
        return (BIRD / relative).read_text(encoding="utf-8")

    def test_client_reads_api_key_only_from_env(self):
        source = self._read("src/client.ts")
        self.assertIn("BIRD_API_KEY", source)
        self.assertIn("process.env", source)
        self.assertIn("BirdClient", source)
        self.assertIn("apiKey", source)
        self.assertNotIn("bk_us1_", source)
        self.assertNotIn("bk_eu1_", source)

    def test_hello_world_is_gated_and_not_auto_sent(self):
        source = self._read("src/hello-world.ts")
        self.assertIn("BIRD_SEND_HELLO", source)
        self.assertIn("BIRD_HELLO_TO", source)
        self.assertIn("BIRD_FROM", source)
        self.assertIn("MT1FL8M9VY", source)
        self.assertIn('BIRD_SEND_HELLO !== "1"', source)

    def test_otp_example_is_gated_and_names_the_catalogue_template(self):
        source = self._read("src/otp-example.ts")
        self.assertIn("bird_otp_verification", source)
        self.assertIn("BIRD_SEND_OTP", source)
        self.assertIn('BIRD_SEND_OTP !== "1"', source)

    def test_env_example_has_no_literal_key(self):
        source = self._read(".env.example")
        self.assertIn("BIRD_API_KEY=", source)
        self.assertIn("bk_xxxxxxxxx", source)
        assigned = [
            line
            for line in source.splitlines()
            if line.startswith("BIRD_API_KEY=") and line.strip() != "BIRD_API_KEY="
        ]
        self.assertEqual(assigned, [])

    def test_readme_documents_order_and_secret_placement(self):
        source = self._read("README.md")
        self.assertIn("MT1FL8M9VY", source)
        self.assertIn("BIRD_API_KEY", source)
        self.assertIn("GitHub", source)
        self.assertIn("bird_otp_verification", source)
        self.assertIn("BIRD_SEND_HELLO=1", source)
