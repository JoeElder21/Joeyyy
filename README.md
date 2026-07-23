# APEX Chief of Staff

APEX Chief of Staff is a native Codex custom agent for Joe Elder's professional command center. Its job is to reduce mental load by turning authorized project context into prioritized briefs, meeting preparation, proposed tasks, decision support, and draft communications.

Version 1 is intentionally read-only. It may analyze and draft, but it may not send messages, change calendars, edit external systems, create tasks, or commit code. It previews consequential actions and asks Joe for explicit approval.

## Start here

1. Open this repository as the active project in Codex.
2. Ask Codex: `Use the apex_chief_of_staff agent to prepare my APEX daily brief.`
3. Provide or authorize only the sources needed for that run.
4. Review the proposed actions before approving anything in another workflow.

See [docs/APEX_CHIEF_OF_STAFF.md](docs/APEX_CHIEF_OF_STAFF.md) for the operating contract and example requests.

## Repository map

- `.codex/agents/apex_chief_of_staff.toml` — native Codex custom-agent definition.
- `.codex/config.toml` — project-scoped agent settings.
- `AGENTS.md` — durable repository guidance for Codex.
- `docs/APEX_CHIEF_OF_STAFF.md` — scope, workflow, safety boundaries, and invocation examples.
- `templates/daily-brief.md` — stable daily briefing structure.
- `templates/project-intake.md` — structured intake for new assignments.
- `tests/test_agent_contract.py` — automated validation of the agent's required safety and operating boundaries.

## Memory and connected tools

The agent can use tools and connectors available in the active Codex session. Yaps Memory is optional and must be connected separately. The agent must never claim that a connector or memory source is available until the active session verifies it.

## Validation

Run `python -m unittest discover -s tests -v`. GitHub Actions runs the same contract checks on pushes to `main` and on pull requests.
