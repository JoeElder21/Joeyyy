"""Robust cross-sectional statistics for the ranking engine.

Every number a rank depends on passes through here. Three rules hold
throughout:

1. A cross-section of one or two assets cannot support a percentile. Small
   samples are labelled, not silently normalised into confident-looking
   spreads.
2. Zero dispersion is a real state, not a division by zero. When every asset
   carries the same value that feature distinguishes nothing and contributes
   nothing.
3. Missing is missing. Nothing here imputes a mean, a median or a zero for an
   absent observation -- the caller decides, and the ranking engine records
   the coverage cost.

The normalisations are deliberately rank-based or median/MAD-based rather than
mean/standard-deviation: a single memecoin up 2,500% in three hours would
otherwise dominate the z-score of every other asset in the book.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import NormalDist

# Below this many scored observations a cross-sectional position is reported
# but marked low confidence: with four assets a "75th percentile" is one place.
MIN_CROSS_SECTION = 5
# MAD -> sigma for a normal distribution.
MAD_SCALE = 1.4826
# Winsorising bound for MAD z-scores, in robust sigmas.
Z_CLIP = 3.0

FULL, LOW_SAMPLE, ZERO_DISPERSION, EMPTY = (
    "FULL",
    "LOW_SAMPLE",
    "ZERO_DISPERSION",
    "EMPTY",
)

_NORMAL = NormalDist()


@dataclass(frozen=True)
class CrossSection:
    """One feature normalised across the assets that actually carry it.

    ``values`` holds only the assets with an observation. ``missing`` names the
    ones that did not, so the caller can charge for the gap rather than let an
    absent risk reading quietly vanish from the denominator.
    """

    name: str
    values: dict[str, float]
    normalised: dict[str, float]
    status: str
    median: float | None
    mad: float | None
    n: int
    missing: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def usable(self) -> bool:
        """Whether this feature can move a rank at all."""
        return self.status in (FULL, LOW_SAMPLE) and bool(self.normalised)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "n": self.n,
            "median": self.median,
            "mad": self.mad,
            "missing": list(self.missing),
            "note": self.note,
            "normalised": dict(self.normalised),
        }


def _finite(value: object) -> float | None:
    """A value is usable only if it is a finite real number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def mad(values: list[float], centre: float | None = None) -> float | None:
    """Median absolute deviation. Zero is a legitimate answer, not an error."""
    if not values:
        return None
    mid = median(values) if centre is None else centre
    if mid is None:
        return None
    return median([abs(v - mid) for v in values])


def fractional_ranks(values: dict[str, float], higher_is_better: bool = True) -> dict[str, float]:
    """Ranks on (0, 1) with ties averaged.

    The open interval matters: a closed [0, 1] would hand the best asset a
    perfect score and the worst a zero, which reads as certainty the data
    cannot support. Ties share their average rank so two identical assets
    cannot be ordered by an accident of dictionary insertion.
    """
    if not values:
        return {}
    items = sorted(values.items(), key=lambda kv: (kv[1], kv[0]))
    n = len(items)
    ranks: dict[str, float] = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and items[j + 1][1] == items[i][1]:
            j += 1
        # Average 1-based position across the tie group.
        average_position = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[items[k][0]] = average_position / (n + 1.0)
        i = j + 1
    if not higher_is_better:
        ranks = {key: 1.0 - value for key, value in ranks.items()}
    return ranks


def normal_scores(values: dict[str, float], higher_is_better: bool = True) -> dict[str, float]:
    """Rank-based z-scores (van der Waerden). Outlier-proof by construction."""
    ranks = fractional_ranks(values, higher_is_better)
    return {key: _NORMAL.inv_cdf(value) for key, value in ranks.items()}


def cross_section(
    name: str,
    raw: dict[str, object],
    higher_is_better: bool = True,
    method: str = "rank",
    universe: list[str] | None = None,
) -> CrossSection:
    """Normalise one feature across the universe.

    ``method`` is ``"rank"`` (fractional ranks on (0,1), the default) or
    ``"mad"`` (median/MAD z-scores clipped to +/- Z_CLIP then squashed to
    (0,1)). Rank is the default because it needs no distributional assumption
    and cannot be dragged by one outlier.
    """
    members = list(universe) if universe is not None else list(raw)
    values: dict[str, float] = {}
    for key in members:
        number = _finite(raw.get(key))
        if number is not None:
            values[key] = number
    missing = sorted(set(members) - set(values))

    if not values:
        return CrossSection(
            name, {}, {}, EMPTY, None, None, 0, missing, "no asset carries this feature"
        )

    centre = median(list(values.values()))
    spread = mad(list(values.values()), centre)

    if spread == 0:
        # Every asset agrees. The feature is real but discriminates nothing, so
        # it must not tilt any rank. Returning 0.5 for all would silently add a
        # constant; returning an unusable section removes it from the weights.
        return CrossSection(
            name,
            values,
            {},
            ZERO_DISPERSION,
            centre,
            spread,
            len(values),
            missing,
            "every scored asset shares one value; the feature cannot separate them",
        )

    if method == "mad":
        assert spread is not None and centre is not None
        sigma = spread * MAD_SCALE
        z = {k: max(-Z_CLIP, min(Z_CLIP, (v - centre) / sigma)) for k, v in values.items()}
        if not higher_is_better:
            z = {k: -v for k, v in z.items()}
        normalised = {k: _NORMAL.cdf(v) for k, v in z.items()}
    elif method == "rank":
        normalised = fractional_ranks(values, higher_is_better)
    else:
        raise ValueError(f"unknown normalisation method: {method!r}")

    status = FULL if len(values) >= MIN_CROSS_SECTION else LOW_SAMPLE
    note = ""
    if status == LOW_SAMPLE:
        note = (
            f"only {len(values)} scored asset(s); a percentile across this few "
            f"carries little information"
        )
    return CrossSection(
        name,
        values,
        {k: round(v, 6) for k, v in normalised.items()},
        status,
        centre,
        spread,
        len(values),
        missing,
        note,
    )


def winsorise(values: list[float], lower: float = 0.05, upper: float = 0.95) -> list[float]:
    """Clip a sample to its own quantiles before estimating a moment."""
    usable = sorted(v for v in (_finite(x) for x in values) if v is not None)
    if not usable:
        return []
    lo = quantile(usable, lower)
    hi = quantile(usable, upper)
    if lo is None or hi is None:
        return usable
    return [min(max(v, lo), hi) for v in usable]


def quantile(values: list[float], q: float) -> float | None:
    """Linear-interpolated quantile. ``q`` in [0, 1]."""
    if not values:
        return None
    if not 0.0 <= q <= 1.0:
        raise ValueError("quantile must lie in [0, 1]")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = q * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[int(position)]
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


@dataclass(frozen=True)
class TailLoss:
    """A downside tail estimate with the sample size that produced it.

    Reported as a NON-NEGATIVE magnitude: 0.08 means an 8% expected loss in the
    tail. The sign convention is fixed here so the decision functional can
    subtract it without a sign bug flipping a penalty into a reward.
    """

    expected_shortfall: float | None
    value_at_risk: float | None
    confidence: float
    n: int
    adequate: bool
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "expected_shortfall": self.expected_shortfall,
            "value_at_risk": self.value_at_risk,
            "confidence": self.confidence,
            "n": self.n,
            "adequate": self.adequate,
            "note": self.note,
        }


# Below this many return observations a 95% tail is being read off two or three
# points and is not an estimate of anything.
MIN_TAIL_SAMPLE = 30


def expected_shortfall(returns: list[float], confidence: float = 0.95) -> TailLoss:
    """Mean loss in the worst ``1 - confidence`` of observed returns.

    Returns a magnitude, so a 12% average loss in the tail is ``0.12``. A gain
    in the tail (possible on a strongly trending sample) clamps to 0.0 rather
    than becoming a negative penalty that would *reward* the asset.
    """
    usable = [v for v in (_finite(x) for x in returns) if v is not None]
    n = len(usable)
    if n == 0:
        return TailLoss(None, None, confidence, 0, False, "no return observations")

    cut = quantile(usable, 1.0 - confidence)
    if cut is None:
        return TailLoss(None, None, confidence, n, False, "could not compute the quantile")
    tail = [v for v in usable if v <= cut]
    if not tail:
        tail = [min(usable)]
    mean_tail = sum(tail) / len(tail)

    adequate = n >= MIN_TAIL_SAMPLE
    note = ""
    if not adequate:
        note = (
            f"{n} observations is below the {MIN_TAIL_SAMPLE} needed for a "
            f"{confidence:.0%} tail; treat as indicative only"
        )
    return TailLoss(
        max(0.0, -mean_tail),
        max(0.0, -cut),
        confidence,
        n,
        adequate,
        note,
    )


def ewma_volatility(returns: list[float], half_life: int = 10) -> float | None:
    """Exponentially weighted volatility, recent observations weighted more."""
    usable = [v for v in (_finite(x) for x in returns) if v is not None]
    if len(usable) < 2:
        return None
    lam = 0.5 ** (1.0 / half_life)
    weights = [lam**i for i in range(len(usable))]  # index 0 == most recent
    series = list(reversed(usable))
    total = sum(weights)
    mean = sum(w * v for w, v in zip(weights, series, strict=True)) / total
    var = sum(w * (v - mean) ** 2 for w, v in zip(weights, series, strict=True)) / total
    return math.sqrt(var)


def downside_deviation(returns: list[float], threshold: float = 0.0) -> float | None:
    """Volatility of the losses only. Upside dispersion is not risk."""
    usable = [v for v in (_finite(x) for x in returns) if v is not None]
    if len(usable) < 2:
        return None
    shortfalls = [min(0.0, v - threshold) ** 2 for v in usable]
    return math.sqrt(sum(shortfalls) / len(shortfalls))


def max_drawdown(prices: list[float]) -> float | None:
    """Largest peak-to-trough decline, as a non-negative fraction."""
    usable = [v for v in (_finite(x) for x in prices) if v is not None and v > 0]
    if len(usable) < 2:
        return None
    peak = usable[0]
    worst = 0.0
    for price in usable:
        peak = max(peak, price)
        worst = max(worst, (peak - price) / peak)
    return worst


def shrink(
    estimate: float | None, prior: float, n: int, prior_strength: float = 20.0
) -> float | None:
    """James-Stein style shrinkage of an estimate toward a prior.

    With few observations the estimate is mostly prior; with many it is mostly
    data. ``prior_strength`` is the pseudo-count the prior is worth. This is
    what keeps a coin with six days of history from ranking first on a
    spectacular but meaningless mean.
    """
    if estimate is None:
        return None
    if n <= 0:
        return prior
    weight = n / (n + prior_strength)
    return weight * estimate + (1.0 - weight) * prior


def standard_error(returns: list[float]) -> float | None:
    """Standard error of the MEAN -- uncertainty in the estimate itself.

    Distinct from volatility, which is the dispersion of outcomes. The decision
    functional charges for these separately and they must not be conflated.
    """
    usable = [v for v in (_finite(x) for x in returns) if v is not None]
    n = len(usable)
    if n < 2:
        return None
    mean = sum(usable) / n
    variance = sum((v - mean) ** 2 for v in usable) / (n - 1)
    return math.sqrt(variance / n)


def spearman(a: dict[str, float], b: dict[str, float]) -> tuple[float | None, int]:
    """Spearman rank correlation over the assets present in both mappings."""
    shared = sorted(set(a) & set(b))
    n = len(shared)
    if n < 3:
        return None, n
    ra = fractional_ranks({k: a[k] for k in shared})
    rb = fractional_ranks({k: b[k] for k in shared})
    xs = [ra[k] for k in shared]
    ys = [rb[k] for k in shared]
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None, n
    return num / (dx * dy), n
