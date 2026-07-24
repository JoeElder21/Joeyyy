"""Lifecycle gate engine for the specialist corps.

Encodes the stage machine from ``docs/AGENT_REGISTRY.md``::

    candidate -> shadow -> active -> value-proven
    (any) -> restricted / deprecated -> retired

as pure, stdlib-only functions so the gates are testable in the stdlib CI
environment. ``runtime/lifecycle_graph.py`` wires these gates into a LangGraph
``StateGraph`` when langgraph is installed; the gate logic never depends on it.

Gate sources (docs/SPECIALIST_ACCEPTANCE_TESTS.md, global gates):

- Gate 4 (lifecycle honesty): static and synthetic packet tests permit shadow;
  every material mode needs a controlled real mission, runtime
  connector-isolation evidence, and readback where mutation occurs before
  active.
- Gate 20 (connector isolation): activation requires runtime evidence.
- Gate 21 (harness honesty): the validation harness pass cannot promote an
  agent — promotion demands evidence the harness cannot produce.
- Gate 11 (value gate): value-proven requires no critical boundary failure,
  return-schema compliance, low false-alert burden, and positive net value.

Promotion to ``active`` additionally requires Joe's explicit approval — the
human-in-the-loop checkpoint from the integration build-out plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Stage(str, Enum):
    CANDIDATE = "candidate"
    SHADOW = "shadow"
    ACTIVE = "active"
    VALUE_PROVEN = "value-proven"
    RESTRICTED = "restricted"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


# Forward promotions; administrative moves are handled separately.
PROMOTIONS: dict[Stage, Stage] = {
    Stage.CANDIDATE: Stage.SHADOW,
    Stage.SHADOW: Stage.ACTIVE,
    Stage.ACTIVE: Stage.VALUE_PROVEN,
}

ADMINISTRATIVE_TARGETS = {Stage.RESTRICTED, Stage.DEPRECATED, Stage.RETIRED}


@dataclass
class ModeEvidence:
    """Controlled real-mission evidence for one material mode (gate 4)."""

    mode: str
    real_mission_completed: bool = False
    boundary_behavior_verified: bool = False
    handoff_schema_valid: bool = False
    mutation_occurred: bool = False
    readback_verified: bool = False
    writer_lease_compliant: bool = True

    def promotion_failures(self) -> list[str]:
        failures = []
        if not self.real_mission_completed:
            failures.append(f"mode {self.mode}: no controlled real-mission evidence")
        if not self.boundary_behavior_verified:
            failures.append(f"mode {self.mode}: boundary behavior unverified")
        if not self.handoff_schema_valid:
            failures.append(f"mode {self.mode}: handoff not schema-valid")
        if not self.writer_lease_compliant:
            failures.append(f"mode {self.mode}: writer-lease violation")
        if self.mutation_occurred and not self.readback_verified:
            failures.append(f"mode {self.mode}: mutation without verified readback")
        return failures


@dataclass
class AgentLifecycleState:
    agent_id: str
    brain: str
    stage: Stage
    # candidate -> shadow (gate 4, first half)
    static_contract_valid: bool = False
    synthetic_packets_valid: bool = False
    registered: bool = False
    # shadow -> active (gates 4, 20, 21 + human checkpoint)
    material_modes: list[ModeEvidence] = field(default_factory=list)
    connector_isolation_runtime_verified: bool = False
    evidence_source: str = "none"  # "harness" alone can never promote (gate 21)
    joe_approved_activation: bool = False
    # active -> value-proven (gate 11)
    critical_boundary_failures: int = 0
    return_schema_compliant: bool = False
    false_alert_burden_low: bool = False
    net_value_positive_after_review: bool = False
    # administrative
    administrative_reason: str = ""


def shadow_gate(state: AgentLifecycleState) -> list[str]:
    failures = []
    if not state.registered:
        failures.append("agent is not registered in the agent registry")
    if not state.static_contract_valid:
        failures.append("static contract validation has not passed")
    if not state.synthetic_packets_valid:
        failures.append("synthetic packet validation has not passed")
    return failures


def active_gate(state: AgentLifecycleState) -> list[str]:
    failures = []
    if not state.material_modes:
        failures.append("no material-mode evidence recorded")
    for mode in state.material_modes:
        failures.extend(mode.promotion_failures())
    if not state.connector_isolation_runtime_verified:
        failures.append("no runtime connector-isolation evidence (gate 20)")
    if state.evidence_source == "harness":
        failures.append(
            "harness honesty (gate 21): the validation harness pass cannot promote an agent"
        )
    if not state.joe_approved_activation:
        failures.append("activation requires Joe's explicit approval (human checkpoint)")
    return failures


def value_proven_gate(state: AgentLifecycleState) -> list[str]:
    failures = []
    if state.critical_boundary_failures > 0:
        failures.append("critical boundary failure on record (gate 11)")
    if not state.return_schema_compliant:
        failures.append("return-schema compliance not demonstrated (gate 11)")
    if not state.false_alert_burden_low:
        failures.append("false-alert burden not shown low (gate 11)")
    if not state.net_value_positive_after_review:
        failures.append("net value after review not positive (gate 11)")
    return failures


_GATES = {
    Stage.SHADOW: shadow_gate,
    Stage.ACTIVE: active_gate,
    Stage.VALUE_PROVEN: value_proven_gate,
}


@dataclass
class TransitionResult:
    agent_id: str
    from_stage: Stage
    to_stage: Stage
    allowed: bool
    failures: list[str]


def evaluate_promotion(state: AgentLifecycleState) -> TransitionResult:
    """Evaluate the next forward promotion for the agent's current stage."""
    if state.stage not in PROMOTIONS:
        return TransitionResult(
            state.agent_id,
            state.stage,
            state.stage,
            False,
            [f"stage {state.stage.value} has no forward promotion"],
        )
    target = PROMOTIONS[state.stage]
    failures = _GATES[target](state)
    return TransitionResult(state.agent_id, state.stage, target, not failures, failures)


def evaluate_administrative(
    state: AgentLifecycleState, target: Stage
) -> TransitionResult:
    """Restrict, deprecate, or retire an agent. Requires a recorded reason.

    Retired is terminal: nothing transitions out of it, ever.
    """
    failures = []
    if target not in ADMINISTRATIVE_TARGETS:
        failures.append(f"{target.value} is not an administrative target stage")
    if state.stage is Stage.RETIRED:
        failures.append("retired is terminal; no transition may leave it")
    if not state.administrative_reason.strip():
        failures.append("administrative transitions require a recorded reason")
    return TransitionResult(state.agent_id, state.stage, target, not failures, failures)


def apply(result: TransitionResult, state: AgentLifecycleState) -> AgentLifecycleState:
    """Apply an allowed transition; refuses disallowed results fail-closed."""
    if not result.allowed:
        raise PermissionError(
            f"{result.agent_id}: {result.from_stage.value} -> {result.to_stage.value} "
            f"blocked: {'; '.join(result.failures)}"
        )
    state.stage = result.to_stage
    return state
