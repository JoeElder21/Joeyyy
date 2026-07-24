"""AutoGen GroupChat adapter for brain-private Agent 007 missions.

This adapter deliberately creates a chat for one brain at a time.  Agent 007
chooses and starts a brain-private chat, then remains the sole integrator of
APEX and JEOS results.  It never supplies connectors, secrets, or write access
on behalf of a specialist.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
CHIEF_OF_STAFF = "apex_chief_of_staff"


@dataclass(frozen=True)
class GroupChatPlan:
    """Validated, brain-private speaking plan derived from the manifest."""

    brain: str
    participants: tuple[str, ...]
    speaker_order: tuple[str, ...]
    manager: str = CHIEF_OF_STAFF


def load_manifest(root: Path = ROOT) -> dict[str, Any]:
    with (root / "config" / "specialist_corps.toml").open("rb") as source:
        return tomllib.load(source)


def plan_group_chat(
    brain: str,
    participants: Iterable[str],
    *,
    manifest: dict[str, Any] | None = None,
) -> GroupChatPlan:
    """Return a deterministic GroupChat plan or reject a boundary violation."""
    loaded = manifest or load_manifest()
    if brain not in {"APEX", "JEOS"}:
        raise ValueError("brain must be APEX or JEOS")
    roster = loaded[f"{brain.lower()}_roster"]
    requested = tuple(dict.fromkeys(participants))
    if not requested:
        raise ValueError("a GroupChat needs at least one specialist")
    invalid = [agent for agent in requested if agent not in roster]
    if invalid:
        raise ValueError(f"brain-private GroupChat rejects non-{brain} agents: {invalid}")
    if any(loaded["agents"][agent]["brain"] != brain for agent in requested):
        raise ValueError("GroupChat participants must belong to the declared brain")
    order = tuple(agent for agent in roster if agent in requested)
    return GroupChatPlan(brain=brain, participants=requested, speaker_order=order)


def build_group_chat(
    plan: GroupChatPlan,
    llm_config: dict[str, Any] | bool,
    *,
    system_message_factory: Callable[[str], str] | None = None,
) -> tuple[Any, Any, dict[str, Any]]:
    """Build, but do not start, legacy AutoGen ConversableAgent GroupChat.

    ``llm_config`` is supplied only by a verified runtime.  The returned
    specialist map gives the runtime a place to attach packet-only handlers.
    Importing AutoGen here means a missing runtime dependency fails clearly at
    execution rather than silently falling back to an ungoverned simulation.
    """
    from autogen import ConversableAgent, GroupChat, GroupChatManager

    make_message = system_message_factory or (
        lambda agent: (
            f"You are {agent}, a {plan.brain}-only Agent 007 specialist. "
            "Use only delegated packet evidence; return a schema-valid handoff; "
            "do not use direct connectors or mutate external systems."
        )
    )
    specialists = {
        agent: ConversableAgent(name=agent, system_message=make_message(agent), llm_config=llm_config)
        for agent in plan.speaker_order
    }
    group = GroupChat(
        agents=list(specialists.values()),
        messages=[],
        max_round=max(2, len(specialists) * 2),
        speaker_selection_method="round_robin",
    )
    manager = GroupChatManager(
        groupchat=group,
        name=f"{plan.brain.lower()}_groupchat_manager",
        llm_config=llm_config,
    )
    return manager, group, specialists
