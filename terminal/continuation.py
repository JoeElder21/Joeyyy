"""Continuation scoring: does a move persist, or has it already stopped?

Status: **HEURISTIC / NOT YET VALIDATED**, on exactly the terms
``terminal.ranking`` sets out. The horizon weights below are hypotheses chosen
for economic plausibility. They are not fitted coefficients and they have not
been tested out of sample, so nothing here converts to an expected return --
this module produces an ORDERING and a label, never a forecast percentage.

The problem it exists to solve. A ranking built on current state answers "what
went up most?", and that question has a well-known failure: the biggest recent
gainer is frequently the name closest to exhaustion. Asking instead "which of
these conditions persist?" requires separating two things a level cannot
distinguish:

* an asset 30% above its base because it is trending, and
* an asset 30% above its base because it spiked and stopped.

Both show the same extension. They differ in their RATE: the first is still
advancing, the second has flat-lined while the trailing number still looks
strong. That is what ``decay`` measures, and it is the term that most changes
the ordering relative to a current-state rank.

Two structural commitments:

* **Persistence and exhaustion are scored separately, then netted.** A single
  blended score hides whether a middling result means "nothing going on" or
  "strong trend fighting a stretched tape". Callers get both component lists
  back and can show the disagreement rather than averaging it away.

* **Horizon changes the weighting, not the inputs.** Short-horizon reversal
  and intermediate-horizon momentum are separately documented effects with
  opposite signs. So exhaustion is weighted heaviest at 3d and lightest at
  30d, and persistence the other way round. A name reading PULLBACK at 3d and
  CONTINUE at 30d is the model working, not contradicting itself.

Missing data never helps, as everywhere else in this package, and the two
sides enforce that differently. A missing PERSISTENCE input is dropped from
the earned score while still counting against coverage, so the asset simply
fails to earn it. A missing EXHAUSTION input is a missing risk reading, so it
is charged the worst case (``MISSING_EXHAUST``) rather than dropped -- absence
of evidence about risk is not evidence of safety. Either way a substituted
zero or neutral midpoint is never accepted in place of a reading, and below
``MIN_COVERAGE`` the score is withheld rather than reported thin.

The one exception is a gap the caller has established is systemic rather than
asset-specific; see ``systemic_gaps`` on :func:`score`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Horizons this module scores. Adding one means adding its weights to both
# tables below; there is no default, because a horizon without a stated
# reversal/momentum balance has no defined meaning here.
HORIZONS: tuple[str, ...] = ("3d", "7d", "30d")

# Persistence and exhaustion weights per horizon. Exhaustion dominates the
# short horizon (reversal), persistence the long one (momentum).
PERSIST_WEIGHT: dict[str, float] = {"3d": 0.70, "7d": 1.00, "30d": 1.30}
EXHAUST_WEIGHT: dict[str, float] = {"3d": 1.40, "7d": 1.00, "30d": 0.50}

# Per-term horizon weights for the two terms whose relevance is itself
# horizon-dependent: deceleration bites soonest, distance from a 200-day
# base reverts on a 200-day timescale.
DECAY_WEIGHT: dict[str, float] = {"3d": 1.5, "7d": 1.2, "30d": 0.6}
FAR200_WEIGHT: dict[str, float] = {"3d": 0.5, "7d": 0.8, "30d": 1.2}

MIN_COVERAGE = 0.60

# What an unmeasured exhaustion input is charged. Exhaustion terms are risk
# readings, and ``terminal.ranking``'s rule for risk is that absence scores
# worst rather than neutral -- so a gap can never flatter an asset.
#
# Persistence is averaged over the weights PRESENT; exhaustion is divided by
# the full weight of every term still in play. That asymmetry is deliberate:
# averaging exhaustion over present weights would let each additional
# zero-valued term dilute the average and raise the score, so substituting
# 0.0 for an unmeasured reading would mechanically pay. It is the precise
# failure the feed-boundary rule exists to prevent.
MISSING_EXHAUST = 100.0

# Verdict bands, applied to the ROUNDED score so that a published number and
# the label beside it can never disagree.
CONTINUE, MIXED, PULLBACK_RISK, PULLBACK, BREAK, NO_SCORE = (
    "CONTINUE",
    "MIXED",
    "PULLBACK RISK",
    "PULLBACK",
    "BREAK",
    "NO SCORE",
)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def rsi(closes: list[float], n: int = 14) -> float | None:
    """Wilder RSI over ``n`` periods, or None without a full lookback.

    ``rsi / 100`` is the share of recent absolute price movement that was
    upward -- the magnitude-weighted sibling of :func:`up_volume_share`. Where
    a feed serves prices but not volume, this is the buy-pressure reading that
    remains available; it is not a substitute for the volume-weighted one and
    callers should say which they used.
    """
    if len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    avg_gain, avg_loss = gains / n, losses / n
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (n - 1) + max(d, 0.0)) / n
        avg_loss = (avg_loss * (n - 1) + max(-d, 0.0)) / n
    if avg_gain + avg_loss == 0:
        return None
    return 100.0 * avg_gain / (avg_gain + avg_loss)


def up_volume_share(closes: list[float], volumes: list[float | None], n: int) -> float | None:
    """Share of the last ``n`` sessions' volume that printed on up days.

    This is the measurable buys-versus-sells at a daily lookback. It returns
    None unless the ENTIRE window is present: a partial window is a different
    measurement over a different period, not this one, and silently shortening
    the lookback is how a feature comes to mean whatever the data allowed.
    """
    if n < 1 or len(closes) < n + 1 or len(volumes) < len(closes):
        return None
    up = down = 0.0
    for i in range(len(closes) - n, len(closes)):
        v = volumes[i]
        if v is None:
            return None
        if closes[i] > closes[i - 1]:
            up += v
        elif closes[i] < closes[i - 1]:
            down += v
    total = up + down
    return (up / total) if total > 0 else None


def deceleration(
    ret_short: float | None, n_short: int, ret_long: float | None, n_long: int
) -> float | None:
    """How far the recent pace has fallen below the trend's pace.

    ``0`` means the short window is running at the long window's daily rate;
    ``1`` means it has stopped entirely while the long window still reads
    positive; negative means it is ACCELERATING.

    Defined only against a positive long-window return -- asking whether a
    decline is decelerating is a different question with a different sign
    convention, and conflating them would let a falling asset score as
    persistent. Returns None rather than guessing which was meant.
    """
    if ret_short is None or ret_long is None:
        return None
    if n_short < 1 or n_long < 1 or ret_long <= 0:
        return None
    return 1.0 - (ret_short / n_short) / (ret_long / n_long)


def robust_z(x: float | None, peers: list[float | None]) -> float | None:
    """Median/MAD cross-sectional score, matching ``terminal.ranking``.

    Returns None when the cross-section has no dispersion, so a degenerate
    peer set yields a withheld feature instead of a fabricated zero that would
    read as an ordinary measurement.
    """
    vals = sorted(v for v in peers if v is not None)
    if x is None or len(vals) < 3:
        return None
    mid = len(vals) // 2
    median = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2.0
    devs = sorted(abs(v - median) for v in vals)
    dmid = len(devs) // 2
    mad = devs[dmid] if len(devs) % 2 else (devs[dmid - 1] + devs[dmid]) / 2.0
    if mad <= 0:
        return None
    return (x - median) / (1.4826 * mad)


@dataclass(frozen=True)
class Features:
    """One asset's continuation inputs. Every field may be None.

    align:    +1 price > 50dma > 200dma; 0 price > 50dma but 50dma <= 200dma;
              -1 price below the 50dma (a broken trend, which overrides the
              band verdict entirely).
    stretch:  normalized distance above the 50dma, on a 0..3 scale.
    far200:   normalized distance above the 200dma, on a 0..3 scale.
    range_pos: position in the trailing range, 0..1.
    day_pct:  latest session's percent move, signed.
    flow:     share of recent volume on up days, 0..1.
    rsi:      Wilder RSI, 0..100.
    decay:    see :func:`deceleration`.
    """

    align: int | None = None
    stretch: float | None = None
    far200: float | None = None
    range_pos: float | None = None
    day_pct: float | None = None
    flow: float | None = None
    rsi: float | None = None
    decay: float | None = None


@dataclass(frozen=True)
class Score:
    horizon: str
    value: int | None
    verdict: str
    coverage: float
    persist: list[tuple[str, float, float]] = field(default_factory=list)
    exhaust: list[tuple[str, float, float]] = field(default_factory=list)

    @property
    def scored(self) -> bool:
        return self.value is not None


def _verdict(value: int | None, align: int | None) -> str:
    if value is None:
        return NO_SCORE
    if align == -1:
        return BREAK
    if value >= 62:
        return CONTINUE
    if value >= 45:
        return MIXED
    if value >= 30:
        return PULLBACK_RISK
    return PULLBACK


def score(
    features: Features, horizon: str, systemic_gaps: frozenset[str] | set[str] = frozenset()
) -> Score:
    """Score one asset at one horizon.

    ``systemic_gaps`` names exhaustion terms the caller has established are
    missing for the ENTIRE cross-section -- because no reachable feed serves
    them, not because this asset withheld them. Those are dropped for everyone
    instead of charged at :data:`MISSING_EXHAUST`. The distinction is the whole
    point: an asset that alone cannot produce a reading has told you something
    about itself, while a feed outage has told you something about your
    pipeline, and charging the second as if it were the first penalises every
    asset for the analyst's missing API key.

    Raises for an unknown horizon rather than falling back to a default: a
    silently-defaulted horizon would report a 3-day judgment under a 30-day
    label, which is worse than an error.
    """
    if horizon not in PERSIST_WEIGHT:
        raise ValueError(f"unknown horizon: {horizon!r}")

    f = features
    persist: list[tuple[str, float, float]] = []
    exhaust: list[tuple[str, float, float]] = []
    have = total = 0

    total += 1
    if f.align is not None:
        have += 1
        persist.append(("trend", {1: 100.0, 0: 55.0, -1: 0.0}[f.align], 1.0))

    total += 1
    if f.range_pos is not None:
        have += 1
        # The upper range is where momentum regimes live -- but past ~0.95 the
        # same reading is exhaustion, and it is charged there instead.
        v = 100.0 * clamp((f.range_pos - 0.35) / 0.45, 0.0, 1.0) if f.range_pos <= 0.95 else 70.0
        persist.append(("range", v, 0.8))

    total += 1
    if f.flow is not None:
        have += 1
        persist.append(("flow", 100.0 * clamp((f.flow - 0.35) / 0.30, 0.0, 1.0), 1.1))

    total += 1
    if f.day_pct is not None:
        have += 1
        persist.append(("today", 100.0 * clamp((f.day_pct + 2.0) / 4.0, 0.0, 1.0), 0.9))

    total += 1
    if f.rsi is not None:
        have += 1
        persist.append(("rsi", 100.0 * clamp((f.rsi - 40.0) / 30.0, 0.0, 1.0), 0.9))

    total += 1
    if f.stretch is not None:
        have += 1
    total += 1
    if f.decay is not None:
        have += 1
    total += 1
    if f.far200 is not None:
        have += 1

    def charge(name: str, value: float | None, weight: float) -> None:
        """Place one exhaustion term, or account for its absence."""
        if value is not None:
            exhaust.append((name, value, weight))
        elif name not in systemic_gaps:
            exhaust.append((name, MISSING_EXHAUST, weight))
        # A systemic gap is dropped: no charge, and no weight in the divisor.

    # Wilder's own overbought threshold, not a fitted one.
    charge(
        "overbought", None if f.rsi is None else 100.0 * clamp((f.rsi - 70.0) / 15.0, 0.0, 1.0), 1.0
    )
    charge("stretch", None if f.stretch is None else 100.0 * clamp(f.stretch / 3.0, 0.0, 1.0), 1.3)
    charge(
        "decay",
        None if f.decay is None else 100.0 * clamp(f.decay, 0.0, 1.0),
        DECAY_WEIGHT[horizon],
    )
    charge(
        "far200",
        None if f.far200 is None else 100.0 * clamp(f.far200 / 3.0, 0.0, 1.0),
        FAR200_WEIGHT[horizon],
    )
    charge(
        "topped",
        None if f.range_pos is None else 100.0 * clamp((f.range_pos - 0.95) / 0.05, 0.0, 1.0),
        0.9,
    )
    # An uptrend name falling today is the crack that precedes the break.
    charge(
        "crack",
        None
        if (f.day_pct is None or f.align is None)
        else (100.0 * clamp(-f.day_pct / 5.0, 0.0, 1.0) if f.align >= 0 else 0.0),
        1.0,
    )

    coverage = have / total if total else 0.0
    if not persist or coverage < MIN_COVERAGE:
        return Score(horizon, None, NO_SCORE, coverage, persist, exhaust)

    pv = sum(v * w for _, v, w in persist) / sum(w for _, _, w in persist)
    # Every non-systemic term carries weight here whether or not it was
    # measured, so the divisor does not shrink when a reading is missing.
    # Without that, each additional zero-valued term would dilute the average
    # and raise the score -- making a substituted 0.0 strictly better than an
    # honest gap.
    ew = sum(w for _, _, w in exhaust)
    ev = (sum(v * w for _, v, w in exhaust) / ew) if ew else 0.0
    raw = 50.0 + (PERSIST_WEIGHT[horizon] * (pv - 50.0) - EXHAUST_WEIGHT[horizon] * ev) / 2.0
    # Round before deriving the verdict: the published number and its label
    # must come from the same value, or a score shown as 45 can carry the band
    # label belonging to 44.
    value = int(round(clamp(raw, 0.0, 100.0)))
    return Score(horizon, value, _verdict(value, f.align), coverage, persist, exhaust)


def score_all(
    features: Features, systemic_gaps: frozenset[str] | set[str] = frozenset()
) -> dict[str, Score]:
    return {h: score(features, h, systemic_gaps) for h in HORIZONS}
