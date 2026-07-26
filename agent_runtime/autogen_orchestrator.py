"""AutoGen-shaped, fail-closed group-chat routing for synthetic/runtime adapters.

This module deliberately keeps framework I/O outside the repository.  It turns
the existing brain rosters, cadence routes, and challenge pairs into a bounded
participant selection policy that an AutoGen adapter can use after its runtime
has passed the gate in ``config/framework_integrations.toml``.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ChatParticipant:
    """A specialist eligible for one brain-private group chat."""

    name: str
    brain: str
    modes: tuple[str, ...]


class GroupChatOrchestrator:
    """Select an eligible same-brain speaker, preserving cadence preference.

    The caller must validate every resulting handoff with PacketGuard.  Agent
    007 is represented as the integrator and may terminate a chat, but it is
    never returned as a specialist speaker.
    """

    def __init__(self, manifest_path: Path = ROOT / "config" / "specialist_corps.toml"):
        with manifest_path.open("rb") as source:
            manifest = tomllib.load(source)
        self._agents = manifest["agents"]
        self._cadence = tuple(
            tuple(route["order"])
            for route in manifest.get("cadence_routes", [])
        )

    def participants(self, owner_brain: str, mode: str) -> tuple[ChatParticipant, ...]:
        eligible = []
        for name, agent in self._agents.items():
            if agent["brain"] == owner_brain and mode in agent["modes"]:
                eligible.append(ChatParticipant(name, owner_brain, tuple(agent["modes"])))
        return tuple(sorted(eligible, key=lambda participant: participant.name))

    def select_next(self, owner_brain: str, mode: str, already_spoke: tuple[str, ...] = ()) -> str:
        """Return the next eligible specialist or fail closed when none exists."""
        eligible = {participant.name for participant in self.participants(owner_brain, mode)}
        if not eligible:
            raise ValueError(f"No {owner_brain} participant is registered for mode {mode!r}.")
        for route in self._cadence:
            for agent in route:
                if agent in eligible and agent not in already_spoke:
                    return agent
        remaining = sorted(eligible - set(already_spoke))
        if not remaining:
            raise ValueError("All eligible participants have already spoken; Agent 007 must integrate or end the chat.")
        return remaining[0]
