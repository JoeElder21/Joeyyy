# Agent 007 — APEX Chief of Staff

Agent 007 is Joe Elder's cross-brain Chief of Staff, agent governor, and multi-agent orchestrator. It oversees APEX and Joe's Brain/JEOS, keeps their domain records separate, delegates to owner agents and specialists, executes authorized work, validates results, and improves the agent ecosystem from evidence.

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

Runtime permissions, connected-service permissions, administrator policies, professional obligations, and mandatory tool controls still apply. No prompt can create access that is not connected or verified.

## Repository map

- `.codex/agents/apex_chief_of_staff.toml` — native Agent 007 custom-agent definition.
- `.codex/config.toml` — project autonomy, networking, and multi-agent settings.
- `AGENTS.md` — durable activation and repository guidance.
- `docs/APEX_CHIEF_OF_STAFF.md` — operating contract and activation examples.
- `docs/AGENT_COMMUNITY_PROTOCOL.md` — delegation, learning, and audit protocol.
- `docs/AGENT_REGISTRY.md` — canonical agent inventory and lifecycle status.
- `templates/agent-intake.md` — new-agent onboarding and validation.
- `templates/weekly-agent-audit.md` — weekly ecosystem review.
- `tests/test_agent_contract.py` — contract validation.

## Validation

Run `python -m unittest discover -s tests -v`. GitHub Actions runs the same checks on pushes to `main` and pull requests.
