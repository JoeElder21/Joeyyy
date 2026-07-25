"""Claude-native governed dispatch: Anthropic SDK tool use over the packet contracts.

Incorporates anthropic-sdk-python (pinned in requirements/runtime-contracts.txt)
as the Claude-native runtime for governed delegation. The same fail-closed core
that powers the OpenAI Agents bridge (scripts/agent_runtime.py) is exposed here
as typed Anthropic `tools` definitions plus a ToolUseBlock handler, so a
Claude-driven Agent 007 dispatches specialists through native tool use —
typed packets, never freeform instruction text.

Everything in this module is offline: building tool definitions and handling
tool-use blocks needs no API key. Only `stream_mission()` performs a network
call, and nothing here invokes it implicitly.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

from scripts.agent_runtime import (
    AuditLedger,
    HandoffRejected,
    admit_delegation,
    load_roster,
    validate_specialist_return,
)
from scripts.packet_guard import PacketGuard

DELEGATE_TOOL = "delegate_to_specialist"
RETURN_TOOL = "validate_handoff_return"
AUDIT_TOOL = "verify_audit_ledger"


def governed_tool_definitions(roster: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Anthropic `tools` parameter entries for governed dispatch.

    The packet travels as canonical JSON text; the JSON schemas in schemas/
    stay the single source of truth for its structure.
    """
    specialists = sorted(name for name, meta in roster.items() if meta["brain"] != "cross-brain")
    return [
        {
            "name": DELEGATE_TOOL,
            "description": (
                "Transfer control to a registered specialist with a schema-valid "
                "v2.1 delegation packet. Admission is fail-closed: an invalid, "
                "legacy, misaddressed, or brain-crossing packet is rejected "
                "before any transfer."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "enum": specialists},
                    "packet_json": {
                        "type": "string",
                        "description": "The delegation packet as canonical JSON text.",
                    },
                },
                "required": ["target", "packet_json"],
            },
        },
        {
            "name": RETURN_TOOL,
            "description": (
                "Validate a specialist's returned handoff packet against the "
                "handoff contract, including evidence rules."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "handoff_json": {"type": "string"},
                    "delegation_json": {
                        "type": "string",
                        "description": "The originating delegation packet as JSON, when known.",
                    },
                },
                "required": ["handoff_json"],
            },
        },
        {
            "name": AUDIT_TOOL,
            "description": "Verify the hash-chained audit ledger and report any violations.",
            "input_schema": {"type": "object", "properties": {}},
        },
    ]


def handle_tool_use(
    block: Any,
    roster: dict[str, dict[str, Any]],
    guard: PacketGuard,
    ledger: AuditLedger | None = None,
    *,
    leases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Handle one ToolUseBlock from a Claude response; returns a tool_result.

    Accepts any object with `.type`, `.id`, `.name`, and `.input` (the shape
    of `anthropic.types.ToolUseBlock`), so tests run without the SDK.
    Failures return `is_error: True` — the model sees the rejection reason,
    but control never transfers on an inadmissible packet.
    """
    if getattr(block, "type", None) != "tool_use":
        raise ValueError("handle_tool_use expects a tool_use block")

    def result(content: Any, is_error: bool = False) -> dict[str, Any]:
        return {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": json.dumps(content, sort_keys=True),
            "is_error": is_error,
        }

    try:
        if block.name == DELEGATE_TOOL:
            packet = json.loads(block.input["packet_json"])
            admit_delegation(
                packet, block.input["target"], roster, guard, ledger, leases=leases
            )
            return result(
                {"admitted": True, "target": block.input["target"],
                 "delegation_id": packet.get("delegation_id")}
            )
        if block.name == RETURN_TOOL:
            handoff_packet = json.loads(block.input["handoff_json"])
            delegations = None
            if block.input.get("delegation_json"):
                delegations = [json.loads(block.input["delegation_json"])]
            errors = validate_specialist_return(
                handoff_packet, guard, ledger, delegations=delegations, leases=leases
            )
            return result({"valid": not errors, "errors": errors}, is_error=bool(errors))
        if block.name == AUDIT_TOOL:
            violations = ledger.verify() if ledger is not None else []
            return result({"intact": not violations, "violations": violations},
                          is_error=bool(violations))
    except HandoffRejected as rejection:
        return result({"admitted": False, "errors": rejection.errors}, is_error=True)
    except (KeyError, json.JSONDecodeError) as error:
        return result({"errors": [f"malformed tool input: {error}"]}, is_error=True)

    return result({"errors": [f"unknown tool {block.name!r}"]}, is_error=True)


def stream_mission(client: Any, **request: Any) -> Iterator[str]:
    """Stream a long-running mission's text instead of waiting on one response.

    Thin wrapper over `client.messages.stream()` (Anthropic SDK) so weekly
    reviews and other long missions surface progress incrementally rather
    than timing out. Network path — requires a configured client; never
    called by anything else in this module.
    """
    with client.messages.stream(**request) as stream:
        yield from stream.text_stream


def governed_request(
    roster: dict[str, dict[str, Any]] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """Assemble the standard governed-dispatch request kwargs for Claude.

    Returns the tools-bearing request skeleton; the caller supplies model,
    max_tokens, and messages (or overrides anything here).
    """
    roster = roster or load_roster()
    request: dict[str, Any] = {"tools": governed_tool_definitions(roster)}
    request.update(overrides)
    return request
