# Ecosystem Repository Analysis — 2026-07-30

Agent analysis of 22 external repository URLs Joe supplied (21 unique; `openai/openai-agents-python` was listed twice), assessed for fit with the Agent 007 / APEX / JEOS system. Companion record to `ECOSYSTEM_REPO_ANALYSIS.md` (2026-07-23); same fit-to-this-system scoring basis. This is the durable record for the agent registry and the weekly ecosystem audit.

## Method

- Four parallel research passes (agent frameworks, Claude Code ecosystem, infrastructure/miscellaneous, civil-engineering domain), each reading the live repository page and README rather than identifying by name alone.
- Stars, language, license, creation date, and last-push date verified against live GitHub metadata on 2026-07-30. Star counts are approximate as rendered at fetch time.
- Fit scored against this system specifically — Claude Code subagents + constitution section 15 capability-absorption intake, land-development practice, APEX/JEOS separation — not generic popularity.
- Two of the 21 were already on the books before this pass: `openai/openai-agents-python` (declared dependency, register row 12 in `EXTERNAL_RUNTIME_REGISTER_2026-07-24.md`, adapter unbuilt) and `Kimi-chuheng/Multi-Agent-AI-in-Civil-Engineering` (vendored, parked, conflict recorded in `requirements/vendor-multi-agent-kg.txt`). `alibaba/open-code-review` was scored 3/10 in the 2026-07-23 record; this pass re-verifies it with one changed fact.

## Verdict summary

No repository in this batch warrants installation or new vendoring. One is already load-bearing upstream (`anthropics/claude-code`). Two are high-value pattern quarries (`oh-my-claudecode`, `open-multi-agent`). Seven more yield a bounded reference or a single absorbable pattern. Eleven are skips, of which five are abandoned, archived, empty, or carry no license and are therefore legally unusable. The 2026-07-23 cross-cutting finding is re-confirmed: almost no public project speaks the land-development domain, and the closest-matching repo by stated intent (`SmartPlansAI`) contains no code at all.

## Tier 1 — Already load-bearing; keep a standing watch

### 1. anthropics/claude-code — upstream, not a candidate

Official repository for Claude Code: public issue tracker, changelog, plugin and example collection; the CLI source itself is not published here. ~139k stars, pushed this week; Anthropic commercial terms, not OSI-licensed. This is the substrate the whole system runs on, so "adopt" is not the question. Action: add the CHANGELOG and `/plugins` directory to the weekly ecosystem audit watch — native features (subagents, skills, hooks) evolve fast and can obsolete hand-built pieces of the governance layer.

## Tier 2 — Mine hard, do not install

### 2. Yeachan-Heo/oh-my-claudecode — score 7/10, absorb

Claude Code plugin implementing teams-first multi-agent orchestration: ~19 specialist agents, staged pipelines (`team-plan → team-prd → team-exec → team-verify → team-fix`), persistence-until-verified loops, cost-tiered model routing (cheap model for mechanical work, strong model for reasoning), magic-keyword invocation. TypeScript, MIT, ~38k stars, created 2026-01, pushed 2026-07-30. It is an off-the-shelf version of the problem this repository solves; installing it would collide with Agent 007 governance, leases, and packet contracts. Absorb instead: (a) explicit verify/fix pipeline stages as modes in the TOML contracts; (b) per-agent model tiering, which Claude Code already supports natively via `model:` in `.claude/agents` — near-zero effort, immediate token savings.

### 3. open-multi-agent/open-multi-agent — score 7/10, absorb

TypeScript multi-agent orchestration where a coordinator compiles a goal into a task DAG at runtime under a deterministic scheduler, with plan approval gates, plan freezing for deterministic replay, execution receipts, multi-agent consensus verification, token/cost budgets, default-deny tool access, and versioned EvalSets that reuse run records as CI regression gates. Drives Claude Code processes as first-class agents. MIT, ~6.7k stars, created April 2026, active. Young — verify patterns rather than treating them as proven prior art. The standout absorption: eval-records-as-regression-fixtures maps directly onto the evaluation harness (`evals/`, 39 material modes, dispatch unwired) and is the most direct path to making the shadow-to-active backlog self-checking once `_invoke_specialist()` is implemented.

## Tier 3 — Bounded reference or single-pattern absorption

| Repository | Score | Verdict |
| --- | --- | --- |
| Blueprints-org/blueprints | 5/10 | The only professionally-run engineering repo in the batch: design-code formulas as typed, tested Python (claimed 100% coverage), MIT, pushed 2026-07-30. **Eurocode only** (EN 1992/1993/1997) — unusable for direct professional checking in a US jurisdiction, and structural concrete/steel is not the land-development lane. Star as the architecture template for any future home-grown ACI/AASHTO/stormwater calculation modules. Python ≥3.12 floor fits only the 3.12 side of this repo's window. |
| openai/openai-agents-python | 5/10 | Already declared in `requirements/runtime-orchestration.txt`; register row 12 already names the open item: packet-bound handoff adapter and controlled test. Decision is wire-or-prune, not adopt. Typed-handoff and guardrail APIs remain useful reference; nothing new beyond what langgraph/crewai/autogen cover. |
| zhayujie/CowAgent | 4/10 | Formerly chatgpt-on-wechat; channel-integrated personal-assistant harness, MIT, ~46k stars, very active, Chinese-first ecosystem. Product misaligned. Absorb one design for the JEOS memory-layer gap (deferred in the kody decision): three-tier memory (short-term context → daily logs → long-term core) with a scheduled distillation pass ("Deep Dream"). |
| NousResearch/hermes-agent | 4/10 | ~222k-star competing chief-of-staff orchestrator, MIT, extremely active, ~26k open issues. Philosophical opposite of the constitution: it self-modifies its own skills at runtime — exactly what section 13 gates prevent. Study two patterns only: skill-improvement feedback loop and cross-session memory summarization. Do not adopt architecture. |
| Kimi-chuheng/Multi-Agent-AI-in-Civil-Engineering | 4/10 | Already vendored and parked. Re-verified: entire repo authored in a single day (2025-05-09), never touched since; pipeline hardwired to OpenAI/LlamaParse/Neo4j; pinned llama-index API has churned. **Leave parked.** The concept (agency letters, geotech reports into a queryable graph) is genuinely relevant — a small Claude-native extraction skill against a real corpus (e.g., LFUCG review letters) gets there faster than resuscitating the notebooks. Do not spend credentials or porting effort absent a concrete corpus. |
| alibaba/open-code-review | 4/10 | Re-verified from the 2026-07-23 record (then 3/10). Changed fact: now ships a Claude Code plugin; Apache-2.0, ~16k stars, very active. Still tuned for production Java/Go/JS codebases, not docs/TOML. The prior verdict stands, with the plugin noted as a cheap optional experiment if automated PR review comments on governance PRs are ever wanted. |
| shanraisshan/claude-code-best-practice | 3/10 | Pure documentation ("vibe coding to agentic engineering"), MIT, ~63k stars, active. Beginner/intermediate audience; much restates official docs. Skim the context-management section once as a "is there a native way?" cross-check. |

## Tier 4 — Skip

| Repository | Score | Status |
| --- | --- | --- |
| langflow-ai/langflow | 2/10 | Visual low-code flow builder, MIT, ~152k stars, very active. A drag-and-drop canvas undermines the text-first auditability the constitution mandates and duplicates existing orchestration. The one idea worth keeping — expose a governed workflow as an MCP server — is buildable natively in the runtime layer without the platform. Had a serious pre-1.3 RCE CVE (2025); relevant if ever self-hosted. |
| aden-hive/hive | 2/10 | Python runtime whose core bet is emergent, self-evolving agent graphs — precisely what sealed-domain governance exists to prevent. Apache-2.0, ~10.8k stars, high churn (~900 open issues). Absorbable fragment: hierarchical budget enforcement (team/agent/workflow cost ceilings) as a contract idea; needs no code. |
| musistudio/claude-code-router | 2/10 | Local multi-provider routing proxy, MIT, ~36k stars, active, ~1,000 open issues. Solves cost arbitrage across providers; this system is Anthropic-subscription, Anthropic-models. A third-party proxy in that path adds a failure point and terms-of-service friction for an unneeded capability. Tiered routing is already native per-agent. |
| buildkite/agent | 1/10 | Confirmed: Buildkite's CI/CD build-runner daemon (Go, since 2014), not an AI agent. Superbly maintained, wholly irrelevant — requires a Buildkite account and runner fleet; the validation surface is already served by GitHub Actions and pre-commit. |
| zai-org/Open-AutoGLM | 1/10 | Zhipu phone-use agent framework (Android/HarmonyOS via ADB/HDC) built on its own GLM vision models and a Chinese app catalog. Apache-2.0, ~26k stars, **no code activity since 2026-03**. Neither brain has a phone-automation surface; if one emerges, Anthropic computer-use is the coherent path. |
| winfunc/opcode | 1/10 | Desktop GUI wrapper for Claude Code (Tauri), AGPL-3.0, **dormant since 2025-10** against a fast-moving target. Nearly everything it offered is now native (subagents, session resume, usage visibility). AGPL is awkward for pattern-lifting into an Apache-2.0 public repo. |
| reworkd/AgentGPT | 0/10 | **Archived 2026-01-28.** 2023-era browser goal-loop wrapper, GPL-3.0 — dead, superseded, and a copyleft hazard for section 15 rewritten-pattern intake. Nothing to take. |
| JaredBaileyDuke/sql-agent | 0/10 | Two-day personal build (2025-03), 0 stars, dormant. "Civil engineering" is a tease: the domain database is private; the public demo queries a sample music SQLite DB. **No license file — legally unreusable.** |
| ressay/ArchToCE | 0/10 | Abandoned thesis code (2018–2022): IFC/BIM to preliminary structural layout via pythonocc. **No license.** Wrong problem (building-structure BIM, not civil/site). Living ecosystem for IFC, if ever needed, is IfcOpenShell/BlenderBIM. |
| HodardCodeclub/Construction-Works-Management-System- | 0/10 | PHP 5 CRUD app abandoned since 2019, hardcoded admin credentials in the README, **no license**. The permit-tracker skill already covers the real need. Do not clone. |
| 4EvrEvolving/SmartPlansAI | 0/10 | **Empty repository** — one commit, README of intent only, 0 KB of code. Stated goal (AI automation of Civil 3D plan production) is the closest match to actual practice in the whole batch, which re-confirms that nothing off-the-shelf exists in this niche and the `civil3d-mcp` build-out remains the highest-leverage domain move. |

## Cross-cutting finding

Same as 2026-07-23, sharpened: the popular half of this batch (langflow, hermes-agent, CowAgent, AgentGPT, hive) competes with orchestration this repository already governs better for its purpose, and the domain half is essentially vacant — one Eurocode library, one parked academic demo, and three dead or empty repos. Star count correlated inversely with fit. The leverage remains in (a) wiring what is already built (evaluation-harness dispatch, policy enforcement call sites, the openai-agents adapter) and (b) domain tooling nobody publishes (`civil3d-mcp`, a permit-corpus extraction skill).

## Recommended actions (judgment; not executed)

1. Absorb the eval-records-as-regression-gates pattern (open-multi-agent) into the evaluation harness design before dispatch is wired.
2. Adopt per-agent model tiering natively via `model:` in `.claude/agents` (pattern credit: oh-my-claudecode).
3. Resolve openai-agents: build the packet-bound handoff adapter named in register row 12, or prune the dependency.
4. Add the anthropics/claude-code CHANGELOG and `/plugins` directory to the weekly ecosystem audit watch list.
5. Everything in Tier 4: no action, and record the five unlicensed/archived/empty repos so they are not re-reviewed.

## Joe's decisions

None required. All verdicts here are read-only analysis; the three recommended absorptions go through the normal section 15 intake and section 13 evolution loop when scheduled.
