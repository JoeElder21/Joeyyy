"""Governance MCP server: the connector-isolation rule made enforceable.

Incorporates modelcontextprotocol/python-sdk (pinned `mcp` in
requirements/runtime-contracts.txt). Every specialist carries
`connector_policy = "packet_only_no_direct_connectors"`; this server is what
that policy connects to. A specialist's entire tool surface is whatever MCP
servers Agent 007 mounts for it — starting with this one, which exposes only
governed operations. `hard_connector_isolation_required_for_active` becomes
checkable: an active-stage specialist reaches tools through MCP servers on
this pattern, never through arbitrary direct calls.

External-system servers (calendar, file storage, Civil 3D via civil3d-mcp,
APS) mount alongside this one per their own build-out guides; pre-built
reference servers (filesystem, GitHub) deploy per the integration roadmap.

Run: `python scripts/governance_mcp_server.py` (stdio transport).
Offline-testable: building the server and calling its tool functions makes
no network calls.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.agent_runtime import (  # noqa: E402
    AuditLedger,
    HandoffRejected,
    admit_delegation,
    load_roster,
    validate_specialist_return,
)
from scripts.packet_guard import PacketGuard

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / "audit" / "governance_mcp.jsonl"

try:  # degrade cleanly when the runtime stack is not installed
    from mcp.server.fastmcp import FastMCP

    MCP_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised in stdlib CI
    MCP_AVAILABLE = False


def _tool_functions(
    guard: PacketGuard, roster: dict[str, dict[str, Any]], ledger: AuditLedger
) -> dict[str, Any]:
    """The governed operations, as plain callables (testable without MCP)."""

    def validate_packet(schema_name: str, packet_json: str, historical: bool = False) -> str:
        """Validate any packet against its schema and the relational rules."""
        try:
            packet = json.loads(packet_json)
        except json.JSONDecodeError as error:
            return json.dumps({"valid": False, "errors": [f"invalid JSON: {error}"]})
        errors = guard.validate(schema_name, packet, historical=historical)
        return json.dumps({"valid": not errors, "errors": errors}, sort_keys=True)

    def admit_delegation_packet(target: str, packet_json: str) -> str:
        """Fail-closed admission for a delegation handoff to a specialist."""
        try:
            packet = json.loads(packet_json)
            admit_delegation(packet, target, roster, guard, ledger)
        except HandoffRejected as rejection:
            return json.dumps(
                {"admitted": False, "errors": rejection.errors}, sort_keys=True
            )
        except json.JSONDecodeError as error:
            return json.dumps(
                {"admitted": False, "errors": [f"invalid JSON: {error}"]}, sort_keys=True
            )
        return json.dumps(
            {"admitted": True, "target": target,
             "delegation_id": packet.get("delegation_id")},
            sort_keys=True,
        )

    def validate_handoff_return(handoff_json: str, delegation_json: str = "") -> str:
        """Validate a specialist's returned handoff packet."""
        try:
            handoff_packet = json.loads(handoff_json)
            delegations = [json.loads(delegation_json)] if delegation_json else None
        except json.JSONDecodeError as error:
            return json.dumps({"valid": False, "errors": [f"invalid JSON: {error}"]})
        errors = validate_specialist_return(
            handoff_packet, guard, ledger, delegations=delegations
        )
        return json.dumps({"valid": not errors, "errors": errors}, sort_keys=True)

    def verify_audit_ledger() -> str:
        """Verify the hash chain of this server's audit ledger."""
        violations = ledger.verify()
        return json.dumps(
            {"intact": not violations, "violations": violations}, sort_keys=True
        )

    def list_registered_roster() -> str:
        """List the native agent roster with brains and descriptions."""
        return json.dumps(
            {name: {"brain": meta["brain"], "description": meta["description"]}
             for name, meta in roster.items()},
            sort_keys=True,
        )

    return {
        "validate_packet": validate_packet,
        "admit_delegation_packet": admit_delegation_packet,
        "validate_handoff_return": validate_handoff_return,
        "verify_audit_ledger": verify_audit_ledger,
        "list_registered_roster": list_registered_roster,
    }


if MCP_AVAILABLE:

    def build_server(
        root: Path = ROOT, ledger_path: Path = DEFAULT_LEDGER
    ) -> "FastMCP":
        """Build the governance MCP server; construction is offline."""
        guard = PacketGuard(root)
        roster = load_roster(root)
        ledger = AuditLedger(ledger_path)
        server = FastMCP("agent007-governance")
        for tool in _tool_functions(guard, roster, ledger).values():
            server.tool()(tool)
        return server


if __name__ == "__main__":  # pragma: no cover
    build_server().run()
