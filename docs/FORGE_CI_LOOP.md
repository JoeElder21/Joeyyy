# Forge CI loop — mission recipe

A **CI loop** is a public-safe, issue- or PR-triggered babysit of failing
checks on one open pull request. Forge opens or comments on a Mission
issue. The existing Claude Code Action (`.github/workflows/claude.yml`)
runs because the submitted body contains `@claude`. Claude Code (or an
Agent 007 wrapper) loads `.agents/skills/forge-ci-loop/SKILL.md`, which
orchestrates `loop-on-ci` and `fix-ci`.

Provenance, pin SHA, shared hard stops, `gh` fallback, and
shadow→active rules: [`CURSOR_TEAM_KIT_INTEGRATION.md`](CURSOR_TEAM_KIT_INTEGRATION.md).

This is **not** continuous background operation, a PacketGuard
delegation, a specialist promotion, or merge authorization. Each run is
issue- or PR-triggered. Joe merges in the GitHub UI.

## How it plugs into the mission pipeline

Option A is unchanged: one interactive Claude job. A second
`issues: [opened]` Claude workflow would race two checkouts and
double-spend `ANTHROPIC_API_KEY`. See `docs/MISSION_PACKET.md`.

1. Canon drafts the eight packet fields. Mode remains the authorized
   **brain** (`JEOS` or `APEX`). CI babysitting is almost always APEX.
2. Forge sets Recipe to **CI loop / babysit PR** on
   `.github/ISSUE_TEMPLATE/mission.yml` and replaces the start prompt
   with the recipe below (it must still contain `@claude`).
3. The existing `claude.yml` job starts. Claude reads this document,
   `docs/CURSOR_TEAM_KIT_INTEGRATION.md`, and the shadow skills.
4. The loop pushes fixes to the named PR's head. It does not merge.

A later `@claude` comment on the same issue or on the PR is the resume
path. There is no schedule and no standing watcher.

## Start-prompt recipe

Copy into the Mission form's **Claude Code start prompt**. Keep the
literal `@claude`.

```text
@claude

Read docs/FORGE_CI_LOOP.md, docs/CURSOR_TEAM_KIT_INTEGRATION.md, and
.agents/skills/forge-ci-loop/SKILL.md. Load loop-on-ci and fix-ci.
Babysit PR <number or URL> until required checks are green or a hard
stop fires. Budget: 5 fix-and-push iterations.

Follow AGENTS.md. Prefer gh pr checks as the source of truth. Apply one
minimal focused fix per iteration. Push and re-check.

Do not merge. Do not rotate, print, or commit secrets. Do not bump mcp
to 2.x. Do not touch connectors/relay (leave Dependabot #79). Do not
promote any specialist from shadow to active. Do not cross APEX/JEOS
brains. Do not add a second Claude interactive workflow.
```

## Rollback

Revert with the integration document: delete the skill directories and
both docs, restore the Recipe field and index pointers, and drop the
`claude.yml` comment. Labels `mission` and `claude` can stay.
