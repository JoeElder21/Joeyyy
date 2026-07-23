# Absorbed Patterns — 2026-07-23

Capability-absorption record from the ecosystem repository analysis (`docs/ECOSYSTEM_REPO_ANALYSIS.md`). Ten external repositories were read completely per the absorption protocol in `docs/AGENT_COMMUNITY_PROTOCOL.md`; the smallest reusable orchestration, evaluation, recovery, memory, and packaging patterns were extracted. No prompts, identities, credentials, or access claims were copied.

Each pattern below is merge-ready text with its source named. Patterns marked **candidate merge** propose changes to an existing governance doc; adopt them individually through normal change standards (small, reviewable, reversible, with a recurrence test where behavior changes). Until merged, this file is the canonical record.

## 1. Delegation and dispatch

### Ticket-as-control-plane (files decide, not chat) — from Git-on-my-level/codex-autorunner

Store every delegated task as its own file with a machine-readable header: stable task id, assigned agent, and a done flag. The file is the single source of truth for task state — agents reload it from disk before acting and update it on completion; never track task state only in chat. Work open tasks in ascending order and write tasks so each is independently completable when its turn comes; prerequisites go in lower-numbered tasks. If chat and file disagree, the file wins. *Candidate merge: delegation packet rules, `docs/AGENT_COMMUNITY_PROTOCOL.md`.*

### Notify-only-when-stuck async loop — from codex-autorunner

Run delegated queues silently by default. Notify Joe only when an agent is blocked on a decision, credential, or approval it cannot resolve itself — not on routine progress. Every such notification names the task, states exactly what input is needed, and pauses only that task; unblocked tasks keep running. Batch non-blocking status into the daily brief instead of ad-hoc pings.

### Child-task spawning for discovered work — from codex-autorunner

When an agent discovers follow-up work mid-task (review needed, cleanup, tech debt), it spawns a child task instead of expanding the current task's scope. Each child task gets its own file, id, assigned agent, and done flag, names its parent task, and enters the queue behind it. The parent task stays single-scoped and closes on its original acceptance criteria; child tasks are triaged like any other intake.

### One durable terminal outcome per run — from codex-autorunner

Record exactly one durable outcome for every delegated run — ok, error, or interrupted — before the next queued task may start. If a resumed or duplicate run reports the same outcome, treat it as already complete; if it reports a different outcome, keep the first record and log the conflict to the error ledger. When a task exhausts its retry budget, mark it dead-lettered and escalate to Joe rather than retrying indefinitely.

### Dispatch discipline: one in-flight task per resource, queue-and-batch, respawn on crash — from block/buzz

Allow at most one task in flight per agent per resource; queue later requests instead of running them in parallel. When the agent frees up, batch the queued requests into one combined task rather than replaying them one at a time. If an agent process dies mid-task, detect the crash, restart the agent, and re-dispatch from the queue — a stalled resource must never fail silently. This serializes work at dispatch time and complements the one-designated-writer rule, which serializes at write time. Cap the number of concurrently running agents at a fixed, documented limit.

### Deterministic scope pre-computation before delegation — from alibaba/open-code-review

Before issuing a packet, Agent 007 pre-computes the task scope deterministically: the exact resource list in scope, the resources excluded and why, and the rule or checklist set matched to each resource. Group related resources into one packet so the specialist never needs another packet's context; isolated packets may run in parallel under the coordination rules. The specialist spends its reasoning on the delegated work, never on discovering scope. Record the pre-computed scope in the packet so handoff validation can check the return against it. *Candidate merge: delegation packet section, `docs/AGENT_COMMUNITY_PROTOCOL.md`.*

### Resumable delegation sessions — from open-code-review

Treat every delegation as resumable: the specialist records progress under the delegation ID so an interrupted task continues from the last completed unit instead of restarting. Before re-issuing a packet, list open sessions for that mission and resume the existing one if scope is unchanged. Re-delegate from scratch only when scope has changed. This prevents duplicate work and duplicate writes against the same resource.

### Squad-leader routing — from multica-ai/multica

When several specialists share a class, assign work to the class through one leader agent instead of naming a member directly. The leader claims the assignment, selects the member, and records the routing decision in the delegation packet. Callers keep one stable address per class, so the roster can change without rewriting delegations. A class leader routes only inside its own brain and class; Agent 007 remains the final integrator.

### Task lifecycle state machine with stale-task sweeper — from multica

Track every delegated task through explicit states — enqueued, claimed, running, completed, failed, cancelled — and record the timestamp of each transition. Run a periodic sweep that marks a task failed when it sits claimed-but-unstarted or running past a fixed threshold, and write the failure to the error ledger. Do not leave a delegation in an untracked in-between state; unknown state is a blocker, not a success.

## 2. Approval gates and human handoff

### Approval gate before anything leaves the system — from buzz

Any automation that files, sends, or submits anything outside the system — emails, permit submittals, agency uploads, client deliverables — must stop at an approval gate immediately before the send step. The gate names who must approve, shows exactly what will be sent, and carries a timeout (default 24 hours); an expired or unanswered gate fails the run closed, never auto-approves. Record the grant or denial, the approver, and the timestamp in the run's log. On approval, resume from the suspended step only — never re-run earlier steps. *Candidate merge: coordination rules, `docs/AGENT_COMMUNITY_PROTOCOL.md`.*

### Explicit human-handoff protocol for logins and captchas — from citrolabs/ego-lite

When a task reaches a step only Joe can perform — a login, a captcha, a signature — finish all safe preparation first, then hand the resource to Joe with exact instructions on what to do. Verify the hand-off actually registered before waiting. Resume only after Joe's explicit confirmation, through an explicit take-back step; never resume by detecting activity and assuming consent. Treat any signal that Joe is actively controlling the resource as a hard stop for the whole task: do not retry, work around it, or take over automatically. Standing requirement for any future permit-portal automation (LFUCG, KYTC, KDOW), where credentials and captchas are certain.

### Ownership as a recorded state machine — from ego-lite

Record an explicit owner state on every shared resource: agent-owned, delegated-to-user, or user-owned. Define what each operation does in each state — switching to a resource the agent does not own fails, an explicit claim is the only transition into agent ownership, and a hand-off or completion against the wrong state returns a checkable skipped result instead of silently proceeding. Treat an operation against the wrong state as a hard stop, not a retry. Check the returned result of every hand-off and completion before claiming it happened. This turns the one-designated-writer rule from a convention into a checkable state machine, and complements the v2.1 writer-lease model.

## 3. Error learning and recovery

### Hash-chained append-only error ledger — from buzz

Treat the error ledger as append-only: never edit or delete a past line, only add new lines, and keep one designated writer per the one-writer-per-resource rule. Append a chain field to each ledger line: a short hash of the previous line's full text, with a fixed constant for the first line. Any edit to history then breaks every hash after it, so the weekly audit can verify the chain and flag tampering or accidental rewrites. Write ledger lines in a fixed field order so the hash is reproducible. Never put credentials, keys, or client-sensitive material in a ledger line — record the fact of the failure, not the secret involved. *Candidate merge: error-learning section, `docs/AGENT_COMMUNITY_PROTOCOL.md`.*

### Ordered fallback chain with quota-aware demotion — from diegosouzapw/OmniRoute

For each recurring mission type, keep an ordered fallback chain of at least two agents or connectors, from preferred to last-resort. When a candidate is approaching its usage or quota limit, demote it within the chain instead of removing it; block it outright only when the limit is actually reached. Route each retry to the next chain entry, never back to the entry that just failed. Record the chain position used and any demotion reason in the error-ledger evidence field.

### Scope-matched failure isolation — from OmniRoute

Before correcting a failure, classify its scope: the whole platform, one account or credential, or one capability of one agent. Restrict only at the failing scope — pause a platform only for infrastructure-level errors, cool down a single connector for credential errors, and lock out a single agent mode for capability errors while the agent's other modes keep working. Never let an authentication or quota error on one account disable an entire platform or agent. Record the scope in the error-ledger root-cause field so the recurrence test targets the right layer.

### Exponential backoff with probe recovery and terminal states — from OmniRoute

After a failed delegation, wait before retrying and double the wait after each consecutive failure, up to a fixed cap. When the wait ends, send one low-stakes probe mission before restoring normal delegation; a failed probe restarts the cooldown at the next backoff step. On each success, halve the recorded failure count and clear the restriction when it reaches zero. Treat expired credentials, revoked access, and exhausted accounts as terminal: stop retrying, log the ledger line, and mark the agent or connector restricted in the registry until Joe resets it.

### Pre-exhaustion quota surfacing — from OmniRoute

Track usage of every rate-limited connector or paid account in a rolling window, in the units the provider actually limits (requests, tokens, or dollars). Surface remaining headroom and burn rate in the daily brief before a limit is hit, not after a rejection. While shared capacity is below half its limit, let any agent borrow unused headroom; past half, confine each agent to its planned share. Log any quota rejection that was not predicted by tracking as an error-ledger entry, because it marks a tracking gap, not a one-time output error.

### Incident mode: suspend exploration during widespread failure — from OmniRoute

When more than half of the agents or connectors serving a mission type are restricted at the same time, declare an incident. During an incident, suspend candidate-agent trials and any experimental routing, and delegate only to proven active agents until restrictions clear. Log the incident window, its trigger, and its clearance in the error ledger so the weekly audit can check for repeat incidents.

### Runs must be explainable from artifacts — from codex-autorunner

Require every agent run to leave enough on-disk artifacts to explain what happened, why, and where it failed. In the weekly audit, treat any run that cannot be reconstructed from its artifacts as a failed run, even if its output looks correct, and log it to the error ledger. *Candidate merge: weekly audit section and `templates/weekly-agent-audit.md`.*

### Independent anchor and reflection checks on specialist returns — from open-code-review

After a handoff packet arrives, run two independent checks before integration: an anchor check that every finding points at a resource, line, or record that actually exists in the delegated scope, and a reflection check that every claim is supported by the attached evidence. Run both checks outside the specialist that produced the work. Discard or flag findings that fail either check; never merge them. Log discarded findings in the error ledger so repeat offenders surface in the weekly audit.

### Trace-distilled minimal toolsets — from open-code-review

Give each specialist the smallest toolset its real work has demonstrated it needs, not the full generic set. During the weekly audit, review each agent's actual tool-call history: which allowed actions were used, which repeated without progress, and which failed. Remove allowed actions that were never used and record repeated or failing calls in the error ledger. Tighten the delegation packet's allowed-actions list to the observed minimum on the next cycle.

## 4. Agent 007 memory layer requirements

Blueprint requirements for the future cross-brain memory layer, absorbed from kentcdodds/kody's design. These bind any memory system adopted later, whether self-hosted or built.

### Verify-before-write memory discipline

Require a verify step before every memory write. Before any agent creates, updates, or deletes a durable memory record, it must first search existing memories for related records and review what comes back, then choose exactly one outcome: create, update, delete, or skip. Treat a blind memory write as a protocol violation and record it in the error ledger. This is the primary guard against duplicate and contradictory entries in the APEX and JEOS brains.

### Task-context memory surfacing with conversation-scoped dedupe

Surface memory through task context, not bulk recall. Each agent attaches a short task hint to its normal calls — current task, current query, key entities, key constraints — and the memory layer may return a small number of relevant, not-yet-shown memories alongside the normal result. Tag related calls with one conversation id so the same memory is never surfaced twice in the same conversation. Keep the hint brief and factual; it is a filter, not a transcript.

### Memory records carry source provenance

Every durable memory record must be able to name its source. Store optional source URIs on each record pointing at the canonical document it was derived from — a repo file, a drive document, a permit-portal page — so a stale or disputed memory can be re-verified against its source instead of trusted on faith. Keep categories freeform strings, but publish a suggested starter set (preference, identifier, relationship, workflow, project, profile) so APEX and JEOS agents converge on shared labels.

### Durable jobs: idempotency keys and run lists

Give every scheduled or long-running job an explicit idempotency key; submitting the same key again must return the existing run, never start a duplicate. Route work that can outlive one agent call — batch sweeps, migrations, polling loops, retryable steps — to a durable job runner instead of chaining short executions against a timeout. Keep a run list of recent jobs with statuses, and review it in the weekly agent audit.

### Capability as repo-backed package

Save reusable agent capabilities as repo-backed packages, not as loose prompt text. Each capability lives in the repo with a manifest, a stable scoped name, and its own storage, so improvements land as reviewed commits under the one-designated-writer rule and the capability stays discoverable through search. When one capability needs another, it invokes it by name after an input check, rather than copying its code.

## 5. Tool-surface design

Three sources converge on the same conclusion: a compact tool surface with vetted templates beats a large tool catalog.

### Meta-tools instead of fixed tool lists — from barbosaihan/civil3d-mcp

When giving an agent access to a large API, expose three meta-tools instead of one tool per operation: an execute tool for writes (changes committed), a query tool for reads (nothing committed), and a skills tool that lists, searches, and returns vetted code templates. The agent reads a template, fills in parameters, then runs it through execute or query. Grow capability by adding template files; never widen the tool surface itself. This keeps the read/write boundary enforced by the tool, not by agent judgment, which matches the one-designated-writer rule.

### Compact MCP surface: search plus execute — from kody

Prefer a compact tool surface over a large tool catalog. Expose one search tool that returns short ranked matches (result type, title, one-line summary, entity reference) and one execute tool that runs code against whatever search found, instead of registering every capability as its own tool. Let search be scoped to a named domain when the caller already knows it.

### Skill-as-code-facade with separated completion commit — from ego-lite

When wrapping a complex tool for agents, expose it as a small code runtime with a few preloaded object facades rather than many one-shot commands. Let the agent compose the whole multi-step task — observe, act, wait, verify — into one script and adapt in-process, instead of a call-look-call loop that burns rounds and tokens. Keep the completion claim separate from the work: print evidence that every requested outcome is proven, review that output, then commit completion in a distinct final step that performs no further work. Partial results, a stalled run, or exhausted retries are not completion evidence.

## 6. Skill packaging standards

### Per-skill SKILL.md structure with provenance line — from earthtojake/text-to-cad

Package each skill as one directory with a single SKILL.md. Start with frontmatter: a name and a description that lists the exact request types that should trigger it. Then use fixed sections in order: Purpose, Use-this-skill-when, Defaults (assumptions applied unless the user overrides), Tool (the exact run command), Workflow (numbered steps), Validation (programmatic checks), and Handoff (what the final response must include). Add one provenance line naming the source repo, and state that the installed local files are the runtime source of truth. *Candidate merge: skill-packaging standards, `templates/agent-intake.md`.*

### Validation-first skill authoring — from text-to-cad

Every skill that produces a file artifact must define programmatic pass/fail checks the agent runs after generation — entity counts, closure flags, extents, and every dimension stated in the brief — never visual inspection. List the exact checks in the skill doc next to the generation steps. The agent reports only checks that actually ran; if a check could not run, say so instead of claiming validation. An artifact that fails a check is regenerated from source, not hand-patched.

### Dual Claude Code + Codex packaging from one skill source — from text-to-cad

When a capability must run on both Claude Code and Codex, keep one repo of skill source and generate provider-native plugin outputs from it; do not maintain two copies. Add a marketplace manifest listing each plugin's name, source directory, version, and description. Keep generated installer outputs on the release branch only and develop on a separate branch, so an install never pulls a half-built skill. Record both provider install commands in the agent's intake entry.

### Skill template file format (.skill.md) for executable capabilities — from civil3d-mcp

Record each reusable capability as one markdown file with YAML frontmatter: name, category, one-line description, requires_write (true/false), and a parameters list giving each parameter's name, type, required flag, and description. Below the frontmatter, add a Code Template section with the runnable pattern and a Usage Notes section listing constraints, units, and failure cases. Name files `<name>.skill.md` and group them in category folders so they can be listed, keyword-searched, or read individually without a central registry. At intake, require the requires_write flag so the audit can verify each capability routes through the correct (read or write) execution path.

### Declared execution blocklist for code-running agents — from civil3d-mcp

For any agent that executes code, record an explicit blocklist in its intake entry, not just an allowed scope. Default blocklist: process execution, file deletion, network requests, registry access, and dynamic code loading; state what remains allowed (the domain API only). Any exception must be written into the entry with a reason. Re-verify the blocklist at each weekly audit.

### Skills as compounding knowledge, mounted at task start — from multica

After a specialist solves a repeatable problem, capture the solution as a named skill file rather than leaving it in conversation history. Mount the relevant skills into the working directory at task start, in the location the runtime natively reads, so reuse requires no per-task reconfiguration. Review the skill inventory during the weekly audit and retire skills whose benefit no longer covers their maintenance burden.

### Benchmark suite as markdown task files with test-case tables — from text-to-cad

Keep a benchmarks folder where each agent design task is one markdown file: a fixed prompt, then a Test Cases table pairing each check with its expected result. Include at least one negative check per task — features the output must NOT contain — to catch over-generation. Re-run the suite after any skill, prompt, or model change and record pass/fail per table row, not an overall impression. Keep benchmark markdown in normal Git for readable diffs; store heavy result assets in Git LFS.

## 7. Recurring automation

### Named automations with declared concurrency policy — from multica

Define each recurring agent job as a named automation with one owner agent, an execution mode, and a concurrency policy — skip, queue, or replace — declared before the first run. Attach triggers separately from the job definition: a cron schedule with an explicit timezone, an authenticated webhook, or a manual run. When a trigger fires while a prior run is still open, apply the declared policy instead of deciding ad hoc. Record every firing as a normal task so it enters the same audit trail as delegated work. *Candidate merge: `docs/BRAIN_CADENCE_RUNBOOK.md`.*

## 8. Registry and identity

### Per-agent identity with scoped access and attributable audit trail — from buzz

Give every agent its own identity — its own account, key, or named login — and never let two agents share credentials. Each registry entry must record three things: the identity the agent acts under, the exact scopes it holds (read vs. write, which brain, which tools), and where its action log lives. Every action must trace to exactly one agent identity so an audit reconstructs who did what without guessing. Keep an agent's APEX and JEOS footprints scoped separately even when one agent serves both brains. When an agent moves to restricted or retired, revoke or rotate its identity — do not just edit the registry row. *Candidate merge: registry entry template, `docs/AGENT_REGISTRY.md`.*

## 9. APEX Civil 3D developer-agent standards

Absorbed from shtirlitsDva/Autocad-Civil3d-Tools — the reference exemplar of a practicing engineer maintaining production Civil 3D .NET plugins with AI agents in the loop. These apply the day APEX starts writing its own Civil 3D automation.

### Evidence-first operating mode for developer agents

Run APEX developer agents in evidence-first mode. Tag every key claim [Verified] or [Unverified] with a source and a confidence score; forbid speculation, ballpark numbers without sources, and fabricated links. When data is insufficient, ask a bounded set of clarifying questions and wait; if still lacking, write "I cannot verify this" rather than guessing. When sources disagree, surface the divergence and plausible reasons instead of silently averaging.

### Agent-invokable per-project build scripts

Keep one agent-invokable build script per project at the repo root and document them in a table in the agent-facing doc: script name, project, configuration. State toolchain constraints explicitly — Civil 3D .NET plugins reference COM interop assemblies that `dotnet build` cannot resolve, so scripts pin the full MSBuild path. Require quiet, errors-only output so an agent can read the build result without parsing a full log.

### Domain-knowledge section in agent-facing docs

End every agent-facing repo doc with a short Domain Knowledge section explaining the real-world objects behind the CAD entities the code manipulates. State how each object type is drawn and what a Civil 3D corridor, pipe network, or surface represents on the ground. Keep entries to a few sentences per object type; an agent that misreads geometry semantics writes wrong code that still compiles.

### Git-worktree parallel-agent discipline

Run parallel developer agents only in separate git worktrees — one worktree, one branch, one agent — which enforces the one-designated-writer rule at the filesystem level. Before parallelizing, confirm the tasks touch different files or modules; keep same-file, dependent-output, or shared-state work sequential. Initialize dependencies in each worktree, name each agent session after its task, and merge through normal branches or PRs. Remove the worktree and prune stale references once the branch merges. For quality-critical changes, run a second agent as reviewer in its own worktree with no implementation context, so the review is unbiased.

### Headless AutoCAD Core Console batch runner

For batch operations across many drawings, use headless AutoCAD Core Console (`AcCoreConsole.exe`) instead of the full GUI. A small driver reads a text file listing drawings and runs the console once per file with `/i <drawing> /s <script> /product C3D /loadmodule AecBase.dbx`, waiting for each exit before starting the next. This turns repetitive drawing edits into scriptable, agent-triggerable jobs with no open AutoCAD session. Record the exact exe path and script path before first use, and verify output on one drawing before running the full list.

## 10. Seed spec: APEX civil DXF exhibit generator — from text-to-cad

A home-grown APEX skill to build later, on this pipeline: convert the request into a short brief covering outline dimensions, layers, units, output path, and validation targets; then write a Python source where every meaningful dimension is a named parameter and a `gen_dxf()` function returns an ezdxf document (ezdxf is a Python DXF read/write library). Run the source through a small launcher script that owns output paths and writes the .dxf; never hard-code output paths in the generator. Set units explicitly on the document and keep boundary geometry, easements, and annotation on separate named layers so downstream tools classify them correctly. Validate programmatically — entity counts by layer, closed-polyline flags on parcel and boundary loops, drawing extents, and each briefed dimension — and report only checks that ran. Keep the generator .py and its .dxf output side by side with the same basename so every exhibit regenerates from source instead of hand edits.

## Rollback

This file is additive. Rolling back the absorption is deleting this file and the registry's candidate-infrastructure references to it; no existing governance rule was modified by this record.
