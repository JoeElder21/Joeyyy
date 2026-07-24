"""Group orchestration on AutoGen: challenge-pair debates and cadence chats.

Incorporates microsoft/autogen (pinned `autogen-agentchat` in
requirements/runtime-orchestration.txt). The manifests' [[challenge_pairs]]
become actual two-agent debates, cadence_routes order becomes the speaking
order of a round-robin group chat with the integrator last, and a
selector chat provides the dynamic who-speaks-next manager over a brain's
specialists — the runtime version of the static TOML routes.

Governance at the bridge:

- A debate can only be built from a pair registered in the brain manifest;
  unregistered or cross-brain pairs are refused.
- Group chats are single-brain plus Agent 007; the brain boundary is the
  chat boundary.
- The model client is injected. Tests use autogen's replay client (scripted
  turns, fully offline); live model clients are an activation-time
  injection under the shadow-stage gates.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.agent_runtime import CHIEF, load_roster
from scripts.orchestration_graphs import load_manifest

ROOT = Path(__file__).resolve().parents[1]


class DebateRefused(Exception):
    """The requested debate or chat violates the manifest governance."""


from dataclasses import dataclass  # noqa: E402
import tomllib  # noqa: E402


@dataclass(frozen=True)
class GroupChatPlan:
    """Validated, brain-private speaking plan produced before any agent
    is constructed (ported from the Codex PR #11 adapter onto the modern
    stack). Participants are a subset of one brain's canonical roster;
    speaker order follows the roster order in config/specialist_corps.toml."""

    brain: str
    participants: tuple[str, ...]
    speaker_order: tuple[str, ...]
    manager: str = CHIEF


def plan_brain_chat(
    brain: str,
    participants: list[str] | tuple[str, ...],
    root: Path = ROOT,
) -> GroupChatPlan:
    """Deterministic dry-run planning with fail-closed boundary checks."""
    if brain not in ("APEX", "JEOS"):
        raise DebateRefused("brain must be APEX or JEOS")
    with (root / "config" / "specialist_corps.toml").open("rb") as source:
        corps = tomllib.load(source)
    roster_order = corps[f"{brain.lower()}_roster"]
    requested = tuple(dict.fromkeys(participants))
    if not requested:
        raise DebateRefused("a group chat needs at least one specialist")
    unknown = [name for name in requested if name not in roster_order]
    if unknown:
        raise DebateRefused(
            f"brain-private chat rejects non-{brain} participants: {unknown}"
        )
    return GroupChatPlan(
        brain=brain,
        participants=requested,
        speaker_order=tuple(n for n in roster_order if n in requested),
    )


try:  # degrade cleanly when the runtime stack is not installed
    from autogen_agentchat.agents import AssistantAgent
    from autogen_agentchat.teams import RoundRobinGroupChat, SelectorGroupChat

    AUTOGEN_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised in stdlib CI
    AUTOGEN_AVAILABLE = False


if AUTOGEN_AVAILABLE:

    def _assistant(name: str, meta: dict[str, Any], model_client) -> AssistantAgent:
        return AssistantAgent(
            name=name,
            model_client=model_client,
            system_message=(
                f"{meta['description']} Argue from evidence, cite sources, "
                "and stay strictly inside your brain's records."
            ),
        )

    def build_challenge_debate(
        brain: str,
        pair: tuple[str, str],
        model_client,
        max_turns: int = 4,
        root: Path = ROOT,
    ) -> "RoundRobinGroupChat":
        """A registered challenge pair as a real two-agent debate."""
        manifest = load_manifest(brain, root)
        registered = {
            frozenset(item["agents"]): item["purpose"]
            for item in manifest.get("challenge_pairs", [])
        }
        if frozenset(pair) not in registered:
            raise DebateRefused(
                f"{pair} is not a registered {brain} challenge pair; "
                "debates run only on manifest-registered pairs"
            )
        roster = load_roster(root)
        for name in pair:
            if roster.get(name, {}).get("brain") != brain:
                raise DebateRefused(f"{name!r} is not a {brain} specialist")
        purpose = registered[frozenset(pair)]
        agents = [
            _assistant(
                name,
                {**roster[name],
                 "description": f"{roster[name]['description']} "
                                f"Debate purpose: {purpose}"},
                model_client,
            )
            for name in pair
        ]
        return RoundRobinGroupChat(agents, max_turns=max_turns)

    def build_cadence_chat(
        brain: str,
        cadence: str,
        model_client,
        root: Path = ROOT,
    ) -> "RoundRobinGroupChat":
        """A cadence route as a group chat; manifest order is speaking order."""
        manifest = load_manifest(brain, root)
        route = next(
            item for item in manifest["cadence_routes"] if item["cadence"] == cadence
        )
        roster = load_roster(root)
        order = list(route["order"]) + [route["integrator"]]
        agents = [_assistant(name, roster[name], model_client) for name in order]
        return RoundRobinGroupChat(agents, max_turns=len(order))

    def build_planned_chat(
        plan: GroupChatPlan,
        model_client,
        root: Path = ROOT,
    ) -> "RoundRobinGroupChat":
        """Construct the chat a validated plan describes, in plan order."""
        roster = load_roster(root)
        agents = [
            _assistant(name, roster[name], model_client)
            for name in plan.speaker_order
        ]
        return RoundRobinGroupChat(agents, max_turns=max(2, len(agents) * 2))

    def build_selector_chat(
        brain: str,
        model_client,
        max_turns: int = 8,
        root: Path = ROOT,
    ) -> "SelectorGroupChat":
        """Dynamic who-speaks-next over one brain's specialists plus 007."""
        roster = load_roster(root)
        members = [
            _assistant(name, meta, model_client)
            for name, meta in sorted(roster.items())
            if meta["brain"] == brain or name == CHIEF
        ]
        return SelectorGroupChat(
            members, model_client=model_client, max_turns=max_turns
        )
