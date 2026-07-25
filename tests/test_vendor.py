"""Contract tests for the vendored submodules under vendor/.

Two things are asserted here. First, that every declared submodule is
genuinely a pinned gitlink rather than committed upstream content. Second,
that the scanner exclusion which keeps upstream files out of this
repository's privacy and TOML contracts stays narrowly scoped to the declared
submodule paths — a widened exclusion would silently stop scanning this
repository's own files.
"""

import configparser
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.privacy_guard import is_vendored, repository_files, scan_repository, submodule_paths

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SUBMODULES = {
    "vendor/multi-agent-ai-in-civil-engineering": (
        "https://github.com/Kimi-chuheng/Multi-Agent-AI-in-Civil-Engineering.git"
    ),
    "vendor/awesome-civil-engineering": (
        "https://github.com/QuantumNovice/awesome-civil-engineering.git"
    ),
    "vendor/civil-innovation-agent": ("https://github.com/Sun3hine7/civil-innovation-agent.git"),
    "vendor/relay": "https://github.com/AgentWorkforce/relay.git",
}


class VendorSubmoduleTests(unittest.TestCase):
    def test_gitmodules_declares_the_expected_upstreams(self) -> None:
        parser = configparser.ConfigParser()
        parser.read(ROOT / ".gitmodules", encoding="utf-8")
        declared = {
            parser.get(section, "path"): parser.get(section, "url") for section in parser.sections()
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


class TrackedSymlinkScanTests(unittest.TestCase):
    """Gitlinks are dropped by index mode, never by probing the filesystem.

    Filtering with ``Path.is_file()`` would also drop a tracked *dangling*
    symlink, letting a prohibited filename pointing at a private path pass the
    scan as clean. Excluding submodules must not open that hole.
    """

    def _repo_with_dangling_symlink(self, directory: str) -> Path:
        root = Path(directory)

        def run(*args: str) -> None:
            subprocess.run(args, cwd=root, check=True, capture_output=True)

        run("git", "init", "-q", ".")
        # Deliberately not an address-shaped string: this repository's own
        # privacy guard scans this file, and a literal address here would be a
        # finding. Git accepts any non-empty identity.
        run("git", "config", "user.email", "privacy-guard-fixture")
        run("git", "config", "user.name", "privacy-guard-fixture")
        (root / "token.json").symlink_to("/nonexistent/private/token.json")
        (root / "normal.md").write_text("nothing private here\n", encoding="utf-8")
        run("git", "add", "-A")
        run("git", "commit", "-qm", "fixture")
        return root

    def test_tracked_dangling_symlink_is_still_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo_with_dangling_symlink(directory)
            names = {path.name for path in repository_files(root)}
            self.assertIn("token.json", names)

    def test_prohibited_filename_behind_a_dangling_symlink_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo_with_dangling_symlink(directory)
            findings = scan_repository(root)
            self.assertTrue(
                any("prohibited private filename" in finding for finding in findings),
                f"dangling symlink escaped the scan: {findings}",
            )


class StaleGitmodulesScanTests(unittest.TestCase):
    """The tracked-file scan trusts the index mode, never `.gitmodules` text.

    A stale or malformed `path =` entry naming a tracked regular directory
    must not exclude first-party files from the scan. Only a real gitlink
    (mode 160000) is a submodule, and submodule contents never appear in this
    repository's index at all.
    """

    def test_stale_gitmodules_path_does_not_hide_tracked_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def run(*args: str) -> None:
                subprocess.run(args, cwd=root, check=True, capture_output=True)

            run("git", "init", "-q", ".")
            run("git", "config", "user.email", "privacy-guard-fixture")
            run("git", "config", "user.name", "privacy-guard-fixture")
            # Declares a submodule at "private" while actually tracking a
            # regular file there — the drift case.
            (root / ".gitmodules").write_text(
                '[submodule "private"]\n\tpath = private\n\turl = https://example.invalid/x.git\n',
                encoding="utf-8",
            )
            (root / "private").mkdir()
            # Content is deliberately innocuous — this repository's own privacy
            # guard scans this test file, and a credential-shaped literal here
            # would be a finding. The assertion below is on the filename rule.
            (root / "private" / "token.json").write_text("{}\n", encoding="utf-8")
            run("git", "add", "-A")
            run("git", "commit", "-qm", "fixture")

            self.assertEqual(submodule_paths(root), frozenset({"private"}))
            scanned = {str(path.relative_to(root)) for path in repository_files(root)}
            self.assertIn("private/token.json", scanned)
            findings = scan_repository(root)
            self.assertTrue(
                any("prohibited private filename" in finding for finding in findings),
                f"stale .gitmodules path hid a tracked file: {findings}",
            )


if __name__ == "__main__":
    unittest.main()
