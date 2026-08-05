# Promotion Checklists — 2026-07-31

One checklist per specialist: what has to be true before Joe approves that
specialist's promotion out of `shadow`, and the exact loop that makes each line
true. Written so that Joe's side of activation is running catalog missions and
approving reviewed evidence — nothing here asks him to design anything.

**What this document is not.** It is not a status record and never asserts a
lifecycle stage. Coverage is measured by `MissionRunner.promotion_status()` from
the mission ledger; the checkboxes below are a worksheet for Joe's own tracking,
and a checked box that the ledger does not corroborate means nothing. Per
`docs/REPOSITORY_OVERVIEW.md` discipline, docs follow measurement — as of this
writing all ten specialists are `shadow` and no mode has a value verdict.

The gate being satisfied, from `config/specialist_corps.toml`:

> Static contracts, typed 2.1 output, one controlled real mission per material
> mode, runtime connector-isolation evidence, readback, and a versioned
> lifecycle promotion; a separate sandbox promotion is required before any
> specialist may hold its own writer lease.

Every material mode now has a prepared entry in `config/mission_catalog.toml`,
so "one controlled real mission per material mode" means: run the named catalog
entry once, for real, and review it. The static-contract and typed-output legs
of the gate are already enforced mechanically by `PacketGuard` and
`scripts/validate_specialist_corps.py` on every run.

---

## The loop that covers one mode

Repeat per mode. After the first few, this is a few minutes of Joe's attention
per mission.

1. **Declare the baseline** (first run of the mode only). Agent 007 asks how
   long the task takes by hand; answer in minutes. Recorded once per mode.
   Modes you can estimate now can go straight into `config/value_policy.toml`.
2. **Run the catalog mission.** Say the trigger phrase (or name the entry);
   Agent 007 retrieves live evidence, prepares the PacketGuard-validated
   delegation, and invokes the specialist. Real connector evidence only —
   synthetic evidence is excluded from coverage by `MissionEvidence.real_evidence`.
3. **Review the output and say whether it was right.** Review and correction
   time are part of the value arithmetic; skipping the review makes the value
   number a lie, and an unreviewed mission should not be accepted.
4. **Confirm readback.** A mission only counts once its result is read back
   (`readback_performed` is part of `qualifies_mode`). Agent 007 performs the
   readback; confirm it happened before moving on.
5. **Check coverage moved:**

   ```bash
   python -c "
   from runtime.mission_runner import MissionRunner
   import json; print(json.dumps(MissionRunner().promotion_status(), indent=2))
   "
   ```

A mode is covered only when a single mission satisfies all of: status
`completed`, typed return valid, connector isolation verified, readback
performed, value recorded, real evidence, and no errors. Anything less and the
mode stays uncovered — rerun rather than argue with the gate.

---

## The promotion decision (per specialist, after its last mode covers)

All of the following, in order. No agent promotes itself, and coverage alone
does not promote anything — the decision is Joe's, on reviewed evidence.

- [ ] `promotion_status()` lists the specialist under `agents_fully_covered`.
- [ ] The same report shows `ledger_trustworthy: true` and the specialist's
      missions appear in none of `stale_contract_evidence` or
      `unrecorded_evidence`.
- [ ] Connector-isolation evidence reviewed: no mission return cited a source
      its packet did not carry, and the specialist's projection still holds
      `Read` only with `mcp__*`, shell, writers, delegation, and web denied.
- [ ] Joe has personally reviewed at least one artifact per mode and would let
      each stand in front of a client or agency with his name on the review.
- [ ] **Versioned promotion PR**: a pull request (never a direct write to main)
      flipping `status = "shadow"` to `"active"` for this specialist in both
      `brains/<brain>/agents.toml` and `config/specialist_corps.toml`, updating
      `docs/AGENT_REGISTRY.md` and `docs/REPOSITORY_OVERVIEW.md` to the newly
      measured state, and citing the covering mission ids from the ledger.
- [ ] Joe approves and merges that PR. That merge *is* the promotion.

Two things promotion does **not** grant, by design:

- **No connectors.** `connector_stages` membership governs mounts; promotion to
  `active` does not hand the specialist a connector, and the packet-only policy
  stays in force.
- **No writer lease.** A separate sandbox promotion is required before any
  specialist holds its own lease; until then `apex_chief_of_staff` remains the
  designated executor and performs every canonical write with readback.

And one standing boundary regardless of stage: nothing a specialist produces is
licensed judgment. Sealing, certifying, submitting, or signing stays with Joe,
live, always.

---

## APEX

### `apex_war_architect` — APEX-15, class `strategy`

Responsibility: Professional outcomes, priorities, campaigns, and strategic anchors.

| Mode | Catalog entry | Required artifact | Baseline declared | Mode covered |
| --- | --- | --- | --- | --- |
| `operating_campaign` | `operating_campaign` | `campaign_map` | [ ] | [ ] |
| `career_integration` | `career_direction` | `decision_brief` | [ ] | [ ] |
| `delegation_topology` | `delegation_topology` | `delegation_topology` | [ ] | [ ] |

### `apex_deal_engine` — APEX-16, class `opportunity_momentum`

Responsibility: Pre-award opportunities, observable relationship evidence, proposals, and follow-up.

| Mode | Catalog entry | Required artifact | Baseline declared | Mode covered |
| --- | --- | --- | --- | --- |
| `pipeline_triage` | `pipeline_triage` | `opportunity_pipeline` | [ ] | [ ] |
| `reactivation` | `reactivation` | `follow_up_plan` | [ ] | [ ] |
| `proposal_control` | `proposal_control` | `proposal_checkpoint` | [ ] | [ ] |

Review attention: outbound follow-up drafts are proposals only while in
`shadow`; nothing is sent without Joe.

### `apex_delivery_commander` — APEX-17, class `execution_capacity`

Responsibility: Committed-work state, dependencies, throughput, technical QA, and quantity validation.

| Mode | Catalog entry | Required artifact | Baseline declared | Mode covered |
| --- | --- | --- | --- | --- |
| `delivery_control` | `submittal_status` | `delivery_board` | [ ] | [ ] |
| `technical_qa` | `sheet_qa_review` | `qa_risk_packet` | [ ] | [ ] |
| `quantity_delta` | `quantity_revision_delta` | `quantity_delta` | [ ] | [ ] |
| `cost_evidence` | `cost_basis_check` | `cost_evidence` | [ ] | [ ] |

Review attention: this is the professional-liability specialist. A
`technical_qa` return that reads as seal-ready confirmation, or a
`cost_evidence` return that states an allowance as a bid, fails its own
definition of done — reject it even if everything else is right.

### `apex_intelligence_forge` — APEX-18, class `intelligence_reflection`

Responsibility: Unstructured intake, source normalization, decision intelligence, and outcome learning.

| Mode | Catalog entry | Required artifact | Baseline declared | Mode covered |
| --- | --- | --- | --- | --- |
| `intake_normalization` | `weekend_intake` | `intelligence_brief` | [ ] | [ ] |
| `source_replay` | `source_replay` | `source_cursor` | [ ] | [ ] |
| `decision_brief` | `decision_brief` | `intelligence_brief` | [ ] | [ ] |
| `meeting_brief` | `meeting_brief` | `intelligence_brief` | [ ] | [ ] |
| `playbook` | `playbook` | `playbook` | [ ] | [ ] |

Five modes — the widest specialist. Review attention: facts labeled apart from
inferences, and contradictions preserved rather than smoothed.

### `apex_systems_blacksmith` — APEX-19, class `systems_automation`

Responsibility: Stable repeated-work systems, observed value, maintenance, and reversible automation.

| Mode | Catalog entry | Required artifact | Baseline declared | Mode covered |
| --- | --- | --- | --- | --- |
| `process_diagnosis` | `process_diagnosis` | `automation_assessment` | [ ] | [ ] |
| `system_design` | `system_design` | `system_design` | [ ] | [ ] |
| `shadow_validation` | `shadow_validation` | `automation_assessment` | [ ] | [ ] |
| `value_review` | `automation_value_review` | `value_review` | [ ] | [ ] |

Review attention: a design that understates its own maintenance cost is the
classic failure — the value meter will catch it later, but cheaper to catch in
review.

---

## JEOS

### `jeos_life_architect` — JEOS-14, class `strategy`

Responsibility: Personal outcomes, priorities, and daily or weekly anchors.

| Mode | Catalog entry | Required artifact | Baseline declared | Mode covered |
| --- | --- | --- | --- | --- |
| `life_direction` | `life_direction` | `life_plan` | [ ] | [ ] |
| `weekly_plan` | `weekly_plan` | `life_plan` | [ ] | [ ] |
| `monthly_review` | `monthly_review` | `monthly_life_review` | [ ] | [ ] |
| `commitment_radar` | `commitment_radar` | `commitment_radar` | [ ] | [ ] |
| `relationship_family` | `relationship_family` | `life_plan` | [ ] | [ ] |

Review attention: recommendations, never prescriptions — an output that decides
for Joe instead of recommending fails `role_adherence`.

### `jeos_momentum_engine` — JEOS-15, class `opportunity_momentum`

Responsibility: Personal next actions, activation queue, habit loops, and study repetition.

| Mode | Catalog entry | Required artifact | Baseline declared | Mode covered |
| --- | --- | --- | --- | --- |
| `daily_activation` | `daily_activation` | `activation_queue` | [ ] | [ ] |
| `habit_recovery` | `habit_recovery` | `habit_protocol` | [ ] | [ ] |
| `study_retrieval` | `study_retrieval` | `study_repetition` | [ ] | [ ] |

### `jeos_energy_director` — JEOS-16, class `execution_capacity`

Responsibility: Personal capacity constraints and optional task placement.

| Mode | Catalog entry | Required artifact | Baseline declared | Mode covered |
| --- | --- | --- | --- | --- |
| `daily_capacity` | `daily_capacity` | `capacity_map` | [ ] | [ ] |
| `weekly_load` | `weekly_load` | `weekly_load_review` | [ ] | [ ] |
| `recovery_adjustment` | `recovery_adjustment` | `schedule_adjustment` | [ ] | [ ] |

### `jeos_reflection_forge` — JEOS-17, class `intelligence_reflection`

Responsibility: Evidence-labeled lived learning, faith reflection, and growth experiments.

| Mode | Catalog entry | Required artifact | Baseline declared | Mode covered |
| --- | --- | --- | --- | --- |
| `weekly_reflection` | `weekly_reflection` | `reflection_synthesis` | [ ] | [ ] |
| `pattern_hypothesis` | `pattern_hypothesis` | `reflection_synthesis` | [ ] | [ ] |
| `faith_examen` | `faith_examen` | `faith_examen` | [ ] | [ ] |
| `growth_experiment` | `growth_experiment` | `growth_experiment` | [ ] | [ ] |

Review attention: the hardest isolation surface in the corps. A reflection may
carry professional load only at capacity level, never professional detail —
check `weekly_reflection` returns for this specifically.

### `jeos_lifestyle_systems_builder` — JEOS-18, class `systems_automation`

Responsibility: Stable recurring personal-administration systems and automation.

| Mode | Catalog entry | Required artifact | Baseline declared | Mode covered |
| --- | --- | --- | --- | --- |
| `life_admin_system` | `life_admin_system` | `life_system_design` | [ ] | [ ] |
| `renewal_maintenance` | `renewal_maintenance` | `admin_control_plan` | [ ] | [ ] |
| `finance_admin` | `finance_admin` | `admin_control_plan` | [ ] | [ ] |
| `travel_errand` | `travel_errand` | `admin_control_plan` | [ ] | [ ] |
| `system_value_review` | `lifestyle_value_review` | `system_value_review` | [ ] | [ ] |

Review attention: `finance_admin` is administrative organization only; any
return drifting toward investment or financial advice fails its definition of
done and should be rejected on sight.

---

## Sequencing suggestion, not a rule

39 modes at five accepted runs each is a long road if walked evenly. The fast
path to a first honest promotion is the specialist with the fewest modes that
Joe actually uses daily — `jeos_energy_director` or `jeos_momentum_engine`
(three modes each), or `apex_deal_engine` if professional value should come
first. Covering one specialist completely beats covering every specialist
partially: the gate is per-specialist, and the first promotion proves the whole
pipeline end to end.
