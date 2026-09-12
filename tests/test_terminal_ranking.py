"""Acceptance gates for the quantitative ranking upgrade.

Each test named ``test_gate_*`` corresponds to one bullet in section 14 of the
implementation directive. They are written as adversarial checks: every one of
them tries to make the engine do the dishonest thing and asserts that it
refuses.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from terminal import entry, features, ledger, quant, ranking


def crypto_asset(
    liquidity: float = 500_000.0,
    momentum: float = 0.05,
    drawdown: float = 0.20,
    spread: float = 0.003,
    verified: bool = True,
    price: float = 1.0,
    returns: list[float] | None = None,
    **extra,
) -> dict:
    payload = {
        "display": "test asset",
        "identity": {"verified": verified},
        "price": price,
        "venue": "solana_dex",
        "liquidity_usd": liquidity,
        "return_series": returns if returns is not None else [0.02, -0.03, 0.05, -0.04] * 10,
        "features": {
            "liquidity_depth": liquidity / 1000.0,
            "liquidity_usd_raw": liquidity,
            "spread_cost": spread,
            "residual_momentum": momentum,
            "relative_strength_vs_market": momentum * 0.8,
            "trend_persistence": 0.5,
            "downside_deviation": 0.04,
            "max_drawdown": drawdown,
            "ewma_volatility": 0.05,
            "turnover_ratio": 2.0,
            "extension_from_support": 1.5,
            "float_ratio": 0.9,
        },
    }
    payload.update(extra)
    return payload


def universe(n: int = 6, **overrides) -> dict[str, dict]:
    out = {}
    for i in range(n):
        out[f"sol:T{i}"] = crypto_asset(
            liquidity=100_000.0 * (i + 1),
            momentum=0.01 * (i + 1),
            drawdown=0.10 + 0.05 * i,
        )
    out.update(overrides)
    return out


class GateReproducibility(unittest.TestCase):
    """Identical frozen inputs reproduce identical numeric scores and ranks."""

    def test_gate_identical_inputs_reproduce_identical_ranks(self):
        assets = universe()
        cfg = ranking.config_for("crypto", "7d")
        first = ranking.rank_universe(assets, cfg)
        second = ranking.rank_universe(assets, cfg)
        self.assertEqual(first.input_digest, second.input_digest)
        self.assertEqual([a.asset_id for a in first.ranked], [a.asset_id for a in second.ranked])
        self.assertEqual([a.composite for a in first.ranked], [a.composite for a in second.ranked])

    def test_gate_config_change_changes_the_digest(self):
        assets = universe()
        a = ranking.rank_universe(assets, ranking.config_for("crypto", "7d"))
        b = ranking.rank_universe(assets, ranking.config_for("crypto", "30d"))
        self.assertNotEqual(a.input_digest, b.input_digest)


class GateNoLookahead(unittest.TestCase):
    """Injecting future observations cannot alter a prior published ranking."""

    def test_gate_published_row_is_immutable_under_later_data(self):
        published = _row(horizon="7d")
        book = ledger.Ledger([published])
        snapshot = published.as_row()

        # A "later" correction is appended, never written over the original.
        correction = _row(horizon="7d", corrects=published.row_id, score=0.99)
        book.append(correction)

        self.assertEqual(book.get(published.row_id).as_row()["score"], snapshot["score"])
        self.assertEqual(book.get(published.row_id).outcome_status, ledger.SUPERSEDED)
        self.assertEqual(len(book.supersedes_chain(correction.row_id)), 2)

    def test_gate_fill_before_publication_is_refused(self):
        row = _row(horizon="24h")
        too_early = datetime.fromisoformat(row.earliest_entry_at.replace("Z", "+00:00"))
        with self.assertRaises(ValueError) as caught:
            ledger.grade(row, 100.0, 110.0, too_early - timedelta(minutes=1))
        self.assertIn("precedes earliest_entry_at", str(caught.exception))

    def test_gate_earliest_entry_is_after_publication(self):
        published = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)
        self.assertGreater(ledger.earliest_entry(published), published)


class GateIdentity(unittest.TestCase):
    """Assets sharing a ticker but not identity cannot be merged accidentally."""

    def test_gate_unverified_identity_is_excluded(self):
        assets = universe(3)
        assets["sol:FAKE"] = crypto_asset(verified=False)
        result = ranking.rank_universe(assets, ranking.config_for("crypto"))
        excluded = {a.asset_id for a in result.excluded}
        self.assertIn("sol:FAKE", excluded)
        self.assertNotIn("sol:FAKE", {a.asset_id for a in result.ranked})

    def test_gate_same_ticker_different_chain_are_separate_rows(self):
        assets = {
            "solana:8RNU...:PURR": crypto_asset(liquidity=600_000.0, momentum=0.07),
            "hyperliquid:PURR": crypto_asset(liquidity=900_000.0, momentum=0.01),
        }
        result = ranking.rank_universe(assets, ranking.config_for("crypto"))
        self.assertEqual(len(result.ranked), 2)
        self.assertEqual(len({a.asset_id for a in result.ranked}), 2)


class GateMissingDataNeverHelps(unittest.TestCase):
    """Missing or stale data cannot silently improve actionability."""

    def test_gate_missing_risk_feature_scores_worst_not_neutral(self):
        assets = universe(5)
        complete = crypto_asset(liquidity=300_000.0, momentum=0.03, drawdown=0.15)
        incomplete = crypto_asset(liquidity=300_000.0, momentum=0.03, drawdown=0.15)
        incomplete["features"]["max_drawdown"] = None
        incomplete["features"]["downside_deviation"] = None
        assets["sol:COMPLETE"] = complete
        assets["sol:INCOMPLETE"] = incomplete

        result = ranking.rank_universe(assets, ranking.config_for("crypto"))
        by_id = {a.asset_id: a for a in result.ranked}
        self.assertIsNotNone(by_id["sol:COMPLETE"].composite)
        self.assertLessEqual(
            by_id["sol:INCOMPLETE"].composite or 0.0,
            by_id["sol:COMPLETE"].composite or 0.0,
            "an asset missing risk data must never outrank an identical asset that has it",
        )
        self.assertTrue(
            any("unavailable" in f for f in by_id["sol:INCOMPLETE"].risk_flags),
            "the missing risk reading must be flagged, not silently dropped",
        )

    def test_gate_stale_price_blocks_actionability(self):
        assets = universe(3)
        assets["sol:STALE"] = crypto_asset(stale=True)
        result = ranking.rank_universe(assets, ranking.config_for("crypto"))
        stale = [a for a in result.excluded if a.asset_id == "sol:STALE"]
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0].decision.state, entry.EXCLUDE)

    def test_gate_missing_tail_is_charged_not_forgiven(self):
        policy = entry.RISK_POLICIES["7d"]
        cost = entry.round_trip_cost(1000.0, 500_000.0, 0.002, "solana_dex")
        with_tail = entry.decide("a", "7d", 0.10, cost, 0.05, True, 0.01, policy)
        without = entry.decide("b", "7d", 0.10, cost, None, False, 0.01, policy)
        self.assertLess(
            without.net_edge,
            with_tail.net_edge,
            "an asset with no tail estimate must not out-score one with a measured tail",
        )


class GateEntryEconomics(unittest.TestCase):
    """A worse entry cannot improve net opportunity, payoff held fixed."""

    def test_gate_higher_cost_lowers_net_edge(self):
        policy = entry.RISK_POLICIES["7d"]
        cheap = entry.round_trip_cost(1000.0, 5_000_000.0, 0.001, "solana_dex")
        dear = entry.round_trip_cost(1000.0, 50_000.0, 0.020, "solana_dex")
        good = entry.decide("a", "7d", 0.10, cheap, 0.05, True, 0.01, policy)
        bad = entry.decide("a", "7d", 0.10, dear, 0.05, True, 0.01, policy)
        self.assertGreater(good.net_edge, bad.net_edge)

    def test_gate_larger_notional_costs_more_in_the_same_book(self):
        small = entry.round_trip_cost(100.0, 200_000.0, 0.002, "solana_dex")
        large = entry.round_trip_cost(10_000.0, 200_000.0, 0.002, "solana_dex")
        self.assertGreater(large.impact, small.impact)

    def test_gate_spread_is_not_double_counted(self):
        charged = entry.round_trip_cost(1000.0, 200_000.0, 0.01, "solana_dex")
        embedded = entry.round_trip_cost(
            1000.0, 200_000.0, 0.01, "solana_dex", spread_in_price=True
        )
        self.assertGreater(charged.total, embedded.total)
        self.assertEqual(embedded.spread, 0.0)

    def test_gate_high_quality_asset_can_be_marked_wait_at_a_poor_entry(self):
        policy = entry.RISK_POLICIES["7d"]
        cost = entry.round_trip_cost(1000.0, 5_000_000.0, 0.001, "solana_dex")
        plan = entry.entry_plan(
            reference_price=120.0,
            zone_low=90.0,
            zone_high=100.0,
            invalidation=85.0,
            expiry_iso="2026-09-19T00:00:00Z",
        )
        self.assertTrue(plan["trigger_required"])
        decision = entry.decide(
            "quality", "7d", 0.20, cost, 0.04, True, 0.005, policy, entry_plan=plan
        )
        self.assertEqual(decision.state, entry.WAIT)

    def test_gate_negative_net_edge_yields_no_qualifying_entry(self):
        policy = entry.RISK_POLICIES["7d"]
        cost = entry.round_trip_cost(1000.0, 100_000.0, 0.01, "solana_dex")
        decision = entry.decide("weak", "7d", 0.005, cost, 0.30, True, 0.05, policy)
        self.assertEqual(decision.state, entry.NO_QUALIFYING_ENTRY)
        self.assertLess(decision.net_edge, 0)

    def test_gate_unpriceable_trade_is_not_actionable(self):
        policy = entry.RISK_POLICIES["7d"]
        cost = entry.round_trip_cost(1000.0, None, 0.002, "solana_dex")
        self.assertIsNone(cost.total)
        decision = entry.decide("x", "7d", 0.50, cost, 0.02, True, 0.01, policy)
        self.assertEqual(decision.state, entry.WATCH)
        self.assertIsNone(decision.net_edge)


class GateNoForcedRecommendations(unittest.TestCase):
    """Zero qualified entries and fewer than 50 candidates are allowed."""

    def test_gate_v1_produces_no_actionable_entries_without_a_validated_forecast(self):
        result = ranking.rank_universe(universe(8), ranking.config_for("crypto"))
        self.assertEqual(result.counts["actionable"], 0)
        self.assertTrue(all(a.decision.net_edge is None for a in result.ranked))

    def test_gate_empty_universe_is_legal(self):
        result = ranking.rank_universe({}, ranking.config_for("crypto"))
        self.assertEqual(result.counts["scored"], 0)
        self.assertEqual(result.ranked, [])

    def test_gate_all_excluded_is_legal(self):
        assets = {f"x{i}": crypto_asset(verified=False) for i in range(4)}
        result = ranking.rank_universe(assets, ranking.config_for("crypto"))
        self.assertEqual(result.counts["eligible"], 0)
        self.assertEqual(result.counts["excluded"], 4)


class GateTraceability(unittest.TestCase):
    """One top-ranked asset is traceable from raw inputs to its displayed rank."""

    def test_gate_composite_equals_the_sum_of_its_contributions(self):
        result = ranking.rank_universe(universe(6), ranking.config_for("crypto"))
        top = result.ranked[0]
        earned = sum(c.contribution or 0.0 for c in top.contributions)
        weight = sum(c.weight for c in top.contributions)
        self.assertAlmostEqual(top.composite, earned / weight, places=6)

    def test_gate_every_contribution_names_a_registered_feature(self):
        result = ranking.rank_universe(universe(6), ranking.config_for("crypto"))
        registry = features.for_asset_class("crypto")
        for asset in result.ranked:
            for contribution in asset.contributions:
                self.assertIn(contribution.feature, registry)


class GateProbabilityDiscipline(unittest.TestCase):
    """Probabilities are withheld when uncalibrated; percentiles are never probabilities."""

    def test_gate_score_type_is_labelled_a_percentile(self):
        result = ranking.rank_universe(universe(5), ranking.config_for("crypto"))
        self.assertEqual(result.score_type, "within_universe_percentile")
        self.assertIn("NOT a probability", result.as_dict()["score_type_note"])

    def test_gate_probability_score_type_requires_a_probability(self):
        with self.assertRaises(ValueError):
            _row(score_type="probability", probability=None)

    def test_gate_probability_outside_unit_interval_is_refused(self):
        with self.assertRaises(ValueError):
            _row(probability=1.4)

    def test_gate_model_is_labelled_heuristic(self):
        cfg = ranking.config_for("crypto").as_dict()
        self.assertEqual(cfg["model_status"], "HEURISTIC")
        self.assertEqual(cfg["validation_status"], "NOT_YET_VALIDATED")


class GateOutcomeHonesty(unittest.TestCase):
    """Overlapping horizons, latency and pending outcomes are handled honestly."""

    def test_gate_outcomes_stay_pending_until_the_horizon_matures(self):
        row = _row(horizon="7d")
        book = ledger.Ledger([row])
        start = datetime.fromisoformat(row.earliest_entry_at.replace("Z", "+00:00"))
        self.assertEqual(len(book.due(start + timedelta(days=3))), 0)
        self.assertEqual(len(book.due(start + timedelta(days=8))), 1)

    def test_gate_accountability_excludes_pending_from_averages(self):
        book = ledger.Ledger()
        matured = book.append(_row(horizon="24h", asset_id="A"))
        book.append(_row(horizon="24h", asset_id="B"))
        start = datetime.fromisoformat(matured.earliest_entry_at.replace("Z", "+00:00"))
        ledger.grade(matured, 100.0, 110.0, start + timedelta(hours=1), benchmark_return=0.02)
        summary = ledger.accountability(book, "24h")
        self.assertEqual(summary["graded"], 1)
        self.assertEqual(summary["pending"], 1)
        self.assertFalse(summary["sample_adequate"])
        self.assertIn("NO DEMONSTRATED EDGE", summary["caveat"])

    def test_gate_void_when_no_tradable_reference_existed(self):
        row = _row(horizon="24h")
        ledger.grade(row, None, None, None)
        self.assertEqual(row.outcome_status, ledger.VOID)
        self.assertIsNone(row.realized_net_return)

    def test_gate_ledger_carries_every_declared_column(self):
        row = _row()
        self.assertEqual(tuple(row.as_row()), ledger.COLUMNS)

    def test_gate_excluded_assets_are_retained_not_discarded(self):
        assets = universe(3)
        assets["sol:BAD"] = crypto_asset(verified=False)
        result = ranking.rank_universe(assets, ranking.config_for("crypto"))
        self.assertEqual(len(result.excluded), 1)
        self.assertIn("retained in the ledger", result.excluded[0].notes[0])


class GateHorizonSeparation(unittest.TestCase):
    """Horizons are never averaged into one universal score."""

    def test_gate_multi_horizon_returns_separate_results(self):
        results = ranking.multi_horizon(universe(5), "crypto")
        self.assertEqual(set(results), set(ranking.HORIZONS))
        digests = {h: r.config.digest() for h, r in results.items()}
        self.assertEqual(len(set(digests.values())), len(ranking.HORIZONS))

    def test_gate_risk_policy_differs_by_horizon(self):
        short = entry.RISK_POLICIES["24h"]
        long = entry.RISK_POLICIES["30d"]
        self.assertGreater(short.kappa, long.kappa)


class GateAssetClassSeparation(unittest.TestCase):
    """The same engine serves equities without importing crypto-only concepts."""

    def test_gate_funding_rate_is_not_an_equity_feature(self):
        self.assertNotIn("funding_rate_8h", features.for_asset_class("equity"))
        self.assertIn("funding_rate_8h", features.for_asset_class("crypto"))

    def test_gate_earnings_yield_is_not_a_crypto_feature(self):
        self.assertNotIn("earnings_yield", features.for_asset_class("crypto"))
        self.assertIn("earnings_yield", features.for_asset_class("equity"))

    def test_gate_equity_universe_ranks(self):
        assets = {
            "us:NEM": _equity(0.03, 1.2, 0.18),
            "us:MPC": _equity(0.09, 0.8, 0.22),
            "us:VLO": _equity(0.07, 1.0, 0.25),
            "us:DELL": _equity(0.05, 1.5, 0.30),
            "us:NVDA": _equity(0.02, 0.4, 0.35),
        }
        result = ranking.rank_universe(assets, ranking.config_for("equity"))
        self.assertEqual(result.counts["eligible"], 5)
        self.assertTrue(all(a.composite is not None for a in result.ranked))

    def test_gate_group_weights_cover_the_registry_exactly(self):
        for asset_class in (features.CRYPTO, features.EQUITY):
            declared = set(ranking.GROUP_WEIGHTS[asset_class])
            actual = set(features.groups(asset_class))
            self.assertEqual(declared, actual, f"{asset_class} weights must match the registry")
            self.assertAlmostEqual(sum(ranking.GROUP_WEIGHTS[asset_class].values()), 1.0, places=9)


class GateCorrelationBudget(unittest.TestCase):
    """Correlated indicators share one budget instead of voting separately."""

    def test_gate_trend_group_weight_is_split_not_multiplied(self):
        result = ranking.rank_universe(universe(6), ranking.config_for("crypto"))
        top = result.ranked[0]
        trend_weight = sum(c.weight for c in top.contributions if c.group == "trend")
        self.assertAlmostEqual(trend_weight, ranking.GROUP_WEIGHTS["crypto"]["trend"], places=6)

    def test_gate_losing_a_feature_keeps_the_group_budget_intact(self):
        assets = universe(6)
        for payload in assets.values():
            payload["features"]["trend_persistence"] = None
        result = ranking.rank_universe(assets, ranking.config_for("crypto"))
        top = result.ranked[0]
        trend_weight = sum(c.weight for c in top.contributions if c.group == "trend")
        self.assertAlmostEqual(
            trend_weight,
            ranking.GROUP_WEIGHTS["crypto"]["trend"],
            places=6,
            msg="a dropped feature returns weight to its own group, not to the model",
        )


class QuantPrimitives(unittest.TestCase):
    def test_zero_dispersion_is_reported_not_divided_by(self):
        section = quant.cross_section("f", {"a": 5.0, "b": 5.0, "c": 5.0})
        self.assertEqual(section.status, quant.ZERO_DISPERSION)
        self.assertFalse(section.usable)

    def test_small_sample_is_labelled(self):
        section = quant.cross_section("f", {"a": 1.0, "b": 2.0})
        self.assertEqual(section.status, quant.LOW_SAMPLE)
        self.assertIn("little information", section.note)

    def test_ranks_are_open_interval_and_ties_average(self):
        ranks = quant.fractional_ranks({"a": 1.0, "b": 1.0, "c": 3.0})
        self.assertEqual(ranks["a"], ranks["b"])
        self.assertTrue(all(0.0 < v < 1.0 for v in ranks.values()))

    def test_expected_shortfall_is_a_non_negative_magnitude(self):
        tail = quant.expected_shortfall([-0.2, -0.1, 0.05, 0.1] * 10)
        self.assertGreaterEqual(tail.expected_shortfall, 0.0)
        self.assertTrue(tail.adequate)

    def test_expected_shortfall_flags_a_short_sample(self):
        tail = quant.expected_shortfall([-0.1, 0.05, 0.2])
        self.assertFalse(tail.adequate)
        self.assertIn("below the", tail.note)

    def test_shrinkage_pulls_a_short_sample_toward_the_prior(self):
        self.assertLess(quant.shrink(1.0, 0.0, n=2), quant.shrink(1.0, 0.0, n=200))

    def test_standard_error_is_not_volatility(self):
        series = [0.02, -0.03, 0.05, -0.04] * 10
        self.assertLess(quant.standard_error(series), quant.ewma_volatility(series))

    def test_outlier_cannot_dominate_a_rank_normalisation(self):
        section = quant.cross_section("f", {"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0, "e": 10_000.0})
        spread = max(section.normalised.values()) - min(section.normalised.values())
        self.assertLess(spread, 1.0)

    def test_missing_values_are_reported_not_imputed(self):
        section = quant.cross_section(
            "f", {"a": 1.0, "b": None, "c": 3.0}, universe=["a", "b", "c"]
        )
        self.assertEqual(section.missing, ["b"])
        self.assertNotIn("b", section.normalised)


def _equity(earnings_yield: float, leverage: float, drawdown: float) -> dict:
    return {
        "display": "equity",
        "identity": {"verified": True},
        "price": 100.0,
        "venue": "us_equity",
        "liquidity_usd": 50_000_000.0,
        "return_series": [0.01, -0.012, 0.008, -0.005] * 10,
        "features": {
            "liquidity_depth": 50_000.0,
            "liquidity_usd_raw": 50_000_000.0,
            "spread_cost": 0.0004,
            "residual_momentum": 0.02,
            "relative_strength_vs_market": 0.01,
            "trend_persistence": 0.55,
            "downside_deviation": 0.012,
            "max_drawdown": drawdown,
            "ewma_volatility": 0.015,
            "extension_from_support": 1.1,
            "earnings_yield": earnings_yield,
            "balance_sheet_quality": leverage,
        },
    }


def _row(**overrides) -> ledger.ForecastRow:
    published = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)
    base = {
        "run_id": "run-1",
        "edition_id": "ed-1",
        "snapshot_at": "2026-09-12T09:55:00Z",
        "published_at": published.isoformat().replace("+00:00", "Z"),
        "earliest_entry_at": ledger.earliest_entry(published).isoformat().replace("+00:00", "Z"),
        "asset_id": "sol:TEST",
        "chain_contract": "solana:8RNU",
        "universe_version": "U1",
        "model_version": ranking.MODEL_VERSION,
        "config_version": "RANK_CFG_V1",
        "code_version": "abc123",
        "horizon": "7d",
        "benchmark": "BTC",
        "rank": 1,
        "score_type": "within_universe_percentile",
        "score": 0.82,
        "reference_quote": 100.0,
        "quote_at": "2026-09-12T09:55:00Z",
        "venue_route": "solana_dex",
        "notional": 1000.0,
        "entry_rule": "limit within zone",
        "estimated_cost": 0.006,
        "gross_forecast": None,
        "net_forecast": None,
    }
    base.update(overrides)
    return ledger.ForecastRow(**base)


if __name__ == "__main__":
    unittest.main()
