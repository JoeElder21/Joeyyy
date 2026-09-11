"""The daily research pipeline on the synthetic fixture, including every failure path."""

import copy
import json
import unittest
from pathlib import Path

from terminal import critic, pipeline, schema, store

FIXTURE = Path(__file__).resolve().parents[1] / "terminal" / "fixtures" / "synthetic_inputs.json"


def load_inputs() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = load_inputs()
        cls.store = store.MemoryStore()
        cls.result = pipeline.run(copy.deepcopy(cls.inputs), cls.store)

    def test_fixture_is_synthetic(self):
        self.assertTrue(self.inputs.get("synthetic"))

    def test_clean_run_publishes(self):
        self.assertEqual(self.result.status, "PUBLISHED")
        self.assertEqual(
            [s["name"] for s in self.result.stages],
            [
                "idempotency",
                "lock",
                "steward",
                "universe",
                "quant",
                "risk",
                "critic",
                "learning",
                "release",
            ],
        )
        self.assertTrue(all(g.passed for g in self.result.gate_checks))
        self.assertIn("snapshots/current", self.store.paths())

    def test_stances_follow_the_policy_ladder(self):
        recs = {d["symbol"]: d for _, d in self.store.list("recommendations")}
        self.assertEqual(
            {k: v["stance"] for k, v in recs.items()},
            {"EXA": "HOLD", "EXB": "ADD", "EXC": "HOLD", "EXD": "BUY", "SYNTH": "HOLD"},
        )
        self.assertIsNotNone(recs["EXB"]["cooling_period_ends"])
        self.assertIsNone(recs["EXA"]["cooling_period_ends"])
        self.assertTrue(recs["EXD"]["hurdle_cleared"])
        self.assertEqual(recs["EXD"]["reference_price"], None)
        self.assertIn("open after publication", recs["EXD"]["reference_convention"])
        self.assertEqual(recs["SYNTH"]["scorecard"]["rubric_status"], "PROPOSED")

    def test_excluded_and_insufficient_assets_are_listed_not_ranked(self):
        board = self.store.get("boards/rankings-equity")
        by_symbol = {r["symbol"]: r for r in board["rows"]}
        self.assertEqual(by_symbol["EXE"]["status"], "EXCLUDED")
        self.assertEqual(by_symbol["EXE"]["rank"], 0)
        self.assertEqual(by_symbol["EXF"]["status"], "INSUFFICIENT")
        self.assertEqual(
            [r["symbol"] for r in board["rows"] if r["rank"]], ["EXD", "EXA", "EXB", "EXC"]
        )
        crypto = self.store.get("boards/rankings-crypto")
        self.assertEqual(
            {r["symbol"]: r["status"] for r in crypto["rows"]},
            {"SYNTH": "SCORED", "MOCK": "EXCLUDED"},
        )

    def test_critic_revised_the_low_coverage_recommendation(self):
        self.assertEqual(self.result.debate["verdict"], critic.REVISED)
        self.assertEqual(self.result.debate["rounds"], 2)
        rec = self.store.get(
            "recommendations/"
            + next(rid for rid, d in self.store.list("recommendations") if d["symbol"] == "EXC")
        )
        self.assertIn("Unscored factors: portfolio_fit, technicals_liquidity", rec["rationale"])

    def test_portfolio_limits_are_applied_per_portfolio(self):
        by_id = {r["portfolio_id"]: r for r in self.result.risk}
        self.assertEqual(by_id["schwab-roth"]["status"], "OK")
        self.assertEqual(by_id["schwab-rollover"]["status"], "REVIEW")
        self.assertTrue(
            any("cash 1.2% is below" in b for b in by_id["schwab-rollover"]["breaches"])
        )
        self.assertTrue(any("14.0% exceeds" in b for b in by_id["schwab-rollover"]["breaches"]))

    def test_prior_recommendations_are_graded(self):
        graded = dict(self.store.list("outcomes"))
        self.assertEqual(graded["rec-prior-exa-buy"]["status"], "HIT")
        self.assertEqual(graded["rec-prior-exb-avoid"]["status"], "MISS")
        self.assertEqual(graded["rec-prior-exc-hold"]["status"], "OPEN")
        self.assertEqual(graded["rec-prior-exd-void"]["status"], "VOID")
        learning = self.store.get("learning/current")
        rate = next(iter(learning["hit_rates"].values()))
        self.assertEqual((rate["graded"], rate["hits"], rate["open"], rate["void"]), (2, 1, 1, 1))

    def test_every_stored_document_validates(self):
        for path in self.store.paths():
            name = pipeline.SCHEMA_BY_COLLECTION.get(path.split("/")[0])
            if name is None or path in pipeline.UNSCHEMAED_DOCS:
                continue
            with self.subTest(path=path):
                self.assertEqual(
                    schema.validate(self.store.get(path), schema.load_schema(name)), []
                )

    def test_health_names_the_dst_drift_and_starts_vs_ready(self):
        health = self.store.get("health/current")
        daily = next(s for s in health["schedule"] if s["name"] == "daily")
        self.assertEqual([w["fires_at_et"] for w in daily["dst_drift"]], ["05:00", "05:00"])
        self.assertEqual(daily["last_starts_vs_ready"], "starts 6:00 AM, ready 6:41 AM (41 min)")
        self.assertEqual(health["boards"]["rankings-equity"]["status"], "LIVE")

    def test_second_run_with_the_same_key_is_skipped(self):
        again = pipeline.run(copy.deepcopy(self.inputs), self.store)
        self.assertEqual(again.status, "SKIPPED")
        self.assertEqual(again.stages[0]["status"], "SKIPPED")

    def test_run_is_deterministic(self):
        a = pipeline.run(copy.deepcopy(self.inputs), store.MemoryStore())
        b = pipeline.run(copy.deepcopy(self.inputs), store.MemoryStore())
        self.assertEqual(a.manifest.result_sha, b.manifest.result_sha)


class FailureInjectionTests(unittest.TestCase):
    def run_with(self, inject: str):
        inputs = load_inputs() | {"inject": inject}
        return pipeline.run(inputs, store.MemoryStore())

    def test_unknown_injection_is_rejected(self):
        with self.assertRaises(ValueError):
            self.run_with("meteor")

    def test_stale_prices_degrade_the_boards_but_label_them(self):
        result = self.run_with("stale-prices")
        self.assertEqual(result.status, "PUBLISHED")
        self.assertEqual(result.boards["rankings-equity"], "DEGRADED")
        self.assertEqual(
            next(s for s in result.stages if s["name"] == "steward")["status"], "DEGRADED"
        )

    def test_missing_evidence_withdraws_buys_and_adds(self):
        result = self.run_with("missing-evidence")
        stances = {
            d["symbol"]: d["stance"]
            for p, d in result.docs.items()
            if p.startswith("recommendations/")
        }
        self.assertNotIn("EXD", stances)
        self.assertNotIn("EXB", stances)
        self.assertEqual(result.debate["verdict"], critic.REVISED)

    def test_lock_held_blocks_before_any_work(self):
        result = self.run_with("lock-held")
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual([s["name"] for s in result.stages], ["idempotency", "lock"])
        self.assertEqual(result.docs, {})

    def test_duplicate_run_is_skipped(self):
        self.assertEqual(self.run_with("duplicate-run").status, "SKIPPED")

    def test_chain_break_fails_the_release_gate(self):
        result = self.run_with("chain-break")
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual([g.name for g in result.gate_checks if not g.passed], ["run_chain"])

    def test_critic_block_stops_the_release_and_keeps_the_run_record(self):
        s = store.MemoryStore()
        result = pipeline.run(load_inputs() | {"inject": "critic-block"}, s)
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.debate["verdict"], critic.BLOCKED)
        self.assertEqual([p for p in s.paths() if not p.startswith("runs/")], [])
        self.assertTrue(any(p.startswith("runs/") for p in s.paths()))

    def test_pooled_schwab_portfolios_fail_the_invariant(self):
        inputs = load_inputs()
        for portfolio in inputs["portfolios"]:
            portfolio["distinct_from"] = []
        result = pipeline.run(inputs, store.MemoryStore())
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("invariants", [g.name for g in result.gate_checks if not g.passed])

    def test_invalid_portfolio_document_blocks_at_the_steward(self):
        inputs = load_inputs()
        inputs["portfolios"][0]["source"] = "estimate"
        result = pipeline.run(inputs, store.MemoryStore())
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.stages[-1]["name"], "steward")


if __name__ == "__main__":
    unittest.main()
