"""Pure technical-indicator math over daily candles.

Every function returns ``None`` rather than guessing when the series is too
short. That is deliberate: a 200-day average computed from 40 days of data
would silently poison a hold-or-sell decision.

Candles are Schwab price-history dicts with ``open``/``high``/``low``/
``close``/``volume``/``datetime`` keys, oldest first.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

Candle = dict[str, Any]

#: Sessions per year, used to annualize daily realized volatility.
TRADING_DAYS = 252


def closes(candles: Sequence[Candle]) -> list[float]:
    return [float(c["close"]) for c in candles if c.get("close") is not None]


def volumes(candles: Sequence[Candle]) -> list[float]:
    return [float(c.get("volume") or 0.0) for c in candles]


def sma(values: Sequence[float], window: int) -> float | None:
    if window <= 0 or len(values) < window:
        return None
    return sum(values[-window:]) / window


def ema_series(values: Sequence[float], window: int) -> list[float] | None:
    """Exponential moving average seeded with the first ``window`` mean."""
    if window <= 0 or len(values) < window:
        return None
    multiplier = 2.0 / (window + 1.0)
    current = sum(values[:window]) / window
    series = [current]
    for value in values[window:]:
        current = (value - current) * multiplier + current
        series.append(current)
    return series


def ema(values: Sequence[float], window: int) -> float | None:
    series = ema_series(values, window)
    return series[-1] if series else None


def rsi(values: Sequence[float], window: int = 14) -> float | None:
    """Wilder's smoothed relative strength index."""
    if len(values) < window + 1:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(values, values[1:], strict=False):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains[:window]) / window
    avg_loss = sum(losses[:window]) / window
    for gain, loss in zip(gains[window:], losses[window:], strict=False):
        avg_gain = (avg_gain * (window - 1) + gain) / window
        avg_loss = (avg_loss * (window - 1) + loss) / window

    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    strength = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + strength))


@dataclass(frozen=True)
class Macd:
    line: float
    signal: float
    histogram: float


def macd(
    values: Sequence[float],
    fast: int = 12,
    slow: int = 26,
    signal_window: int = 9,
) -> Macd | None:
    fast_series = ema_series(values, fast)
    slow_series = ema_series(values, slow)
    if fast_series is None or slow_series is None:
        return None
    # The fast series starts earlier; align both to their common tail.
    overlap = min(len(fast_series), len(slow_series))
    line_series = [fast_series[-overlap:][i] - slow_series[-overlap:][i] for i in range(overlap)]
    signal_series = ema_series(line_series, signal_window)
    if signal_series is None:
        return None
    line = line_series[-1]
    signal_value = signal_series[-1]
    return Macd(line=line, signal=signal_value, histogram=line - signal_value)


def true_ranges(candles: Sequence[Candle]) -> list[float]:
    ranges: list[float] = []
    for previous, current in zip(candles, candles[1:], strict=False):
        high = float(current["high"])
        low = float(current["low"])
        prior_close = float(previous["close"])
        ranges.append(max(high - low, abs(high - prior_close), abs(low - prior_close)))
    return ranges


def atr(candles: Sequence[Candle], window: int = 14) -> float | None:
    """Average true range — the volatility unit used to size stop distance."""
    ranges = true_ranges(candles)
    if len(ranges) < window:
        return None
    current = sum(ranges[:window]) / window
    for value in ranges[window:]:
        current = (current * (window - 1) + value) / window
    return current


def daily_returns(values: Sequence[float]) -> list[float]:
    return [
        (current / previous) - 1.0
        for previous, current in zip(values, values[1:], strict=False)
        if previous
    ]


def realized_volatility(values: Sequence[float], window: int = 30) -> float | None:
    """Annualized standard deviation of daily returns, as a decimal fraction."""
    returns = daily_returns(values)
    if len(returns) < window:
        return None
    sample = returns[-window:]
    mean = sum(sample) / len(sample)
    variance = sum((value - mean) ** 2 for value in sample) / (len(sample) - 1)
    return math.sqrt(variance) * math.sqrt(TRADING_DAYS)


def max_drawdown(values: Sequence[float]) -> float | None:
    """Worst peak-to-trough decline in the series, as a negative fraction."""
    if len(values) < 2:
        return None
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak:
            worst = min(worst, (value / peak) - 1.0)
    return worst


def change_over(values: Sequence[float], sessions: int) -> float | None:
    """Fractional price change across the last ``sessions`` sessions."""
    if sessions <= 0 or len(values) < sessions + 1:
        return None
    start = values[-(sessions + 1)]
    if not start:
        return None
    return (values[-1] / start) - 1.0


def range_position(price: float, low: float, high: float) -> float | None:
    """Where ``price`` sits inside ``low``..``high``: 0.0 at low, 1.0 at high."""
    span = high - low
    if span <= 0:
        return None
    return max(0.0, min(1.0, (price - low) / span))


def volume_ratio(candles: Sequence[Candle], short: int = 5, long: int = 60) -> float | None:
    """Recent volume versus its longer baseline. Above 1.0 means participation."""
    series = volumes(candles)
    if len(series) < long:
        return None
    baseline = sum(series[-long:]) / long
    if baseline <= 0:
        return None
    return (sum(series[-short:]) / short) / baseline


def slope_pct(values: Sequence[float], window: int) -> float | None:
    """Fractional change of a moving average over its own window.

    A rising 50-day average matters more than price merely sitting above it.
    """
    if len(values) < window * 2:
        return None
    now_avg = sum(values[-window:]) / window
    then_avg = sum(values[-window * 2 : -window]) / window
    if not then_avg:
        return None
    return (now_avg / then_avg) - 1.0
