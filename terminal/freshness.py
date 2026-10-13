"""Field-specific freshness with session awareness.

A price is fresh when it is at or after the last regular close (or within a
few hours for 24/7 venues); a fundamental is fresh for a quarter plus filing
lag; a screenshot balance is fresh for a few days and then must be re-marked.
The terminal never leaves an old number standing unlabelled: every board is
LIVE, STALE or DEGRADED, and the label is computed, not typed.

Freshness of the *new* observation is only half the question. A source that
reports a change also reports the value it changed FROM, and that baseline can
silently be an observation this terminal already superseded -- in which case
the stated change steps over everything that happened in between while looking
perfectly well-formed. ``baseline_match`` answers which held observation a
stated baseline actually is, so a stale baseline is caught by arithmetic
rather than by whether the resulting number looks plausible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from terminal import clock

FRESH, STALE, MISSING = "FRESH", "STALE", "MISSING"
LIVE, STALE_BOARD, DEGRADED = "LIVE", "STALE", "DEGRADED"
CURRENT, SUPERSEDED, UNKNOWN = "CURRENT", "SUPERSEDED", "UNKNOWN"

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


@dataclass(frozen=True)
class Baseline:
    """Which held observation a source's stated prior value turned out to be."""

    state: str
    matched_at: datetime | None
    latest_at: datetime | None
    stated: float
    latest_value: float | None
    drift: float | None
    note: str = ""


def baseline_match(
    stated: float,
    observations: dict[datetime, float],
    *,
    tolerance: float = 0.005,
) -> Baseline:
    """Locate a source's stated prior value among the observations we hold.

    ``observations`` maps the moment each reading was taken to its value. The
    answer is CURRENT when the stated baseline is the latest reading we hold,
    SUPERSEDED when it is an earlier one, and UNKNOWN when it is neither -- and
    UNKNOWN is not a lesser result than SUPERSEDED, only a different one: a
    baseline we cannot place is a baseline we cannot check.

    ``drift`` is what the stated baseline misses by: the distance from the
    latest held reading to the stated one, so a SUPERSEDED baseline carries the
    exact amount of change the source's own figure steps over. It is signed
    from the source's point of view -- positive when the source is measuring
    from a higher value than the one we hold.

    The tolerance is absolute and defaults to half a cent, because these are
    currency amounts that should agree to the cent when they agree at all. A
    baseline that matches only loosely has not been identified.
    """
    if tolerance < 0:
        raise ValueError("tolerance must not be negative")
    if not observations:
        return Baseline(UNKNOWN, None, None, stated, None, None, "no observations held")
    stamps = sorted(observations)
    latest_at = stamps[-1]
    latest_value = observations[latest_at]
    # Latest first: when one value was read more than once, the most recent
    # reading of it is the one the source is entitled to be measuring from.
    matched_at = next(
        (at for at in reversed(stamps) if abs(observations[at] - stated) <= tolerance),
        None,
    )
    if matched_at is None:
        return Baseline(
            UNKNOWN,
            None,
            latest_at,
            stated,
            latest_value,
            None,
            "stated baseline matches no observation held for this venue",
        )
    drift = round(stated - latest_value, 10)
    if matched_at == latest_at:
        return Baseline(CURRENT, matched_at, latest_at, stated, latest_value, drift)
    return Baseline(
        SUPERSEDED,
        matched_at,
        latest_at,
        stated,
        latest_value,
        drift,
        f"stated baseline is the {matched_at.isoformat()} reading, "
        f"superseded by {latest_at.isoformat()}",
    )


def banner(status: str, board: str, stamp: str) -> str:
    if status == LIVE:
        return f"{board}: live as of {stamp}"
    if status == STALE_BOARD:
        return f"{board}: STALE, some rows carry their last good mark (as of {stamp})"
    return f"{board}: DEGRADED, a critical source did not refresh (last good {stamp})"
