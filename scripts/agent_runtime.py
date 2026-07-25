"""Runtime bridge: PacketGuard-governed handoffs on the OpenAI Agents SDK.

This module makes the handoff contract executable. `handoff_packet.schema.json`
and `delegation_packet.schema.json` define what a lawful transfer of control
looks like; the OpenAI Agents SDK (`openai-agents`, absorbed per
docs/INTEGRATION_ROADMAP.md) supplies the runtime primitives — `Agent`,
`handoff()`, guardrails — and this bridge wires PacketGuard into them so an
invalid packet cannot transfer control at all.

Layering:

- The stdlib core (roster loading, the hash-chained audit ledger, packet
  admission) imports with no third-party dependencies, matching the
  degrade-cleanly rule from scripts/verify_runtime_stack.py.
- The SDK layer activates only when `openai-agents` is installed. Building the
  governed agent graph makes no network calls and needs no API key; only
  `Runner.run()` does, and nothing here invokes it.

Topology enforced: Agent 007 may hand off to every registered specialist; a
specialist may hand off only back to Agent 007. Specialists never receive
handoffs to one another, in either brain — cross-specialist coordination is
routed through Agent 007 per AGENTS.md.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import tomllib
from typing import Any

from scripts.packet_guard import PacketGuard

ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = ROOT / ".codex" / "agents"
CHIEF = "apex_chief_of_staff"
LEDGER_GENESIS = "agent007-audit-genesis"


class HandoffRejected(Exception):
    """A delegation packet failed admission; control must not transfer."""

    def __init__(self, target: str, errors: list[str]):
        super().__init__(f"handoff to {target!r} rejected: {'; '.join(errors)}")
        self.target = target
        self.errors = errors


def load_roster(root: Path = ROOT) -> dict[str, dict[str, Any]]:
    """Load every native agent definition: name -> {brain, description, instructions}."""
    roster: dict[str, dict[str, Any]] = {}
    for path in sorted((root / ".codex" / "agents").glob("*.toml")):
        with path.open("rb") as source:
            data = tomllib.load(source)
        name = data["name"]
        brain = "cross-brain" if name == CHIEF else (
            "APEX" if name.startswith("apex_") else "JEOS"
        )
        roster[name] = {
            "brain": brain,
            "description": data.get("description", ""),
            "instructions": data.get("developer_instructions", ""),
        }
    return roster


class AuditLedger:
    """Append-only, hash-chained JSONL audit log (absorbed pattern: block/buzz).

    Each entry stores the SHA-256 of the previous entry's canonical line; the
    first entry chains to a fixed genesis constant. Editing any historical
    line breaks every hash after it, so `verify()` detects rewrites.
    """

    def __init__(self, path: Path):
        self.path = path

    @staticmethod
    def _canonical(entry: dict[str, Any]) -> str:
        return json.dumps(entry, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _digest(line: str) -> str:
        return hashlib.sha256(line.encode("utf-8")).hexdigest()

    def _last_hash(self) -> str:
        if not self.path.exists():
            return self._digest(LEDGER_GENESIS)
        last = None
        with self.path.open("r", encoding="utf-8") as source:
            for raw in source:
                raw = raw.strip()
                if raw:
                    last = raw
        if last is None:
            return self._digest(LEDGER_GENESIS)
        return self._digest(last)

    def append(self, event: str, detail: dict[str, Any]) -> dict[str, Any]:
        entry = {
            "at": datetime.now(timezone.utc).isoformat(),
            "detail": detail,
            "event": event,
            "prev_hash": self._last_hash(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as sink:
            sink.write(self._canonical(entry) + "\n")
        return entry

    def verify(self) -> list[str]:
        """Return chain violations; empty list means the ledger is intact."""
        errors: list[str] = []
        expected = self._digest(LEDGER_GENESIS)
        if not self.path.exists():
            return errors
        with self.path.open("r", encoding="utf-8") as source:
            for index, raw in enumerate(source):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError:
                    errors.append(f"line {index}: not valid JSON")
                    continue
                if entry.get("prev_hash") != expected:
                    errors.append(f"line {index}: chain broken")
                if self._canonical(entry) != raw:
                    errors.append(f"line {index}: non-canonical field order")
                expected = self._digest(raw)
        return errors


def admit_delegation(
    packet: dict[str, Any],
    target: str,
    roster: dict[str, dict[str, Any]],
    guard: PacketGuard,
    ledger: AuditLedger | None = None,
    *,
    leases: list[dict[str, Any]] | None = None,
) -> None:
    """Fail-closed admission for a delegation handoff. Raises HandoffRejected.

    Checks, in order: PacketGuard schema + relational validation (which also
    enforces the v2.1 legacy gate), addressee match, and the brain lock
    (packet owner_brain must equal the target specialist's brain).
    """
    errors = guard.validate("delegation_packet.schema.json", packet, leases)
    if not errors and packet.get("agent") != target:
        errors = [f"packet addresses {packet.get('agent')!r}, not {target!r}"]
    if not errors:
        target_brain = roster.get(target, {}).get("brain")
        if packet.get("owner_brain") != target_brain:
            errors = [
                f"brain lock: packet owner_brain {packet.get('owner_brain')!r} "
                f"does not match {target!r} brain {target_brain!r}"
            ]
    if errors:
        if ledger is not None:
            ledger.append(
                "handoff_rejected",
                {"target": target, "errors": errors,
                 "delegation_id": packet.get("delegation_id")},
            )
        raise HandoffRejected(target, errors)
    if ledger is not None:
        ledger.append(
            "handoff_admitted",
            {"target": target, "delegation_id": packet.get("delegation_id"),
             "mode": packet.get("mode")},
        )


def validate_specialist_return(
    handoff_packet: dict[str, Any],
    guard: PacketGuard,
    ledger: AuditLedger | None = None,
    *,
    delegations: list[dict[str, Any]] | None = None,
    leases: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Validate a specialist's returned handoff packet; log the outcome."""
    errors = guard.validate(
        "handoff_packet.schema.json", handoff_packet, leases,
        delegations=delegations,
    )
    if ledger is not None:
        ledger.append(
            "return_validated" if not errors else "return_rejected",
            {"agent": handoff_packet.get("agent"),
             "delegation_id": handoff_packet.get("delegation_id"),
             "status": handoff_packet.get("status"), "errors": errors},
        )
    return errors


# --- SDK layer -----------------------------------------------------------

try:  # degrade cleanly when the runtime stack is not installed
    from agents import Agent, handoff  # type: ignore
    from pydantic import BaseModel  # type: ignore

    SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised in stdlib CI
    SDK_AVAILABLE = False


if SDK_AVAILABLE:

    class DelegationHandoffInput(BaseModel):
        """Typed handoff payload: the delegation packet as canonical JSON.

        The JSON schema in schemas/ stays the single source of truth; this
        wrapper gives the SDK a strict-schema-compatible typed transport
        without duplicating the schema as pydantic fields (which would
        drift). The packet travels as a JSON string because the SDK's
        strict mode forbids open object fields.
        """

        packet_json: str

    def governed_handoff(
        target,
        roster: dict[str, dict[str, Any]],
        guard: PacketGuard,
        ledger: AuditLedger | None = None,
    ):
        """A handoff() whose on_handoff runs PacketGuard admission fail-closed."""

        def on_handoff(ctx, payload: DelegationHandoffInput) -> None:
            try:
                packet = json.loads(payload.packet_json)
            except json.JSONDecodeError as error:
                raise HandoffRejected(
                    target.name, [f"packet_json is not valid JSON: {error}"]
                ) from error
            admit_delegation(packet, target.name, roster, guard, ledger)

        return handoff(
            agent=target,
            input_type=DelegationHandoffInput,
            on_handoff=on_handoff,
            tool_description_override=(
                f"Transfer control to {target.name} with a schema-valid v2.1 "
                "delegation packet. Invalid packets are rejected before transfer."
            ),
        )

    def build_governed_graph(
        guard: PacketGuard | None = None,
        ledger: AuditLedger | None = None,
        root: Path = ROOT,
        model: str | None = None,
    ):
        """Build Agent 007 plus all registered specialists with governed topology.

        Returns (chief, specialists_by_name). Construction is offline: no
        network calls and no API key are needed until a Runner executes.
        """
        guard = guard or PacketGuard(root)
        roster = load_roster(root)
        kwargs = {"model": model} if model else {}

        chief_meta = roster[CHIEF]
        chief = Agent(
            name=CHIEF,
            handoff_description=chief_meta["description"],
            instructions=chief_meta["instructions"],
            **kwargs,
        )

        specialists = {}
        for name, meta in roster.items():
            if name == CHIEF:
                continue
            specialist = Agent(
                name=name,
                handoff_description=meta["description"],
                instructions=meta["instructions"],
                # Specialists return to Agent 007 only; no specialist-to-
                # specialist handoffs exist in either brain.
                handoffs=[chief],
                **kwargs,
            )
            specialists[name] = specialist

        chief.handoffs = [
            governed_handoff(specialist, roster, guard, ledger)
            for _, specialist in sorted(specialists.items())
        ]
        return chief, specialists
