"""Field-level freshness and the board banners derived from it."""

import unittest
from datetime import UTC, datetime

from terminal import freshness


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


class FreshnessTests(unittest.TestCase):
    NOW = utc("2026-09-11T10:41:00")

    def test_equity_price_follows_the_session_clock(self):
        fresh = freshness.assess("equity_price", utc("2026-09-10T20:00:00"), self.NOW)
        self.assertEqual(fresh.state, freshness.FRESH)
        stale = freshness.assess("equity_price", utc("2026-09-09T20:00:00"), self.NOW)
        self.assertEqual(stale.state, freshness.STALE)

    def test_wall_clock_fields_use_their_limits(self):
        self.assertEqual(
            freshness.assess("crypto_price", utc("2026-09-11T05:00:00"), self.NOW).state,
            freshness.FRESH,
        )
        self.assertEqual(
            freshness.assess("crypto_price", utc("2026-09-11T04:00:00"), self.NOW).state,
            freshness.STALE,
        )
        self.assertEqual(
            freshness.assess("balance_screenshot", utc("2026-09-09T17:13:00"), self.NOW).state,
            freshness.FRESH,
        )
        self.assertEqual(
            freshness.assess("catalyst", utc("2026-09-01T00:00:00"), self.NOW).state,
            freshness.STALE,
        )

    def test_missing_future_and_unknown_fields(self):
        self.assertEqual(freshness.assess("equity_price", None, self.NOW).state, freshness.MISSING)
        with self.assertRaises(ValueError):
            freshness.assess("news", utc("2026-09-12T00:00:00"), self.NOW)
        with self.assertRaises(ValueError):
            freshness.assess("weather", self.NOW, self.NOW)

    def test_board_status_rules(self):
        fresh = freshness.Freshness("equity_price", freshness.FRESH, self.NOW, 0.0, "x")
        stale = freshness.Freshness("equity_price", freshness.STALE, self.NOW, 30.0, "x")
        missing = freshness.Freshness("equity_price", freshness.MISSING, None, None, "x")
        self.assertEqual(freshness.board_status([]), freshness.DEGRADED)
        self.assertEqual(freshness.board_status([fresh, fresh]), freshness.LIVE)
        self.assertEqual(freshness.board_status([fresh, fresh, stale]), freshness.STALE_BOARD)
        self.assertEqual(freshness.board_status([fresh, stale, stale]), freshness.DEGRADED)
        self.assertEqual(freshness.board_status([fresh, fresh, fresh, missing]), freshness.DEGRADED)
        self.assertIn("DEGRADED", freshness.banner(freshness.DEGRADED, "Board", "now"))


class BaselineTests(unittest.TestCase):
    """A source states what it changed FROM, and that figure can be stale.

    The shape these pin down was found in a real account update: every venue's
    stated prior value matched an earlier capture rather than the later one
    that had replaced it, so a well-formed, internally consistent change figure
    stepped straight over an entire capture. Nothing about the numbers looked
    wrong; the only way to catch it was to ask which reading the baseline was.
    """

    EARLY = utc("2026-09-14T05:07:00")
    LATE = utc("2026-09-14T21:34:00")

    # Synthetic figures. Nothing in this repository carries a real balance.
    def held(self) -> dict:
        return {self.EARLY: 12_000.00, self.LATE: 11_250.00}

    def test_a_baseline_matching_the_latest_reading_is_current(self):
        found = freshness.baseline_match(11_250.00, self.held())
        self.assertEqual(found.state, freshness.CURRENT)
        self.assertEqual(found.matched_at, self.LATE)
        self.assertEqual(found.drift, 0.0)

    def test_a_baseline_matching_an_earlier_reading_is_superseded(self):
        found = freshness.baseline_match(12_000.00, self.held())
        self.assertEqual(found.state, freshness.SUPERSEDED)
        self.assertEqual(found.matched_at, self.EARLY)
        self.assertEqual(found.latest_at, self.LATE)
        # The drift is exactly the change the source's own figure steps over.
        self.assertAlmostEqual(found.drift, 750.00, places=2)
        self.assertIn("superseded", found.note)

    def test_an_unplaceable_baseline_is_unknown_rather_than_superseded(self):
        # Neither held reading. This is a different failure from a stale
        # baseline and must not be reported as one -- we cannot say what the
        # source measured from, only that it is not something we hold.
        found = freshness.baseline_match(12_500.00, self.held())
        self.assertEqual(found.state, freshness.UNKNOWN)
        self.assertIsNone(found.matched_at)
        self.assertIsNone(found.drift)
        self.assertEqual(found.latest_at, self.LATE)

    def test_matching_is_to_the_cent_not_approximate(self):
        # Two cents out is not this reading. A loose match would let a genuinely
        # different figure be filed as one we already hold.
        self.assertEqual(freshness.baseline_match(11_250.02, self.held()).state, freshness.UNKNOWN)
        self.assertEqual(
            freshness.baseline_match(11_250.02, self.held(), tolerance=0.05).state,
            freshness.CURRENT,
        )

    def test_a_repeated_value_resolves_to_its_most_recent_reading(self):
        # An unchanged balance read twice is CURRENT, not SUPERSEDED: the source
        # is entitled to be measuring from the later of two identical readings.
        mid = utc("2026-09-14T12:00:00")
        found = freshness.baseline_match(
            11_250.00, {self.EARLY: 12_000.00, mid: 11_250.00, self.LATE: 11_250.00}
        )
        self.assertEqual(found.state, freshness.CURRENT)
        self.assertEqual(found.matched_at, self.LATE)

    def test_no_observations_and_a_negative_tolerance(self):
        empty = freshness.baseline_match(1.0, {})
        self.assertEqual(empty.state, freshness.UNKNOWN)
        self.assertIsNone(empty.latest_at)
        with self.assertRaises(ValueError):
            freshness.baseline_match(1.0, self.held(), tolerance=-0.01)


if __name__ == "__main__":
    unittest.main()
