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

Runtime permissions, connected-service permissions, administrator policies, professional obligations, and mandatory tool controls still apply. No prompt can create access that is not connected or verified.

## Repository map

- `.codex/agents/apex_chief_of_staff.toml` — native Agent 007 custom-agent definition.
- `.codex/agents/apex_*.toml` — five APEX-only specialist definitions.
- `.codex/agents/jeos_*.toml` — five JEOS-only specialist definitions.
- `.codex/config.toml` — project autonomy, networking, and multi-agent settings.
- `config/specialist_corps.toml` — Agent 007's mirrored-class routing, lifecycle, and migration lineage.
- `brains/apex/` — APEX-owned roster, namespace, target, route, and memory policy.
- `brains/jeos/` — JEOS-owned roster, namespace, target, route, and memory policy.
- `AGENTS.md` — durable activation and repository guidance.
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
- `docs/ABSORBED_PATTERNS.md` — capability-absorption record from the ecosystem analysis.
- `docs/CIVIL3D_MCP_BUILDOUT.md` — Civil 3D MCP connector workstation build and validation guide.
- `docs/EXECUTION_LAYER_TRIAL.md` — codex-autorunner vs multica trial plan and decision rule.
- `schemas/` — delegation, handoff, and roundtable packet contracts.
- `templates/agent-intake.md` — new-agent onboarding and validation.
- `templates/specialist-handoff.md` — human-readable specialist packet.
- `templates/weekly-agent-audit.md` — weekly ecosystem review.
- `scripts/validate_specialist_corps.py` — honest static and synthetic v2.1 packet validation.
- `runtime/autogen_groupchat.py` — brain-private AutoGen GroupChat planning adapter.
- `requirements-runtime.txt` — opt-in runtime integration dependency set.
- `tests/test_agent_contract.py` — contract validation.
- `tests/test_specialist_corps.py` — roster, isolation, schema, privacy, and registry validation.
- `tests/test_local_validation.py` — validates the harness result and its no-runtime claims.

## Validation

Run:

```bash
python scripts/privacy_guard.py
python scripts/validate_specialist_corps.py
python -m unittest discover -s tests -v
```

GitHub Actions runs the same checks on pushes to `main` and pull requests.

The harness parses the configuration and validates synthetic v2.1 packets and fail-closed boundary probes. It does not invoke named agents, call connectors, complete real missions, or prove output quality.

The ten v2.1 specialists are deployed in `shadow` stage. Each becomes active only after every material mode completes a controlled real mission with evidence, runtime connector-isolation verification, writer-lease compliance, and readback where a mutation occurs. Agents are invoked on demand and do not claim continuous background operation.
