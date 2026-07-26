# Execution Layer Trial — codex-autorunner vs multica

Decision package for the ecosystem's missing execution layer, per `docs/ECOSYSTEM_REPO_ANALYSIS.md`. Both candidates solve the same gap — running queued agent work unattended with notify-when-stuck — so exactly one gets adopted. Setup facts below are verbatim from upstream docs (2026-07-23); re-verify before executing.

## The gap

The agent civilization has governance (registry, packets, guards) but no dispatcher: nothing runs queued specialist work unattended, tracks task state durably, or fires recurring jobs like the weekly ecosystem audit. Both candidates wrap the runtimes already in use (Codex; Multica also wraps Claude Code).

## Candidate A — codex-autorunner (CAR)

Local-first queue of markdown tickets fed to an agent one at a time by a persistent state machine; pings Telegram/Discord only when stuck. Filesystem and git are the data plane.

- Install: `pipx install codex-autorunner` (or `pip install codex-autorunner`); verify with `car --version`. Prerequisites: Python 3.10+ and at least one supported agent (Codex, Hermes, OMP, or Opencode).
- Hub quickstart: `mkdir ~/car-hub && cd ~/car-hub`, then `car init --mode hub`; start with `car serve` (web UI at `http://localhost:8765`, `/pma` is the primary interface). Health check: `car doctor`.
- Tickets: markdown files `TICKET-###*.md` run in ascending numeric order. Required frontmatter: `ticket_id`, `agent` (a registered CAR agent ID such as `codex`, or `user`), `done: false`. Recommended body sections: Tasks, Acceptance criteria, Tests, Notes.
- Codex connection: CAR runs `codex app-server` as a subprocess speaking newline-delimited JSON over stdio; auth by API key or ChatGPT OAuth.
- Telegram: BotFather bot + `telegram_bot` block in `codex-autorunner.yml` with allowlisted chat/user IDs, then `car telegram start`.
- State: `.codex-autorunner/flows.db` is the single source of truth; each turn records exactly one durable terminal status (ok, error, interrupted); exhausted retries dead-letter the job.
- Verify on workstation during trial: exact `car ticket-flow` pause/resume subcommands (not fully documented; check `car ticket-flow --help`).

Strengths for this system: file-as-truth matches the repo-centric governance layer; one durable outcome per run and dead-lettering match the error-learning protocol; smallest ops footprint. Limits: Codex-side only (no Claude Code lane); repo-based work only; no recurring-schedule concept documented — cadence jobs would still need external cron.

## Candidate B — multica

Managed-agents platform: a daemon auto-detects agent CLIs on PATH and registers them as runtimes; dashboard issues, Squads under a leader agent, Autopilots for recurring work.

- Install (no npm path exists): `brew install multica-ai/tap/multica`, or the install script (`curl -fsSL https://raw.githubusercontent.com/multica-ai/multica/main/scripts/install.sh | bash`); Windows PowerShell: `irm https://raw.githubusercontent.com/multica-ai/multica/main/scripts/install.ps1 | iex`. Verify with `multica version`.
- Cloud quickstart is one command: `multica setup` (configures CLI, browser auth, starts daemon). Daemon auto-detects Claude Code (`claude`) and Codex (`codex`) on PATH. Monitor: `multica daemon status`, `multica daemon logs -f`.
- Issues: `multica issue create --title "..." --priority high --assignee "<agent>"`; history via `multica issue runs <issue-id>`.
- Autopilots: `multica autopilot create --title "Weekly ecosystem audit" --agent "<agent>" --mode create_issue`, then `multica autopilot trigger-add <id> --cron "..." --timezone "America/New_York"`. Concurrency policy declared up front: skip, queue, or replace. Caveat: webhook/API triggers are defined in the data model but have no server endpoint yet — treat cron and manual as the only working triggers.
- Task lifecycle: queued → dispatched → running → completed/failed/cancelled, with a sweeper that force-fails tasks stuck 5+ minutes dispatched or 2.5+ hours running.
- Squad creation: described in the README (leader agent routes work within a group) but no CLI or UI steps are documented — verify in the web UI during the trial before relying on it.
- Self-host (only if the trial sticks): `curl -fsSL .../install.sh | bash -s -- --with-server` then `multica setup self-host` (requires Docker + Compose; web app at `localhost:3000`). Never use the fixed dev verification code on a reachable instance.

Strengths: wraps both runtimes (Claude Code and Codex); Autopilots directly implement the cadence runbook; Squads mirror the class-leader routing model; lifecycle sweeper matches the absorbed stale-task pattern. Limits: dev-team framing (issues/PRs); cloud dependency for the trial; squad setup and webhook triggers under-documented.

## Trial protocol

Bounded, non-production, on the Joeyyy repo only — no client-facing or permit work until the winner passes validation.

Execution sequencing for the current program: Civil 3D workstation build evidence closes first (Friday), then the execution-layer trial run starts (Monday).

1. The task set is pre-defined in `trial/` (fixed ground truth, per the benchmarking pattern in `docs/ABSORBED_PATTERNS.md`): five tickets drawn from the real backlog — a registry intake draft, a weekly-audit dry run, an absorbed-pattern merge proposal, one deliberately blocked task (missing input) to test notify-when-stuck, and one recurring cadence job. The ticket files are CAR-native and map one-to-one onto multica issues/Autopilots per `trial/README.md`.
2. Metrics, defined up front, cost beside quality: tasks completed without intervention; correct notify-on-block behavior (did it ping only when genuinely stuck); durable state accuracy after a forced interruption/resume; wall-clock and token cost per task; setup + weekly upkeep time.
3. Run Candidate B first (`multica setup` against Multica Cloud is the cheaper trial); run Candidate A second only if B fails a defining metric.
4. Score per metric, not by impression; state each candidate's known weakness plainly in the results.
5. Winner's registry entry moves `candidate → shadow` per lifecycle rules; loser is recorded in `docs/ECOSYSTEM_REPO_ANALYSIS.md` with the reason.
6. Every start/stop action for trial tasks must use `runtime/trusted_launcher.py` with a user-signed one-time grant; missing or replayed grants are expected hard denies.

## Decision rule

Adopt Multica if squad routing and Autopilots work as described and the daemon drives both CLIs reliably — it covers more of the governance model. Fall back to CAR if Multica's undocumented pieces (squads, pause/resume) fail the trial or the platform overhead outweighs a solo operator's needs — CAR's file-as-truth model is the safer, smaller fit. Do not run both beyond the trial window.

## Rollback

Trial artifacts live in the Joeyyy repo and Multica Cloud/CAR hub state only. Uninstall the loser (`brew uninstall multica` / `pipx uninstall codex-autorunner`), delete its hub/daemon state, and update the registry entry with the outcome and evidence.
