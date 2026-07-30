# ADK Samples Absorption — 2026-07-24

Capability-absorption record for `google/adk-samples`, run on the five samples Joe named. Each sample was deep-read from its **actual source** (agent wiring, sub-agent prompts, callbacks, eval configs) in a local clone, then every proposed pattern was checked by an independent adversarial reviewer against this repository's already-built runtime.

**Result: 17 patterns proposed, 8 dropped as already-built or unsupported by the source, 9 absorbed.** Two of the nine were code defects in this repository's own observability layer and were fixed in the same pass.

## Why the drop rate matters

The verification pass is the reason this record is short. Eight proposals died on contact with the existing build, among them: overall-verdict-separate-from-criteria (the handoff contract already carries `criterion_validation` plus a status), declared-type-is-a-hint (already covered by evidence `source_type` validation), bidirectional dependency edges (redundant with the existing writer-lease and packet checks), paired start/close records with duration, and named-aggregation-per-scorecard-column (both already satisfied by `MissionTracer` + `weekly_review`). Recording a pattern this repository already implements would inflate the absorption log and hide the genuinely new material.

## Absorbed — recorded in `docs/ABSORBED_PATTERNS.md`

| Sample | Pattern | Section |
| --- | --- | --- |
| llm-auditor | Claim-level verdicts from a closed five-value set, anchored to a span | 3 — error learning |
| llm-auditor | Verdict-bounded repair with a no-new-claims termination rule | 3 — error learning |
| deep-search | Typed sufficiency verdict, stop decision made outside the evaluator | 1 — delegation |
| academic-research | Declared retrieval target per bucket with a reformulation ladder | 1 — delegation |
| high-volume-document-analyzer | Read-coverage contract on every batch document read | 3 — error learning |
| sdlc-task-planner | Branch-chained task ordering | 1 — delegation |
| sdlc-task-planner | Task-size ceiling enforced before dispatch | 1 — delegation |
| agent-observability-bq | Correlation and brain keys on every telemetry record | 3 — **implemented** |
| agent-observability-bq | Weekly review reads the durable store, not the live process | 3 — **implemented** |

## Two real defects found in this repository, and fixed

The observability sample's value was not a new idea — it was exposing two holes in `scripts/observability.py` as shipped:

1. **The weekly review could not see history.** `weekly_review()` read the in-process `InMemorySpanExporter`, so a review spanning a week of separate runs aggregated to *nothing* — the module existed to replace narrative reconstruction and would have forced it. Fixed: every span now mirrors to the hash-chained `AuditLedger` as it closes, and `weekly_review(since, until)` reads that ledger over a stated window, reports the window with every count, and reports an empty window as empty rather than as zeros. A test proves two separate tracer instances aggregate through one shared ledger.
2. **The APEX/JEOS scorecard rows had no evidence.** `owner_brain` was validated at admission but never recorded, so the weekly audit's per-brain rows could not be filled from telemetry at all. Fixed: `MissionTracer._keys` carries mission, resource, delegation, agent, brain, and parent id on the span, and `agent_runtime.py` writes the identical key set into the ledger — so a span and its ledger entry match each other and both group back to the mission. `weekly_review` now returns `by_brain` counts.

Keys carry identifiers only, never packet content, per the error-learning rules.

## Not absorbed, deliberately

- **No sample code is vendored.** The clone lives in the session scratchpad and is disposable; the durable artifacts are these records.
- **The ADK framework itself** (`google/adk-python`) was not adopted. This repository's runtime already spans openai-agents, the Anthropic SDK, MCP, LangGraph, AutoGen, crewAI, and Prefect; a seventh agent framework needs a demonstrated gap, not a sample library's endorsement. It stays a roadmap candidate under normal intake if Joe wants it.
- **Sample-specific prompts and identities** were not copied, per the absorption protocol.

## Rollback

This record is additive. Rolling back the absorption means deleting this file and the nine entries in `docs/ABSORBED_PATTERNS.md`; the two observability fixes are ordinary code changes reverted with their commit.
