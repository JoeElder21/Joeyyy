# Agent 007 Registry

This is the canonical cross-brain index for agents governed by Agent 007. Brain-owned metadata lives in `brains/apex/agents.toml` and `brains/jeos/agents.toml`.

## Lifecycle

`candidate` → `shadow` → `active` → `value-proven` / `restricted` / `deprecated` / `retired`

Static and synthetic packet validation permit shadow operation. An agent becomes active only after every material mode has controlled real-mission evidence, verified boundary behavior, runtime connector isolation, handoff accuracy, writer-lease behavior, and readback where a mutation occurs. Value-proven additionally requires observed net benefit after review, correction, maintenance, and failure burden.

## Agent 007 / APEX Chief of Staff

- Status: active
- Canonical native name: `apex_chief_of_staff`
- Aliases: Agent 007, 007, Chief of Staff
- Owner layer: cross-brain governance
- Purpose: classify ownership, coordinate APEX and JEOS, govern the community, integrate results, execute authorized work, and improve the ecosystem
- Triggers: `Activate Agent 007`, explicit native invocation, cross-brain coordination, agent intake, ecosystem audit
- Inputs: Joe's mission, active conversation, verified APEX/JEOS memory, authorized connectors, agent files, specialist handoffs
- Outputs: integrated plan, delegated work, verified actions, brain sync, registry changes, error learning, audit report
- Tools/connectors/skills: only those verified in the active runtime; never assumed from configuration
- Write targets: cross-brain governance plus owner-routed domain targets; one active writer lease per canonical brain/target/resource
- Native sandbox: `workspace-write` — Agent 007 is the sole write-capable native agent and executes all mutations while specialists remain `read-only` (restored 2026-07-23 on Joe's instruction; the v2.1 hardening had left no configured writer)
- Boundaries: sole cross-brain agent; preserve brain ownership; no unsupported access claims; no silent conflict merging; platform and professional controls remain in force
- Handoff: `docs/AGENT_COMMUNITY_PROTOCOL.md` and `schemas/`
- Validation: `scripts/validate_specialist_corps.py`, `tests/test_agent_contract.py`, `tests/test_specialist_corps.py`, and `tests/test_local_validation.py`
- Version: 2.1
- Last audit: v2 mirrored-corps migration, 2026-07-23
- Known errors: no v2.1 named-specialist runtime evidence yet

## APEX specialist unit

All APEX specialists are brain-locked, read-only by default, and in shadow stage. They use only APEX evidence and communicate only inside APEX.

| Agent | ID | Mirrored class | Memory namespace | Primary proposed target | Status |
|---|---|---|---|---|---|
| `apex_war_architect` / APEX WAR ARCHITECT | APEX-15 | Strategy | `APEX::Strategy-Campaigns::apex_war_architect` | `APEX/Strategy-Campaigns` | shadow |
| `apex_deal_engine` / APEX DEAL ENGINE | APEX-16 | Opportunity / momentum | `APEX::Opportunity-Pipeline::apex_deal_engine` | `APEX/Opportunity-Pipeline` | shadow |
| `apex_delivery_commander` / APEX DELIVERY COMMANDER | APEX-17 | Execution / capacity | `APEX::Delivery-Control::apex_delivery_commander` | `APEX/Delivery-Control` | shadow |
| `apex_intelligence_forge` / APEX INTELLIGENCE FORGE | APEX-18 | Intelligence / reflection | `APEX::Intelligence-Decisions::apex_intelligence_forge` | `APEX/Intelligence-Decisions` | shadow |
| `apex_systems_blacksmith` / APEX SYSTEMS BLACKSMITH | APEX-19 | Systems / automation | `APEX::Systems-Registry::apex_systems_blacksmith` | `APEX/Systems-Registry` | shadow |

Brain-owned triggers, outputs, routes, and challenge pairs: `brains/apex/agents.toml`.

## JEOS specialist unit

All JEOS specialists are brain-locked, read-only by default, and in shadow stage. They use only JEOS evidence and communicate only inside JEOS.

| Agent | ID | Mirrored class | Memory namespace | Primary proposed target | Status |
|---|---|---|---|---|---|
| `jeos_life_architect` / JEOS LIFE ARCHITECT | JEOS-14 | Strategy | `JEOS::Life-Architecture::jeos_life_architect` | `JEOS/Life-Architecture` | shadow |
| `jeos_momentum_engine` / JEOS MOMENTUM ENGINE | JEOS-15 | Opportunity / momentum | `JEOS::Momentum-Queue::jeos_momentum_engine` | `JEOS/Momentum-Queue` | shadow |
| `jeos_energy_director` / JEOS ENERGY DIRECTOR | JEOS-16 | Execution / capacity | `JEOS::Energy-Capacity::jeos_energy_director` | `JEOS/Energy-Capacity` | shadow |
| `jeos_reflection_forge` / JEOS REFLECTION FORGE | JEOS-17 | Intelligence / reflection | `JEOS::Reflection-Ledger::jeos_reflection_forge` | `JEOS/Reflection-Ledger` | shadow |
| `jeos_lifestyle_systems_builder` / JEOS LIFESTYLE SYSTEMS BUILDER | JEOS-18 | Systems / automation | `JEOS::Lifestyle-Systems-Registry::jeos_lifestyle_systems_builder` | `JEOS/Lifestyle-Systems-Registry` | shadow |

Brain-owned triggers, outputs, routes, and challenge pairs: `brains/jeos/agents.toml`.

## Shared specialist contract

- Inputs: a schema-valid v2.1, brain-matched, single-mode delegation packet and only its allowed evidence; direct invocation is contained to `direct_read_only`
- Outputs: a schema-valid handoff with registered typed artifacts, stable criterion validation, evidence, assumptions, challenges, deterministic proposed writes, and next handoff
- Tools/connectors/skills: specialists receive no direct connector handles under this contract; Agent 007 or a runtime-enforced brain proxy supplies PacketGuard-validated evidence
- Write behavior: exact per-agent target arrays live in the manifests; proposed mutations only while shadow; Agent 007 holds the writer lease until a specialist is active or value-proven, its native sandbox is versioned away from read-only, and the exact target is allowlisted
- Communication: same-brain asks, challenges, and handoffs only; Agent 007 is the sole bridge
- Validation: `scripts/packet_guard.py` enforces relational packet rules and rejects legacy 2.0 delegation, handoff, and brain-private constraint packets unless explicitly validated as archived (`historical=True`); `scripts/validate_specialist_corps.py` validates synthetic contracts and boundary probes without invoking agents; `schemas/mutation_result.schema.json` proves readback and rollback
- Privacy: runtime private evidence is never committed to this public repository
- Version: 2.1.0
- Last audit: v2.1 static and synthetic contract hardening, 2026-07-23
- Known errors: no controlled real mission has run; named-agent behavior and runtime connector isolation remain unproven

## Retired callable roster and capability lineage

The v1 agents were shadow-stage definitions. Their native TOMLs are removed from `.codex/agents/` to prevent duplicate routing; Git history at `4465ee9dd728f9ab0a8a9d13791f1f65523a4b3c` is the rollback point.

| Retired agent | Replacement capability owner |
|---|---|
| `apex_grademaster` | `apex_delivery_commander` |
| `apex_countwise` | `apex_delivery_commander`, `apex_intelligence_forge` |
| `apex_signalkeeper` | `apex_intelligence_forge`, `apex_delivery_commander`, `apex_deal_engine` |
| `apex_ascent_90` | `apex_war_architect`, `apex_intelligence_forge` |
| `apex_forgewright` | `apex_systems_blacksmith` |
| APEX RAINMAKER bench concept | `apex_deal_engine` |
| `jeos_examiner` | `jeos_momentum_engine` |
| `jeos_tempo` | `jeos_energy_director` |
| `jeos_shepherd` | `jeos_reflection_forge` |
| `jeos_hearthkeeper` | `jeos_life_architect`, `jeos_momentum_engine` |
| `jeos_lifewright` | `jeos_lifestyle_systems_builder` |

See `docs/ROSTER_MIGRATION_2026-07-23.md` for the reversible migration record.

## Candidate infrastructure and tools

External tools under evaluation for the ecosystem. These are not agents; they are infrastructure that agents would use. None may be treated as available until validated in its target environment. Source analysis: `docs/ECOSYSTEM_REPO_ANALYSIS.md` (2026-07-23).

### Civil 3D MCP connector (barbosaihan/civil3d-mcp)

- Status: candidate
- Owner layer: APEX (Civil 3D workflow automation)
- Purpose: let Claude query and edit live Civil 3D drawings through MCP meta-tools (`civil3d_query`, `civil3d_execute`, `civil3d_skills`)
- Validation gate: build on the Civil 3D workstation per `docs/CIVIL3D_MCP_BUILDOUT.md`; read-only queries on copies of project DWGs must pass before any write use
- Boundaries: write operations follow the one-designated-writer rule; production DWGs require explicit task-level instruction
- Rollback: remove the MCP server entry from Claude config and unload the plugin (no persistent state)

### APS cloud connector (autodesk-platform-services/aps-sdk-node)

- Status: candidate
- Owner layer: APEX (cloud project-file and model-data access; the cloud leg of the Civil 3D / engineering MCP layer)
- Purpose: give APEX agents read access to BIM 360/ACC file trees (`data-management`) and element-level model properties/quantities (`model-derivative`) through the official APS Node.js SDK; headless cloud automation later via the Design Automation REST API (no SDK package exists for it — see the capability corrections in `docs/APS_SDK_BUILDOUT.md`)
- Validation gate: per `docs/APS_SDK_BUILDOUT.md` — sandbox-only, read-only scopes first; employer/client hub access requires explicit task-level authorization
- Boundaries: APS credentials live only in the runtime env/secret store, never in chat or this repository; any write scope follows the one-designated-writer rule
- Rollback: remove the connector configuration and revoke the APS app credentials (no persistent state in this repository)

### Agent runtime bridge (openai/openai-agents-python)

- Status: shadow (code and tests merged; live `Runner` execution not yet activated)
- Owner layer: Agent 007 governance — runtime enforcement of the delegation and handoff contracts
- Purpose: make handoffs executable and fail-closed — `scripts/agent_runtime.py` wires PacketGuard into the SDK's `handoff()` so an invalid, misaddressed, legacy, or brain-crossing packet cannot transfer control, with every admission, rejection, and return validation auto-logged to a hash-chained audit ledger
- Validation gate: 131-test suite green stdlib-side; 39/39 in the full-stack venv including live fail-closed `on_invoke_handoff` proofs; live-mission activation follows the shadow-stage acceptance gates and requires Joe's instruction plus runtime credentials
- Boundaries: no API keys stored or read; audit ledger carries packet metadata only; topology is 007 → specialists and specialists → 007 exclusively
- Rollback: delete `scripts/agent_runtime.py`, `tests/test_agent_runtime.py`, and `docs/AGENT_RUNTIME_BRIDGE.md`; no persistent state beyond user-created ledgers

### Native runtime layers (anthropic-sdk-python, mcp python-sdk, pydantic, langchain)

- Status: shadow (three layers implemented and tested offline; langchain absorbed, activation-gated)
- Owner layer: Agent 007 governance — Claude-native dispatch (`scripts/claude_runtime.py`), enforceable connector isolation (`scripts/governance_mcp_server.py`), typed packets generated from the canonical schemas (`scripts/packet_models.py`)
- Validation gate: full suite green stdlib-side with skips by design; all native-runtime tests pass in the pinned full-stack venv; live activation (streaming missions, mounted MCP clients, summary memory) requires Joe's instruction plus runtime credentials
- Boundaries: no credentials stored or read; specialists' tool surface under the connector policy is MCP servers only
- Rollback: per `docs/RUNTIME_NATIVE_LAYERS.md`

### Data and memory layers (llama_index, mem0, crewAI)

- Status: shadow (governance gateways implemented and tested offline; vector embeddings, mem0 backend, and crew kickoff activation-gated)
- Owner layer: Agent 007 governance — governed evidence indexes (`scripts/evidence_index.py`), leased memory gateway on the mem0 scope model (`scripts/memory_layer.py`), roster-to-crew bridge with fail-closed admission (`scripts/crew_bridge.py`)
- Validation gate: full suite green stdlib-side with skips by design; all layer tests pass in the pinned full-stack venv (leased writes, brain locks, writer locks, crew admission)
- Boundaries: no credentials stored or read; namespace writes require the owner agent plus a PacketGuard-valid active writer lease; cross-brain reads route through Agent 007 only
- Rollback: per `docs/DATA_MEMORY_LAYERS.md`

### Orchestration and connectors (autogen, langgraph, MCP reference servers, aps-sdk, logseq)

- Status: shadow (graphs, debates, knowledge graph, and two MCP mounts verified working offline; model clients, external mounts, and APS calls activation-gated)
- Owner layer: Agent 007 governance — executable lifecycle/cadence/HITL state machines (`scripts/orchestration_graphs.py`), manifest-registered debates and selector chats (`scripts/group_debate.py`), the approved-MCP-mounts registry (`config/mcp_mounts.toml`), APS credential-readiness (`scripts/aps_credential_check.mjs`), and the JEOS knowledge graph (`scripts/jeos_knowledge.py`)
- Validation gate: full suite green stdlib-side; all orchestration tests pass in the pinned venv including a live offline debate run, lifecycle gate enforcement, HITL pause/resume, and real MCP stdio probes of the governance and filesystem mounts
- Boundaries: no credentials stored or read; the JEOS graph is unreadable by APEX agents; mounts not listed are not reachable
- Rollback: per `docs/ORCHESTRATION_AND_CONNECTORS.md`

### Cadence scheduling and observability (prefect, opentelemetry/phoenix)

- Status: shadow (flows execute locally with audit logging; span capture and weekly-review aggregation proven offline; Prefect work-pool schedules and the Phoenix collector are activation steps)
- Owner layer: Agent 007 governance — manifest cadence routes as Prefect flows with cron deployment specs (`scripts/cadence_flows.py`); OpenTelemetry spans over admissions and returns with a weekly-review aggregator (`scripts/observability.py`)
- Boundaries: spans carry packet metadata only, never packet content or credentials
- Rollback: delete `scripts/cadence_flows.py`, `scripts/observability.py`, and `tests/test_cadence_observability.py`

### Trusted launcher (grant-gated mount activation)

- Status: shadow (all denial paths proven by tests; first live grant happens on Joe's workstation)
- Owner layer: Agent 007 governance — authority separated from execution: write-capable MCP mounts (`require_grant = true` in `config/mcp_mounts.toml`) start only through `scripts/trusted_launcher.py` with a Joe-signed, single-use, time-boxed grant; every authorization and denial lands in the hash-chained launcher ledger
- Validation gate: `tests/test_trusted_launcher.py` proves denial without a grant, for unregistered mounts, tampered signatures, expired grants, reused nonces, and wrong-mount grants; the civil3d first live use follows `docs/CIVIL3D_FIRST_WRITE_TEST.md`
- Boundaries: the signing key lives outside the repository (0600, Joe's machine); agents cannot mint grants
- Rollback: delete the launcher, its tests, and the grant flags; mounts revert to registered-not-launchable

### Execution layer (codex-autorunner OR multica — one, not both)

- Status: candidate, pending Joe's platform pick
- Owner layer: Agent 007 governance (task dispatch for repo-based agent work)
- Purpose: run queued agent work unattended with notify-when-stuck; see `docs/EXECUTION_LAYER_TRIAL.md`
- Validation gate: bounded trial on non-production tasks (registry maintenance, doc audits) before any client-facing work

### Integration roadmap, Phases 1–5 (15 external platforms)

- Status: candidate (identity and maturity verified 2026-07-24; adoption still requires full per-item intake). Exception: LangKit verified stale with an overstated PII claim — its Phase 1 slot is open pending a maintained substitute. Verification table: `docs/INTEGRATION_ROADMAP.md`
- Owner layer: Agent 007 governance; per-item target layers in `docs/INTEGRATION_ROADMAP.md`
- Purpose: add the runtime enforcement and automation (prompt optimization, schema enforcement, sandboxing, privacy monitoring, memory, scheduling, document intake, reasoning patterns, AEC data exchange) that makes the existing contracts real
- Validation gate: full intake per item before any adoption; recorded conflicts (memory-layer decision, execution-trial precedence) stay visible until Joe resolves them
- Rollback: the roadmap grants no access; each adopted item records its own rollback at intake

### Deferred / watch list

- kentcdodds/kody — cross-brain memory/secrets/scheduler layer; absorb-only for now, revisit next quarter
- citrolabs/ego-lite — permit-portal agent browser; blocked on Windows support, revisit on release
- max-sixty/worktrunk — install when multiple agents edit this repo concurrently
- ADN-DevTech/Civil3DSnoop — bookmark for future Civil 3D .NET development sessions

## Dream-team charter modes (2026-07-24)

Registered on Joe's direct instruction and refined the same day per his decision: dream-team roles are **modes of the existing ten-specialist corps**, not separate agents. Forty charter modes (37 APEX across six layers, 3 JEOS personal-command; Joe's JEOS roster message truncated after five names and the remainder registers on arrival) are chartered in `config/dream_team_roster.toml`, validated by `tests/test_dream_team.py`.

- The corps remains ten specialists plus Agent 007. Each charter mode extends the remit of the v2.1 specialist of its class (e.g., Contrarian Analyst is a charter mode of `apex_intelligence_forge`).
- Charter modes are staffing vocabulary, not v2.1 contract modes: packet-bound contract modes in `brains/*/agents.toml` are unchanged, and a charter mode gains typed packets and acceptance tests only through the normal acceptance process.
- Charter modes carry no write targets, connectors, or routes of their own; brain locks, writer leases, and specialist stages apply exactly as before.
- Seven dream-team names (5 APEX, 2 JEOS listed before truncation) are the v2.1 specialists themselves; the other three v2.1 JEOS specialists remain rostered unchanged.

## Intake rule

Use `templates/agent-intake.md` before adding or materially changing an agent. A name in conversation is not a deployed agent until its configuration, owner brain, namespace, targets, handoff, runtime access, tests, and controlled mission are verified.
