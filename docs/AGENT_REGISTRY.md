# Agent 007 Registry

This is the canonical index for agents governed by Agent 007. Add one entry per agent and preserve version and audit history.

## Lifecycle

`candidate` → `shadow` → `active` → `value-proven` / `restricted` / `deprecated` / `retired`

Static validation permits shadow operation. An agent becomes active only after its configuration, boundaries, handoff, and one controlled real mission with readback evidence are recorded. Value-proven status additionally requires observed net benefit after review, correction, and maintenance burden.

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

## APEX specialist unit

All APEX specialists are brain-locked, read-only by default, and currently in shadow stage. They may exchange task-relevant challenges only within APEX. Agent 007 or an existing APEX owner remains the designated writer.

| Agent | Roster ID | Specialty | Primary challenge |
|---|---|---|---|
| `apex_grademaster` / GRADEMASTER | APEX-10 | Terrain, grading, drainage, and accessibility QA | COUNTWISE |
| `apex_countwise` / COUNTWISE | APEX-11 | Reproducible quantities, cost evidence, and revision cascades | GRADEMASTER |
| `apex_signalkeeper` / SIGNALKEEPER | APEX-12 | Project intake, change propagation, and register-feed mutation packets | GRADEMASTER and COUNTWISE |
| `apex_ascent_90` / ASCENT-90 | APEX-13 | Professional integration and career-evidence stewardship | FORGEWRIGHT |
| `apex_forgewright` / FORGEWRIGHT | APEX-14 | Professional systems and automation design | ASCENT-90 |

Configuration files live in `.codex/agents/`. Acceptance gates are defined in `docs/SPECIALIST_ACCEPTANCE_TESTS.md`.

## JEOS specialist unit

All JEOS specialists are brain-locked, read-only by default, and currently in shadow stage. They may exchange task-relevant challenges only within JEOS. Agent 007 or an existing JEOS owner remains the designated writer.

| Agent | Roster ID | Specialty | Primary challenge |
|---|---|---|---|
| `jeos_examiner` / EXAMINER | JEOS-09 | LARE retrieval practice and evidence-based readiness | TEMPO |
| `jeos_tempo` / TEMPO | JEOS-10 | Capacity, cadence, overload, and consistency governance | EXAMINER and LIFEWRIGHT |
| `jeos_shepherd` / SHEPHERD | JEOS-11 | Sourced faith formation and concise examen | HEARTHKEEPER |
| `jeos_hearthkeeper` / HEARTHKEEPER | JEOS-12 | Confirmed relationship commitments and family logistics | SHEPHERD and TEMPO |
| `jeos_lifewright` / LIFEWRIGHT | JEOS-13 | Personal systems and automation design | TEMPO |

Configuration files live in `.codex/agents/`. Acceptance gates are defined in `docs/SPECIALIST_ACCEPTANCE_TESTS.md`.

## Dormant bench

### RAINMAKER

- Owner brain: APEX only
- Status: dormant
- Purpose: on-demand side-practice stewardship
- Decision: preserve the concept without a native active file. Current Drive evidence shows that project-change intake has greater recurring load and broader applicability, so SIGNALKEEPER occupies the fifth core APEX seat.
- Reactivation gate: repeated, measurable side-practice demand that exceeds the value of a current core seat or justifies a sixth specialist.

## Intake rule

Use `templates/agent-intake.md` before adding another entry. Do not treat a name mentioned in conversation as a deployed agent until its configuration and callable environment are verified.
