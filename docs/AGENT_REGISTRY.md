# Agent 007 Registry

This is the canonical index for agents governed by Agent 007. Add one entry per agent and preserve version and audit history.

## Lifecycle

`candidate` → `active` → `restricted` / `deprecated` / `retired`

An agent becomes active only after its configuration, boundaries, handoff, and validation evidence are recorded.

## Registered agents

### Agent 007 / APEX Chief of Staff

- Status: active
- Canonical native name: `apex_chief_of_staff`
- Aliases: Agent 007, 007, Chief of Staff
- Owner layer: cross-brain governance
- Purpose: coordinate APEX and JEOS, govern the agent community, integrate results, execute authorized work, and improve the ecosystem
- Triggers: `Activate Agent 007`, explicit native-agent invocation, cross-brain coordination, agent intake, ecosystem audit
- Inputs: Joe's mission, active conversation, verified APEX/JEOS memory, authorized connectors, agent files, specialist handoffs
- Outputs: integrated plan, delegated work, verified actions, brain sync, agent registry changes, error learning, audit report
- Write targets: governance records across both brains; domain writes routed to owner agents whenever available
- Boundaries: preserve brain ownership; no unsupported access claims; no silent conflict merging; platform and professional controls remain in force
- Handoff: `docs/AGENT_COMMUNITY_PROTOCOL.md`
- Validation: `tests/test_agent_contract.py`
- Version: 2.0
- Last audit: pending first scheduled audit
- Known errors: none recorded in this repository

## Candidate infrastructure and tools

External tools under evaluation for the ecosystem. These are not agents; they are infrastructure that agents would use. None may be treated as available until validated in its target environment. Source analysis: `docs/ECOSYSTEM_REPO_ANALYSIS.md` (2026-07-23).

### Civil 3D MCP connector (barbosaihan/civil3d-mcp)

- Status: candidate
- Owner layer: APEX (Civil 3D workflow automation)
- Purpose: let Claude query and edit live Civil 3D drawings through MCP meta-tools (`civil3d_query`, `civil3d_execute`, `civil3d_skills`)
- Validation gate: build on the Civil 3D workstation per `docs/CIVIL3D_MCP_BUILDOUT.md`; read-only queries on copies of project DWGs must pass before any write use
- Boundaries: write operations follow the one-designated-writer rule; production DWGs require explicit task-level instruction
- Rollback: remove the MCP server entry from Claude config and unload the plugin (no persistent state)

### Execution layer (codex-autorunner OR multica — one, not both)

- Status: candidate, pending Joe's platform pick
- Owner layer: Agent 007 governance (task dispatch for repo-based agent work)
- Purpose: run queued agent work unattended with notify-when-stuck; see `docs/EXECUTION_LAYER_TRIAL.md`
- Validation gate: bounded trial on non-production tasks (registry maintenance, doc audits) before any client-facing work

### Deferred / watch list

- kentcdodds/kody — cross-brain memory/secrets/scheduler layer; absorb-only for now, revisit next quarter
- citrolabs/ego-lite — permit-portal agent browser; blocked on Windows support, revisit on release
- max-sixty/worktrunk — install when multiple agents edit this repo concurrently
- ADN-DevTech/Civil3DSnoop — bookmark for future Civil 3D .NET development sessions

## Intake rule

Use `templates/agent-intake.md` before adding another entry. Do not treat a name mentioned in conversation as a deployed agent until its configuration and callable environment are verified.
