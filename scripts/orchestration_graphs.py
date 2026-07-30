"""Stateful orchestration graphs on LangGraph.

Incorporates langchain-ai/langgraph (pinned in
requirements/runtime-orchestration.txt) as the executable form of three
things the governance layer previously stated only as prose:

1. The specialist lifecycle (candidate → shadow → active → value-proven,
   with restricted/deprecated/retired exits) as a StateGraph whose edge
   guards are the acceptance gates — a specialist cannot advance from
   shadow to active unless every gate condition is recorded true.
   The gate logic itself is NOT implemented here: per the seam rule in
   docs/RECONCILIATION_2026-07-24.md, ``runtime/lifecycle.py`` is the sole
   authority and this module only projects graph state onto it.
2. Cadence runs (from the brain manifests' [[cadence_routes]]) as linear
   graphs ending in the integrator as the terminal reduction node.
3. The irreversible-action boundary as a human-in-the-loop checkpoint:
   the mission graph interrupts before the irreversible node and waits
   for Joe; resuming is an explicit act.

Everything here is offline: nodes are pure functions and the injected
step executor decides what a "step" does (live LLM execution is an
activation-time injection).
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Callable, TypedDict

from runtime.lifecycle import (
    AgentLifecycleState,
    ModeEvidence,
    Stage,
    evaluate_administrative,
    evaluate_promotion,
)
from runtime.lifecycle import PROMOTIONS as _RUNTIME_PROMOTIONS

try:  # degrade cleanly when the runtime stack is not installed
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, StateGraph

    LANGGRAPH_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised in stdlib CI
    LANGGRAPH_AVAILABLE = False

ROOT = Path(__file__).resolve().parents[1]

LIFECYCLE_STAGES = [stage.value for stage in Stage]

# String view of runtime.lifecycle.PROMOTIONS for graph state, which carries
# stage names as plain strings. Derived, never restated.
PROMOTIONS = {
    source.value: target.value for source, target in _RUNTIME_PROMOTIONS.items()
}

# Graph gate flags mapped onto the AgentLifecycleState / ModeEvidence fields
# that runtime.lifecycle actually reads. This module owns the vocabulary a
# caller types into graph state; it owns none of the gate logic. Adding a gate
# in runtime/lifecycle.py without adding it here is caught by
# tests/test_reconciliation.py::test_lifecycle_gate_parity.

# candidate -> shadow (runtime.lifecycle.shadow_gate)
SHADOW_GATE_FIELDS = {
    "static_contracts_valid": "static_contract_valid",
    "synthetic_packets_valid": "synthetic_packets_valid",
    "registered": "registered",
}

# shadow -> active, agent-level (runtime.lifecycle.active_gate)
ACTIVE_AGENT_GATE_FIELDS = {
    "connector_isolation_verified": "connector_isolation_runtime_verified",
    # Activation is Joe's call, not the graph's. Previously absent here, which
    # let this graph promote shadow -> active with no human checkpoint.
    "joe_approved_activation": "joe_approved_activation",
}

# shadow -> active, per material mode (runtime.lifecycle.ModeEvidence)
MODE_GATE_FIELDS = {
    "controlled_mission_per_material_mode": "real_mission_completed",
    "boundary_behavior_verified": "boundary_behavior_verified",
    "typed_v21_output_proven": "handoff_schema_valid",
    "writer_lease_compliance": "writer_lease_compliant",
    "readback_on_mutation": "readback_verified",
}

AGENT_GATE_FIELDS = {**SHADOW_GATE_FIELDS, **ACTIVE_AGENT_GATE_FIELDS}

# Flags a caller must record true for each promotion. Each tuple contains
# exactly the flags the corresponding runtime gate consults — no more.
SHADOW_GATES = tuple(SHADOW_GATE_FIELDS)
ACTIVE_GATES = tuple(ACTIVE_AGENT_GATE_FIELDS) + tuple(MODE_GATE_FIELDS)

DEFAULT_MATERIAL_MODE = "all_material_modes"


def load_manifest(brain: str, root: Path = ROOT) -> dict[str, Any]:
    with (root / "brains" / brain.lower() / "agents.toml").open("rb") as source:
        return tomllib.load(source)


class LifecycleState(TypedDict, total=False):
    agent: str
    brain: str
    stage: str
    gates: dict[str, bool]
    material_modes: list[str]
    evidence_source: str
    violation: str
    decision_log: list[str]


def to_runtime_state(state: LifecycleState) -> AgentLifecycleState:
    """Project graph state onto the canonical runtime.lifecycle dataclass.

    Each named material mode gets one ModeEvidence carrying the flat gate
    flags. ``mutation_occurred`` is always true so ``readback_on_mutation`` is
    a live requirement rather than one that silently self-satisfies — the
    conservative reading of gate 4.
    """
    gates = state.get("gates", {})
    modes = state.get("material_modes") or [DEFAULT_MATERIAL_MODE]
    evidence = [
        ModeEvidence(
            mode=mode,
            mutation_occurred=True,
            **{
                field: bool(gates.get(flag))
                for flag, field in MODE_GATE_FIELDS.items()
            },
        )
        for mode in modes
    ]
    runtime_state = AgentLifecycleState(
        agent_id=state.get("agent", "unknown"),
        brain=state.get("brain", "unknown"),
        stage=Stage(state["stage"]),
        material_modes=evidence,
        administrative_reason=state.get("violation", ""),
        **{
            field: bool(gates.get(flag))
            for flag, field in AGENT_GATE_FIELDS.items()
        },
    )
    if state.get("evidence_source"):
        runtime_state.evidence_source = state["evidence_source"]
    return runtime_state


def _evaluate(state: LifecycleState) -> LifecycleState:
    log = list(state.get("decision_log", []))
    if state.get("violation"):
        log.append(f"violation recorded: {state['violation']}")
        return {"decision_log": log}
    result = evaluate_promotion(to_runtime_state(state))
    if result.from_stage is result.to_stage:
        log.append(f"evaluated at stage {state['stage']}")
    elif result.allowed:
        log.append("all active gates satisfied")
    else:
        log.append(f"gates unsatisfied: {', '.join(result.failures)}")
    return {"decision_log": log}


def _route(state: LifecycleState) -> str:
    if state.get("violation"):
        return "restrict"
    return "promote" if evaluate_promotion(to_runtime_state(state)).allowed else "hold"


def _promote(state: LifecycleState) -> LifecycleState:
    nxt = evaluate_promotion(to_runtime_state(state)).to_stage.value
    return {
        "stage": nxt,
        "decision_log": state.get("decision_log", []) + [f"promoted to {nxt}"],
    }


def _hold(state: LifecycleState) -> LifecycleState:
    return {"decision_log": state.get("decision_log", []) + ["held at current stage"]}


def _restrict(state: LifecycleState) -> LifecycleState:
    """Administrative move to restricted, adjudicated by runtime.lifecycle.

    Refusals are honored: retired is terminal, and a violation with no recorded
    reason is not a valid administrative transition.
    """
    result = evaluate_administrative(to_runtime_state(state), Stage.RESTRICTED)
    log = state.get("decision_log", [])
    if not result.allowed:
        return {"decision_log": log + [f"restriction refused: {'; '.join(result.failures)}"]}
    return {
        "stage": Stage.RESTRICTED.value,
        "decision_log": log + ["moved to restricted"],
    }


def build_lifecycle_graph():
    """The lifecycle state machine with acceptance gates as edge guards."""
    graph = StateGraph(LifecycleState)
    graph.add_node("evaluate", _evaluate)
    graph.add_node("promote", _promote)
    graph.add_node("hold", _hold)
    graph.add_node("restrict", _restrict)
    graph.set_entry_point("evaluate")
    graph.add_conditional_edges(
        "evaluate", _route,
        {"promote": "promote", "hold": "hold", "restrict": "restrict"},
    )
    graph.add_edge("promote", END)
    graph.add_edge("hold", END)
    graph.add_edge("restrict", END)
    return graph.compile()


class CadenceState(TypedDict, total=False):
    cadence: str
    steps: list[dict[str, Any]]


def build_cadence_graph(
    brain: str,
    cadence: str,
    step_fn: Callable[[str, CadenceState], dict[str, Any]],
    root: Path = ROOT,
):
    """One cadence route as a linear graph; the integrator is terminal.

    `step_fn(agent, state)` executes one agent's step and returns its
    record — injected, so live execution is an activation-time decision.
    """
    manifest = load_manifest(brain, root)
    route = next(
        item for item in manifest["cadence_routes"] if item["cadence"] == cadence
    )
    order = list(route["order"]) + [route["integrator"]]

    graph = StateGraph(CadenceState)

    def make_node(agent: str):
        def node(state: CadenceState) -> CadenceState:
            record = step_fn(agent, state)
            return {"steps": state.get("steps", []) + [{"agent": agent, **record}]}
        return node

    for agent in order:
        graph.add_node(agent, make_node(agent))
    graph.set_entry_point(order[0])
    for current, nxt in zip(order, order[1:]):
        graph.add_edge(current, nxt)
    graph.add_edge(order[-1], END)
    return graph.compile()


class MissionState(TypedDict, total=False):
    mission: str
    actions: list[str]
    irreversible_action: str
    approved_by_joe: bool


def build_mission_graph():
    """Mission flow with the irreversible boundary as a Joe checkpoint.

    The graph interrupts before `execute_irreversible`; execution resumes
    only when the run is explicitly continued with `approved_by_joe` set —
    the explicit-task-level-instruction rule, executable.
    """

    def plan(state: MissionState) -> MissionState:
        return {"actions": state.get("actions", []) + ["planned"]}

    def execute_reversible(state: MissionState) -> MissionState:
        return {"actions": state.get("actions", []) + ["reversible work done"]}

    def execute_irreversible(state: MissionState) -> MissionState:
        if not state.get("approved_by_joe"):
            raise PermissionError(
                "irreversible action requires Joe's explicit approval"
            )
        return {
            "actions": state.get("actions", [])
            + [f"irreversible executed: {state.get('irreversible_action', '?')}"]
        }

    graph = StateGraph(MissionState)
    graph.add_node("plan", plan)
    graph.add_node("execute_reversible", execute_reversible)
    graph.add_node("execute_irreversible", execute_irreversible)
    graph.set_entry_point("plan")
    graph.add_edge("plan", "execute_reversible")
    graph.add_edge("execute_reversible", "execute_irreversible")
    graph.add_edge("execute_irreversible", END)
    return graph.compile(
        checkpointer=MemorySaver(), interrupt_before=["execute_irreversible"]
    )
