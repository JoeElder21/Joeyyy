"""Turn holdings plus price history into an explainable verdict per position.

The scoring here is deterministic and fully traceable: every point in a
composite score names the condition that produced it, and hard risk
guardrails override the score outright. That matters because a number
without a reason cannot be argued with, and this output is meant to be
argued with before any money moves.

This module produces *analysis*, not advice and not orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib
from typing import Any, Sequence

from connectors.schwab import indicators
from connectors.schwab.portfolio import Holding, Portfolio

Candle = dict[str, Any]

#: Verdicts, strongest conviction to weakest.
ADD = "ADD"
HOLD = "HOLD"
WATCH = "WATCH"
TRIM = "TRIM"
EXIT = "EXIT"
NO_DATA = "NO_DATA"


class PolicyError(RuntimeError):
    """Raised when the policy file is missing or malformed."""


@dataclass(frozen=True)
class Policy:
    """Loaded ``config/portfolio_policy.toml``."""

    risk: dict[str, float]
    lookback: dict[str, int]
    indicators: dict[str, float]
    scoring: dict[str, float]
    thresholds: dict[str, float]
    research: dict[str, float]

    @classmethod
    def load(cls, path: Path) -> "Policy":
        try:
            with Path(path).open("rb") as handle:
                raw = tomllib.load(handle)
        except FileNotFoundError as error:
            raise PolicyError(f"Policy file not found: {path}") from error
        except tomllib.TOMLDecodeError as error:
            raise PolicyError(f"Policy file {path} is not valid TOML: {error}") from error

        missing = [
            section
            for section in ("risk", "lookback", "indicators", "scoring", "thresholds", "research")
            if section not in raw
        ]
        if missing:
            raise PolicyError(f"Policy file {path} is missing sections: {', '.join(missing)}")

        return cls(
            risk=raw["risk"],
            lookback=raw["lookback"],
            indicators=raw["indicators"],
            scoring=raw["scoring"],
            thresholds=raw["thresholds"],
            research=raw["research"],
        )


@dataclass
class Metrics:
    """Every computed number for one symbol. ``None`` means not enough data."""

    last_close: float | None = None
    week_return: float | None = None
    month_return: float | None = None
    quarter_return: float | None = None
    half_year_return: float | None = None
    fast_ma: float | None = None
    medium_ma: float | None = None
    slow_ma: float | None = None
    medium_ma_slope: float | None = None
    rsi: float | None = None
    macd_histogram: float | None = None
    atr: float | None = None
    atr_pct: float | None = None
    annualized_volatility: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    range_position: float | None = None
    drawdown_from_high: float | None = None
    max_drawdown: float | None = None
    volume_ratio: float | None = None
    sessions: int = 0


@dataclass
class Verdict:
    """A scored, reasoned recommendation for one holding."""

    symbol: str
    verdict: str
    score: float
    metrics: Metrics
    reasons: list[str] = field(default_factory=list)
    guardrail_breaches: list[str] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)
    research_questions: list[str] = field(default_factory=list)
    weight: float = 0.0
    unrealized_pl_pct: float | None = None
    market_value: float = 0.0

    @property
    def needs_corroboration(self) -> bool:
        return bool(self.guardrail_breaches) or abs(self.score) >= 40.0


def compute_metrics(candles: Sequence[Candle], policy: Policy) -> Metrics:
    """Derive every indicator for one symbol from its daily candles."""
    series = indicators.closes(candles)
    metrics = Metrics(sessions=len(series))
    if not series:
        return metrics

    ind = policy.indicators
    look = policy.lookback

    metrics.last_close = series[-1]
    metrics.week_return = indicators.change_over(series, int(look["week"]))
    metrics.month_return = indicators.change_over(series, int(look["month"]))
    metrics.quarter_return = indicators.change_over(series, int(look["quarter"]))
    metrics.half_year_return = indicators.change_over(series, int(look["half_year"]))

    metrics.fast_ma = indicators.sma(series, int(ind["fast_ma"]))
    metrics.medium_ma = indicators.sma(series, int(ind["medium_ma"]))
    metrics.slow_ma = indicators.sma(series, int(ind["slow_ma"]))
    metrics.medium_ma_slope = indicators.slope_pct(series, int(ind["medium_ma"]))

    metrics.rsi = indicators.rsi(series, int(ind["rsi_window"]))
    macd_value = indicators.macd(series)
    metrics.macd_histogram = macd_value.histogram if macd_value else None

    metrics.atr = indicators.atr(candles, int(ind["atr_window"]))
    if metrics.atr is not None and metrics.last_close:
        metrics.atr_pct = metrics.atr / metrics.last_close
    metrics.annualized_volatility = indicators.realized_volatility(
        series, int(ind["volatility_window"])
    )

    window = series[-252:] if len(series) >= 252 else series
    metrics.high_52w = max(window)
    metrics.low_52w = min(window)
    metrics.range_position = indicators.range_position(
        metrics.last_close, metrics.low_52w, metrics.high_52w
    )
    if metrics.high_52w:
        metrics.drawdown_from_high = (metrics.last_close / metrics.high_52w) - 1.0
    metrics.max_drawdown = indicators.max_drawdown(series)
    metrics.volume_ratio = indicators.volume_ratio(
        candles, int(ind["volume_short_window"]), int(ind["volume_long_window"])
    )
    return metrics


def _score(metrics: Metrics, policy: Policy) -> tuple[float, list[str]]:
    """Sum the scoring conditions, recording a reason for each contribution."""
    points = policy.scoring
    ind = policy.indicators
    total = 0.0
    reasons: list[str] = []

    def award(value: float, reason: str) -> None:
        nonlocal total
        total += value
        reasons.append(f"{reason} ({value:+.0f})")

    price = metrics.last_close
    if price is not None:
        if metrics.slow_ma is not None:
            above = price > metrics.slow_ma
            award(
                points["above_slow_ma"] if above else -points["above_slow_ma"],
                f"price {'above' if above else 'below'} the {int(ind['slow_ma'])}-day average",
            )
        if metrics.medium_ma is not None:
            above = price > metrics.medium_ma
            award(
                points["above_medium_ma"] if above else -points["above_medium_ma"],
                f"price {'above' if above else 'below'} the {int(ind['medium_ma'])}-day average",
            )
        if metrics.fast_ma is not None:
            above = price > metrics.fast_ma
            award(
                points["above_fast_ma"] if above else -points["above_fast_ma"],
                f"price {'above' if above else 'below'} the {int(ind['fast_ma'])}-day average",
            )

    if metrics.medium_ma_slope is not None:
        rising = metrics.medium_ma_slope > 0
        award(
            points["medium_ma_rising"] if rising else -points["medium_ma_rising"],
            f"{int(ind['medium_ma'])}-day average {'rising' if rising else 'falling'} "
            f"({metrics.medium_ma_slope:+.1%})",
        )

    if metrics.macd_histogram is not None:
        positive = metrics.macd_histogram > 0
        award(
            points["macd_positive"] if positive else -points["macd_positive"],
            f"MACD histogram {'positive' if positive else 'negative'}",
        )

    if metrics.rsi is not None:
        if metrics.rsi >= ind["rsi_overbought"]:
            award(points["rsi_overbought_penalty"], f"RSI stretched at {metrics.rsi:.0f}")
        elif metrics.rsi <= ind["rsi_oversold"]:
            award(points["rsi_oversold_penalty"], f"RSI washed out at {metrics.rsi:.0f}")
        elif metrics.rsi >= 45.0:
            award(points["rsi_constructive"], f"RSI constructive at {metrics.rsi:.0f}")

    for label, value, key in (
        ("1-week", metrics.week_return, "week_return_positive"),
        ("1-month", metrics.month_return, "month_return_positive"),
        ("3-month", metrics.quarter_return, "quarter_return_positive"),
    ):
        if value is not None:
            positive = value > 0
            award(
                points[key] if positive else -points[key],
                f"{label} return {value:+.1%}",
            )

    if metrics.volume_ratio is not None and metrics.volume_ratio > 1.1:
        award(points["volume_confirmation"], f"volume {metrics.volume_ratio:.1f}x its baseline")

    if metrics.range_position is not None:
        if metrics.range_position >= 0.8:
            award(points["near_52w_high"], "trading in the top fifth of its 52-week range")
        elif metrics.range_position <= 0.2:
            award(points["near_52w_low"], "trading in the bottom fifth of its 52-week range")

    if (
        metrics.annualized_volatility is not None
        and metrics.annualized_volatility > policy.risk["max_annualized_volatility"]
    ):
        award(
            points["high_volatility_penalty"],
            f"realized volatility {metrics.annualized_volatility:.0%} above the "
            f"{policy.risk['max_annualized_volatility']:.0%} ceiling",
        )

    if (
        metrics.drawdown_from_high is not None
        and metrics.drawdown_from_high <= policy.risk["trailing_stop_from_high_pct"]
    ):
        award(
            points["deep_drawdown_penalty"],
            f"{metrics.drawdown_from_high:.0%} below its 52-week high",
        )

    return max(-100.0, min(100.0, total)), reasons


def _guardrails(holding: Holding, metrics: Metrics, policy: Policy) -> list[str]:
    """Hard risk breaches that override the momentum score."""
    risk = policy.risk
    breaches: list[str] = []

    if holding.weight > risk["max_position_weight"]:
        breaches.append(
            f"position is {holding.weight:.1%} of invested capital, above the "
            f"{risk['max_position_weight']:.0%} single-name cap"
        )

    pl_pct = holding.unrealized_pl_pct
    if pl_pct is not None and pl_pct <= risk["stop_loss_pct"]:
        breaches.append(
            f"unrealized return on cost is {pl_pct:.1%}, at or beyond the "
            f"{risk['stop_loss_pct']:.0%} stop-loss review line"
        )

    if (
        metrics.drawdown_from_high is not None
        and metrics.drawdown_from_high <= risk["trailing_stop_from_high_pct"]
        and metrics.slow_ma is not None
        and metrics.last_close is not None
        and metrics.last_close < metrics.slow_ma
    ):
        breaches.append(
            f"{metrics.drawdown_from_high:.0%} off its 52-week high and below the "
            f"{int(policy.indicators['slow_ma'])}-day average"
        )

    if (
        metrics.annualized_volatility is not None
        and metrics.annualized_volatility > risk["max_annualized_volatility"]
        and holding.weight > risk["max_position_weight"] / 2
    ):
        breaches.append(
            f"realized volatility {metrics.annualized_volatility:.0%} is above the ceiling "
            f"while the position carries {holding.weight:.1%} weight"
        )

    return breaches


def _data_gaps(metrics: Metrics, policy: Policy) -> list[str]:
    gaps: list[str] = []
    if metrics.sessions == 0:
        gaps.append("no price history returned")
        return gaps
    if metrics.slow_ma is None:
        gaps.append(
            f"fewer than {int(policy.indicators['slow_ma'])} sessions of history; "
            "long-term trend not assessed"
        )
    if metrics.rsi is None:
        gaps.append("insufficient history for RSI")
    if metrics.volume_ratio is None:
        gaps.append("insufficient history to compare volume against its baseline")
    return gaps


def _research_questions(symbol: str, verdict: str, metrics: Metrics) -> list[str]:
    """What the agent must go verify before the verdict is presented.

    The mechanical score reads price only. These questions are the bridge to
    the research pass, and they are the part a human should read first.
    """
    questions = [
        f"What has {symbol} reported or disclosed in the last 7 days "
        "(earnings, guidance, filings, management changes)?",
        f"Is there an upcoming catalyst for {symbol} inside the next 30 days "
        "(earnings date, product event, regulatory decision, lockup expiry)?",
    ]
    if verdict in (TRIM, EXIT):
        questions.append(
            f"Is the weakness in {symbol} company-specific or is its whole sector down "
            "over the same window?"
        )
        questions.append(
            f"Have analysts cut estimates or price targets on {symbol} recently, and on what basis?"
        )
    if verdict == ADD:
        questions.append(
            f"Is the strength in {symbol} supported by fundamentals (revenue, margin, guidance) "
            "or only by multiple expansion?"
        )
    if metrics.volume_ratio is not None and metrics.volume_ratio > 1.5:
        questions.append(
            f"What explains the unusual volume in {symbol} over the last week?"
        )
    if metrics.drawdown_from_high is not None and metrics.drawdown_from_high <= -0.2:
        questions.append(
            f"What specifically caused {symbol} to fall "
            f"{abs(metrics.drawdown_from_high):.0%} from its 52-week high?"
        )
    return questions


def evaluate(holding: Holding, candles: Sequence[Candle], policy: Policy) -> Verdict:
    """Score one holding and resolve it to a verdict with reasons."""
    metrics = compute_metrics(candles, policy)
    gaps = _data_gaps(metrics, policy)

    if metrics.sessions == 0:
        return Verdict(
            symbol=holding.symbol,
            verdict=NO_DATA,
            score=0.0,
            metrics=metrics,
            data_gaps=gaps,
            weight=holding.weight,
            unrealized_pl_pct=holding.unrealized_pl_pct,
            market_value=holding.market_value,
            research_questions=[
                f"Why did Schwab return no price history for {holding.symbol}? "
                "Confirm the symbol is still listed and tradable."
            ],
        )

    score, reasons = _score(metrics, policy)
    breaches = _guardrails(holding, metrics, policy)
    cuts = policy.thresholds

    if breaches:
        # A guardrail breach caps the verdict regardless of momentum: a
        # winner that has become too large is still a trim.
        resolved = EXIT if score <= cuts["trim"] else TRIM
    elif score >= cuts["add"]:
        resolved = ADD
    elif score >= cuts["hold"]:
        resolved = HOLD
    elif score >= cuts["trim"]:
        resolved = WATCH
    elif score >= cuts["exit_watch"]:
        resolved = TRIM
    else:
        resolved = EXIT

    return Verdict(
        symbol=holding.symbol,
        verdict=resolved,
        score=score,
        metrics=metrics,
        reasons=reasons,
        guardrail_breaches=breaches,
        data_gaps=gaps,
        research_questions=_research_questions(holding.symbol, resolved, metrics),
        weight=holding.weight,
        unrealized_pl_pct=holding.unrealized_pl_pct,
        market_value=holding.market_value,
    )


def evaluate_portfolio(
    portfolio: Portfolio,
    history: dict[str, Sequence[Candle]],
    policy: Policy,
) -> list[Verdict]:
    """Score every non-cash holding, strongest conviction first."""
    verdicts = [
        evaluate(holding, history.get(holding.symbol, []), policy)
        for holding in portfolio.equity_holdings
    ]
    order = {ADD: 0, HOLD: 1, WATCH: 2, TRIM: 3, EXIT: 4, NO_DATA: 5}
    verdicts.sort(key=lambda v: (order.get(v.verdict, 9), -v.market_value))
    return verdicts


def portfolio_alerts(portfolio: Portfolio, policy: Policy) -> list[str]:
    """Book-level breaches that no single-position verdict would catch."""
    risk = policy.risk
    alerts: list[str] = []

    if portfolio.concentration_index > risk["max_effective_concentration"]:
        alerts.append(
            f"Concentration index {portfolio.concentration_index:.2f} exceeds the "
            f"{risk['max_effective_concentration']:.2f} ceiling — the book behaves like "
            f"{portfolio.effective_positions:.1f} equal-weight positions."
        )

    cash_weight = portfolio.cash_weight
    if cash_weight is not None and cash_weight < risk["min_cash_weight"]:
        alerts.append(
            f"Cash is {cash_weight:.1%} of account equity, below the "
            f"{risk['min_cash_weight']:.0%} floor — no dry powder for a drawdown."
        )

    if portfolio.largest_weight > risk["max_position_weight"]:
        alerts.append(
            f"Largest position is {portfolio.largest_weight:.1%} of invested capital, "
            f"above the {risk['max_position_weight']:.0%} single-name cap."
        )

    return alerts
