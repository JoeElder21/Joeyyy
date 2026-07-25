# Frontier Repository Scan — 2026-07-24

Agent 007 proactive sweep of the public GitHub ecosystem for innovative repositories worth incorporating into the Agent 007 / APEX / JEOS system. Unlike `docs/ECOSYSTEM_REPO_ANALYSIS.md` (14 repos Joe supplied), this scan sourced candidates from open web research across five gap areas: execution/orchestration, agent memory, MCP infrastructure, civil-engineering domain tooling, and agent governance/safety.

## Method and verification honesty

- Candidates were sourced via web search (session GitHub access is scoped to this repository only, so discovery ran through public web sources rather than the GitHub search API).
- Verification levels are stated per entry and are lower than the ecosystem analysis standard:
  - **Verified** — repository page read directly this session; identity, maturity, and capabilities confirmed.
  - **Corroborated** — consistent across multiple independent secondary sources; repository not read directly.
  - **Unverified** — single-source claim; treat as a lead, not a finding.
- Per the house protocol, any Build decision below still requires a full adversarial verification pass and registry intake before deployment. Scores are fit-to-this-system, not generic quality.

## Verdict summary

Two repositories are near-term adopts: `chrome-devtools-mcp` (unblocks the ego-lite watch-list use case on Windows) and `graphiti` (a lighter, MCP-native answer to the open kody memory-layer decision). One is a cheap defensive adopt pending verification (supply-chain scanning for the absorption pipeline). The rest are absorption reading, sourcing catalogs, or explicit skips. One cross-cutting security finding changes the intake protocol regardless of any adoption.

## Cross-cutting security finding — act first

**FakeGit campaign (July 2026):** security reporting identified roughly 7,600 malicious GitHub repositories, over 800 posing as AI skills or MCP servers, with malware logging 14M+ downloads. AI agents were specifically manipulated into recommending these repositories. Consequences for this system:

1. The capability-absorption protocol and `templates/agent-intake.md` must require provenance verification before any external repo is read for absorption: confirm the owning org/user is the canonical author (releases, website cross-link, package-registry linkage), check age and contributor history, and never execute code from an unverified repo.
2. Web-sourced repo recommendations — including this document — are exactly the channel FakeGit poisoned. Every candidate below must be re-verified against its canonical URL at intake time.
3. This finding upgrades the case for a supply-chain scanning gate (see Bumblebee, Tier 2).

## Tier 1 — Adopt near-term

### 1. ChromeDevTools/chrome-devtools-mcp — score 8/10, low effort. **Verified.**

Google-maintained MCP server (~47.5k stars, active) that lets an agent drive a live Chrome browser: click/type/fill forms, screenshots, console and network inspection, performance traces. Critically, it connects to an **already-running Chrome with existing logged-in sessions and profiles** (`--browser-url`, custom user-data directories), and runs on Windows (with documented Windows 11 configuration).

**Fit:** this substantially unblocks the ego-lite watch-list item — LFUCG/KYTC/KDOW permit-portal automation — which was blocked solely because ego-lite is macOS-only and the Civil 3D workstation is Windows. chrome-devtools-mcp is cross-runtime (any MCP host, so both Claude and Codex), first-party maintained, and read/write browser control on real logins. Risks: no ego-lite-style per-agent Space isolation — sessions are the human's real sessions, so the one-designated-writer rule and human-handoff protocol (login/captcha, absorbed from ego-lite) apply from day one; start read-only (status checks, document pulls) before any form submission.

### 2. getzep/graphiti — score 7/10, medium effort. **Verified.**

Temporal knowledge-graph memory framework (~29.1k stars, 2.9k forks, actively maintained) from Zep. Facts are edges with validity windows — when information changes, old facts are invalidated, not deleted — with provenance to source episodes and hybrid retrieval (semantic + BM25 + graph traversal). Ships a first-party **MCP server**, so both Claude and Codex runtimes can read/write the same memory without custom glue. Requires Python 3.10+, a graph database (Neo4j or FalkorDB), and an LLM provider key.

**Fit:** this is the strongest candidate yet against open decision #3 from the ecosystem analysis (kody deploy-vs-absorb, default absorb-only). Graphiti is a purpose-built memory layer rather than a full assistant-home platform: far smaller ops surface than kody, MCP-native, and its temporal validity model matches the house rule that memory records are corrected by supersession, not deletion. Natural mapping: one graph group per brain namespace (APEX / JEOS logical namespaces preserved), Agent 007 as the sole cross-group reader, writes routed through writer leases. Risks: real infrastructure dependency (graph DB) on the workstation; LLM-in-the-loop ingestion costs; still requires the memory-layer trial gate before anything relies on it.

## Tier 2 — Conditional / cheap, pending verification

### 3. Bumblebee (Perplexity) — supply-chain scanner — score 6/10, low effort. **Corroborated.**

Read-only scanner for malicious/suspicious packages across npm, PyPI, Go modules, **MCP servers, and editor extensions**. Directly responsive to the FakeGit finding: run it as a standing gate before any MCP server or skill is installed, and as a step in the capability-absorption checklist. Verify the canonical repository under the PerplexityAI org before use; a supply-chain scanner is itself a prime typosquat target.

### 4. OpenClaw — self-hosted personal assistant — score 5/10, high effort. **Corroborated.**

The breakout self-hosted personal agent of 2025–26 (reported ~247k stars): messaging-first (WhatsApp/Telegram/Discord/Slack), 50+ tool connections, multi-model, runs entirely on personal infrastructure. **Fit:** JEOS-side only — a persistent, reachable-from-anywhere front end for the personal brain that this repository's on-demand agents deliberately do not claim to be. Cautions: large attack surface for a tool wired into personal messaging and credentials; widely publicized security incidents around hastily-deployed instances; would need its own hardening review, strict JEOS-only scoping, and no APEX/professional data. Same posture as kody: do not deploy casually; absorb its channel-integration and heartbeat/proactivity patterns unless Joe wants a real personal-assistant deployment project.

## Tier 3 — Absorb patterns, do not deploy

| Repository / project | Verification | What to absorb |
| --- | --- | --- |
| Hephaestus (Open Agent OS, ~951 stars) | Corroborated | Governed memory and security gates over Claude Code/Codex/Cursor, meta-agent builder, A2A hub routing, local ontology. Small project, same architectural thesis as this repo — read its gate and ontology design for convergent/divergent choices; do not replatform onto a sub-1k-star runtime. |
| Destructive Command Guard | Corroborated | Deny-classes of dangerous shell/git commands before agent execution. Absorb the command-class taxonomy into PacketGuard / the Codex sandbox policy as a pre-execution check. |
| Anvilate (local-first text-to-CAD) | Corroborated | Physics-validated, parametric STEP/DXF output that drops into AutoCAD. Wrong domain (mechanical), same lesson as earthtojake/text-to-cad: validation-first CAD outputs. Second reference for the future APEX exhibit-DXF skill. |
| codebase-memory-mcp | Unverified | MCP server giving coding agents persistent codebase understanding without rescanning. Lead only; evaluate if agent context-rebuilding cost becomes measurable. |
| Memory-framework field (Letta, Cognee, Mem0, Zep) | Corroborated | Reference reading for the memory-layer decision: Letta = agent self-managed memory runtime; Cognee = local-first graph ECL pipeline; Mem0 = lightweight personalization API; Zep/Graphiti = temporal graphs. Graphiti (Tier 1) is the extracted pick; revisit this field note if its trial fails. |
| awesome-agent-orchestrators; awesome-cli-coding-agents | Verified (list pages) | Add both to the weekly-audit sourcing catalog alongside ComposioHQ/awesome-claude-skills. Curated indexes of the exact orchestration niche this repo occupies. |

## Tier 4 — Watch list / skip

| Project | Verdict |
| --- | --- |
| Ruflo (renamed from Claude Flow, reported ~61k stars) | **Watch, hype-risk flag.** Orchestration layer over Claude Code. The execution-layer trial is already committed (Multica Cloud first, CAR fallback); do not add a third contender mid-trial. The lineage has a history of inflated capability claims — if it ever enters intake, it gets the full adversarial pass. |
| LangGraph, CrewAI, AutoGen, AgentScope, Agno | **Skip as platforms.** Mature general-purpose agent frameworks, but adopting one means rebuilding the system outside its native Codex custom-agents + Claude skills/MCP runtimes for no domain gain. LangGraph's state-machine orchestration model is worth a read when formalizing cadence routing; nothing to deploy. |
| Strix (AI penetration testing) | **Skip.** Offensive-security agent; no fit with land development or personal ops. |
| Vibe-Trading | **Skip.** Prompt-to-backtest trading research; out of scope for both brains, and live-trading agents sit behind the high-impact financial-transaction boundary anyway. |
| BlenderLLM, FreeCAD LLM script generators | **Skip for now.** Text-to-CAD in non-Autodesk ecosystems; civil3d-mcp remains the domain build. Note the pattern (LLM → validated script → CAD session) matches civil3d-mcp's architecture — convergent evidence the build-out bet is sound. |

## Cross-cutting finding

The frontier confirms the prior analysis's thesis and sharpens it: the ecosystem now offers first-party, high-maturity infrastructure for exactly two of this system's three gaps — browser execution (chrome-devtools-mcp) and memory (graphiti) — while still offering nothing for the land-development domain itself. That keeps `civil3d-mcp` the highest-leverage build in the portfolio, and shifts the memory-layer question from "build vs kody" to "trial graphiti." Meanwhile FakeGit makes provenance verification a mandatory intake gate: the more this system absorbs from the frontier, the more the frontier is a threat surface.

## Decisions for Joe

1. **chrome-devtools-mcp:** approve a read-only permit-portal trial on the Windows workstation (status checks only, human handles logins/captchas, no form submission). Default: proceed after adversarial verification pass.
2. **graphiti:** approve a memory-layer trial (FalkorDB + MCP server, one brain namespace first) as the concrete test of open decision #3. Default: proceed after the execution-layer trial concludes, not concurrently.
3. **Intake hardening:** amend `templates/agent-intake.md` and the absorption protocol with the FakeGit provenance checklist, and evaluate Bumblebee as the automated gate. Default: amend now.
4. **OpenClaw:** park unless Joe wants a JEOS personal-assistant deployment project this quarter. Default: absorb-only.
