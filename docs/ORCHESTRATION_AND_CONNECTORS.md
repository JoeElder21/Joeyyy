# Orchestration and Connectors — AutoGen, LangGraph, MCP Servers, APS, Logseq

Runtime record, 2026-07-24. Fourth build-out wave per Joe's directive.

## LangGraph — the governance state machines, executable (`scripts/orchestration_graphs.py`)

- **Lifecycle**: candidate → shadow → active → value-proven (restricted/deprecated/retired exits) as a StateGraph whose edge guards are the acceptance gates. A shadow specialist advances to active only when all six gate conditions (`static_contracts_valid`, `typed_v21_output_proven`, `controlled_mission_per_material_mode`, `connector_isolation_verified`, `writer_lease_compliance`, `readback_on_mutation`) are recorded true; a violation routes to restricted. Proven in tests.
- **Cadence runs**: built from the brain manifests' real `[[cadence_routes]]` — the daily APEX run executes intelligence_forge → delivery_commander → deal_engine with chief_of_staff as the terminal reduction node. The step executor is injected (live LLM execution is an activation-time injection).
- **Human-in-the-loop**: the mission graph interrupts before `execute_irreversible` and resumes only when the run is explicitly continued with Joe's approval recorded — the explicit-task-level-instruction boundary, executable and tested (pause + resume proven).

## AutoGen — debates and dynamic routing, actually running (`scripts/group_debate.py`)

- **Challenge pairs debate for real**: `build_challenge_debate()` accepts only manifest-registered pairs (unregistered or cross-brain pairs are refused) and wires them as conversing agents. A war_architect vs intelligence_forge debate **ran end-to-end in tests** via AutoGen's replay model client — fully offline, both agents spoke.
- **Cadence chats**: manifest order = speaking order, integrator last, in a round-robin group chat.
- **Dynamic manager**: `build_selector_chat()` gives a brain's specialists + 007 the who-speaks-next selector — the runtime version of the static TOML routes. Live model clients are activation-time injections.

## MCP reference servers — mounted under the connector policy (`config/mcp_mounts.toml`)

The approved-mounts registry is the executable form of `packet_only_no_direct_connectors`: a specialist's tool surface is exactly its listed mounts. `scripts/verify_mcp_mounts.py` probes offline-verifiable mounts through a real MCP ClientSession:

- **governance** — verified live: five governed tools served over stdio.
- **filesystem** (reference server) — verified live: full tool set over stdio, path-scoped.
- **github / postgres / gdrive** — registered with explicit activation requirements (token / connection string / one-time OAuth on Joe's machine). The MCP→Google Drive path is already proven end-to-end at the session level (the Drive command-center documents were created and read back through an authorized Drive MCP connector); the reference gdrive server mount activates with Joe's OAuth.
- **civil3d** — registered; activates at the scheduled workstation build.

## APS SDK — credential-ready before the 1:00 session (`scripts/aps_credential_check.mjs`)

All four `@aps_sdk` packages (`autodesk-sdkmanager`, `authentication`, `data-management`, `model-derivative`) verified installable and importable today. The check script completes validation-gate steps 2–3 from `docs/APS_SDK_BUILDOUT.md` the moment `APS_CLIENT_ID`/`APS_CLIENT_SECRET` exist in the env store (read-only scope, lists sandbox hubs, stores nothing). Creating the APS app credentials is the only step that requires Joe.

## Logseq — the JEOS knowledge graph, operational (`scripts/jeos_knowledge.py`)

Because a Logseq graph is a directory of Markdown with `[[links]]` and `#tags`, this layer is fully operational offline and the desktop app opens the same directory. Governed: the four knowledge targets (Reflection-Ledger, Pattern-Hypotheses, Lessons-and-Rules → jeos_reflection_forge; Life-Architecture → jeos_life_architect) are designated-writer-only; reads are JEOS + 007 only (APEX agents are refused); daily journals append in Logseq's format; `query_by_tag("pattern-hypothesis", since_days=30)` and backlinks run over stored pages — retrieval, not recall. The Logseq HTTP API becomes an alternative transport at activation with the format unchanged.

## Validation

Stdlib: full suite green, heavy tests skip by design. Pinned venv (now + `autogen-agentchat 0.7.5`, `autogen-ext`, `langgraph`): all orchestration tests pass, including the live debate run, lifecycle gate enforcement, HITL pause/resume, and both MCP mount probes.

## Boundaries and rollback

No credentials stored or read; every live path (model clients, github/postgres/gdrive mounts, APS calls, Logseq HTTP) activates only on Joe's instruction. Rollback: delete `scripts/orchestration_graphs.py`, `scripts/group_debate.py`, `scripts/jeos_knowledge.py`, `scripts/verify_mcp_mounts.py`, `scripts/aps_credential_check.mjs`, `config/mcp_mounts.toml`, `tests/test_orchestration.py`, and this document.
