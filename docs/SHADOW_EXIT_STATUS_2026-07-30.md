# Shadow Exit Status — 2026-07-30

What now stands between the ten specialists and `active`, measured rather than
estimated. Produced after the runtime stack was made installable and installed
for the first time (`docs/RUNTIME_HOST_DECISION.md`).

## The gate, verbatim

`runtime/lifecycle.py::active_gate` fails a promotion unless **all** hold:

1. Every material mode has `real_mission_completed`
2. Every material mode has `boundary_behavior_verified`
3. Every material mode has `handoff_schema_valid`
4. Every material mode has `writer_lease_compliant`
5. Any mode where a mutation occurred has `readback_verified`
6. `connector_isolation_runtime_verified`
7. `evidence_source != "harness"` — gate 21
8. `joe_approved_activation`

## Measured position

```
material modes:                     39
covered by real-mission evidence:    0
agents fully covered:              0/10
ledger_trustworthy:               True
```

Every one of the ten specialists is `0/N` modes:

| Agent | Brain | Modes covered |
| --- | --- | --- |
| `apex_war_architect` | APEX | 0/3 |
| `apex_deal_engine` | APEX | 0/3 |
| `apex_delivery_commander` | APEX | 0/4 |
| `apex_intelligence_forge` | APEX | 0/5 |
| `apex_systems_blacksmith` | APEX | 0/4 |
| `jeos_life_architect` | JEOS | 0/5 |
| `jeos_momentum_engine` | JEOS | 0/3 |
| `jeos_energy_director` | JEOS | 0/3 |
| `jeos_reflection_forge` | JEOS | 0/4 |
| `jeos_lifestyle_systems_builder` | JEOS | 0/5 |

## What is now cleared

Everything mechanical. Before today the path out of shadow was blocked by
infrastructure that could not run at all; that is no longer true.

| Prerequisite | Status |
| --- | --- |
| A runtime host is chosen | Decided — `docs/RUNTIME_HOST_DECISION.md` |
| The full stack can be installed | **Yes** — lock regenerated from a real manifest, 1,053 packages, install exits 0 |
| Every declared dependency imports | **Yes** — `--require-tier all` → `installed_count: 20, missing: []` |
| The contract suite passes with the stack present | **Yes** — 1,083 tests, 0 failures |
| The mission harness works | **Yes** — `tests/test_mission_runner.py`, 50 tests, all pass |
| The lifecycle gate is trustworthy | **Yes** — the `scripts/` graph no longer carries divergent gate logic, so it can no longer promote without gates 7 and 8 |
| The evidence ledger is intact | **Yes** — `ledger_trustworthy: True` |
| The challenge-pair debates can run | **Yes** — AutoGen API split resolved; a registered pair produces a real transcript offline |

Dependency-gated tests went from **31 skipped to 6**, and then to **0** once the
AutoGen API split was resolved (§4 below). Every test in the suite now runs on
the installed stack.

## What is not cleared, and why

### 1. Thirty-nine controlled real missions — needs Joe's connectors

`runtime/mission_runner.py` is explicit that the harness does not execute the
specialist, and that **synthetic evidence is excluded from coverage**. A mission
counts only when Agent 007 pulls real evidence from live connectors, minimizes
it into the packet, delegates, and reads the typed return back.

That requires Joe's authorized Gmail / Drive / Calendar / Todoist / GitHub
sessions and his real APEX and JEOS records. It cannot be produced from this
repository, and it must not be simulated: a fabricated pass is exactly what
gates 4 and 21 exist to reject.

It also cannot usefully be produced in an ephemeral container. `audit/*.jsonl`
is gitignored by design — mission evidence is machine-local — so evidence
generated in a throwaway environment vanishes and no later promotion could cite
it.

### 2. Runtime connector-isolation evidence — needs a live mount

Gate 6 wants evidence from a real run, not from configuration. `governance` and
`filesystem` verify offline; `github`, `postgres`, `gdrive`, `civil3d`,
`terraform` and `azure` each need a credential or a workstation build, and every
`require_grant` mount starts only through a Joe-signed single-use grant.

### 3. Joe's approval — structurally reserved

Gate 8 is `joe_approved_activation`. Nothing in this repository can set it on
Joe's behalf, and the change that accompanies this record exists precisely to
guarantee that: `scripts/orchestration_graphs.py` previously could promote
`shadow → active` without it.

### 4. The challenge-pair mechanism — RESOLVED 2026-07-30

The repository had declared two incompatible AutoGen APIs:

| Module | Imported | Needed |
| --- | --- | --- |
| `runtime/autogen_orchestrator.py` | `from autogen import ...` | AutoGen **0.2** (as pinned) |
| `runtime/autogen_groupchat.py` | `from autogen import ...` | AutoGen **0.2** |
| `scripts/group_debate.py` | `from autogen_agentchat.agents import ...` | AutoGen **0.4+** |

`autogen-agentchat>=0.2.35,<0.3` provides `autogen`, never `autogen_agentchat`,
and `autogen_ext` was in no manifest at all — so `scripts/group_debate.py`, the
module `docs/RECONCILIATION_2026-07-24.md` closes build ticket 4 with, could not
run under any installation of the declared set. The registered challenge pairs
were unsatisfiable rather than dormant.

**Converged on 0.2**, the pinned line. `scripts/group_debate.py` now imports
`autogen` and builds `GroupChat`/`GroupChatManager`; `RoundRobinGroupChat`
becomes `speaker_selection_method="round_robin"` over a manifest-ordered agent
list, and `SelectorGroupChat` becomes `"auto"` selection.

Why this direction rather than moving the other two modules to 0.4: they carry
the governed, packet-validating, currently-passing path, including a custom
speaker-selection guard that *raises* when a transcript violates the manifest
order — which 0.4 has no direct equivalent for. Converging on 0.2 rewrote 179
lines of code that had never run; the alternative rewrote 454 lines that work.

Two governance rules were carried across in the process, neither of which the
0.4 version had:

- `llm_config` may not carry `tools` or `functions`. A model-side tool grant
  would route straight around `packet_only_no_direct_connectors`; a specialist's
  tool surface is its MCP mounts. Same rule the orchestrator already enforced.
- A selector chat with `llm_config=False` is refused rather than silently
  degrading to round-robin. There is no model to select with, and a fallback
  that still calls itself dynamic selection is the quiet-degradation pattern
  this repository keeps removing.

The tests now run, fully offline, using the `llm_config=False` +
`default_auto_reply` pattern already proven by
`tests/test_autogen_orchestrator.py` — no model, no network, and no replay
client from an unmanifested package. A registered APEX pair produces a real
adversarial transcript:

```
apex_chief_of_staff:     Debate: is campaign two the right focus?
apex_war_architect:      Campaign two is the highest-leverage move.
apex_intelligence_forge: Two of three cited opportunities are stale.
```

**Dependency-gated skips are now zero.** No test in the suite probes a module
absent from the installed stack.

Remaining, and deliberately not done here: AutoGen 0.2 is the legacy line, and
migrating all three modules to the maintained 0.4 API is worth doing on its own
schedule. It is a single coordinated migration — including a 0.4 replacement for
the orchestrator's speaker-order guard and adding `autogen-ext` to a manifest —
not a side effect of repairing the split.

## Honest summary

The blockers that were **infrastructural** are cleared. The blockers that
remain are **evidentiary and authorizational**, and they are load-bearing by
design: real missions on real records, a live mount, and Joe's explicit
approval. No amount of further work inside this repository can substitute for
any of the three, and the correct behavior of a system built to refuse
unearned promotion is to say so rather than to route around it.

The next action is not a code change. It is Joe running the first controlled
mission from `docs/MONDAY_ACTIVATION_RUNBOOK.md` on the workstation, against a
live connector, for one mode of one specialist.
