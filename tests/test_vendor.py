"""Contract tests for the vendored submodules under vendor/.

Two things are asserted here. First, that every declared submodule is
genuinely a pinned gitlink rather than committed upstream content. Second,
that the scanner exclusion which keeps upstream files out of this
repository's privacy and TOML contracts stays narrowly scoped to the declared
submodule paths — a widened exclusion would silently stop scanning this
repository's own files.
"""

from pathlib import Path
import configparser
import subprocess
import unittest

from scripts.privacy_guard import is_vendored, submodule_paths


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SUBMODULES = {
    "vendor/multi-agent-ai-in-civil-engineering": (
        "https://github.com/Kimi-chuheng/Multi-Agent-AI-in-Civil-Engineering.git"
    ),
    "vendor/awesome-civil-engineering": (
        "https://github.com/QuantumNovice/awesome-civil-engineering.git"
    ),
    "vendor/civil-innovation-agent": (
        "https://github.com/Sun3hine7/civil-innovation-agent.git"
    ),
    "vendor/relay": "https://github.com/AgentWorkforce/relay.git",
}


class VendorSubmoduleTests(unittest.TestCase):
    def test_gitmodules_declares_the_expected_upstreams(self) -> None:
        parser = configparser.ConfigParser()
        parser.read(ROOT / ".gitmodules", encoding="utf-8")
        declared = {
            parser.get(section, "path"): parser.get(section, "url")
            for section in parser.sections()
        }
        self.assertEqual(declared, EXPECTED_SUBMODULES)

    def test_every_submodule_is_a_pinned_gitlink_not_committed_content(self) -> None:
        listing = subprocess.run(
            ["git", "ls-files", "-s", "--", "vendor"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        gitlinks = {}
        for line in listing:
            metadata, path = line.split("\t", 1)
            mode, sha, _stage = metadata.split()
            if mode == "160000":
                gitlinks[path] = sha
        self.assertEqual(set(gitlinks), set(EXPECTED_SUBMODULES))
        for path, sha in gitlinks.items():
            with self.subTest(submodule=path):
                self.assertRegex(sha, r"^[0-9a-f]{40}$")

    def test_no_upstream_file_content_is_tracked_in_this_repository(self) -> None:
        tracked = subprocess.run(
            ["git", "ls-files", "--", "vendor"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        own_files = {"vendor/README.md"}
        self.assertEqual(set(tracked) - set(EXPECTED_SUBMODULES), own_files)


class VendorScannerExclusionTests(unittest.TestCase):
    def test_submodule_paths_are_read_from_gitmodules(self) -> None:
        self.assertEqual(submodule_paths(ROOT), frozenset(EXPECTED_SUBMODULES))

    def test_upstream_files_are_excluded_from_the_privacy_contract(self) -> None:
        for submodule in EXPECTED_SUBMODULES:
            with self.subTest(submodule=submodule):
                self.assertTrue(is_vendored(ROOT / submodule / "README.md", ROOT))

    def test_this_repositorys_own_files_are_still_scanned(self) -> None:
        # vendor/README.md is this repository's file and must stay covered;
        # the exclusion is scoped to the submodules, not to vendor/ wholesale.
        for path in ("vendor/README.md", "AGENTS.md", "scripts/privacy_guard.py"):
            with self.subTest(path=path):
                self.assertFalse(is_vendored(ROOT / path, ROOT))

    def test_exclusion_does_not_match_lookalike_sibling_paths(self) -> None:
        self.assertFalse(is_vendored(ROOT / "vendor" / "relay-notes.md", ROOT))
        self.assertFalse(is_vendored(ROOT / "vendor-archive" / "relay" / "x.md", ROOT))

    def test_paths_outside_the_repository_are_not_vendored(self) -> None:
        self.assertFalse(is_vendored(Path("/etc/hosts"), ROOT))


if __name__ == "__main__":
    unittest.main()
