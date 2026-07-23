# Agent 007 Registry

This is the canonical cross-brain index for agents governed by Agent 007. Brain-owned metadata lives in `brains/apex/agents.toml` and `brains/jeos/agents.toml`.

## Lifecycle

`candidate` → `shadow` → `active` → `value-proven` / `restricted` / `deprecated` / `retired`

Static validation permits shadow operation. An agent becomes active only after its configuration, boundary behavior, handoff, writer-lease behavior, and one controlled real mission with readback evidence are recorded. Value-proven additionally requires observed net benefit after review, correction, maintenance, and failure burden.

## Agent 007 / APEX Chief of Staff

- Status: active
- Canonical native name: `apex_chief_of_staff`
- Aliases: Agent 007, 007, Chief of Staff
- Owner layer: cross-brain governance
- Purpose: classify ownership, coordinate APEX and JEOS, govern the community, integrate results, execute authorized work, and improve the ecosystem
- Triggers: `Activate Agent 007`, explicit native invocation, cross-brain coordination, agent intake, ecosystem audit
- Inputs: Joe's mission, active conversation, verified APEX/JEOS memory, authorized connectors, agent files, specialist handoffs
- Outputs: integrated plan, delegated work, verified actions, brain sync, registry changes, error learning, audit report
- Tools/connectors/skills: only those verified in the active runtime; never assumed from configuration
- Write targets: cross-brain governance plus owner-routed domain targets; one active writer lease per canonical brain/target/resource
- Boundaries: sole cross-brain agent; preserve brain ownership; no unsupported access claims; no silent conflict merging; platform and professional controls remain in force
- Handoff: `docs/AGENT_COMMUNITY_PROTOCOL.md` and `schemas/`
- Validation: `tests/test_agent_contract.py` and `tests/test_specialist_corps.py`
- Version: 2.1
- Last audit: v2 mirrored-corps migration, 2026-07-23
- Known errors: no v2 runtime evidence yet

## APEX specialist unit

All APEX specialists are brain-locked, read-only by default, and in shadow stage. They use only APEX evidence and communicate only inside APEX.

| Agent | ID | Mirrored class | Memory namespace | Primary proposed target | Status |
|---|---|---|---|---|---|
| `apex_war_architect` / APEX WAR ARCHITECT | APEX-15 | Strategy | `APEX::Strategy-Campaigns::apex_war_architect` | `APEX/Strategy-Campaigns` | shadow |
| `apex_deal_engine` / APEX DEAL ENGINE | APEX-16 | Opportunity / momentum | `APEX::Opportunity-Pipeline::apex_deal_engine` | `APEX/Opportunity-Pipeline` | shadow |
| `apex_delivery_commander` / APEX DELIVERY COMMANDER | APEX-17 | Execution / capacity | `APEX::Delivery-Control::apex_delivery_commander` | `APEX/Delivery-Control` | shadow |
| `apex_intelligence_forge` / APEX INTELLIGENCE FORGE | APEX-18 | Intelligence / reflection | `APEX::Intelligence-Decisions::apex_intelligence_forge` | `APEX/Intelligence-Decisions` | shadow |
| `apex_systems_blacksmith` / APEX SYSTEMS BLACKSMITH | APEX-19 | Systems / automation | `APEX::Systems-Registry::apex_systems_blacksmith` | `APEX/Systems-Registry` | shadow |

Brain-owned triggers, outputs, routes, and challenge pairs: `brains/apex/agents.toml`.

## JEOS specialist unit

All JEOS specialists are brain-locked, read-only by default, and in shadow stage. They use only JEOS evidence and communicate only inside JEOS.

| Agent | ID | Mirrored class | Memory namespace | Primary proposed target | Status |
|---|---|---|---|---|---|
| `jeos_life_architect` / JEOS LIFE ARCHITECT | JEOS-14 | Strategy | `JEOS::Life-Architecture::jeos_life_architect` | `JEOS/Life-Architecture` | shadow |
| `jeos_momentum_engine` / JEOS MOMENTUM ENGINE | JEOS-15 | Opportunity / momentum | `JEOS::Momentum-Queue::jeos_momentum_engine` | `JEOS/Momentum-Queue` | shadow |
| `jeos_energy_director` / JEOS ENERGY DIRECTOR | JEOS-16 | Execution / capacity | `JEOS::Energy-Capacity::jeos_energy_director` | `JEOS/Energy-Capacity` | shadow |
| `jeos_reflection_forge` / JEOS REFLECTION FORGE | JEOS-17 | Intelligence / reflection | `JEOS::Reflection-Ledger::jeos_reflection_forge` | `JEOS/Reflection-Ledger` | shadow |
| `jeos_lifestyle_systems_builder` / JEOS LIFESTYLE SYSTEMS BUILDER | JEOS-18 | Systems / automation | `JEOS::Lifestyle-Systems-Registry::jeos_lifestyle_systems_builder` | `JEOS/Lifestyle-Systems-Registry` | shadow |

Brain-owned triggers, outputs, routes, and challenge pairs: `brains/jeos/agents.toml`.

## Shared specialist contract

- Inputs: a schema-valid, brain-matched delegation packet and only its allowed evidence; direct invocation is contained to `direct_read_only`
- Outputs: a schema-valid handoff with evidence, assumptions, challenges, proposed writes, validation, and next handoff
- Tools/connectors/skills: inherited only when verified in the active runtime and permitted by the owner-brain packet
- Write behavior: exact per-agent target arrays live in the manifests; proposed mutations only while shadow; the named writer lease controls one resource mutation
- Communication: same-brain asks, challenges, and handoffs only; Agent 007 is the sole bridge
- Validation: `scripts/packet_guard.py` enforces relational packet rules; `schemas/mutation_result.schema.json` proves readback and rollback
- Privacy: runtime private evidence is never committed to this public repository
- Version: 2.0.0
- Last audit: static migration validation pending
- Known errors: none observed; no v2 controlled mission has run

## Retired callable roster and capability lineage

The v1 agents were shadow-stage definitions. Their native TOMLs are removed from `.codex/agents/` to prevent duplicate routing; Git history at `4465ee9dd728f9ab0a8a9d13791f1f65523a4b3c` is the rollback point.

| Retired agent | Replacement capability owner |
|---|---|
| `apex_grademaster` | `apex_delivery_commander` |
| `apex_countwise` | `apex_delivery_commander`, `apex_intelligence_forge` |
| `apex_signalkeeper` | `apex_intelligence_forge`, `apex_delivery_commander`, `apex_deal_engine` |
| `apex_ascent_90` | `apex_war_architect`, `apex_intelligence_forge` |
| `apex_forgewright` | `apex_systems_blacksmith` |
| APEX RAINMAKER bench concept | `apex_deal_engine` |
| `jeos_examiner` | `jeos_momentum_engine` |
| `jeos_tempo` | `jeos_energy_director` |
| `jeos_shepherd` | `jeos_reflection_forge` |
| `jeos_hearthkeeper` | `jeos_life_architect`, `jeos_momentum_engine` |
| `jeos_lifewright` | `jeos_lifestyle_systems_builder` |

See `docs/ROSTER_MIGRATION_2026-07-23.md` for the reversible migration record.

## Intake rule

Use `templates/agent-intake.md` before adding or materially changing an agent. A name in conversation is not a deployed agent until its configuration, owner brain, namespace, targets, handoff, runtime access, tests, and controlled mission are verified.
