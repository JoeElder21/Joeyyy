---
ticket_id: "tkt_trial0003c9e50123"
agent: "codex"
done: false
---

# Propose one absorbed-pattern merge as a reviewable diff

## Tasks

- Read `docs/ABSORBED_PATTERNS.md` and pick exactly one pattern marked *candidate merge*.
- Draft the smallest edit that merges it into its named target doc, preserving the target's existing style and rules.
- Write the proposal to `trial/output/pattern-merge-proposal.md` as: pattern name, target file and section, unified diff, and a two-sentence rationale. Do not modify the target doc itself.

## Acceptance criteria

- Exactly one pattern; the diff applies cleanly to the current target file.
- The merged text contradicts no existing rule in the target (state this check was performed and how).
- Rationale names the observed need, per the capability-absorption protocol.

## Tests

- File exists at `trial/output/pattern-merge-proposal.md` and contains a fenced diff block.

## Notes

Measures judgment on minimal, compatible governance changes.
