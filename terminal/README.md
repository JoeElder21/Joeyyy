# terminal

The Claude Stocks Terminal research-workflow package: stdlib-only Python 3.11,
no broker, no wallet, no credential.

| Module | Purpose |
| --- | --- |
| `schema.py` | JSON Schema subset validator; `schemas/*.schema.json` |
| `identity.py` | contract-first crypto and exchange-qualified equity ids |
| `clock.py` | America/New_York, NYSE calendar, DST drift, starts-vs-ready |
| `freshness.py` | per-field freshness, board LIVE / STALE / DEGRADED |
| `scorecard.py` | adopted 100-point equity rubric; proposed crypto rubric |
| `scenarios.py` | total return, probability-weighted return, hurdle |
| `outcomes.py` | grading from the next open against the benchmark |
| `gates.py` | fatal-risk exclusion and release gates |
| `universe.py` | tiers T1–T4 and the bounded research budget |
| `runs.py` | manifests, idempotency keys, hash chain, lock, snapshot |
| `critic.py` | two-round challenge protocol |
| `store.py` | memory and JSON-directory stores, write plans for the artifact db |
| `pipeline.py` | the daily run, stages 1–9, six failure injections |
| `legacy.py` | migration of the legacy page (capsule v43) |
| `render.py` | the thirteen-view page |
| `cli.py` | `dry-run`, `migrate`, `render`, `verify`, `write-plan` |
| `agents/` | ten bounded role definitions |
| `fixtures/` | synthetic inputs (every figure invented) |

Documentation: `docs/TERMINAL_AUDIT.md`, `docs/TERMINAL_ARCHITECTURE.md`,
`docs/TERMINAL_RUNBOOK.md`, `docs/TERMINAL_MIGRATION.md`,
`docs/TERMINAL_HANDOFF.md`, `docs/TERMINAL_CRYPTO_RUBRIC_PROPOSAL.md`.
