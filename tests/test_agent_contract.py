from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
AGENT_PATH = ROOT / ".codex" / "agents" / "apex_chief_of_staff.toml"
CONFIG_PATH = ROOT / ".codex" / "config.toml"
PROTOCOL_PATH = ROOT / "docs" / "AGENT_COMMUNITY_PROTOCOL.md"


class AgentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with AGENT_PATH.open("rb") as source:
            cls.agent = tomllib.load(source)
        with CONFIG_PATH.open("rb") as source:
            cls.config = tomllib.load(source)
        cls.instructions = cls.agent["developer_instructions"]

    def test_required_agent_fields(self):
        self.assertEqual(self.agent["name"], "apex_chief_of_staff")
        self.assertTrue(self.agent["description"].strip())
        self.assertTrue(self.instructions.strip())

    def test_agent_can_execute_without_its_old_approval_gate(self):
        self.assertEqual(self.agent["sandbox_mode"], "workspace-write")
        self.assertEqual(self.agent["approval_policy"], "never")
        self.assertNotIn("<approval_boundary>", self.instructions)
        self.assertNotIn("ask Joe for explicit approval", self.instructions)

    def test_delegated_authority_covers_requested_actions(self):
        required = [
            "<delegated_authority>",
            "send messages and emails",
            "calendar events",
            "complete, or reorganize tasks",
            "edit authorized external systems",
            "commit, and push code",
            "Do not ask Joe for per-action approval",
        ]
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.instructions)

    def test_agent_community_contract_is_present(self):
        required = [
            "<agent_community>",
            "delegate bounded work",
            "Run independent work in parallel",
            "one designated writer",
            "Reconcile disagreements using evidence",
        ]
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.instructions)
        self.assertTrue(PROTOCOL_PATH.is_file())

    def test_context_boundary_is_preserved(self):
        self.assertIn("APEX is professional and career context", self.instructions)
        self.assertIn("JEOS is personal context", self.instructions)
        self.assertIn("Keep them separate", self.instructions)

    def test_memory_claims_are_guarded(self):
        self.assertIn("Treat Yaps Memory and every external connector as optional", self.instructions)
        self.assertIn("Never imply memory or connector access", self.instructions)

    def test_default_close_is_actionable(self):
        self.assertIn("Joe's Next Move", self.instructions)
        self.assertIn("no more than three ordered actions", self.instructions)

    def test_project_autonomy_and_network_are_enabled(self):
        self.assertEqual(self.config["sandbox_mode"], "workspace-write")
        self.assertEqual(self.config["approval_policy"], "never")
        self.assertTrue(self.config["sandbox_workspace_write"]["network_access"])

    def test_multi_agent_support_is_enabled_and_bounded(self):
        agents = self.config["agents"]
        self.assertTrue(agents["enabled"])
        self.assertGreaterEqual(agents["max_concurrent_threads_per_session"], 2)
        self.assertLessEqual(agents["max_concurrent_threads_per_session"], 8)


if __name__ == "__main__":
    unittest.main()
