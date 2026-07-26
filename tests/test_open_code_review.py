"""Static and no-model checks for the bounded Open Code Review integration."""

import json
import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIN = "1.7.17"


class OpenCodeReviewIntegrationTests(unittest.TestCase):
    def test_project_rules_are_valid_and_keep_private_state_out(self) -> None:
        rules = json.loads(
            (ROOT / ".opencodereview" / "rule.json").read_text(encoding="utf-8")
        )
        self.assertIn("tests/**/*.py", rules["include"])
        for path in ("audit/**", "private-memory/**", "brains/*/memory/**"):
            self.assertIn(path, rules["exclude"])
        self.assertTrue(rules["rules"])

    def test_install_and_runtime_wrappers_share_the_exact_pin(self) -> None:
        installer = (ROOT / "scripts" / "install_open_code_review.sh").read_text(
            encoding="utf-8"
        )
        wrapper = (ROOT / "scripts" / "open_code_review.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn(f'OCR_VERSION="{PIN}"', installer)
        self.assertIn(f'REQUIRED_OCR_VERSION="{PIN}"', wrapper)
        self.assertIn("OCR_NO_UPDATE=1", installer)
        self.assertIn("OCR_NO_UPDATE=1", wrapper)
        self.assertNotIn("@latest", installer)

    def test_host_adapters_preserve_authority_and_brain_boundary(self) -> None:
        paths = (
            ROOT / ".claude" / "commands" / "open-code-review.md",
            ROOT / ".agents" / "skills" / "open-code-review" / "SKILL.md",
        )
        for path in paths:
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertIn("Agent 007", text)
                self.assertIn("APEX", text)
                self.assertIn("JEOS", text)
                self.assertNotIn("npm install -g", text)

    @unittest.skipUnless(os.environ.get("OCR_INTEGRATION_TEST") == "1", "opt-in installed CLI check")
    def test_installed_cli_resolves_project_rules_without_a_model(self) -> None:
        version = subprocess.run(
            ["ocr", "version"], cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout
        self.assertIn(f"v{PIN}", version)
        result = subprocess.run(
            ["ocr", "rules", "check", "runtime/mission_runner.py"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "OCR_NO_UPDATE": "1"},
        )
        self.assertIn("Source: Project (.opencodereview/rule.json)", result.stdout)
        self.assertIn("fail-closed authority", result.stdout)


if __name__ == "__main__":
    unittest.main()
