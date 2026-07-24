"""AutoGen 0.2 group-chat adapter that enforces Agent 007 brain boundaries.

This module turns a *single-brain* cadence route into AutoGen
``ConversableAgent`` participants and a ``GroupChatManager``.  It neither
creates model clients nor retrieves private data: the verified host runtime
must provide both.  Packets are validated before a specialist can be included
in a chat, and shadow-stage specialists remain advisory.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any, Callable, Iterable

from scripts.packet_guard import PacketGuard


ROOT = Path(__file__).resolve().parents[1]
INTEGRATOR = "apex_chief_of_staff"


@dataclass(frozen=True)
class GroupChatPlan:
    """A validated, single-brain plan for one AutoGen conversation."""

    brain: str
    cadence: str
    participants: tuple[str, ...]
    speaker_order: tuple[str, ...]
    challenge_pairs: tuple[tuple[str, ...], ...]


class AutoGenMissionOrchestrator:
    """Build and start bounded AutoGen chats from the versioned manifests."""

    def __init__(self, root: Path = ROOT, guard: PacketGuard | None = None) -> None:
        self.root = root
        self.guard = guard or PacketGuard(root)
        with (root / "config" / "specialist_corps.toml").open("rb") as source:
            self.corps = tomllib.load(source)

    def plan_cadence(self, brain: str, cadence: str) -> GroupChatPlan:
        """Return the manifest-defined speaking order for a brain cadence."""
        if brain not in {"APEX", "JEOS"}:
            raise ValueError("brain must be APEX or JEOS")
        manifest_path = self.root / self.corps[f"{brain.lower()}_brain_manifest"]
        with manifest_path.open("rb") as source:
            manifest = tomllib.load(source)
        route = next(
            (item for item in manifest["cadence_routes"] if item["cadence"] == cadence),
            None,
        )
        if route is None:
            raise ValueError(f"{brain} has no {cadence!r} cadence route")
        order = tuple(route["order"])
        self._assert_same_brain(brain, order)
        pairs = tuple(
            tuple(pair["agents"])
            for pair in manifest.get("challenge_pairs", [])
            if set(pair["agents"]).issubset(set(order))
        )
        # Agent 007 integrates after all specialists, never as a specialist.
        return GroupChatPlan(
            brain=brain,
            cadence=cadence,
            participants=order,
            speaker_order=(*order, INTEGRATOR),
            challenge_pairs=pairs,
        )

    def validate_delegations(
        self, plan: GroupChatPlan, delegations: Iterable[dict[str, Any]]
    ) -> None:
        """Fail closed unless every participant has one valid v2.1 packet."""
        by_agent = {packet.get("agent"): packet for packet in delegations}
        if set(by_agent) != set(plan.participants):
            raise ValueError("delegations must contain exactly one packet for each planned specialist")
        for agent in plan.participants:
            packet = by_agent[agent]
            if packet.get("owner_brain") != plan.brain:
                raise ValueError(f"{agent} delegation crosses the {plan.brain} brain boundary")
            self.guard.require_valid("delegation_packet.schema.json", packet)

    def build_group_chat(
        self,
        plan: GroupChatPlan,
        delegations: Iterable[dict[str, Any]],
        *,
        llm_config: dict[str, Any],
        system_message_factory: Callable[[dict[str, Any]], str],
    ) -> tuple[dict[str, Any], Any]:
        """Create AutoGen objects after packet validation.

        ``llm_config`` is deliberately caller-supplied.  Supplying it is the
        host runtime's assertion that its model access is authorized and
        configured; this repository stores no model or connector identifiers.
        """
        self.validate_delegations(plan, delegations)
        try:
            from autogen import ConversableAgent, GroupChat, GroupChatManager
        except ImportError as exc:  # pragma: no cover - exercised by host setup
            raise RuntimeError(
                "AutoGen is not installed. Install requirements.txt in a verified runtime."
            ) from exc

        packets = {packet["agent"]: packet for packet in delegations}
        specialists = {
            name: ConversableAgent(
                name=name,
                system_message=system_message_factory(packets[name]),
                llm_config=llm_config,
                human_input_mode="NEVER",
                code_execution_config=False,
            )
            for name in plan.participants
        }
        order = list(plan.speaker_order)

        def select_next(last_speaker: Any, groupchat: Any) -> Any:
            names = [message.get("name") for message in groupchat.messages]
            next_name = order[min(len(names), len(order) - 1)]
            return specialists.get(next_name, "auto")

        groupchat = GroupChat(
            agents=list(specialists.values()),
            messages=[],
            max_round=len(plan.participants),
            speaker_selection_method=select_next,
            allow_repeat_speaker=False,
        )
        manager = GroupChatManager(groupchat=groupchat, llm_config=llm_config)
        return specialists, manager

    def initiate_chat(
        self,
        agent_007: Any,
        manager: Any,
        mission: str,
    ) -> Any:
        """Use Agent 007 as the sole entry point and terminal integrator."""
        return agent_007.initiate_chat(
            manager,
            message=mission,
            clear_history=True,
            silent=True,
        )

    def _assert_same_brain(self, brain: str, agents: Iterable[str]) -> None:
        for agent in agents:
            definition = self.corps["agents"].get(agent)
            if definition is None or definition["brain"] != brain:
                raise ValueError(f"{agent} is not a registered {brain} specialist")
