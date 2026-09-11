"""The market clock: ET wall time, DST drift, sessions, starts-vs-ready."""

import unittest
from datetime import UTC, date, datetime, time

from terminal import clock


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


class ClockTests(unittest.TestCase):
    def test_fixed_utc_cron_drifts_an_hour_in_standard_time(self):
        self.assertEqual(clock.to_et(utc("2026-07-01T10:00:00")).hour, 6)
        self.assertEqual(clock.to_et(utc("2026-11-15T10:00:00")).hour, 5)
        windows = clock.dst_drift(10, 0, time(6, 0), 2026)
        self.assertEqual(
            [(w.starts, w.ends, w.fires_at_et) for w in windows],
            [
                (date(2026, 1, 1), date(2026, 3, 7), "05:00"),
                (date(2026, 11, 1), date(2026, 12, 31), "05:00"),
            ],
        )
        self.assertEqual(clock.et_wall_time_in_utc(6, 0, date(2026, 12, 1)), (11, 0))

    def test_session_states_and_holidays(self):
        self.assertEqual(clock.session_state(utc("2026-09-11T10:41:00")), "PRE")
        self.assertEqual(clock.session_state(utc("2026-09-11T14:00:00")), "OPEN")
        self.assertEqual(clock.session_state(utc("2026-09-11T20:30:00")), "AFTER")
        self.assertEqual(clock.session_state(utc("2026-09-12T14:00:00")), "CLOSED")
        self.assertEqual(clock.session_state(utc("2026-09-07T14:00:00")), "CLOSED")
        self.assertFalse(clock.is_trading_day(date(2026, 11, 26)))
        with self.assertRaises(ValueError):
            clock.is_trading_day(date(2031, 1, 6))

    def test_last_close_and_next_open_skip_weekends_and_holidays(self):
        friday_pre = utc("2026-09-11T10:41:00")
        self.assertEqual(
            clock.last_regular_close(friday_pre).isoformat(), "2026-09-10T16:00:00-04:00"
        )
        self.assertEqual(
            clock.next_regular_open(friday_pre).isoformat(), "2026-09-11T09:30:00-04:00"
        )
        friday_after = utc("2026-09-11T21:00:00")
        self.assertEqual(
            clock.next_regular_open(friday_after).isoformat(), "2026-09-14T09:30:00-04:00"
        )
        after_labor_day_weekend = utc("2026-09-07T12:00:00")
        self.assertEqual(
            clock.last_regular_close(after_labor_day_weekend).isoformat(),
            "2026-09-04T16:00:00-04:00",
        )

    def test_starts_vs_ready_is_honest_about_the_lag(self):
        label = clock.starts_vs_ready(utc("2026-09-11T10:00:00"), utc("2026-09-11T10:41:00")).label
        self.assertEqual(label, "starts 6:00 AM, ready 6:41 AM (41 min)")
        with self.assertRaises(ValueError):
            clock.starts_vs_ready(utc("2026-09-11T10:41:00"), utc("2026-09-11T10:00:00"))

    def test_naive_datetimes_are_refused_and_stamps_name_the_zone(self):
        with self.assertRaises(ValueError):
            clock.to_et(datetime(2026, 9, 11, 6, 0))
        self.assertEqual(clock.stamp(utc("2026-09-11T10:41:00")), "Fri Sep 11, 2026, 6:41 AM ET")
        self.assertEqual(clock.calendar_covered_through(), 2026)


if __name__ == "__main__":
    unittest.main()
