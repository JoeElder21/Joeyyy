---
name: forge-ci-loop
description: >
  Thin Mission-mode orchestrator: load loop-on-ci and fix-ci to babysit
  one open PR until required checks are green or a hard stop fires. Use
  when Forge selects Recipe CI loop / babysit PR. Does not merge,
  rotate secrets, or promote specialists. Lifecycle: shadow.
---

# Forge CI loop (shadow orchestrator)

Read `AGENTS.md`, `docs/FORGE_CI_LOOP.md`, and
`docs/CURSOR_TEAM_KIT_INTEGRATION.md`. APEX only. Lifecycle is
**shadow**. This file does not re-implement CI diagnosis.

## When to use

Forge opened a Mission issue with Recipe **CI loop / babysit PR**, or
Joe asked to babysit a mission / Dependabot-supersede / Cloud Agent PR
until green.

## Procedure

1. Identify the PR from the issue or `gh pr view`.
2. Load `.agents/skills/loop-on-ci/SKILL.md` and follow it.
3. When checks are red, load `.agents/skills/fix-ci/SKILL.md` for that
   set, then return to the loop.
4. Optional reads, not required for green: `get-pr-comments` if review
   text would change the fix; `make-pr-easy-to-review` only if Joe
   asked to tidy the description after CI is green.
5. Stop on green, after `N` iterations (default 5), or a hard stop in
   the leaf skill / integration doc.

Do not merge. Do not add a second Claude interactive workflow. Do not
claim continuous background operation.

## Output

Whatever `loop-on-ci` returns, plus residuals Joe still owns (merge,
secrets, #79, promotion).
