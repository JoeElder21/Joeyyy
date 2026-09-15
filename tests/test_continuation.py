"""Acceptance tests for the continuation scorer.

These are written as claims about behaviour that would be WRONG if violated,
not as restatements of the implementation. The load-bearing ones are the
missing-data tests: a substituted zero is indistinguishable from a real
measurement at read time, so the only place it can be caught is here.
"""

import unittest

from terminal.continuation import (
    BREAK,
    CONTINUE,
    HORIZONS,
    MIN_COVERAGE,
    MISSING_PERSIST,
    NO_SCORE,
    Features,
    deceleration,
    robust_z,
    rsi,
    score,
    score_all,
    up_volume_share,
)


def trending(**over) -> Features:
    """A clean, fully-covered uptrend: aligned, mid-upper range, buying."""
    base = {
        "align": 1,
        "stretch": 0.4,
        "far200": 0.3,
        "range_pos": 0.75,
        "day_pct": 1.0,
        "flow": 0.62,
        "rsi": 60.0,
        "decay": 0.1,
    }
    base.update(over)
    return Features(**base)


class Rsi(unittest.TestCase):
    def test_monotone_rise_pins_at_100(self):
        self.assertEqual(rsi([float(i) for i in range(1, 40)]), 100.0)

    def test_monotone_fall_pins_at_zero(self):
        self.assertEqual(rsi([float(i) for i in range(40, 1, -1)]), 0.0)

    def test_short_history_is_none_not_a_partial_answer(self):
        self.assertIsNone(rsi([1.0, 2.0, 3.0], n=14))

    def test_flat_series_is_none_rather_than_a_neutral_fifty(self):
        # No movement at all means the ratio is undefined. Reporting 50 would
        # put a fabricated "balanced" reading into a coverage count.
        self.assertIsNone(rsi([100.0] * 30))


class UpVolumeShare(unittest.TestCase):
    def test_all_up_days_is_one(self):
        closes = [float(i) for i in range(1, 15)]
        self.assertEqual(up_volume_share(closes, [10.0] * 14, 5), 1.0)

    def test_split_is_volume_weighted_not_day_counted(self):
        # Four small up days and one large down day: counting days says 80%
        # bought, weighting by volume says the opposite. Volume is the claim.
        closes = [10.0, 11.0, 12.0, 13.0, 14.0, 5.0]
        vols = [1.0, 1.0, 1.0, 1.0, 1.0, 96.0]
        self.assertAlmostEqual(up_volume_share(closes, vols, 5), 4.0 / 100.0)

    def test_a_single_missing_volume_voids_the_window(self):
        closes = [float(i) for i in range(1, 15)]
        vols: list = [10.0] * 14
        vols[-2] = None
        self.assertIsNone(up_volume_share(closes, vols, 5))

    def test_window_longer_than_history_is_none(self):
        self.assertIsNone(up_volume_share([1.0, 2.0], [1.0, 1.0], 30))


class Deceleration(unittest.TestCase):
    def test_same_pace_is_zero(self):
        self.assertAlmostEqual(deceleration(0.07, 7, 0.30, 30), 0.0, places=9)

    def test_stalled_recent_window_is_one(self):
        self.assertAlmostEqual(deceleration(0.0, 7, 0.30, 30), 1.0)

    def test_accelerating_is_negative(self):
        self.assertLess(deceleration(0.20, 7, 0.30, 30), 0.0)

    def test_undefined_against_a_falling_trend(self):
        # "Is this decline decelerating?" is a different question with the
        # opposite sign; answering it here would let a falling asset earn a
        # persistence reading.
        self.assertIsNone(deceleration(-0.01, 7, -0.30, 30))


class RobustZ(unittest.TestCase):
    def test_zero_dispersion_is_none_not_zero(self):
        self.assertIsNone(robust_z(5.0, [5.0, 5.0, 5.0, 5.0]))

    def test_outlier_scores_far_from_the_pack(self):
        peers = [1.0, 1.1, 0.9, 1.05, 12.0]
        self.assertGreater(robust_z(12.0, peers), 3.0)


class HorizonBehaviour(unittest.TestCase):
    def test_every_horizon_scores(self):
        got = score_all(trending())
        self.assertEqual(set(got), set(HORIZONS))
        for s in got.values():
            self.assertIsNotNone(s.value)

    def test_extension_is_punished_hardest_at_the_short_horizon(self):
        stretched = trending(stretch=3.0, decay=0.9)
        self.assertLess(score(stretched, "3d").value, score(stretched, "30d").value)

    def test_a_stalled_move_ranks_below_a_running_one_at_equal_extension(self):
        # The central claim of the module: two assets identical in level, one
        # still advancing and one flat-lined, must not score the same.
        running = trending(decay=-0.5)
        stalled = trending(decay=1.0)
        for h in HORIZONS:
            self.assertGreater(
                score(running, h).value, score(stalled, h).value, f"deceleration ignored at {h}"
            )

    def test_broken_trend_is_BREAK_at_every_horizon_whatever_the_score(self):
        broken = trending(align=-1, flow=0.95, rsi=68.0, decay=-1.0)
        for h in HORIZONS:
            self.assertEqual(score(broken, h).verdict, BREAK)

    def test_published_value_and_label_agree(self):
        # A score rendered as 45 must never carry the band label for 44.
        for decay in [i / 40.0 for i in range(-20, 45)]:
            s = score(trending(decay=decay), "7d")
            if s.value is None or s.verdict == BREAK:
                continue
            expect = (
                CONTINUE
                if s.value >= 62
                else "MIXED"
                if s.value >= 45
                else "PULLBACK RISK"
                if s.value >= 30
                else "PULLBACK"
            )
            self.assertEqual(s.verdict, expect, f"value {s.value} labelled {s.verdict}")

    def test_unknown_horizon_raises_rather_than_defaulting(self):
        with self.assertRaises(ValueError):
            score(trending(), "90d")


class MissingNeverHelps(unittest.TestCase):
    def test_below_minimum_coverage_the_score_is_withheld(self):
        thin = Features(align=1, range_pos=0.8)
        s = score(thin, "7d")
        self.assertIsNone(s.value)
        self.assertEqual(s.verdict, NO_SCORE)
        self.assertLess(s.coverage, MIN_COVERAGE)

    def test_absent_feature_lowers_coverage_rather_than_scoring_neutral(self):
        full = score(trending(), "7d")
        partial = score(trending(flow=None), "7d")
        self.assertLess(partial.coverage, full.coverage)

    def test_an_asset_specific_gap_is_charged_as_the_worst_case(self):
        # Exhaustion terms are risk readings: an asset that cannot produce one
        # is charged the worst case, never a convenient neutral. So the gap
        # scores strictly worse than a benign reading, and no better than the
        # most adverse one -- which it ties, because that IS the worst case.
        gap = score(trending(stretch=None), "7d").value
        benign = score(trending(stretch=0.0), "7d").value
        worst = score(trending(stretch=3.0), "7d").value
        self.assertLess(gap, benign)
        self.assertLessEqual(gap, worst)

    def test_score_never_rises_as_an_exhaustion_input_worsens(self):
        # Monotonicity is what forecloses the dilution failure. Under a
        # present-weights average, introducing a zero-valued exhaustion term
        # LIFTS the score, so a feed could improve any asset by reporting 0.0
        # for things it never measured. With a fixed divisor the score can only
        # fall -- check that across every exhaustion input.
        for field_name, worse in (
            ("stretch", [0.0, 0.5, 1.5, 3.0, 6.0]),
            ("far200", [0.0, 0.5, 1.5, 3.0, 6.0]),
            ("decay", [-1.0, 0.0, 0.5, 1.0, 2.0]),
            ("rsi", [70.0, 75.0, 85.0, 95.0]),
        ):
            for horizon in HORIZONS:
                vals = [score(trending(**{field_name: v}), horizon).value for v in worse]
                # strict=False is required, not laziness: the two operands are
                # deliberately offset by one, so strict=True would raise.
                for earlier, later in zip(vals, vals[1:], strict=False):
                    self.assertLessEqual(
                        later,
                        earlier,
                        f"{field_name} at {horizon}: score rose from {earlier} "
                        f"to {later} as the input worsened",
                    )

    def test_a_missing_persistence_term_never_outscores_a_real_one(self):
        # The mirror of the exhaustion dilution failure, and the one that
        # actually reached a published board. Persistence was averaged over
        # the terms PRESENT, so dropping a below-average reading raised the
        # mean: flow=0.35 scored 51 at 7d while flow=None scored 61. A feed
        # that served nothing beat a feed that served bad news.
        base = {
            "align": 1,
            "stretch": 0.5,
            "far200": 0.3,
            "range_pos": 0.8,
            "day_pct": 0.5,
            "rsi": 62.0,
            "decay": 0.4,
        }
        for horizon in HORIZONS:
            absent = score(Features(**base, flow=None), horizon).value
            for reading in (0.0, 0.10, 0.35):
                present = score(Features(**base, flow=reading), horizon).value
                self.assertLessEqual(
                    absent,
                    present,
                    f"{horizon}: no flow scored {absent} against {present} for a real "
                    f"flow of {reading} -- a gap must never beat a measurement",
                )

    def test_a_missing_persistence_term_keeps_its_weight_in_the_divisor(self):
        # The mechanism, asserted directly rather than through an outcome:
        # the weight of every non-systemic term is present whether or not the
        # reading was, so the denominator cannot shrink.
        base = {
            "align": 1,
            "stretch": 0.5,
            "far200": 0.3,
            "range_pos": 0.8,
            "day_pct": 0.5,
            "rsi": 62.0,
            "decay": 0.4,
        }
        full = score(Features(**base, flow=0.8), "7d")
        gapped = score(Features(**base, flow=None), "7d")
        self.assertEqual(
            sum(w for _, _, w in full.persist),
            sum(w for _, _, w in gapped.persist),
            "the persistence divisor shrank when a reading went missing",
        )
        self.assertIn("flow", [n for n, _, _ in gapped.persist])
        self.assertEqual(
            [v for n, v, _ in gapped.persist if n == "flow"],
            [MISSING_PERSIST],
            "an unmeasured persistence term must earn nothing, not be dropped",
        )

    def test_a_systemic_persistence_gap_is_dropped_weight_and_all(self):
        # The exception: a term no feed serves for anyone is the analyst's
        # problem, not the asset's, so it leaves the divisor entirely rather
        # than scoring every asset zero for it.
        base = {
            "align": 1,
            "stretch": 0.5,
            "far200": 0.3,
            "range_pos": 0.8,
            "day_pct": 0.5,
            "rsi": 62.0,
            "decay": 0.4,
        }
        charged = score(Features(**base, flow=None), "7d")
        dropped = score(Features(**base, flow=None), "7d", systemic_gaps={"flow"})
        self.assertNotIn("flow", [n for n, _, _ in dropped.persist])
        self.assertGreater(
            dropped.value,
            charged.value,
            "a systemic gap must not be charged like an asset-specific one",
        )

    def test_coverage_records_the_gap_either_way(self):
        honest = score(trending(stretch=None, far200=None), "7d")
        measured = score(trending(stretch=0.0, far200=0.0), "7d")
        self.assertLess(honest.coverage, measured.coverage)

    def test_a_systemic_gap_is_dropped_rather_than_charged(self):
        # A feed outage is a fact about the pipeline, not about the asset.
        # Charging every asset the worst case for one missing API key would
        # rank a whole asset class below another for the analyst's reason.
        charged = score(trending(decay=None), "7d")
        dropped = score(trending(decay=None), "7d", systemic_gaps={"decay"})
        self.assertLess(charged.value, dropped.value)
        # And the dropped term leaves no trace in the exhaustion components.
        self.assertNotIn("decay", {n for n, _, _ in dropped.exhaust})

    def test_a_systemic_gap_still_costs_coverage(self):
        # Dropping the charge does not make the reading exist. Coverage has to
        # keep saying the score rests on less than a complete asset.
        dropped = score(trending(decay=None), "7d", systemic_gaps={"decay"})
        full = score(trending(), "7d")
        self.assertLess(dropped.coverage, full.coverage)

    def test_components_are_returned_so_disagreement_can_be_shown(self):
        s = score(trending(flow=0.95, stretch=2.9), "7d")
        names_p = {n for n, _, _ in s.persist}
        names_e = {n for n, _, _ in s.exhaust}
        self.assertIn("flow", names_p)
        self.assertIn("stretch", names_e)


if __name__ == "__main__":
    unittest.main()
