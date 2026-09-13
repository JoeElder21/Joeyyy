# Mission packet — Canon → Forge → Claude Code

A **mission packet** is a public-safe GitHub brief. Canon drafts it. Forge
opens one GitHub Issue from it. The existing Claude Code GitHub Action
(`.github/workflows/claude.yml`) executes when the issue body contains
`@claude`.

This is **not** a PacketGuard 2.1 delegation, handoff, or cross-brain
constraint packet. Those contracts live in `schemas/` and are enforced by
`scripts/packet_guard.py`. A mission packet does not admit a specialist, does
not grant a writer lease, and does not move anyone from `shadow` to `active`.

Official Action reference: <https://code.claude.com/docs/en/github-actions>

## Roles

| Role | What it does | What it does not do |
| --- | --- | --- |
| **Canon** | Drive brain librarian. Drafts the packet from authorized private sources. | Does not open GitHub Issues, push branches, or run CI. |
| **Forge** | Repo/CI operator. Opens the Issue from `.github/ISSUE_TEMPLATE/mission.yml` and shepherds the Action run and resulting PR. | Does not invent packet fields. Does not merge. |
| **Claude Code GitHub Action** | Executes when triggered (`@claude` on the issue, or a later `@claude` comment). Implements on a branch and opens a PR. | Does not merge. Does not create repo secrets. Does not promote specialists. |

Forge is a **human** with write access (typically Joe). The Action rejects bot
actors unless `allowed_bots` is later set; do not have a bot open the issue
and expect Claude to start.

## Packet schema

Every packet, and every mission Issue, uses these fields. Headings below are
the canonical names. The issue form ids map 1:1.

### Objective

One sentence. The outcome, not the method.

### Mode

Exactly one of `JEOS` or `APEX`. This is the authorized brain for the work,
not a specialist identity. Cross-brain work still requires Agent 007 and a
separate PacketGuard transfer; do not encode that transfer here.

### Constraints

What must not change. Name locks, Dependabot PRs, lifecycle stages, privacy
class, and merge policy when they apply.

### Acceptance

Observable definition of done. Commands, artifacts, or PR-only (not merged)
outcomes. A skipped checker is skipped, never passed.

### Drive source IDs

Private-system handles Canon used while drafting. This repository is public
and so is every GitHub Issue.

- Default on a public Issue: `none — no Drive source`.
- Do **not** paste live Google Drive file ids, folder urls, or document
  titles that identify clients, employer work, or personal records.
- If Joe has accepted a public-safe handle, use a redacted token such as
  `drive:synthetic-example`. Keep the real id in Drive.

### Claude Code start prompt

The instruction Claude executes. It must contain the literal trigger
`@claude` so `.github/workflows/claude.yml` runs on `issues: [opened]`.
GitHub issue-form markdown blocks are **not** copied into the submitted
body; the trigger has to live in a submitted field (the start prompt and
the required checkbox).

### Owner

Accountable human. Usually Joe. Not an agent name.

### Due

ISO date `YYYY-MM-DD`, or `none`.

## Example filled packet

Public-safe dry-mission. Do not copy live Drive ids from this example;
there are none.

```text
Objective:
  Confirm the Canon→Forge→Claude Code path by opening a mission Issue
  whose Action run comments and stops without merging.

Mode:
  APEX

Constraints:
  Do not merge. Do not bump requirements locks or MCP pins. Do not
  promote any specialist from shadow to active. Do not commit secrets.
  Do not touch Dependabot #90.

Acceptance:
  - A GitHub Issue exists with title prefix [mission] and labels
    mission, claude.
  - The issue body contains @claude and this start prompt.
  - A Claude Code workflow run starts, or the local fallback is used
    and recorded on the issue.
  - No PR is merged.

Drive source IDs:
  none — no Drive source

Claude Code start prompt:
  @claude Read docs/MISSION_PACKET.md. Do not edit the repository.
  Reply on this issue with (1) the eight packet fields you read,
  (2) whether ANTHROPIC_API_KEY appears to be configured from the
  fact that you are running, and (3) stop. Do not open a pull request.

Owner:
  Joe Elder

Due:
  none
```

## How Canon fills the packet

1. Classify the authorized brain (`JEOS` or `APEX`) before reading a roster
   or Drive folder.
2. Draft only the eight fields. Move bounded constraints, not raw narrative.
3. Leave Drive source IDs as private handles in Drive. On the packet that
   Forge will publish, write `none — no Drive source` unless Joe has
   accepted a public-safe token.
4. Write a start prompt that begins with `@claude`, names the acceptance
   checks, and repeats the hard constraints.
5. Hand the packet to Forge. Stop.

Canon does not file the Issue. Filing is a Forge action on the public
repository.

## How Forge turns the packet into a GitHub Issue

1. Confirm the Claude GitHub App is installed on `JoeElder21/Joeyyy` with
   Contents, Issues, and Pull requests write (see checklist below).
2. Confirm one authentication secret is set in repository Actions secrets.
3. Create labels `mission` and `claude` if they do not exist (Settings →
   Labels). The form names them; GitHub will not apply a label that is
   missing.
4. Open a new Issue and choose **Mission**. Title prefix is `[mission]`.
5. Copy each packet field into the matching form input. Keep `@claude` in
   the start prompt. Leave the required trigger checkbox checked.
6. Submit. Shepherd the workflow run and any PR. Do not merge.

If the Action does not start, comment `@claude` plus the start prompt on
the same issue (the `issue_comment` path in `claude.yml`), or use the
local fallback.

## How Claude Code consumes the start prompt

`.github/workflows/claude.yml` is interactive mode: it has no `prompt`
input. It runs when `issues: [opened]` and the issue title or body
contains `@claude`, or when a later comment does.

On that path Claude reads `AGENTS.md` / `CLAUDE.md`, the issue body
(including every packet field), and the start prompt. It then implements
inside the runner checkout. There is no second interactive Claude job
for missions; a duplicate job on the same `opened` event would race two
checkouts and double-spend the key.

Automation mode (`prompt:` on a label-only workflow) is deliberately not
added. The mission form supplies the trigger the existing job already
understands.

## Secrets and GitHub App checklist

Set these in the repository (Settings → Secrets and variables → Actions).
**Do not commit them.**

| Secret | When to use |
| --- | --- |
| `ANTHROPIC_API_KEY` | Claude API key from the Claude Console. This is what the checked-in workflows pass today. |
| `CLAUDE_CODE_OAUTH_TOKEN` | Alternative: a subscription token from `claude setup-token` (Pro/Max/Team/Enterprise). If you switch to this, change the workflow input from `anthropic_api_key` to `claude_code_oauth_token`. |

Also required, and not a secret:

- Claude GitHub App installed on this repository:
  <https://github.com/apps/claude>
- App permissions used by the Action: **Contents** read/write, **Issues**
  read/write, **Pull requests** read/write.

If the key is unset, `claude.yml` fails rather than skipping. That is
existing behavior, distinct from `claude-code-review.yml`, which skips
when the key is empty.

## Local fallback

When the App or the secret is missing:

1. Paste the start prompt into Claude Code locally in this clone, or
2. Set the secret and App, then comment `@claude` on the issue.

Record which fallback was used on the issue. Do not claim the Action ran
if only the local path ran.

## Dry-mission

Use the example packet above.

1. Create labels `mission` and `claude` if needed.
2. Confirm the secret and the App.
3. Open a Mission issue from the example packet.
4. Confirm a `Claude Code` workflow run starts and Claude comments.
5. Close the issue. Close any PR without merging.

A dry-mission that never starts the Action is not a failed pipeline if
the local fallback was used and recorded; it is evidence the secret or
App is still missing.

## Wiring (Option A)

- Issue form: `.github/ISSUE_TEMPLATE/mission.yml`
- Trigger: `@claude` in the submitted issue body
- Job: existing `.github/workflows/claude.yml` (SHA-pinned
  `anthropics/claude-code-action`, `persist-credentials: false`, no
  fork-reachable `--allowedTools`)
- Review job unchanged: `.github/workflows/claude-code-review.yml`

## Rollback

Revert this change set. Delete `docs/MISSION_PACKET.md` and
`.github/ISSUE_TEMPLATE/mission.yml`, restore the README / docs index /
CONTRIBUTING / CHANGELOG pointers, and drop the comment on `claude.yml`.
Labels `mission` and `claude`, if created by hand, can stay; they do not
change runtime behavior.
