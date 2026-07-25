"""The repository-engineering substrate must not silently regress.

Record: docs/REPO_OPTIMIZATION_2026-07-25.md. These tests assert the gates
themselves exist and stay wired up, so a later change cannot quietly drop a CI
step, unpin an action, or remove a boundary document.
"""

from pathlib import Path
import re
import unittest


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

    def test_workflows_declare_least_privilege_permissions(self):
        for path in self._workflow_files():
            text = path.read_text(encoding="utf-8")
            with self.subTest(workflow=path.name):
                self.assertIn("permissions:", text)
                self.assertIn("contents: read", text)

    def test_security_workflow_audits_the_workflows_themselves(self):
        text = SECURITY_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("zizmorcore/zizmor-action@", text)
        self.assertIn("schedule:", text, "audit rules must reach a quiet repository too")


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

    def test_optimization_record_states_its_open_decisions(self):
        text = OPTIMIZATION_RECORD.read_text(encoding="utf-8")
        for phrase in [
            "## Verification honesty",
            "Part 1 — What the repository is missing",
            "Part 2 — External repositories that fit these gaps",
            "## Open decisions for Joe",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
