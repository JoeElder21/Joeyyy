"""Enforcement for the JOEYYY Global Agent Engineering Constitution adoption.

Guards the section-18 single-canonical-copy rule, the thin runtime adapters,
and the 2026-07-25 staffing-rule supersession recorded in
docs/CONSTITUTION_ADOPTION_2026-07-25.md.
"""

from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
AGENTS_PATH = ROOT / "AGENTS.md"
CLAUDE_ADAPTER_PATH = ROOT / "CLAUDE.md"
COPILOT_ADAPTER_PATH = ROOT / ".github" / "copilot-instructions.md"
CODEX_CONTRACT_PATH = ROOT / ".codex" / "agents" / "apex_chief_of_staff.toml"
ADOPTION_RECORD_PATH = ROOT / "docs" / "CONSTITUTION_ADOPTION_2026-07-25.md"

CONSTITUTION_TITLE = "# JOEYYY Global Agent Engineering Constitution"

SECTION_HEADINGS = [
    "## 1. Normative Authority and Empirical Evidence",
    "## 2. Activation, Scope, and Mandatory Preflight",
    "## 3. Truth and Status Discipline",
    "## 4. Public Repository and Private Canon",
    "## 5. Brain Separation and Agent 007",
    "## 6. Roster Discovery, Staffing, Handoffs, and Group Plans",
    "## 7. Capabilities, Identities, and Agent Foundry",
    "## 8. Designated Writer, Mutation, and Git Control",
    "## 9. Always-Gated and Unattended Actions",
    "## 10. Engineering, Security, and Credentials",
    "## 11. Validation and Completion Evidence",
    "## 12. Lifecycle, Evaluation, and Promotion",
    "## 13. Evidence-Governed Evolution",
    "## 14. Durable Memory and Learning",
    "## 15. External Agent and Capability Intake",
    "## 16. Professional, AEC, Scientific, and Human Boundaries",
    "## 17. Value and Performance",
    "## 18. One Cross-Runtime Repository Policy",
    "## 19. Stop Conditions",
    "## 20. Completion Contract and Operating Loop",
]

# External or generated trees that are not policy surfaces of this repository.
EXCLUDED_DIRS = {".git", "vendor", "third_party", "node_modules", ".venv", "__pycache__"}

SUPERSEDED_STAFFING_PHRASE = "full registered corps"
CURRENT_STAFFING_PHRASE = "smallest evidence-justified team"


def markdown_files():
    for path in sorted(ROOT.rglob("*.md")):
        if EXCLUDED_DIRS.intersection(part.name for part in path.parents):
            continue
        yield path


class ConstitutionCanonicalCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agents_text = AGENTS_PATH.read_text(encoding="utf-8")

    def test_constitution_lives_in_root_agents_md(self):
        self.assertTrue(self.agents_text.startswith(CONSTITUTION_TITLE))
        for heading in SECTION_HEADINGS:
            with self.subTest(heading=heading):
                self.assertIn(heading, self.agents_text)

    def test_agents_md_holds_exactly_one_copy(self):
        self.assertEqual(self.agents_text.count(CONSTITUTION_TITLE), 1)
        for heading in SECTION_HEADINGS:
            with self.subTest(heading=heading):
                self.assertEqual(self.agents_text.count(heading), 1)

    def test_no_second_copy_anywhere_in_the_repository(self):
        carriers = []
        for path in markdown_files():
            if path == AGENTS_PATH:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            title_as_heading = any(
                line.strip() == CONSTITUTION_TITLE for line in text.splitlines()
            )
            section_hits = sum(heading in text for heading in SECTION_HEADINGS)
            if title_as_heading or section_hits >= 3:
                carriers.append(str(path.relative_to(ROOT)))
        self.assertEqual(carriers, [])

    def test_annex_is_subordinate_to_the_constitution(self):
        self.assertIn("Repository Operating Annex", self.agents_text)
        self.assertIn("the constitution wins", self.agents_text)


class RuntimeAdapterTests(unittest.TestCase):
    def adapter_texts(self):
        for path in (CLAUDE_ADAPTER_PATH, COPILOT_ADAPTER_PATH):
            yield path, path.read_text(encoding="utf-8")

    def test_adapters_exist_and_point_to_agents_md(self):
        for path, text in self.adapter_texts():
            with self.subTest(adapter=path.name):
                self.assertIn("AGENTS.md", text)
                self.assertIn("thin runtime adapter", text)
                self.assertIn("JOEYYY Global Agent Engineering Constitution", text)

    def test_adapters_stay_thin(self):
        for path, text in self.adapter_texts():
            with self.subTest(adapter=path.name):
                self.assertLess(len(text), 4000)
                for heading in SECTION_HEADINGS:
                    self.assertNotIn(heading, text)


class StaffingRuleSupersessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agents_text = AGENTS_PATH.read_text(encoding="utf-8")
        with CODEX_CONTRACT_PATH.open("rb") as source:
            cls.contract = tomllib.load(source)
        cls.instructions = cls.contract["developer_instructions"]

    def test_policy_states_current_staffing_rule(self):
        self.assertIn(CURRENT_STAFFING_PHRASE, self.agents_text)

    def test_codex_contract_matches_current_staffing_rule(self):
        self.assertIn(CURRENT_STAFFING_PHRASE, self.instructions)
        self.assertNotIn(SUPERSEDED_STAFFING_PHRASE, self.instructions)

    def test_adoption_record_preserves_the_supersession_trail(self):
        record = ADOPTION_RECORD_PATH.read_text(encoding="utf-8")
        self.assertIn(SUPERSEDED_STAFFING_PHRASE, record)
        self.assertIn(CURRENT_STAFFING_PHRASE, record)
        self.assertIn("2026-07-24", record)


if __name__ == "__main__":
    unittest.main()
