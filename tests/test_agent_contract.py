from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
AGENT_PATH = ROOT / ".codex" / "agents" / "apex_chief_of_staff.toml"
CONFIG_PATH = ROOT / ".codex" / "config.toml"


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

    def test_agent_is_read_only(self):
        self.assertEqual(self.agent["sandbox_mode"], "read-only")

    def test_approval_boundary_is_preserved(self):
        required = [
            "<approval_boundary>",
            "Never send messages or emails.",
            "ask Joe for explicit approval",
            "Do not treat general enthusiasm, old approval, or silence as authorization.",
        ]
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.instructions)

    def test_context_boundary_is_preserved(self):
        self.assertIn("APEX is professional and career context", self.instructions)
        self.assertIn("JEOS is personal context", self.instructions)
        self.assertIn("Keep them separate", self.instructions)

    def test_memory_claims_are_guarded(self):
        self.assertIn("Treat Yaps Memory and every external connector as optional", self.instructions)
        self.assertIn("Never imply memory access when it is unavailable", self.instructions)

    def test_default_close_is_actionable(self):
        self.assertIn("Joe's Next Move", self.instructions)
        self.assertIn("no more than three ordered actions", self.instructions)

    def test_thread_limit_is_bounded(self):
        limit = self.config["agents"]["max_concurrent_threads_per_session"]
        self.assertGreaterEqual(limit, 1)
        self.assertLessEqual(limit, 4)


if __name__ == "__main__":
    unittest.main()

