"""Contract tests for the vendored awesome-claude-agents reference corps.

These prompts are third-party text living in an auto-discovered path, so the
constraints recorded in `docs/AGENT_REGISTRY.md` are enforced here rather than
trusted. See the "Vendored reference corps" section of that file.
"""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
VENDORED = ROOT / ".claude" / "agents" / "awesome-claude-agents"
# AGENTS.md: specialists default to read-only; Agent 007 alone executes mutations.
FORBIDDEN_TOOLS = {"Write", "WriteFile", "Edit", "MultiEdit", "NotebookEdit", "Bash"}
NAME_PATTERN = re.compile(r"\A[a-z0-9]+(?:-[a-z0-9]+)*\Z")
DESCRIPTION_PATTERN = re.compile(r"^description:[ \t]*\S", re.M)
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
# `@agent-foo`, or a bare `foo` in backticks on a delegation line.
DELEGATION = re.compile(
    r"(?:delegate to|Target:|hand off to|route (?:them |it )?to)\s*`?@?(?:agent-)?"
    r"([a-z0-9]+(?:-[a-z0-9]+)+)`?",
    re.I,
)


def agent_files() -> list[Path]:
    return sorted(p for p in VENDORED.rglob("*.md") if p.name != "README.md")


def frontmatter_of(path: Path) -> str:
    match = FRONTMATTER.match(path.read_text(encoding="utf-8"))
    assert match is not None, f"{path} has no parseable frontmatter block"
    return match.group(1)


def declared_tools(path: Path) -> list[str]:
    match = re.search(r"^tools:[ \t]*(.+)$", frontmatter_of(path), re.M)
    if not match:
        return []
    return [tool.strip() for tool in match.group(1).split(",") if tool.strip()]


def declared_name(path: Path) -> str:
    match = re.search(r"^name:[ \t]*(\S+)[ \t]*$", frontmatter_of(path), re.M)
    assert match is not None, f"{path} declares no single-token name"
    return match.group(1)


class VendoredAgentContractTests(unittest.TestCase):
    def setUp(self):
        if not VENDORED.is_dir():
            self.skipTest("vendored corps not present")
        self.files = agent_files()
        self.assertTrue(self.files, "vendored corps directory is empty")

    def test_every_prompt_has_parseable_frontmatter_and_description(self):
        for path in self.files:
            with self.subTest(path=path.relative_to(ROOT)):
                block = frontmatter_of(path)
                self.assertIsNotNone(
                    DESCRIPTION_PATTERN.search(block), "missing description"
                )

    def test_names_are_unique_kebab_case_slugs(self):
        seen: dict[str, Path] = {}
        for path in self.files:
            name = declared_name(path)
            with self.subTest(path=path.relative_to(ROOT), name=name):
                self.assertRegex(
                    name, NAME_PATTERN, "agent name must be a kebab-case slug"
                )
                self.assertNotIn(
                    name, seen, f"duplicate name also declared by {seen.get(name)}"
                )
            seen[name] = path

    def test_no_vendored_agent_declares_a_write_capable_tool(self):
        """Agent 007 is the sole write-capable agent; vendored prompts stay read-only."""
        for path in self.files:
            granted = set(declared_tools(path)) & FORBIDDEN_TOOLS
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertEqual(
                    granted, set(), f"write-capable tools must be stripped: {granted}"
                )

    def test_delegation_targets_resolve_to_agents_that_exist(self):
        """An unfulfillable handoff is worse than none: it fails when help is needed."""
        known = {declared_name(path) for path in self.files}
        dangling: dict[str, set[str]] = {}
        for path in self.files:
            text = path.read_text(encoding="utf-8")
            missing = {
                target
                for target in DELEGATION.findall(text)
                if target not in known and target != declared_name(path)
            }
            if missing:
                dangling[str(path.relative_to(VENDORED))] = missing
        self.assertEqual(dangling, {}, f"delegation targets do not exist: {dangling}")


if __name__ == "__main__":
    unittest.main()
