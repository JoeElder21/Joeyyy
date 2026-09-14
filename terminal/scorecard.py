"""Reproducible rankings.

The equity scorecard is a fixed 100-point rubric. Each factor is scored on
``[0, 1]`` from stated inputs and multiplied by its weight. A factor without
evidence is *unscored*: it is removed from the denominator, never imputed as an
average, and the result reports how much of the rubric was actually earned.
Any missing core factor makes the asset INSUFFICIENT and keeps it out of the
ranking. The crypto rubric is carried as PROPOSED until it is approved; its
results say so on every row.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field

EQUITY_WEIGHTS: dict[str, int] = {
    "fundamentals": 20,
    "valuation": 20,
    "catalysts_revisions": 15,
    "downside_protection": 15,
    "portfolio_fit": 10,
    "technicals_liquidity": 10,
    "evidence_quality": 10,
}
EQUITY_CORE = frozenset({"fundamentals", "valuation", "downside_protection"})

# Proposed, not adopted: see docs/TERMINAL_CRYPTO_RUBRIC_PROPOSAL.md.
CRYPTO_WEIGHTS_PROPOSED: dict[str, int] = {
    "liquidity_realizability": 25,
    "supply_integrity": 15,
    "holder_structure": 15,
    "trend_entry": 15,
    "venue_quality": 10,
    "catalyst": 10,
    "evidence_quality": 10,
}
CRYPTO_CORE = frozenset({"liquidity_realizability", "supply_integrity"})

SCORED, PARTIAL, INSUFFICIENT = "SCORED", "PARTIAL", "INSUFFICIENT"
MIN_COVERAGE = 0.70
UPSIDE_HURDLE = 0.15
RUBRIC_VERSION = "EQUITY_SCORECARD_100_V1"
CRYPTO_RUBRIC_VERSION = "CRYPTO_SCORECARD_100_PROPOSED_V0"


@dataclass(frozen=True)
class ScorecardResult:
    rubric: str
    rubric_status: str
    status: str
    score: float | None
    earned: float
    possible: int
    coverage: float
    factors: dict[str, float | None]
    unscored: list[str]
    input_digest: str
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "rubric": self.rubric,
            "rubric_status": self.rubric_status,
            "status": self.status,
            "score": self.score,
            "earned": self.earned,
            "possible": self.possible,
            "coverage": self.coverage,
            "factors": dict(self.factors),
            "unscored": list(self.unscored),
            "input_digest": self.input_digest,
            "notes": list(self.notes),
        }


def clamp01(value: float) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("factor values must be finite numbers")
    return max(0.0, min(1.0, number))


def input_digest(payload: object) -> str:
    """A stable digest of the inputs, so identical inputs are provably identical."""
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _score(
    factors: dict[str, float | None],
    evidence: dict[str, list[str]] | None,
    weights: dict[str, int],
    core: frozenset[str],
    rubric: str,
    rubric_status: str,
) -> ScorecardResult:
    unknown = set(factors) - set(weights)
    if unknown:
        raise ValueError(f"unknown factors for {rubric}: {sorted(unknown)}")
    notes: list[str] = []
    resolved: dict[str, float | None] = {}
    for name in weights:
        value = factors.get(name)
        if name == "evidence_quality" and value is None and evidence is not None:
            scored_names = [n for n in weights if n != name and factors.get(n) is not None]
            if scored_names:
                cited = sum(1 for n in scored_names if evidence.get(n))
                value = cited / len(scored_names)
                notes.append("evidence_quality derived from citation coverage")
        resolved[name] = None if value is None else round(clamp01(value), 4)
    unscored = [name for name, value in resolved.items() if value is None]
    possible = sum(weights[name] for name in weights if resolved[name] is not None)
    earned = round(
        sum(weights[name] * resolved[name] for name in weights if resolved[name] is not None), 2
    )
    coverage = round(possible / sum(weights.values()), 4)
    digest = input_digest({"rubric": rubric, "factors": resolved, "evidence": evidence or {}})
    missing_core = sorted(core & set(unscored))
    if missing_core:
        notes.append(f"core factor(s) unscored: {', '.join(missing_core)}")
        return ScorecardResult(
            rubric,
            rubric_status,
            INSUFFICIENT,
            None,
            earned,
            possible,
            coverage,
            resolved,
            unscored,
            digest,
            notes,
        )
    score = round(100.0 * earned / possible, 1)
    status = SCORED if coverage >= MIN_COVERAGE else PARTIAL
    if status == PARTIAL:
        notes.append(f"coverage {coverage:.0%} is below the {MIN_COVERAGE:.0%} floor")
    return ScorecardResult(
        rubric,
        rubric_status,
        status,
        score,
        earned,
        possible,
        coverage,
        resolved,
        unscored,
        digest,
        notes,
    )


def score_equity(
    factors: dict[str, float | None], evidence: dict[str, list[str]] | None = None
) -> ScorecardResult:
    return _score(factors, evidence, EQUITY_WEIGHTS, EQUITY_CORE, RUBRIC_VERSION, "ADOPTED")


def score_crypto(
    factors: dict[str, float | None], evidence: dict[str, list[str]] | None = None
) -> ScorecardResult:
    return _score(
        factors, evidence, CRYPTO_WEIGHTS_PROPOSED, CRYPTO_CORE, CRYPTO_RUBRIC_VERSION, "PROPOSED"
    )


def clears_hurdle(expected_upside: float | None, hurdle: float = UPSIDE_HURDLE) -> bool:
    """The screening hurdle: probability-weighted upside must reach the hurdle."""
    return expected_upside is not None and expected_upside >= hurdle


def rank(results: dict[str, ScorecardResult]) -> list[tuple[str, ScorecardResult]]:
    """Ranked, deterministic: fully covered first, then score, then coverage, then id."""
    ranked = [(key, r) for key, r in results.items() if r.status != INSUFFICIENT]
    ranked.sort(
        key=lambda item: (
            item[1].status != SCORED,
            -(item[1].score or 0.0),
            -item[1].coverage,
            item[0],
        )
    )
    return ranked
