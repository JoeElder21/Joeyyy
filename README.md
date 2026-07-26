# Agent 007 — APEX Chief of Staff

Agent 007 is Joe Elder's cross-brain Chief of Staff, agent governor, and multi-agent orchestrator. It oversees APEX and Joe's Brain/JEOS, keeps their domain records separate, delegates to owner agents and specialists, executes authorized work, validates results, and improves the agent ecosystem from evidence.

The repository includes two brain-locked, mirrored specialist units: five APEX agents and five JEOS agents. Both units cover strategy, opportunity or momentum, execution or capacity, intelligence or reflection, and systems or automation—but they remain ten independent agents. Agent 007 is the only agent permitted to see or coordinate both brains.

## Activate

Say:

`Activate Agent 007. <mission>`

The personal Agent 007 skill makes that phrase portable across chats where the skill is available. In this repository, the native custom-agent name remains `apex_chief_of_staff` for compatibility.

## What changed

- Universal Agent 007 activation phrase and operating identity.
- Cross-brain comparison and governance without merging APEX and JEOS.
- Owner-agent routing and one designated writer per shared resource.
- Agent registry, candidate validation, and new-agent intake.
- Controlled capability absorption from new agent files.
- Error ledger, root-cause repair, reflection, and recurrence tests.
- Weekly self, specialist, brain, and ecosystem audits.
- Autonomous routine execution within Joe's requested mission and available tools.
- Five native v2.1 APEX specialist definitions and five native v2.1 JEOS specialist definitions.
- Separate brain-owned manifests, logical memory namespaces, proposed write targets, routes, and private roundtables.
- Strict brain locks, same-brain challenge pairs, deterministic routing and cadence, mode-bound typed handoffs, writer leases, readback, rollback, and shadow-to-active acceptance gates.
- A repository-only roster rationale plus a reversible v2 migration record.
- Market Operator: a standalone JEOS-owned portfolio agent with a read-only Charles Schwab connector, a versioned risk policy, and a research-corroborated daily brief. It recommends; it never trades.

Runtime permissions, connected-service permissions, administrator policies, professional obligations, and mandatory tool controls still apply. No prompt can create access that is not connected or verified.

## Repository map

- `.codex/agents/apex_chief_of_staff.toml` — native Agent 007 custom-agent definition.
- `.codex/agents/apex_*.toml` — five APEX-only specialist definitions.
- `.codex/agents/jeos_*.toml` — five JEOS-only specialist definitions.
- `.codex/config.toml` — project autonomy, networking, and multi-agent settings.
- `config/specialist_corps.toml` — Agent 007's mirrored-class routing, lifecycle, and migration lineage.
- `brains/apex/` — APEX-owned roster, namespace, target, route, and memory policy.
- `brains/jeos/` — JEOS-owned roster, namespace, target, route, and memory policy.
- `AGENTS.md` — the JOEYYY Global Agent Engineering Constitution: canonical cross-runtime repository policy, activation, and repository operating annex.
- `CLAUDE.md` — Claude-runtime guidance with detailed non-obvious constraints; defers to `AGENTS.md` as the single contract.
- `.github/copilot-instructions.md` — thin GitHub Copilot runtime adapter pointing to `AGENTS.md`.
- `docs/README.md` — indexed entry point to every documentation record.
- `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md` — contribution mechanics, threat model and reporting, dated change history.
- `.pre-commit-config.yaml` — local offline gates (gitleaks, ruff, privacy guard, corps validation) before a commit exists.
- `docs/CONSTITUTION_ADOPTION_2026-07-25.md` — constitution adoption record, staffing-rule supersession, and rollback point.
- `docs/MONDAY_ACTIVATION_RUNBOOK.md` — how to actually run the corps, what each value verdict means, and what is honestly not ready.
- `.claude/agents/` — the ten specialists and Agent 007 projected into Claude Code subagents from the canonical contracts; connector isolation enforced by the tool list. Regenerate with `python scripts/generate_claude_agents.py`.
- `runtime/mission_runner.py` — controlled-mission harness: validated delegation, typed return, connector-isolation check, hash-chained evidence, per-mode promotion coverage.
- `config/value_policy.toml` + `runtime/value_meter.py` — the section 17 value policy and its meter: net saving after review, correction, incident, and maintenance, against a binding 35% threshold.
- `docs/REPO_OPTIMIZATION_2026-07-25.md` — repository-engineering review: substrate gaps, evaluation and supply-chain candidates, and the five resolved decisions.
- `evals/` + `docs/EVALUATION_HARNESS.md` — behavioral evaluation harness: 39 material modes derived from the brain manifests, a metric contract traced to recorded gates, and a publication path to the Evaluations folder on Drive rather than this repository. **Built and tested, not yet wired** — `_invoke_specialist()` raises `NotImplementedError`, so no mission is dispatched, no output is judged, and no behavioral evidence exists yet. It makes the shadow-to-active backlog *measurable* (39 modes, 3 with authored cases); it does not yet close the output-quality gate. Wiring dispatch needs a model credential and a connector-isolation decision.
- `docs/SECRET_HISTORY_SWEEP_2026-07-25.md` — full-history secret sweep: clean across all 95 commits, with coverage verified independently of the tool's own summary.
- `docs/DEPENDENCY_AUDIT_2026-07-25.md` — known-vulnerability scan of the pinned dependency set, plus the lockfile resolution conflict it exposed; now a standing weekly CI job.
- `scripts/policy_enforcement.py` — the single policy-enforcement point: eight rules (roster, brain lock, connector policy, packet admission, writer lease, lifecycle stage, high-impact boundary, launch grant) in one call a caller cannot partially perform. **Built and tested, not yet wired** — `enforce()` has no call sites, so it constrains nothing at runtime today. Connecting it is the top follow-up in `docs/REPO_OPTIMIZATION_2026-07-25.md`; until then this module is a specification with a test suite, not an active gate.
- `evals/packet_validity.py` — deterministic, model-free evaluation metric running the live `PacketGuard`, so an evaluation and a real handoff are judged by identical rules.
- `LICENSE`, `NOTICE`, `CITATION.cff` — Apache-2.0, with the reusable contribution scoped to the governance patterns rather than the roster.
- `docs/APEX_CHIEF_OF_STAFF.md` — operating contract and activation examples.
- `docs/AGENT_COMMUNITY_PROTOCOL.md` — delegation, learning, and audit protocol.
- `docs/AGENT_REGISTRY.md` — canonical agent inventory and lifecycle status.
- `docs/ROSTER_MIGRATION_2026-07-23.md` — v1-to-v2 capability mapping and rollback procedure.
- `docs/PRIVACY_AND_DATA_BOUNDARIES.md` — public-repository and runtime-data rules.
- `docs/SPECIALIST_CORPS_PROTOCOL.md` — specialist isolation and operating system.
- `docs/BRAIN_CADENCE_RUNBOOK.md` — daily, weekly, and monthly brain-specific orchestration.
- `docs/SPECIALIST_ACCEPTANCE_TESTS.md` — static, shadow, activation, and value gates.
- `docs/ECOSYSTEM_REPO_ANALYSIS.md` — ranked external-repository analysis and build/absorb/skip verdicts.
- `docs/FRAMEWORK_INTEGRATION_PROGRAM.md` — framework integration sequence, AutoGen-first implementation, deployment gates, and Google Drive publication record.
- `docs/AUTOGEN_INTEGRATION.md` — bounded Microsoft AutoGen runtime-adapter contract, validation, and Drive-record handoff.
- `runtime/autogen_orchestrator.py` — optional AutoGen `ConversableAgent`/`GroupChatManager` cadence adapter; requires a verified host runtime.
- `docs/FRONTIER_REPO_SCAN_2026-07-24.md` — proactive frontier scan: adoption candidates, absorption patterns, and the FakeGit intake-hardening finding.
- `docs/INTEGRATION_BUILDOUT_2026-07-24.md` — runtime integration record: installed stack tiers, registered workstation deployments, flagged items, and first build tickets.
- `requirements/` — tiered runtime-stack manifests (`runtime-*.txt`), vendored-repo manifests (`vendor-*.txt`), and the resolved version lock.
- `vendor/` — external repositories installed as pinned git submodules; provenance, declared dependencies, and boundaries in `vendor/README.md`. Fetch with `git submodule update --init --recursive`.
- `connectors/relay/` — declared `agent-relay` dependency for the vendored Agent Relay transport; a declaration only, with no relay server configured.
- `scripts/verify_runtime_stack.py` — dependency audit plus jsonschema/rtoml contract enforcement; degrades to stdlib cleanly.
- `scripts/agent_runtime.py` — governed-handoff runtime bridge on the OpenAI Agents SDK: fail-closed packet admission, brain-locked topology, hash-chained audit ledger.
- `docs/AGENT_RUNTIME_BRIDGE.md` — runtime-bridge record: contract-to-runtime mapping, measured dispatch-overhead reduction, boundaries, and rollback.
- `scripts/claude_runtime.py` — Claude-native governed dispatch: typed Anthropic tool definitions, fail-closed ToolUseBlock handling, mission streaming.
- `scripts/governance_mcp_server.py` — governance MCP server making the packet-only connector policy enforceable.
- `scripts/packet_models.py` — pydantic packet models generated at import time from the canonical JSON schemas.
- `docs/RUNTIME_NATIVE_LAYERS.md` — native runtime layers record: Anthropic SDK, MCP, pydantic implementations and the gated LangChain absorption.
- `scripts/evidence_index.py` — governed evidence indexes on llama_index: designated-writer writes, brain-locked retrieval.
- `scripts/memory_layer.py` — governed memory gateway on the mem0 scope model: leased namespace writes, open in-brain reads, verify-before-write.
- `scripts/crew_bridge.py` — roster-to-crewAI bridge: fail-closed task admission, single-brain crews, 007 as the integration step.
- `docs/DATA_MEMORY_LAYERS.md` — data and memory layers record: llama_index, mem0, crewAI.
- `scripts/orchestration_graphs.py` — LangGraph state machines: lifecycle with acceptance-gate guards, manifest cadence runs, human-in-the-loop irreversible boundary.
- `scripts/group_debate.py` — AutoGen challenge-pair debates, cadence chats, and the dynamic selector over each brain.
- `scripts/jeos_knowledge.py` — governed JEOS knowledge graph in Logseq format: writer-locked targets, brain-locked reads, tag queries, backlinks.
- `config/mcp_mounts.toml` + `scripts/verify_mcp_mounts.py` — approved MCP server mounts per the connector policy, with live stdio verification.
- `scripts/aps_credential_check.mjs` — APS readiness check completing validation-gate steps 2–3 once credentials exist.
- `docs/ORCHESTRATION_AND_CONNECTORS.md` — orchestration and connectors record: AutoGen, LangGraph, MCP servers, APS, Logseq.
- `scripts/cadence_flows.py` — cadence routes as Prefect flows with cron deployment specs; steps audit-logged.
- `scripts/observability.py` — OpenTelemetry spans over governed operations with a weekly-review aggregator; Phoenix export at activation.
- `scripts/trusted_launcher.py` — user-signed, one-time launch grants for write-capable mounts; denial paths proven by tests.
- `scripts/issue_instruction.py` — mints the signed task-level instruction the high-impact boundary requires, for one category and one resource, with a capped validity window. A separate command from the launcher on purpose: launching a mount and minting Joe's personal authority are different privileges. The grant is **replayable until it expires** — nonce consumption needs an execution boundary and is a recorded open decision.
- `docs/CIVIL3D_FIRST_WRITE_TEST.md` — the separately-approved synthetic disposable DWG first-write protocol.
- `config/dream_team_roster.toml` — dream-team charter modes: 40 roles registered 2026-07-24 on Joe's instruction as modes of the ten v2.1 specialists, per his roles-as-modes decision.
- `runtime/` — executable governance: the lifecycle gate engine (`lifecycle.py`, stdlib-pure) and its LangGraph state machine (`lifecycle_graph.py`) with a hard human checkpoint before activation; the cadence engine (`cadence.py`) building validated delegation plans from the brain manifests plus the real TICKET-005 hygiene sweep, and its Prefect scheduling layer (`cadence_flow.py`); the writer-lease registry and serialized mutation admission (`writer_lease.py`) with Celery per-key queues (`lease_queue.py`); the graphiti memory-trial harness (`memory_trial.py`).
- `docs/RECONCILIATION_2026-07-24.md` — cross-stream ownership record: canonical homes for lifecycle/cadence/leases, ticket-4 absorption, memory-layer decision rule, drift locks.
- `connectors/schwab/` — read-only Charles Schwab Trader/Market Data client plus portfolio analytics, indicators, policy-driven verdicts, and the daily-brief CLI. Stdlib-only; `GET` requests only, with no order-placement path.
- `config/portfolio_policy.toml` — the Market Operator rulebook: risk guardrails, indicator windows, scoring weights, and verdict thresholds.
- `.claude/agents/market-operator.md` — Market Operator operating contract (daily loop, research protocol, hard boundaries).
- `docs/SCHWAB_TRADING_AGENT.md` — Schwab setup runbook: app registration, OAuth, the 7-day refresh wall, daily scheduling, tuning, and honest limits.
- `docs/ABSORBED_PATTERNS.md` — capability-absorption record from the ecosystem analysis.
- `docs/ADK_SAMPLES_ABSORPTION.md` — google/adk-samples absorption record: nine patterns absorbed, eight dropped as already-built, two observability defects fixed.
- `docs/CIVIL3D_MCP_BUILDOUT.md` — Civil 3D MCP connector workstation build and validation guide.
- `docs/EXECUTION_LAYER_TRIAL.md` — codex-autorunner vs multica trial plan and decision rule.
- `docs/INTEGRATION_ROADMAP.md` — phased runtime-stack integration program with recorded conflicts and intake gates.
- `schemas/` — delegation, handoff, and roundtable packet contracts.
- `templates/agent-intake.md` — new-agent onboarding and validation.
- `templates/specialist-handoff.md` — human-readable specialist packet.
- `templates/weekly-agent-audit.md` — weekly ecosystem review.
- `scripts/validate_specialist_corps.py` — honest static and synthetic v2.1 packet validation.
- `runtime/autogen_groupchat.py` — brain-private AutoGen GroupChat planning adapter.
- `runtime/trusted_launcher.py` — user-signed one-time grant launcher for constrained external tool activation.
- `scripts/trusted_launcher.py` — user-signed, one-time launch grants for write-capable MCP mounts; denial paths proven by tests.
- `requirements-runtime.txt` — opt-in runtime integration dependency set.
- `tests/test_agent_contract.py` — contract validation.
- `tests/test_specialist_corps.py` — roster, isolation, schema, privacy, and registry validation.
- `tests/test_local_validation.py` — validates the harness result and its no-runtime claims.

## Validation

Repository validation and the optional AutoGen adapter require Python 3.11 or 3.12. Run:

```bash
# The install comes first: verify_runtime_stack.py catches the ImportError for
# jsonschema and rtoml, reports zero schemas and zero TOML files checked, and
# exits 0 -- so running it beforehand passes the audit while validating nothing.
# The LOCK, not the manifest. CI installs the resolved lock and osv-scanner
# audits it with --no-resolve, so installing the floating manifest here puts a
# resolution on the workstation that nothing scanned and CI never tested.
# The root lock FIRST. CI's validate job installs this before the contracts
# lock, and it carries autogen-agentchat -- so `tests/test_autogen_orchestrator.py`
# SKIPS on a workstation that installed only the contracts tier and RUNS in CI.
# A sequence advertised as "run everything by hand" that silently exercises
# fewer tests than CI is the aggregate-versus-hand-run divergence again, in the
# direction that lets a real failure reach CI unseen.
python -m pip install -r requirements/lock-runtime-root.txt
python -m pip install -r requirements/lock-runtime-contracts.txt
# Ruff too: runtime-contracts.txt does not carry it, and installing
# pre-commit builds Ruff an isolated hook environment whose executable is
# not on PATH -- so this sequence reached `ruff check .` with no `ruff`
# command and stopped there. Pinned to the version CI and the hook use.
python -m pip install ruff==0.14.6
python scripts/privacy_guard.py
python scripts/validate_specialist_corps.py
python scripts/verify_runtime_stack.py
python scripts/verify_mcp_mounts.py --strict
ruff check .
ruff format --check .
python -m unittest discover -s tests -v
```

`pre-commit install` runs **most** of these automatically before each commit — the privacy guard, corps validation, the unit suite, gitleaks, `ruff check`, and `ruff format --check`. It deliberately does **not** run `verify_runtime_stack.py` or the strict mount probe: the probe launches servers and fetches an npm package, which is not something to do on every commit. Those two, and the `pip install` they depend on, remain manual.

That distinction matters rather than being pedantry: the unit suite lets its JSON Schema check skip when `jsonschema` is absent, so a contributor relying on the hooks alone can pass locally and still fail CI on a malformed schema or a broken mount. Run the full sequence above before pushing. See `CONTRIBUTING.md`.

For a verified Microsoft AutoGen 0.2 host runtime, install the optional adapter dependency with `python -m pip install -r requirements/lock-runtime-root.txt` (the lock, for the same reason as above — `requirements.txt` is the manifest it resolves). The dependency uses Microsoft's official `autogen-agentchat` distribution and remains pinned to the legacy 0.2 API. This repository does not contain model configuration or connector credentials.

GitHub Actions validates Python 3.11 and 3.12, installs the pinned adapter dependency, and runs the same checks plus a no-model AutoGen lifecycle smoke test on pushes to `main` and pull requests. Separate jobs lint the Python tree and install the APS Node connector, and a scheduled zizmor job audits the workflows themselves. Every action is pinned to a full commit SHA, enforced by `tests/test_repo_hygiene.py` and kept current by Dependabot.

The harness parses the configuration and validates synthetic v2.1 packets and fail-closed boundary probes. It does not invoke named agents, call connectors, complete real missions, or prove output quality.

The ten v2.1 specialists are deployed in `shadow` stage. Each becomes active only after every material mode completes a controlled real mission with evidence, runtime connector-isolation verification, writer-lease compliance, and readback where a mutation occurs. Agents are invoked on demand and do not claim continuous background operation.
