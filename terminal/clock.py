"""The market clock: America/New_York, DST-aware, session-aware.

Every published timestamp in the terminal is derived through this module so a
"6 AM run" means 6 AM Eastern in both halves of the year. Cloud schedules are
expressed in UTC and do not follow DST; :func:`dst_drift` makes that gap
explicit instead of letting the page print the wrong local hour.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)

# NYSE full-day closures. Maintained by hand; the health view prints the last
# year covered so a run after that year is visibly running on an unknown calendar.
NYSE_HOLIDAYS: dict[int, frozenset[date]] = {
    2026: frozenset(
        {
            date(2026, 1, 1),
            date(2026, 1, 19),
            date(2026, 2, 16),
            date(2026, 4, 3),
            date(2026, 5, 25),
            date(2026, 6, 19),
            date(2026, 7, 3),
            date(2026, 9, 7),
            date(2026, 11, 26),
            date(2026, 12, 25),
        }
    ),
}


def calendar_covered_through() -> int:
    return max(NYSE_HOLIDAYS)


def ensure_aware(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        raise ValueError("naive datetimes are not accepted; pass a timezone-aware moment")
    return moment


def to_et(moment: datetime) -> datetime:
    return ensure_aware(moment).astimezone(ET)


def to_utc(moment: datetime) -> datetime:
    return ensure_aware(moment).astimezone(UTC)


def is_trading_day(day: date) -> bool:
    if day.weekday() >= 5:
        return False
    holidays = NYSE_HOLIDAYS.get(day.year)
    if holidays is None:
        raise ValueError(f"no NYSE calendar for {day.year}; extend NYSE_HOLIDAYS first")
    return day not in holidays


def session_state(moment: datetime) -> str:
    """``PRE``, ``OPEN``, ``AFTER`` on a trading day; ``CLOSED`` otherwise."""
    local = to_et(moment)
    if not is_trading_day(local.date()):
        return "CLOSED"
    now = local.time()
    if now < REGULAR_OPEN:
        return "PRE"
    if now < REGULAR_CLOSE:
        return "OPEN"
    return "AFTER"


def last_regular_close(moment: datetime) -> datetime:
    """The most recent 4:00 PM ET regular close at or before ``moment``."""
    local = to_et(moment)
    day = local.date()
    if not (is_trading_day(day) and local.time() >= REGULAR_CLOSE):
        day -= timedelta(days=1)
        while not is_trading_day(day):
            day -= timedelta(days=1)
    return datetime.combine(day, REGULAR_CLOSE, tzinfo=ET)


def next_regular_open(moment: datetime) -> datetime:
    """The first 9:30 AM ET regular open strictly after ``moment``."""
    local = to_et(moment)
    day = local.date()
    if not (is_trading_day(day) and local.time() < REGULAR_OPEN):
        day += timedelta(days=1)
        while not is_trading_day(day):
            day += timedelta(days=1)
    return datetime.combine(day, REGULAR_OPEN, tzinfo=ET)


def et_wall_time_in_utc(hour: int, minute: int, on: date) -> tuple[int, int]:
    """The UTC hour and minute at which ``hour:minute`` ET falls on ``on``."""
    local = datetime.combine(on, time(hour, minute), tzinfo=ET)
    utc = local.astimezone(UTC)
    return utc.hour, utc.minute


@dataclass(frozen=True)
class DriftWindow:
    starts: date
    ends: date
    fires_at_et: str


def dst_drift(
    cron_hour_utc: int, cron_minute_utc: int, target_et: time, year: int
) -> list[DriftWindow]:
    """Days in ``year`` on which a fixed-UTC cron fires at a different ET wall time
    than ``target_et``. A cron pinned to 10:00 UTC is 6:00 AM EDT but 5:00 AM EST."""
    windows: list[DriftWindow] = []
    day = date(year, 1, 1)
    current: DriftWindow | None = None
    while day.year == year:
        fired = datetime.combine(day, time(cron_hour_utc, cron_minute_utc), tzinfo=UTC)
        local = fired.astimezone(ET).time().replace(second=0, microsecond=0)
        if local != target_et:
            label = local.strftime("%H:%M")
            if current is None or current.fires_at_et != label:
                if current is not None:
                    windows.append(current)
                current = DriftWindow(day, day, label)
            else:
                current = DriftWindow(current.starts, day, label)
        elif current is not None:
            windows.append(current)
            current = None
        day += timedelta(days=1)
    if current is not None:
        windows.append(current)
    return windows


@dataclass(frozen=True)
class StartsVsReady:
    scheduled_et: str
    ready_et: str
    lag_minutes: int

    @property
    def label(self) -> str:
        return f"starts {self.scheduled_et}, ready {self.ready_et} ({self.lag_minutes} min)"


def starts_vs_ready(scheduled: datetime, ready: datetime) -> StartsVsReady:
    """The honest freshness stamp: when the run began and when the page was ready."""
    started, done = to_et(scheduled), to_et(ready)
    lag = int(round((done - started).total_seconds() / 60))
    if lag < 0:
        raise ValueError("a run cannot be ready before it was scheduled")
    return StartsVsReady(started.strftime("%-I:%M %p"), done.strftime("%-I:%M %p"), lag)


def stamp(moment: datetime) -> str:
    """The page's human stamp, always in ET with the zone named."""
    local = to_et(moment)
    return local.strftime("%a %b %-d, %Y, %-I:%M %p ET")
