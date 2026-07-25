from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
AGENT_PATH = ROOT / ".codex" / "agents" / "apex_chief_of_staff.toml"
CONFIG_PATH = ROOT / ".codex" / "config.toml"
PROTOCOL_PATH = ROOT / "docs" / "AGENT_COMMUNITY_PROTOCOL.md"
REGISTRY_PATH = ROOT / "docs" / "AGENT_REGISTRY.md"
INTAKE_PATH = ROOT / "templates" / "agent-intake.md"
AUDIT_PATH = ROOT / "templates" / "weekly-agent-audit.md"


class AgentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with AGENT_PATH.open("rb") as source:
            cls.agent = tomllib.load(source)
        with CONFIG_PATH.open("rb") as source:
            cls.config = tomllib.load(source)
        cls.instructions = cls.agent["developer_instructions"]

    def assert_phrases(self, phrases):
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.instructions)

    def test_required_agent_fields_and_compatible_name(self):
        self.assertEqual(self.agent["name"], "apex_chief_of_staff")
        self.assertIn("Agent 007", self.agent["description"])
        self.assertTrue(self.instructions.strip())

    def test_activation_contract(self):
        self.assert_phrases([
            "<identity_and_activation>",
            'When Joe says "Activate Agent 007"',
            '"Agent 007 activated."',
            "Do not require a second invocation",
            "operating mode, not a claim of omniscience",
        ])

    def test_cross_brain_governance(self):
        self.assert_phrases([
            "<brain_governance>",
            "Agent 007 is the only cross-brain",
            "APEX owns professional and firm context",
            "JEOS owns personal context",
            "Keep each brain's source records separate",
            "Route domain writes through the owning brain's agent",
            "Unknown ownership means investigate and flag",
        ])

    def test_lare_conflict_is_preserved(self):
        self.assertIn("Preserve the current recorded LARE ownership conflict", self.instructions)
        self.assertIn("do not silently choose or merge", self.instructions)

    def test_delegated_authority_covers_requested_actions(self):
        # Agent 007 is the sole write-capable native agent; specialists stay
        # read-only (asserted per-agent in test_specialist_corps).
        self.assertEqual(self.agent["sandbox_mode"], "workspace-write")
        self.assertNotIn("approval_policy", self.agent)
        self.assert_phrases([
            "<delegated_authority>",
            "send messages and emails",
            "calendar events",
            "complete, or reorganize tasks",
            "edit authorized external systems",
            "commit, and push code",
            "Do not ask Joe for per-action approval",
        ])

    def test_agent_community_contract(self):
        self.assert_phrases([
            "<agent_community>",
            "full registered corps",
            "delegation packet",
            "one designated writer",
            "Reconcile disagreements using evidence",
        ])
        self.assertTrue(PROTOCOL_PATH.is_file())

    def test_registry_and_new_agent_intake(self):
        self.assert_phrases([
            "<agent_registry_and_intake>",
            "New agents begin as candidates",
            "read its complete Markdown, TOML, YAML",
            "Do not blindly concatenate prompts",
            "smallest reusable improvement",
            "rollback point",
        ])
        self.assertTrue(REGISTRY_PATH.is_file())
        self.assertTrue(INTAKE_PATH.is_file())

    def test_reflection_and_error_learning(self):
        self.assert_phrases([
            "<reflection_and_self_improvement>",
            "Log material errors",
            "recurrence test",
            "testable, versioned, and reversible",
            "Propose new specialists",
        ])

    def test_weekly_audit_contract(self):
        self.assert_phrases([
            "<weekly_audit>",
            "every registered agent",
            "Compare APEX and JEOS",
            "Analyze Agent 007's own decisions",
            "Never manufacture metrics",
        ])
        self.assertTrue(AUDIT_PATH.is_file())

    def test_memory_and_access_claims_are_guarded(self):
        self.assertIn("Treat Yaps Memory and every external connector as optional", self.instructions)
        self.assertIn("Never imply memory or connector access", self.instructions)
        self.assertIn("Verify every agent, connector, skill, memory source", self.instructions)

    def test_default_close_is_actionable(self):
        self.assertIn("Joe's Next Move", self.instructions)
        self.assertIn("no more than three ordered actions", self.instructions)

    def test_project_defaults_are_read_only_and_do_not_bypass_approval(self):
        self.assertEqual(self.config["sandbox_mode"], "read-only")
        self.assertNotIn("approval_policy", self.config)
        self.assertNotIn("sandbox_workspace_write", self.config)

    def test_multi_agent_support_is_enabled_and_bounded(self):
        agents = self.config["agents"]
        self.assertTrue(agents["enabled"])
        self.assertGreaterEqual(agents["max_concurrent_threads_per_session"], 2)
        self.assertLessEqual(agents["max_concurrent_threads_per_session"], 8)


if __name__ == "__main__":
    unittest.main()
