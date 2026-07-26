# Agent Framework Integration Record — July twenty-fourth, twenty-twenty-six

This is the implementation and Drive-ready change record for the framework intake requested by Joe. The request names **nine** upstream repositories (not eight); this record covers all nine. The repository is public: it contains contracts, adapters, and tests only—not Drive content, credentials, connector IDs, or personal/professional source records.

## Operating status

The local integration is active: `runtime/orchestration.py` compiles same-brain cadence plans and guarded lifecycle transitions; `runtime/contracts.py` validates packet boundaries; `scripts/packet_guard.py` uses the canonical `jsonschema` Draft 2020-12 validator before Agent 007's relational checks. These components execute in the repository test suite.

The upstream runtime services are **not installed, authenticated, or connected** by this change. Consequently, none is represented as a live agent, memory store, Google Drive connector, scheduler, or external execution authority. Agent 007 must verify the approved account, deployment, and connector at runtime before enabling any adapter. Specialists remain `shadow`, read-only, and packet-only.

## Integration map

| Upstream repository | Adopted operational contract | Controlled activation required |
| --- | --- | --- |
| `microsoft/autogen` | `GroupChatPlan` compiles each brain's `cadence_routes` order with Agent 007 as manager; same-brain participants are checked before a plan is returned. Challenge pairs are the approved two-agent debate topology. | Install the selected AutoGen package, bind a model client, and validate one controlled mission per material mode. |
| `langchain-ai/langgraph` | `lifecycle_transition_allowed()` implements guarded state-machine edges; `shadow → active` fails closed without complete gate evidence. | Add a persisted checkpointer only after an approved storage target and human approval checkpoint are verified. |
| `crewAIInc/crewAI` | Manifest role/purpose/modes/artifact types remain the authoritative Agent/Task source; each handoff requires its declared typed artifact. | Install CrewAI and bind one brain-scoped crew at a time; no cross-brain crew is permitted. |
| `PrefectHQ/prefect` | Cadence plans are deterministic task order and may be wrapped as retryable flows only after deployment; every run must retain a packet/audit artifact. | Approve scheduler account, timezone, deployment, retry policy, and idempotency key. |
| `mem0ai/mem0` | Manifest memory namespaces map to agent scopes; writer leases remain required before durable writes. | Verify a self-hosted or managed store, encryption/access controls, retention, and separate APEX/JEOS credentials. |
| `run-llama/llama_index` | APEX source-index/playbook and JEOS reflection retrieval remain separate logical indexes; retrieval must be limited to the packet's authorized evidence. | Approve document loaders and vector storage; do not ingest raw Drive data into Git. |
| `langchain-ai/langchain` | Typed packet boundaries are the structured-output contract; tool definitions must remain brain-scoped and least-privilege. | Install selected components only, bind loader/tool permissions, and test parser failures. |
| `python-jsonschema/jsonschema` | Installed as a required dependency. `Draft202012Validator.iter_errors()` collects all structural violations at every PacketGuard boundary. | No external service activation needed; CI installs and tests it. |
| `pydantic/pydantic` | Installed as a required dependency. `PacketModel` supplies strict (`extra=forbid`) typed transport-model defaults; JSON Schema remains the interoperable packet contract. | Add schema-specific models only alongside their full relational test fixtures; do not duplicate or weaken PacketGuard rules. |

## Microsoft AutoGen first implementation

`cadence_group_chat("APEX", "daily")` produces the ordered APEX speakers from `config/specialist_corps.toml`; the returned plan's manager is `apex_chief_of_staff`. It rejects invalid brain/cadence requests and rejects a plan whose participants fall outside its brain roster. A future AutoGen adapter must call `initiate_chat()` only with this validated plan and validate every outgoing delegation and incoming handoff through `runtime.contracts.validate_packet()`.

Agent 007, not `GroupChatManager`, remains the only cross-brain integrator. An AutoGen manager may choose the next speaker only from the already-authorized same-brain plan and cannot grant tools, evidence, memory, or write access.

## Google Drive documentation handoff

No Google Drive connector is verified in this session, so this change does **not** claim to have written to Drive. Upload this public-safe file to the Agent 007 governance folder as `Framework Integration Record — July twenty-fourth, twenty-twenty-six`, then record the Drive document URL and revision in the runtime-only governance log. Do not add the URL, Drive IDs, or private content to this public repository. The receiving owner must read back the uploaded document and retain the prior revision as the rollback point.

## Rollback

Revert this integration commit to remove the local runtime plan, dependency declarations, CI dependency installation, and this record. This change creates no external deployment, schedule, memory, index, or Drive mutation to roll back.
