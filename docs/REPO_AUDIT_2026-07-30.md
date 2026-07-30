# External Audit — Agent 007 vs Google Antigravity SDK — 2026-07-30

A five-agent adversarial audit compared this repository against Google's `antigravity-sdk-python` on one question: which is usable for daily work today. Both repositories were read at line level **and executed**. This record captures what was verified, what the repository does not do, and the decisions that stand between this harness and a system that actually runs.

The comparison is not apples-to-apples, and that is the finding. This repository is a governance harness with no runtime; the Antigravity SDK is a runtime with no auditable core. Neither is a complete daily system on its own.

## Method and verification honesty

- Four assessor agents ran in parallel — one deep-read and one execution agent per repository — followed by one adversarial cross-examiner that re-checked every claim against the files on disk and corrected the assessors.
- Verification levels used below:
  - **Executed** — the command was run this session and its output recorded.
  - **Read-verified** — the claim was confirmed against a specific file and line.
- Stated limits of this audit:
  - The SDK's supported path (`pip install google-antigravity`, which delivers the compiled binary, plus model credentials) was **not** exercised. Every claim about its daily usability is inference from source, not measurement.
  - **No mission was run.** This audit measures the harness, its contracts, and its honesty. It proves nothing about output quality, and nothing here upgrades any specialist out of shadow stage.
  - The audit was performed by AI agents on a repository substantially built by AI agents. The cross-examiner exists because of that, not despite it.

## Verdict summary

From source on disk, this repository runs 100% green in under three seconds with zero dependencies installed; the Antigravity SDK does not import at all. Reverse the frame to live agent work and the result inverts: the SDK can act today and this repository cannot, because nothing here constructs a model client. The honest one-line summary is that this is a well-tested governance layer waiting for a runtime, and the runtime decision (below) is the only one that unblocks the rest.

## What this repository verifiably does

| Claim | Verification | Evidence |
| --- | --- | --- |
| Full suite green on a bare clone, no third-party packages | Executed | `python3 -m unittest discover -s tests -v` → `Ran 241 tests in 2.769s`, `OK (skipped=27)`, 0 failures, 0 errors |
| Degradation is engineered, not skip-decorated dead code | Executed | With `pydantic`, `jsonschema`, `mcp` installed, skips drop 27 → 20 and all 241 still pass — gated tests convert to passing tests |
| Every skip names its missing dependency | Executed | langgraph ×5, pydantic ×4, openai-agents ×4, autogen ×4, prefect ×3, mcp ×2, and one each for jsonschema, crewai, celery, llama-index-core, opentelemetry |
| All three validators exit 0 | Executed | `privacy_guard.py` → `Privacy guard passed.`; `validate_specialist_corps.py` → `valid: true`, 10 contract packets, 10 boundary rejections; `verify_runtime_stack.py` → `valid: true`, `installed_count: 0`, 18 TOML files checked |
| Every module imports cleanly on stdlib alone | Executed | 10/10 in `runtime/`, 19/19 in `scripts/` (as `scripts.X` from the repo root) |
| PacketGuard is substantive, portable validation | Read-verified | 1,321 stdlib-only lines: NFKC canonicalization and Unicode-alias rejection (`scripts/packet_guard.py:1205-1232`), cross-packet sensitivity monotonicity and `boundary_blocked` emptiness so refused content cannot leak (`:590-850`), working CLI (`:1283`) |
| The governance MCP server is deployable now | Executed | `build_server()` constructed a live FastMCP instance with `mcp` installed (`scripts/governance_mcp_server.py:119-135`) |
| Fail-closed paths genuinely raise | Read-verified | `PermissionError` on disallowed lifecycle transitions (`runtime/lifecycle.py:193-201`); `HandoffRejected` before control transfer with ledgered rejection (`scripts/agent_runtime.py:137-176`); launch denial for unknown, unsigned, expired, and replayed grants (`scripts/trusted_launcher.py:114-152`) |
| Anti-fabrication discipline is enforced in code | Read-verified | `CadenceRun.status` returns `partial` unless steps executed (`runtime/cadence.py:76-80`); `memory_trial.run_trial()` returns `blocked` with named missing preconditions (`runtime/memory_trial.py:68-83`); the corps validator emits `named_agents_invoked: false`, `real_missions_completed: false` |
| Test suite is real, not smoke | Read-verified | 4,349 lines across 24 files, including a 1,091-line packet-contract suite |

The cross-examiner's judgment on the last row is worth preserving: for a repository built in roughly four days largely by parallel AI agents, machinery that refuses to simulate success is the most transferable idea here.

## What this repository verifiably does not do

| Gap | Verification | Evidence |
| --- | --- | --- |
| No model client is ever constructed — no mission can run | Read-verified | Grep across `*.py` finds no client construction. `scripts/claude_runtime.py:153` holds a live `client.messages.stream()` call that is dormant because nothing supplies a client |
| The corps has never left shadow stage | Read-verified | Corps-wide `deployed_stage = "shadow"` (`config/specialist_corps.toml:36`); active-stage gates require evidence no in-repo code can generate |
| Operational history is a single line | Read-verified | `trial/output/cadence-log.md` — one TICKET-005 hygiene sweep, 2026-07-24 |
| Writer leases do not survive across processes | Read-verified | In-memory dicts with no persistence (`runtime/writer_lease.py:55-127`); two processes can each believe they hold the same lease. The Celery layer that would fix this is unperformed activation work |
| Enforcement is opt-in, not interposed | Read-verified | `config/mcp_mounts.toml` declares rather than intercepts; any process can start a server directly, bypassing `trusted_launcher.py`, whose signing key is readable by any same-user process (`:55-60`). This is a workflow convention, not a security boundary against the agents it governs |
| Write targets have no bound storage | Read-verified | `APEX/Strategy-Campaigns`, `JEOS/Reflection-Ledger` and peers are logical strings; `scripts/evidence_index.py:74` holds documents in a Python list in RAM |
| Four integrations are nominal | Read-verified | `mem0` is never imported anywhere — `scripts/memory_layer.py:44-88` is a stdlib keyword store described as "on the mem0 scope model"; `dspy` and `guardrails-ai` appear only as dependency-audit rows with zero call sites; Phoenix export is a comment (`scripts/observability.py:9-11`) |
| Parallel-stream duplication persists | Read-verified | Two lifecycle engines (`runtime/lifecycle.py` vs `scripts/orchestration_graphs.py:38-99`), two Prefect layers, three AutoGen adapters. `docs/RECONCILIATION_2026-07-24.md` names canonical homes and drift-lock tests pin agreement, but the redundant code remains |
| Some tests assert prose, not behavior | Read-verified | `tests/test_reconciliation.py:39-50` and `tests/test_governance_docs.py` check that phrases exist in Markdown — useful drift locks, but they inflate the apparent test count |

## Findings on antigravity-sdk-python

Recorded as the comparison basis, and because two findings bear on our own intake protocol.

- **The Python package is a wire-protocol client around a closed Go binary.** `localharness` owns the model loop, the system prompt, all builtin tools including command execution and its sandboxing, MCP, subagents, and session storage. Every backend — including the local Ollama and LiteRT paths — subclasses `LocalConnectionStrategy`, whose constructor resolves the binary and raises without it. The components a security-conscious operator most needs to audit are precisely the ones that cannot be audited.
- **The repository does not import from a clone.** Generated protobuf modules are absent from git and the regeneration step is documented nowhere for external users; the audit agent had to derive it. Once derived, 681 of 715 tests pass in 8.28 seconds, with failures decomposing into 22 binary-dependent tests and harness artifacts (`policy_test.py` passes 74/74 under its intended runner). The pure-Python layer is genuinely well made.
- **The GitHub repository is a one-way mirror, not an open-source project.** Every commit is a squashed export with no description, and the only CI triggers on tag push and tests the published wheel rather than the repository's code.
- **Documentation rot has reached a safety claim.** The README states the agent runs read-only by default; the verified default enables all file-write tools with command execution denied, and the README's suggested remedy is a no-op because it is already the default. Pydantic's silent extra-field ignoring has additionally fossilized five nonexistent capability fields in a shipped config.
- **Alpha churn is real:** eight releases in eight weeks, a default model swapped in a patch release, transports removed within weeks, and one advertised feature with no Python surface.

**Intake consequences for this system.** Two house rules gain evidence. First, our provenance rule should extend to first-party vendor repositories: a Google-owned mirror still failed to import, still shipped a wrong safety default, and still could not be built from source — vendor identity is not a substitute for verification. Second, any dependency whose enforcement lives inside an unauditable binary cannot satisfy our connector-isolation policy on its own; it would have to be wrapped, not trusted.

## Corrections to earlier records

The cross-examiner corrected the assessors, and two corrections touch existing repository records:

- The build window is **2026-07-22 through 2026-07-25** (91 commits, 22 on the first day), not the 07-23 start reported mid-audit.
- The `83%` figure in `docs/AGENT_RUNTIME_BRIDGE.md:29` was initially flagged as a measurement dressed up from a step count. On re-reading, the section is titled "Efficiency, measured honestly", defines the metric in its first sentence, and disclaims wall-clock and model-quality effects. The hedge is headline-level. Expressing a 6-to-1 step count as a percentage is still the weakest presentational choice in the docs, but the record is not dishonest.

## Open decisions — Joe

Ordered by how much each unblocks. Decisions 2, 3, 4, and 7 only become concrete once decision 1 is made.

1. **Which runtime hosts Agent 007?** Nothing here constructs a model client, so no mission can run until this is answered. Three surfaces are already half-built: `scripts/claude_runtime.py` (typed Anthropic tool definitions), `scripts/agent_runtime.py` (OpenAI Agents SDK), and `.codex/agents/*.toml` (Codex CLI). *Recommendation: an MCP-capable host with `scripts/governance_mcp_server.py` mounted as the enforcement layer — shortest path from here to something that executes, and it uses the one artifact already deployable.*
2. **Where do write targets physically land?** Options: in-repo directories, a Logseq graph, external storage, or SQLite. *Recommendation: in-repo directories first (`brains/apex/records/`, `brains/jeos/records/`), since git and the privacy guard already provide audit and rollback.*
3. **What clears the activation gate, and who signs?** The gate currently demands evidence no in-repo code can produce, which is a closed loop. *Recommendation: promote exactly one specialist on one real mission with Joe's manual sign-off. Ten at once is how this stays in shadow indefinitely.*
4. **Does cadence run on a schedule, and where?** Cron specs exist; no deployment does. *Recommendation: defer Prefect; a scheduled invocation of the host from decision 1 achieves the same outcome with far less infrastructure.*
5. **Implement the nominal integrations, or strike them?** mem0, dspy, guardrails-ai, and Phoenix are named but uncalled. *Recommendation: strike them from the README and requirements tiers. This repository's strongest quality is that it does not overclaim; these four are the exceptions.*
6. **Delete the duplicate engines, or keep the drift locks?** *Recommendation: delete. Three AutoGen adapters is maintenance for a framework that may not survive decision 1.*
7. **Do writer leases become durable?** *Recommendation: persist to SQLite or a lockfile. It converts the headline single-writer guarantee from aspiration to fact.*
8. **Does this repository stay public, and under what license?** There is no LICENSE file, so the default is all-rights-reserved. *Recommendation: decide deliberately — add a license if it stays public, or make it private if the governance design is the valuable asset.*

## Rollback

This change adds one document and one README index line. No code, schema, configuration, or test behavior was modified, and no agent lifecycle stage changed. To reverse: delete `docs/REPO_AUDIT_2026-07-30.md` and remove its entry from the README repository map, or revert the commit. Nothing in this record grants authority, promotes an agent, or activates a capability.
