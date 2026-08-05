"""Contract tests for the vendored submodules under vendor/.

Two things are asserted here. First, that every declared submodule is
genuinely a pinned gitlink rather than committed upstream content. Second,
that the scanner exclusion which keeps upstream files out of this
repository's privacy and TOML contracts stays narrowly scoped to the declared
submodule paths — a widened exclusion would silently stop scanning this
repository's own files.
"""

import configparser
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.privacy_guard import (
    gitlink_paths,
    index_is_authoritative,
    is_vendored,
    repository_files,
    scan_repository,
    submodule_paths,
    tracked_paths,
)

ROOT = Path(__file__).resolve().parents[1]

# vendor/relay is pinned to the immutable commit that upstream tag v11.2.0
# points at. Textual agreement between the provenance tables cannot establish
# this: copying an arbitrary SHA into both of them reads as consistent while
# the repository goes on claiming, and installing, the v11.2.0 release.
RELAY_TAG = "v11.2.0"
RELAY_TAG_COMMIT = "cce0cb9af8035869629afb252518b79d27167dbc"

# sha256 of each upstream repository's own dependency source, recorded at
# intake. The declarations under requirements/ are derived from these files;
# if upstream changes one, the derived declaration must be re-derived rather
# than silently left behind when the gitlink advances.
UPSTREAM_DEPENDENCY_SOURCES = {
    "vendor/awesome-civil-engineering": (
        "requirements.txt",
        "25adfa7521f75fe7cb54c6c4172221adef3fb3268dea95f032347a2fd6a85441",
    ),
    "vendor/multi-agent-ai-in-civil-engineering": (
        "requirements",
        "0073ab722a9ca69a55593983e0195c1ccb8b4c00982e9f27236d23d9a2dbfd59",
    ),
    "vendor/civil-innovation-agent": (
        "package.json",
        "55e3afc066b53b5228a7227717085a582e778c095c810f0a114e433847094f9a",
    ),
}

# sha256 of the derived declarations themselves. The record above binds a
# declaration to the upstream file it came from; this binds the other
# direction. Without it, editing a committed declaration — dropping a package
# the pinned code needs — leaves every upstream digest valid and the suite
# green, because nothing in the repository ever hashed the derived file.
#
# Unlike the upstream sources, these are committed here, so this check runs
# everywhere including CI rather than only where submodules are initialized.
DERIVED_DEPENDENCY_DECLARATIONS = {
    "requirements/vendor-civil-domain.txt": (
        "b6e0ca9c47ef9cd7535693a182756108acc13897d19a5a8b4eef7631f00edc3e"
    ),
    "requirements/vendor-multi-agent-kg.txt": (
        "f467a303eae3dbd6f2fe4d44d8b38a2e226f60a427fe3216a2bc40eab0492e6d"
    ),
}

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

# First-party JoeElder21 repositories pinned under repos/ so this repository
# can serve as the umbrella without merging their trees. They follow the same
# gitlink discipline as vendor/ but carry no upstream-dependency records: their
# provenance table lives in repos/README.md and they are governed by their own
# repositories, not by this one's contracts.
FIRST_PARTY_SUBMODULES = {
    "repos/elder-command-center": ("https://github.com/JoeElder21/Elder-Command-Center.git"),
    "repos/antigravity-sdk-python": ("https://github.com/JoeElder21/antigravity-sdk-python.git"),
}


def _git_available() -> bool:
    """Whether a git executable exists at all.

    Minimal containers ship without one. The probe below must not be the thing
    that crashes when the code under test explicitly supports git's absence.
    """
    return shutil.which("git") is not None


def _inside_git_worktree(root: Path = ROOT) -> bool:
    """Whether an index describing ``root`` itself is readable.

    A source archive (``git archive``) carries the tracked files but no index,
    so every index-derived assertion here is unverifiable rather than failing.

    Delegates to the scanner's own ``index_is_authoritative`` rather than
    re-probing with ``--is-inside-work-tree``. That weaker question — "is
    there a repository *above* me" — is true for an archive extracted beneath
    an unrelated checkout, and the assertions below would then run against
    that repository's index instead of skipping.
    """
    return index_is_authoritative(root)


class VendorSubmoduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.has_git_index = _git_available() and _inside_git_worktree()

    def _require_index(self) -> None:
        """Skip only the assertions that genuinely read this checkout's index.

        A class-wide skip is too blunt: it also suppressed the manifest,
        lockfile, README and Node-engine consistency checks, none of which
        need an index. In an archive that let a manifest engine of `>=1` pass
        while the suite still reported OK.
        """
        if not self.has_git_index:
            self.skipTest(
                "no Git index here (archive or no git binary); CI checkout validates this"
            )

    def test_gitmodules_declares_the_expected_upstreams(self) -> None:
        parser = configparser.ConfigParser()
        parser.read(ROOT / ".gitmodules", encoding="utf-8")
        declared = {
            parser.get(section, "path"): parser.get(section, "url") for section in parser.sections()
        }
        self.assertEqual(declared, EXPECTED_SUBMODULES | FIRST_PARTY_SUBMODULES)

    def test_every_submodule_is_a_pinned_gitlink_not_committed_content(self) -> None:
        self._require_index()
        listing = subprocess.run(
            ["git", "ls-files", "-s", "--", "vendor", "repos"],
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
        self.assertEqual(set(gitlinks), set(EXPECTED_SUBMODULES | FIRST_PARTY_SUBMODULES))
        for path, sha in gitlinks.items():
            with self.subTest(submodule=path):
                self.assertRegex(sha, r"^[0-9a-f]{40}$")

    def _index_gitlinks(self) -> dict[str, str]:
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
        return gitlinks

    def test_recorded_pins_match_the_index(self) -> None:
        """A bare gitlink advance must fail rather than desync the provenance table.

        vendor/README.md records a short SHA per submodule. Advancing the
        gitlink without updating that row — and the declared dependency and
        lockfile alongside it — would otherwise leave the repository auditing
        one commit while documenting, and installing, another.
        """
        self._require_index()
        readme = (ROOT / "vendor" / "README.md").read_text(encoding="utf-8")
        for path, sha in self._index_gitlinks().items():
            name = path.split("/")[-1]
            row = next(
                (line for line in readme.splitlines() if f"`{name}`" in line and "|" in line),
                None,
            )
            with self.subTest(submodule=path):
                self.assertIsNotNone(row, f"{name} has no provenance row in vendor/README.md")
                recorded = re.findall(r"`([0-9a-f]{7,40})`", row or "")
                self.assertTrue(recorded, f"{name} row records no pin SHA: {row}")
                self.assertTrue(
                    any(sha.startswith(candidate) for candidate in recorded),
                    f"{name} is pinned at {sha[:7]} but vendor/README.md records {recorded}",
                )

    def test_relay_gitlink_is_the_documented_release_tag(self) -> None:
        """The pin must be the tag's commit, not merely a self-consistent SHA.

        Every other assertion here compares records against each other, which
        an arbitrary commit copied into both provenance tables satisfies. This
        one binds the index to the immutable commit `v11.2.0` names, so
        advancing relay off the released tag fails even when the paperwork is
        internally consistent.
        """
        self._require_index()
        self.assertEqual(
            self._index_gitlinks()["vendor/relay"],
            RELAY_TAG_COMMIT,
            f"vendor/relay must be pinned to {RELAY_TAG} ({RELAY_TAG_COMMIT[:7]}); "
            "moving off the tag requires updating RELAY_TAG_COMMIT and every "
            "provenance record together",
        )
        # The contents row's own tag, not the tag appearing anywhere in the
        # document. `v11.2.0` occurs three times in vendor/README.md, so a
        # whole-document search passes even when this row is rewritten to
        # claim the pin came from `main` — publishing a false source-to-release
        # provenance claim while every gate stays green.
        contents_row = next(
            (
                line
                for line in (ROOT / "vendor" / "README.md").read_text(encoding="utf-8").splitlines()
                if "`relay`" in line and RELAY_TAG_COMMIT[:7] in line
            ),
            None,
        )
        self.assertIsNotNone(
            contents_row,
            f"vendor/README.md has no relay contents row recording {RELAY_TAG_COMMIT[:7]}",
        )
        recorded_tag = re.search(r"tag `([^`]+)`", contents_row or "")
        self.assertIsNotNone(recorded_tag, f"relay contents row records no tag: {contents_row}")
        self.assertEqual(
            recorded_tag.group(1),
            RELAY_TAG,
            f"relay contents row claims tag {recorded_tag.group(1)!r}, pinned to {RELAY_TAG}",
        )

    def test_upstream_dependency_sources_are_unchanged(self) -> None:
        """Declarations under requirements/ are derived from upstream files.

        Binding the gitlink alone is not enough: advancing a vendored repo
        whose own requirements changed leaves the derived declaration stale
        while every SHA still agrees. Hashing the upstream source makes that
        drift fail, forcing a re-derivation.

        Skipped when submodules are not checked out — CI does not fetch them.
        """
        for submodule, (relative, expected) in UPSTREAM_DEPENDENCY_SOURCES.items():
            source = ROOT / submodule / relative
            with self.subTest(submodule=submodule):
                if not source.exists():
                    self.skipTest(f"{submodule} not checked out; run git submodule update --init")
                digest = hashlib.sha256(source.read_bytes()).hexdigest()
                self.assertEqual(
                    digest,
                    expected,
                    f"{submodule}/{relative} changed upstream — re-derive the declaration "
                    "in requirements/ and update the recorded hash together",
                )

    def test_derived_dependency_declarations_are_unchanged(self) -> None:
        """The committed declarations are bound too, not only their sources.

        Hashing upstream catches drift in one direction: the source moving out
        from under a stale declaration. Editing the declaration itself —
        dropping a package the pinned code needs — leaves every upstream
        digest valid, so nothing failed. These files are committed here, so
        unlike the upstream sources this runs in CI as well.
        """
        for relative, expected in DERIVED_DEPENDENCY_DECLARATIONS.items():
            declaration = ROOT / relative
            with self.subTest(declaration=relative):
                self.assertTrue(declaration.exists(), f"missing {relative}")
                digest = hashlib.sha256(declaration.read_bytes()).hexdigest()
                self.assertEqual(
                    digest,
                    expected,
                    f"{relative} was edited — confirm it still matches the upstream "
                    "source it is derived from, then update the recorded hash",
                )

    def test_every_relay_provenance_record_agrees(self) -> None:
        """All five records that describe the relay pin must move together.

        Upgrading relay touches the gitlink, the manifest, the lockfile, and
        two provenance tables. Asserting only a subset lets a partial upgrade
        pass, leaving the documented install resolving one version while the
        repository claims to audit another.
        """
        connector = ROOT / "connectors" / "relay"
        manifest = json.loads((connector / "package.json").read_text(encoding="utf-8"))
        spec = manifest["dependencies"]["agent-relay"]
        version = spec.lstrip("^~>=< ")

        lock = json.loads((connector / "package-lock.json").read_text(encoding="utf-8"))
        self.assertEqual(
            lock["packages"][""]["dependencies"]["agent-relay"],
            spec,
            "lockfile root dependency spec has drifted from package.json",
        )
        self.assertEqual(
            lock["packages"]["node_modules/agent-relay"]["version"],
            version,
            f"lockfile resolves a different agent-relay than the declared {version}",
        )

        # The *declared dependencies* row, not merely the first row mentioning
        # relay. The contents table comes first and carries the release tag,
        # which already contains the version — so matching on `relay` alone
        # asserted against the wrong row and let a stale `agent-relay@^11.2.0`
        # declaration survive a coordinated upgrade.
        vendor_row = next(
            (
                line
                for line in (ROOT / "vendor" / "README.md").read_text(encoding="utf-8").splitlines()
                if "`relay`" in line and "agent-relay@" in line
            ),
            None,
        )
        self.assertIsNotNone(
            vendor_row,
            "vendor/README.md has no relay row declaring an agent-relay dependency",
        )
        # The complete spec, operator included. Capturing from the first digit
        # normalizes `agent-relay@11.2.0` and `agent-relay@>=11.2.0` to the
        # same bare `11.2.0` as `^11.2.0`, so a row declaring materially
        # different install semantics passes as agreement.
        declared_in_vendor_row = re.search(r"agent-relay@([^\s`|]+)", vendor_row or "")
        self.assertIsNotNone(
            declared_in_vendor_row,
            f"no agent-relay spec in the vendor row: {vendor_row}",
        )
        self.assertEqual(
            declared_in_vendor_row.group(1),
            spec,
            f"vendor/README.md declares agent-relay@{declared_in_vendor_row.group(1)}, "
            f"manifest declares {spec}",
        )

        # The connector's own provenance table must carry both the version and
        # the pinned commit, tying it to the gitlink the index records.
        #
        # Parsed per row, not searched document-wide. A whole-document search
        # passes as soon as the new version appears anywhere — so bumping the
        # "Vendored at" row to tag v12.0.0 would satisfy it while
        # "Declared version" still read ^11.2.0, which is exactly the desync
        # this test exists to catch.
        connector_readme = (connector / "README.md").read_text(encoding="utf-8")
        rows = {}
        for line in connector_readme.splitlines():
            cells = [cell.strip() for cell in line.split("|") if cell.strip()]
            if len(cells) == 2:
                rows[cells[0]] = cells[1]

        self.assertIn("Declared version", rows, "connector README has no Declared version row")
        # Exact comparison against the manifest spec, not a substring search:
        # `version` is the bare number, so `in` also accepts `^111.2.0` and
        # `^11.2.0 || ^12.0.0` — ranges that install something the pinned
        # source does not correspond to.
        self.assertEqual(
            rows["Declared version"].strip("`"),
            spec,
            f"Declared version row reads {rows['Declared version']!r}, expected {spec!r}",
        )

        self.assertIn("Vendored at", rows, "connector README has no Vendored at row")
        # The tag token, compared exactly — `RELAY_TAG in cell` also accepts
        # `v11.2.0-rc1` and `not-v11.2.0`, either of which would be a false
        # source-tag claim that every gate waved through.
        connector_tag = re.search(r"tag `([^`]+)`", rows["Vendored at"])
        self.assertIsNotNone(
            connector_tag, f"Vendored at row records no tag: {rows['Vendored at']}"
        )
        self.assertEqual(
            connector_tag.group(1),
            RELAY_TAG,
            f"Vendored at row claims tag {connector_tag.group(1)!r}, pinned to {RELAY_TAG}",
        )
        # Only this last comparison needs the index. Guarding the whole test on
        # it would take the manifest, lockfile, README and Node-engine checks
        # down with it in an archive — the very over-skip this addresses.
        if self.has_git_index:
            relay_sha = self._index_gitlinks()["vendor/relay"]
            recorded = re.findall(r"`([0-9a-f]{7,40})`", rows["Vendored at"])
            self.assertTrue(
                any(relay_sha.startswith(candidate) for candidate in recorded),
                f"vendor/relay is pinned at {relay_sha[:7]}, "
                f"but the Vendored at row records {recorded}",
            )

        # The Node floor must cover the whole locked tree, not just
        # agent-relay's own declaration — npm downgrades engine mismatches to
        # warnings, so an understated floor installs and fails at runtime.
        #
        # Every `>=` bound is scanned, including those inside compound ranges
        # such as posthog-node's `^20.20.0 || >=22.22.0`. An earlier version of
        # this test matched only bare `>=x.y.z` strings and silently ignored
        # those, which is exactly how the floor came to be understated.
        # agent-relay itself requires Node 22+, so the 22.x branch of every
        # compound range is the one that binds here.
        bounds = set()
        for entry in lock["packages"].values():
            if not isinstance(entry, dict):
                continue
            declared_range = (entry.get("engines") or {}).get("node")
            if not declared_range:
                continue
            for match in re.finditer(r">=\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?", declared_range):
                major = int(match.group(1))
                if major >= 22:
                    bounds.add((major, int(match.group(2) or 0), int(match.group(3) or 0)))

        self.assertTrue(bounds, "no Node 22+ bound found in the locked tree")
        major, minor, patch = max(bounds)
        highest = f">={major}.{minor}.{patch}"
        self.assertEqual(
            manifest["engines"]["node"],
            highest,
            f"locked tree requires Node {highest}, manifest declares {manifest['engines']['node']}",
        )

    def test_no_upstream_file_content_is_tracked_in_this_repository(self) -> None:
        self._require_index()
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
    @classmethod
    def setUpClass(cls) -> None:
        cls.has_git_index = _git_available() and _inside_git_worktree()

    def test_submodule_paths_are_read_from_gitmodules(self) -> None:
        self.assertEqual(
            submodule_paths(ROOT), frozenset(EXPECTED_SUBMODULES | FIRST_PARTY_SUBMODULES)
        )

    def test_declared_and_index_proven_submodules_agree(self) -> None:
        """`.gitmodules` declares; the index proves. Drift between them is a bug.

        Scans gate on the index-proven set, so a `.gitmodules` entry with no
        matching gitlink would be inert rather than loud. This makes it loud.
        """
        if not self.has_git_index:
            self.skipTest("no Git index here (source archive); CI checkout validates this gate")
        self.assertEqual(submodule_paths(ROOT), gitlink_paths(ROOT))

    def test_scans_gate_on_index_proven_gitlinks_not_declarations(self) -> None:
        if not _git_available():
            self.skipTest("no git binary; this fixture builds a real repository")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def run(*args: str) -> None:
                subprocess.run(args, cwd=root, check=True, capture_output=True)

            run("git", "init", "-q", ".")
            run("git", "config", "user.email", "privacy-guard-fixture")
            run("git", "config", "user.name", "privacy-guard-fixture")
            (root / ".gitmodules").write_text(
                '[submodule "config"]\n\tpath = config\n\turl = https://example.invalid/x.git\n',
                encoding="utf-8",
            )
            (root / "config").mkdir()
            (root / "config" / "settings.toml").write_text("k = 'v'\n", encoding="utf-8")
            run("git", "add", "-A")
            run("git", "commit", "-qm", "fixture")

            # Declared but not proven: no gitlink exists, so nothing is excluded.
            self.assertEqual(submodule_paths(root), frozenset({"config"}))
            self.assertEqual(gitlink_paths(root), frozenset())
            self.assertFalse(is_vendored(root / "config" / "settings.toml", root))

    def test_gitlink_paths_are_scanned_for_private_data_patterns(self) -> None:
        """A submodule's path is published text and gets the full pattern set.

        The filename and suffix rules only catch exact matches, so a gitlink
        named after a client — carrying an email address, a phone number, an
        address — passes them all. Its contents are excluded from the content
        scan by design, and with no `.gitmodules` entry to catch the name
        incidentally, nothing else in the scan ever reads it.
        """
        if not _git_available():
            self.skipTest("no git binary; this fixture builds a real repository")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def run(*args: str, cwd: Path = root) -> None:
                subprocess.run(args, cwd=cwd, check=True, capture_output=True)

            inner = root / "inner"
            inner.mkdir()
            run("git", "init", "-q", ".", cwd=inner)
            run("git", "config", "user.email", "gitlink-fixture", cwd=inner)
            run("git", "config", "user.name", "gitlink-fixture", cwd=inner)
            (inner / "a.txt").write_text("hi\n", encoding="utf-8")
            run("git", "add", "a.txt", cwd=inner)
            run("git", "commit", "-qm", "inner", cwd=inner)
            sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=inner,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

            run("git", "init", "-q", ".")
            run("git", "config", "user.email", "gitlink-fixture")
            run("git", "config", "user.name", "gitlink-fixture")
            # A gitlink recorded directly in the index, with no .gitmodules
            # entry — the case where the path is the only published record.
            # Assembled at runtime: as a literal this fixture would trip the
            # scanner it exercises when the guard walks this file, failing the
            # repository's own privacy gate.
            private = "clients-jane.doe" + "@" + "acmecorp" + ".invalid"
            run(
                "git",
                "update-index",
                "--add",
                "--cacheinfo",
                f"160000,{sha},{private}",
            )
            run("git", "commit", "-qm", "fixture")

            self.assertEqual(gitlink_paths(root), frozenset({private}))
            findings = scan_repository(root)
            self.assertTrue(
                any("possible email address" in finding for finding in findings),
                f"a gitlink path publishing an email scanned clean: {findings}",
            )

    def test_upstream_files_are_excluded_from_the_privacy_contract(self) -> None:
        if not self.has_git_index:
            self.skipTest("no Git index here (source archive); CI checkout validates this gate")
        for submodule in EXPECTED_SUBMODULES | FIRST_PARTY_SUBMODULES:
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

    def test_scanners_degrade_rather_than_crash_without_a_git_binary(self) -> None:
        """No git installed must mean "nothing provable", not a crash.

        subprocess.run raises FileNotFoundError when the binary is absent,
        regardless of check=False, so a caller inspecting only returncode still
        dies. These scanners run in minimal containers and extracted archives.

        The fallback is deliberately fail-closed: with no index to consult,
        nothing can be proven vendored, so everything is scanned. `.gitmodules`
        is not consulted as a substitute — a stale entry there must never
        exclude a first-party file from a privacy scan.
        """
        import scripts.privacy_guard as guard

        original = guard.subprocess.run

        def no_git(args, *rest, **kwargs):
            if args and args[0] == "git":
                raise FileNotFoundError(2, "No such file or directory: 'git'")
            return original(args, *rest, **kwargs)

        guard.subprocess.run = no_git
        try:
            self.assertEqual(gitlink_paths(ROOT), frozenset())
            self.assertFalse(is_vendored(ROOT / "vendor" / "relay" / "README.md", ROOT))
            # Falls back to the filesystem walk instead of raising.
            self.assertTrue(repository_files(ROOT))
        finally:
            guard.subprocess.run = original


@unittest.skipUnless(_git_available(), "no git binary; these fixtures build real repositories")
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

    def test_symlink_target_string_is_scanned_not_the_file_it_resolves_to(self) -> None:
        """Git publishes a symlink's target string, not the bytes it points at.

        A link named innocuously, resolving to a perfectly benign existing
        file, still publishes its target path — which can carry a client name,
        an address, or a private directory layout. Reading through the link
        scans the wrong content entirely and reports nothing.
        """
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            # Assembled from fragments: this repository's own privacy guard
            # scans this file, and an address-shaped literal would be a finding.
            private_dir = base / ("clients-" + "jane.doe" + "@" + "acmecorp.com")
            private_dir.mkdir(parents=True)
            benign = private_dir / "notes.md"
            benign.write_text("nothing sensitive in this file\n", encoding="utf-8")

            root = base / "repo"
            root.mkdir()

            def run(*args: str) -> None:
                subprocess.run(args, cwd=root, check=True, capture_output=True)

            run("git", "init", "-q", ".")
            run("git", "config", "user.email", "privacy-guard-fixture")
            run("git", "config", "user.name", "privacy-guard-fixture")
            (root / "reference.md").symlink_to(benign)
            run("git", "add", "-A")
            run("git", "commit", "-qm", "fixture")

            self.assertTrue((root / "reference.md").exists(), "fixture link should resolve")
            findings = scan_repository(root)
            self.assertTrue(
                any("email address" in finding for finding in findings),
                f"symlink target string was not scanned: {findings}",
            )

    def test_prohibited_filename_behind_a_dangling_symlink_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo_with_dangling_symlink(directory)
            findings = scan_repository(root)
            self.assertTrue(
                any("prohibited private filename" in finding for finding in findings),
                f"dangling symlink escaped the scan: {findings}",
            )


@unittest.skipUnless(_git_available(), "no git binary; these fixtures build real repositories")
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


@unittest.skipUnless(_git_available(), "no git binary")
class ForeignIndexScanTests(unittest.TestCase):
    """An ancestor repository's index must never be treated as ours.

    `git rev-parse --is-inside-work-tree` answers "is there a repository
    above me", so a source archive extracted anywhere beneath an unrelated
    checkout answers yes and then reports on that checkout's index — under
    which none of the archive's files are tracked. Every exclusion built on
    the index then fires on every path: the privacy scan opens nothing and
    passes, and the TOML verifier checks nothing and reports valid.
    """

    def _archive_under_foreign_repo(self, directory: str) -> Path:
        outer = Path(directory) / "outer"
        outer.mkdir()

        def run(*args: str, cwd: Path) -> None:
            subprocess.run(args, cwd=cwd, check=True, capture_output=True)

        run("git", "init", "-q", ".", cwd=outer)
        run("git", "config", "user.email", "foreign-index-fixture", cwd=outer)
        run("git", "config", "user.name", "foreign-index-fixture", cwd=outer)
        (outer / "unrelated.txt").write_text("unrelated\n", encoding="utf-8")
        run("git", "add", "unrelated.txt", cwd=outer)
        run("git", "commit", "-qm", "outer", cwd=outer)

        # The extracted tree is a plain directory: no .git of its own, and
        # untracked as far as the outer repository is concerned.
        extracted = outer / "extracted"
        extracted.mkdir()
        return extracted

    def test_privacy_scan_does_not_trust_an_ancestor_repositorys_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            extracted = self._archive_under_foreign_repo(directory)
            # Assembled at runtime: written as a literal, this fixture would
            # trip the very scanner it exercises when the guard walks this
            # file, failing the repository's own privacy gate.
            planted = "contact: someone@" + "example" + ".invalid\n"
            (extracted / "leaked.md").write_text(planted, encoding="utf-8")

            self.assertIsNone(
                tracked_paths(extracted),
                "an ancestor repository's index was reported as this tree's",
            )
            scanned = {str(path.relative_to(extracted)) for path in repository_files(extracted)}
            self.assertIn(
                "leaked.md",
                scanned,
                "the scan walked nothing: the outer index tracks none of these files",
            )
            findings = scan_repository(extracted)
            self.assertTrue(
                any("possible email address" in finding for finding in findings),
                f"privacy scan passed a tree it never opened: {findings}",
            )

    def test_toml_verifier_does_not_trust_an_ancestor_repositorys_index(self) -> None:
        sys.path.insert(0, str(ROOT))
        try:
            from scripts import verify_runtime_stack
        finally:
            sys.path.pop(0)

        with tempfile.TemporaryDirectory() as directory:
            extracted = self._archive_under_foreign_repo(directory)
            broken = extracted / "node_modules" / "broken.toml"
            broken.parent.mkdir()
            broken.write_text("this is not valid toml\n", encoding="utf-8")

            original = verify_runtime_stack.ROOT
            verify_runtime_stack.ROOT = extracted
            try:
                _checked, errors = verify_runtime_stack.enforce_toml()
            finally:
                verify_runtime_stack.ROOT = original

        self.assertTrue(
            any("broken.toml" in error for error in errors),
            f"archive-owned TOML was skipped as installed content: {errors}",
        )


if __name__ == "__main__":
    unittest.main()
