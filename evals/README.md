# Behavioral evaluation harness

The repository's unittest suite proves specialists **cannot misbehave**. This
harness is for proving they **do the job** — the other half of the active gate in
`docs/SPECIALIST_ACCEPTANCE_TESTS.md`, which requires one controlled real mission
per material mode.

Full record: `docs/EVALUATION_HARNESS.md`.

## Where results go

Results land in the **Evaluations** folder on Joe's Drive. They are never
committed here.

That is not filing preference, it is the data boundary. Evaluation inputs and
transcripts are exactly the private material `docs/PRIVACY_AND_DATA_BOUNDARIES.md`
keeps out of a public tree, and `scripts/privacy_guard.py` would reject most real
ones outright. `evals/output/` is gitignored; Agent 007 publishes each run
directory to Drive through the approved connector. No script here holds a Drive
credential — publication is a connector action under the packet-only policy.

## Layout

| Path | What it is |
| --- | --- |
| `harness.py` | Mode inventory and metric contract. Stdlib-pure; imports without deepeval. |
| `cases/*.json` | Golden cases, one file per material mode. |
| `test_specialist_modes.py` | DeepEval suite. Not reached by `unittest discover`. |
| `run_evaluations.py` | Coverage report and runner. |
| `output/` | Run results. Gitignored; published to Drive. |

## Running it

```bash
# Inventory only — no model, no runtime, safe anywhere
python evals/run_evaluations.py --coverage

# Full run — needs the evaluation stack and a judge model
# The LOCK, not the manifest. CI installs the resolved lock and osv-scanner
# audits it with --no-resolve, so installing the floating manifest here puts a
# resolution on the workstation that nothing scanned and CI never tested.
python -m pip install -r requirements/lock-runtime-evaluation.txt
python evals/run_evaluations.py --run-id <mission-id>
```

Coverage today: **3 of 39 material modes** have a case. The 36 uncovered modes are
listed by `--coverage`, and none of them can be promoted out of `shadow` until
they have one.

## Two deliberate refusals

**Specialist dispatch is unimplemented.** `_invoke_specialist` raises
`NotImplementedError`. Wiring it to `scripts/agent_runtime.py` or
`scripts/claude_runtime.py` needs a verified model credential and a
connector-isolation decision that is not made in this repository. A stub
returning canned text would produce green evaluations that attest to nothing —
worse than no harness, because it would look like evidence.

**The runner will not fabricate a pass.** With no evaluation runtime installed,
`run_evaluations.py` exits 2 and prints the inventory. An unproven mode reads as
unproven.

## Adding a case

Copy an existing file in `cases/`. Required keys: `mode_key` (must match a mode
derived from `brains/*/agents.toml`), `title`, `mission`, `expected_artifacts`,
`expected_behaviors`, `forbidden_behaviors`, `provenance`. Optional: `metrics`,
`thresholds`, `context`, `expected_tools`, `notes`.

Keep case content as public-safe as the rest of the repository — synthetic
missions, no real project identifiers, client names, or agency correspondence. A
real controlled mission runs on the workstation against real context and
publishes only its scored result to Drive.

`metrics` are validated against the contract in `harness.py`; an unmapped metric
name is an error. Baseline metrics (`packet_validity`, `role_adherence`,
`brain_isolation`) apply to every case and do not need declaring.

Set `role_adherence` and `brain_isolation` thresholds to 1.0 where a single
failure is disqualifying rather than averageable — see the technical-QA and
weekly-reflection cases for the two shapes that warrant it.
