"""Entry economics: what the trade actually costs, and whether it qualifies.

A rank that ignores the entry price is a statement about an asset, not about a
decision. The same forecast is worth less when bought extended, worth less
again when the round trip costs 90 basis points, and worth nothing when the
book cannot absorb the notional. This module makes those deductions explicit
and publishes each one separately.

The decision functional:

    U(i, h, q) = shrunk_expected_gross_return(i, h)
                 - round_trip_cost(i, h, q)
                 - lambda(h) * downside_tail_loss(i, h)
                 - kappa(h)  * mean_estimate_uncertainty(i, h)

Four things about it are load-bearing:

* Every term is in the same unit -- fraction of notional over the horizon.
  Mixing an annualised volatility into a 7-day return is the classic way these
  formulas silently become nonsense.
* ``downside_tail_loss`` is a NON-NEGATIVE magnitude, so the subtraction is
  always a penalty. ``terminal.quant.expected_shortfall`` guarantees the sign.
* Lambda and kappa are RISK POLICY, not constants discovered in a paper. They
  are declared in the config, versioned, and published with the result.
* The output is an absolute estimated net edge in return units. Only after
  that is shown does anything get mapped to a percentile -- and a percentile is
  never called a probability.

No part of this module authorises a trade. It prices one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Entry states. The list deliberately includes three ways of saying "not now".
ACTIONABLE = "ACTIONABLE"  # qualifies at the quoted price
WAIT = "WAIT"  # good asset, poor entry -- a level is named
WATCH = "WATCH"  # interesting, but no entry rule is defensible yet
NO_QUALIFYING_ENTRY = "NO_QUALIFYING_ENTRY"  # net edge does not clear the floor
EXCLUDE = "EXCLUDE"  # a hard block: identity, liquidity, or a verified event

STATES = (ACTIONABLE, WAIT, WATCH, NO_QUALIFYING_ENTRY, EXCLUDE)

# Standardised research notionals. These are RESEARCH sizes for comparing
# execution cost across assets. They are not assumptions about anyone's
# balances and are not position-size advice.
STANDARD_NOTIONALS = (100.0, 1_000.0, 10_000.0)
DEFAULT_NOTIONAL = 1_000.0

# Square-root market impact: impact ~ coefficient * sqrt(notional / depth).
# A hypothesis with a long history in execution research, not a fitted value.
IMPACT_COEFFICIENT = 0.10
IMPACT_MODEL = "square_root_v1"

# A net edge below this does not qualify, however well the asset ranks.
DEFAULT_NET_EDGE_FLOOR = 0.0


@dataclass(frozen=True)
class CostModel:
    """Per-venue execution costs. Every component is named and published."""

    venue: str
    taker_fee: float  # fraction, one side
    gas_usd: float  # fixed cost per leg, chain fee or commission
    financing_rate: float = 0.0  # fraction per horizon, borrow or margin
    impact_coefficient: float = IMPACT_COEFFICIENT
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "venue": self.venue,
            "taker_fee": self.taker_fee,
            "gas_usd": self.gas_usd,
            "financing_rate": self.financing_rate,
            "impact_coefficient": self.impact_coefficient,
            "impact_model": IMPACT_MODEL,
            "note": self.note,
        }


# Venue cost profiles. Values are documented defaults, to be replaced by
# measured fills as the ledger accumulates them.
VENUES: dict[str, CostModel] = {
    "solana_dex": CostModel(
        "solana_dex",
        taker_fee=0.0025,
        gas_usd=0.02,
        note="AMM swap fee plus priority fee; a documented default, not a measured fill",
    ),
    "us_equity": CostModel(
        "us_equity",
        taker_fee=0.0,
        gas_usd=0.0,
        note="commission-free retail equities; spread and impact remain",
    ),
    "centralised_crypto": CostModel(
        "centralised_crypto",
        taker_fee=0.006,
        gas_usd=0.0,
        note="retail taker tier; withdrawal costs are not modelled here",
    ),
    "unknown": CostModel(
        "unknown",
        taker_fee=0.01,
        gas_usd=1.00,
        note="deliberately pessimistic placeholder for an unidentified venue",
    ),
}


@dataclass(frozen=True)
class CostBreakdown:
    """A round-trip cost, itemised. Fractions of notional over the horizon."""

    notional: float
    venue: str
    spread: float | None
    fees: float
    impact: float | None
    gas: float
    financing: float
    total: float | None
    complete: bool
    missing: list[str] = field(default_factory=list)
    note: str = ""
    impact_model: str = IMPACT_MODEL

    def as_dict(self) -> dict:
        return {
            "notional": self.notional,
            "venue": self.venue,
            "spread": self.spread,
            "fees": self.fees,
            "impact": self.impact,
            # Published so a reader can see WHICH model produced the impact
            # figure rather than having to take the number on trust.
            "impact_model": self.impact_model,
            "gas": self.gas,
            "financing": self.financing,
            "total": self.total,
            "complete": self.complete,
            "missing": list(self.missing),
            "note": self.note,
        }


def round_trip_cost(
    notional: float,
    liquidity_usd: float | None,
    spread: float | None,
    venue: str = "unknown",
    horizon_days: float = 7.0,
    spread_in_price: bool = False,
) -> CostBreakdown:
    """Itemise the cost of entering and exiting ``notional`` at this venue.

    ``spread_in_price`` says the caller already used executable bid/ask quotes
    to compute the return. When true the spread is NOT charged again here --
    double-counting it would penalise the assets with the best data.
    """
    model = VENUES.get(venue, VENUES["unknown"])
    missing: list[str] = []

    if spread_in_price:
        spread_cost = 0.0
        note = "spread already embedded in executable quotes; not charged twice"
    elif spread is None:
        spread_cost = 0.0
        missing.append("spread")
        note = "no quoted spread available"
    else:
        # Cross the spread on the way in and again on the way out.
        spread_cost = abs(spread)
        note = ""

    fees = model.taker_fee * 2.0

    if liquidity_usd is None or liquidity_usd <= 0:
        impact = None
        missing.append("liquidity_depth")
    else:
        # Entry and exit each pay impact.
        impact = 2.0 * model.impact_coefficient * math.sqrt(notional / liquidity_usd)

    gas = (model.gas_usd * 2.0) / notional if notional > 0 else 0.0
    financing = model.financing_rate * (horizon_days / 365.0)

    complete = not missing
    # No depth reading means no total: an unpriceable trade stays unpriced
    # rather than being totalled as if impact were zero.
    total = None if impact is None else spread_cost + fees + impact + gas + financing

    return CostBreakdown(
        notional=notional,
        venue=model.venue,
        spread=None if spread is None and not spread_in_price else spread_cost,
        fees=fees,
        impact=impact,
        gas=gas,
        financing=financing,
        total=total,
        complete=complete,
        missing=missing,
        note=note,
    )


@dataclass(frozen=True)
class RiskPolicy:
    """Lambda and kappa per horizon. Policy choices, published as such."""

    horizon: str
    lam: float  # weight on downside tail loss
    kappa: float  # weight on uncertainty in the mean estimate
    net_edge_floor: float = DEFAULT_NET_EDGE_FLOOR
    source: str = "risk policy default, not an empirically fitted parameter"

    def as_dict(self) -> dict:
        return {
            "horizon": self.horizon,
            "lambda": self.lam,
            "kappa": self.kappa,
            "net_edge_floor": self.net_edge_floor,
            "source": self.source,
        }


# Shorter horizons carry less forecastable signal relative to their noise, so
# the uncertainty charge is heavier. These are hypotheses.
RISK_POLICIES: dict[str, RiskPolicy] = {
    "24h": RiskPolicy("24h", lam=0.50, kappa=1.50),
    "7d": RiskPolicy("7d", lam=0.40, kappa=1.00),
    "30d": RiskPolicy("30d", lam=0.30, kappa=0.75),
}


@dataclass(frozen=True)
class Decision:
    """The full decision, with every deduction shown separately."""

    asset_id: str
    horizon: str
    notional: float
    gross_forecast: float | None
    cost: CostBreakdown
    tail_loss: float | None
    tail_adequate: bool
    mean_uncertainty: float | None
    lam: float
    kappa: float
    cost_deduction: float | None
    tail_deduction: float | None
    uncertainty_deduction: float | None
    net_edge: float | None
    state: str
    reasons: list[str] = field(default_factory=list)
    entry_plan: dict | None = None

    def as_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "horizon": self.horizon,
            "notional": self.notional,
            "gross_forecast": self.gross_forecast,
            "deductions": {
                "round_trip_cost": self.cost_deduction,
                "tail_loss_charge": self.tail_deduction,
                "estimate_uncertainty_charge": self.uncertainty_deduction,
            },
            "net_edge": self.net_edge,
            "cost_detail": self.cost.as_dict(),
            "tail_loss": self.tail_loss,
            "tail_adequate": self.tail_adequate,
            "mean_uncertainty": self.mean_uncertainty,
            "lambda": self.lam,
            "kappa": self.kappa,
            "state": self.state,
            "reasons": list(self.reasons),
            "entry_plan": self.entry_plan,
        }


def decide(
    asset_id: str,
    horizon: str,
    gross_forecast: float | None,
    cost: CostBreakdown,
    tail_loss: float | None,
    tail_adequate: bool,
    mean_uncertainty: float | None,
    policy: RiskPolicy,
    hard_blocks: list[str] | None = None,
    entry_plan: dict | None = None,
) -> Decision:
    """Apply the decision functional and resolve an entry state.

    Ordering matters. Hard blocks are checked first: no forecast, however
    attractive, survives a failed identity check or an unexecutable book. Only
    then are the deductions applied, and only a positive net edge above the
    policy floor can reach ACTIONABLE.
    """
    reasons: list[str] = []
    blocks = list(hard_blocks or [])

    if blocks:
        return Decision(
            asset_id,
            horizon,
            cost.notional,
            gross_forecast,
            cost,
            tail_loss,
            tail_adequate,
            mean_uncertainty,
            policy.lam,
            policy.kappa,
            None,
            None,
            None,
            None,
            EXCLUDE,
            [f"hard block: {b}" for b in blocks],
            entry_plan,
        )

    if gross_forecast is None:
        reasons.append("no supported gross forecast; nothing to price")
        return Decision(
            asset_id,
            horizon,
            cost.notional,
            None,
            cost,
            tail_loss,
            tail_adequate,
            mean_uncertainty,
            policy.lam,
            policy.kappa,
            None,
            None,
            None,
            None,
            WATCH,
            reasons,
            entry_plan,
        )

    if cost.total is None:
        reasons.append(
            "round-trip cost cannot be computed (" + ", ".join(cost.missing) + "); "
            "an unpriceable trade is not actionable"
        )
        return Decision(
            asset_id,
            horizon,
            cost.notional,
            gross_forecast,
            cost,
            tail_loss,
            tail_adequate,
            mean_uncertainty,
            policy.lam,
            policy.kappa,
            None,
            None,
            None,
            None,
            WATCH,
            reasons,
            entry_plan,
        )

    cost_deduction = cost.total

    # Missing risk data must never flatter a score. An absent tail estimate is
    # charged at the policy weight against a deliberately conservative stand-in
    # rather than being treated as zero risk.
    if tail_loss is None:
        tail_deduction = policy.lam * _MISSING_TAIL_STANDIN
        reasons.append(
            "no tail estimate available; charged at the conservative stand-in "
            f"of {_MISSING_TAIL_STANDIN:.0%} rather than treated as risk-free"
        )
    else:
        tail_deduction = policy.lam * tail_loss
        if not tail_adequate:
            reasons.append("tail estimated on a short sample; treat as indicative")

    if mean_uncertainty is None:
        uncertainty_deduction = policy.kappa * _MISSING_UNCERTAINTY_STANDIN
        reasons.append(
            "estimate uncertainty unavailable; charged at the conservative "
            f"stand-in of {_MISSING_UNCERTAINTY_STANDIN:.0%}"
        )
    else:
        uncertainty_deduction = policy.kappa * mean_uncertainty

    net = gross_forecast - cost_deduction - tail_deduction - uncertainty_deduction

    if net <= policy.net_edge_floor:
        state = NO_QUALIFYING_ENTRY
        reasons.append(
            f"net edge {net:+.2%} does not clear the "
            f"{policy.net_edge_floor:+.2%} floor after costs and risk charges"
        )
    elif entry_plan and entry_plan.get("trigger_required"):
        state = WAIT
        reasons.append(
            "net edge is positive but the quoted price is outside the "
            "permissible entry zone; a trigger is named and may never fill"
        )
    else:
        state = ACTIONABLE

    return Decision(
        asset_id,
        horizon,
        cost.notional,
        gross_forecast,
        cost,
        tail_loss,
        tail_adequate,
        mean_uncertainty,
        policy.lam,
        policy.kappa,
        round(cost_deduction, 6),
        round(tail_deduction, 6),
        round(uncertainty_deduction, 6),
        round(net, 6),
        state,
        reasons,
        entry_plan,
    )


# Conservative stand-ins used when a risk input is missing. Chosen so that an
# asset with no risk data can never outrank an otherwise identical asset that
# has it -- the acceptance gate that missing data cannot improve actionability.
_MISSING_TAIL_STANDIN = 0.25
_MISSING_UNCERTAINTY_STANDIN = 0.10


def entry_plan(
    reference_price: float,
    zone_low: float | None,
    zone_high: float | None,
    invalidation: float | None,
    expiry_iso: str,
    rule: str = "limit within zone",
) -> dict:
    """A named entry plan. Honest about what an unfilled order means."""
    inside = True
    if zone_low is not None and reference_price < zone_low:
        inside = False
    if zone_high is not None and reference_price > zone_high:
        inside = False
    return {
        "reference_price": reference_price,
        "zone_low": zone_low,
        "zone_high": zone_high,
        "invalidation": invalidation,
        "expiry": expiry_iso,
        "rule": rule,
        "trigger_required": not inside,
        "caveat": (
            "A pullback order may never fill and a breakout may slip. An "
            "invalidation level is a decision rule, not a guaranteed exit "
            "price; gaps trade through it."
        ),
    }


def percentile_label(net_edges: dict[str, float]) -> dict[str, float]:
    """Within-universe percentile of the NET edge.

    Called only after the absolute net edge has been shown. The returned value
    is a position within this universe on this date. It is not a probability of
    profit, and the ranking engine labels it ``score_type: percentile`` so the
    UI cannot present it as one.
    """
    from terminal.quant import fractional_ranks

    return fractional_ranks(net_edges, higher_is_better=True)
