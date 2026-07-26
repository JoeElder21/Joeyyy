"""Enforcement for the JOEYYY Global Agent Engineering Constitution adoption.

Guards the section-18 single-canonical-copy rule, the thin runtime adapters,
and the 2026-07-25 supersessions recorded in
docs/CONSTITUTION_ADOPTION_2026-07-25.md.
"""

import tomllib
import unittest
from pathlib import Path

from scripts.privacy_guard import gitlink_paths, is_vendored

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

EXCLUDED_PARTS = {".git", "__pycache__", ".venv", "node_modules"}

SUPERSEDED_STAFFING_PHRASES = ("full registered corps", "smallest useful team")
CURRENT_STAFFING_PHRASE = "smallest evidence-justified team"

# Surfaces allowed to quote superseded phrases as recorded history.
SUPERSESSION_TRAIL_FILES = {
    Path("AGENTS.md"),
    Path("docs/CONSTITUTION_ADOPTION_2026-07-25.md"),
}


def policy_surface_files(suffixes):
    """First-party tracked policy surfaces; vendored gitlink trees excluded.

    Exclusion is computed on the path relative to ROOT so directory names in
    the checkout location above the repository cannot silently empty the scan,
    and vendor content is excluded only when the git index proves it is a
    gitlink (scripts/privacy_guard.is_vendored), keeping this repository's own
    files under vendor/ covered.
    """
    gitlinks = gitlink_paths(ROOT)
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        if EXCLUDED_PARTS.intersection(path.relative_to(ROOT).parts):
            continue
        if is_vendored(path, ROOT, gitlinks):
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
        scanned = []
        carriers = []
        for path in policy_surface_files({".md"}):
            scanned.append(path)
            if path == AGENTS_PATH:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            title_as_heading = any(line.strip() == CONSTITUTION_TITLE for line in text.splitlines())
            section_hits = sum(heading in text for heading in SECTION_HEADINGS)
            if title_as_heading or section_hits >= 3:
                carriers.append(str(path.relative_to(ROOT)))
        # The scan must prove it actually saw the tree, not pass vacuously.
        self.assertIn(AGENTS_PATH, scanned)
        self.assertIn(ROOT / "README.md", scanned)
        self.assertEqual(carriers, [])

    def test_annex_is_subordinate_to_the_constitution(self):
        self.assertIn("Repository Operating Annex", self.agents_text)
        self.assertIn("the constitution wins", self.agents_text)


class RuntimeAdapterTests(unittest.TestCase):
    def adapter_texts(self):
        for path in (CLAUDE_ADAPTER_PATH, COPILOT_ADAPTER_PATH):
            yield path, path.read_text(encoding="utf-8")

    def test_adapters_name_the_canonical_policy(self):
        for path, text in self.adapter_texts():
            with self.subTest(adapter=path.name):
                self.assertIn("AGENTS.md", text)
                self.assertIn("JOEYYY Global Agent Engineering Constitution", text)
                # The adapter must say which document wins, or "thin" is a
                # description rather than a rule.
                self.assertIn("the constitution wins", text)

    def test_adapters_do_not_restate_the_constitution(self):
        """Section 18's actual rule is no duplicated policy, not a byte budget.

        An earlier version capped adapters at 2000 characters. PR #26 then
        merged a genuinely substantive Copilot entry point — bidirectional
        activation, the Awesome Copilot layer, the mission protocol — which is
        exactly the runtime-specific invocation guidance section 18 permits, and
        it is far over any sensible byte cap. The cap was a proxy; the rule it
        stood for is that no adapter may carry an independently editable copy of
        constitution policy. Test the rule.
        """
        for path, text in self.adapter_texts():
            with self.subTest(adapter=path.name):
                for heading in SECTION_HEADINGS:
                    self.assertNotIn(heading, text)
                self.assertNotIn(CONSTITUTION_TITLE, text)


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
        for phrase in SUPERSEDED_STAFFING_PHRASES:
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, self.instructions)

    def test_superseded_phrases_do_not_reappear_on_any_policy_surface(self):
        scanned = []
        offenders = []
        for path in policy_surface_files({".md", ".toml"}):
            scanned.append(path)
            if path.relative_to(ROOT) in SUPERSESSION_TRAIL_FILES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for phrase in SUPERSEDED_STAFFING_PHRASES:
                if phrase in text:
                    offenders.append(f"{path.relative_to(ROOT)}: {phrase}")
        self.assertIn(AGENTS_PATH, scanned)
        self.assertIn(CODEX_CONTRACT_PATH, scanned)
        self.assertEqual(offenders, [])

    def test_adoption_record_preserves_the_supersession_trail(self):
        record = ADOPTION_RECORD_PATH.read_text(encoding="utf-8")
        for phrase in SUPERSEDED_STAFFING_PHRASES:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, record)
        self.assertIn(CURRENT_STAFFING_PHRASE, record)
        self.assertIn("2026-07-24", record)


class ContractCascadeTests(unittest.TestCase):
    """The constitution's section 5 and 9 rules must hold in the Codex contract."""

    @classmethod
    def setUpClass(cls):
        with CODEX_CONTRACT_PATH.open("rb") as source:
            cls.instructions = tomllib.load(source)["developer_instructions"]

    def test_lare_amendment_cascaded(self):
        self.assertIn("Apply the current valid LARE amendment", self.instructions)
        self.assertNotIn("Preserve the current recorded LARE ownership conflict", self.instructions)

    def test_always_gated_list_cascaded(self):
        for phrase in (
            "final permit or agency submission",
            "scheduled-task creation or deletion",
            "modification of Separation governance",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.instructions)


if __name__ == "__main__":
    unittest.main()
