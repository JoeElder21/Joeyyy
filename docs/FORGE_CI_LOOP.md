# Forge CI loop — mission recipe

A **CI loop** is a public-safe, issue- or PR-triggered babysit of failing
checks on one open pull request. Forge (the human repo/CI operator) opens
or comments on a Mission issue. The existing Claude Code Action
(`.github/workflows/claude.yml`) runs because the submitted body contains
`@claude`. Claude Code (or an Agent 007 wrapper) loads
`.agents/skills/forge-ci-loop/SKILL.md` and iterates until green or a
hard stop.

This is **not** continuous background operation, a PacketGuard
delegation, a specialist promotion, or merge authorization. Each run ends
when the skill's stop conditions fire. Joe merges in the GitHub UI.

## Provenance and intake

| Item | Verified intake state |
| --- | --- |
| Upstream | `https://github.com/cursor/plugins` — `cursor-team-kit` skills `loop-on-ci`, `fix-ci`, plus compound-engineering `ce-babysit-pr` as a watch-until-ready *pattern* |
| Pin fetched | `5bf2b1544db739998121a306340631963c2ff3de` (resolved `cursor/plugins` `main` on 2026-09-14) |
| Skills last touched | `loop-on-ci` / `fix-ci` last changed in `bca612957941f8bad424d1856e7f46226a122d60` (2026-04-30); content at the pin matches that revision |
| License | MIT — Copyright (c) 2026 Cursor — `cursor-team-kit/LICENSE` at the pin |
| What was absorbed | The check-source (`gh pr checks`), fail-fast watch, one-cause-per-fix, and "never merge as part of babysitting" rules |
| What was not copied | Upstream skill text, bundled scripts, watch-loop helpers, merge-ready settle protocol, managed-stack rebase, or any executable |

Upstream was treated as untrusted input (AGENTS.md section 15). The local
skill is rewritten under Joeyyy governance: APEX-only, `@claude` Option A
reuse, hard stops for secrets / `mcp` 2.x / relay #79 / specialist
lifecycle / brain lock. No binary was vendored.

MIT requires the copyright and permission notice to accompany substantial
portions. This change rewrites the procedure rather than pasting those
skills, so the notice is recorded here instead of a second LICENSE file.
The upstream MIT text at the pin begins: "Copyright (c) 2026 Cursor" and
grants use subject to including that notice with substantial portions.

## How it plugs into the mission pipeline

Option A is unchanged: one interactive Claude job. A second
`issues: [opened]` Claude workflow would race two checkouts and
double-spend `ANTHROPIC_API_KEY`. See `docs/MISSION_PACKET.md`.

1. Canon drafts the eight packet fields. Mode remains the authorized
   **brain** (`JEOS` or `APEX`). CI babysitting is almost always APEX.
2. Forge sets Recipe to **CI loop / babysit PR** on
   `.github/ISSUE_TEMPLATE/mission.yml` and replaces the start prompt
   with the recipe below (it must still contain `@claude`).
3. The existing `claude.yml` job starts. Claude reads
   `.agents/skills/forge-ci-loop/SKILL.md` and this document.
4. The loop pushes fixes to the named PR's head. It does not merge.

A later `@claude` comment on the same issue or on the PR is the resume
path. There is no schedule and no standing watcher.

## Start-prompt recipe

Copy into the Mission form's **Claude Code start prompt**. Keep the
literal `@claude`.

```text
@claude

Read docs/FORGE_CI_LOOP.md and .agents/skills/forge-ci-loop/SKILL.md.
Babysit PR <number or URL> until required checks are green or a hard
stop fires. Budget: 5 fix-and-push iterations.

Follow AGENTS.md. Prefer gh pr checks as the source of truth. Apply one
minimal focused fix per iteration. Push and re-check.

Do not merge. Do not rotate or commit secrets. Do not bump mcp to 2.x.
Do not touch connectors/relay (leave Dependabot #79). Do not promote
any specialist from shadow to active. Do not cross APEX/JEOS brains.
Do not add a second Claude interactive workflow.
```

## Hard stops (summary)

The skill is the contract. In short: never merge; never rotate secrets;
never bump `mcp` to 2.x; never touch relay npm; never promote
specialists; never cross brains; never commit credentials; stop on
blocked/auth/secret/OSV-accepted-risk that is out of scope (including
inherited relay/#79 OSV reds).

## `gh` fallback

Prefer `gh`. If it is missing or unauthenticated, the skill falls back to
an already-authorized GitHub MCP read, then to `curl` with an
environment token that is already present (never printed), then to the
Actions UI. If none of those can read checks and failed logs, the run
stops as blocked/auth.

## Rollback

1. Revert this change set (skill, this document, mission-form Recipe,
   `claude.yml` comment, README / docs index / CONTRIBUTING / CHANGELOG
   pointers, and the hygiene tests that assert them).
2. Close any in-flight Mission issue that selected CI loop without
   merging its PR.
3. No schedule, secret, App, or specialist lifecycle is created by this
   change, so none needs demotion.

Labels `mission` and `claude` can stay; they do not change runtime
behavior.
