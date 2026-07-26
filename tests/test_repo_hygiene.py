"""The repository-engineering substrate must not silently regress.

Record: docs/REPO_OPTIMIZATION_2026-07-25.md. These tests assert the gates
themselves exist and stay wired up, so a later change cannot quietly drop a CI
step, unpin an action, or remove a boundary document.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
VALIDATE_WORKFLOW = WORKFLOW_DIR / "validate-agent.yml"
SECURITY_WORKFLOW = WORKFLOW_DIR / "security.yml"
DEPENDABOT = ROOT / ".github" / "dependabot.yml"
PRE_COMMIT = ROOT / ".pre-commit-config.yaml"
PYPROJECT = ROOT / "pyproject.toml"
OPTIMIZATION_RECORD = ROOT / "docs" / "REPO_OPTIMIZATION_2026-07-25.md"


def _npm_lockfiles() -> list[str]:
    """Every committed npm lock, as a repo-relative POSIX path.

    Derived from the tree rather than listed, because a list is what let the
    relay connector's lock go unscanned. `node_modules` is excluded: those locks
    belong to dependencies, are not committed, and are covered transitively by
    the top-level lock that resolved them.
    """
    return [
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("package-lock.json")
        if "node_modules" not in path.parts and ".git" not in path.parts
    ]


# `uses: owner/repo@ref` — captures the ref so it can be checked for a SHA pin.
USES_PATTERN = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", re.MULTILINE)
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


class WorkflowSecurityTests(unittest.TestCase):
    """CI is the one place here that runs third-party code with repository tokens."""

    def _workflow_files(self) -> list[Path]:
        return sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml"))

    def test_every_action_is_pinned_to_a_full_commit_sha(self):
        # A floating tag is mutable: whoever controls the tag controls what runs.
        # This is the class of failure behind the March 2026 trivy-action incident.
        for path in self._workflow_files():
            text = path.read_text(encoding="utf-8")
            for reference in USES_PATTERN.findall(text):
                if "@" not in reference:
                    self.fail(f"{path.name}: unversioned action reference {reference!r}")
                _, _, ref = reference.rpartition("@")
                with self.subTest(workflow=path.name, action=reference):
                    self.assertRegex(
                        ref,
                        FULL_SHA,
                        f"{path.name}: {reference!r} must be pinned to a full commit SHA "
                        "with the version in a trailing comment",
                    )

    def test_checkout_never_persists_credentials(self):
        for path in self._workflow_files():
            text = path.read_text(encoding="utf-8")
            if "actions/checkout@" not in text:
                continue
            with self.subTest(workflow=path.name):
                self.assertIn(
                    "persist-credentials: false",
                    text,
                    f"{path.name}: checkout leaves a usable token in the runner by default",
                )

    def test_workflows_declare_explicit_permissions(self):
        # The security property is that a workflow *states* its permissions
        # rather than inheriting the repository default, which is broad.
        #
        # This deliberately does not require `contents: read` everywhere. An
        # earlier version did, and it failed a workflow that legitimately needs
        # `contents: write` to push a fix — a test asserting "no workflow may
        # ever write" would be wrong about what least privilege means. Least
        # privilege is the minimum a job needs, declared on purpose; it is not
        # read-only for everything.
        for path in self._workflow_files():
            text = path.read_text(encoding="utf-8")
            with self.subTest(workflow=path.name):
                self.assertIn(
                    "permissions:",
                    text,
                    f"{path.name}: declares no permissions block, so it inherits the "
                    "repository default token scope",
                )

    def test_security_workflow_audits_the_workflows_themselves(self):
        text = SECURITY_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("zizmorcore/zizmor-action@", text)
        self.assertIn("schedule:", text, "audit rules must reach a quiet repository too")

    def test_pinned_dependencies_are_scanned_for_known_vulnerabilities(self):
        # Disclosures land against unchanged pins, so a dependency set that was
        # clean at merge does not stay clean. Only a scheduled scan notices.
        text = SECURITY_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("osv-scanner-action@", text)
        for lockfile in (
            "requirements/lock-2026-07-24.txt",
            "connectors/aps/package-lock.json",
        ):
            with self.subTest(lockfile=lockfile):
                self.assertIn(lockfile, text)

    def test_every_npm_lockfile_in_the_tree_is_scanned(self):
        # The hand-written list above named the APS lock and the relay lock was
        # committed later, so a second npm dependency tree sat outside the
        # vulnerability gate while the job read as complete coverage. Deriving
        # the set from the tree means the next connector added either appears in
        # the scan or fails here; enumerating it by hand means the next one
        # repeats this.
        text = SECURITY_WORKFLOW.read_text(encoding="utf-8")
        locks = sorted(_npm_lockfiles())
        self.assertTrue(locks, "no package-lock.json found; this test would be vacuous")
        for lockfile in locks:
            with self.subTest(lockfile=lockfile):
                self.assertIn(lockfile, text)

    def test_every_npm_lockfile_in_the_tree_gets_update_pull_requests(self):
        # The same omission on the update side. A scanned-but-unupdated lock
        # reports vulnerabilities nothing moves off, and an updated-but-unscanned
        # one moves without anyone knowing why it needed to.
        text = DEPENDABOT.read_text(encoding="utf-8")
        for lockfile in sorted(_npm_lockfiles()):
            directory = "/" + str(Path(lockfile).parent)
            with self.subTest(directory=directory):
                self.assertIn(f"directory: {directory}", text)


class ValidationCoverageTests(unittest.TestCase):
    """Every checker the repository ships must actually run somewhere in CI."""

    def test_all_house_checkers_run_in_ci(self):
        text = VALIDATE_WORKFLOW.read_text(encoding="utf-8")
        for checker in [
            "scripts/privacy_guard.py",
            "scripts/validate_specialist_corps.py",
            "scripts/verify_runtime_stack.py",
            "scripts/verify_mcp_mounts.py",
            "unittest discover -s tests",
        ]:
            with self.subTest(checker=checker):
                self.assertIn(checker, text)

    def test_python_is_linted_in_ci(self):
        text = VALIDATE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("ruff check", text)

    def test_node_connector_is_exercised_in_ci(self):
        # connectors/aps ships a lockfile and real dependencies; an untested tree
        # is where dependency drift hides.
        text = VALIDATE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("connectors/aps", text)
        self.assertIn("npm ci", text)

    def test_ruff_config_is_declared(self):
        text = PYPROJECT.read_text(encoding="utf-8")
        self.assertIn("[tool.ruff]", text)
        self.assertIn("[tool.ruff.lint]", text)

    def test_dependabot_covers_every_dependency_ecosystem(self):
        text = DEPENDABOT.read_text(encoding="utf-8")
        for ecosystem in ["pip", "npm", "github-actions"]:
            with self.subTest(ecosystem=ecosystem):
                self.assertIn(f"package-ecosystem: {ecosystem}", text)

    def test_every_dependabot_ecosystem_has_a_cooldown(self):
        # A compromised release is usually caught and yanked within days, so
        # adopting a brand-new version immediately is the one way an automated
        # update bot makes supply-chain risk worse instead of better.
        text = DEPENDABOT.read_text(encoding="utf-8")
        ecosystems = text.count("package-ecosystem:")
        self.assertEqual(
            text.count("cooldown:"),
            ecosystems,
            "every package-ecosystem entry needs its own cooldown block",
        )
        self.assertEqual(text.count("default-days:"), ecosystems)


class GitleaksSuppressionTests(unittest.TestCase):
    """A line-pinned exemption drifts whenever the file above it changes.

    Working-tree fingerprints carry a CURRENT line number, so an entry stops
    matching the moment anything above that line grows or shrinks -- even when
    the excused line itself is untouched. Editing `scripts/privacy_guard.py`
    shifted its fixture by 32 lines and turned CI's `gitleaks dir` scan red,
    while the history scan stayed green and the local pre-commit hook passed:
    that hook scans the STAGED DIFF, and CI scans the whole tree, so local green
    never predicted it.

    This cannot prove an entry is right -- only gitleaks can, and it is not a
    dependency of this suite. It proves the weaker thing that catches the
    failure which actually happens: an entry must sit on a line that could
    plausibly produce the rule it names. After the drift above, the stale entry
    pointed at a bare `),`.
    """

    IGNORE_FILE = ROOT / ".gitleaksignore"
    # What each rule keys on, lowercased. Deliberately generous: a false PASS
    # here costs a CI round, while a false FAIL blocks a legitimate edit on a
    # keyword list nobody can complete from memory.
    RULE_MARKERS = {
        "generic-api-key": ("key", "secret", "token", "password", "passwd", "credential"),
        "stripe-access-token": ("sk_", "pk_", "rk_", "stripe"),
    }

    def _working_tree_entries(self):
        """`path:rule:line` entries only — the history form carries a commit."""
        entries = []
        for raw in self.IGNORE_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(":")
            # History entries are `commit:path:rule:line`; a 40-char hex first
            # field is what distinguishes them. Those pin a line as it was in
            # that commit, which no present-day file can be checked against.
            if len(parts) == 4 and FULL_SHA.match(parts[0]):
                continue
            self.assertEqual(len(parts), 3, f"unparseable .gitleaksignore entry: {line!r}")
            entries.append((parts[0], parts[1], int(parts[2])))
        return entries

    def test_every_suppressed_line_still_exists(self):
        entries = self._working_tree_entries()
        self.assertTrue(entries, "no working-tree entries; this test would be vacuous")
        for path, rule, number in entries:
            with self.subTest(entry=f"{path}:{rule}:{number}"):
                target = ROOT / path
                self.assertTrue(target.exists(), f"{path} no longer exists")
                lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
                self.assertGreaterEqual(
                    len(lines),
                    number,
                    f"{path} has {len(lines)} lines but the entry cites {number}",
                )

    def test_every_suppressed_line_could_produce_the_rule_it_names(self):
        for path, rule, number in self._working_tree_entries():
            with self.subTest(entry=f"{path}:{rule}:{number}"):
                markers = self.RULE_MARKERS.get(rule)
                self.assertIsNotNone(
                    markers,
                    f"{rule} has no marker list; add one rather than letting an "
                    "unrecognised rule pass unchecked",
                )
                text = (
                    (ROOT / path)
                    .read_text(encoding="utf-8", errors="replace")
                    .splitlines()[number - 1]
                    .lower()
                )
                self.assertTrue(
                    any(marker in text for marker in markers),
                    f"{path}:{number} holds {text.strip()[:60]!r}, which cannot produce a "
                    f"{rule} finding -- the exemption has drifted off the line it was "
                    "written for and the tree scan will report that line unsuppressed",
                )

    def test_the_drift_detector_detects(self):
        # Without this, both tests above pass on any input including the drift
        # they exist for. The real stale entry pointed at a bare `),`.
        markers = self.RULE_MARKERS["generic-api-key"]
        self.assertFalse(any(m in "    )," for m in markers))
        self.assertTrue(any(m in '"client_secret": "pi_123"'.lower() for m in markers))

    def test_history_entries_are_not_silently_skipped(self):
        # The parser drops commit-prefixed entries because no present-day file
        # can be checked against them. If a typo turned every entry into that
        # shape, both tests above would pass while checking nothing.
        raw = [
            line.strip()
            for line in self.IGNORE_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        self.assertEqual(
            len(raw),
            len(self._working_tree_entries())
            + sum(1 for line in raw if FULL_SHA.match(line.split(":")[0])),
            "an entry is neither working-tree nor history shaped",
        )


class VulnerabilityTriageTests(unittest.TestCase):
    """A triage entry must stay a decision, not become a silence.

    `osv-scanner.toml` says of itself that `ignoreUntil` "is the point. These
    expire and come back, so a triage decision cannot quietly become permanent
    by being forgotten." Nothing asserted that. An entry with no expiry, or one
    dated far enough out to outlive anyone's memory of it, reads exactly like
    the acknowledged findings around it — and the file's own claim about itself
    is the kind of prose that stops being true without anything failing.
    """

    TRIAGE = ROOT / "osv-scanner.toml"
    # A year is not a triage, it is a deletion with extra steps. Every entry
    # here today sits at one month.
    MAX_WINDOW_DAYS = 120

    def _entries(self):
        import tomllib

        with self.TRIAGE.open("rb") as handle:
            return tomllib.load(handle).get("IgnoredVulns", [])

    def test_every_ignored_vulnerability_states_a_reason_and_an_expiry(self):
        entries = self._entries()
        self.assertTrue(entries, "no triage entries; this test would be vacuous")
        for entry in entries:
            with self.subTest(vuln=entry.get("id")):
                self.assertTrue(entry.get("id"), "an entry with no id ignores nothing")
                self.assertIn("ignoreUntil", entry, "an exemption with no expiry is permanent")
                reason = entry.get("reason", "")
                # Length is a crude proxy and deliberately low. It cannot judge
                # whether a reason is GOOD; it only refuses "n/a" and "known
                # issue", which is the failure mode that actually occurs.
                self.assertGreater(
                    len(reason.split()),
                    12,
                    f"{entry.get('id')}: a triage needs a reason someone can re-evaluate",
                )

    def test_no_exemption_outlives_the_memory_of_the_decision(self):
        import datetime

        for entry in self._entries():
            expiry = entry["ignoreUntil"]
            if isinstance(expiry, datetime.datetime):
                expiry = expiry.date()
            with self.subTest(vuln=entry["id"]):
                self.assertIsInstance(
                    expiry, datetime.date, "ignoreUntil must be a TOML date, not a string"
                )
                # Measured from the file's own newest entry rather than from
                # today. Anchoring on `date.today()` would make this test start
                # failing on a fixed calendar day for reasons unrelated to any
                # change -- a time bomb in CI rather than a check. The property
                # under test is the WINDOW an author granted, which is a
                # property of the file.
                newest = max(
                    e["ignoreUntil"].date()
                    if isinstance(e["ignoreUntil"], datetime.datetime)
                    else e["ignoreUntil"]
                    for e in self._entries()
                )
                self.assertLessEqual(
                    (newest - expiry).days,
                    self.MAX_WINDOW_DAYS,
                    f"{entry['id']}: expires {(newest - expiry).days} days before the "
                    "newest entry, which suggests a stale exemption nobody revisited",
                )

    def test_the_reasons_do_not_claim_a_fix_that_was_not_applied(self):
        # The relay entries say the patched versions are "in range" and blocked
        # by a published shrinkwrap. That is a checkable claim, and if a future
        # edit drops the blocker while keeping the exemption, the entry becomes
        # a fixable finding sitting behind a stale excuse.
        for entry in self._entries():
            reason = entry.get("reason", "").lower()
            if "fixed in" not in reason:
                continue
            with self.subTest(vuln=entry["id"]):
                self.assertTrue(
                    any(
                        blocker in reason
                        for blocker in (
                            "shrinkwrap",
                            "out of range",
                            "outside it",
                            "dated evidence record",
                            "no fix available",
                            "semver-major",
                        )
                    ),
                    f"{entry['id']}: names a fixed version but no reason it was not taken",
                )


class WorkflowYamlShapeTests(unittest.TestCase):
    """Two ways a YAML edit passes review and changes nothing, or everything.

    Both were live for minutes while the relay lockfile was added to the OSV
    scan. Neither is caught by anything else here: a workflow that parses is not
    a workflow that says what its author read.

    Hand-rolled rather than parsed. PyYAML is in no live requirements manifest,
    and `skipUnless(yaml)` is the silent-degradation pattern this repository
    spent a round removing -- a test that skips itself reports the same green as
    one that passed. See `test_scan_applicability_is_its_own_required_question`
    for the same decision.
    """

    def _yaml_files(self) -> list[Path]:
        return [
            *sorted(WORKFLOW_DIR.glob("*.yml")),
            *sorted(WORKFLOW_DIR.glob("*.yaml")),
            DEPENDABOT,
        ]

    # Block scalars whose CONTENT is a language with its own comment syntax. A
    # `#` line in `run: |` is a shell comment and entirely correct; the same line
    # in `scan-args: |-` is argv. The first version of this detector did not
    # distinguish them and flagged every commented step script in the repository
    # -- a check that fires on correct code gets suppressed, and then it is not a
    # check.
    _SCRIPT_KEYS = frozenset({"run", "script"})

    @classmethod
    def _block_scalar_comment_lines(cls, text: str) -> list[tuple[int, str]]:
        """Lines inside a data `|`/`>` block that LOOK like comments and are not.

        A block scalar has no comment syntax of its own, so an indented `#` line
        is literal content. `scan-args: |-` followed by an explanatory `#` note
        passed eight comment lines to osv-scanner as arguments -- the workflow
        still parsed, the step still ran, and the tool exited on an unknown flag.
        """
        offenders: list[tuple[int, str]] = []
        in_script = False
        block_indent: int | None = None
        for number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if block_indent is not None:
                indent = len(line) - len(line.lstrip())
                if stripped and indent <= block_indent:
                    block_indent = None  # the block ended; fall through
                elif stripped.startswith("#") and not in_script:
                    offenders.append((number, stripped))
                    continue
                else:
                    continue
            if not stripped or stripped.startswith("#"):
                continue
            head = stripped.split("#", 1)[0].rstrip()
            if ": " in head or head.endswith(":"):
                key = head.split(":", 1)[0].strip().removeprefix("- ").strip()
                value = head.split(":", 1)[1].strip()
                if value and value[0] in "|>":
                    block_indent = len(line) - len(line.lstrip())
                    in_script = key in cls._SCRIPT_KEYS
        return offenders

    @staticmethod
    def _duplicate_sibling_keys(text: str) -> list[tuple[int, str]]:
        """Keys repeated among siblings, where the later one silently wins.

        Editing one occurrence of `scan-args:` and leaving another produced a
        file that parsed, validated, and dropped the edit. A duplicate key is
        never intentional in these files.
        """
        offenders: list[tuple[int, str]] = []
        seen: dict[int, set[str]] = {}
        block_indent: int | None = None
        for number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            indent = len(line) - len(line.lstrip())
            if block_indent is not None:
                if stripped and indent <= block_indent:
                    block_indent = None
                else:
                    continue
            if not stripped or stripped.startswith("#"):
                continue
            for depth in list(seen):
                if depth > indent:
                    del seen[depth]
            if stripped.startswith("- "):
                # A new sequence item opens a fresh mapping at this depth, and
                # its first key sits further right than the dash.
                for depth in list(seen):
                    if depth >= indent:
                        del seen[depth]
                stripped = stripped[2:]
                indent += 2
            head = stripped.split("#", 1)[0].rstrip()
            if ": " not in head and not head.endswith(":"):
                continue
            key = head.split(":", 1)[0].strip()
            value = head.split(":", 1)[1].strip()
            if key in seen.setdefault(indent, set()):
                offenders.append((number, key))
            seen[indent].add(key)
            if value and value[0] in "|>":
                block_indent = indent
        return offenders

    def test_no_comment_is_stranded_inside_a_block_scalar(self):
        for path in self._yaml_files():
            with self.subTest(path=path.name):
                self.assertEqual(
                    self._block_scalar_comment_lines(path.read_text(encoding="utf-8")),
                    [],
                    f"{path.name}: a `#` line inside a `|` block is an ARGUMENT, not a "
                    "comment; move the note above the key",
                )

    def test_no_key_is_silently_overwritten_by_a_sibling(self):
        for path in self._yaml_files():
            with self.subTest(path=path.name):
                self.assertEqual(
                    self._duplicate_sibling_keys(path.read_text(encoding="utf-8")),
                    [],
                    f"{path.name}: a repeated key parses and discards the earlier value",
                )

    def test_the_detectors_detect(self):
        # Without this, both tests above pass on any input, including the
        # defects they were written for -- and a scanner that finds nothing
        # reads exactly like a clean tree.
        stranded = "jobs:\n  a:\n    steps:\n      - with:\n          args: |-\n            --x\n            # note\n"
        self.assertTrue(self._block_scalar_comment_lines(stranded))
        duplicated = (
            "jobs:\n  a:\n    steps:\n      - with:\n          args: one\n          args: two\n"
        )
        self.assertTrue(self._duplicate_sibling_keys(duplicated))
        # And the reverse direction: the real files' shapes must not be flagged.
        # Two steps each carrying `args:` are siblings of DIFFERENT parents.
        distinct = (
            "jobs:\n  a:\n    steps:\n      - name: one\n        with:\n          args: |-\n"
            "            --x\n      - name: two\n        with:\n          args: |-\n            --y\n"
        )
        self.assertEqual(self._duplicate_sibling_keys(distinct), [])
        self.assertEqual(self._block_scalar_comment_lines(distinct), [])
        # A shell comment in `run: |` is correct and must not be flagged. The
        # first version of the detector reported every commented step script in
        # this repository, which is how a check earns a suppression.
        script = "jobs:\n  a:\n    steps:\n      - run: |\n          set -e\n          # explain\n          echo hi\n"
        self.assertEqual(self._block_scalar_comment_lines(script), [])


class LocalGateTests(unittest.TestCase):
    """The house gates must be runnable before a commit exists, not only after a push."""

    def test_pre_commit_runs_the_house_gates_and_secret_scanning(self):
        text = PRE_COMMIT.read_text(encoding="utf-8")
        for hook in [
            "gitleaks",
            "ruff",
            "scripts/privacy_guard.py",
            "scripts/validate_specialist_corps.py",
        ]:
            with self.subTest(hook=hook):
                self.assertIn(hook, text)


class AutomationClaimTests(unittest.TestCase):
    """A document may not claim a gate runs automatically when it does not."""

    def test_the_readme_does_not_overstate_what_pre_commit_runs(self):
        # The README listed eight commands and then said pre-commit "runs these
        # gates automatically". Two of them -- verify_runtime_stack.py and the
        # strict mount probe -- are in no hook, and the unit suite lets its JSON
        # Schema check skip when jsonschema is absent. A contributor trusting
        # the automatic path could pass locally and fail CI on a malformed
        # schema or a broken mount.
        #
        # Derived from the hook config rather than restated, so a hook removed
        # later cannot leave the claim standing.
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        hooks = PRE_COMMIT.read_text(encoding="utf-8")
        for checker in ("scripts/verify_runtime_stack.py", "scripts/verify_mcp_mounts.py"):
            if checker in hooks:
                continue  # if it is ever added as a hook, this stops applying
            with self.subTest(checker=checker):
                self.assertIn(
                    "does **not** run",
                    readme,
                    f"{checker} is in no pre-commit hook, so the README must say "
                    "which gates remain manual",
                )
        self.assertNotIn(
            "`pre-commit install` runs these gates automatically",
            readme,
            "the unqualified claim is false while two listed gates have no hook",
        )

    def test_contributing_does_not_overstate_what_pre_commit_runs(self):
        # The same claim, in the document a contributor actually follows before
        # a first commit, and it was left untouched when the README was fixed.
        # Fixing the reported instance and leaving the sibling is the shape this
        # record has now logged more times than any other; here the sibling was
        # the higher-traffic surface of the two.
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        hooks = PRE_COMMIT.read_text(encoding="utf-8")
        manual = [
            checker
            for checker in ("scripts/verify_runtime_stack.py", "scripts/verify_mcp_mounts.py")
            if checker not in hooks
        ]
        if not manual:
            return  # every gate is hooked; the caveat is no longer required
        for checker in manual:
            with self.subTest(checker=checker):
                self.assertIn(
                    Path(checker).name,
                    contributing,
                    f"{checker} has no hook, so CONTRIBUTING must name it as manual",
                )
        for overstatement in (
            "installs **all** of the gates",
            "installs **every** gate",
            "installs all of the gates",
        ):
            with self.subTest(claim=overstatement):
                self.assertNotIn(
                    overstatement,
                    contributing,
                    "a contributor trusting full parity passes locally and fails CI",
                )


class RollbackCompletenessTests(unittest.TestCase):
    """Every dated record's rollback must name the files its change touched.

    Scoped to the PROPERTY, not to the one document where it was found.
    `docs/EVALUATION_HARNESS.md` had its rollback corrected two rounds before
    `docs/DEPENDENCY_AUDIT_2026-07-25.md` was found with the identical defect --
    and worse, a closing sentence ("no dependency, pin, or governance rule was
    changed") contradicted by that record's own body. A test written for one
    file cannot catch the second file.
    """

    # Artefacts that make a change non-additive if the rollback ignores them.
    # A record whose body mentions one of these has, by its own account,
    # touched it -- so a rollback that never names it is incomplete.
    TRACKED = (
        "osv-scanner.toml",
        "lock-runtime-root.txt",
        "lock-runtime-contracts.txt",
        "lock-runtime-evaluation.txt",
    )

    @staticmethod
    def _split(text):
        """(body, rollback section) for a record, anchored on the HEADING.

        Matched line-anchored, not as a substring: this record's own prose
        mentions `## Rollback` inline while describing this very check, and a
        substring match treated that sentence as the start of a rollback
        section. The test then reported a document that HAS no rollback as
        having an incomplete one. Found by running it.
        """
        marker = "\n## Rollback"
        if not text.startswith("## Rollback") and marker not in text:
            return None
        start = 0 if text.startswith("## Rollback") else text.index(marker) + 1
        section = text[start:]
        if "\n## " in section[1:]:
            section = section[: section.index("\n## ", 1)]
        return text[:start], section

    def _records(self):
        found = []
        for path in sorted((ROOT / "docs").glob("*.md")):
            split = self._split(path.read_text(encoding="utf-8"))
            if split is not None:
                found.append((path, *split))
        return found

    def test_dated_records_are_being_checked(self):
        self.assertGreaterEqual(len(self._records()), 2, "no rollback sections found to check")

    def test_a_rollback_names_the_artefacts_its_record_discusses(self):
        for path, body, section in self._records():
            for artefact in self.TRACKED:
                if artefact not in body:
                    continue
                with self.subTest(record=path.name, artefact=artefact):
                    self.assertIn(
                        artefact,
                        section,
                        f"{path.name} discusses {artefact} but its rollback does not "
                        "name it, so following the rollback leaves it behind",
                    )

    def test_no_rollback_claims_nothing_changed_while_naming_a_pin(self):
        # The specific falsehood found here: a rollback asserting that no
        # dependency or pin changed, in a record whose body raises one.
        for path, body, section in self._records():
            text = body + section
            claims_nothing = "No dependency, pin, or governance rule was" in section
            with self.subTest(record=path.name):
                self.assertFalse(
                    claims_nothing and bool(re.search(r"[a-z0-9_-]+>=\d", text)),
                    f"{path.name} claims no pin changed while its body raises one",
                )


class DocumentedInstallTests(unittest.TestCase):
    """What a human is told to install must be what CI tested and OSV scanned."""

    VALIDATE = ROOT / ".github" / "workflows" / "validate-agent.yml"

    def _locked_manifests(self):
        """Manifest -> lock, derived from the drift-check job, never restated.

        The `locks` job is the authority on which manifests have a resolved
        form. Hard-coding the pairs here would let a fourth manifest be locked
        in CI and stay floating in the documentation without anything failing --
        which is the exact divergence this test exists to catch, one level up.
        """
        pairs = {}
        for line in self.VALIDATE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith("check "):
                continue
            parts = stripped.split()
            if len(parts) == 3:
                pairs[parts[1]] = parts[2]
        return pairs

    def test_the_manual_sequence_installs_every_tier_ci_installs(self):
        # CI's validate job installs the root lock AND the contracts lock before
        # running the suite; the documented sequence installed only contracts.
        # `lock-runtime-root.txt` carries autogen-agentchat, so
        # tests/test_autogen_orchestrator.py SKIPPED on a workstation following
        # the documented steps and RAN in CI -- a sequence advertised as "run
        # everything by hand" that quietly exercises fewer tests than the gate
        # it is meant to reproduce.
        #
        # Derived from the workflow, so a fourth tier added to CI setup and
        # missed in the documentation fails here rather than being discovered
        # by a contributor whose green local run goes red on push.
        installed = set(
            re.findall(
                r"pip install -r (requirements/lock-[a-z-]+\.txt)",
                self.VALIDATE.read_text(encoding="utf-8"),
            )
        )
        self.assertTrue(installed, "CI installs no locks; this test would be vacuous")
        for relative in ("CONTRIBUTING.md", "README.md"):
            # The fenced block that RUNS THE SUITE, not the whole document.
            # Searching the file passed while the sequence itself had lost the
            # root lock, because the same filename appears in a separate
            # paragraph about the AutoGen adapter -- presence somewhere in the
            # document is not presence in the steps a contributor executes.
            # Found by mutation testing; the equivalent weakness one round
            # earlier was not fixable, and this one is.
            block = self._sequence_block((ROOT / relative).read_text(encoding="utf-8"))
            self.assertIsNotNone(block, f"{relative} documents no runnable validation sequence")
            for lock in sorted(installed):
                with self.subTest(doc=relative, lock=lock):
                    self.assertIn(
                        lock,
                        block,
                        f"{relative} documents a full validation sequence that never "
                        f"installs {lock}, which CI installs before the same suite",
                    )

    @staticmethod
    def _sequence_block(text):
        """The fenced bash block that invokes the unit suite."""
        for block in re.findall(r"```bash\n(.*?)```", text, re.DOTALL):
            if "unittest discover -s tests" in block:
                return block
        return None

    def test_the_drift_check_declares_its_pairs(self):
        # Guard against the derivation silently finding nothing, which would
        # make every assertion below vacuous.
        pairs = self._locked_manifests()
        self.assertGreaterEqual(len(pairs), 3, f"expected the locked tiers, found {pairs}")

    def test_documentation_installs_the_lock_not_the_manifest(self):
        # CI installs `lock-runtime-*.txt` and osv-scanner audits those with
        # `--no-resolve`, while every documented command named the floating
        # manifest. A dependency released after the last drift run therefore
        # lands on the workstation without being the version CI tested or the
        # scanner cleared -- the aggregate and the hand-run sequence diverging
        # again, this time between CI and the documentation a human follows.
        # Markdown AND the commands programs print. `evals/run_evaluations.py`
        # printed "install requirements/runtime-evaluation.txt" to an operator
        # who had just been told the runtime was missing -- the one instruction
        # seen at the moment it is acted on, and the sweep that fixed every
        # document missed it because the sweep was scoped to `*.md`. The
        # property is "anything that tells a human what to install", not "every
        # markdown file": the file type was the incidental part.
        docs = (
            sorted(ROOT.glob("*.md"))
            + sorted(ROOT.glob("*/*.md"))
            + sorted(ROOT.glob("*/*.py"))
            + sorted(ROOT.glob("*.py"))
        )
        for manifest in self._locked_manifests():
            command = f"pip install -r {manifest}"
            for path in docs:
                if not path.is_file():
                    continue
                for number, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), start=1
                ):
                    if command in line:
                        with self.subTest(doc=path.name, line=number):
                            self.fail(
                                f"{path.relative_to(ROOT)}:{number} installs the floating "
                                f"{manifest}; CI installs and scans its lock, so this "
                                "documents an unaudited environment"
                            )


class IssueFormEnforceabilityTests(unittest.TestCase):
    """Issue forms cannot cross-validate, so each required answer must stand alone."""

    FORMS = ("agent-intake.yml", "absorption-candidate.yml")

    def _blocks(self, name):
        text = (ROOT / ".github" / "ISSUE_TEMPLATE" / name).read_text(encoding="utf-8")
        blocks = {}
        for chunk in text.split("\n  - type: "):
            for line in chunk.splitlines():
                if line.strip().startswith("id: "):
                    blocks[line.split("id: ", 1)[1].strip()] = chunk
                    break
        return blocks

    def test_no_form_splits_one_decision_across_two_required_answers(self):
        # GitHub issue forms do not cross-validate fields. The intake form had a
        # `stage` dropdown AND a separate "are the active gates complete?"
        # dropdown, so a submission could request `active` and simultaneously
        # answer "not applicable -- requesting shadow", recording an active
        # intake with no evidence. Two enforceable answers about one decision
        # enforce nothing, because they can disagree.
        blocks = self._blocks("agent-intake.yml")
        self.assertIn("stage", blocks)
        self.assertNotIn(
            "active-gates-complete",
            blocks,
            "the stage and its attestation are one decision and must be one field",
        )
        stage = blocks["stage"]
        self.assertIn("required: true", stage)
        self.assertIn("active", stage)
        self.assertIn("shadow", stage)

    def test_every_required_dropdown_option_states_an_outcome(self):
        # An option that only points at boxes elsewhere decides nothing, which
        # is how both forms ended up accepting a submission with every
        # attestation blank.
        for form, field, markers in (
            ("agent-intake.yml", "stage", ("verified", "not claimed")),
            ("absorption-candidate.yml", "agent-scan-applies", ("scanned", "not applicable")),
        ):
            with self.subTest(form=form, field=field):
                block = self._blocks(form)[field]
                options = [line for line in block.splitlines() if line.strip().startswith('- "')]
                self.assertGreaterEqual(len(options), 2)
                for option in options:
                    self.assertTrue(
                        any(marker in option.lower() for marker in markers),
                        f"{form}:{field} option decides nothing: {option.strip()}",
                    )


class AggregateShortcutTests(unittest.TestCase):
    """The advertised shortcut must cover the sequence it stands in for."""

    def test_task_validate_covers_the_documented_manual_sequence(self):
        # `task validate` is presented in CONTRIBUTING.md as the alternative to
        # running the manual sequence, so a step in that sequence and missing
        # from the shortcut means the shortcut passes while CI fails.
        #
        # This divergence has now appeared three times: the mount verifier was
        # made strict in the aggregate and left permissive by hand, then strict
        # by hand and permissive in the aggregate; and the formatter was added
        # to three documents and the `lint` task while `validate` -- the command
        # people actually run -- was missed. Derived from pyproject rather than
        # restated, so a step added to one and not the other fails here.
        validate = ""
        for line in PYPROJECT.read_text(encoding="utf-8").splitlines():
            if line.startswith("validate = "):
                validate = line
                break
        self.assertTrue(validate, "no `validate` task is defined")
        for step in (
            "privacy_guard.py",
            "validate_specialist_corps.py",
            "verify_runtime_stack.py",
            "verify_mcp_mounts.py --strict",
            "ruff check",
            "ruff format --check",
            "unittest discover -s tests",
        ):
            with self.subTest(step=step):
                self.assertIn(
                    step,
                    validate,
                    f"`task validate` is advertised as the full sequence but omits {step}",
                )


class UnwiredComponentTests(unittest.TestCase):
    """A component with no call sites may not be described as active."""

    def test_the_readme_does_not_claim_enforce_runs_before_tools(self):
        # `enforce()` appears only in its own module and its tests, so the
        # consolidated gate constrains nothing at runtime. The README described
        # it as "evaluated immediately before tool execution", which tells an
        # operator that eight controls are running when none are.
        #
        # Asserted against the actual call sites so the claim becomes sayable
        # again the moment it becomes true, rather than staying pessimistic
        # after the wiring lands.
        callers = []
        for path in sorted((ROOT / "scripts").glob("*.py")) + sorted(
            (ROOT / "runtime").glob("*.py")
        ):
            if path.name == "policy_enforcement.py":
                continue
            if "enforce(" in path.read_text(encoding="utf-8"):
                callers.append(path.name)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        if callers:
            return  # wired: the stronger claim is now permitted
        self.assertNotIn(
            "evaluated immediately before tool execution",
            readme,
            "enforce() has no call sites, so the README must not describe it as running",
        )
        self.assertIn("not yet wired", readme)


class ContributorSurfaceTests(unittest.TestCase):
    """A public repository needs a stated boundary, not an implied one."""

    def test_required_surface_documents_exist(self):
        for relative in [
            "SECURITY.md",
            "CONTRIBUTING.md",
            "CHANGELOG.md",
            "CLAUDE.md",
            ".editorconfig",
            "docs/README.md",
            ".github/CODEOWNERS",
            ".github/pull_request_template.md",
            ".github/ISSUE_TEMPLATE/agent-intake.yml",
            ".github/ISSUE_TEMPLATE/absorption-candidate.yml",
        ]:
            with self.subTest(path=relative):
                self.assertTrue((ROOT / relative).is_file(), f"missing {relative}")

    def test_claude_guidance_defers_to_the_single_contract(self):
        # Two copies of the operating contract is how the two runtimes drift apart.
        # The PROPERTY is deference, not a particular word for it. This
        # asserted the literal "authoritative"; the constitution merger replaced
        # CLAUDE.md with a thin adapter saying "the constitution wins" -- more
        # deferential, and it failed. Prose instead of property, again.
        text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("AGENTS.md", text)
        lowered = text.lower()
        self.assertTrue(
            any(
                phrase in lowered
                for phrase in ("authoritative", "canonical", "constitution wins", "supersede")
            ),
            "CLAUDE.md must defer to AGENTS.md rather than restate it",
        )

    def test_claude_guidance_agrees_with_the_enforced_formatter(self):
        # CLAUDE.md told Claude-based contributors that ruff-format was not
        # enabled while the same change made `ruff format --check` a required
        # CI step and added the pre-commit hook. Following the guidance would
        # have produced an avoidable CI failure. Runtime guidance that
        # contradicts the gate is worse than no guidance: it is trusted.
        text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "validate-agent.yml").read_text(
            encoding="utf-8"
        )
        formatter_enforced = "ruff format --check" in workflow
        self.assertTrue(formatter_enforced, "this test assumes CI enforces the formatter")
        # The property is that the guidance must not CONTRADICT the gate. It
        # additionally required CLAUDE.md to MENTION the formatter, which a thin
        # runtime adapter forbidden from restating policy has no business doing.
        # A file that says nothing about formatting contradicts nothing.
        self.assertNotIn("`ruff-format` is not enabled", text)
        if "ruff" in text.lower():
            self.assertNotIn("ruff format is not", text.lower())

    def test_absorption_form_requires_provenance_before_execution(self):
        # The FakeGit finding is only enforced if the check cannot be skipped.
        text = (ROOT / ".github" / "ISSUE_TEMPLATE" / "absorption-candidate.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("canonical author", text)
        self.assertIn("No code from this repository has been executed", text)
        self.assertGreaterEqual(
            text.count("required: true"),
            4,
            "provenance checks must be required fields, not optional prompts",
        )

    def test_every_documented_manual_gate_includes_the_formatter(self):
        # `ruff check` does not verify formatting; CI runs `ruff format --check`
        # as a separate required step. Four surfaces listed the manual gate and
        # all four stopped at `ruff check`, so a contributor could run every
        # documented command, pass, and still be rejected by CI.
        #
        # Asserted across all four rather than the one that was reported. Fixing
        # only CONTRIBUTING.md would have left three copies of the same defect,
        # which is the failure mode this record keeps re-learning: an instance
        # is not a class.
        # Conditional on the document actually documenting the gate, and the
        # candidate list is swept rather than hand-written. The fixed
        # four-name list broke the moment CLAUDE.md became a thin runtime
        # adapter that documents no commands at all: the test demanded a lint
        # step from a file whose own contract forbids restating policy. The
        # property was never "these four files mention ruff" -- it is "a
        # surface that tells you to run `ruff check` must also tell you about
        # the formatter CI enforces separately".
        surfaces = [
            path
            for path in sorted(ROOT.glob("*.md")) + [ROOT / "pyproject.toml"]
            if path.is_file() and "ruff check" in path.read_text(encoding="utf-8")
        ]
        self.assertTrue(surfaces, "no surface documents `ruff check`; this test is vacuous")
        for path in surfaces:
            with self.subTest(path=path.name):
                self.assertIn(
                    "ruff format --check",
                    path.read_text(encoding="utf-8"),
                    f"{path.name}: documents `ruff check` without the formatter CI also requires",
                )

    def test_every_documented_gate_installs_the_tools_it_invokes(self):
        # `ruff` is in no requirements manifest, and installing pre-commit builds
        # it an isolated hook environment whose executable is not on PATH -- so
        # the documented "run everything by hand" sequence reached `ruff check .`
        # with no `ruff` command and stopped there.
        #
        # Stated as the general property rather than the reported instance: a
        # sequence that invokes a tool must install it. Found by mutation-testing
        # the fix and getting MISSED, which is the third time chasing an uncaught
        # mutation has produced coverage that was simply absent.
        # Compared over COMMAND lines only. The first version searched the
        # whole file and failed on its own explanatory comment, which mentions
        # `ruff check` while describing the defect and sits above the install --
        # a test measuring prose rather than the sequence, which is the exact
        # weakness corrected in the metric-table test two rounds ago.
        for relative in ("CONTRIBUTING.md", "README.md"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            commands = [
                line.strip()
                for block in text.split("```bash")[1:]
                for line in block.split("```")[0].splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            for tool, install in (("ruff check", "pip install ruff=="),):
                invocations = [i for i, line in enumerate(commands) if line.startswith(tool)]
                if not invocations:
                    continue
                installs = [i for i, line in enumerate(commands) if install in line]
                with self.subTest(path=relative, tool=tool):
                    self.assertTrue(
                        installs,
                        f"{relative}: invokes `{tool}` without installing it, so the "
                        "documented sequence stops with command not found",
                    )
                    self.assertLess(
                        min(installs),
                        min(invocations),
                        f"{relative}: installs the tool after invoking it",
                    )

    def test_the_documented_ruff_matches_the_enforced_pin(self):
        # A different version documented from the one CI pins is the divergence
        # the pin exists to prevent, arriving through the install line.
        workflow = VALIDATE_WORKFLOW.read_text(encoding="utf-8")
        pinned = re.search(r"pip install ruff==([\d.]+)", workflow)
        self.assertIsNotNone(pinned, "CI does not pin ruff")
        for relative in ("CONTRIBUTING.md", "README.md"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            if "pip install ruff==" not in text:
                continue
            with self.subTest(path=relative):
                self.assertIn(f"pip install ruff=={pinned.group(1)}", text)

    # The contracts tier in either spelling. Hard-coding the manifest path made
    # this test CRASH with ValueError -- not fail with a message -- the moment
    # the documented command was pointed at the lock, which is a supply-chain
    # correction and not a reordering. A test that names an incidental spelling
    # blocks a change it has no opinion about.
    _CONTRACTS_INSTALL = re.compile(
        r"pip install -r requirements/(?:lock-runtime-contracts|runtime-contracts)\.txt"
    )

    def _contracts_install_position(self, relative, text):
        found = self._CONTRACTS_INSTALL.search(text)
        self.assertIsNotNone(
            found, f"{relative} documents no contracts-tier install for the verifiers to follow"
        )
        return found.start()

    def test_every_documented_gate_installs_validators_first(self):
        # Generalized from the CONTRIBUTING-only version below, which is how
        # README.md kept the defect after CONTRIBUTING.md was fixed: it ran
        # verify_runtime_stack.py three lines BEFORE installing jsonschema and
        # rtoml, so the audit passed having validated nothing.
        for relative in ("CONTRIBUTING.md", "README.md"):
            with self.subTest(path=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                install = self._contracts_install_position(relative, text)
                for verifier in (
                    "python scripts/verify_runtime_stack.py",
                    "python scripts/verify_mcp_mounts.py",
                ):
                    self.assertLess(
                        install,
                        text.index(verifier),
                        f"{relative}: {verifier} runs before the dependencies it needs, "
                        "so it reports success having checked nothing",
                    )

    def test_documented_manual_gate_installs_validators_first(self):
        # verify_runtime_stack.py catches the ImportError for jsonschema and
        # rtoml, reports zero schemas and zero TOML files checked, and exits 0 --
        # so a contributor following the documented order passed the audit while
        # it validated nothing.
        text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        install = self._contracts_install_position("CONTRIBUTING.md", text)
        verifier = text.index("python scripts/verify_runtime_stack.py")
        self.assertLess(
            install, verifier, "the verifier's dependencies must be installed before it runs"
        )

    def test_scan_applicability_is_its_own_required_question(self):
        # The first attempt made one checkbox required with an "either the
        # boxes above are ticked, or this is out of scope" label. That
        # established neither branch: a submitter could tick that box alone and
        # leave the scan and every safety result blank. Applicability has to be
        # a separate required answer, or the attestations are unenforceable.
        #
        # Asserted per-block rather than by parsing YAML: PyYAML is not in any
        # live requirements manifest, and the alternatives were both worse than
        # this. Adding a dependency for one assertion is heavy; guarding the
        # test with `skipUnless(yaml)` would be the silent-degradation pattern
        # this very round was spent removing from three CI steps -- a test that
        # skips itself reports the same green as a test that passed.
        #
        # Block-scoped is also what the old version lacked: it counted
        # `required: true` across the whole file, which is why a required box
        # in the wrong group satisfied it.
        text = (ROOT / ".github" / "ISSUE_TEMPLATE" / "absorption-candidate.yml").read_text(
            encoding="utf-8"
        )
        blocks = {}
        for chunk in text.split("\n  - type: "):
            for line in chunk.splitlines():
                if line.strip().startswith("id: "):
                    blocks[line.split("id: ", 1)[1].strip()] = chunk
                    break

        applies = blocks.get("agent-scan-applies")
        self.assertIsNotNone(applies, "no explicit scan-applicability question")
        self.assertTrue(applies.startswith("dropdown"), "applicability must be a dropdown")
        self.assertIn("required: true", applies)
        # Every option must BE an attestation, not a pointer to one elsewhere.
        #
        # This asserted exactly two options, on the reasoning that a third
        # would reintroduce an ambiguous "either ... or". That was the wrong
        # property: with two options the "Yes" branch said "complete the
        # attestations below" while those attestations stayed optional, so a
        # submitter could select Yes and leave every safety result blank. The
        # risk was never the COUNT of options -- it was an option that decides
        # nothing. Each option now states an outcome, so no branch can be
        # selected without asserting something.
        options = [line for line in applies.splitlines() if line.startswith('        - "')]
        self.assertGreaterEqual(len(options), 2)
        self.assertTrue(
            any("not applicable" in option.lower() for option in options),
            "no branch for a candidate the scan does not apply to",
        )
        self.assertTrue(
            all(
                "scanned" in option.lower() or "not applicable" in option.lower()
                for option in options
            ),
            "every option must state an outcome rather than defer to the boxes below",
        )

        attestations = blocks.get("agent-scan")
        self.assertIsNotNone(attestations)
        self.assertNotIn(
            "required: true",
            attestations,
            "attestations must not carry the applicability decision themselves",
        )

    def test_optimization_record_states_findings_and_decision_outcomes(self):
        text = OPTIMIZATION_RECORD.read_text(encoding="utf-8")
        for phrase in [
            "## Verification honesty",
            "Part 1 — What the repository is missing",
            "Part 2 — External repositories that fit these gaps",
            # Decisions must be tracked to an outcome, not left as a standing list.
            "## Decisions",
            "resolved",
            "What remains open after this round",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)


class MountVerifierTests(unittest.TestCase):
    """The mount verifier's own failure modes, found in the fifteenth pass."""

    def test_an_exact_contract_refuses_undeclared_tools(self):
        # Checking only for MISSING tools meant a server could register anything
        # extra and still verify. The governance mount is granted to
        # `agents = ["*"]`, so an undeclared tool reaches the whole corps with
        # CI green.
        from scripts.verify_mcp_mounts import _verdict

        exact = {"expected_tools": ["a", "b"], "tools_are_exhaustive": True}
        self.assertEqual(_verdict(exact, ["a", "b"]), "verified")
        self.assertIn("undeclared", _verdict(exact, ["a", "b", "delete_all"]))

    def test_a_subset_contract_still_tolerates_upstream_additions(self):
        # The other half of the fix: naming every tool an upstream release ships
        # would turn any additive change into a CI failure, so the filesystem
        # mount's list stays a floor.
        from scripts.verify_mcp_mounts import _verdict

        subset = {"expected_tools": ["a", "b"]}
        self.assertEqual(_verdict(subset, ["a", "b", "new_upstream_tool"]), "verified")
        self.assertIn("missing", _verdict(subset, ["a"]))

    def test_the_governance_mount_declares_an_exact_contract(self):
        # The config half. Without the declaration the code change enforces
        # nothing, and the two would drift silently.
        import tomllib

        data = tomllib.loads((ROOT / "config" / "mcp_mounts.toml").read_text(encoding="utf-8"))
        governance = next(m for m in data["mounts"] if m["name"] == "governance")
        self.assertTrue(governance.get("tools_are_exhaustive"))
        self.assertTrue(governance.get("expected_tools"))

    def test_each_probe_is_bounded_by_a_timeout(self):
        # `ClientSession` defaults `read_timeout_seconds` to None, so a server
        # that starts but never answers leaves the await blocked until GitHub
        # Actions kills the job at its limit. One hung mount then costs the
        # whole run instead of reporting one failed verification.
        import asyncio
        import inspect

        from scripts import verify_mcp_mounts as module

        self.assertIn("asyncio.wait_for", inspect.getsource(module._probe_with_timeout))
        self.assertGreater(module.PROBE_TIMEOUT_SECONDS, 0)
        self.assertIn(
            "_probe_with_timeout",
            inspect.getsource(module.main),
            "main() must call the bounded probe, not the unbounded one",
        )

        # Exercised, not merely asserted about: a probe that never responds must
        # raise rather than hang, or this test proves only that a string appears
        # in the source.
        #
        # The inner probe is STUBBED, because the real one imports the optional
        # `mcp` package. Calling it made `python -m unittest discover -s tests`
        # -- the repository's mandatory command -- error outright in any
        # checkout without the runtime-contracts install, which the documented
        # pre-commit path does not perform. This suite's whole contract is that
        # it runs on the standard library alone.
        #
        # Stubbed rather than skipped, deliberately. A `skipUnless(mcp)` would
        # report the same green as a passing test on exactly the machines where
        # the dependency is missing, which is the silent-degradation shape this
        # change set has removed from three CI gates. The timeout lives in
        # `_probe_with_timeout`, so wrapping a sleeping coroutine tests the real
        # thing without the dependency.
        async def _never_answers(_command):
            await asyncio.sleep(60)

        original_probe = module._probe
        original_timeout = module.PROBE_TIMEOUT_SECONDS
        module._probe = _never_answers
        module.PROBE_TIMEOUT_SECONDS = 1
        try:
            with self.assertRaises(TimeoutError):
                asyncio.run(module._probe_with_timeout(["irrelevant"]))
        finally:
            module._probe = original_probe
            module.PROBE_TIMEOUT_SECONDS = original_timeout

    def test_the_unit_suite_needs_no_optional_runtime(self):
        # The suite's stated contract, asserted rather than assumed. A test that
        # imports an optional package turns the mandatory command into one that
        # errors on a fresh checkout -- which is how the timeout test above
        # started life.
        import importlib
        import unittest.mock

        real_import = __import__

        def blocked(name, *args, **kwargs):
            if name == "mcp" or name.startswith("mcp."):
                raise ModuleNotFoundError("No module named 'mcp'")
            return real_import(name, *args, **kwargs)

        module = importlib.import_module("scripts.verify_mcp_mounts")
        with unittest.mock.patch("builtins.__import__", blocked):
            # The verifier itself must still import and report, degraded.
            self.assertTrue(callable(module.main))
            self.assertEqual(module._verdict({"expected_tools": ["a"]}, ["a"]), "verified")

    def test_a_misspelled_flag_is_rejected_rather_than_ignored(self):
        # `"--strict" in argv` meant `--strcit` in a workflow file silently ran
        # the permissive path: mounts unverified, exit 0, CI green -- the exact
        # false success strict mode was added to remove.
        import contextlib
        import io

        from scripts.verify_mcp_mounts import main

        # redirect_stderr suppresses argparse's usage text, nothing more.
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            main(["--strcit"])
        self.assertNotEqual(raised.exception.code, 0)

    def test_the_strict_flag_still_parses(self):
        # A rejection test alone would pass if the flag stopped working
        # entirely, which would be a worse version of the same silence.
        import inspect

        from scripts.verify_mcp_mounts import main

        source = inspect.getsource(main)
        self.assertIn('"--strict"', source)
        self.assertIn("argparse", source)


class DependencyProvenanceTests(unittest.TestCase):
    """The scan must cover what is installed, not a file nothing installs."""

    def test_ci_installs_from_the_locks_the_security_scan_audits(self):
        # security.yml calls requirements/lock-runtime-*.txt "the resolved forms
        # of the sets CI installs" -- while CI installed the ranged manifests,
        # so pip could select a version the scan had never seen. A clean scan of
        # a lock nothing installs proves nothing about what ran.
        workflow = VALIDATE_WORKFLOW.read_text(encoding="utf-8")
        security = SECURITY_WORKFLOW.read_text(encoding="utf-8")
        for lock in ("lock-runtime-root.txt", "lock-runtime-contracts.txt"):
            with self.subTest(lock=lock):
                self.assertIn(f"requirements/{lock}", security, f"{lock} is not scanned")
                self.assertIn(
                    f"pip install -r requirements/{lock}",
                    workflow,
                    f"{lock} is scanned but never installed",
                )

    def test_no_ci_step_installs_the_floating_manifest_it_has_a_lock_for(self):
        workflow = VALIDATE_WORKFLOW.read_text(encoding="utf-8")
        for manifest in ("requirements.txt", "requirements/runtime-contracts.txt"):
            with self.subTest(manifest=manifest):
                self.assertNotIn(
                    f"pip install -r {manifest}",
                    workflow,
                    f"{manifest} has a committed lock; installing the ranged form "
                    "reintroduces the gap between what is scanned and what runs",
                )

    def test_lock_drift_is_checked_on_every_supported_python(self):
        # Installing from a lock is half the property; the other half is that
        # the lock still represents its manifest. A dependency release can make
        # the manifest resolve elsewhere, and CI would keep installing a stale
        # set the scan reports as clean forever.
        #
        # Both legs, because one shared lock is only valid while 3.11 and 3.12
        # resolve identically -- which is checked rather than assumed.
        workflow = VALIDATE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("uv pip compile", workflow)
        job = workflow[workflow.index("  locks:") : workflow.index("  lint:")]
        for version in ("3.11", "3.12"):
            with self.subTest(python=version):
                self.assertIn(version, job)
        # Every generated lock the security workflow scans must appear here.
        # The first version of this job checked two of the three and omitted
        # lock-runtime-evaluation.txt, so the documented evaluation install
        # could drift from the audited lock indefinitely. Derived from the
        # security workflow rather than restated, so adding a lock there
        # without adding it to the drift matrix fails instead of passing.
        security = SECURITY_WORKFLOW.read_text(encoding="utf-8")
        scanned = sorted(set(re.findall(r"requirements/lock-runtime-[\w.-]+\.txt", security)))
        self.assertTrue(scanned, "no generated locks are scanned at all")
        for lock in scanned:
            with self.subTest(lock=lock):
                self.assertIn(lock, job, f"{lock} is scanned but its drift is never checked")


class SecretScanScopeTests(unittest.TestCase):
    """Each event gets the range it is responsible for."""

    def test_a_push_scans_its_own_range_not_all_history(self):
        # BASE_SHA is empty on BOTH push and schedule, so the else branch ran
        # the unscoped whole-history scan on every push to main -- the exact
        # behaviour the surrounding comment says was moved to the weekly run.
        # With fetch-depth: 0 that can fail a push for a secret on an unrelated
        # unmerged branch, which the pusher cannot remove.
        # Asserted against the env BINDING and the branch that uses it, not the
        # bare expression. The first version checked for "github.event.before"
        # anywhere in the file and still passed when the binding was deleted,
        # because the surrounding comment mentions the same string -- a test
        # satisfied by prose describing the property rather than by the
        # property. Caught by mutation-testing it, not by reading it.
        text = SECURITY_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("BEFORE_SHA: ${{ github.event.before }}", text)
        self.assertIn("EVENT_NAME: ${{ github.event_name }}", text)
        self.assertIn('[ "${EVENT_NAME}" = "push" ]', text)
        self.assertIn('--log-opts="${BEFORE_SHA}..HEAD"', text)

    def test_the_new_ref_sentinel_is_handled(self):
        # `github.event.before` is all zeros for a newly created ref, and a
        # force-push can leave it unreachable. Both must fall through to the
        # full scan rather than building a broken range.
        text = SECURITY_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("0000000000000000000000000000000000000000", text)
        self.assertIn("git cat-file -e", text)

    def test_ref_values_reach_the_script_through_env_only(self):
        # A ref value interpolated into the script body could be read as shell.
        text = SECURITY_WORKFLOW.read_text(encoding="utf-8")
        script = text[text.index("GITLEAKS=") :]
        for expression in ("${{ github.event.before }}", "${{ github.event_name }}"):
            with self.subTest(expression=expression):
                self.assertNotIn(expression, script)


if __name__ == "__main__":
    unittest.main()


class PrivacyGuardFixtureShapeTests(unittest.TestCase):
    """The guard's own fixtures must need no gitleaks suppression.

    `scripts/privacy_guard.py` builds negative fixtures as split literals so its
    OWN patterns do not match its test data. Splitting off the first character
    (`"c" + 'lient_secret...'`) achieves that but not the same for gitleaks,
    which reads the reassembled line -- so one fixture produced a working-tree
    finding, that finding needed a LINE-PINNED suppression, and a line-pinned
    suppression drifts whenever anything above it moves. It broke CI once, was
    raised in review four times, and Joe marked it Fix.

    The fix was to stop producing the finding rather than to keep suppressing it.
    This test keeps it that way: no working-tree entry may name this file. It is
    the one file in the exemption list this repository actually wrote, so it is
    the one where "do not need the exemption" was available -- the rest are
    absorbed documents whose sample text must keep looking like the credential it
    warns about.
    """

    GUARD = "scripts/privacy_guard.py"

    def test_the_guard_needs_no_working_tree_exemption(self):
        for path, rule, number in GitleaksSuppressionTests()._working_tree_entries():
            with self.subTest(entry=f"{path}:{rule}:{number}"):
                self.assertNotEqual(
                    path,
                    self.GUARD,
                    f"{self.GUARD} is back in the working-tree exemptions. Re-split the "
                    "fixture so gitleaks stops matching it instead of pinning a line "
                    "number that will drift again.",
                )

    def test_the_history_exemption_is_still_present_and_immutable(self):
        # The other direction, and the part that CANNOT be removed: `gitleaks git`
        # attributes a secret to the commit that ADDED the line, so that
        # fingerprint is pinned to an immutable ancestor. Deleting it because the
        # working-tree one went away would turn the history scan red.
        text = (ROOT / ".gitleaksignore").read_text(encoding="utf-8")
        history = [
            line.strip()
            for line in text.splitlines()
            if self.GUARD in line and not line.strip().startswith("#")
        ]
        self.assertEqual(
            len(history),
            1,
            f"expected exactly one (history-form) entry for {self.GUARD}, found {history}",
        )
        self.assertRegex(history[0], r"^[0-9a-f]{40}:")

    def test_the_fixture_value_still_matches_the_document_it_excuses(self):
        # The re-split is only safe because the runtime VALUE is unchanged. This
        # string is an allowlist entry: if it stops matching the absorbed
        # document, the guard starts reporting that document as a real leak.
        import sys

        sys.path.insert(0, str(ROOT))
        from scripts.privacy_guard import PLACEHOLDER_LITERALS

        document = Path(".claude/agents/awesome-claude-agents/specialized/python/testing-expert.md")
        literals = PLACEHOLDER_LITERALS[document]
        matching = [value for value in literals if value.startswith("client_secret")]
        self.assertEqual(len(matching), 1, f"expected one client_secret literal, got {matching}")
        self.assertIn(
            matching[0],
            (ROOT / document).read_text(encoding="utf-8"),
            "the re-split fixture no longer matches the document it exempts, so the "
            "guard will report that document as a real leak",
        )
