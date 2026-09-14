# cursor-team-kit skills — intake and lifecycle

Four Cursor Team Kit skills are absorbed here as **separate shadow
skills**, plus a thin Mission orchestrator. They are capabilities under
Agent 007 / Forge, not new identities and not PacketGuard specialists.

This is **not** continuous background operation. Each run is issue- or
PR-triggered. Green is not merge authorization. Joe merges in the UI.

## Provenance and intake

| Item | Verified intake state |
| --- | --- |
| Upstream | `https://github.com/cursor/plugins` — `cursor-team-kit/` |
| Pin fetched | `5bf2b1544db739998121a306340631963c2ff3de` (resolved `main` on 2026-09-14) |
| Skills last touched | `loop-on-ci` / `fix-ci` last changed in `bca612957941f8bad424d1856e7f46226a122d60` (2026-04-30); content at the pin matches that revision |
| License | MIT — Copyright (c) 2026 Cursor — `cursor-team-kit/LICENSE` at the pin |
| What was absorbed | Check-source (`gh pr checks`), fail-fast watch, one-cause-per-fix, comment summary, reviewability-without-behavior-change |
| What was not copied | Upstream skill text wholesale, bundled scripts, watch-loop helpers, merge-ready settle, managed-stack rebase, `review-and-ship` auto-merge posture, or any executable |

Upstream was untrusted input (AGENTS.md section 15). Local skills are
rewritten for `gh` plus existing Joeyyy wrappers. Privacy guard and
Agent 007 rules win over upstream text.

MIT requires the copyright and permission notice to accompany
substantial portions. These files rewrite the procedures rather than
paste the upstream skills, so the notice is recorded here instead of a
second LICENSE file.

## Scope (in)

| Skill | Path | Lifecycle | Mutation |
| --- | --- | --- | --- |
| `fix-ci` | `.agents/skills/fix-ci/SKILL.md` | shadow | Diagnose + one focused fix |
| `loop-on-ci` | `.agents/skills/loop-on-ci/SKILL.md` | shadow | Watch + invoke `fix-ci` |
| `get-pr-comments` | `.agents/skills/get-pr-comments/SKILL.md` | shadow | Read-only summary |
| `make-pr-easy-to-review` | `.agents/skills/make-pr-easy-to-review/SKILL.md` | shadow | Description / notes by default |
| `forge-ci-loop` | `.agents/skills/forge-ci-loop/SKILL.md` | shadow | Thin orchestrator for Mission Recipe |

Mission Recipe **CI loop / babysit PR** and the start-prompt copy live
in `docs/FORGE_CI_LOOP.md`. Option A still reuses
`.github/workflows/claude.yml`.

## Scope (out)

- `orchestrate` and any skill that needs `CURSOR_API_KEY`
- thermos / thermo-nuclear review plugins
- Open Code Review GitHub Action (runner-up; see
  `docs/OPEN_CODE_REVIEW_INTEGRATION.md` for the existing wrapper)
- third_party SaaS plugins
- Auto-merge, secret printing, specialist `shadow` → `active`

## Shared hard stops

Every skill above inherits these. Do not work around them.

- Never merge.
- Never rotate, mint, print, or commit secrets.
- Never bump the Python `mcp` package to 2.x.
- Never touch `connectors/relay` npm (leave Dependabot #79).
- Never promote specialists from `shadow` to `active`.
- Never cross APEX/JEOS brains or write private facts to this public tree.
- Stop on blocked/auth/secret/OSV-accepted-risk that is out of scope,
  including inherited relay/#79 OSV reds.

## `gh` fallback

Prefer `gh`. If it is missing or unauthenticated:

1. Say so. Do not claim checks or comments were read.
2. Fall back, in order: already-authorized GitHub MCP read tools; `curl`
   against `https://api.github.com` using a token **already** in the
   environment (`GH_TOKEN` or `GITHUB_TOKEN`) — never print it, never
   paste a new one; the PR's Actions or Conversation UI.
3. If none of those work, stop as blocked/auth.

## Shadow → active

Landing these files is not promotion. A skill stays **shadow** until a
controlled representative mission for *that* skill produces evidence,
privacy/corps/unittest stay green, and Joe authorizes the exact reviewed
version. One green babysit does not promote sibling skills. No skill may
promote itself.

## Rollback

1. Revert this change set (the five skill directories, this document,
   `docs/FORGE_CI_LOOP.md`, mission-form Recipe, `claude.yml` comment,
   README / docs index / CONTRIBUTING / CHANGELOG pointers, and the
   hygiene tests that assert them).
2. Close any in-flight Mission issue that selected CI loop without
   merging its PR.
3. No schedule, secret, App, or specialist lifecycle is created, so none
   needs demotion.
