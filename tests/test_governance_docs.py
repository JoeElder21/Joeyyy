from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_PATH = ROOT / "docs" / "ECOSYSTEM_REPO_ANALYSIS.md"
ABSORBED_PATH = ROOT / "docs" / "ABSORBED_PATTERNS.md"
BUILDOUT_PATH = ROOT / "docs" / "CIVIL3D_MCP_BUILDOUT.md"
TRIAL_PATH = ROOT / "docs" / "EXECUTION_LAYER_TRIAL.md"
REGISTRY_PATH = ROOT / "docs" / "AGENT_REGISTRY.md"
README_PATH = ROOT / "README.md"


class EcosystemGovernanceDocTests(unittest.TestCase):
    """The ecosystem analysis cycle must leave a complete, cross-linked record."""

    def test_analysis_record_exists_with_tiers_and_decisions(self):
        text = ANALYSIS_PATH.read_text(encoding="utf-8")
        for phrase in [
            "## Method",
            "adversarial verification",
            "Tier 1 — Build",
            "civil3d-mcp",
            "Pick one",
            "Watch list / skip",
            "## Joe's decisions",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_absorption_record_is_provenanced_and_reversible(self):
        text = ABSORBED_PATH.read_text(encoding="utf-8")
        for phrase in [
            "No prompts, identities, credentials, or access claims were copied",
            "— from ",
            "## Rollback",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_buildout_guide_keeps_validation_and_rollback_gates(self):
        text = BUILDOUT_PATH.read_text(encoding="utf-8")
        for phrase in [
            "civil3d_query",
            "civil3d_execute",
            "Read-only proof on copies",
            "one-designated-writer rule",
            "explicit task-level instruction",
            "## Rollback",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_trial_plan_defines_metrics_before_running(self):
        text = TRIAL_PATH.read_text(encoding="utf-8")
        for phrase in [
            "exactly one gets adopted",
            "Metrics, defined up front",
            "## Decision rule",
            "## Rollback",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_integration_roadmap_keeps_gates_and_conflicts_visible(self):
        text = (ROOT / "docs" / "INTEGRATION_ROADMAP.md").read_text(encoding="utf-8")
        for phrase in [
            "candidate-unverified",
            "Recorded conflict",
            "## Phase 1",
            "## Phase 5",
            "## Verification record — 2026-07-24",
            "LangKit",
            "## Rollback",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_registry_tracks_candidate_infrastructure(self):
        text = REGISTRY_PATH.read_text(encoding="utf-8")
        for phrase in [
            "## Candidate infrastructure and tools",
            "Civil 3D MCP connector",
            "docs/CIVIL3D_MCP_BUILDOUT.md",
            "docs/EXECUTION_LAYER_TRIAL.md",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_readme_maps_the_new_docs(self):
        text = README_PATH.read_text(encoding="utf-8")
        for name in [
            "docs/ECOSYSTEM_REPO_ANALYSIS.md",
            "docs/ABSORBED_PATTERNS.md",
            "docs/CIVIL3D_MCP_BUILDOUT.md",
            "docs/EXECUTION_LAYER_TRIAL.md",
        ]:
            with self.subTest(doc=name):
                self.assertIn(name, text)


if __name__ == "__main__":
    unittest.main()
