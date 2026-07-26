# Framework Integration Program — 2026-07-24

This is the bounded integration record for the nine repositories named in Joe's
mission. It begins with `microsoft/autogen`. The request mentions both 12 and 9
repositories but supplies nine unique repository identifiers; this program
implements those nine and preserves the remaining three as an unresolved intake
item rather than inventing repository identities.

## Current state and safety boundary

All nine integrations are **configured, not runtime-validated**. Their public,
machine-checked contracts are in `config/framework_integrations.toml`; the
validator intentionally reports `0 runtime-validated`. This repository cannot
truthfully mark a package, hosted service, scheduler, memory store, Google Drive
connector, or live specialist as active unless it is installed, configured, and
passes the listed gate in the target runtime.

The ten specialists therefore remain in their existing `shadow` lifecycle
stage. The integration program does not relax PacketGuard, one-writer leases,
brain separation, or the explicit approval boundary. Private APEX and JEOS
source material remains external to this public repository.

## Microsoft AutoGen first

`agent_runtime/autogen_orchestrator.py` supplies the safe local control plane
for a future AutoGen `ConversableAgent`/group-chat adapter:

1. It reads the canonical specialist manifest, rather than duplicating roles.
2. It constructs an eligible speaker list only from the requested owner brain
   and registered mode.
3. It prefers the configured cadence sequence when selecting a next speaker.
4. It fails closed when a mode has no same-brain participant or every eligible
   participant already spoke; Agent 007 must then integrate or close the chat.
5. An external adapter must still validate each handoff with PacketGuard and may
   only use Agent 007 as the cross-brain integrator.

The synthetic test proves the APEX strategy participant is selectable for
`operating_campaign`, while JEOS is not. It does not invoke AutoGen or a named
specialist and is not real-mission evidence.

## Integration matrix

| Repository | Contracted capability | Canonical control point | Runtime validation before use |
| --- | --- | --- | --- |
| `microsoft/autogen` | Dynamic same-brain group-chat selection | `agent_runtime/autogen_orchestrator.py` | Synthetic debate with PacketGuard handoffs and opposite-brain selection rejection. |
| `langchain-ai/langgraph` | Lifecycle/cadence state graph and approval pause | lifecycle gates in `config/specialist_corps.toml` | Shadow-to-active rejection and high-impact pause tests. |
| `crewAIInc/crewAI` | Roster-to-role/task crew mapping | specialist TOMLs and registered artifact types | Same-brain crew emits each required typed artifact. |
| `PrefectHQ/prefect` | Retriable, idempotent cadence jobs | `cadence_routes` and trial tickets | Synthetic retry flow with safe artifact metadata. |
| `mem0ai/mem0` | Scoped user/agent/run memory | manifest memory namespaces and leases | Synthetic scoped retrieval and leased writes only. |
| `run-llama/llama_index` | Separate APEX/JEOS retrieval indexes | brain namespaces and privacy policy | Synthetic index isolation proof. |
| `langchain-ai/langchain` | Structured outputs and shared tool interface | schemas and brain-scoped proxy | Synthetic schema parsing and proxy-only tool proof. |
| `python-jsonschema/jsonschema` | Standards-compliant schema error collection | `schemas/` and PacketGuard baseline | Draft validation cross-check on valid/invalid fixtures. |
| `pydantic/pydantic` | Typed Python packet models | v2.1 JSON schemas and PacketGuard | Model validation cross-check on synthetic v2.1 packets. |

## Google Drive change record

No Google Drive connector, account, folder, or document target was verified in
this runtime. No Drive write was attempted, and no private Drive content was
copied here. Once an authorized connector is available, Agent 007 should create
or update a **sanitized** `Framework Integration Program` change record using
only this document, the integration TOML, the commit hash, validation output,
and rollback instructions. It must not include Drive IDs, credentials, raw
APEX/JEOS documents, or runtime memory.

Required readback before reporting that future write complete: verify the
document title, destination account/folder, revision timestamp, sanitized body,
and the rollback method. Create matching evidence separately in the APEX and
JEOS owner memories without copying either brain's source data across the
boundary.

## Activation order

1. Install and pin only the selected package in an approved runtime; record the
   version outside this public repository if it reveals internal environment
   details.
2. Complete the named synthetic validation gate with no private source data.
3. Add evidence, a rollback point, and an integration-specific test.
4. Run one controlled real mission per material mode where applicable.
5. Only then change the integration status to runtime-validated. Specialist
   lifecycle promotions remain governed independently by their existing active
   gate.

## Rollback

The implementation is additive and has no external state. Revert the commit
that introduces `config/framework_integrations.toml`, `agent_runtime/`, this
document, and their tests. For a later runtime activation, use the per-entry
rollback instruction in the TOML, then read back the disabled state and record
the result in the appropriate owner memory.
