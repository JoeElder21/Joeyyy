"""Declarative orchestration planning and lifecycle gates for Agent 007.

This module deliberately does not invoke agents or third-party orchestration
frameworks.  It provides the contracts a future runtime must satisfy: a
brain-locked speaking plan, a terminal Agent 007 reduction, lifecycle edge
guards, and an explicit pause before a high-impact action.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Checkpoint:
    """A planned pause that a runtime must resolve before continuing."""

    required: bool
    reason: str | None = None


@dataclass(frozen=True)
class CadencePlan:
    """A deterministic, same-brain specialist sequence ending at Agent 007."""

    brain: str
    cadence: str
    speakers: tuple[str, ...]
    checkpoint: Checkpoint


class OrchestrationContract:
    """Load and enforce the repository's declarative runtime contract."""

    def __init__(self, root: Path = ROOT) -> None:
        with (root / "config" / "specialist_corps.toml").open("rb") as source:
            self.manifest: dict[str, Any] = tomllib.load(source)

    def cadence_plan(
        self, brain: str, cadence: str, *, requested_actions: tuple[str, ...] = ()
    ) -> CadencePlan:
        normalized_brain = brain.upper()
        if normalized_brain not in {"APEX", "JEOS"}:
            raise ValueError(f"unknown owner brain {brain!r}")
        try:
            speakers = tuple(self.manifest["cadence"][normalized_brain.lower()][cadence])
        except KeyError as error:
            raise ValueError(f"unknown {normalized_brain} cadence {cadence!r}") from error
        self._validate_speakers(normalized_brain, speakers)
        high_impact = set(requested_actions) & set(
            self.manifest["orchestration"]["high_impact_actions"]
        )
        checkpoint = Checkpoint(
            required=bool(high_impact),
            reason=("explicit_task_level_instruction_required:" + ",".join(sorted(high_impact)))
            if high_impact
            else None,
        )
        return CadencePlan(normalized_brain, cadence, speakers, checkpoint)

    def can_promote(self, current: str, target: str, evidence: set[str]) -> bool:
        """Return whether a lifecycle edge is allowed by the declared active gate."""
        stages = self.manifest["lifecycle"]["stages"]
        if current not in stages or target not in stages:
            return False
        if current == target:
            return True
        if target in {"restricted", "deprecated", "retired"}:
            return True
        if current == "shadow" and target == "active":
            required = {
                "static_contracts",
                "typed_2_1_output",
                "controlled_real_mission_per_material_mode",
                "runtime_connector_isolation",
                "readback",
                "versioned_lifecycle_promotion",
            }
            return required <= evidence
        return stages.index(target) == stages.index(current) + 1

    def _validate_speakers(self, brain: str, speakers: tuple[str, ...]) -> None:
        integrator = self.manifest["orchestration"]["terminal_integrator"]
        if not speakers or speakers[-1] != integrator:
            raise ValueError("every cadence must terminate with Agent 007")
        for agent in speakers[:-1]:
            if self.manifest["agents"].get(agent, {}).get("brain") != brain:
                raise ValueError(f"cadence leaks {agent!r} into {brain}")
