# APEX Chief of Staff

APEX Chief of Staff is a native Codex custom agent for Joe Elder's professional command center. It converts authorized project context into priorities, delegates work to specialist agents, executes routine actions, validates results, and reports what changed.

The agent now uses delegated autonomy. Within Joe's requested outcome and the tools available in the active session, it may send communications, manage calendars and tasks, edit authorized external systems, and change, test, commit, or push code without asking for per-action approval. It also coordinates specialist agents as a working community through scoped handoffs and a single-writer rule.

Codex runtime permissions, connected-service permissions, administrator policies, and tool-enforced controls still apply. The configuration cannot grant access to a service that has not been connected or override a mandatory provider restriction.

## Start here

1. Open this repository as the active project in Codex.
2. Select an execution-capable permission mode for the parent session when the Codex surface exposes one.
3. Ask: `Use apex_chief_of_staff to complete today's APEX priorities. Delegate specialist work where useful and execute routine actions.`
4. Review the completion report, action log, and any true runtime blockers.

See [docs/APEX_CHIEF_OF_STAFF.md](docs/APEX_CHIEF_OF_STAFF.md) for the operating contract and [docs/AGENT_COMMUNITY_PROTOCOL.md](docs/AGENT_COMMUNITY_PROTOCOL.md) for collaboration rules.

## Repository map

- `.codex/agents/apex_chief_of_staff.toml` — native Codex custom-agent definition.
- `.codex/config.toml` — project-scoped autonomy, networking, and multi-agent settings.
- `AGENTS.md` — durable repository guidance for Codex.
- `docs/APEX_CHIEF_OF_STAFF.md` — scope, delegated authority, and invocation examples.
- `docs/AGENT_COMMUNITY_PROTOCOL.md` — multi-agent delegation and handoff protocol.
- `templates/daily-brief.md` — daily briefing and completed-action structure.
- `templates/project-intake.md` — structured intake and execution map.
- `tests/test_agent_contract.py` — automated validation of autonomy and coordination requirements.

## Memory and connected tools

The agent can use only the tools and connectors available in the active Codex session. Yaps Memory is optional and must be connected separately. The agent must never claim that a connector, memory source, or delegated agent is available until the active session verifies it.

## Validation

Run `python -m unittest discover -s tests -v`. GitHub Actions runs the same contract checks on pushes to `main` and on pull requests.
