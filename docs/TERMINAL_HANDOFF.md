# Claude Stocks Terminal — handoff (milestone 1, 2026-09-11)

Status labels follow the implementation prompt: **BUILT AND TESTED**,
**BUILT NOT VERIFIED**, **PROPOSED**, **BLOCKED**.

## Deliverables

| Deliverable | Status | Evidence |
| --- | --- | --- |
| Audit matrix with VERIFIED / INFERRED / UNAVAILABLE labels | BUILT AND TESTED | `TERMINAL_AUDIT.md`; chain and duplicate findings computed by `terminal/legacy.py` |
| Architecture and data flow tied to files | BUILT AND TESTED | `TERMINAL_ARCHITECTURE.md` |
| Document schemas (11) and a stdlib validator | BUILT AND TESTED | `terminal/schemas/`, `tests/test_terminal_schema.py` |
| Asset identity, market clock, freshness | BUILT AND TESTED | `tests/test_terminal_identity.py`, `..._clock.py`, `..._freshness.py` |
| 100-point equity scorecard with missing-data treatment | BUILT AND TESTED | `tests/test_terminal_scorecard.py` |
| Crypto rubric | PROPOSED | `TERMINAL_CRYPTO_RUBRIC_PROPOSAL.md` |
| Scenario mathematics, hurdle | BUILT AND TESTED | `tests/test_terminal_scenarios.py` |
| Outcome grading from a tradable reference | BUILT AND TESTED | `tests/test_terminal_outcomes.py` |
| Fatal-risk and release gates | BUILT AND TESTED | `tests/test_terminal_gates.py` |
| Tiered universe and bounded budget | BUILT AND TESTED | `tests/test_terminal_universe.py` |
| Run manifest, idempotency, hash chain, lock, atomic snapshot | BUILT AND TESTED | `tests/test_terminal_runs.py` |
| Two-round critic protocol | BUILT AND TESTED | `tests/test_terminal_critic.py` |
| Store adapters and write plans | BUILT AND TESTED | `tests/test_terminal_store.py` |
| Daily pipeline with six failure injections | BUILT AND TESTED | `tests/test_terminal_pipeline.py`, `tests/test_terminal_cli.py` |
| Legacy migration (capsule v43, boards, accounts, calls, run log) | BUILT AND TESTED on the synthetic page; BUILT NOT VERIFIED in the repository for the real V53 page (the clean V53 migration and `verify` were observed in the session only) | `tests/test_terminal_legacy.py` |
| Renderer with thirteen views | BUILT AND TESTED | `tests/test_terminal_render.py`; one visual check of the migrated page |
| Role definitions (10) | BUILT AND TESTED | `terminal/agents/`, `tests/test_terminal_agents.py` |
| Revamped Edition artifact with the artifact database seeded | BUILT NOT VERIFIED | published from the session; store seeded and read back through the publishing tool; the in-page store check was not observed in a viewer from this session |
| Store-backed writer lease and in-session artifact-db adapter | PROPOSED | `RunLock` is in-memory; the production lease and the Routine-side db reader/writer are designed in `TERMINAL_RUNBOOK.md` and not built |
| Cutover of the Routines and the live page | BLOCKED | needs Joe's approval on policy, schedule and prompts (`TERMINAL_MIGRATION.md`) |
| Live analyst research through the roles (real evidence, real scores) | BLOCKED | no run has been fired; the dry run uses fixture inputs |

## Where state lives

- Repository: `terminal/` (code, schemas, roles, synthetic fixture), `tests/test_terminal_*.py`, `docs/TERMINAL_*.md`.
- Real data: only in the private artifacts (the legacy page and the Revamped
  Edition with its store). No private fact is in this repository.
- Session scratchpad: the V53 readback, the migrated store directory and the
  rendered page. Ephemeral; regenerate with `migrate` from a fresh readback.

## Test results

`python -m unittest discover -s tests -p "test_terminal_*.py"`: 117 tests, 0
failures, after the independent review's findings were fixed (ledger ordering,
gate strictness, bounded outcome references, critic resolution keys, payload
escaping, no stance from the proposed crypto rubric). The full repository surface (`task validate`) was run before the
pull request; its figures are in `REPOSITORY_OVERVIEW.md`.

## Remaining tasks (in order)

1. Joe's decisions on the policy document, the crypto rubric and the schedule.
2. Screenshots for both Schwab IRAs so positions can be split.
3. Replace the fixture-driven analyst stage with the role briefs running on
   real evidence; keep the same document shapes so the tests still hold.
4. Routine prompts rewritten to the runbook sequence; shown before any change.
5. First production run into the store; observe the in-page store check.
6. Freeze the legacy page.

## Next commands

```
python -m unittest discover -s tests -p "test_terminal_*.py"
python -m terminal.cli dry-run --inputs terminal/fixtures/synthetic_inputs.json --store /tmp/run --render /tmp/run.html
python -m terminal.cli migrate --html <fresh readback>.html --store /tmp/store && python -m terminal.cli verify --store /tmp/store
python -m terminal.cli render --store /tmp/store --out /tmp/page.html
```
