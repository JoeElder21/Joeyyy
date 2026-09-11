"""Scenario mathematics with one definition of return.

Total return over a horizon is ``(end value + distributions - entry - costs) / entry``.
Probability-weighted return is the probability-weighted sum of scenario
returns, with the probabilities required to sum to one. Nothing here converts
a model output into a probability of being right; the numbers are inputs an
analyst states and a critic can challenge.
"""

from __future__ import annotations

from dataclasses import dataclass

PROBABILITY_TOLERANCE = 1e-6


@dataclass(frozen=True)
class Scenario:
    name: str
    probability: float
    end_value: float
    distributions: float = 0.0


@dataclass(frozen=True)
class WeightedReturn:
    expected: float
    by_scenario: dict[str, float]
    best: float
    worst: float
    asymmetry: float | None

    def as_dict(self) -> dict:
        return {
            "expected": self.expected,
            "by_scenario": dict(self.by_scenario),
            "best": self.best,
            "worst": self.worst,
            "asymmetry": self.asymmetry,
        }


def total_return(
    entry: float, end_value: float, distributions: float = 0.0, costs: float = 0.0
) -> float:
    if entry <= 0:
        raise ValueError("entry price must be positive")
    if costs < 0 or distributions < 0:
        raise ValueError("costs and distributions cannot be negative")
    return (end_value + distributions - entry - costs) / entry


def probability_weighted(
    entry: float, scenarios: list[Scenario], costs: float = 0.0
) -> WeightedReturn:
    if not scenarios:
        raise ValueError("at least one scenario is required")
    total = sum(s.probability for s in scenarios)
    if any(s.probability < 0 or s.probability > 1 for s in scenarios):
        raise ValueError("each probability must lie in [0, 1]")
    if abs(total - 1.0) > PROBABILITY_TOLERANCE:
        raise ValueError(f"probabilities sum to {total:.6f}, not 1")
    names = [s.name for s in scenarios]
    if len(set(names)) != len(names):
        raise ValueError("scenario names must be unique")
    by_scenario = {
        s.name: round(total_return(entry, s.end_value, s.distributions, costs), 6)
        for s in scenarios
    }
    expected = round(sum(s.probability * by_scenario[s.name] for s in scenarios), 6)
    best, worst = max(by_scenario.values()), min(by_scenario.values())
    asymmetry = None if worst >= 0 else round(best / abs(worst), 4) if best > 0 else 0.0
    return WeightedReturn(expected, by_scenario, best, worst, asymmetry)


def base_beats_bear(by_scenario: dict[str, float], base: str = "base", bear: str = "bear") -> bool:
    """The mandate's automatic-rejection test: base-case upside must exceed bear-case loss."""
    if base not in by_scenario or bear not in by_scenario:
        raise KeyError("scenarios need a base and a bear case")
    return by_scenario[base] > abs(min(by_scenario[bear], 0.0))
