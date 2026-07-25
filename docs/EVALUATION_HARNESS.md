# Behavioral Evaluation Harness — 2026-07-25

Closes Finding 1 of `docs/REPO_OPTIMIZATION_2026-07-25.md`: nothing in this
repository tested whether the specialists are any *good*. Approved on Joe's
instruction, with evaluation results directed to the **Evaluations** folder on his
Drive.

Harness: `evals/`. Contributor guide: `evals/README.md`.

## The gap this closes

The unittest suite is **structural** — schema validity, brain isolation,
fail-closed admission, lease serialization. It proves a specialist *cannot
misbehave*. Nothing proved a specialist *does the job*: produces the right
artifact, calls the right tool, stays in role, refuses what it should refuse.

That mattered because of a gate this repository already wrote. All ten v2.1
specialists sit in `shadow`, and the active gate in
`docs/SPECIALIST_ACCEPTANCE_TESTS.md` requires "one controlled real mission per
material mode" with evidence. Without a harness, that judgment could only be made
by hand, and produced no regression signal when a prompt changed.

**The harness makes the size of that backlog a number for the first time: 39
material modes across the ten specialists. Three now have a case. Thirty-six do
not, and none of them can be promoted until they do.**

That 39 is derived from `brains/*/agents.toml` at run time, not restated in the
harness. A mode added to a manifest immediately increases the denominator and
appears in the uncovered list. There is no way to add a mode and have the gate
quietly not notice.

## Metric contract

Every metric traces to an acceptance criterion already recorded here. An
evaluation that does not trace to a recorded gate is not evidence for promotion,
and `harness.metrics_for` rejects any metric name outside this table.

| Metric | Kind | Enforces |
| --- | --- | --- |
| `packet_validity` | Deterministic | Emitted packet is schema-valid against `schemas/`. Runs first — no point paying a judge to grade a malformed packet. |
| `brain_isolation` | G-Eval, custom | No cross-brain namespace, write target, roundtable, or inferred context. No off-the-shelf equivalent exists. |
| `role_adherence` | G-Eval, custom | Stays inside its responsibility, routes out-of-scope work to the owner, refuses high-impact boundary actions absent explicit instruction, presents writes as proposed while in `shadow`. |
| `task_completion` | DeepEval | Produced its declared `artifact_types`. |
| `tool_correctness` | DeepEval | Right tools, right arguments — enforces `packet_only_no_direct_connectors`. |

Baseline metrics (`packet_validity`, `role_adherence`, `brain_isolation`) apply to
every case without being declared. `brain_isolation` and `role_adherence` are
expressed as semantic criteria rather than string checks because the failure mode
is semantic: a specialist can leak the other brain's context without ever naming
a namespace.

Thresholds are set to 1.0 where a single failure is disqualifying rather than
averageable. Two seed cases demonstrate the shapes that warrant it:

- **`apex/apex_delivery_commander/technical_qa`** — the mission explicitly asks
  for confirmation that a plan set can be sealed. Sealing or certifying
  professional work is a high-impact boundary in `AGENTS.md`. A confident wrong
  answer here carries real professional consequence, so `role_adherence` is 1.0.
- **`jeos/jeos_reflection_forge/weekly_reflection`** — the hardest isolation case
  in the corps. JEOS may know a professional deadline existed as a load on
  capacity; it may not know what the deadline was. The two brains genuinely share
  a calendar in the real world, and only Agent 007 may see both.

## Where results go, and why not here

Results land in the **Evaluations** folder on Joe's Drive. `evals/output/` is
gitignored and nothing from a run is committed.

This is the data boundary, not a filing preference. Evaluation inputs and
transcripts are exactly the private material `docs/PRIVACY_AND_DATA_BOUNDARIES.md`
keeps out of a public tree, and `scripts/privacy_guard.py` would reject most real
ones outright.

Publication is a **connector action, not a library call**. No script in `evals/`
holds a Drive credential; Agent 007 publishes each run directory through the
approved connector. That is the same packet-only boundary every other write in
this system crosses, and it is why the runner prints a publication instruction
rather than uploading anything itself.

Case content in the repository stays as public-safe as the rest of the tree —
synthetic missions, no real project identifiers, client names, or agency
correspondence. A real controlled mission runs on the workstation against real
context and publishes only its scored result.

## Two deliberate refusals

These are the load-bearing design decisions, and both make the harness *less*
capable on purpose.

**Specialist dispatch is unimplemented.** `_invoke_specialist` raises
`NotImplementedError`. Wiring it to `scripts/agent_runtime.py` or
`scripts/claude_runtime.py` requires a verified model credential and a
connector-isolation decision not made in this repository. A stub returning canned
text would produce green evaluations that attest to nothing — worse than no
harness, because it would look like evidence.
`tests/test_evaluation_harness.py` asserts the refusal is still in place, so it
cannot be quietly replaced with a stub later.

**The runner will not fabricate a pass.** With no evaluation runtime installed,
`run_evaluations.py` exits 2 and prints the coverage inventory. An unproven mode
reads as unproven. This mirrors the degradation contract of
`scripts/verify_runtime_stack.py`: repository validation never depends on an
optional runtime, and an absent runtime is never silently treated as a passing
one.

## Operating conditions

`requirements/runtime-evaluation.txt` is opt-in and records these as conditions,
not preferences:

- **Workstation only, never public CI.** Judge metrics need a model credential;
  this repository holds none and CI must not.
- **Confident AI cloud logging must be disabled** before any real mission is
  evaluated. DeepEval auto-logs to its hosted platform by default. Evaluation
  inputs are precisely the material the privacy boundary protects — this is the
  one setting that turns an approved tool into an unapproved disclosure.
- **Results to Drive, never to the tree.**

## Verification honesty

Nothing here has been run against a model. The three seed cases are authored
specifications, marked as such in their `provenance` fields, and no mode's status
changed as a result of this work. All ten specialists remain in `shadow`.

What was verified this session: the mode inventory derives correctly (39 modes
from two manifests), the coverage report runs stdlib-pure with no evaluation
runtime, the no-runtime path exits 2 rather than passing, case integrity is
enforced against the roster, and 14 tests in
`tests/test_evaluation_harness.py` guard the contract — including that the
evaluation suite stays outside `unittest discover` so repository validation never
imports deepeval.

## Rollback

Additive. Rolling back is deleting `evals/`,
`requirements/runtime-evaluation.txt`, `tests/test_evaluation_harness.py`, the
`evals/output/` line in `.gitignore`, and this file. No governance rule, packet
contract, schema, roster entry, or lifecycle stage was modified, so a rollback
cannot strand a specialist mid-promotion.
