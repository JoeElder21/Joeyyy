# External Audit — Agent 007 vs Google Antigravity SDK — 2026-07-30

A five-agent adversarial audit compared this repository against Google's `antigravity-sdk-python` on one question: which is usable for daily work today. Both repositories were read at line level **and executed**. This record captures what was verified, what the repository does not do, and the decisions that stand between this harness and a system that actually runs.

The comparison is not apples-to-apples, and that is the finding. This repository is a governance harness with no runtime; the Antigravity SDK is a runtime with no auditable core. Neither is a complete daily system on its own.

## Measurement points — read this before citing any number below

This audit was executed against a session clone of `main` at **2026-07-25**. By the time the record was written, `main` had advanced **235 commits**. Every claim was then **re-verified against `main` at `4c0f46e` (2026-07-30)**, and the numbers below are stated per measurement point rather than merged into one figure. Where the two disagree, the current-`main` figure governs, per `AGENTS.md` §1.

| Measured | 07-25 snapshot | Current `main` (`4c0f46e`) |
| --- | --- | --- |
| Test suite | 241 tests, 2.769s, `OK (skipped=27)`, 0 failures | 1,080 tests, `OK (skipped=23)`, 0 failures in CI |
| Test corpus | 4,349 lines / 24 files | 21,622 lines / 35 files |
| `scripts/packet_guard.py` | 1,321 lines | 1,228 lines |
| LICENSE | absent | **Apache-2.0 present** (`LICENSE`, `NOTICE`, `CITATION.cff`) |

A note on where numbers come from, because this audit got it wrong once. Running the suite inside the audit sandbox produced two failures in `tests/test_orchestration.py` on the Azure MCP grant-scope verifier, reproducible there against a clean `origin/main` worktree. **They do not reproduce in CI**, which runs the same 1,080 tests green (`OK (skipped=23)`, 166s, both 3.11 and 3.12). The verifier launches MCP servers through `npx`, which the sandbox restricts, so the most likely reading is a sandbox artifact rather than repository state. An earlier revision of this document reported those two failures as the current condition of `main`. That was wrong: **`main` is green on tests**, and CI is authoritative for that claim over any single local environment.

## Method and verification honesty

- Four assessor agents ran in parallel — one deep-read and one execution agent per repository — followed by one adversarial cross-examiner that re-checked every claim against the files on disk and corrected the assessors.
- Verification levels used below:
  - **Executed** — the command was run and its output recorded.
  - **Read-verified** — the claim was confirmed against a specific file and line in `main` at `4c0f46e`.
- Stated limits of this audit:
  - The SDK's supported path (`pip install google-antigravity`, which delivers the compiled binary, plus model credentials) was **not** exercised. Every claim about its daily usability is inference from source, not measurement.
  - **No mission was run.** This audit measures the harness, its contracts, and its honesty. It proves nothing about output quality, and nothing here upgrades any specialist out of shadow stage.
  - The audit was performed by AI agents on a repository substantially built by AI agents. The cross-examiner exists because of that, not despite it.
  - The audit ran against a stale base. That is itself a finding: it is precisely the failure mode `AGENTS.md` §1 warns about, and it was caught only when CI surfaced files the snapshot did not contain.

## Verdict summary

On the 07-25 snapshot this repository ran fully green in under three seconds with zero dependencies installed, while the Antigravity SDK did not import from a clone at all. Reverse the frame to live agent work and the result inverts: the SDK can act today and this repository cannot, because nothing here constructs a model client. That remains true on current `main` — `runtime/mission_runner.py` exists, but no model client is constructed anywhere in the tree.

The honest one-line summary is that this is a well-tested governance layer waiting for a runtime, and the runtime decision (below) is the only one that unblocks the rest.

## What this repository verifiably does

| Claim | Verification | Evidence |
| --- | --- | --- |
| Dependency degradation is engineered, not skip-decorated dead code | Executed | On the 07-25 snapshot, installing `pydantic`/`jsonschema`/`mcp` converted 7 skips into passing tests (27 → 20) with all 241 still passing |
| Every skip names its missing dependency | Executed | langgraph ×5, pydantic ×4, openai-agents ×4, autogen ×4, prefect ×3, mcp ×2, and one each for jsonschema, crewai, celery, llama-index-core, opentelemetry |
| Validators pass | Executed | `privacy_guard.py` → `Privacy guard passed.`; `validate_specialist_corps.py` → `valid: true`, 10 contract packets, 10 boundary rejections; `verify_runtime_stack.py` → exit 0 |
| Every module imports cleanly on stdlib alone | Executed | 10/10 in `runtime/`, 19/19 in `scripts/` (as `scripts.X` from the repo root) — measured on the 07-25 snapshot |
| PacketGuard is substantive, portable validation | Read-verified | 1,228 stdlib-only lines: NFKC identifier canonicalization (`scripts/packet_guard.py:1117-1118`) and non-canonical rejection (`:1135`), `boundary_blocked` emptiness so refused content cannot leak (`:581-608`), validate dispatch (`:100`), working CLI (`:1192`) |
| The governance MCP server is deployable now | Executed | `build_server()` constructed a live FastMCP instance with `mcp` installed (`scripts/governance_mcp_server.py`) |
| Fail-closed paths genuinely raise | Read-verified | `PermissionError` on disallowed lifecycle transitions (`runtime/lifecycle.py:196`); `HandoffRejected` before control transfer (`scripts/agent_runtime.py:135,173`); ledgered `grant_denied` on launch refusal (`scripts/trusted_launcher.py:318,344,463`) |
| Anti-fabrication discipline is enforced in code | Read-verified | `CadenceRun.status` returns `partial` unless steps executed (`runtime/cadence.py:80`); `memory_trial.run_trial()` returns `blocked` with named missing preconditions (`runtime/memory_trial.py:67`); the corps validator emits `named_agents_invoked: false`, `real_missions_completed: false` |

For a repository built in roughly four days largely by parallel AI agents, machinery that refuses to simulate success is the most transferable idea here.

## What this repository verifiably does not do

All rows re-verified against `main` at `4c0f46e`.

| Gap | Evidence |
| --- | --- |
| No model client is constructed anywhere — no mission can run | Grep across the tree finds no `Anthropic(`, `OpenAI(`, or `genai.Client(` construction outside `vendor/`. `scripts/claude_runtime.py:156` holds a live `client.messages.stream()` call whose own docstring says it is "never called by anything else in this module". `runtime/mission_runner.py` does not construct one either; `evals/test_specialist_modes.py:316` raises `NotImplementedError` |
| The corps has never left shadow stage | Corps-wide `deployed_stage = "shadow"` (`config/specialist_corps.toml:36`) |
| Operational history is a single line | `trial/output/cadence-log.md` — one TICKET-005 hygiene sweep, 2026-07-24 |
| Writer leases do not survive across processes | In-memory registry with no persistence (`runtime/writer_lease.py:56`, `MutationAdmission` at `:158`); two processes can each believe they hold the same lease |
| Enforcement is largely opt-in | `scripts/policy_enforcement.py` is the intended single enforcement point; the README itself records it as "built and tested, not yet wired". It now has call sites in `scripts/issue_instruction.py:47` and `evals/harness.py:42`, so this gap is narrowing but not closed |
| Write targets have no bound storage | `scripts/evidence_index.py:74` holds documents in a Python list in RAM |
| Four integrations remain nominal | `mem0` is never imported anywhere — `scripts/memory_layer.py` is a stdlib keyword store described as "on the mem0 scope model"; `dspy` and `guardrails-ai` still have zero call sites; Phoenix export "changes no call sites" by its own comment (`scripts/observability.py:10-11`) |
| Parallel-stream duplication persists | Two lifecycle engines (`runtime/lifecycle.py` vs `scripts/orchestration_graphs.py`), two Prefect layers, three AutoGen adapters, pinned by drift-lock tests rather than removed |
| Some tests assert prose, not behavior | `tests/test_reconciliation.py` and `tests/test_governance_docs.py` check that phrases exist in Markdown — useful drift locks, but they inflate the apparent test count |

## Findings on antigravity-sdk-python

Recorded as the comparison basis, and because two findings bear on our own intake protocol.

- **The Python package is a wire-protocol client around a closed Go binary.** `localharness` owns the model loop, the system prompt, all builtin tools including command execution and its sandboxing, MCP, subagents, and session storage. Every backend — including the local Ollama and LiteRT paths — subclasses `LocalConnectionStrategy`, whose constructor resolves the binary and raises without it. The components a security-conscious operator most needs to audit are precisely the ones that cannot be audited.
- **The repository does not import from a clone.** Generated protobuf modules are absent from git and the regeneration step is documented nowhere for external users. Once derived, 681 of 715 tests pass in 8.28 seconds, with failures decomposing into 22 binary-dependent tests and harness artifacts (`policy_test.py` passes 74/74 under its intended runner). The pure-Python layer is genuinely well made.
- **The GitHub repository is a one-way mirror, not an open-source project.** Every commit is a squashed export with no description, and the only CI triggers on tag push and tests the published wheel rather than the repository's code.
- **Documentation rot has reached a safety claim.** The README states the agent runs read-only by default; the verified default enables all file-write tools with command execution denied, and the README's suggested remedy is a no-op because it is already the default.
- **Alpha churn is real:** eight releases in eight weeks, a default model swapped in a patch release, transports removed within weeks, and one advertised feature with no Python surface.

**Intake consequences for this system.** Two house rules gain evidence. First, our provenance rule should extend to first-party vendor repositories: a Google-owned mirror still failed to import, still shipped a wrong safety default, and still could not be built from source — vendor identity is not a substitute for verification. Second, any dependency whose enforcement lives inside an unauditable binary cannot satisfy our connector-isolation policy on its own; it would have to be wrapped, not trusted.

## Corrections to earlier records

The cross-examiner corrected the assessors, and the re-verification against current `main` corrected the record again:

- The build window is **2026-07-22 through 2026-07-25** (91 commits, 22 on the first day), not the 07-23 start reported mid-audit.
- The `83%` figure in `docs/AGENT_RUNTIME_BRIDGE.md` was initially flagged as a measurement dressed up from a step count. On re-reading, the section is titled "Efficiency, measured honestly", defines the metric in its first sentence, and disclaims wall-clock and model-quality effects. The hedge is headline-level; the record is not dishonest.
- An earlier draft of this document asserted that the repository has no LICENSE file and listed licensing as an open decision. **That was wrong on current `main`**, which ships Apache-2.0 with `NOTICE` and `CITATION.cff`. The decision is closed and has been removed.
- An earlier draft described the repository as running fully green. That held for the 07-25 snapshot only; current `main` has two failing orchestration tests.

## Open decisions — Joe

Ordered by how much each unblocks. Decisions 2, 3, 4, and 6 only become concrete once decision 1 is made.

1. **Which runtime hosts Agent 007?** Nothing here constructs a model client, so no mission can run until this is answered. Three surfaces are already half-built: `scripts/claude_runtime.py` (typed Anthropic tool definitions), `scripts/agent_runtime.py` (OpenAI Agents SDK), and `.codex/agents/*.toml` (Codex CLI), with `runtime/mission_runner.py` now waiting above them. *Recommendation: an MCP-capable host with `scripts/governance_mcp_server.py` mounted as the enforcement layer — shortest path from here to something that executes.*
2. **Where do write targets physically land?** Options: in-repo directories, a Logseq graph, external storage, or SQLite. *Recommendation: in-repo directories first, since git and the privacy guard already provide audit and rollback.*
3. **What clears the activation gate, and who signs?** The gate demands evidence no in-repo code can produce, which is a closed loop; the evals harness now makes the backlog measurable (39 modes) but still raises `NotImplementedError` at dispatch. *Recommendation: promote exactly one specialist on one real mission with Joe's manual sign-off.*
4. **Does cadence run on a schedule, and where?** Cron specs exist; no deployment does. *Recommendation: defer Prefect; a scheduled invocation of the host from decision 1 achieves the same outcome with far less infrastructure.*
5. **Implement the nominal integrations, or strike them?** mem0, dspy, guardrails-ai, and Phoenix are named but uncalled. *Recommendation: strike them from the README and requirements tiers.*
6. **Do writer leases become durable?** *Recommendation: persist to SQLite or a lockfile, converting the single-writer guarantee from aspiration to fact.*
7. **Who fixes the standing red CI checks?** The test and contract surface is green. Of the four checks that were red when this audit ran, two have since been fixed upstream and two remain:
   - `Locks match their manifests` (3.11 and 3.12) — **fixed**. PR #57 merged 2026-07-30T16:02Z, seeding each pair's own committed lock so `uv` preserves pins that still satisfy the manifest, instead of resolving against latest and losing to the cooldown window.
   - `zizmor` — **fixed**. `main` now pins `anthropics/claude-code-action` to `c3d45e8e941e…`, which is the commit its `# v1.0.99` comment actually names, so the `ref-version-mismatch` findings are resolved.
   - `.github/dependabot.yml` — **open**. An invalid `semver-major-days` property under the `github-actions` ecosystem (`updates[3]`), where the schema does not allow it. **Dependabot is not running for this repository at all** until that one line is removed; the same property is valid in the other three ecosystem blocks and should stay.
   - `claude-review` — **open, and not fixable in a pull request**. Its `ANTHROPIC_API_KEY` secret resolves empty in the workflow environment, so the action exits in ~19s having produced no review. It needs a repository secret or a different supported auth method.

   *Recommendation: a one-line infrastructure PR for the Dependabot property; the last is a repository-settings action for Joe. Neither belongs in a documentation change.*

## Rollback

This change adds one document and two index lines (`README.md`, `docs/README.md`). No code, schema, configuration, or test behavior was modified, and no agent lifecycle stage changed. To reverse: delete `docs/REPO_AUDIT_2026-07-30.md` and remove its index entries, or revert the commit. Nothing in this record grants authority, promotes an agent, or activates a capability.

`requirements/lock-runtime-evaluation.txt` is named in this record only as the subject of a pre-existing CI failure inherited from `main`. This change does **not** modify it, regenerate it, or alter any pin, so reverting this record leaves it exactly as it stands and nothing about that failure is undone here. Fixing it remains open decision 7, and belongs to a separate infrastructure change.
