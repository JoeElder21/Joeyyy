# Changelog

Repository-level changes. Agent-contract and roster history lives in
`docs/AGENT_REGISTRY.md` and the dated records in `docs/`.

## 2026-09-14 — Forge CI loop / babysit-PR mission recipe

Optional Recipe on the Mission form. Claude Code (or an Agent 007
wrapper) loops on failing PR checks until green or a hard stop. Not a
second Claude workflow, not a merge, not a specialist promotion, and not
a continuous background claim.

### Added

- `.agents/skills/forge-ci-loop/SKILL.md` — procedure, `gh` source of
  truth, hard stops, fallback if `gh` is unavailable.
- `docs/FORGE_CI_LOOP.md` — intake pin
  `5bf2b1544db739998121a306340631963c2ff3de` (cursor-team-kit
  `loop-on-ci` / `fix-ci` patterns, rewritten), start-prompt recipe,
  rollback.

### Changed

- Mission form Recipe dropdown. README / docs index / CONTRIBUTING
  pointers. `claude.yml` comment records CI-loop reuse of Option A.

## 2026-09-12 — Canon→Forge→Claude Code mission pipeline

A public-safe GitHub mission brief, filed by Forge, executed by the
existing `@claude` Action. Not a PacketGuard packet and not a
shadow-to-active promotion.

### Added

- `docs/MISSION_PACKET.md` — eight-field schema, roles, example packet,
  secrets/App checklist, dry-mission, local fallback.
- `.github/ISSUE_TEMPLATE/mission.yml` — issue form mapped 1:1 to that
  schema. Submitted body keeps `@claude` so `claude.yml` runs.

### Changed

- README pointer and docs index. `claude.yml` comments record that
  mission issues reuse the existing interactive job (Option A).

## 2026-09-12 — First APEX slice and Bird sample

One executable APEX path, specialists still shadow, plus a keyless Bird
TypeScript sample.

### Added

- `runtime/specialist_dispatch.py` — packet-only worker for
  `apex_delivery_commander` / `technical_qa`. Other modes still raise
  `DispatchUnavailable` / `NotImplementedError`.
- `runtime/first_apex_slice.py` and `scripts/run_first_apex_slice.py` — PREPARE
  → EXECUTE → VERIFY (`MissionRunner.complete`) → REPORT. Synthetic evidence;
  `qualifies_mode` stays false.
- `connectors/bird/` — `@messagebird/sdk` `BirdClient` sample. Key from
  `BIRD_API_KEY` only. Hello World email and `bird_otp_verification` are
  env-gated and never auto-sent. Order reference `MT1FL8M9VY`.
- `docs/FIRST_APEX_SLICE.md` — slice contract, honesty bounds, rollback.

### Changed

- `_invoke_specialist` in `evals/test_specialist_modes.py` calls the governed
  dispatch for the wired mode and still raises for every other mode.

## 2026-08-30 — The daily briefing becomes a verified schedule

Briefings were produced by hand on 2026-07-30 through 2026-08-04 — one new
artifact per day — and then stopped, because no Routine had ever been
created and the 08-04 run additionally found Gmail and Google Calendar
toggled off for its chat. This change records the diagnosis and the standing
contract now that the schedule actually exists: one private artifact updated
in place at 6:00 AM America/New_York daily by a Routine bound to a
persistent briefing session that holds the Gmail and Google Calendar mounts
(per-Routine connector grants are unavailable on this plan, and a
fresh-session Routine would fire connector-less — the Aug 4 failure again).
Private specifics (artifact URL, Routine identifier, holdings) stay out of
the repository.

### Added

- `docs/DAILY_EXECUTIVE_BRIEFING.md` — the public-safe operating contract:
  why the briefing stalled, the schedule and single-artifact contract, the
  twelve-section spec with per-section sources and truth rules, read-only
  boundaries under `AGENTS.md` section 9, to-do intake through the task
  tracker, and a four-step failure-diagnosis order. The 6:00 AM daily
  schedule supersedes the ~7:30 AM weekday reading-slot placeholders.

## 2026-08-05 — The governed host gets its WSL layer

`docs/RUNTIME_HOST_DECISION.md` put the runtime on Joe's workstation and no
third host; the workstation runs Windows. This change makes the host concrete —
an Ubuntu distribution under WSL with the governed clone at `/root/Joeyyy` — so
the whole stack is one command away: `wsl -d Ubuntu --cd /root/Joeyyy -- claude`.

### Added

- `scripts/wsl_ubuntu_setup.sh` — idempotent WSL-layer provisioning: refuses
  non-WSL kernels and non-root users before any mutation, installs the OS
  packages the validation surface needs (including Node.js, without which the
  `npx`-launched mounts cannot be probed), makes root the distribution's
  default user via `/etc/wsl.conf` when no `[user]` section exists, installs
  the Claude Code CLI when absent and links it into `/usr/local/bin` (the
  launch command runs a non-login shell that never reads `~/.profile`),
  creates the Python 3.12 `.venv`, and hands off to
  `scripts/workstation_setup.sh`. No credential, grant, or signing-key step.
- `docs/WSL_UBUNTU_SETUP.md` — the runbook from bare Windows to the launch
  command, recording the one floating-channel trust decision (Anthropic's CLI
  installer, deliberately unpinned because the CLI self-updates) and the
  host-side rollback.
- `tests/test_wsl_bootstrap.py` — 7 drift locks: script and runbook agree on
  the launch command byte for byte; the WSL layer delegates stack
  installation instead of reimplementing it; both setup scripts fail fast and
  stay executable (the workstation script's first coverage); guards precede
  mutation; the `/usr/local/bin` PATH mechanism and the floating-channel
  guard are enforced, not just described; the runbook is indexed and routed.

### Changed

- `docs/README.md` — indexed the new runbook; header count set to the
  measured row count (it said 31 against an actual 38 before this change;
  40 after merging #75's checklist row).
- `docs/MONDAY_ACTIVATION_RUNBOOK.md` — routes Windows workstations to the
  WSL runbook as the clean-signal environment `scripts/setup_workstation.ps1`
  itself points to for the full suite.
- `docs/REPOSITORY_OVERVIEW.md` — suite figures moved by the new module and
  the #74/#75 merge: 1128 tests across 38 modules.

## 2026-07-30 — Joeyyy becomes the account umbrella

Joe is consolidating everything under the JoeElder21 account. Joeyyy now pins
his other repositories as first-party submodules instead of merging their
trees — each keeps its own history, CI, issues, and deployment.

### Added

- `repos/` — first-party submodules `repos/elder-command-center`
  (`JoeElder21/Elder-Command-Center` @ `946a545`) and
  `repos/antigravity-sdk-python` (`JoeElder21/antigravity-sdk-python` @
  `9e47a90`), with a provenance table in `repos/README.md`. A third,
  `elder-briefing-app`, is planned once the Next.js briefing app transfers
  from the old account.
- `tests/test_vendor.py` gains `FIRST_PARTY_SUBMODULES`: the gitlink and
  `.gitmodules` contracts now cover `repos/` alongside `vendor/`, so a
  first-party submodule can no more silently become committed content than a
  vendored one. The upstream-dependency and vendor provenance checks stay
  scoped to `vendor/`.

## 2026-07-25 — All five open decisions resolved

Joe answered every open decision from `docs/REPO_OPTIMIZATION_2026-07-25.md` the
same day. No governance rule, packet contract, schema, roster entry, or lifecycle
stage changed; all ten specialists remain in `shadow`.

### Added

- **Apache-2.0 licensing, patterns citable.** `LICENSE` (verbatim upstream text),
  `NOTICE` (copyright plus what the grant does and does not cover), `CITATION.cff`
  (GitHub "Cite this repository"; the abstract names the enforcement layer as the
  reusable contribution, not the roster).
- **Behavioral evaluation harness** — `evals/` with `docs/EVALUATION_HARNESS.md`.
  Derives 39 material modes from `brains/*/agents.toml` so a new mode cannot be
  silently missed; metric contract traced to already-recorded acceptance criteria;
  three seed cases. Results publish to the Evaluations folder on Drive and are
  gitignored here. Two deliberate refusals: specialist dispatch raises rather than
  returning canned text, and the runner exits 2 rather than fabricating a pass.
- `requirements/runtime-evaluation.txt` — opt-in evaluation stack, recording the
  workstation-only and cloud-logging-disabled conditions.
- `tests/test_evaluation_harness.py` — 14 tests, including that the evaluation
  suite stays outside `unittest discover` and that the dispatch refusal is intact.
- `docs/SECRET_HISTORY_SWEEP_2026-07-25.md` — TruffleHog full-history sweep.
  Clean: 0 verified and 0 unverified secrets across 95 commits, two independent
  passes, coverage verified against `git rev-list` rather than the tool's summary.

### Changed

- **`snyk/agent-scan` approved for pre-install candidate scanning only.** Required
  section in `.github/ISSUE_TEMPLATE/absorption-candidate.yml` and a provenance
  block in `templates/agent-intake.md`, both stating the scope limit alongside the
  requirement — candidate only, never Joe's configured estate.
- **`ruff-format` enabled** and enforced in CI (`ruff format --check`) and
  pre-commit, applied as one mechanical commit across 46 files with no behavior
  change.
- **Lint rule set widened** to `E, F, W, I, UP, B, C4, SIM` in a separate commit:
  92 findings, 86 auto-fixed, 6 resolved by hand. The hand fixes were judgment
  calls, not mechanical: `assertRaises(Exception)` narrowed to `LeaseError` so the
  test asserts the lease actually closed rather than that anything at all went
  wrong; `zip()` given an explicit `strict=False` because the ragged pair is the
  point of the pairwise walk; and `Stage` moved to `StrEnum`, which is
  behavior-neutral here only because every call site already stringifies through
  `.value` — checked before changing it.
- `.gitignore` — `evals/output/`.

## 2026-07-25 — Repository engineering substrate

Record: `docs/REPO_OPTIMIZATION_2026-07-25.md`. No governance rule, packet contract,
schema, or agent definition changed.

### Added

- Supply-chain and workflow security: `.github/workflows/security.yml` runs zizmor static
  analysis over the workflows on push, PR, and weekly.
- `.github/dependabot.yml` — grouped weekly updates for pip, npm (`connectors/aps`), and
  GitHub Actions, each with a cooldown (7 days; 14 for majors) so a compromised release has
  time to be caught and yanked before the bot proposes it. Added in response to zizmor's
  `dependabot-cooldown` finding on this file's first CI run.
- `.pre-commit-config.yaml` — gitleaks, ruff, hygiene hooks, plus `privacy_guard.py` and
  `validate_specialist_corps.py` as local hooks.
- Contributor surface: `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `.editorconfig`,
  `.github/CODEOWNERS`, `.github/pull_request_template.md`.
- Issue forms converting existing paper workflows to structured intake:
  `.github/ISSUE_TEMPLATE/agent-intake.yml` and `absorption-candidate.yml`. The absorption
  form makes the FakeGit provenance check a required field.
- `docs/README.md` — index of all 31 documentation records.
- `CLAUDE.md` — repository guidance for Claude-based runtimes, pointing at `AGENTS.md`.
- `tests/test_repo_hygiene.py` — 15 tests asserting the substrate cannot silently regress,
  including that no GitHub Action is referenced by a floating tag.

### Changed

- `.github/workflows/validate-agent.yml` — added `verify_runtime_stack.py` and
  `verify_mcp_mounts.py` to validation; added `lint` (ruff) and `connectors` (Node) jobs;
  pinned all actions to full commit SHAs; set `persist-credentials: false`; added a
  cancel-in-progress concurrency group.
- `pyproject.toml` — added `[tool.ruff]` (house Python standard) and a `lint` task; the
  `validate` task now includes `verify_mcp_mounts.py`.

### Fixed

- Four pre-existing lint findings, with no behavior change: unused `re` import in
  `tests/test_specialist_corps.py`; ambiguous variable `l` in `scripts/trusted_launcher.py`
  and `tests/test_trusted_launcher.py`; unused-import annotation on the OpenTelemetry
  availability probe in `scripts/observability.py`.

### Open decisions

Recorded in `docs/REPO_OPTIMIZATION_2026-07-25.md`: license selection, DeepEval adoption
for the behavioral acceptance gate, `snyk/agent-scan` under the connector policy, whether to
enable `ruff-format`, and a one-off TruffleHog history sweep.
