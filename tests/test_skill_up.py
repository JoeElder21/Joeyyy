"""Static and installed-binary checks for the governed skill-up workflow."""

import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN = "0.7.0"


class SkillUpIntegrationTests(unittest.TestCase):
    def test_install_and_wrapper_share_pin_and_private_report_root(self) -> None:
        installer = (ROOT / "scripts/install_skill_up.sh").read_text(encoding="utf-8")
        wrapper = (ROOT / "scripts/skill_up.sh").read_text(encoding="utf-8")
        self.assertIn(f'SKILL_UP_VERSION="{PIN}"', installer)
        self.assertIn(f'REQUIRED_VERSION="{PIN}"', wrapper)
        self.assertIn("sha256sum --check", installer)
        self.assertIn("${repo_root}/.state/skill-up", wrapper)
        self.assertNotIn("/latest/", installer)

    def test_adapters_preserve_agent_007_and_brain_separation(self) -> None:
        for relative in (
            ".agents/skills/skill-upper/SKILL.md",
            ".claude/commands/skill-upper.md",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("Agent 007", text)
            self.assertIn("APEX", text)
            self.assertIn("JEOS", text)
            self.assertNotIn("curl -fsSL", text)

        chief = (ROOT / ".codex/agents/apex_chief_of_staff.toml").read_text(encoding="utf-8")
        self.assertIn(".agents/skills/skill-upper/SKILL.md", chief)
        self.assertIn("scripts/skill_up.sh", chief)
        self.assertIn("Keep APEX and JEOS suites", chief)

    def test_public_suite_has_separate_brain_cases_and_no_secrets(self) -> None:
        eval_root = ROOT / ".agents/skills/skill-upper/evals"
        apex = (eval_root / "cases/apex-boundary.yaml").read_text(encoding="utf-8")
        jeos = (eval_root / "cases/jeos-boundary.yaml").read_text(encoding="utf-8")
        config = (eval_root / "eval.yaml").read_text(encoding="utf-8")
        self.assertIn("APEX_ONLY", apex)
        self.assertNotIn("JEOS_PAYLOAD", jeos)
        self.assertIn("JEOS_ONLY", jeos)
        self.assertNotIn("api_key", config.lower())

    @unittest.skipUnless(
        os.environ.get("SKILL_UP_INTEGRATION_TEST") == "1", "opt-in installed CLI check"
    )
    def test_installed_cli_validates_committed_suite(self) -> None:
        completed = subprocess.run(
            [str(ROOT / "scripts/skill_up.sh"), "validate"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("loaded 3 case(s)", completed.stdout)


if __name__ == "__main__":
    unittest.main()
