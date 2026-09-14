"""Forming periods: a bar that has not closed is not a session.

This module exists because the same defect was found twice in one refresh
cycle, and both times it reached a published ranking before it was caught.

The failure is a close relative of the one documented in
``docs/TERMINAL_RANKING_V2.md`` §8. There, a feed substituted a value the
declared formula could not produce. Here, a feed supplies a value the formula
*can* produce but the market has not finished producing: the current day's bar,
some hours into its 24, presented alongside closed bars as though it were one
of them.

Why that is not a rounding-level concern. Features computed over sessions ask a
categorical question of each bar -- was this an up day or a down day? -- and a
forming bar has no settled answer. Its close is the last trade, not the
session's close, so a bar sitting fractionally above its open moves to the
other bucket the moment the tape ticks down. The up-volume share, the
volume-weighted read on buyers against sellers, is computed by exactly that
bucketing. In the observed case one asset's forming bar crossed its open
mid-session, its up-volume share moved by nine points, and it moved nine places
in the published ranking -- on no new information, only on the clock.

The asymmetry that makes this worth a module rather than a comment: a forming
bar is **systematically biased toward the prevailing direction of the session
so far**, across the whole cross-section at once. It is not noise that averages
out between assets. On a broad up day every asset's forming bar lands in the up
bucket together, every up-volume share is inflated together, and the ranking
reads a market-wide intraday drift as though it were 30 sessions of evidence.

Not every feed is exposed. The rule is about **calendar-aligned** periods -- a
bar stamped with the start of a fixed window that the clock has not yet left.
A rolling series of samples spaced one period apart, each taken at the same
offset from request time, has no forming member: every point closes a full
window ending at the sample. Both shapes appear in this repository's crypto
sources, they look alike in a list of timestamps, and only the first needs
this. :func:`completed` is therefore explicit about which shape it is given
and refuses to guess.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

DAY_SECONDS = 86_400
HOUR_SECONDS = 3_600


def is_complete(period_start: float, period_seconds: float, now: float) -> bool:
    """True when the period opening at ``period_start`` has fully elapsed.

    The boundary is exclusive at the close: a period is complete once ``now``
    has reached its end, not while ``now`` still falls inside it. All three
    arguments are seconds in the same epoch and the same timezone; mixing a
    millisecond stamp with a second stamp here is the obvious way to get a
    silently wrong answer, so callers convert before calling rather than
    passing a unit flag.
    """
    if period_seconds <= 0:
        raise ValueError(f"period_seconds must be positive, got {period_seconds!r}")
    return now >= period_start + period_seconds


def completed(
    bars: Sequence[Any],
    now: float,
    period_seconds: float = DAY_SECONDS,
    start_of: Callable[[Any], float] | None = None,
) -> list[Any]:
    """The bars whose period has closed, in the order given.

    ``start_of`` reads a bar's period START as epoch seconds; it defaults to
    ``bar["t"]``. The distinction matters: a feed stamping bars with their
    close needs a ``start_of`` that subtracts the period, and getting that
    backwards keeps exactly the bar this function exists to drop.

    Every bar is tested, not just the last. A feed that returns bars out of
    order, or that pads a gap with a placeholder for a period still running,
    would defeat a "drop the final element" shortcut -- and the shortcut also
    silently discards a good bar whenever the series happens to end on a
    closed period, which is the normal case between sessions.
    """
    read = start_of if start_of is not None else (lambda b: b["t"])
    return [b for b in bars if is_complete(float(read(b)), period_seconds, now)]


def dropped(
    bars: Sequence[Any],
    now: float,
    period_seconds: float = DAY_SECONDS,
    start_of: Callable[[Any], float] | None = None,
) -> int:
    """How many bars :func:`completed` would exclude.

    Feeds are expected to report this rather than discard it silently. A run
    that drops nothing and a run that drops a bar produce different features
    from the same request, and a reader who cannot tell which happened cannot
    reproduce either.
    """
    return len(bars) - len(completed(bars, now, period_seconds, start_of))


def up_volume_share(
    bars: Sequence[Any],
    window: int,
    open_of: Callable[[Any], float] | None = None,
    close_of: Callable[[Any], float] | None = None,
    volume_of: Callable[[Any], float] | None = None,
) -> float | None:
    """Share of the window's volume that transacted on up bars, or ``None``.

    Pass only bars that have closed -- run :func:`completed` first. This
    function cannot check that for itself, because a bar carries no evidence of
    whether its period has ended; that is precisely why the check has to happen
    upstream, against a clock.

    ``None`` is returned when the window carries no volume at all, and it is
    returned rather than ``0.0`` on the rule in §8: an absent observation is
    never a zero. Zero would read as "every trade was a sell", which is a
    measurement, while the truth is that nothing was measured.
    """
    if window <= 0:
        raise ValueError(f"window must be positive, got {window!r}")
    o = open_of or (lambda b: float(b["o"]))
    c = close_of or (lambda b: float(b["c"]))
    v = volume_of or (lambda b: float(b["v"]))
    recent = list(bars)[-window:]
    total = sum(v(b) for b in recent)
    if total <= 0:
        return None
    return sum(v(b) for b in recent if c(b) > o(b)) / total
