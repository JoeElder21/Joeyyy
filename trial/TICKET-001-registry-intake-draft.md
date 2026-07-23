---
ticket_id: "tkt_trial0001a7c3e901"
agent: "codex"
done: false
---

# Draft a candidate registry entry for the worktrunk tool

## Tasks

- Read `templates/agent-intake.md`, `docs/AGENT_REGISTRY.md`, and the worktrunk row in `docs/ECOSYSTEM_REPO_ANALYSIS.md`.
- Draft a complete intake form for `max-sixty/worktrunk` as candidate infrastructure (it is a tool, not an agent — adapt the identity and capability sections accordingly).
- Write the draft to `trial/output/worktrunk-intake-draft.md`. Do not modify `docs/AGENT_REGISTRY.md`.

## Acceptance criteria

- Every intake-form section is present and filled or explicitly marked not-applicable with a reason.
- Status is `candidate`; the validation section names a concrete, runnable gate.
- No invented facts: every claim about worktrunk traces to `docs/ECOSYSTEM_REPO_ANALYSIS.md` or the upstream repo.

## Tests

- File exists at `trial/output/worktrunk-intake-draft.md` and renders as valid markdown.

## Notes

Real backlog work; measures unattended completion quality on a docs task.
