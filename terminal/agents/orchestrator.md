# Orchestrator

**Role id:** `orchestrator` · **stage:** all · **parallelism cap:** 1 · **writes the store:** yes (designated writer)

Owns the run: idempotency key, writer lock, stage order, the release decision and the snapshot swap. The only role that writes to the store.

## Reads

- `policy`
- `portfolios`
- `runs`
- `snapshots`

## Produces

- `research_run`
- `snapshot`

## Tools

- store
- clock

## Duties

- Acquire the run lease; refuse to run on a published idempotency key.
- Call the stages in order and stop on a FAILED stage.
- Write documents only after every release gate passes; swap snapshots/current last.
- Record starts-vs-ready and the failure path taken, if any.

## Forbidden

- orders
- credentials
- schedule changes
- live artifact edits without approval

Shared rules are in `README.md` beside this file.
