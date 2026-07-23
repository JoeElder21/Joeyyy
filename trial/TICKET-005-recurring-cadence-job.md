---
ticket_id: "tkt_trial0005e1072345"
agent: "codex"
done: false
---

# Recurring cadence job: repository hygiene sweep

## Tasks

- Run a repository hygiene sweep: `python -m unittest discover -s tests`, `python scripts/privacy_guard.py`, `python scripts/validate_specialist_corps.py`.
- Append one dated status line (pass/fail per check, nothing else) to `trial/output/cadence-log.md`.

## Acceptance criteria

- All three checks executed and reported honestly; a failure is reported as a failure, never retried into silence.
- Exactly one new line per run; prior lines untouched (append-only).

## Tests

- `trial/output/cadence-log.md` gains exactly one line per firing, ISO-dated.

## Notes

Recurrence test. On multica: create as an Autopilot (`--mode create_issue`, cron `0 7 * * 1-5`, timezone `America/New_York`, concurrency policy `skip`) rather than a one-shot issue. On CAR: re-queue via external cron; note in scoring that CAR has no native scheduler — this asymmetry is part of the decision data.
