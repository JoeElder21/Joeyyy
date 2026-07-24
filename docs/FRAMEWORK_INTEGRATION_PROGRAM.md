# Framework Integration Program — 2026-07-24

This is the implementation and deployment record for the nine repositories named in Joe's request. The request says “eight,” but enumerates **nine** distinct upstream projects; this record preserves all nine rather than silently omitting Pydantic. They are integration candidates, not vendored repositories and not claims that their cloud services, schedules, or Google Drive connectors are available.

## Current completion state (review-first, no duplicate work)

- Completed already: candidate identification and scoring (`docs/ECOSYSTEM_REPO_ANALYSIS.md`), Civil 3D workstation build gate (`docs/CIVIL3D_MCP_BUILDOUT.md`), execution-layer trial package and fixed task set (`docs/EXECUTION_LAYER_TRIAL.md`, `trial/`), and registry tracking (`docs/AGENT_REGISTRY.md`).
- Not completed yet: actual workstation Civil 3D build evidence, execution-layer winner evidence, and memory-layer reopen decision evidence.
- New immediate addition: trusted launcher runtime (`runtime/trusted_launcher.py`) enforcing signed one-time grants, constrained tool catalog operations, and replay denial.

## Guardrails that apply to every adapter

- APEX and JEOS run separate processes, stores, indexes, crews, graphs, and conversation transcripts. Only Agent 007 may compare minimized outputs.
- A specialist receives only a schema-valid delegation packet and returns a schema-valid handoff packet. PacketGuard validates before dispatch and before integration.
- Specialist direct connector access is prohibited. Memory and index writes require an Agent 007-issued writer lease, readback, and rollback evidence.
- A deployment must provide its own verified credentials and destination; this public repository contains neither private source content nor Google Drive identifiers.
- High-impact actions become a paused approval checkpoint; no framework may turn a pause into an authorization.

## Program order and phase gates

1. Finish in-flight candidates first (Civil 3D build Friday, execution trial Monday).
2. Phase 1: one tool at a time, each proving an existing contract boundary before activation.
3. Phase 2: proceed only after the memory-layer decision is formally reopened.
4. Phase 3: cover execution gaps the phase-1 winner does not cover; Unstructured intake may start early if still same-boundary.
5. Phases 4–5: capability absorption and APEX expansion after phases 1–3 evidence is recorded.

This program installs nothing and grants no access by itself. Every adopted item must carry its own rollback record at intake, and conflicts remain explicit until Joe resolves them.

## Active integration sequence

| Order | Upstream | Operational responsibility | Repository implementation / deployment gate |
| --- | --- | --- | --- |
| 1 | microsoft/autogen | Brain-private multi-agent discussion | `runtime/autogen_groupchat.py` creates a `ConversableAgent`/`GroupChat` plan from the canonical roster; it rejects mixed-brain participants. Attach only packet handlers and validate every return. This legacy API requires a Python runtime supported by the selected `pyautogen` release. |
| 2 | langchain-ai/langgraph | Lifecycle and cadence state machines | Model the lifecycle and cadence routes as graph state; edge guards must require every active-gate evidence item. Pause at an approval node for high-impact work. |
| 3 | crewAIInc/crewAI | Role/task composition | Generate each Crew agent from the native TOML role/purpose/modes and bind expected output to its declared artifact type. Run mirrored APEX and JEOS crews independently. |
| 4 | PrefectHQ/prefect | Retried, observable cadence flows | Wrap one delegated specialist call per task and a same-brain cadence per flow. Deployment may schedule only after a runtime destination and failure/rollback route are verified. |
| 5 | mem0ai/mem0 | Scoped fact/context memory | Use `user_id="joe"` only for explicitly authorized cross-brain preferences; use a distinct `agent_id` per manifest namespace and a run ID per mission. Enforce writer leases before `add`. |
| 6 | run-llama/llama_index | Brain-private retrieval | Maintain separate APEX and JEOS `VectorStoreIndex` instances. The intelligence/reflection agents query indexes through a packet-scoped tool only. |
| 7 | langchain-ai/langchain | Tools, loaders, summaries, structured returns | Share packet-scoped tool wrappers, use rolling summaries only inside a brain, and parse every output against the existing contracts. Do not enable a Drive loader until a verified, authorized connector is present. |
| 8 | python-jsonschema/jsonschema | Canonical JSON Schema validation | Add Draft 2020-12 validation to `PacketGuard` at every packet boundary and report all errors with `iter_errors`. |
| 9 | pydantic/pydantic | Python packet models | Introduce packet models beside schemas for typed runtime calls; retain JSON Schema as the cross-language source of contract truth. |

## AutoGen first mission path

1. Agent 007 determines one owner brain and selects the smallest needed same-brain specialist set.
2. `plan_group_chat()` reads `config/specialist_corps.toml`, preserves roster/cadence ordering, and rejects cross-brain or unknown participants.
3. A verified deployment calls `build_group_chat()` with its own LLM configuration, attaches packet-only execution handlers, and starts the chat from Agent 007 using `initiate_chat()`.
4. Each response is validated as `handoff_packet.schema.json`; invalid output is returned for correction or the mission is blocked.
5. Agent 007 creates the only permitted cross-brain comparison from minimized, valid outputs. Any proposed write follows the existing lease/readback/rollback protocol.

## Trusted launcher gate (before any dynamic bridge or autorunner activation)

Use `runtime/trusted_launcher.py` as the only launcher for external runtime actions tied to this program:

- Deny by default without a valid grant (`prove_denial` path).
- Require a user-signed one-time grant per launch with expiry and replay prevention.
- Restrict execution to allowlisted tool+operation pairs.
- Consume grant IDs once, even on dry runs, to prove single-use behavior.
- Run manual dynamic-C# validation only on a separately approved synthetic disposable DWG.

## Google Drive publication record

No Google Drive connector or destination folder is verified in this session, so no external Drive write was attempted and none is claimed. When an authorized connector is available, publish this document and the deployment evidence as a **Google Drive change record** containing: commit SHA, document title, deployment environment, enabled adapters/versions, owner brain, validation output, writer lease/readback/rollback evidence, and Drive URL. Never publish raw APEX/JEOS source records, credentials, connector IDs, or cross-brain transcripts.

## Rollback

Each adapter is opt-in through the deployment environment. Disable its deployment, retain packet evidence, revoke any active writer leases, and roll back this repository to the preceding commit if the adapter violates a boundary or cannot provide schema-valid readback. The static repository configuration remains the authority until a controlled real mission completes the active gate.
