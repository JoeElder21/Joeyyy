---
name: make-pr-easy-to-review
description: >
  Prepare a PR for review with a current description and reviewer
  guidance without changing code behavior. Use for make-pr-easy-to-review,
  tidy this PR, or annotate the diff. Does not merge, force-push, or
  rewrite history unless Joe explicitly asks. Lifecycle: shadow.
---

# Make PR easy to review (shadow)

Read `AGENTS.md` and `docs/CURSOR_TEAM_KIT_INTEGRATION.md`. APEX only.
Lifecycle is **shadow**. Default work is reviewability: description and
notes, not behavior changes.

## When to use

The PR is hard to review: stale description, mixed mechanical and logic
diffs, missing entry points, or noisy commit list. Do not use this to
merge or to "clean up" by hiding behavior changes.

## Procedure

1. Resolve the PR (`gh pr view --json title,body,headRefName,baseRefName,files,commits`).
2. Inspect diff size, paths, generated files, and the current body.
3. Name reviewability issues. Propose the plan before any mutation.
4. Safe default (no history rewrite):
   - Refresh the PR body via `gh pr edit` so TL;DR matches the diff.
   - Separate core files from generated or mechanical files.
   - Call out risk, test coverage, and rollback.
5. History rewrite or force-push is **out of the default envelope**.
   Only if Joe explicitly asked: show the plan, record
   `ORIGINAL_TREE=$(git rev-parse origin/<head>^{tree})`, and refuse to
   push if the tree changed unintentionally. Joeyyy default remains
   no rebase and no force-push.

If the PR is too large to make reviewable with notes, recommend
splitting instead of polishing around the problem.

## Hard stops

Never merge. Never hide behavior changes inside cleanup. Never bypass
hooks. Never print secrets. Never bump `mcp` to 2.x or touch relay npm.
Never promote specialists. Never cross APEX/JEOS.

## Output

- Reviewability issues found
- Description or notes changed (or the proposed split)
- Confirmation that code behavior was not intended to change
