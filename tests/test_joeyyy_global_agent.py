from pathlib import Path
import json
import subprocess
import sys
import tomllib
import unittest

from scripts.agent_runtime import load_roster


ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / ".codex" / "agents" / "joeyyy_global_agent_engineer.toml"
CONSTITUTION = ROOT / "docs" / "JOEYYY_GLOBAL_AGENT_ENGINEERING_CONSTITUTION.md"


class JoeyyyGlobalAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with AGENT.open("rb") as source:
            cls.agent = tomllib.load(source)
        cls.instructions = cls.agent["developer_instructions"]
        cls.constitution = CONSTITUTION.read_text(encoding="utf-8")

    def test_native_agent_and_exact_activation_are_configured(self):
        self.assertEqual(self.agent["name"], "joeyyy_global_agent_engineer")
        self.assertEqual(self.agent["sandbox_mode"], "workspace-write")
        self.assertIn('complete activation command is "JOEYYY"', self.instructions)
        self.assertIn('"JOEYYY Global Agent Engineer activated."', self.instructions)

    def test_constitution_is_canonical_and_complete(self):
        self.assertIn("canonical constitution", self.instructions)
        for section in range(1, 21):
            self.assertIn(f"## {section}.", self.constitution)
        self.assertIn("Evidence-Governed Evolution", self.constitution)
        self.assertIn("35% threshold", self.constitution)

    def test_agent_007_remains_the_only_cross_brain_governor(self):
        self.assertIn("Agent 007 is the sole cross-brain governor", self.instructions)
        self.assertIn("do not impersonate a second cross-brain channel", self.instructions)
        self.assertIn("progressively retrieving private context", self.instructions)
        self.assertNotIn("joeyyy_global_agent_engineer", load_roster())

    def test_preflight_is_public_safe_and_honest_about_memory(self):
        result = subprocess.run(
            [sys.executable, "scripts/joeyyy_preflight.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        report = json.loads(result.stdout)
        self.assertTrue(report["constitution_exists"])
        self.assertTrue(report["agent_007_contract_exists"])
        self.assertTrue(report["brain_manifests_exist"])
        self.assertEqual(report["private_memory_provider"], "unverified")
        self.assertIn("not private APEX or JEOS memory", report["memory_notice"])

    def test_mission_template_covers_control_points(self):
        template = (ROOT / "templates" / "joeyyy-mission-contract.md").read_text()
        for phrase in ("Definition of done", "Designated writer", "Value hypothesis", "Rollback"):
            self.assertIn(phrase, template)


if __name__ == "__main__":
    unittest.main()
