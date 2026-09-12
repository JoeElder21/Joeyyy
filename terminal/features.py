"""The feature registry.

Every input the ranking engine is allowed to use is declared here with its
formula, units, lookback, economic rationale, expected direction, data
dependencies, availability lag, missing-data handling and evidence status. A
feature that is not in this registry cannot reach a score -- there is no path
from a raw observation to a rank that bypasses a declaration.

Two structural rules are enforced rather than documented:

* **Correlation groups.** Three flavours of price momentum are one economic
  bet, not three independent votes. Features carry a ``group``; the engine
  budgets weight per group, so adding a fourth momentum variant cannot inflate
  the influence of trend.
* **Direction is declared, not inferred.** ``higher_is_better`` is part of the
  registry. A risk feature such as drawdown scores better when it is *smaller*,
  and that is stated once here rather than re-derived at every call site.

The same registry serves equities and crypto. Features name the asset classes
they are meaningful for: a funding rate is not defined for a share of DELL, and
a price/earnings comparison is not defined for a memecoin. Applying a DeFi
revenue multiple to Bitcoin, or an equity valuation multiple to a dog coin, is
a category error the ``asset_classes`` field exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass

CRYPTO, EQUITY = "crypto", "equity"

# Evidence status for a feature's link to forward returns.
LITERATURE = "LITERATURE"  # motivated by published cross-sectional research
MECHANICAL = "MECHANICAL"  # an accounting or execution identity, not a forecast
HYPOTHESIS = "HYPOTHESIS"  # plausible, untested on this universe

# Feature families, per the directive.
TREND = "A_relative_strength_trend"
RISK = "B_downside_volatility"
ENTRY = "C_entry_execution"
POSITIONING = "D_derivatives_positioning"
FUNDAMENTAL = "E_fundamentals_token_economics"
EVENT = "F_verified_events"

# Missing-data policies.
OMIT = "OMIT"  # drop from the weighted average and shrink coverage
BLOCK = "BLOCK"  # absence blocks actionable ranking entirely
PENALISE = "PENALISE"  # absence is itself bad news; score the worst observed


@dataclass(frozen=True)
class Feature:
    key: str
    family: str
    group: str
    label: str
    formula: str
    units: str
    lookback: str
    rationale: str
    higher_is_better: bool
    depends_on: tuple[str, ...]
    availability_lag: str
    missing_policy: str
    evidence: str
    asset_classes: frozenset[str]
    method: str = "rank"
    note: str = ""

    def applies_to(self, asset_class: str) -> bool:
        return asset_class in self.asset_classes

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "family": self.family,
            "group": self.group,
            "label": self.label,
            "formula": self.formula,
            "units": self.units,
            "lookback": self.lookback,
            "rationale": self.rationale,
            "direction": "higher is better" if self.higher_is_better else "lower is better",
            "depends_on": list(self.depends_on),
            "availability_lag": self.availability_lag,
            "missing_policy": self.missing_policy,
            "evidence": self.evidence,
            "asset_classes": sorted(self.asset_classes),
            "method": self.method,
            "note": self.note,
        }


BOTH = frozenset({CRYPTO, EQUITY})
ONLY_CRYPTO = frozenset({CRYPTO})
ONLY_EQUITY = frozenset({EQUITY})


_FEATURES: tuple[Feature, ...] = (
    # ---- A. Relative strength and trend -------------------------------
    Feature(
        key="residual_momentum",
        family=TREND,
        group="trend",
        label="Beta-adjusted residual momentum",
        formula="log(P_t / P_{t-k}) - beta_market * log(M_t / M_{t-k})",
        units="log return, dimensionless",
        lookback="k = the ranking horizon, capped at available history",
        rationale=(
            "Cross-sectional momentum is among the more replicated effects in "
            "the crypto factor literature (Liu, Tsyvinski and Wu). Stripping "
            "market beta stops the whole book from ranking on one BTC rally."
        ),
        higher_is_better=True,
        depends_on=("price_series", "market_series", "beta_market"),
        availability_lag="one bar",
        missing_policy=OMIT,
        evidence=LITERATURE,
        asset_classes=BOTH,
        note=(
            "A candidate signal, not a guarantee. Momentum reverses in crowded "
            "regimes; the engine tests the regime separately."
        ),
    ),
    Feature(
        key="relative_strength_vs_market",
        family=TREND,
        group="trend",
        label="Excess return versus the eligible market",
        formula="r_asset(h) - r_eligible_equal_weight(h)",
        units="fraction",
        lookback="the ranking horizon",
        rationale=(
            "Separates asset selection from market direction. An asset up 4% "
            "in a market up 9% is a laggard, not a winner."
        ),
        higher_is_better=True,
        depends_on=("price_series", "market_series"),
        availability_lag="one bar",
        missing_policy=OMIT,
        evidence=LITERATURE,
        asset_classes=BOTH,
    ),
    Feature(
        key="trend_persistence",
        family=TREND,
        group="trend",
        label="Trend persistence",
        formula="share of bars in the lookback closing above the rolling median",
        units="fraction on [0, 1]",
        lookback="the ranking horizon",
        rationale=(
            "Distinguishes a steady advance from one gap that happened to land "
            "inside the window. A single candle is not a trend."
        ),
        higher_is_better=True,
        depends_on=("price_series",),
        availability_lag="one bar",
        missing_policy=OMIT,
        evidence=HYPOTHESIS,
        asset_classes=BOTH,
    ),
    # ---- B. Downside and volatility -----------------------------------
    Feature(
        key="downside_deviation",
        family=RISK,
        group="risk",
        label="Downside deviation",
        formula="sqrt(mean(min(0, r_t - threshold)^2))",
        units="fraction per bar",
        lookback="trailing window, sample size reported",
        rationale=(
            "Upside dispersion is not risk. Penalising total volatility "
            "punishes exactly the asymmetry a long position wants."
        ),
        higher_is_better=False,
        depends_on=("return_series",),
        availability_lag="one bar",
        missing_policy=PENALISE,
        evidence=LITERATURE,
        asset_classes=BOTH,
        note="Missing risk data must never help a score: absence scores worst.",
    ),
    Feature(
        key="max_drawdown",
        family=RISK,
        group="risk",
        label="Historical maximum drawdown",
        formula="max over t of (peak_{<=t} - P_t) / peak_{<=t}",
        units="fraction, non-negative",
        lookback="trailing window, sample size reported",
        rationale=(
            "A realised measurement of how far this asset has actually fallen "
            "from a high. Backward-looking: it is not a forecast of the next one."
        ),
        higher_is_better=False,
        depends_on=("price_series",),
        availability_lag="one bar",
        missing_policy=PENALISE,
        evidence=MECHANICAL,
        asset_classes=BOTH,
    ),
    Feature(
        key="ewma_volatility",
        family=RISK,
        group="risk",
        label="EWMA volatility",
        formula="sqrt(EWMA variance of log returns, half-life 10 bars)",
        units="fraction per bar",
        lookback="trailing window",
        rationale="Recent turbulence is more informative than a flat average.",
        higher_is_better=False,
        depends_on=("return_series",),
        availability_lag="one bar",
        missing_policy=PENALISE,
        evidence=LITERATURE,
        asset_classes=BOTH,
    ),
    # ---- C. Entry and execution ---------------------------------------
    Feature(
        key="liquidity_depth",
        family=ENTRY,
        group="liquidity",
        label="Executable depth against the research notional",
        formula="liquidity_usd / standard_notional",
        units="multiple",
        lookback="point in time",
        rationale=(
            "A rank is worthless if the position cannot be entered or exited. "
            "Depth is measured against a stated notional, never assumed."
        ),
        higher_is_better=True,
        depends_on=("liquidity_usd", "standard_notional"),
        availability_lag="quote time",
        missing_policy=BLOCK,
        evidence=MECHANICAL,
        asset_classes=BOTH,
        note="A hard block: no depth reading means no actionable rank.",
    ),
    Feature(
        key="spread_cost",
        family=ENTRY,
        group="liquidity",
        label="Quoted round-trip spread",
        formula="(ask - bid) / mid",
        units="fraction",
        lookback="point in time",
        rationale="The first and most certain cost of the round trip.",
        higher_is_better=False,
        depends_on=("bid", "ask"),
        availability_lag="quote time",
        missing_policy=PENALISE,
        evidence=MECHANICAL,
        asset_classes=BOTH,
    ),
    Feature(
        key="turnover_ratio",
        family=ENTRY,
        group="liquidity",
        label="Volume to liquidity turnover",
        formula="volume_24h / liquidity_usd",
        units="multiple per day",
        lookback="24h",
        rationale=(
            "Real two-sided interest relative to the size of the book. Very "
            "high turnover on a thin pool is churn, not depth."
        ),
        higher_is_better=True,
        depends_on=("volume_24h", "liquidity_usd"),
        availability_lag="provider cache",
        missing_policy=OMIT,
        evidence=HYPOTHESIS,
        asset_classes=ONLY_CRYPTO,
        note=(
            "Crypto wash trading is documented and material (Cong, Li, Tang "
            "and Yang). Reported volume is treated as a weak signal, and this "
            "feature is capped so extreme turnover cannot dominate."
        ),
    ),
    Feature(
        key="extension_from_support",
        family=ENTRY,
        group="entry_timing",
        label="Volatility-normalised extension above support",
        formula="(P_now - support_lagged) / (P_now * ewma_volatility)",
        units="volatility units",
        lookback="support from the lagged window, strictly before the quote",
        rationale=(
            "Entry price is part of the economics. The same forecast is worth "
            "less when bought extended. Support is LAGGED so a level cannot be "
            "drawn using the very bar being scored."
        ),
        higher_is_better=False,
        depends_on=("price_series", "ewma_volatility"),
        availability_lag="one bar",
        missing_policy=OMIT,
        evidence=HYPOTHESIS,
        asset_classes=BOTH,
        note=("A low unit price and distance below an all-time high are not valuation."),
    ),
    # ---- D. Derivatives and positioning --------------------------------
    Feature(
        key="funding_rate_8h",
        family=POSITIONING,
        group="positioning",
        label="Perpetual funding, normalised to 8h",
        formula="funding_rate * (8 / native_interval_hours)",
        units="fraction per 8h",
        lookback="latest settled interval",
        rationale=(
            "Extreme funding marks crowded positioning. Venues quote over "
            "different intervals; comparing them unnormalised is meaningless."
        ),
        higher_is_better=False,
        depends_on=("funding_rate", "native_interval_hours"),
        availability_lag="settlement interval",
        missing_policy=OMIT,
        evidence=HYPOTHESIS,
        asset_classes=ONLY_CRYPTO,
        note=(
            "Negative funding is not automatically bullish and high funding is "
            "not automatically bearish; this is a crowding reading only. Using "
            "it as a feature authorises no derivatives execution."
        ),
    ),
    Feature(
        key="open_interest_change",
        family=POSITIONING,
        group="positioning",
        label="Open interest change",
        formula="(OI_t - OI_{t-k}) / OI_{t-k}",
        units="fraction",
        lookback="the ranking horizon",
        rationale="Rising price on rising OI is new money; on falling OI it is a squeeze.",
        higher_is_better=True,
        depends_on=("open_interest_series",),
        availability_lag="venue reporting",
        missing_policy=OMIT,
        evidence=HYPOTHESIS,
        asset_classes=ONLY_CRYPTO,
    ),
    # ---- E. Fundamentals and token economics ---------------------------
    Feature(
        key="holder_accrual",
        family=FUNDAMENTAL,
        group="value_capture",
        label="Value accruing to token holders",
        formula="holder_accrual_annualised / fully_diluted_value",
        units="fraction per year",
        lookback="trailing, with the accounting basis stated",
        rationale=(
            "Fees are not revenue and revenue is not holder accrual. Only the "
            "portion that actually reaches holders is a claim on value."
        ),
        higher_is_better=True,
        depends_on=("holder_accrual", "fully_diluted_value"),
        availability_lag="protocol reporting",
        missing_policy=OMIT,
        evidence=HYPOTHESIS,
        asset_classes=ONLY_CRYPTO,
        note=(
            "Do not double-count TVL, and do not count token emissions paid to "
            "users as external revenue. Not applicable to a memecoin: a token "
            "with no value-capture mechanism is N/A here, not zero."
        ),
    ),
    Feature(
        key="float_ratio",
        family=FUNDAMENTAL,
        group="supply",
        label="Circulating share of total supply",
        formula="circulating_supply / total_supply",
        units="fraction on [0, 1]",
        lookback="point in time",
        rationale=(
            "A low float with a large locked remainder means the price is set "
            "by a small slice of the eventual supply."
        ),
        higher_is_better=True,
        depends_on=("circulating_supply", "total_supply"),
        availability_lag="provider refresh",
        missing_policy=OMIT,
        evidence=LITERATURE,
        asset_classes=ONLY_CRYPTO,
    ),
    Feature(
        key="unlock_overhang",
        family=FUNDAMENTAL,
        group="supply",
        label="Scheduled unlocks against credible liquidity",
        formula="unlock_value_next_90d / liquidity_usd",
        units="multiple",
        lookback="forward 90 days",
        rationale=(
            "Measured against the liquidity that would have to absorb it, not "
            "against market capitalisation, which no one has to buy."
        ),
        higher_is_better=False,
        depends_on=("unlock_schedule", "liquidity_usd"),
        availability_lag="published schedule",
        missing_policy=OMIT,
        evidence=HYPOTHESIS,
        asset_classes=ONLY_CRYPTO,
    ),
    Feature(
        key="earnings_yield",
        family=FUNDAMENTAL,
        group="value_capture",
        label="Trailing earnings yield",
        formula="trailing_twelve_month_earnings / market_capitalisation",
        units="fraction per year",
        lookback="trailing twelve months",
        rationale=(
            "The equity analogue of holder accrual: the earnings claim per "
            "dollar of price. Sector-relative, never compared across sectors "
            "without saying so."
        ),
        higher_is_better=True,
        depends_on=("ttm_earnings", "market_cap"),
        availability_lag="filing date, not period end",
        missing_policy=OMIT,
        evidence=LITERATURE,
        asset_classes=ONLY_EQUITY,
    ),
    Feature(
        key="balance_sheet_quality",
        family=FUNDAMENTAL,
        group="solvency",
        label="Net debt to EBITDA",
        formula="(total_debt - cash) / ebitda_ttm",
        units="multiple",
        lookback="latest reported period",
        rationale="Leverage is what turns a cyclical downturn into a permanent loss.",
        higher_is_better=False,
        depends_on=("total_debt", "cash", "ebitda_ttm"),
        availability_lag="filing date",
        missing_policy=OMIT,
        evidence=LITERATURE,
        asset_classes=ONLY_EQUITY,
    ),
    # ---- F. Verified events --------------------------------------------
    Feature(
        key="event_risk",
        family=EVENT,
        group="events",
        label="Verified adverse event pressure",
        formula="weighted count of verified adverse events inside the lookback",
        units="index, non-negative",
        lookback="trailing 30 days",
        rationale=(
            "Exploits, outages, delistings and regulatory actions are facts "
            "with dates, not sentiment. Rumour and social attention are "
            "labelled separately and never enter here."
        ),
        higher_is_better=False,
        depends_on=("verified_events",),
        availability_lag="publication date, tracked apart from event date",
        missing_policy=OMIT,
        evidence=MECHANICAL,
        asset_classes=BOTH,
        note=(
            "Absence of recorded events means 'nothing verified', not 'nothing "
            "happened'. It is N/A, not a clean bill of health."
        ),
    ),
)

REGISTRY: dict[str, Feature] = {f.key: f for f in _FEATURES}


def for_asset_class(asset_class: str) -> dict[str, Feature]:
    """The features that are economically meaningful for this asset class."""
    if asset_class not in (CRYPTO, EQUITY):
        raise ValueError(f"unknown asset class: {asset_class!r}")
    return {k: f for k, f in REGISTRY.items() if f.applies_to(asset_class)}


def groups(asset_class: str) -> dict[str, list[str]]:
    """Correlation groups -> the feature keys inside them."""
    out: dict[str, list[str]] = {}
    for key, feature in sorted(for_asset_class(asset_class).items()):
        out.setdefault(feature.group, []).append(key)
    return out


def blocking_features(asset_class: str) -> list[str]:
    """Features whose absence blocks an actionable rank outright."""
    return sorted(k for k, f in for_asset_class(asset_class).items() if f.missing_policy == BLOCK)


def registry_document(asset_class: str) -> dict:
    """The registry as a publishable document, for the terminal's methodology view."""
    features = for_asset_class(asset_class)
    return {
        "asset_class": asset_class,
        "feature_count": len(features),
        "groups": groups(asset_class),
        "blocking": blocking_features(asset_class),
        "features": [features[k].as_dict() for k in sorted(features)],
    }
