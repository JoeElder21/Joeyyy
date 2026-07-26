"""Framework-neutral, brain-locked runtime plan compiled from the TOML contract.

This module executes no LLMs or connectors.  It makes the AutoGen GroupChat,
LangGraph StateGraph, crewAI Crew, and Prefect flow integrations deterministic
and testable before an approved runtime adapter is enabled.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class GroupChatPlan:
    brain: str
    participants: tuple[str, ...]
    manager: str = "apex_chief_of_staff"


def cadence_group_chat(brain: str, cadence: str, root: Path = ROOT) -> GroupChatPlan:
    """Compile a same-brain AutoGen speaking order from cadence_routes."""
    with (root / "config" / "specialist_corps.toml").open("rb") as source:
        manifest = tomllib.load(source)
    roster_key = f"{brain.lower()}_roster"
    if brain not in {"APEX", "JEOS"} or roster_key not in manifest:
        raise ValueError("brain must be APEX or JEOS")
    route = next((item for item in manifest["cadence_routes"] if item["cadence"] == cadence and item["brain"] == brain), None)
    if route is None:
        raise ValueError(f"unknown cadence: {cadence}")
    participants = tuple(route["order"])
    if not set(participants).issubset(manifest[roster_key]):
        raise ValueError("cadence route crosses a brain boundary")
    return GroupChatPlan(brain=brain, participants=participants)


def lifecycle_transition_allowed(current: str, target: str, gates_passed: bool) -> bool:
    """LangGraph-style guarded lifecycle edge; promotion requires all evidence."""
    stages = ("candidate", "shadow", "active", "value-proven", "restricted", "deprecated", "retired")
    if current not in stages or target not in stages:
        return False
    if current == "shadow" and target == "active":
        return gates_passed
    return (current, target) in {("candidate", "shadow"), ("active", "value-proven"),
                                 ("active", "restricted"), ("restricted", "active"),
                                 ("restricted", "deprecated"), ("deprecated", "retired")}
