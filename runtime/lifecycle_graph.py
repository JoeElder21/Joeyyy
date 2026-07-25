"""LangGraph StateGraph over the lifecycle gate engine.

Build ticket #1 from ``docs/INTEGRATION_BUILDOUT_2026-07-24.md``: the stage
machine ``candidate -> shadow -> active -> value-proven`` as an executable
graph. The graph pauses (LangGraph interrupt) before any promotion into
``active`` so Joe's approval is a hard runtime checkpoint, not a doc rule.

langgraph is imported lazily: importing this module without langgraph
installed raises only when ``build_lifecycle_graph`` is called, keeping the
stdlib CI environment importable.

Usage::

    graph = build_lifecycle_graph()
    config = {"configurable": {"thread_id": "apex_war_architect"}}
    out = graph.invoke({"state": agent_state}, config)   # runs until gate/interrupt
    # On an activation attempt the graph interrupts; after Joe approves:
    graph.update_state(config, {"joe_approved_activation": True})
    out = graph.invoke(None, config)                     # resume
"""

from __future__ import annotations

from typing import Any, TypedDict

from .lifecycle import (
    AgentLifecycleState,
    Stage,
    TransitionResult,
    apply,
    evaluate_promotion,
)


class LifecycleGraphState(TypedDict, total=False):
    state: AgentLifecycleState
    result: TransitionResult
    joe_approved_activation: bool
    log: list[str]


def _evaluate(graph_state: LifecycleGraphState) -> LifecycleGraphState:
    agent_state = graph_state["state"]
    if graph_state.get("joe_approved_activation"):
        agent_state.joe_approved_activation = True
    result = evaluate_promotion(agent_state)
    log = graph_state.get("log", [])
    log.append(
        f"{result.agent_id}: {result.from_stage.value} -> {result.to_stage.value}: "
        + ("allowed" if result.allowed else "; ".join(result.failures))
    )
    return {"result": result, "log": log}


def _needs_joe(graph_state: LifecycleGraphState) -> str:
    result = graph_state["result"]
    pending_activation = (
        result.to_stage is Stage.ACTIVE
        and not graph_state["state"].joe_approved_activation
    )
    if pending_activation:
        return "await_joe"
    return "apply" if result.allowed else "blocked"


def _await_joe(graph_state: LifecycleGraphState) -> LifecycleGraphState:
    # Interrupt target: compiled with interrupt_before=["await_joe"], the graph
    # halts before this node until Joe's approval is written into state.
    return {}


def _apply(graph_state: LifecycleGraphState) -> LifecycleGraphState:
    apply(graph_state["result"], graph_state["state"])
    log = graph_state.get("log", [])
    log.append(
        f"{graph_state['state'].agent_id}: now {graph_state['state'].stage.value}"
    )
    return {"log": log}


def _blocked(graph_state: LifecycleGraphState) -> LifecycleGraphState:
    return {}


def build_lifecycle_graph(checkpointer: Any = None):
    """Compile the lifecycle StateGraph. Requires langgraph."""
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, StateGraph

    builder = StateGraph(LifecycleGraphState)
    builder.add_node("evaluate", _evaluate)
    builder.add_node("await_joe", _await_joe)
    builder.add_node("apply", _apply)
    builder.add_node("blocked", _blocked)
    builder.set_entry_point("evaluate")
    builder.add_conditional_edges(
        "evaluate",
        _needs_joe,
        {"await_joe": "await_joe", "apply": "apply", "blocked": "blocked"},
    )
    # After Joe's approval the promotion is re-evaluated from scratch — the
    # approval never bypasses the evidence gates.
    builder.add_edge("await_joe", "evaluate")
    builder.add_edge("apply", END)
    builder.add_edge("blocked", END)
    return builder.compile(
        checkpointer=checkpointer or MemorySaver(),
        interrupt_before=["await_joe"],
    )
