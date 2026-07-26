# Framework Absorption Plan — 2026-07-24

## Decision and boundary

This is a reversible implementation plan for the nine frameworks supplied by Joe. It absorbs their **interfaces and control patterns**, not their agents, prompts, data, credentials, daemon processes, or vendor claims. No orchestration, memory, retrieval, scheduler, or LLM framework is installed or invoked by this repository through this change. The sole executable adoption is the `jsonschema` structural-validation dependency described below; `PacketGuard` still owns all Agent 007 relational and governance checks.

The existing contracts remain authoritative: Agent 007 is the sole cross-brain coordinator, specialists are brain-locked and packet-only, all canonical mutations require a writer lease and readback, and high-impact actions require explicit task-level instruction. A framework adapter cannot expand an agent's scope, create a connector, merge memories, or bypass a gate.

## Primary references for implementation verification

Verify the exact installed version against these primary references before implementing a framework API:

- [Microsoft AutoGen](https://microsoft.github.io/autogen/stable/) — multi-agent messaging and team orchestration.
- [LangGraph](https://langchain-ai.github.io/langgraph/) — state graphs, conditional routing, and persistence/checkpoints.
- [crewAI](https://docs.crewai.com/) — role-scoped agents, tasks, and sequential or hierarchical crews.
- [Prefect](https://docs.prefect.io/) — flows, tasks, deployments, schedules, retries, and artifacts.
- [Mem0](https://docs.mem0.ai/) — scoped memory storage and retrieval.
- [LlamaIndex](https://docs.llamaindex.ai/) — data ingestion, indexes, and query engines.
- [LangChain](https://python.langchain.com/docs/introduction/) — tools and structured output integration.
- [jsonschema](https://python-jsonschema.readthedocs.io/) — draft-aware JSON Schema validation.
- [Pydantic](https://docs.pydantic.dev/latest/) — typed Python models and runtime parsing.

Framework APIs evolve independently. Any implementation must verify the exact installed version against its primary documentation before using an API name from this plan.

## Absorption matrix

| Source pattern | Agent 007 mapping | Adoption state | Guardrail before implementation |
| --- | --- | --- | --- |
| AutoGen conversational agents and manager-selected turns | A same-brain mission session: Agent 007 selects the bounded participants; only same-brain challenge pairs may exchange evidence; Agent 007 reduces the final typed handoffs. Cadence order is a default order, not permission for cross-brain discussion. | Candidate runtime adapter | Validate every inbound and outbound packet; terminate only after required artifacts and criteria validate. |
| LangGraph `StateGraph`, conditional edges, checkpoints | Lifecycle and cadence state machine. `shadow → active` is a guarded edge, and high-impact execution is a paused approval node. | Candidate runtime adapter | Persist only sanitized packet IDs, state, and evidence references; resume only after revalidation and an unexpired lease. |
| crewAI roles, tasks, and crew process | TOML role/purpose/modes/artifact types map to a role adapter and task expected outputs. APEX and JEOS are separate crews; integration is never delegated across crews. | Candidate mapping only | Disable unrestricted delegation; manifest routing and PacketGuard remain the authority. |
| Prefect flows, tasks, retries, schedules, artifacts | A brain-local cadence can become one flow with specialist steps and a final Agent 007 reduction. The manifest remains the source of cadence order. | Candidate scheduler | No `serve()` or schedule until a verified runtime, timezone, concurrency policy, audit store, and failure/approval behavior are approved. |
| Mem0 user/agent/run memory scopes | A future provider adapter may use `user_id` only for approved cross-brain governance constraints; agent/run records stay in their owner-brain namespace. | Candidate memory adapter | Enforce writer leases before writes and prevent search/write calls across brain boundaries. |
| LlamaIndex vector indexes and query engines | Separate APEX evidence/playbook index and JEOS reflection index, queried through their brain proxy rather than direct specialist connectors. | Candidate retrieval adapter | Keep raw source content out of Git and prove index, source, and query isolation first. |
| LangChain memory, tools, structured output | Rolling session summaries and reusable tool wrappers are optional implementation details; JSON Schema remains the interchange contract. | Candidate utility adapter | Do not treat conversation memory as canonical memory; tools are allowlisted, scoped, and independently authorized. |
| `jsonschema` Draft 2020-12 validation | Structural validation at every packet boundary, collecting all violations before PacketGuard's relational checks. | **Adopted now** | CI installs the pinned major range and tests both structural and relational failures. |
| Pydantic `BaseModel` / `model_validate()` | Python ergonomic model layer that mirrors—not replaces—the published JSON Schemas. | Deferred companion | Generate or hand-write models only after a runtime module exists; contract parity tests must pass. |

## Runtime-neutral mission state machine

A future adapter must represent these states without changing the manifest lifecycle: `created → scope_validated → routed → delegated → handoff_validated → integrated → completed`. It may enter `boundary_blocked`, `failed`, or `awaiting_approval` from any applicable nonterminal state. Only Agent 007 can route a cross-brain constraint or integrate a completed mission.

Required transition guards:

1. **Scope validation:** owner brain, registered agent/mode/artifact type, allowed evidence, and writer-lease fields pass `PacketGuard` before a specialist receives anything.
2. **Challenge turn:** only participants in the same owner brain and registered challenge pairing can receive the other specialist's sanitized evidence references. The challenger returns a normal typed handoff; it never writes or selects the next brain.
3. **Completion:** every delegated required artifact and every definition-of-done criterion validates. A missing artifact is a failure, not a manager decision.
4. **Mutation:** the runtime stops before execution unless the allowed operation, active writer lease, idempotency key, expected version, readback, and rollback all validate. A `mutation_result` is required before reporting completion.
5. **High impact:** irreversible deletion, financial transactions, access changes, signatures/certifications, legal commitments, and public publication transition to `awaiting_approval`; only explicit task-level instruction may resume the exact action.
6. **Resume/checkpoint:** recheck schema validity, brain ownership, lease expiry, approval scope, and connector isolation. A checkpoint is evidence of suspension, not approval or completion.

## Delivery sequence

1. **Complete (this change):** validate the eight published schemas with `Draft202012Validator.check_schema()` at startup and collect all structural errors with `iter_errors()` before relational validation. CI installs `requirements.txt` so the same validator runs locally and in GitHub Actions.
2. **First controlled runtime trial:** implement a small, local, same-brain cadence adapter with no direct connectors, no persistence of source content, no scheduler, and no mutation. Feed synthetic v2.1 packets through the state machine and prove every negative guard above.
3. **Lifecycle trial:** add a LangGraph-compatible guarded lifecycle adapter only after the first trial; keep lifecycle evidence in versioned, sanitized records and require the current active gate unchanged.
4. **Memory/retrieval trial:** test one brain-scoped provider at a time using synthetic data, search isolation probes, retention/deletion behavior, and writer-lease enforcement. No shared user-level private fact store is enabled by default.
5. **Scheduling trial:** add one manual-first Prefect-compatible cadence with explicit UTC timezone, `queue`/`skip` concurrency policy, retry limits, and artifact retention. Promote it to a schedule only after its controlled trial is accepted.
6. **Typed runtime ergonomics:** add Pydantic models generated from or parity-tested against the JSON Schemas. A model must never silently accept a packet rejected by `PacketGuard`.

## Acceptance evidence and rollback

A framework moves from candidate to a controlled trial only with a registry entry, a bounded ticket, a version-pinned dependency, a threat/privacy review, synthetic success and failure fixtures, and tests proving no cross-brain leak, direct connector access, unauthorized write, auto-approval, or false completion. The deployment remains `shadow` until the existing material-mode, real-mission, isolation, readback, and lifecycle-promotion gates are met.

Rollback this change by removing `requirements.txt`, the CI dependency-install step, and the `jsonschema` calls in `scripts/packet_guard.py`; restore the prior commit if a framework trial is later added. Removing this plan does not change existing TOML manifests, lifecycle status, or any source records.
