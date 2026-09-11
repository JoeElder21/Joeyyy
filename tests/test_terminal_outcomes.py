"""Outcome grading against a tradable reference and the benchmark."""

import unittest
from datetime import UTC, datetime

from terminal import outcomes


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def obs(text: str, price: float, kind: str = "open") -> outcomes.Observation:
    return outcomes.Observation(utc(text), price, kind)


ASSET = [
    obs("2026-05-01T20:00:00", 78.0, "close"),
    obs("2026-05-04T13:30:00", 80.0),
    obs("2026-08-03T13:30:00", 96.0),
]
BENCH = [
    obs("2026-05-01T20:00:00", 495.0, "close"),
    obs("2026-05-04T13:30:00", 500.0),
    obs("2026-08-03T13:30:00", 520.0),
]


class OutcomeTests(unittest.TestCase):
    def test_reference_is_the_next_open_not_the_prior_close(self):
        reference = outcomes.tradable_reference(utc("2026-05-01T21:00:00"), ASSET)
        self.assertEqual((reference.price, reference.kind), (80.0, "open"))
        self.assertEqual(outcomes.tradable_reference(utc("2026-05-01T21:00:00"), ASSET[:1]), None)
        # Published pre-market on Friday: the reference is Friday's open, and a Monday print is not it.
        self.assertIsNone(outcomes.tradable_reference(utc("2026-05-01T10:41:00"), ASSET))

    def test_reference_during_the_session_is_the_next_quote(self):
        series = [
            obs("2026-05-01T14:00:00", 79.0, "quote"),
            obs("2026-05-01T15:00:00", 79.5, "quote"),
        ]
        self.assertEqual(
            outcomes.tradable_reference(utc("2026-05-01T14:30:00"), series).price, 79.5
        )

    def test_long_hit_short_miss_and_open(self):
        hit = outcomes.evaluate(
            "BUY", utc("2026-05-01T21:00:00"), 90, ASSET, BENCH, utc("2026-09-01T00:00:00")
        )
        self.assertEqual(hit.status, outcomes.HIT)
        self.assertAlmostEqual(hit.realized_return, 0.2)
        self.assertAlmostEqual(hit.benchmark_return, 0.04)
        self.assertAlmostEqual(hit.relative_return, 0.16)
        miss = outcomes.evaluate(
            "AVOID", utc("2026-05-01T21:00:00"), 90, ASSET, BENCH, utc("2026-09-01T00:00:00")
        )
        self.assertEqual(miss.status, outcomes.MISS)
        early = outcomes.evaluate(
            "BUY", utc("2026-05-01T21:00:00"), 90, ASSET, BENCH, utc("2026-06-01T00:00:00")
        )
        self.assertEqual(early.status, outcomes.OPEN)
        self.assertEqual(early.reference_price, 80.0)

    def test_horizon_observation_must_be_near_the_horizon_end(self):
        late = [obs("2026-05-04T13:30:00", 80.0), obs("2026-09-01T13:30:00", 96.0)]
        result = outcomes.evaluate(
            "BUY", utc("2026-05-01T21:00:00"), 90, late, BENCH, utc("2026-09-15T00:00:00")
        )
        self.assertEqual(result.status, outcomes.OPEN)
        self.assertIn("within 5 days", result.note)

    def test_benchmark_reference_must_share_the_session(self):
        bench_late = [obs("2026-05-05T13:30:00", 500.0), obs("2026-08-03T13:30:00", 520.0)]
        result = outcomes.evaluate(
            "BUY", utc("2026-05-01T21:00:00"), 90, ASSET, bench_late, utc("2026-09-01T00:00:00")
        )
        self.assertEqual(result.status, outcomes.VOID)

    def test_neutral_stances_are_void(self):
        result = outcomes.evaluate(
            "WATCH", utc("2026-05-01T21:00:00"), 90, ASSET, BENCH, utc("2026-09-01T00:00:00")
        )
        self.assertEqual(result.status, outcomes.VOID)
        self.assertIn("no position", result.note)

    def test_void_without_a_tradable_reference(self):
        void = outcomes.evaluate(
            "BUY", utc("2026-05-01T21:00:00"), 30, [], BENCH, utc("2026-09-01T00:00:00")
        )
        self.assertEqual(void.status, outcomes.VOID)
        self.assertIsNone(void.realized_return)

    def test_hold_is_a_hit_when_not_negative_on_either_measure(self):
        flat = [obs("2026-05-04T13:30:00", 80.0), obs("2026-08-03T13:30:00", 80.0)]
        hold = outcomes.evaluate(
            "HOLD", utc("2026-05-01T21:00:00"), 90, flat, BENCH, utc("2026-09-01T00:00:00")
        )
        self.assertEqual(hold.status, outcomes.HIT)
        with self.assertRaises(ValueError):
            outcomes.evaluate(
                "YOLO", utc("2026-05-01T21:00:00"), 90, flat, BENCH, utc("2026-09-01T00:00:00")
            )

    def test_hit_rate_and_brier(self):
        graded = [
            outcomes.Outcome(outcomes.HIT, 1, None, None, 0.1, 0.0, 0.1),
            outcomes.Outcome(outcomes.MISS, 1, None, None, -0.1, 0.0, -0.1),
            outcomes.Outcome(outcomes.OPEN, 1, None, None, None, None, None),
            outcomes.Outcome(outcomes.VOID, None, None, None, None, None, None),
        ]
        rate = outcomes.hit_rate(graded)
        self.assertEqual(
            (rate["graded"], rate["hits"], rate["hit_rate"], rate["open"], rate["void"]),
            (2, 1, 0.5, 1, 1),
        )
        self.assertIsNone(outcomes.hit_rate([])["hit_rate"])
        self.assertAlmostEqual(outcomes.brier_score([(0.8, True), (0.3, False)]), (0.04 + 0.09) / 2)
        self.assertIsNone(outcomes.brier_score([]))
        with self.assertRaises(ValueError):
            outcomes.brier_score([(1.5, True)])


if __name__ == "__main__":
    unittest.main()
