---
ticket_id: "tkt_trial0002b8d4f012"
agent: "codex"
done: false
---

# Run the weekly ecosystem audit checklist against this repository

## Tasks

- Follow `templates/weekly-agent-audit.md` using only evidence available in this repository (docs, tests, git history).
- Mark every item lacking evidence as unavailable — never manufacture metrics.
- Write the audit record to `trial/output/weekly-audit-dry-run.md`, ending with at most three decisions for Joe.

## Acceptance criteria

- Every checklist section is addressed; missing-evidence items say "unavailable", not a guess.
- Findings cite specific files or commits.
- At most three decisions for Joe, ordered.

## Tests

- File exists at `trial/output/weekly-audit-dry-run.md`; contains the word "unavailable" at least once (this repo has no runtime evidence yet).

## Notes

Measures instruction-following against a long structured checklist.
