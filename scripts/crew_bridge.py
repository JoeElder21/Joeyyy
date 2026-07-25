"""Crew bridge: the TOML roster as crewAI role-based crews.

Incorporates crewAIInc/crewAI (pinned `crewai` in
requirements/runtime-orchestration.txt). The native agent definitions map
near-1:1 onto crewAI's Agent constructor (role/goal/backstory), delegation
packets map onto Task (description/expected_output/agent), and the mirrored
class structure maps onto two parallel brain crews with Agent 007 as the
integration step consuming both outputs.

Governance preserved at the bridge:

- Every task enters a crew only through `admit_delegation()` — the same
  fail-closed PacketGuard admission as every other runtime path.
- A crew is single-brain by construction: mixing APEX and JEOS packets in
  one crew raises. Cross-brain integration belongs to Agent 007, outside
  either crew.
- crewAI's built-in delegation stays enabled *within* a crew, which matches
  the community protocol: same-brain specialists may collaborate; the crew
  boundary is the brain boundary.

Building agents, tasks, and crews is offline; `Crew.kickoff()` (live LLM
execution) is activation-gated and never called here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.agent_runtime import (
    AuditLedger,
    HandoffRejected,
    admit_delegation,
    load_roster,
)
from scripts.packet_guard import PacketGuard

ROOT = Path(__file__).resolve().parents[1]

try:  # degrade cleanly when the runtime stack is not installed
    from crewai import Agent as CrewAgent
    from crewai import Crew, Process
    from crewai import Task as CrewTask

    CREWAI_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised in stdlib CI
    CREWAI_AVAILABLE = False


if CREWAI_AVAILABLE:

    def crew_agent(name: str, meta: dict[str, Any]) -> CrewAgent:
        """Map one native TOML definition onto crewAI's Agent constructor."""
        return CrewAgent(
            role=name,
            goal=meta["description"],
            backstory=meta["instructions"] or meta["description"],
            allow_delegation=True,
            verbose=False,
        )

    def task_from_packet(
        packet: dict[str, Any],
        agents: dict[str, CrewAgent],
        roster: dict[str, dict[str, Any]],
        guard: PacketGuard,
        ledger: AuditLedger | None = None,
    ) -> CrewTask:
        """Admit the delegation packet, then express it as a crewAI Task."""
        target = packet.get("agent", "")
        admit_delegation(packet, target, roster, guard, ledger)
        expected = (
            "Typed artifacts of type(s) "
            + ", ".join(packet.get("required_artifact_types", []))
            + " satisfying definition-of-done IDs "
            + ", ".join(packet.get("definition_of_done_ids", []))
            + ", returned as a schema-valid v2.1 handoff packet."
        )
        return CrewTask(
            description=packet["mission"],
            expected_output=expected,
            agent=agents[target],
        )

    def build_brain_crew(
        brain: str,
        packets: list[dict[str, Any]],
        guard: PacketGuard | None = None,
        ledger: AuditLedger | None = None,
        root: Path = ROOT,
    ) -> "Crew":
        """Build one single-brain sequential crew from admitted packets."""
        guard = guard or PacketGuard(root)
        roster = load_roster(root)
        wrong = [p.get("agent") for p in packets
                 if roster.get(p.get("agent", ""), {}).get("brain") != brain]
        if wrong:
            raise HandoffRejected(
                brain, [f"crew is {brain}-only; packets address {wrong}"]
            )
        agents = {
            name: crew_agent(name, meta)
            for name, meta in roster.items()
            if meta["brain"] == brain
        }
        tasks = [
            task_from_packet(packet, agents, roster, guard, ledger)
            for packet in packets
        ]
        return Crew(
            agents=list(agents.values()),
            tasks=tasks,
            process=Process.sequential,
            verbose=False,
        )
