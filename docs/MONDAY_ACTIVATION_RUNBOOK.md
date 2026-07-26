# Monday Activation Runbook — 2026-07-27

What Joe does Monday morning, what actually works, and what is honestly not ready.

Written 2026-07-26. Read the "What is not ready" section before relying on
anything here for client-facing or agency-facing work.

---

## The 60-second version

Open Claude Code in this repository and type:

```
Activate Agent 007. <what you need>
```

Agent 007 classifies the brain, staffs the smallest evidence-justified team,
retrieves evidence from your live connectors, delegates to specialists inside
validated packets, and integrates the result. Every controlled mission writes a
hash-chained evidence record and a value observation.

**The specialists are real and callable as of this branch.** They were not
before — they existed only as Codex TOML prompts with nothing to execute them.

---

## What changed to make this possible

| Before | Now |
| --- | --- |
| Specialists were `.codex/agents/*.toml` prompts; nothing invoked them in Claude Code | `.claude/agents/*.md` projections generated from the same canonical contracts, callable via the `Task` tool |
| Connector isolation was prose ("never call a connector directly") | Enforced by the tool list: specialists have `Read, Glob, Grep` and no connector, shell, or writer |
| No controlled-mission machinery | `runtime/mission_runner.py` brackets each mission and writes evidence |
| Section 17's 35% value threshold had no policy file | `config/value_policy.toml` + `runtime/value_meter.py` |

---

## The architecture in one paragraph

**Agent 007 holds the connectors. Specialists never do.** You talk to Agent 007.
It calls Gmail, Drive, Calendar, Todoist, GitHub, or the web, extracts the
minimum task-relevant records, and hands each specialist a PacketGuard-validated
delegation packet containing only that evidence. A specialist that cites a source
which was not in its packet fails connector isolation and its mission does not
count. This is checked mechanically in `MissionRunner.complete()`, not trusted.

---

## Monday morning, step by step

### 1. Confirm the corps loaded

```bash
python scripts/generate_claude_agents.py --check
```

Expect `OK: 11 generated agents match their canonical sources.` If it reports
stale files, run it without `--check` to regenerate.

### 2. Start a mission

Say what you need in your own words. Examples that map to registered modes:

| What you say | Brain | Specialist | Mode |
| --- | --- | --- | --- |
| "Where do my submittals stand this week?" | APEX | `apex_delivery_commander` | `delivery_control` |
| "Triage my proposal pipeline" | APEX | `apex_deal_engine` | `pipeline_triage` |
| "Normalize what came in over the weekend" | APEX | `apex_intelligence_forge` | `intake_normalization` |
| "What is realistic for me today?" | JEOS | `jeos_energy_director` | `daily_capacity` |
| "Plan my week" | JEOS | `jeos_life_architect` | `weekly_plan` |
| "Get me moving on the thing I keep avoiding" | JEOS | `jeos_momentum_engine` | `daily_activation` |

Agent 007 routes; you do not need to name the specialist.

### 3. Give a baseline the first time you run a mode

The value meter refuses to invent one. The first time you run a mode, Agent 007
will ask a single question:

> How long does this normally take you by hand?

Answer in minutes. That becomes a `joe_declared` baseline. It is recorded once;
you will not be asked again for that mode.

**Why it matters:** without it the mode reports `no_baseline` forever and can
never show measured value. Thirty seconds of your time per mode buys the entire
measurement system.

### 4. Review the output, and say if it was wrong

Whether you accepted the first answer, and how long review took, are recorded.
This is what makes the value number honest — an answer produced in 20 seconds
that costs you four minutes to check has not saved four minutes, and the meter
will say so.

---

## Seeing whether it is actually saving you time

```bash
python -c "
from runtime.value_meter import ValuePolicy, ValueLedger
from pathlib import Path
policy = ValuePolicy.load()
ledger = ValueLedger(Path('audit/value.jsonl'))
import json; print(json.dumps(ledger.report(policy), indent=2))
"
```

Verdicts you will see, and what each one means:

| Verdict | Meaning |
| --- | --- |
| `no_baseline` | You have not told it how long the task takes you. Nothing can be measured. |
| `insufficient_data` | Fewer than 5 observations. One good run proves nothing. |
| `below_threshold` | Real savings, but under the binding 35%. |
| `meets_threshold` | Net saving clears 35% across at least 5 runs with ≥70% first-pass acceptance. |
| `demote` | Under 20%. The mode costs more than it returns and should be pulled. |
| `blocked_by_incident` | A boundary violation was recorded. No value claim until reviewed. |

The arithmetic subtracts your review time, your correction time, incident time,
and amortized maintenance from the baseline. It is designed to be hard to pass.

---

## Promotion: how agents leave shadow

All ten specialists are in `shadow` and **this runbook does not change that.**
The gate in `config/specialist_corps.toml` requires one controlled real mission
per material mode — 39 modes total — plus connector-isolation evidence and
readback.

Check coverage at any time:

```bash
python -c "
from runtime.mission_runner import MissionRunner
import json; print(json.dumps(MissionRunner().promotion_status([]), indent=2))
"
```

As you use the system, evidence accumulates automatically. When an agent's modes
are all covered, the report lists it under `agents_fully_covered` and you approve
that specific promotion. **No agent promotes itself**, and my running missions
does not promote anything — that is your call on reviewed evidence, per section 12.

This is deliberately not a switch I can flip for you. A status field set to
`active` without mission evidence behind it would make every downstream claim
about the corps false.

---

## What is not ready — read this

Being straight about the gaps, because Monday is a work day and some of this
touches professional liability.

1. **All ten specialists are `shadow`.** They analyze and propose. They do not
   execute canonical writes. Agent 007 performs any mutation and reads it back.
2. **No mode has value evidence yet.** Every mode reports `no_baseline` or
   `insufficient_data` until you have run it about five times with a baseline.
   Expect roughly a week before any verdict means something.
3. **Nothing here is licensed judgment.** For permits, grading, quantities, and
   cost, output is analysis for your review. Never sign, seal, submit, or
   certify anything on an agent's say-so. Final permit or agency submission is
   an always-gated action requiring you live.
4. **Connector reach is whatever your session actually has.** If Drive, Gmail,
   Calendar, or Todoist is not authorized in the session, Agent 007 reports the
   blocker rather than pretending. It does not silently degrade.
5. **The evidence ledger is tamper-evident for history, not for the newest
   entry.** `AuditLedger.verify()` catches rewriting of records that already had
   a successor; it does not protect the most recent record, and a later append
   re-anchors onto tampered content. Recorded in `tests/test_mission_runner.py`.
6. **The JEOS Executive Chief of Staff does not exist as an agent.** Section 5
   names it as JEOS's front door, but no such identity is registered. JEOS work
   currently routes through Agent 007. This is a real gap between the
   constitution and the roster, and it needs your decision (see below).

---

## Decisions that need you

1. **JEOS front door.** Section 5 names a "JEOS Executive Chief of Staff" as
   JEOS's intake and routing agent. No such agent is registered in
   `brains/jeos/agents.toml`. Either register it (a Foundry contract plus roster
   entry) or amend section 5 to route JEOS through Agent 007, which is what
   happens today.
2. **Which modes matter first.** 39 modes is a lot of evidence to accumulate.
   Naming the six or eight you will genuinely use gets those to `active` in
   about a week instead of spreading thin across all 39.
3. **Baselines.** Any mode you can estimate now — "a delivery status pass takes
   me 45 minutes" — can go straight into `config/value_policy.toml` and start
   measuring on its first run instead of its second.

---

## Rollback

Everything in this layer is additive. `git revert` the execution-layer commit
removes the projections, harness, and meter without touching the roster,
schemas, lifecycle stages, or any specialist's status — all ten were `shadow`
before it and remain `shadow` after it.
