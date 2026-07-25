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
        text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("AGENTS.md", text)
        self.assertIn("authoritative", text.lower())

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
        self.assertNotIn("`ruff-format` is not enabled", text)
        self.assertIn("ruff format", text)

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
        for relative in ("CONTRIBUTING.md", "README.md", "CLAUDE.md", "pyproject.toml"):
            with self.subTest(path=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("ruff check", text, f"{relative}: no lint step to compare against")
                self.assertIn(
                    "ruff format --check",
                    text,
                    f"{relative}: documents `ruff check` without the formatter CI also requires",
                )

    def test_every_documented_gate_installs_validators_first(self):
        # Generalized from the CONTRIBUTING-only version below, which is how
        # README.md kept the defect after CONTRIBUTING.md was fixed: it ran
        # verify_runtime_stack.py three lines BEFORE installing jsonschema and
        # rtoml, so the audit passed having validated nothing.
        for relative in ("CONTRIBUTING.md", "README.md"):
            with self.subTest(path=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                install = text.index("pip install -r requirements/runtime-contracts.txt")
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
        install = text.index("pip install -r requirements/runtime-contracts.txt")
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
        # Exactly two branches: applies, or does not. An ambiguous third option
        # would reintroduce the "either ... or" problem.
        self.assertEqual(applies.count('\n        - "'), 2)

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

        # Exercised, not merely asserted about: a command that never responds
        # must raise rather than hang, or this test proves only that a string
        # appears in the source.
        original = module.PROBE_TIMEOUT_SECONDS
        module.PROBE_TIMEOUT_SECONDS = 1
        try:
            with self.assertRaises(TimeoutError):
                asyncio.run(
                    module._probe_with_timeout(["python", "-c", "import time; time.sleep(60)"])
                )
        finally:
            module.PROBE_TIMEOUT_SECONDS = original

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
