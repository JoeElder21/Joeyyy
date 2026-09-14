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


if __name__ == "__main__":
    unittest.main()
