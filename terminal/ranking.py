"""The deterministic V1 ranking engine.

Status: **HEURISTIC / NOT YET VALIDATED.** The weights below are hypotheses
chosen for economic plausibility. They are not fitted coefficients, they have
not been tested out of sample on this universe, and nothing here licenses a
claim that a high rank predicts a return.

That status has a concrete consequence, and it is the most important design
decision in this module. The decision functional in ``terminal.entry`` needs a
``shrunk_expected_gross_return``. A validated model supplies one. V1 does not
have a validated model, so V1 **does not supply one** -- it will not convert a
composite factor score into an expected percentage return, because a weighted
average of percentile ranks is not a return forecast and dressing it up as one
is the exact failure this rebuild exists to remove.

The practical result: with no external forecast, every asset resolves to WATCH
or EXCLUDE and ``net_edge`` is null. The engine still does real work -- it
ranks on structural quality, measures risk and execution cost from data,
applies hard blocks, and reports coverage -- but it reports NO QUALIFYING
ENTRY rather than inventing an edge. When a validated forecast becomes
available it is passed in via ``forecasts`` and the functional prices it.

Two invariants are enforced by construction rather than convention:

* **Group budgeting.** Weight is allocated to correlation GROUPS, then split
  within a group. Adding a fourth momentum variant dilutes the other three
  instead of tripling the influence of trend.
* **Missing never helps.** A feature the asset lacks is dropped from that
  asset's earned score but stays in its possible score, so coverage falls and
  the composite falls with it. Risk features are stronger still: absence
  scores worst observed, never neutral.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from terminal import entry as entry_mod
from terminal import features as feat
from terminal import quant

MODEL_VERSION = "SAVAGE_RANK_V1_HEURISTIC"
MODEL_STATUS = "HEURISTIC"
VALIDATION_STATUS = "NOT_YET_VALIDATED"

HORIZONS = ("24h", "7d", "30d")
DEFAULT_HORIZON = "7d"
STRUCTURAL_HORIZON = "90d"

# Coverage below this makes a composite unreliable enough to withhold.
MIN_COVERAGE = 0.60

# Group weight budgets, by asset class. Each maps a correlation group to its
# share of the composite. They sum to 1.0. These are hypotheses.
GROUP_WEIGHTS: dict[str, dict[str, float]] = {
    feat.CRYPTO: {
        "liquidity": 0.30,  # realisability dominates: an unexitable rank is worthless
        "risk": 0.25,
        "trend": 0.20,
        "supply": 0.10,
        "entry_timing": 0.08,
        "value_capture": 0.04,  # rarely applicable outside protocols with real accrual
        "positioning": 0.03,
        "events": 0.00,  # events act as a GATE, not a weighted contributor
    },
    feat.EQUITY: {
        "risk": 0.30,
        "value_capture": 0.25,
        "trend": 0.20,
        "solvency": 0.15,
        "liquidity": 0.05,
        "entry_timing": 0.05,
        "events": 0.00,
    },
}


@dataclass(frozen=True)
class RankingConfig:
    """Frozen, versioned ranking configuration. Part of the reproducibility key."""

    asset_class: str
    horizon: str
    group_weights: dict[str, float]
    min_coverage: float = MIN_COVERAGE
    notional: float = entry_mod.DEFAULT_NOTIONAL
    model_version: str = MODEL_VERSION
    config_version: str = "RANK_CFG_V1"

    def digest(self) -> str:
        payload = {
            "asset_class": self.asset_class,
            "horizon": self.horizon,
            "group_weights": {k: round(v, 6) for k, v in sorted(self.group_weights.items())},
            "min_coverage": self.min_coverage,
            "notional": self.notional,
            "model_version": self.model_version,
            "config_version": self.config_version,
        }
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def as_dict(self) -> dict:
        return {
            "asset_class": self.asset_class,
            "horizon": self.horizon,
            "group_weights": dict(self.group_weights),
            "min_coverage": self.min_coverage,
            "notional": self.notional,
            "model_version": self.model_version,
            "config_version": self.config_version,
            "model_status": MODEL_STATUS,
            "validation_status": VALIDATION_STATUS,
            "digest": self.digest(),
        }


def config_for(asset_class: str, horizon: str = DEFAULT_HORIZON, **overrides) -> RankingConfig:
    if horizon not in HORIZONS:
        raise ValueError(f"unknown horizon {horizon!r}; expected one of {HORIZONS}")
    weights = dict(GROUP_WEIGHTS[asset_class])
    return RankingConfig(
        asset_class=asset_class, horizon=horizon, group_weights=weights, **overrides
    )


@dataclass(frozen=True)
class Contribution:
    """One feature's contribution to one asset's composite."""

    feature: str
    group: str
    raw: float | None
    normalised: float | None
    weight: float
    contribution: float | None
    status: str

    def as_dict(self) -> dict:
        return {
            "feature": self.feature,
            "group": self.group,
            "raw": self.raw,
            "normalised": self.normalised,
            "weight": round(self.weight, 6),
            "contribution": self.contribution,
            "status": self.status,
        }


@dataclass(frozen=True)
class AssetRank:
    asset_id: str
    display: str
    composite: float | None
    coverage: float
    contributions: list[Contribution]
    hard_blocks: list[str]
    risk_flags: list[str]
    decision: entry_mod.Decision
    structural_quality: float | None
    data_confidence: str
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "display": self.display,
            "composite": self.composite,
            "coverage": round(self.coverage, 4),
            "structural_quality": self.structural_quality,
            "data_confidence": self.data_confidence,
            "hard_blocks": list(self.hard_blocks),
            "risk_flags": list(self.risk_flags),
            "contributions": [c.as_dict() for c in self.contributions],
            "decision": self.decision.as_dict(),
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class RankingResult:
    config: RankingConfig
    ranked: list[AssetRank]
    excluded: list[AssetRank]
    cross_sections: dict[str, dict]
    counts: dict[str, int]
    input_digest: str
    score_type: str = "within_universe_percentile"

    def as_dict(self) -> dict:
        return {
            "config": self.config.as_dict(),
            "score_type": self.score_type,
            "score_type_note": (
                "A within-universe percentile is a position among the assets "
                "scored on this date. It is NOT a probability of profit."
            ),
            "counts": dict(self.counts),
            "input_digest": self.input_digest,
            "ranked": [a.as_dict() for a in self.ranked],
            "excluded": [a.as_dict() for a in self.excluded],
            "cross_sections": dict(self.cross_sections),
        }


def _input_digest(assets: dict[str, dict], config: RankingConfig) -> str:
    """A digest over exactly the inputs that can move a rank."""
    trimmed = {
        aid: {k: v for k, v in sorted(payload.items()) if k != "_meta"}
        for aid, payload in sorted(assets.items())
    }
    text = json.dumps(
        {"assets": trimmed, "config": config.digest()},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _hard_blocks(asset_id: str, payload: dict, asset_class: str) -> list[str]:
    """Conditions that stop an actionable rank outright, checked before scoring."""
    blocks: list[str] = []
    identity = payload.get("identity") or {}
    if not identity.get("verified"):
        blocks.append(
            "asset identity is not verified (provider id plus chain and "
            "contract address, never ticker alone)"
        )
    price = payload.get("price")
    if price is None or not isinstance(price, int | float) or price <= 0:
        blocks.append("no positive price observation")
    if payload.get("stale"):
        blocks.append("price observation is stale beyond the venue tolerance")
    for flag in payload.get("event_blocks") or []:
        blocks.append(f"verified event: {flag}")
    for key in feat.blocking_features(asset_class):
        if payload.get("features", {}).get(key) is None:
            blocks.append(f"blocking feature unavailable: {key}")
    return blocks


def _within_group_weights(
    group: str, keys: list[str], available: dict[str, quant.CrossSection]
) -> dict[str, float]:
    """Split a group's budget across the features in it that are usable.

    An unusable feature returns its share to its own group, never to the whole
    model -- so a group that loses a feature keeps its total influence rather
    than silently handing weight to whatever else happens to be present.
    """
    usable = [k for k in keys if k in available and available[k].usable]
    if not usable:
        return {}
    return dict.fromkeys(usable, 1.0 / len(usable))


def rank_universe(
    assets: dict[str, dict],
    config: RankingConfig,
    forecasts: dict[str, float] | None = None,
    risk_policy: entry_mod.RiskPolicy | None = None,
) -> RankingResult:
    """Rank a universe deterministically.

    ``assets`` maps an asset id to a payload carrying ``identity``, ``price``,
    ``features`` and optional risk/return series. ``forecasts`` supplies a
    validated expected gross return per asset; when it is absent -- the state
    today -- no net edge is produced and nothing reaches ACTIONABLE.
    """
    registry = feat.for_asset_class(config.asset_class)
    policy = risk_policy or entry_mod.RISK_POLICIES[config.horizon]
    supplied = forecasts or {}

    # Hard blocks first: an excluded asset is not scored, so it cannot borrow
    # credibility from a good momentum reading.
    blocks: dict[str, list[str]] = {
        aid: _hard_blocks(aid, payload, config.asset_class) for aid, payload in assets.items()
    }
    eligible = [aid for aid, b in blocks.items() if not b]
    blocked = [aid for aid, b in blocks.items() if b]

    # Cross-sections are computed over the ELIGIBLE set only. Including blocked
    # assets would let an unexecutable token set the percentile scale.
    sections: dict[str, quant.CrossSection] = {}
    for key, feature in registry.items():
        raw = {aid: (assets[aid].get("features") or {}).get(key) for aid in eligible}
        sections[key] = quant.cross_section(
            key,
            raw,
            higher_is_better=feature.higher_is_better,
            method=feature.method,
            universe=eligible,
        )

    group_map = feat.groups(config.asset_class)
    ranks: list[AssetRank] = []

    for aid in eligible:
        payload = assets[aid]
        contributions: list[Contribution] = []
        earned = 0.0
        possible = 0.0
        flags: list[str] = list(payload.get("risk_flags") or [])
        notes: list[str] = []

        for group, budget in sorted(config.group_weights.items()):
            if budget <= 0:
                continue
            keys = group_map.get(group, [])
            if not keys:
                continue
            within = _within_group_weights(group, keys, sections)
            # The group's budget counts toward `possible` whether or not this
            # asset carries the features: that is what makes missing data cost
            # coverage instead of being quietly renormalised away.
            possible += budget
            for key in sorted(keys):
                feature = registry[key]
                section = sections.get(key)
                raw_value = (payload.get("features") or {}).get(key)
                weight = budget * within.get(key, 0.0)

                if section is None or not section.usable:
                    contributions.append(
                        Contribution(
                            key,
                            group,
                            raw_value,
                            None,
                            0.0,
                            None,
                            section.status if section else "EMPTY",
                        )
                    )
                    continue

                normalised = section.normalised.get(aid)
                if normalised is None:
                    # This asset lacks the feature. Risk features are charged
                    # the worst observed value rather than omitted, so a
                    # missing drawdown cannot look like a safe one.
                    if feature.missing_policy == feat.PENALISE:
                        earned += weight * 0.0
                        flags.append(f"{key} unavailable; scored worst")
                        contributions.append(
                            Contribution(key, group, None, 0.0, weight, 0.0, "PENALISED")
                        )
                    else:
                        contributions.append(
                            Contribution(key, group, None, None, 0.0, None, "MISSING")
                        )
                    continue

                # Round BEFORE accumulating so the contributions the terminal
                # publishes sum exactly to the composite it publishes. A reader
                # who adds the displayed column must get the displayed total;
                # accumulating full precision and rounding only at the end
                # leaves a residue that makes the trace impossible to check.
                value = round(weight * normalised, 6)
                earned += value
                contributions.append(
                    Contribution(
                        key,
                        group,
                        raw_value,
                        round(normalised, 6),
                        weight,
                        value,
                        "SCORED",
                    )
                )

        scored_weight = sum(c.weight for c in contributions)
        coverage = scored_weight / possible if possible > 0 else 0.0
        if coverage >= config.min_coverage and scored_weight > 0:
            composite = round(earned / scored_weight, 6)
        else:
            composite = None
            notes.append(
                f"coverage {coverage:.0%} is below the {config.min_coverage:.0%} "
                "floor; composite withheld rather than published on partial inputs"
            )

        # Structural quality is the non-timing part: what the asset IS, apart
        # from what its price has done lately.
        structural_groups = {"liquidity", "supply", "value_capture", "solvency", "risk"}
        s_earned = sum(c.contribution or 0.0 for c in contributions if c.group in structural_groups)
        s_weight = sum(c.weight for c in contributions if c.group in structural_groups)
        structural = round(s_earned / s_weight, 6) if s_weight > 0 else None

        # Execution economics, measured from data regardless of the model status.
        cost = entry_mod.round_trip_cost(
            notional=config.notional,
            liquidity_usd=(payload.get("features") or {}).get("liquidity_usd_raw")
            or payload.get("liquidity_usd"),
            spread=(payload.get("features") or {}).get("spread_cost"),
            venue=payload.get("venue", "unknown"),
            horizon_days=_horizon_days(config.horizon),
            spread_in_price=bool(payload.get("spread_in_price")),
        )

        returns = payload.get("return_series") or []
        tail = quant.expected_shortfall(returns) if returns else None
        uncertainty = quant.standard_error(returns) if returns else None

        gross = supplied.get(aid)
        if gross is None and supplied:
            notes.append("no validated forecast supplied for this asset")

        decision = entry_mod.decide(
            asset_id=aid,
            horizon=config.horizon,
            gross_forecast=gross,
            cost=cost,
            tail_loss=tail.expected_shortfall if tail else None,
            tail_adequate=bool(tail and tail.adequate),
            mean_uncertainty=uncertainty,
            policy=policy,
            hard_blocks=None,
            entry_plan=payload.get("entry_plan"),
        )

        if gross is None:
            notes.append(
                "V1 is HEURISTIC: no validated return model, so no expected "
                "return is derived from the composite score and no net edge is "
                "published. The composite ranks structural quality only."
            )

        ranks.append(
            AssetRank(
                asset_id=aid,
                display=payload.get("display", aid),
                composite=composite,
                coverage=coverage,
                contributions=contributions,
                hard_blocks=[],
                risk_flags=sorted(set(flags)),
                decision=decision,
                structural_quality=structural,
                data_confidence=payload.get("data_confidence", "UNKNOWN"),
                notes=notes,
            )
        )

    excluded = [
        AssetRank(
            asset_id=aid,
            display=assets[aid].get("display", aid),
            composite=None,
            coverage=0.0,
            contributions=[],
            hard_blocks=blocks[aid],
            risk_flags=sorted(set(assets[aid].get("risk_flags") or [])),
            decision=entry_mod.decide(
                asset_id=aid,
                horizon=config.horizon,
                gross_forecast=None,
                cost=entry_mod.round_trip_cost(config.notional, None, None, "unknown"),
                tail_loss=None,
                tail_adequate=False,
                mean_uncertainty=None,
                policy=policy,
                hard_blocks=blocks[aid],
            ),
            structural_quality=None,
            data_confidence="BLOCKED",
            notes=["excluded before scoring; retained in the ledger, not discarded"],
        )
        for aid in sorted(blocked)
    ]

    # Deterministic order: net edge when one exists, else composite, then
    # coverage, then asset id. The final key guarantees a stable total order.
    def sort_key(a: AssetRank):
        net = a.decision.net_edge
        return (
            net is None,
            -(net if net is not None else 0.0),
            a.composite is None,
            -(a.composite if a.composite is not None else 0.0),
            -a.coverage,
            a.asset_id,
        )

    ranks.sort(key=sort_key)

    counts = {
        "screened": len(assets),
        "eligible": len(eligible),
        "excluded": len(blocked),
        "scored": sum(1 for a in ranks if a.composite is not None),
        "actionable": sum(1 for a in ranks if a.decision.state == entry_mod.ACTIONABLE),
        "wait": sum(1 for a in ranks if a.decision.state == entry_mod.WAIT),
        "watch": sum(1 for a in ranks if a.decision.state == entry_mod.WATCH),
        "no_qualifying_entry": sum(
            1 for a in ranks if a.decision.state == entry_mod.NO_QUALIFYING_ENTRY
        ),
    }

    return RankingResult(
        config=config,
        ranked=ranks,
        excluded=excluded,
        cross_sections={k: v.as_dict() for k, v in sorted(sections.items())},
        counts=counts,
        input_digest=_input_digest(assets, config),
    )


def _horizon_days(horizon: str) -> float:
    return {"24h": 1.0, "7d": 7.0, "30d": 30.0, "90d": 90.0}.get(horizon, 7.0)


def multi_horizon(
    assets: dict[str, dict],
    asset_class: str,
    forecasts: dict[str, dict[str, float]] | None = None,
) -> dict[str, RankingResult]:
    """Rank at every horizon separately.

    Deliberately returns a mapping rather than a blended score: averaging a
    24-hour view with a 30-day view produces a number that answers no question
    anyone asked.
    """
    out: dict[str, RankingResult] = {}
    for horizon in HORIZONS:
        per_horizon = None
        if forecasts:
            per_horizon = {aid: h[horizon] for aid, h in forecasts.items() if horizon in h}
        out[horizon] = rank_universe(assets, config_for(asset_class, horizon), per_horizon)
    return out
