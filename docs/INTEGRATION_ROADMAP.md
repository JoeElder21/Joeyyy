# Integration Roadmap — Runtime Stack, Phases 1–5

Program record dated 2026-07-24, from Joe's directive incorporating an external analysis he supplied. Premise accepted: this repository holds the governance *contracts* (TOML configs, JSON schemas, lifecycle stages, challenge pairs) but lacks the *runtime enforcement and automation* that makes those contracts real. The phases below add that runtime.

Standing rules for every item:

- Every platform enters as **candidate-unverified**. Nothing is adopted, installed, or trusted until it passes intake per `templates/agent-intake.md` — read its docs completely, verify identity and maturity, record boundaries, test one realistic use.
- The capability-absorption protocol applies: extract the smallest reusable pattern; never wholesale-clone prompts, identities, or permissions.
- Existing in-flight candidates run first: the Civil 3D MCP connector (build session scheduled) and the execution-layer trial (multica vs codex-autorunner, scheduled) are prerequisites and are not displaced by this roadmap.
- Recorded conflicts below stay visible until Joe resolves them; they are not silently merged.

## Phase 1 — Make contracts real

| Platform | Role in the system | Target layer |
| --- | --- | --- |
| DSPy | Self-optimizing prompts: compile specialist prompts against scored examples instead of hand-tuning | Agent 007 governance (prompt lifecycle for all specialists) |
| Guardrails | Runtime schema enforcement on agent outputs — the packet schemas enforced at generation time, not only at validation time | PacketGuard companion, both brains |
| E2B | Real sandboxed code execution for agent-written code | Agent 007 execution layer |
| LangKit | Privacy/PII monitoring on agent inputs and outputs at runtime | Complements `scripts/privacy_guard.py`; JEOS-critical |

Intake gate: each tool must demonstrably enforce an existing contract (a packet schema, the privacy policy, a sandbox blocklist) on one real specialist mission before promotion.

## Phase 2 — Make memory real

| Platform | Role | Target layer |
| --- | --- | --- |
| MemGPT (Letta) | Long-horizon agent memory beyond context limits | Cross-brain memory layer under Agent 007 |
| Honcho | Persistent user model — a durable, queryable model of Joe | JEOS-owned; APEX reads through 007 only |
| AgentOps | Session replay and observability for agent runs | Agent 007 audit layer (feeds the weekly audit with real evidence) |

**Recorded conflict:** the memory-layer slot already has a standing decision — kody is absorb-only, revisit next quarter (`docs/ECOSYSTEM_REPO_ANALYSIS.md`). Adopting MemGPT/Honcho reopens that decision. The memory-layer requirements absorbed from kody (`docs/ABSORBED_PATTERNS.md` §4: verify-before-write, source provenance, conversation-scoped surfacing) are the acceptance criteria any Phase 2 memory system must meet.

## Phase 3 — Make execution real

| Platform | Role | Target layer |
| --- | --- | --- |
| Trigger.dev | Scheduled cadences: daily briefs, weekly audits, permit-deadline watchers as durable scheduled jobs | Agent 007 cadence runbook |
| n8n | World-changing actions: workflow automation that files, sends, and updates external systems | Both brains; every outbound flow carries the approval gate from `docs/ABSORBED_PATTERNS.md` §2 |
| Unstructured | Auto-document intake: agency letters, permit PDFs, plans into structured evidence | APEX intake pipeline (feeds Intelligence Forge) |

**Recorded conflict:** Trigger.dev's scheduling overlaps multica Autopilots and the send_later/Routine layer already in use; the execution-layer trial decision comes first, and Trigger.dev enters intake only for what the trial winner does not cover. n8n overlaps existing direct MCP connectors (Gmail, Calendar, Todoist) — intake must name the flows those connectors cannot already do.

## Phase 4 — Make intelligence real

| Platform | Role | Target layer |
| --- | --- | --- |
| Reflexion | Self-correcting agents: verbal reinforcement from failed attempts | Absorption target for specialist retry/reflection rules |
| Tree of Thoughts | Adversarial multi-path reasoning for hard decisions | Absorption target for the challenge-pair and Decision Tribunal patterns |
| JARVIS (HuggingGPT) | Model routing: matching each task to the right model | Absorption target for 007 delegation routing |

Honesty note: these three are research codebases, not maintained products. Default disposition is **pattern absorption into the governance docs**, not deployment — the same treatment as buzz and text-to-cad in the prior cycle. Deployment requires a specific demonstrated need at intake.

## Phase 5 — Make civil work real

| Platform | Role | Target layer |
| --- | --- | --- |
| Speckle | Live AEC model data exchange — design data flowing to and from APEX delivery agents | APEX delivery/production layer |
| IfcOpenShell | IFC (open-BIM) parsing and authoring for model intelligence | APEX, pairs with Speckle |

Sequencing: both complement, not replace, the Civil 3D MCP connector — civil3d-mcp owns the live-DWG side; Speckle/IfcOpenShell own the open-data side. Neither enters intake before the Civil 3D connector passes its validation gate, so APEX learns one live-model integration at a time.

## Verification record — 2026-07-24

All 15 platforms verified by parallel research agents fetching each repository's live GitHub page (identity, activity, license, maturity, role-claim check). Verification covers identity and maturity only; adoption still requires each item's full intake gate.

| Platform | Repo | Stars | Last activity | License | Maturity verdict |
| --- | --- | --- | --- | --- | --- |
| DSPy | stanfordnlp/dspy | ~36.3k | release May 2026 | MIT | maintained product |
| Guardrails | guardrails-ai/guardrails | ~7.2k | release Jun 2026 | Apache-2.0 | active project |
| E2B | e2b-dev/E2B | ~13.1k | release 2026-07-23 | Apache-2.0 | maintained product |
| LangKit | whylabs/langkit | ~994 | Nov 2024 | Apache-2.0 | **stale (~20 months)** |
| MemGPT (Letta) | letta-ai/letta | ~23.9k | Jul 2026 | Apache-2.0 | maintained, **repo going legacy** |
| Honcho | plastic-labs/honcho | ~6.2k | 2026-07-23 | **AGPL-3.0** | active project |
| AgentOps | AgentOps-AI/agentops | ~5.7k | commits Jun 2026; releases lag ~11 mo | MIT | active, release cadence weak |
| Trigger.dev | triggerdotdev/trigger.dev | ~15.7k | release 2026-07-23 | Apache-2.0 | maintained product |
| n8n | n8n-io/n8n | ~197.7k | release 2026-07-23 | **fair-code (Sustainable Use)** | maintained product |
| Unstructured | Unstructured-IO/unstructured | ~15.2k | Jul 2026 | Apache-2.0 | maintained product |
| Reflexion | noahshinn/reflexion | ~3.2k | Jan 2025 (README) | MIT | research code, dormant |
| Tree of Thoughts | princeton-nlp/tree-of-thought-llm | ~6k | Jan 2025 | MIT | research code, dormant |
| JARVIS (HuggingGPT) | microsoft/JARVIS | ~25.1k | early 2024 | MIT | research code, dormant |
| Speckle | specklesystems/speckle-server | ~827 | active Jul 2026 | Apache-2.0 (module variations) | maintained product |
| IfcOpenShell | IfcOpenShell/IfcOpenShell | ~2.7k | active, v0.8.0 | **LGPL/GPL by component** | active project |

Corrections from verification, binding on intake:

- **LangKit**: stale since Nov 2024 and the PII-monitoring role is overstated (regex pattern groups, no dedicated PII engine). Phase 1 intake must reassess it against a maintained alternative before any adoption; treat its slot as open.
- **MemGPT (Letta)**: the letta-ai/letta repo is now the legacy server; Phase 2 intake targets the actively developed Letta Agent SDK instead.
- **Honcho (AGPL-3.0)**, **n8n (fair-code)**, **IfcOpenShell (LGPL/GPL)**: copyleft/source-available licenses recorded as adoption constraints — relevant if APEX ever ships or productizes anything built on them.
- **DSPy** is a full LM-programming framework (prompt optimization is a subset); **Guardrails** also covers input-side risk detection; **AgentOps** is SDK + dashboard (monitoring, not a runtime); **E2B**'s sandbox infrastructure lives in a separate infra repo.
- **JARVIS, Reflexion, Tree of Thoughts**: dormancy confirmed (early 2024 / Jan 2025 / Jan 2025) — the Phase 4 absorption-only disposition stands on evidence.

## Reconciliation with the prior cycle

The 14 repositories analyzed in `docs/ECOSYSTEM_REPO_ANALYSIS.md` keep their recorded dispositions; this roadmap adds the runtime stack around them. Where both name the same slot (memory, execution, scheduling), the recorded decision and its revisit date govern, and this roadmap's item waits for that decision point.

## Program order

1. Finish the in-flight candidates (Civil 3D MCP build; execution-layer trial and decision).
2. Phase 1, one tool at a time, each proving an existing contract.
3. Phase 2 after the memory-layer decision is formally reopened.
4. Phase 3 for whatever the execution winner does not cover; Unstructured may start earlier since it conflicts with nothing.
5. Phases 4–5 as absorption and APEX expansion respectively.

## Rollback

This roadmap is a plan record; it grants no access and installs nothing. Rolling back is deleting this file and the registry's roadmap reference. Each adopted tool records its own rollback at intake.
