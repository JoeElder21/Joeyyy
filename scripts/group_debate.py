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
- ``llm_config`` is injected and may not carry ``tools`` or ``functions``:
  a specialist's tool surface is its MCP mounts, never a model grant. Tests
  pass ``llm_config=False`` with scripted auto-replies, which is fully
  offline; live model access is an activation-time injection under the
  shadow-stage gates.

API line — resolved 2026-07-30
------------------------------
This module previously imported ``autogen_agentchat`` (AutoGen 0.4+) while
``runtime/autogen_orchestrator.py`` and ``runtime/autogen_groupchat.py``
imported ``autogen`` (0.2). Those are different distributions of the same
name: ``autogen-agentchat>=0.2.35,<0.3``, which this repository pins, provides
``autogen`` and never ``autogen_agentchat``. ``autogen_ext`` — which this
module's tests also needed — appeared in no manifest at all.

The consequence was not a skipped test. This module is what
``docs/RECONCILIATION_2026-07-24.md`` closes build ticket 4 with, so the
registered challenge pairs — the adversarial review that keeps strategy honest
against dated evidence — were **unsatisfiable** under any installation of the
declared dependency set. Installing the full stack for the first time on
2026-07-30 is what surfaced it.

Converged onto 0.2, the pinned line, rather than moving the other two modules
to 0.4: those carry the governed, packet-validating, currently-passing path,
and 0.4 has no direct equivalent of the orchestrator's speaker-order guard.
Moving to the maintained 0.4 line remains worth doing and is recorded as its
own decision in ``docs/SHADOW_EXIT_STATUS_2026-07-30.md``; it is a migration of
all three modules together, not a side effect of this repair.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.agent_runtime import CHIEF, load_roster
from scripts.orchestration_graphs import load_manifest

ROOT = Path(__file__).resolve().parents[1]


class DebateRefused(Exception):
    """The requested debate or chat violates the manifest governance."""


import tomllib  # noqa: E402
from dataclasses import dataclass  # noqa: E402


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
        raise DebateRefused(f"brain-private chat rejects non-{brain} participants: {unknown}")
    return GroupChatPlan(
        brain=brain,
        participants=requested,
        speaker_order=tuple(n for n in roster_order if n in requested),
    )


@dataclass(frozen=True)
class BrainChat:
    """A built, not-yet-started group chat plus the agents it speaks through.

    Mirrors the shape ``runtime/autogen_groupchat.build_group_chat`` returns, so
    a caller holding either can drive both the same way. Nothing here has run:
    starting the chat is the caller's act, under the shadow-stage gates.
    """

    manager: Any
    groupchat: Any
    agents: dict[str, Any]
    speaker_order: tuple[str, ...]


def _reject_tool_grants(llm_config: Any) -> None:
    """Connector isolation at the model boundary (same rule as the orchestrator).

    ``False`` is the offline no-model form and is always allowed. Anything else
    must be a non-empty mapping that grants no direct callable surface: a
    specialist's tools are its MCP mounts, and a model-side ``tools`` or
    ``functions`` grant would route straight around
    ``connector_policy = "packet_only_no_direct_connectors"``.
    """
    if llm_config is False:
        return
    if not isinstance(llm_config, dict) or not llm_config:
        raise DebateRefused("llm_config must be a non-empty mapping or False")
    forbidden = {"functions", "tools"}.intersection(llm_config)
    if forbidden:
        raise DebateRefused(
            f"specialist llm_config cannot grant direct {sorted(forbidden)}; "
            "a specialist's tool surface is its MCP mounts"
        )


try:  # degrade cleanly when the runtime stack is not installed
    from autogen import ConversableAgent, GroupChat, GroupChatManager

    AUTOGEN_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised in stdlib CI
    AUTOGEN_AVAILABLE = False


if AUTOGEN_AVAILABLE:

    def _assistant(name: str, meta: dict[str, Any], llm_config: Any) -> ConversableAgent:
        return ConversableAgent(
            name=name,
            system_message=(
                f"{meta['description']} Argue from evidence, cite sources, "
                "and stay strictly inside your brain's records."
            ),
            llm_config=llm_config,
            human_input_mode="NEVER",
            # A debating specialist executes nothing. Without this, AutoGen
            # will run code blocks a model emits.
            code_execution_config=False,
        )

    def _chat(
        agents: list[ConversableAgent],
        llm_config: Any,
        max_round: int,
        *,
        selection: str = "round_robin",
    ) -> BrainChat:
        """Assemble the GroupChat and its manager from an ordered agent list.

        ``round_robin`` follows the list order, which every caller below builds
        from the manifest — so manifest order *is* speaking order, with no
        second source of truth to drift against.
        """
        groupchat = GroupChat(
            agents=agents,
            messages=[],
            max_round=max_round,
            speaker_selection_method=selection,
            allow_repeat_speaker=False,
        )
        manager = GroupChatManager(groupchat=groupchat, llm_config=llm_config, silent=True)
        return BrainChat(
            manager=manager,
            groupchat=groupchat,
            agents={agent.name: agent for agent in agents},
            speaker_order=tuple(agent.name for agent in agents),
        )

    def build_challenge_debate(
        brain: str,
        pair: tuple[str, str],
        llm_config: Any,
        max_turns: int = 4,
        root: Path = ROOT,
    ) -> BrainChat:
        """A registered challenge pair as a real two-agent debate."""
        _reject_tool_grants(llm_config)
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
                {
                    **roster[name],
                    "description": f"{roster[name]['description']} Debate purpose: {purpose}",
                },
                llm_config,
            )
            for name in pair
        ]
        return _chat(agents, llm_config, max_round=max_turns)

    def build_cadence_chat(
        brain: str,
        cadence: str,
        llm_config: Any,
        root: Path = ROOT,
    ) -> BrainChat:
        """A cadence route as a group chat; manifest order is speaking order."""
        _reject_tool_grants(llm_config)
        manifest = load_manifest(brain, root)
        route = next(item for item in manifest["cadence_routes"] if item["cadence"] == cadence)
        roster = load_roster(root)
        order = list(route["order"]) + [route["integrator"]]
        agents = [_assistant(name, roster[name], llm_config) for name in order]
        return _chat(agents, llm_config, max_round=len(order))

    def build_planned_chat(
        plan: GroupChatPlan,
        llm_config: Any,
        root: Path = ROOT,
    ) -> BrainChat:
        """Construct the chat a validated plan describes, in plan order."""
        _reject_tool_grants(llm_config)
        roster = load_roster(root)
        agents = [_assistant(name, roster[name], llm_config) for name in plan.speaker_order]
        return _chat(agents, llm_config, max_round=max(2, len(agents) * 2))

    def build_selector_chat(
        brain: str,
        llm_config: Any,
        max_turns: int = 8,
        root: Path = ROOT,
    ) -> BrainChat:
        """Dynamic who-speaks-next over one brain's specialists plus 007.

        ``auto`` selection is the 0.2 equivalent of 0.4's SelectorGroupChat: the
        manager's own model picks the next speaker. It therefore needs a real
        ``llm_config``; with ``False`` there is no model to select with, and a
        silently-degraded round-robin masquerading as dynamic selection is
        exactly the kind of quiet fallback this repository keeps removing.
        """
        _reject_tool_grants(llm_config)
        if llm_config is False:
            raise DebateRefused(
                "selector chat requires a model to choose the next speaker; "
                "llm_config=False cannot select and must not fall back to round-robin"
            )
        roster = load_roster(root)
        members = [
            _assistant(name, meta, llm_config)
            for name, meta in sorted(roster.items())
            if meta["brain"] == brain or name == CHIEF
        ]
        return _chat(members, llm_config, max_round=max_turns, selection="auto")
