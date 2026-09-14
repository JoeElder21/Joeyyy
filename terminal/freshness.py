"""Field-specific freshness with session awareness.

A price is fresh when it is at or after the last regular close (or within a
few hours for 24/7 venues); a fundamental is fresh for a quarter plus filing
lag; a screenshot balance is fresh for a few days and then must be re-marked.
The terminal never leaves an old number standing unlabelled: every board is
LIVE, STALE or DEGRADED, and the label is computed, not typed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from terminal import clock

FRESH, STALE, MISSING = "FRESH", "STALE", "MISSING"
LIVE, STALE_BOARD, DEGRADED = "LIVE", "STALE", "DEGRADED"

# Wall-clock limits for fields that do not follow the equity session.
LIMITS: dict[str, timedelta] = {
    "crypto_price": timedelta(hours=6),
    "onchain": timedelta(hours=24),
    "news": timedelta(days=3),
    "catalyst": timedelta(days=7),
    "fundamentals": timedelta(days=100),
    "balance_screenshot": timedelta(days=5),
    "options_mark": timedelta(days=1),
}
CRITICAL_FIELDS = frozenset({"equity_price", "crypto_price", "balance_screenshot"})


@dataclass(frozen=True)
class Freshness:
    field: str
    state: str
    observed_at: datetime | None
    age_hours: float | None
    limit: str
    note: str = ""


def assess(field: str, observed_at: datetime | None, now: datetime) -> Freshness:
    """Grade one observation. ``equity_price`` follows the session clock."""
    if observed_at is None:
        return Freshness(field, MISSING, None, None, "n/a", "no observation")
    observed = clock.to_utc(observed_at)
    now_utc = clock.to_utc(now)
    if observed > now_utc + timedelta(minutes=5):
        raise ValueError(f"{field}: observation is in the future")
    age = (now_utc - observed).total_seconds() / 3600
    if field == "equity_price":
        last_close = clock.last_regular_close(now_utc)
        state = FRESH if observed >= last_close - timedelta(minutes=1) else STALE
        return Freshness(field, state, observed, round(age, 2), "last regular close")
    limit = LIMITS.get(field)
    if limit is None:
        raise ValueError(f"no freshness limit is defined for field {field!r}")
    state = FRESH if observed >= now_utc - limit else STALE
    return Freshness(field, state, observed, round(age, 2), f"{limit.total_seconds() / 3600:g}h")


def board_status(items: list[Freshness]) -> str:
    """LIVE when everything is fresh; DEGRADED when a critical field is missing or
    more than half of the observations are stale; STALE otherwise."""
    if not items:
        return DEGRADED
    if any(item.state == MISSING and item.field in CRITICAL_FIELDS for item in items):
        return DEGRADED
    stale = sum(1 for item in items if item.state != FRESH)
    if stale == 0:
        return LIVE
    if stale * 2 > len(items):
        return DEGRADED
    return STALE_BOARD


def banner(status: str, board: str, stamp: str) -> str:
    if status == LIVE:
        return f"{board}: live as of {stamp}"
    if status == STALE_BOARD:
        return f"{board}: STALE, some rows carry their last good mark (as of {stamp})"
    return f"{board}: DEGRADED, a critical source did not refresh (last good {stamp})"
