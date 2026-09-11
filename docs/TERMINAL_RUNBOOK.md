# Claude Stocks Terminal — runbook

## Commands

```
python -m terminal.cli dry-run --inputs terminal/fixtures/synthetic_inputs.json --store /tmp/run --render /tmp/run.html
python -m terminal.cli dry-run --inputs ... --store /tmp/run-x --inject stale-prices   # or missing-evidence, lock-held,
                                                                                      # duplicate-run, chain-break, critic-block
python -m terminal.cli migrate --html <legacy page>.html --store /tmp/store --now 2026-09-11T10:45:00Z
python -m terminal.cli verify  --store /tmp/store
python -m terminal.cli render  --store /tmp/store --out /tmp/page.html
python -m terminal.cli write-plan --store /tmp/store --out /tmp/plan.json
python -m unittest discover -s tests -p "test_terminal_*.py"
```

Exit codes: `dry-run` returns 0 on `PUBLISHED` or `SKIPPED`, 2 on `BLOCKED`;
`verify` returns 1 on any schema error, hash mismatch or chain break.

## A production run, step by step

1. The Routine fires and a fresh session starts. It reads `policy/current`
   and `snapshots/current` from the store (through the publishing tool's
   `read_db`) before doing anything else.
2. It computes the idempotency key for the ET date (`daily:YYYY-MM-DD`). If
   the key is already published, the run stops with `SKIPPED` and says so.
3. It acquires the lease on `runs/lock` (`acquire({holder, ttlMs})`). Busy is a
   normal outcome: stop, do not retry in a loop.
4. It executes the stages in `TERMINAL_ARCHITECTURE.md`. Analyst roles return
   documents; nothing is written until the release gates pass.
5. It writes documents in batches of at most 50, then swaps
   `snapshots/current` in one write, then renders and republishes the page with
   `url`, `file_path` and a label of at most 60 characters. Never `force`.
   Never pass capabilities on a republish.
6. It records `starts_vs_ready` and the failure path taken, if any, in the run
   document and on the Today view.

## Failure diagnosis order

1. `History / as-built`: is there a run document for today's key, and what is
   its status? `SKIPPED` means a duplicate firing; `BLOCKED` names the gate.
2. `Sources / health`: which board is `STALE` or `DEGRADED`, what the store mode
   is, and whether the chain holds.
3. `python -m terminal.cli verify` on a store directory exported from the
   database: schema errors and hash mismatches are listed per document.
4. Only then the Routine's own session log.

## Republish rules for the live page

- Build on the newest readback; never on a cached copy.
- Never change an existing table's column order or count.
- Negative numbers print with U+2212.
- Balances come from screenshots; "not available" is written when a number is
  not available.

## Always-gated actions (Joe live)

Creating, editing or deleting a scheduled task; changing the live page's
schedule or prompts; migrating the production store; enabling a paid service;
widening data access. This runbook proposes those changes; it never performs
them.
