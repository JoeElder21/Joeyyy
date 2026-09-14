"""The 100-point scorecard, its missing-data treatment, and the proposed crypto rubric."""

import unittest

from terminal import scorecard

FULL = {
    "fundamentals": 0.9,
    "valuation": 0.7,
    "catalysts_revisions": 0.8,
    "downside_protection": 0.8,
    "portfolio_fit": 0.6,
    "technicals_liquidity": 0.9,
}
CITED = {name: ["ev-1"] for name in FULL}


class ScorecardTests(unittest.TestCase):
    def test_weights_sum_to_one_hundred(self):
        self.assertEqual(sum(scorecard.EQUITY_WEIGHTS.values()), 100)
        self.assertEqual(sum(scorecard.CRYPTO_WEIGHTS_PROPOSED.values()), 100)

    def test_full_scorecard_is_the_weighted_sum(self):
        result = scorecard.score_equity(FULL, CITED)
        self.assertEqual(result.status, scorecard.SCORED)
        self.assertEqual(result.earned, 81.0)
        self.assertEqual(result.possible, 100)
        self.assertEqual(result.score, 81.0)
        self.assertEqual(result.factors["evidence_quality"], 1.0)
        self.assertEqual(result.rubric_status, "ADOPTED")

    def test_unscored_factor_leaves_the_denominator_instead_of_being_imputed(self):
        factors = dict(FULL) | {"portfolio_fit": None, "technicals_liquidity": None}
        result = scorecard.score_equity(factors, CITED)
        self.assertEqual(result.possible, 80)
        self.assertEqual(result.coverage, 0.8)
        self.assertEqual(sorted(result.unscored), ["portfolio_fit", "technicals_liquidity"])
        self.assertEqual(result.score, round(100 * (18 + 14 + 12 + 12 + 10) / 80, 1))
        self.assertEqual(result.status, scorecard.SCORED)

    def test_missing_core_factor_is_insufficient(self):
        result = scorecard.score_equity(dict(FULL) | {"valuation": None}, CITED)
        self.assertEqual(result.status, scorecard.INSUFFICIENT)
        self.assertIsNone(result.score)
        self.assertTrue(any("core factor(s) unscored: valuation" in n for n in result.notes))

    def test_low_coverage_is_partial(self):
        factors = {"fundamentals": 0.5, "valuation": 0.5, "downside_protection": 0.5}
        result = scorecard.score_equity(factors, {k: ["e"] for k in factors})
        self.assertEqual(result.status, scorecard.PARTIAL)
        self.assertLess(result.coverage, scorecard.MIN_COVERAGE)

    def test_evidence_quality_derives_from_citation_coverage(self):
        half = {name: (["ev"] if i % 2 == 0 else []) for i, name in enumerate(FULL)}
        result = scorecard.score_equity(FULL, half)
        self.assertEqual(result.factors["evidence_quality"], 0.5)

    def test_values_are_clamped_and_unknown_factors_rejected(self):
        result = scorecard.score_equity(dict(FULL) | {"fundamentals": 7.0}, CITED)
        self.assertEqual(result.factors["fundamentals"], 1.0)
        with self.assertRaises(ValueError):
            scorecard.score_equity({"momentum": 1.0})

    def test_digest_is_deterministic_and_sensitive(self):
        a = scorecard.score_equity(FULL, CITED).input_digest
        b = scorecard.score_equity(dict(FULL), dict(CITED)).input_digest
        c = scorecard.score_equity(dict(FULL) | {"valuation": 0.71}, CITED).input_digest
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_crypto_rubric_is_marked_proposed(self):
        result = scorecard.score_crypto(
            {"liquidity_realizability": 0.6, "supply_integrity": 0.7}, {}
        )
        self.assertEqual(result.rubric_status, "PROPOSED")
        self.assertEqual(result.status, scorecard.PARTIAL)

    def test_hurdle_and_ranking(self):
        self.assertTrue(scorecard.clears_hurdle(0.15))
        self.assertFalse(scorecard.clears_hurdle(0.149))
        self.assertFalse(scorecard.clears_hurdle(None))
        results = {
            "b": scorecard.score_equity(dict(FULL) | {"valuation": 0.9}, CITED),
            "a": scorecard.score_equity(FULL, CITED),
            "c": scorecard.score_equity(dict(FULL) | {"valuation": None}, CITED),
        }
        self.assertEqual([k for k, _ in scorecard.rank(results)], ["b", "a"])


if __name__ == "__main__":
    unittest.main()
