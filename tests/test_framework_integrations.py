from pathlib import Path
import subprocess
import sys
import unittest

from agent_runtime.autogen_orchestrator import GroupChatOrchestrator


ROOT = Path(__file__).resolve().parents[1]


class FrameworkIntegrationTests(unittest.TestCase):
    def test_integration_contracts_are_complete_and_fail_closed(self):
        completed = subprocess.run(
            [sys.executable, "scripts/validate_framework_integrations.py"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("9 configured, 0 runtime-validated", completed.stdout)

    def test_autogen_shaped_router_is_brain_locked_and_mode_locked(self):
        router = GroupChatOrchestrator()
        participants = router.participants("APEX", "operating_campaign")
        self.assertEqual([item.name for item in participants], ["apex_war_architect"])
        self.assertEqual(router.select_next("APEX", "operating_campaign"), "apex_war_architect")
        self.assertEqual(router.participants("JEOS", "operating_campaign"), ())
        with self.assertRaises(ValueError):
            router.select_next("JEOS", "operating_campaign")


if __name__ == "__main__":
    unittest.main()
