# Execution Layer Trial — Fixed Task Set

The five pre-defined tasks for the execution-layer trial in `docs/EXECUTION_LAYER_TRIAL.md`. Defined before the trial starts so both candidates are scored against the same ground truth.

- **codex-autorunner (CAR):** copy `TICKET-*.md` into the CAR hub's ticket directory unchanged — the files use CAR's native frontmatter (`ticket_id`, `agent`, `done`).
- **multica:** create one issue per ticket (`multica issue create --title "<ticket title>" --assignee "<agent>"`) and paste the ticket body as the issue description. TICKET-005 becomes an Autopilot instead of an issue.

Score each run against the ticket's Acceptance criteria, per metric, not by impression. All tasks operate on the Joeyyy repo only — no client-facing or permit work.
