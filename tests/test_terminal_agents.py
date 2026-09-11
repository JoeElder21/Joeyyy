"""The bounded role manifest and its briefs."""

import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "terminal" / "agents"
EXPECTED = {
    "orchestrator",
    "data_steward",
    "market_catalyst_analyst",
    "equity_researcher",
    "crypto_researcher",
    "quant_valuation_analyst",
    "portfolio_risk_analyst",
    "ranking_critic",
    "outcome_learning_analyst",
    "release_qa_validator",
}


class RoleManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = tomllib.loads((ROOT / "roles.toml").read_text(encoding="utf-8"))
        cls.roles = {r["id"]: r for r in cls.manifest["role"]}

    def test_the_ten_roles_exist_with_briefs(self):
        self.assertEqual(set(self.roles), EXPECTED)
        for role_id in EXPECTED:
            with self.subTest(role=role_id):
                self.assertTrue((ROOT / f"{role_id}.md").exists())
                text = (ROOT / f"{role_id}.md").read_text(encoding="utf-8")
                self.assertIn("## Forbidden", text)

    def test_only_the_orchestrator_writes_the_store(self):
        writers = [r for r, spec in self.roles.items() if spec["writes_store"]]
        self.assertEqual(writers, ["orchestrator"])
        self.assertEqual(self.manifest["designated_writer"], "orchestrator")
        self.assertEqual(self.manifest["brain"], "JEOS")

    def test_roles_are_bounded_and_forbid_orders(self):
        total = 0
        for role_id, spec in self.roles.items():
            with self.subTest(role=role_id):
                self.assertGreaterEqual(spec["parallelism"], 1)
                self.assertTrue(spec["forbidden"])
                self.assertTrue(spec["reads"] and spec["produces"] and spec["tools"])
            total = max(total, spec["parallelism"])
        self.assertLessEqual(total, self.manifest["max_concurrent_agents"])
        self.assertIn("orders", self.roles["orchestrator"]["forbidden"])


if __name__ == "__main__":
    unittest.main()
