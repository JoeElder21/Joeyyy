# Native Runtime Layers — Anthropic SDK, MCP, Pydantic, LangChain

Runtime record, 2026-07-24. Continues the build-out from `docs/AGENT_RUNTIME_BRIDGE.md`: four foundation layers incorporated per Joe's directive, all pinned already in the `requirements/` tiers from the runtime build-out. Three are implemented; one is absorbed with an activation plan.

## Layer 1 — anthropic-sdk-python: Claude-native governed dispatch (implemented)

`scripts/claude_runtime.py`. Claude is this system's native runtime; governed dispatch now speaks it directly:

- `governed_tool_definitions()` — typed Anthropic `tools` entries for `delegate_to_specialist` (enum-locked to the ten registered specialists; the packet travels as canonical JSON), `validate_handoff_return`, and `verify_audit_ledger`.
- `handle_tool_use()` — parses a `ToolUseBlock` and runs the same fail-closed core as the OpenAI bridge: an inadmissible packet returns `is_error` and control never transfers. Duck-typed, so it is stdlib-testable and SDK-version-tolerant.
- `stream_mission()` — thin wrapper over `client.messages.stream()` so long missions (a full weekly APEX review) stream progress instead of timing out. Network path; nothing invokes it implicitly and no key is stored.

Consequence: the 6→1 dispatch-overhead reduction measured in `docs/AGENT_RUNTIME_BRIDGE.md` now covers **both** runtimes — Claude-native and OpenAI-SDK — instead of one. Governed-dispatch automation coverage: 2 of 2 runtimes.

## Layer 2 — modelcontextprotocol/python-sdk: connector isolation, enforceable (implemented)

`scripts/governance_mcp_server.py`. Every specialist carries `connector_policy = "packet_only_no_direct_connectors"`; this server is what that policy connects to:

- A FastMCP server exposing exactly five governed tools: `validate_packet`, `admit_delegation_packet` (fail-closed), `validate_handoff_return`, `verify_audit_ledger`, `list_registered_roster`. Nothing else.
- The `hard_connector_isolation_required_for_active` rule becomes checkable: an active-stage specialist's tool surface is the MCP servers Agent 007 mounts — this one plus per-system servers (civil3d-mcp for the workstation leg, APS for the cloud leg, reference servers for filesystem/GitHub per the integration roadmap) — never arbitrary direct calls.
- Runs on stdio (`python scripts/governance_mcp_server.py`); building it is offline.

## Layer 3 — pydantic: typed packets without drift (implemented)

`scripts/packet_models.py`. The JSON schemas stay the single source of truth — every model (`DelegationPacket`, `HandoffPacket`, `WriterLease`, `MutationResult`, `RoundtableMemo`, `MemoryRecord`, both constraint packets) is **generated from its schema at import time**, never hand-written, so models cannot drift from contracts. Division of labor: pydantic enforces shape (presence, base types, `extra="forbid"`) with IDE typing; PacketGuard remains the authority on relational rules; `validate_with_guard()` runs both. Agent function signatures can now be typed (`def mission(packet: DelegationPacket) -> ...`) with the contract enforced by Python, not just documentation.

Note against the intake brief: `datamodel-codegen` was not adopted — generated-file codegen would create a second artifact to keep in sync; import-time generation from the canonical schemas achieves the typing with zero drift surface.

## Layer 4 — langchain-ai/langchain: absorbed, activation-gated (not yet implemented)

LangChain's value here — `ConversationSummaryMemory` (rolling compressed per-specialist memory) and summary-based context management — requires live LLM calls to summarize, so implementation waits for runtime activation (credentials + first shadow missions). What is adopted now, recorded in `docs/ABSORBED_PATTERNS.md`:

- Rolling summary memory as the per-specialist session-memory pattern, feeding the Phase 2 memory decision's acceptance criteria.
- Structured-output-parsing discipline is already covered natively: the packet schemas plus `handle_tool_use`/guardrails enforce typed artifacts at the transfer point, which supersedes `StructuredOutputParser` for dispatch. Document loaders (PDF/Word/Drive) route through the Unstructured intake decision in the integration roadmap rather than a second loader stack — one document-intake system, not two.

## Validation

- Stdlib (CI): full suite green with pydantic/MCP/SDK tests skipping by design.
- Isolated venv (`anthropic==0.119.0`, `mcp` 1.28-line, `pydantic` 2.13, `openai-agents==0.18.3`): all native-runtime and bridge tests pass, including fail-closed admission through the Anthropic tool handler and the MCP server's tool functions.

## Boundaries and rollback

No credentials are stored or read by any of these layers; live calls (`stream_mission`, a mounted MCP client session, LangChain memory) activate only on Joe's instruction under the shadow-stage gates. Rollback: delete `scripts/claude_runtime.py`, `scripts/governance_mcp_server.py`, `scripts/packet_models.py`, `tests/test_native_runtime.py`, and this document; audit ledgers created under `audit/` may be deleted or retained as records.
