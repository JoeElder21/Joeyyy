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
- Five native v2 APEX specialist definitions and five native v2 JEOS specialist definitions.
- Separate brain-owned manifests, logical memory namespaces, proposed write targets, routes, and private roundtables.
- Strict brain locks, same-brain challenge pairs, structured handoffs, writer leases, readback, rollback, and shadow-to-active acceptance gates.
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
- `docs/SPECIALIST_ACCEPTANCE_TESTS.md` — static, shadow, activation, and value gates.
- `schemas/` — delegation, handoff, and roundtable packet contracts.
- `templates/agent-intake.md` — new-agent onboarding and validation.
- `templates/specialist-handoff.md` — human-readable specialist packet.
- `templates/weekly-agent-audit.md` — weekly ecosystem review.
- `tests/test_agent_contract.py` — contract validation.
- `tests/test_specialist_corps.py` — roster, isolation, schema, privacy, and registry validation.

## Validation

Run `python -m unittest discover -s tests -v`. GitHub Actions runs the same checks on pushes to `main` and pull requests.

The ten v2 specialists are deployed in `shadow` stage. Static tests verify their contracts; each becomes active only after one controlled real mission with evidence, writer-lease compliance, and readback. Agents are invoked on demand and do not claim continuous background operation.
