# Ecosystem Repository Analysis — 2026-07-23

Agent 007 analysis of 14 external repositories Joe supplied, assessed for fit with the Agent 007 / APEX / JEOS system. This is the durable record for the agent registry and the weekly ecosystem audit.

## Method

- One research pass per repository reading its actual README, docs, and structure (no identification by name alone).
- One independent adversarial verification pass per repository checking identity, claimed capabilities, maturity, and score honesty. All 14 identities confirmed; only minor factual corrections surfaced.
- Fit was scored against this system specifically — Codex custom agents + Claude skills/MCP, Civil 3D land-development practice, APEX/JEOS separation — not generic usefulness.

## Verdict summary

Four repositories genuinely aid the system. One is an immediate build-out (`civil3d-mcp`). Two solve the same execution-layer gap and require a pick (`codex-autorunner` vs `multica`). One is conditional infrastructure (`kody`). Six are capability-absorption reading, not deployments. Three are watch-list or skip.

## Tier 1 — Build

### 1. barbosaihan/civil3d-mcp — score 8/10, medium effort

MCP server that executes AI-generated C# inside a live Civil 3D session: query surfaces, cut/fill volumes, station/offset, batch drawing edits from Claude. Directly implements the APEX "Civil 3D Workflow Translator" role (master plan #101) on tooling already in use. Risks: single-author prototype (~22 stars, no releases); build the plugin against the workstation's own Civil 3D DLLs; start read-only on copies of project DWGs; write access falls under the one-designated-writer rule. Build-out guide: `docs/CIVIL3D_MCP_BUILDOUT.md`.

### 2–3. Git-on-my-level/codex-autorunner and multica-ai/multica — scores 6–7/10, medium effort. Pick one.

Both are the missing execution layer that turns the on-paper agent civilization into running work; do not run both.

- **codex-autorunner (CAR)**: local-first queue of markdown tickets fed to Codex unattended; Telegram/Discord ping only when stuck. Best if Joe wants simplicity around his native Codex runtime. Scope limit: repo-based work only.
- **multica**: daemon wraps Claude Code and Codex CLIs; dashboard issues, Squads with an agent leader (a working "Agent 007 governs specialists" model), Autopilots for recurring work (weekly audit, implemented). Heavier platform, dev-team framing, cheap cloud trial.

Decision package: `docs/EXECUTION_LAYER_TRIAL.md`.

## Tier 2 — Conditional / cheap

### 4. kentcdodds/kody — score 6/10, high effort

Self-hosted "assistant home" (Cloudflare): persistent memory, secrets vault, scheduled jobs, durable workflows shared by every connected MCP host — explicitly both Claude and Codex. Exactly the cross-brain memory/scheduler gap, but a fast-moving monorepo with real ops burden. Deploy only if willing to maintain it; otherwise absorb its `docs/use/` memory/packages/workflows design as the blueprint for Agent 007's future memory layer.

### 5. max-sixty/worktrunk — score 4/10, low effort

Polished Rust CLI for git-worktree-per-agent parallel work with pre-merge hooks. Install the day multiple agents edit this repo concurrently; the pre-merge hook runs the agent-contract unittests as a landing gate — the one-designated-writer rule, operationalized. Not needed before that day.

## Tier 3 — Absorb patterns, do not deploy

Extraction record: `docs/ABSORBED_PATTERNS.md`.

| Repository | Score | What to absorb |
| --- | --- | --- |
| shtirlitsDva/Autocad-Civil3d-Tools | 4/10 | Practicing engineer maintains production Civil 3D .NET plugins with AI agents in the loop: agent-facing AGENTS.md (evidence-first rules, build scripts, domain context), worktree parallelism, headless Core Console batching. Domain (Danish district heating) itself is not usable. |
| block/buzz | 4/10 | Per-agent identity and audit trails, tamper-evident append-only event log (error ledger, formalized), approval-gated workflows, at-most-one-in-flight dispatch. Deployment (relay + Postgres/Redis/S3) is pure overhead for one human. |
| ComposioHQ/awesome-claude-skills | 4/10 | Standing sourcing catalog for the weekly audit: skim monthly, shortlist 1–2 skills, absorb patterns (multi-agent entries first). Composio wrapper skills duplicate existing direct MCP connectors; do not install the plugin. |
| earthtojake/text-to-cad | 4/10 | Wrong CAD domain (mechanical/robotics), right architecture: dual Claude+Codex skill packaging, validation-first outputs (programmatic DXF checks), benchmark suite. Seed spec for a home-grown APEX civil exhibit DXF generator skill. |
| diegosouzapw/OmniRoute | 4/10 | Solves inference-cost pain this system does not have; free-tier pooling is unacceptable variance for professional deliverables. Absorb tiered-fallback and circuit-breaker/cooldown/lockout recovery patterns into the error-learning protocol. |
| alibaba/open-code-review | 3/10 | Rulesets target production software codebases, not this repo's docs/TOML. Absorb: deterministic pre-selection before LLM invocation, purpose-built minimal toolsets, benchmarking discipline. Revisit as a tool only if APEX grows real Python/C# code volume. |

## Tier 4 — Watch list / skip

| Repository | Score | Status |
| --- | --- | --- |
| citrolabs/ego-lite | 3/10 | **Watch list.** Agent browser with isolated per-agent Spaces inheriting real logins — the right shape for LFUCG/KYTC/KDOW permit-portal automation, and it installs into both Claude Code and Codex. Blocked: macOS-only; the Civil 3D workstation is Windows. Revisit immediately when a Windows build ships. Absorb its taskSpace ownership states and human-handoff (login/captcha) protocol now. |
| ADN-DevTech/Civil3DSnoop | 4/10 | **Bookmark.** Autodesk's official Civil 3D object-model inspector. Interactive GUI only — nothing an agent can drive. Becomes a desk-side debugging aid and reference code the day APEX writes Civil 3D .NET automation (pairs with civil3d-mcp development). No action until then. |
| Kristories/awesome-guidelines | 2/10 | **Skip.** Coding style-guide directory for software teams; nothing to run or absorb. At most: PEP 8 + a linter step in CI as the house standard for agent-generated Python. |

## Cross-cutting finding

The system's bottleneck is not tools; it is that governance docs exist while execution and memory infrastructure do not, and almost no public project speaks the land-development domain. Portfolio move: build `civil3d-mcp` (domain leverage nobody else offers), trial one execution layer (Multica or CAR), defer the memory layer decision (kody), and feed Tier 3 through the capability-absorption protocol — several of those repos are mature, battle-tested versions of documents this repo is writing from scratch.

## Joe's decisions

1. Execution layer: trial Multica Cloud or CAR first (see `docs/EXECUTION_LAYER_TRIAL.md`). — *Resolved 2026-07-23: trial proceeds, Multica Cloud first per the decision rule; fixed task set authored in `trial/`.*
2. civil3d-mcp: schedule the workstation build session (see `docs/CIVIL3D_MCP_BUILDOUT.md`). — *Resolved 2026-07-23: build session scheduled.*
3. kody: deploy-and-maintain vs absorb-only for the memory layer (default: absorb-only, revisit next quarter). — *Open; absorb-only default stands.*

Related decisions resolved the same day on Joe's instruction: Agent 007's native sandbox restored to `workspace-write` as the sole mutation executor, and legacy v2.0 delegation/handoff packets are now rejected by PacketGuard unless explicitly validated as archived.
