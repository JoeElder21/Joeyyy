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
# Any explicit @handle, wherever it appears - including the sample commands a prompt
# tells the user to run, which the delegation phrasing above does not cover. The
# lookahead excludes email addresses and domains (@host.tld) and npm scoped packages
# (@radix-ui/react-dialog), neither of which is an agent reference.
AT_REFERENCE = re.compile(r"@(?:agent-)?([a-z0-9]+(?:-[a-z0-9]+)+)(?![./])\b")
EXPECTED_AGENT_COUNT = 33


def agent_files() -> list[Path]:
    return sorted(p for p in VENDORED.rglob("*.md") if p.name != "README.md")


def frontmatter_of(path: Path) -> str:
    match = FRONTMATTER.match(path.read_text(encoding="utf-8"))
    assert match is not None, f"{path} has no parseable frontmatter block"
    return match.group(1)


def declared_tools(path: Path) -> list[str] | None:
    """Declared tools, or None when the field is absent.

    None is NOT the same as "no tools". Claude Code treats an omitted `tools:` field
    as *inherit every tool the main thread has*, Write and Bash included, so an
    absent field is the most permissive state rather than the most restrictive.
    Callers must fail on None instead of treating it as an empty allowlist.
    """
    match = re.search(r"^tools:[ \t]*(.+)$", frontmatter_of(path), re.M)
    if not match:
        return None
    return [tool.strip() for tool in match.group(1).split(",") if tool.strip()]


def declared_name(path: Path) -> str:
    match = re.search(r"^name:[ \t]*(\S+)[ \t]*$", frontmatter_of(path), re.M)
    assert match is not None, f"{path} declares no single-token name"
    return match.group(1)


REGISTRY = ROOT / "docs" / "AGENT_REGISTRY.md"
REGISTRY_HEADING = "## Vendored reference corps"


class VendoredRegistryConsistencyTests(unittest.TestCase):
    """Guards the rollback path, which is only correct if it removes both halves.

    The contract tests below skip when the prompt directory is gone, so a rollback that
    deleted the prompts but left the registry section would otherwise stay green while
    the registry claimed 33 discoverable candidates that no longer exist.
    """

    def test_registry_section_and_prompt_directory_agree(self):
        registered = REGISTRY_HEADING in REGISTRY.read_text(encoding="utf-8")
        present = VENDORED.is_dir() and any(agent_files())
        self.assertEqual(
            registered,
            present,
            "docs/AGENT_REGISTRY.md and .claude/agents/awesome-claude-agents/ disagree: "
            f"registry section {'present' if registered else 'absent'}, prompts "
            f"{'present' if present else 'absent'}. Roll back or restore both together.",
        )


class VendoredAgentContractTests(unittest.TestCase):
    def setUp(self):
        if not VENDORED.is_dir():
            self.skipTest("vendored corps not present")
        self.files = agent_files()
        # An exact count, not merely "some". A partial rollback or an interrupted sync
        # would otherwise leave every contract test passing over a tree that no longer
        # matches what the registry and README claim is installed.
        self.assertEqual(
            len(self.files),
            EXPECTED_AGENT_COUNT,
            f"expected {EXPECTED_AGENT_COUNT} vendored prompts, found {len(self.files)}",
        )

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

    def test_every_prompt_declares_an_explicit_tool_allowlist(self):
        """An omitted `tools:` field inherits everything, including Write and Bash.

        This must be checked separately from the write-capable assertion below: a
        missing field yields no forbidden *names* to match on, so a test that only
        inspects declared names passes while the agent silently holds full access.
        """
        for path in self.files:
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIsNotNone(
                    declared_tools(path),
                    "no `tools:` field — this inherits all tools rather than none",
                )

    def test_no_vendored_agent_declares_a_write_capable_tool(self):
        """Agent 007 is the sole write-capable agent; vendored prompts stay read-only."""
        for path in self.files:
            tools = declared_tools(path)
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIsNotNone(tools, "missing `tools:` grants everything")
                granted = set(tools) & FORBIDDEN_TOOLS
                self.assertEqual(
                    granted, set(), f"write-capable tools must be stripped: {granted}"
                )

    def test_delegation_targets_resolve_to_agents_that_exist(self):
        """An unfulfillable handoff is worse than none: it fails when help is needed."""
        known = {declared_name(path) for path in self.files}
        dangling: dict[str, set[str]] = {}
        for path in self.files:
            text = path.read_text(encoding="utf-8")
            referenced = set(DELEGATION.findall(text)) | set(AT_REFERENCE.findall(text))
            missing = {
                target
                for target in referenced
                if target not in known and target != declared_name(path)
            }
            if missing:
                dangling[str(path.relative_to(VENDORED))] = missing
        self.assertEqual(dangling, {}, f"delegation targets do not exist: {dangling}")


if __name__ == "__main__":
    unittest.main()
