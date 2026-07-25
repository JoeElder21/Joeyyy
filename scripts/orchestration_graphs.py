"""Stateful orchestration graphs on LangGraph.

Incorporates langchain-ai/langgraph (pinned in
requirements/runtime-orchestration.txt) as the executable form of three
things the governance layer previously stated only as prose:

1. The specialist lifecycle (candidate → shadow → active → value-proven,
   with restricted/deprecated/retired exits) as a StateGraph whose edge
   guards are the acceptance gates — a specialist cannot advance from
   shadow to active unless every gate condition is recorded true.
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

try:  # degrade cleanly when the runtime stack is not installed
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, StateGraph

    LANGGRAPH_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised in stdlib CI
    LANGGRAPH_AVAILABLE = False

ROOT = Path(__file__).resolve().parents[1]

LIFECYCLE_STAGES = [
    "candidate", "shadow", "active", "value-proven",
    "restricted", "deprecated", "retired",
]

# Gate conditions for shadow -> active, per README and
# docs/SPECIALIST_ACCEPTANCE_TESTS.md. Every gate must be recorded true.
ACTIVE_GATES = (
    "static_contracts_valid",
    "typed_v21_output_proven",
    "controlled_mission_per_material_mode",
    "connector_isolation_verified",
    "writer_lease_compliance",
    "readback_on_mutation",
)

PROMOTIONS = {
    "candidate": "shadow",
    "shadow": "active",
    "active": "value-proven",
}


def load_manifest(brain: str, root: Path = ROOT) -> dict[str, Any]:
    with (root / "brains" / brain.lower() / "agents.toml").open("rb") as source:
        return tomllib.load(source)


class LifecycleState(TypedDict, total=False):
    agent: str
    stage: str
    gates: dict[str, bool]
    violation: str
    decision_log: list[str]


def _evaluate(state: LifecycleState) -> LifecycleState:
    log = list(state.get("decision_log", []))
    if state.get("violation"):
        log.append(f"violation recorded: {state['violation']}")
    elif state["stage"] == "shadow":
        missing = [gate for gate in ACTIVE_GATES if not state.get("gates", {}).get(gate)]
        log.append(
            "all active gates satisfied" if not missing
            else f"gates unsatisfied: {', '.join(missing)}"
        )
    else:
        log.append(f"evaluated at stage {state['stage']}")
    return {"decision_log": log}


def _route(state: LifecycleState) -> str:
    if state.get("violation"):
        return "restrict"
    if state["stage"] not in PROMOTIONS:
        return "hold"
    if state["stage"] == "shadow":
        gates = state.get("gates", {})
        if not all(gates.get(gate) for gate in ACTIVE_GATES):
            return "hold"
    return "promote"


def _promote(state: LifecycleState) -> LifecycleState:
    nxt = PROMOTIONS[state["stage"]]
    return {
        "stage": nxt,
        "decision_log": state.get("decision_log", []) + [f"promoted to {nxt}"],
    }


def _hold(state: LifecycleState) -> LifecycleState:
    return {"decision_log": state.get("decision_log", []) + ["held at current stage"]}


def _restrict(state: LifecycleState) -> LifecycleState:
    return {
        "stage": "restricted",
        "decision_log": state.get("decision_log", []) + ["moved to restricted"],
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
