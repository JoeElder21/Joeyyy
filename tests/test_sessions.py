"""Tests for the forming-period rule.

The load-bearing test here is not that ``completed`` drops a bar. It is
:meth:`ExhaustsTheClock.test_a_forming_bar_can_flip_the_feature_it_feeds`,
which reproduces the actual defect: the same closed history plus a forming bar
yields two different up-volume shares depending only on where the forming bar's
last trade happens to sit. That test is the standing reason the module exists,
so it asserts the hazard rather than the fix.
"""

from __future__ import annotations

import unittest

from terminal.sessions import (
    DAY_SECONDS,
    completed,
    dropped,
    is_complete,
    up_volume_share,
)

# A Monday 00:00 UTC open, so the arithmetic in the tests reads as dates.
MONDAY = 1_789_257_600.0
TUESDAY = MONDAY + DAY_SECONDS
WEDNESDAY = MONDAY + 2 * DAY_SECONDS


def bar(start, o, c, v):
    return {"t": start, "o": o, "c": c, "v": v}


class IsComplete(unittest.TestCase):
    def test_a_period_is_incomplete_while_the_clock_is_inside_it(self):
        self.assertFalse(is_complete(MONDAY, DAY_SECONDS, MONDAY))
        self.assertFalse(is_complete(MONDAY, DAY_SECONDS, MONDAY + 1))
        self.assertFalse(is_complete(MONDAY, DAY_SECONDS, MONDAY + DAY_SECONDS - 1))

    def test_a_period_is_complete_at_its_close_and_after(self):
        self.assertTrue(is_complete(MONDAY, DAY_SECONDS, MONDAY + DAY_SECONDS))
        self.assertTrue(is_complete(MONDAY, DAY_SECONDS, MONDAY + DAY_SECONDS + 1))

    def test_the_last_two_hours_of_a_day_are_still_inside_it(self):
        # The observed defect: 22 of 24 hours elapsed reads as complete to the
        # eye and to a "drop nothing, it looks like a full day" feed.
        self.assertFalse(is_complete(MONDAY, DAY_SECONDS, MONDAY + 22 * 3_600))

    def test_a_nonpositive_period_is_rejected_rather_than_answered(self):
        for bad in (0, -1, -DAY_SECONDS):
            with self.assertRaises(ValueError):
                is_complete(MONDAY, bad, MONDAY + DAY_SECONDS)


class Completed(unittest.TestCase):
    def setUp(self):
        self.bars = [
            bar(MONDAY, 10.0, 11.0, 100.0),
            bar(TUESDAY, 11.0, 12.0, 100.0),
            bar(WEDNESDAY, 12.0, 12.5, 100.0),
        ]

    def test_the_forming_bar_is_excluded_and_the_closed_ones_kept(self):
        now = WEDNESDAY + 22 * 3_600
        self.assertEqual([b["t"] for b in completed(self.bars, now)], [MONDAY, TUESDAY])
        self.assertEqual(dropped(self.bars, now), 1)

    def test_nothing_is_dropped_once_every_period_has_closed(self):
        # Between sessions the whole series is valid, and a feed that always
        # discards its last element would throw away a good bar here.
        now = WEDNESDAY + DAY_SECONDS
        self.assertEqual(len(completed(self.bars, now)), 3)
        self.assertEqual(dropped(self.bars, now), 0)

    def test_every_bar_is_tested_not_only_the_last(self):
        # An out-of-order feed defeats a drop-the-final-element shortcut.
        shuffled = [self.bars[2], self.bars[0], self.bars[1]]
        kept = completed(shuffled, WEDNESDAY + 22 * 3_600)
        self.assertEqual([b["t"] for b in kept], [MONDAY, TUESDAY])

    def test_start_of_lets_a_close_stamped_feed_be_read_correctly(self):
        closed_stamped = [{"t": t + DAY_SECONDS} for t in (MONDAY, TUESDAY, WEDNESDAY)]
        now = WEDNESDAY + 22 * 3_600
        kept = completed(closed_stamped, now, start_of=lambda b: b["t"] - DAY_SECONDS)
        self.assertEqual([b["t"] - DAY_SECONDS for b in kept], [MONDAY, TUESDAY])

    def test_getting_the_stamp_convention_backwards_fails_in_both_directions(self):
        now = WEDNESDAY + 22 * 3_600
        # Reading close-stamps as if they were open-stamps shifts every bar a
        # period later, so good bars are discarded: conservative, but wrong.
        closed_stamped = [{"t": t + DAY_SECONDS} for t in (MONDAY, TUESDAY, WEDNESDAY)]
        self.assertEqual(len(completed(closed_stamped, now)), 1)
        # The dangerous direction is the mirror image: subtracting a period
        # from stamps that were already opens makes the forming bar look
        # closed, which is exactly the bar the module exists to remove.
        open_stamped = [{"t": t} for t in (MONDAY, TUESDAY, WEDNESDAY)]
        leaked = completed(open_stamped, now, start_of=lambda b: b["t"] - DAY_SECONDS)
        self.assertEqual(len(leaked), 3)
        self.assertIn(
            WEDNESDAY,
            [b["t"] for b in leaked],
            "a mis-set start_of readmitted the forming bar",
        )

    def test_an_empty_series_is_empty_rather_than_an_error(self):
        self.assertEqual(completed([], WEDNESDAY), [])
        self.assertEqual(dropped([], WEDNESDAY), 0)


class UpVolumeShare(unittest.TestCase):
    def test_share_is_volume_weighted_not_bar_counted(self):
        bars = [
            bar(MONDAY, 10.0, 11.0, 900.0),  # up, heavy
            bar(TUESDAY, 11.0, 10.0, 50.0),  # down, light
            bar(WEDNESDAY, 10.0, 9.0, 50.0),  # down, light
        ]
        # Two of three bars are down, but 90% of the volume traded up.
        self.assertAlmostEqual(up_volume_share(bars, 3), 0.90)

    def test_a_flat_bar_counts_as_not_up(self):
        bars = [bar(MONDAY, 10.0, 10.0, 100.0), bar(TUESDAY, 10.0, 11.0, 100.0)]
        self.assertAlmostEqual(up_volume_share(bars, 2), 0.50)

    def test_window_takes_the_most_recent_bars(self):
        bars = [
            bar(MONDAY, 10.0, 11.0, 100.0),
            bar(TUESDAY, 11.0, 10.0, 100.0),
            bar(WEDNESDAY, 10.0, 9.0, 100.0),
        ]
        self.assertAlmostEqual(up_volume_share(bars, 2), 0.0)

    def test_a_window_with_no_volume_is_none_and_never_zero(self):
        # Zero would read as "every trade was a sell" -- a measurement. None
        # says nothing was measured. docs/TERMINAL_RANKING_V2.md section 8.
        bars = [bar(MONDAY, 10.0, 11.0, 0.0), bar(TUESDAY, 11.0, 10.0, 0.0)]
        self.assertIsNone(up_volume_share(bars, 2))

    def test_a_nonpositive_window_is_rejected(self):
        with self.assertRaises(ValueError):
            up_volume_share([bar(MONDAY, 1.0, 2.0, 1.0)], 0)


class ExhaustsTheClock(unittest.TestCase):
    """Why the module exists, asserted rather than described."""

    CLOSED = [
        bar(MONDAY - 2 * DAY_SECONDS, 10.0, 9.0, 100.0),  # down
        bar(MONDAY - DAY_SECONDS, 9.0, 8.0, 100.0),  # down
        bar(MONDAY, 8.0, 7.0, 100.0),  # down
    ]

    def test_a_forming_bar_can_flip_the_feature_it_feeds(self):
        forming_up = bar(TUESDAY, 7.0, 7.01, 300.0)
        forming_down = bar(TUESDAY, 7.0, 6.99, 300.0)
        # One tick apart, in a bar the market has not closed.
        up = up_volume_share([*self.CLOSED, forming_up], 4)
        down = up_volume_share([*self.CLOSED, forming_down], 4)
        self.assertAlmostEqual(up, 0.50)
        self.assertAlmostEqual(down, 0.0)
        self.assertGreater(
            up - down,
            0.40,
            "a forming bar moved the feature by more than 40 points on a "
            "one-cent difference that the session can still reverse",
        )

    def test_dropping_the_forming_bar_makes_the_two_cases_identical(self):
        now = TUESDAY + 22 * 3_600
        shares = {
            up_volume_share(completed([*self.CLOSED, b], now), 3)
            for b in (bar(TUESDAY, 7.0, 7.01, 300.0), bar(TUESDAY, 7.0, 6.99, 300.0))
        }
        self.assertEqual(shares, {0.0}, "the forming bar must not reach the feature")

    def test_the_bias_is_one_directional_across_a_cross_section(self):
        # On a broad up day every asset's forming bar lands in the up bucket
        # together, so the error does not average out between assets -- the
        # property that makes this a ranking problem and not just noise.
        assets = {
            "A": [bar(MONDAY, 10.0, 9.0, 100.0)],
            "B": [bar(MONDAY, 20.0, 19.0, 100.0)],
            "C": [bar(MONDAY, 30.0, 29.0, 100.0)],
        }
        before = {k: up_volume_share(v, 2) for k, v in assets.items()}
        drifting_up = {
            k: [*v, bar(TUESDAY, v[-1]["c"], v[-1]["c"] * 1.01, 100.0)] for k, v in assets.items()
        }
        after = {k: up_volume_share(v, 2) for k, v in drifting_up.items()}
        self.assertEqual(set(before.values()), {0.0})
        self.assertEqual(set(after.values()), {0.5})
        for name in assets:
            self.assertGreater(
                after[name],
                before[name],
                f"{name} was inflated by the forming bar, as was every other "
                "asset -- a common-mode error, not noise that cancels",
            )


if __name__ == "__main__":
    unittest.main()
