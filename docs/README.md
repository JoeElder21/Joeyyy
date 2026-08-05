# Documentation index

32 records, grouped by purpose. Start at the top of each section.

## Start here

| Document | What it is |
| --- | --- |
| [`../AGENTS.md`](../AGENTS.md) | The authoritative operating contract. Read first. |
| [`APEX_CHIEF_OF_STAFF.md`](APEX_CHIEF_OF_STAFF.md) | Agent 007's operating contract and activation examples |
| [`AGENT_REGISTRY.md`](AGENT_REGISTRY.md) | Canonical agent inventory and lifecycle status |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | How to get a change landed |

## Governance and protocol

| Document | What it is |
| --- | --- |
| [`AGENT_COMMUNITY_PROTOCOL.md`](AGENT_COMMUNITY_PROTOCOL.md) | Delegation, handoffs, conflict resolution, intake, absorption, error learning, audits |
| [`SPECIALIST_CORPS_PROTOCOL.md`](SPECIALIST_CORPS_PROTOCOL.md) | Specialist isolation and operating system |
| [`SPECIALIST_ACCEPTANCE_TESTS.md`](SPECIALIST_ACCEPTANCE_TESTS.md) | Static, shadow, activation, and value gates |
| [`PROMOTION_CHECKLISTS.md`](PROMOTION_CHECKLISTS.md) | Per-specialist promotion worksheets: the catalog mission per mode, the covering loop, and the approval steps |
| [`EVALUATION_HARNESS.md`](EVALUATION_HARNESS.md) | Behavioral evaluation harness: metric contract, 39-mode coverage, Drive result boundary |
| [`PRIVACY_AND_DATA_BOUNDARIES.md`](PRIVACY_AND_DATA_BOUNDARIES.md) | Public-repository and runtime-data rules |
| [`BRAIN_CADENCE_RUNBOOK.md`](BRAIN_CADENCE_RUNBOOK.md) | Daily, weekly, and monthly brain-specific orchestration |
| [`../SECURITY.md`](../SECURITY.md) | Threat model, reporting, supply-chain posture |
| [`SECRET_HISTORY_SWEEP_2026-07-25.md`](SECRET_HISTORY_SWEEP_2026-07-25.md) | Full-history secret sweep: method, coverage proof, clean result |
| [`DEPENDENCY_AUDIT_2026-07-25.md`](DEPENDENCY_AUDIT_2026-07-25.md) | Known-vulnerability scan of the pinned dependencies, and the lockfile resolution failure it surfaced |
| [`../LICENSE`](../LICENSE) / [`../NOTICE`](../NOTICE) / [`../CITATION.cff`](../CITATION.cff) | Apache-2.0 grant, copyright and scope, citation metadata |

## Runtime and architecture

| Document | What it is |
| --- | --- |
| [`RUNTIME_NATIVE_LAYERS.md`](RUNTIME_NATIVE_LAYERS.md) | Anthropic SDK, MCP, pydantic layers; gated LangChain absorption |
| [`AGENT_RUNTIME_BRIDGE.md`](AGENT_RUNTIME_BRIDGE.md) | Governed-handoff bridge on the OpenAI Agents SDK |
| [`DATA_MEMORY_LAYERS.md`](DATA_MEMORY_LAYERS.md) | llama_index, mem0, crewAI |
| [`ORCHESTRATION_AND_CONNECTORS.md`](ORCHESTRATION_AND_CONNECTORS.md) | AutoGen, LangGraph, MCP servers, APS, Logseq |
| [`AUTOGEN_INTEGRATION.md`](AUTOGEN_INTEGRATION.md) | Bounded AutoGen runtime-adapter contract |
| [`AUTOGEN_CHALLENGE_PAIR_TRIAL.md`](AUTOGEN_CHALLENGE_PAIR_TRIAL.md) | Challenge-pair preflight trial |

## Domain: Civil 3D and Autodesk

| Document | What it is |
| --- | --- |
| [`CIVIL3D_MCP_BUILDOUT.md`](CIVIL3D_MCP_BUILDOUT.md) | Civil 3D MCP connector build and validation guide |
| [`CIVIL3D_FIRST_WRITE_TEST.md`](CIVIL3D_FIRST_WRITE_TEST.md) | Separately-approved synthetic disposable DWG first-write protocol |
| [`APS_SDK_BUILDOUT.md`](APS_SDK_BUILDOUT.md) | Autodesk Platform Services validation-gate buildout |
| [`DOTNET_SELF_LEARNING_ARCHITECT.md`](DOTNET_SELF_LEARNING_ARCHITECT.md) | .NET self-learning architect agent |

## External sourcing and absorption

Read in date order — each supersedes nothing, but later records assume earlier ones.

| Document | What it is |
| --- | --- |
| [`ECOSYSTEM_REPO_ANALYSIS.md`](ECOSYSTEM_REPO_ANALYSIS.md) | 14 supplied repositories, ranked with build/absorb/skip verdicts (2026-07-23) |
| [`ECOSYSTEM_REPO_ANALYSIS_2026-07-30.md`](ECOSYSTEM_REPO_ANALYSIS_2026-07-30.md) | 21 supplied repositories, ranked watch/absorb/reference/skip; no installs warranted (2026-07-30) |
| [`FRONTIER_REPO_SCAN_2026-07-24.md`](FRONTIER_REPO_SCAN_2026-07-24.md) | Web-sourced frontier scan; the FakeGit intake-hardening finding |
| [`EXTERNAL_RUNTIME_REGISTER_2026-07-24.md`](EXTERNAL_RUNTIME_REGISTER_2026-07-24.md) | Declared runtime dependencies 11–24 and promotion conditions |
| [`REPO_OPTIMIZATION_2026-07-25.md`](REPO_OPTIMIZATION_2026-07-25.md) | Repository-engineering review: substrate gaps, evaluation/supply-chain candidates |
| [`REPO_AUDIT_2026-07-30.md`](REPO_AUDIT_2026-07-30.md) | Adversarial audit against Google's Antigravity SDK; executed verification of what this harness does and does not do |
| [`ABSORBED_PATTERNS.md`](ABSORBED_PATTERNS.md) | Capability-absorption extraction record |
| [`EXECUTION_LAYER_TRIAL.md`](EXECUTION_LAYER_TRIAL.md) | codex-autorunner vs multica trial plan and decision rule |

## Program and change records

| Document | What it is |
| --- | --- |
| [`INTEGRATION_ROADMAP.md`](INTEGRATION_ROADMAP.md) | Phased runtime-stack integration program |
| [`FRAMEWORK_INTEGRATION_PROGRAM.md`](FRAMEWORK_INTEGRATION_PROGRAM.md) | Framework integration sequence and deployment gates |
| [`INTEGRATION_BUILDOUT_2026-07-24.md`](INTEGRATION_BUILDOUT_2026-07-24.md) | Installed stack tiers, workstation deployments, first build tickets |
| [`RECONCILIATION_2026-07-24.md`](RECONCILIATION_2026-07-24.md) | Cross-stream ownership record and drift locks |
| [`ROSTER_MIGRATION_2026-07-23.md`](ROSTER_MIGRATION_2026-07-23.md) | v1-to-v2 capability mapping and rollback procedure |
| [`../CHANGELOG.md`](../CHANGELOG.md) | Dated summary of repository-level changes |

## Elsewhere in the repository

- [`../evals/`](../evals/) — behavioral evaluation harness; results publish to Drive, not here
- [`../templates/`](../templates/) — intake, handoff, brief, and audit templates
- [`../schemas/`](../schemas/) — delegation, handoff, memory, lease, and roundtable packet contracts
- [`../trial/`](../trial/) — execution-layer trial tickets and output
- [`../brains/`](../brains/) — APEX and JEOS brain-owned rosters and memory policy
