"""Drift and isolation tests for the generated Claude Code agent corps.

The `.claude/agents/*.md` corps is a projection of the canonical contracts.
These tests fail if a projection is hand-edited, falls behind its source, or
quietly gains a tool that would break connector isolation or the brain lock.
"""

from pathlib import Path
import tomllib
import unittest

from scripts.generate_claude_agents import (
    CHIEF_OF_STAFF,
    CHIEF_TOOLS,
    GENERATED_MARKER,
    OUTPUT_DIR,
    SPECIALIST_TOOLS,
    build,
    load_manifests,
)

ROOT = Path(__file__).resolve().parents[1]

# Tools that would let a packet-only specialist reach past its delegation packet.
FORBIDDEN_SPECIALIST_TOOLS = {
    "Bash",
    "Write",
    "Edit",
    "NotebookEdit",
    "WebSearch",
    "WebFetch",
    "Task",
}


def frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise AssertionError("missing opening frontmatter fence")
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    raise AssertionError("missing closing frontmatter fence")


class GeneratedCorpsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expected = build()
        cls.roster = load_manifests()

    def test_every_registered_agent_has_a_projection(self):
        expected_names = set(self.roster) | {CHIEF_OF_STAFF}
        produced = {path.stem for path in self.expected}
        self.assertEqual(produced, expected_names)
        # The corps must be non-empty, or every check below passes vacuously.
        self.assertGreaterEqual(len(expected_names), 11)

    def test_projections_on_disk_match_their_canonical_sources(self):
        stale = []
        for path, content in self.expected.items():
            if not path.exists():
                stale.append(f"{path.relative_to(ROOT)} (missing)")
            elif path.read_text(encoding="utf-8") != content:
                stale.append(f"{path.relative_to(ROOT)} (stale)")
        self.assertEqual(
            stale,
            [],
            "run: python scripts/generate_claude_agents.py",
        )

    def test_specialists_cannot_reach_past_their_packet(self):
        for path, content in self.expected.items():
            if path.stem == CHIEF_OF_STAFF:
                continue
            with self.subTest(agent=path.stem):
                tools = {t.strip() for t in frontmatter(content)["tools"].split(",")}
                self.assertEqual(tools, set(SPECIALIST_TOOLS))
                self.assertEqual(tools & FORBIDDEN_SPECIALIST_TOOLS, set())

    def test_chief_of_staff_holds_the_connector_and_writer_surface(self):
        content = self.expected[OUTPUT_DIR / f"{CHIEF_OF_STAFF}.md"]
        tools = {t.strip() for t in frontmatter(content)["tools"].split(",")}
        self.assertEqual(tools, set(CHIEF_TOOLS))
        self.assertIn("Agent 007 activated.", content)

    def test_each_specialist_declares_its_brain_and_packet_only_policy(self):
        for name, meta in self.roster.items():
            with self.subTest(agent=name):
                content = self.expected[OUTPUT_DIR / f"{name}.md"]
                self.assertIn(f"| Owner brain | `{meta['brain']}` |", content)
                self.assertIn("packet_only_no_direct_connectors", content)
                self.assertIn(f"**You are {meta['brain']}-only.**", content)
                other = "JEOS" if meta["brain"] == "APEX" else "APEX"
                # A specialist must never be handed the other brain's namespace.
                self.assertNotIn(f"{other}::", content)

    def test_projections_carry_the_generated_marker_and_source_hash(self):
        for path, content in self.expected.items():
            with self.subTest(agent=path.stem):
                self.assertIn(GENERATED_MARKER, content)
                self.assertIn("<!-- source-sha256: ", content)

    def test_registered_modes_survive_the_projection(self):
        for name, meta in self.roster.items():
            content = self.expected[OUTPUT_DIR / f"{name}.md"]
            for mode in meta.get("modes", []):
                with self.subTest(agent=name, mode=mode):
                    self.assertIn(mode, content)

    def test_lifecycle_status_is_reported_honestly(self):
        for name, meta in self.roster.items():
            with self.subTest(agent=name):
                content = self.expected[OUTPUT_DIR / f"{name}.md"]
                self.assertIn(f"| Lifecycle status | `{meta['status']}` |", content)

    def test_generated_corps_does_not_clobber_unrelated_agents(self):
        """market-operator.md is hand-authored; the generator must leave it alone."""
        market = OUTPUT_DIR / "market-operator.md"
        if market.exists():
            self.assertNotIn(market, self.expected)


class ContractProjectionFidelityTests(unittest.TestCase):
    """The projection reproduces the canonical contract, it does not paraphrase it."""

    def test_developer_instructions_are_reproduced_verbatim(self):
        expected = build()
        roster = load_manifests()
        for name, meta in roster.items():
            with self.subTest(agent=name):
                contract = tomllib.loads(
                    (ROOT / meta["native_file"]).read_text(encoding="utf-8")
                )
                instructions = contract["developer_instructions"].strip()
                content = expected[OUTPUT_DIR / f"{name}.md"]
                self.assertIn(instructions, content)



class BrainSeparationTests(unittest.TestCase):
    def test_duplicate_agent_across_manifests_fails_generation(self):
        """A silent overwrite would emit a projection with the wrong brain lock."""
        import scripts.generate_claude_agents as module

        original = module.tomllib.loads

        def fake_loads(text):
            data = original(text)
            if data.get("brain") == "JEOS":
                data["agents"]["apex_war_architect"] = dict(
                    next(iter(data["agents"].values()))
                )
            return data

        module.tomllib.loads = fake_loads
        try:
            with self.assertRaises(ValueError) as caught:
                module.load_manifests()
            self.assertIn("both brain manifests", str(caught.exception))
        finally:
            module.tomllib.loads = original

if __name__ == "__main__":
    unittest.main()
