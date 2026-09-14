---
name: loop-on-ci
description: >
  Watch PR-attached checks with gh pr checks and iterate until required
  checks are green or a stop fires. Use when asked to loop-on-ci, watch
  CI, or babysit failures. Delegates each red set to fix-ci. Does not
  merge or print secrets. Lifecycle: shadow.
---

# Loop on CI (shadow)

Read `AGENTS.md` and `docs/CURSOR_TEAM_KIT_INTEGRATION.md`. APEX only.
Lifecycle is **shadow**. Each run is issue- or PR-triggered; this is not
continuous background operation.

`gh pr checks` is the source of truth. It includes PR-attached checks;
`gh run list` is Actions-only.

## When to use

Need to watch one open PR and repeat diagnose → fix → push → re-check
until green. Invoke `fix-ci` for each red set. For a Mission Recipe
babysit, start at `forge-ci-loop`.

## Procedure

Default budget: **5** fix-and-push iterations unless the start prompt
says otherwise. No standing schedule.

1. Resolve the PR (`gh pr view --json number,url,headRefName,isDraft,state`).
   Stop if missing, merged, or closed. Confirm
   `git branch --show-current` equals `headRefName`.
2. Snapshot `gh pr checks --json name,bucket,state,workflow,link`.
3. If checks already failed, invoke `fix-ci` on that set first.
4. If checks are pending, `gh pr checks --watch --fail-fast` is allowed.
5. After each push, re-run the JSON check snapshot. The check set can
   change. Repeat until green, `N` is exhausted, or a hard stop.

Flakes: `gh run rerun <id> --failed` once. Same failure afterward is
real. Do not keep retrying.

## Hard stops

Never merge. Never rotate or print secrets. Never bump Python `mcp` to
2.x. Never touch relay npm. Never promote specialists. Never cross
APEX/JEOS. Stop on blocked/auth/OSV-accepted-risk out of scope
(including inherited relay/#79 OSV reds).

`gh` fallback: `docs/CURSOR_TEAM_KIT_INTEGRATION.md`.

## Output

- PR URL, head SHA, iteration count
- Per-iteration failure and fix
- Terminal state: green, budget exhausted, or named hard stop
