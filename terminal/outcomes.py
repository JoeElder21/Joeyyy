"""Outcome grading against a tradable reference.

A recommendation published at 6:41 AM cannot be graded from the prior close it
was written on: nobody could trade that price. The reference is the first
regular-session open after publication (or the publication-time quote when the
market was open). A recommendation with no tradable reference is VOID, never
graded on a number that did not exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from terminal import clock

OPEN, HIT, MISS, VOID = "OPEN", "HIT", "MISS", "VOID"
LONG_STANCES = frozenset({"BUY", "ADD", "HOLD"})
SHORT_STANCES = frozenset({"TRIM", "EXIT", "AVOID", "REDUCE"})


@dataclass(frozen=True)
class Observation:
    at: datetime
    price: float
    kind: str  # "open", "close" or "quote"


@dataclass(frozen=True)
class Outcome:
    status: str
    reference_price: float | None
    reference_at: datetime | None
    horizon_end: datetime | None
    realized_return: float | None
    benchmark_return: float | None
    relative_return: float | None
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "reference_price": self.reference_price,
            "reference_at": self.reference_at.isoformat() if self.reference_at else None,
            "horizon_end": self.horizon_end.isoformat() if self.horizon_end else None,
            "realized_return": self.realized_return,
            "benchmark_return": self.benchmark_return,
            "relative_return": self.relative_return,
            "note": self.note,
        }


def tradable_reference(
    published_at: datetime, observations: list[Observation]
) -> Observation | None:
    """The first observation a reader could have traded on.

    Market open at publication: the first quote at or after publication.
    Otherwise: the first regular-session ``open`` print at or after the next open.
    """
    published = clock.to_utc(published_at)
    ordered = sorted(observations, key=lambda o: clock.to_utc(o.at))
    if clock.session_state(published) == "OPEN":
        for obs in ordered:
            if clock.to_utc(obs.at) >= published:
                return obs
        return None
    next_open = clock.to_utc(clock.next_regular_open(published))
    for obs in ordered:
        if obs.kind == "open" and clock.to_utc(obs.at) >= next_open:
            return obs
    return None


def _at_or_after(observations: list[Observation], moment: datetime) -> Observation | None:
    for obs in sorted(observations, key=lambda o: clock.to_utc(o.at)):
        if clock.to_utc(obs.at) >= moment:
            return obs
    return None


def evaluate(
    stance: str,
    published_at: datetime,
    horizon_days: int,
    asset_prices: list[Observation],
    benchmark_prices: list[Observation],
    now: datetime,
) -> Outcome:
    """Grade one recommendation. Long stances win by beating the benchmark;
    reduce stances win when the asset trails it; HOLD wins when it is not
    negative on either measure."""
    stance = stance.upper()
    if stance not in LONG_STANCES | SHORT_STANCES:
        raise ValueError(f"unknown stance {stance!r}")
    reference = tradable_reference(published_at, asset_prices)
    bench_ref = tradable_reference(published_at, benchmark_prices)
    if reference is None or bench_ref is None:
        return Outcome(VOID, None, None, None, None, None, None, "no tradable reference price")
    horizon_end = clock.to_utc(reference.at) + timedelta(days=horizon_days)
    if clock.to_utc(now) < horizon_end:
        return Outcome(
            OPEN,
            reference.price,
            reference.at,
            horizon_end,
            None,
            None,
            None,
            "horizon not reached",
        )
    end_obs = _at_or_after(asset_prices, horizon_end)
    bench_end = _at_or_after(benchmark_prices, horizon_end)
    if end_obs is None or bench_end is None:
        return Outcome(
            OPEN,
            reference.price,
            reference.at,
            horizon_end,
            None,
            None,
            None,
            "horizon price not observed yet",
        )
    realized = round(end_obs.price / reference.price - 1.0, 6)
    bench = round(bench_end.price / bench_ref.price - 1.0, 6)
    relative = round(realized - bench, 6)
    if stance == "HOLD":
        hit = realized >= 0.0 or relative >= 0.0
    elif stance in LONG_STANCES:
        hit = relative > 0.0
    else:
        hit = relative < 0.0
    return Outcome(
        HIT if hit else MISS, reference.price, reference.at, horizon_end, realized, bench, relative
    )


def hit_rate(outcomes: list[Outcome]) -> dict:
    graded = [o for o in outcomes if o.status in (HIT, MISS)]
    hits = sum(1 for o in graded if o.status == HIT)
    return {
        "graded": len(graded),
        "hits": hits,
        "misses": len(graded) - hits,
        "hit_rate": round(hits / len(graded), 4) if graded else None,
        "open": sum(1 for o in outcomes if o.status == OPEN),
        "void": sum(1 for o in outcomes if o.status == VOID),
    }


def brier_score(pairs: list[tuple[float, bool]]) -> float | None:
    """Mean squared error between stated probabilities and what happened."""
    if not pairs:
        return None
    for probability, _ in pairs:
        if not 0.0 <= probability <= 1.0:
            raise ValueError("probabilities must lie in [0, 1]")
    return round(
        sum((p - (1.0 if happened else 0.0)) ** 2 for p, happened in pairs) / len(pairs), 6
    )
