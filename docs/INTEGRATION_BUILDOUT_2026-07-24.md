# Runtime Integration Build-Out — 2026-07-24

Agent 007 execution record for Joe's directive: incorporate the supplied repository lists into the system. This document is the single reconciliation point for the five intake messages (frontier-scan recap, 23-repo URL list with priorities, 26-repo categorized plan, 5-phase synthesis with deep dives, dream-team roster) and states exactly what was installed, what was registered for workstation deployment, and what was flagged. Companion analyses: `docs/ECOSYSTEM_REPO_ANALYSIS.md`, `docs/FRONTIER_REPO_SCAN_2026-07-24.md`.

## Joe's through-line (accepted as the build thesis)

The repo has governance contracts (TOML configs, JSON schemas, lifecycle stages, challenge pairs) but lacked the runtime enforcement and automation that makes contracts real. Four gaps:

1. **Static configs need a runtime** — AutoGen, LangGraph, crewAI, Prefect, Celery.
2. **Conceptual memory needs a store** — mem0, LlamaIndex, LangChain (+ graphiti from the frontier scan).
3. **Policy needs enforcement** — jsonschema, pydantic, rtoml, Guardrails.
4. **Text outputs need real-world connections** — n8n, Trigger.dev, Twenty, Plane, APS SDK, MCP servers.

## What "built into the system" means here

This is a public governance repo, not a deployment target. Vendoring 24 codebases into it would violate the house change standards (small, reviewable, reversible) and the privacy guard. The build-in therefore has three forms, applied per repo:

- **Installed** — pip-installable runtimes declared in `requirements/runtime-*.txt`, installed into an isolated environment, verified by `scripts/verify_runtime_stack.py` and `tests/test_runtime_stack.py`. The resolved versions are locked in `requirements/lock-2026-07-24.txt`.
- **Registered** — platforms, services, and non-Python SDKs that must be deployed on Joe's workstation or cloud (they are running systems, not libraries). Each has an owner agent and a next action below.
- **Flagged** — items that failed the FakeGit provenance gate or conflict with a standing decision; not downloaded.

## Installed: the runtime stack (six tiers)

| Tier | Packages | Gap | Immediate use in this repo |
| --- | --- | --- | --- |
| contracts | pydantic, jsonschema, rtoml, mcp, anthropic | 3 | `verify_runtime_stack.py` now compiles all eight packet schemas with spec-complete jsonschema and parses every TOML with rtoml — real validators superseding the hand-rolled structural checker for schema correctness. |
| orchestration | langgraph, crewai, autogen-agentchat, prefect, celery, openai-agents | 1 | LangGraph is the designated runtime for the lifecycle state machine and cadence routes; Prefect for scheduled cadences (TICKET-005 is a Prefect flow); Celery queues for writer-lease serialization; AutoGen GroupChat for challenge pairs; crewAI Agent/Task mapping for the TOML→runtime conversion. First build ticket below. |
| memory | mem0ai, langchain, llama-index-core, graphiti-core | 2 | graphiti-core is the memory-layer trial pick (frontier scan Tier 1); mem0 evaluated as the lightweight alternative for per-brain namespaces; llama-index for evidence intake by apex_intelligence_forge. |
| observability | opentelemetry-sdk, arize-phoenix-otel, taskipy | audit | Session tracing for the weekly audit. Full Phoenix server is a workstation deployment, not a library — registered below. |
| guards | guardrails-ai | 3 | Pre-flight output validation wrapping LLM calls, complementing packet_guard's post-hoc checks. |
| intelligence | dspy | 4 (list 2) | Prompt-as-program compilation for agent contracts once example missions accumulate. |

Install results are environment-specific: run `python scripts/verify_runtime_stack.py` to see the live dependency audit. CI remains stdlib-only and green without the stack — runtime tests skip cleanly when packages are absent.

## Registered: workstation / cloud deployments (not pip-installable)

| System | Layer | Owner agent | Next action |
| --- | --- | --- | --- |
| modelcontextprotocol/servers (filesystem, github, postgres) | Connectors | Agent 007 | Install per-host via npx on the workstation; satisfies packet-only connector policy. |
| n8n | World actions | apex_systems_blacksmith | Self-host trial after the Multica/CAR execution-layer trial concludes; do not run three execution layers at once. |
| Trigger.dev / Windmill | Scheduled cadences | apex_systems_blacksmith | Deferred behind Prefect (installed, same capability, no service to run). Revisit only if Prefect underperforms. |
| Twenty CRM | APEX/Opportunity-Pipeline backing store | apex_deal_engine | Candidate system of record; needs a data-privacy review before any client data enters a self-hosted CRM. |
| Plane | APEX/Delivery-Control backing store | apex_delivery_commander | Same posture as Twenty. |
| Logseq | JEOS write-target store | jeos_reflection_forge | Desktop install on personal machine; HTTP API keys stay out of this repo. |
| autodesk-platform-services/aps-sdk-node | Civil 3D cloud data | apex_intelligence_forge | Workstation Node.js install alongside the civil3d-mcp build session (`docs/CIVIL3D_MCP_BUILDOUT.md`). |
| specklepy / IfcOpenShell | Live model data | apex_delivery_commander | Pair with the civil3d-mcp build-out; specklepy is pip-installable when that session starts. |
| E2B sandboxes | Specialist sandbox infrastructure | Agent 007 | Cloud service with API key; evaluate against the native Codex sandbox before adopting a second sandbox layer. |
| cal.com | JEOS calendar actions | jeos_energy_director | Hosted or self-hosted decision belongs to Joe; calendar write access is a connector-permission change. |
| Arize Phoenix (server) | Audit observability | Agent 007 | Deploy on workstation when session volume justifies it; the otel client is already installed. |
| AgentOps / honcho / Unstructured / Jina Reader / LangKit | Session replay, user model, document + web intake, output monitoring | various | Absorption-first per the 26-repo plan; promote to installs when the owning agent has a concrete mission that needs them. |

## Flagged: not downloaded

| Item | Reason |
| --- | --- |
| nicholasgasior/gpt-life-coach | Failed the FakeGit provenance gate: unverifiable author and repo from the sources available this session. Exactly the profile the intake gate exists for. Re-verify canonically before any future intake. |
| apache/airflow | Canonical and safe, but deliberately deferred: redundant with Prefect for this system's scale, and its heavy dependency pins would destabilize the shared runtime environment. Recorded, not installed. |
| microsoft/JARVIS, yoheinakajima/babyagi, kyegomez/tree-of-thoughts, Azure/counterfit | Pattern-gold but code-stale (historical or low-maintenance projects). Absorb the patterns (task decomposition, ToT branching for challenge pairs, red-team templates for the active gate) via `docs/ABSORBED_PATTERNS.md`; do not run their code. |
| SuperAGI, MetaGPT, ChatDev, ai-town | Absorb lifecycle-gating, typed artifact chains, phase termination conditions, and simulation-as-staging patterns; deploying a second agent OS conflicts with the native Codex + Claude architecture. |

## First build tickets (execution order)

1. **Lifecycle StateGraph** — *delivered 2026-07-24.* `runtime/lifecycle.py` encodes the stage machine and gates (4, 11, 20, 21) as stdlib-pure fail-closed functions; `runtime/lifecycle_graph.py` wires them into a LangGraph `StateGraph` that interrupts for Joe's approval before any promotion to active, and approval never bypasses the evidence gates. Validated by `tests/test_lifecycle.py` in both stdlib and full-stack environments.
2. **Cadence flow** — *delivered 2026-07-24.* `runtime/cadence.py` loads all six cadence routes from the brain manifests (single source of truth), builds ordered delegation-packet plans with brain-lock/single-mode/integrator enforcement, reports unexecuted specialist steps as `partial` (never backfilled), and implements the TICKET-005 hygiene sweep for real (three checks, one appended ISO-dated line, append-only, failures never retried into silence). `runtime/cadence_flow.py` adds the Prefect layer: `hygiene_sweep_flow` (cron `0 7 * * 1-5`), `weekly_apex_flow` (cron `0 8 * * 1`, the TICKET-002 Monday review), and `serve_cadences()` as the workstation entry point. Validated by `tests/test_cadence.py` in both environments. Note: Prefect was chosen over Trigger.dev deliberately — the Codex-stream roadmap records Trigger.dev as conflicting with the execution-layer trial, and Prefect is a library with no service to run.
3. **Writer-lease queue** — *delivered 2026-07-24.* `runtime/writer_lease.py` executes acceptance gate 8 (one active lease per canonical ASCII brain/target/resource, ≤24-hour expiry, whitespace and Unicode-alias rejection) with schema-shaped lease dicts, plus serialized mutation admission with readback-gated `verified` release. `runtime/lease_queue.py` adds Celery per-key queues (eager mode for tests, Redis broker + one worker per queue at workstation activation). Validated by `tests/test_writer_lease.py`.
4. **Challenge-pair debate** — *closed as absorbed 2026-07-24.* Delivered by the Codex stream (`scripts/group_debate.py`, `scripts/autogen_challenge_pair.py`); no second implementation. See `docs/RECONCILIATION_2026-07-24.md`.
5. **Memory trial** — *harness delivered 2026-07-24; trial awaits workstation infrastructure.* `runtime/memory_trial.py` runs the one-namespace graphiti trial (write + readback in `APEX::Strategy-Campaigns`) when FalkorDB and an LLM key exist, and reports `blocked` with the exact missing preconditions otherwise — never simulated. Run `python -m runtime.memory_trial` on the workstation after starting FalkorDB.

Cross-stream ownership, the ticket-4 closure, and the memory-layer decision rule are recorded in `docs/RECONCILIATION_2026-07-24.md`, drift-locked by `tests/test_reconciliation.py`.

Each ticket lands as its own reviewed change with tests; none of these are active until their specialists pass the shadow→active gate.

## Dream-team roster (message 5) — resolved 2026-07-24

Joe resolved the held question by direct instruction ("YOLO"), then refined it the same day: **treat the dream-team roles as modes.** The roster is registered as forty charter modes in `config/dream_team_roster.toml` (37 APEX + 3 JEOS; seven names were already v2.1 specialists), each owned by the v2.1 specialist of its class — the corps stays ten agents plus Agent 007. The staffing doctrine in `AGENTS.md` and the Agent 007 native contract is amended to full-corps mission staffing through charter modes, and `tests/test_dream_team.py` validates ownership, brain locks, uniqueness against contract modes, and counts. Charter modes carry no write targets, connectors, or routes. The privacy guard, brain locks, writer leases, and high-impact boundaries were explicitly retained — they protect Joe and are CI-enforced.
