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

1. **Lifecycle StateGraph** — encode `candidate → shadow → active → value-proven → restricted → deprecated → retired` as a LangGraph `StateGraph` whose shadow→active edge enforces the acceptance gates in `docs/SPECIALIST_ACCEPTANCE_TESTS.md`. Human-in-the-loop checkpoint at every high-impact boundary.
2. **Cadence flow** — implement one cadence route (weekly APEX) as a Prefect flow whose tasks emit the existing artifact types; wire TICKET-002/TICKET-005 to it.
3. **Writer-lease queue** — prototype Celery per-target queues enforcing `single_writer_scope`; a mutation packet is only consumed from its target's queue.
4. **Challenge-pair debate** — wire one challenge pair (apex_war_architect vs apex_intelligence_forge) as an AutoGen two-agent exchange terminated by Agent 007 on artifact validity.
5. **Memory trial** — graphiti-core + FalkorDB on the workstation, one brain namespace first, per frontier-scan decision #2.

Each ticket lands as its own reviewed change with tests; none of these are active until their specialists pass the shadow→active gate.

## Dream-team roster (message 5) — resolved 2026-07-24

Joe resolved the held question by direct instruction ("YOLO"), overriding the former smallest-useful-team rule. The full roster is registered at candidate stage in `config/dream_team_roster.toml` (37 new APEX + 3 new JEOS candidates; ten names were already the v2.1 corps), the doctrine in `AGENTS.md` and the Agent 007 native contract is amended to full-corps mission staffing, and `tests/test_dream_team.py` validates the expansion. Candidates carry no write targets, connectors, or routes until individually promoted through the lifecycle. The privacy guard, brain locks, writer leases, and high-impact boundaries were explicitly retained — they protect Joe and are CI-enforced, and the override was read as targeting the conservatism rails, not the safety rails.
