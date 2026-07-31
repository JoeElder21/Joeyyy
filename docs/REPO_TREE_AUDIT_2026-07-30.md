# Repository Audit — 2026-07-30

Full-tree audit of the Agent 007 repository: architecture inventory and an
evidence-backed inefficiency review. Every claim below was checked by running
the code, not by reading it alone. Findings are ordered by severity; the
remediation status column reflects work landed in the same change as this
record.

Measurements taken at commit `c546e4f` on Python 3.11.15.

## Correction — the audit ran against a stale tree

**Read this before trusting any measurement below.** The working clone was
`c546e4f` when this audit ran. `origin/main` was already ~200 commits ahead:
constitution adoption, a vendored agent corps, ruff and gitleaks gates,
restructured per-tier locks, `runtime/mission_runner.py`, `runtime/value_meter.py`,
the Market Operator agent, and four CI workflows. Every scale figure in Part 1
is therefore understated, and several Part 2 findings were fixed on main before
this record was written.

Re-verified against `origin/main` at `4c0f46e`:

| Claim below | Actual on current main |
| --- | --- |
| 241 tests, ~2s | **1,083 tests, ~157s**, 36 test modules |
| 27 docs, 3,305 prose lines | **40 docs** |
| CI never runs `verify_runtime_stack.py` (finding 17) | **Already fixed** — it is a step in the `validate` job |
| The 269-package lock is exercised by nothing (finding 13) | **Largely fixed** — CI installs `lock-runtime-root` and `lock-runtime-contracts`, and a `locks` job re-resolves each manifest with pinned `uv` to catch drift |
| `runtime/autogen_groupchat.py` is legacy (finding 8) | **Withdrawn** — main's README documents it as a live brain-private planning adapter |
| `privacy_guard.py` has no allowlist (finding 22) | **Superseded** — the guard now carries basename and per-pattern allowlists and is far larger |
| No `.claude/` directory or skills (Part 1) | **Superseded** — `.claude/agents/` now holds the corps projected into Claude Code subagents |

Findings re-confirmed as still live on `4c0f46e`:

- **Finding 1** — the lifecycle-gate bypass. `scripts/orchestration_graphs.py`
  on main still carries its own `ACTIVE_GATES` with no `joe_approved_activation`
  and no gate-21 check, and `runtime/lifecycle.py`'s `active_gate` is unchanged.
  Fixed by the change that carries this record.
- **Finding 10** — the seam is still inverted, and worse than recorded:
  `packet_guard.py` remains in `scripts/`, and `runtime/` now imports from
  `scripts/` in two modules (`autogen_orchestrator.py`, `mission_runner.py`)
  rather than one.
- **Finding 5** — the .NET Self-Learning Architect is still unregistered in
  `docs/AGENT_REGISTRY.md`.
- **Finding 7** — roster data is still stated across the corps config and both
  brain manifests.
- **Finding 18** — `trial/output/cadence-log.md` still has exactly one line.

Findings not re-verified are marked by their original date and should be
re-measured before being acted on. The lesson is recorded rather than
explained away: an audit is only as current as its fetch, and this one did not
fetch first.

### The full-stack CI job was attempted and withdrawn

Finding 16 proposed a CI job installing the whole runtime stack so the
dependency-gated tests would run somewhere. It was written, pushed, and failed:

```
ERROR: Cannot install -r requirements/lock-2026-07-24.txt (line 36)
and posthog==7.29.0 because these package versions have conflicting dependencies.
    The user requested posthog==7.29.0
    chromadb 1.1.1 depends on posthog<6.0.0 and >=2.4.0
```

`requirements/lock-2026-07-24.txt` is **not installable**, and main already
knew: `docs/DEPENDENCY_AUDIT_2026-07-25.md` records the same conflict and lists
regenerating the lockfile as an open remedy. That is why the `validate` job
installs the per-tier `lock-runtime-root` and `lock-runtime-contracts` instead.

So the finding is sharper than first recorded, and it is not a CI-configuration
gap:

- There is **no committed lock that resolves the orchestration, memory, or
  observability tiers.** The only one that tried cannot be installed by any
  resolver, so the full stack has never been installed anywhere — not in CI,
  not on a workstation.
- `langgraph` is in that unresolvable set. The lifecycle `StateGraph` in
  `scripts/orchestration_graphs.py` therefore executes in no automated
  environment, which is how it carried divergent gate logic (finding 1)
  invisibly.
- Closing this needs a real dependency decision — regenerate the lock, which
  likely means pinning `posthog<6` or dropping whichever tier pulls `chromadb`
  (crewai). That is a scope and architecture call, not a mechanical fix, and it
  belongs to whoever owns the dependency policy.

The job was removed rather than left red or weakened into something that passes
without proving anything. `verify_runtime_stack.py --require-tier` was kept: it
is what such a job would need, and it makes the absence checkable the moment a
resolvable lock exists.

### Resolved 2026-07-30 — and what installing it exposed

On Joe's instruction the lock was regenerated. The conflict was not inherent to
the stack; it was an artifact of the lock having **no manifest behind it**. No
resolver had ever been asked to solve the set, so nothing forced `posthog` to
respect `chromadb`'s ceiling. Given a manifest
(`requirements/runtime-full.txt`), `uv` resolves it cleanly at `posthog==5.4.0`.

The old file was also **radically incomplete**: 269 pinned packages against a
true resolution of **1,053**. It could not have installed the full stack even
without the conflict.

`pip install -r requirements/lock-2026-07-24.txt` now completes, and
`verify_runtime_stack.py --require-tier all` reports `valid: true`,
`installed_count: 20`, `missing: []` — the first environment in this
repository's history where every declared runtime dependency imports.

Installing it immediately surfaced three defects that absence had been hiding.
Two were fixed; the third is a decision.

1. **`verify_runtime_stack.py` probed the wrong module for AutoGen.** It looked
   for `autogen_agentchat`; the pinned `autogen-agentchat>=0.2.35,<0.3` exposes
   `autogen`. The audit reported an installed, correctly-pinned dependency as
   missing. Fixed: the probe accepts either name.

2. **The same command's stdout contract broke under a real stack.** It emits a
   JSON document, but importing the stack writes to stdout — nltk downloads a
   corpus, dspy and typer emit `DeprecationWarning`. Callers parsing the output
   got a `JSONDecodeError`. Fixed: import side effects are redirected to
   stderr. The contract had held only because nothing was ever installed.

3. **Two mutually exclusive AutoGen APIs — resolved 2026-07-30.**

   | Module | Imports | Requires |
   | --- | --- | --- |
   | `runtime/autogen_orchestrator.py` | `from autogen import ConversableAgent, GroupChat, GroupChatManager` | AutoGen **0.2** |
   | `runtime/autogen_groupchat.py` | same | AutoGen **0.2** |
   | `scripts/group_debate.py` | `from autogen_agentchat.agents import AssistantAgent` | AutoGen **0.4+** |

   `autogen-agentchat<0.3` cannot provide `autogen_agentchat`, and `autogen_ext`
   — which `scripts/group_debate.py`'s tests also require — appears in **no
   manifest at all**. So `scripts/group_debate.py` cannot run under the declared
   dependency set, and its tests skip permanently even with the full stack
   installed.

   That matters more than a skipped test. `docs/RECONCILIATION_2026-07-24.md`
   closes build ticket 4 as "delivered by the Codex stream:
   `scripts/group_debate.py` (challenge-pair debates, cadence chats, dynamic
   selector per brain)". The registered challenge pairs are one of the system's
   core quality mechanisms — the adversarial review that keeps strategy honest
   against dated evidence. As configured, that mechanism is not merely inert:
   it is **unsatisfiable**.

   Converged on **0.2**, the pinned line: `scripts/group_debate.py` now imports
   `autogen` and builds `GroupChat`/`GroupChatManager`. The other two modules
   carry the governed, packet-validating, currently-passing path — including a
   speaker-selection guard that raises on a manifest-order violation, which 0.4
   has no direct equivalent for — so converging on 0.2 rewrote 179 lines that
   had never run instead of 454 lines that work.

   Two governance rules were added in the process, neither present in the 0.4
   version: `llm_config` may not carry `tools` or `functions` (a model-side
   tool grant bypasses `packet_only_no_direct_connectors`), and a selector chat
   with no model is refused rather than silently degrading to round-robin.

   Its tests now run fully offline via `llm_config=False` plus
   `default_auto_reply`, the pattern `tests/test_autogen_orchestrator.py`
   already proved — no model, no network, no unmanifested replay client. A
   registered APEX pair produces a real adversarial transcript. **Dependency-
   gated skips across the whole suite are now zero.**

   Migrating all three modules to the maintained 0.4 line remains worthwhile and
   is recorded as its own decision in `docs/SHADOW_EXIT_STATUS_2026-07-30.md`.

## Part 1 — What the repository is

A governance and contract repository, not an application. It defines a
cross-brain Chief of Staff (`apex_chief_of_staff`, alias Agent 007) governing
two isolated brains — APEX (professional) and JEOS (personal) — each staffed by
five brain-locked specialists, and it ships executable enforcement for the rules
that bind them.

### Inventory

| Layer | Contents | Size |
| --- | --- | --- |
| Agents | 1 governor (`workspace-write`) + 10 specialists (all `shadow`, read-only) + 11 retired with lineage | 11 native TOML definitions, 922 lines |
| Charter modes | 40 dream-team roles as modes of the ten specialists | `config/dream_team_roster.toml`, 364 lines |
| Contracts | 8 JSON schemas: delegation, handoff, writer lease, mutation result, memory record, roundtable memo, cross-brain constraint, brain-private constraint | 700 lines |
| Manifests | corps routing, 2 brain manifests, MCP mounts, project config | 2,213 lines TOML |
| Enforcement | `scripts/packet_guard.py` — fail-closed relational validation | 1,321 lines |
| Runtime (stdlib-pure) | lifecycle, cadence, writer leases + their graph/flow/queue layers, memory trial | `runtime/`, ~1,280 lines |
| Integration | governed dispatch (OpenAI + Anthropic), MCP server, evidence/memory/crew gateways, debates, observability, trusted launcher, validators | `scripts/`, ~4,220 lines |
| Connectors | 6 MCP mounts (2 offline-verifiable) + APS Node validation harness | `config/mcp_mounts.toml`, `connectors/aps/` |
| Tests | 24 files, 241 tests | 4,349 lines |
| Docs | 27 in `docs/` + README + AGENTS.md + a 1,102-line master plan | 3,305 lines |

There are **no skills in this repository** — no `.claude/` directory, no
`SKILL.md`, no hooks, no `settings.json`. The "Agent 007 skill" referenced in
`AGENTS.md` supplies cross-chat activation from outside this tree.

### What the design does well

Six mechanisms carry the quality claim, and they are real in code:

1. **Adversarial by construction** — 16 registered same-brain challenge pairs
   force strategy to defend itself against dated evidence and capacity reality.
2. **Evidence-bound artifacts** — a criterion cannot be marked `passed` without
   artifact record IDs, and artifact records cannot cite evidence that was not
   delegated. Confident fabrication is structurally rejected.
3. **Proof of mutation** — "done" means observed state exactly equals expected
   state, plus a verified rollback test with evidence.
4. **Fail-closed everywhere** — missing ledger, missing or expired lease,
   opposite-brain reference, downgraded sensitivity, legacy schema version: all
   reject before control transfers.
5. **Anti-self-promotion** — gate 21 in `runtime/lifecycle.py` refuses to let a
   validation-harness pass promote an agent, and activation additionally
   requires Joe's explicit approval.
6. **Tamper-evident audit** — SHA-256 hash-chained JSONL whose `verify()`
   detects any rewrite of history.

The repository is also unusually honest about what it has not proven:
`scripts/validate_specialist_corps.py` self-reports `named_agents_invoked:
false`, `connectors_called: false`, `real_missions_completed: false`.

## Part 2 — Inefficiencies

Root cause for most of what follows: 93 commits in four days across four
authors on parallel streams. `docs/RECONCILIATION_2026-07-24.md` was written to
resolve the resulting collisions and only partly succeeded.

### Tier 1 — correctness and trust

| # | Finding | Evidence | Status |
| --- | --- | --- | --- |
| 1 | **Two lifecycle engines; the `scripts/` one omitted the human checkpoint.** `scripts/orchestration_graphs.py` defined its own six-flag `ACTIVE_GATES` with no `joe_approved_activation` and no gate-21 harness-honesty check, so it could promote `shadow → active` with no human approval. `RECONCILIATION` ordered convergence "in its next change"; it had not converged, and `tests/test_reconciliation.py` locked cadence order but not gate parity. | Local gate tuple vs `runtime/lifecycle.py:115` | **Fixed** — graph now projects onto `runtime.lifecycle`; three parity tests added |
| 2 | **Zero of 20 runtime dependencies installed, and the audit could not fail on absence.** `verify_runtime_stack.py` returned `valid: true` with `installed_count: 0`; ~3,000 lines of integration code were inert. | Command output | **Partly fixed** — `--require-tier` added; host decided in `docs/RUNTIME_HOST_DECISION.md`; install is a workstation action |
| 3 | **Promotion deadlock.** `active` requires real missions; real missions require a runtime; no runtime existed. All ten specialists frozen in `shadow` since 2026-07-23 with no self-serviceable exit. | `validate_specialist_corps.py` output | **Unblocked, not resolved** — needs the workstation install and a pilot decision |
| 4 | **No memory layer is active**, with three competing approaches in-tree: mem0 gateway, graphiti trial, and the `.github/Lessons|Memories` markdown model. Reflection, weekly audit, error ledger, and durable learning all depend on it. | `RECONCILIATION_2026-07-24.md` | Open — Joe's decision |
| 5 | **An agent was installed in violation of the repository's own intake rule.** The .NET Self-Learning Architect appears nowhere except its own doc — not in `AGENT_REGISTRY.md`, corps config, README, or CI, against `AGENTS.md` "register every new agent". | Repository-wide grep | Open — register or remove |
| 6 | **`packet_guard.py` silently ignores unsupported JSON Schema keywords.** Its hand-rolled validator handles 12; the current 8 schemas use only those, so it is adequate today. The hazard is the failure mode: an unsupported keyword is ignored, not rejected, and the `jsonschema` cross-check was skipped everywhere. | Keyword audit of `schemas/` | **Mitigated** — the full-stack CI job now runs the `jsonschema` check |

### Tier 2 — maintenance drag

| # | Finding | Status |
| --- | --- | --- |
| 7 | Roster data stated four times: corps config, two brain manifests, and registry prose. One roster change is four coordinated edits. Challenge pairs written out twice verbatim. | Open — needs a source-of-truth decision |
| 8 | Four AutoGen modules with three separate `GroupChatPlan` classes, one self-described "legacy". | **Fixed** — legacy adapter and its test removed |
| 9 | Two cadence implementations kept in sync by a dedicated drift test rather than merged. | Open |
| 10 | Architectural seam inverted: `packet_guard.py`, the core enforcement engine, lives in `scripts/`, and `runtime/autogen_orchestrator.py` imports from it — against the seam rule in `RECONCILIATION`. | Open |
| 11 | Policy text duplicated across the chief's prompt, `AGENTS.md`, and `docs/`, with no consistency check. | Open |
| 12 | Doc sprawl: 3,305 prose lines against 5,593 code lines; six overlapping external-adoption docs; four same-day dated records; a 1,102-line master plan with no stated relationship to current state. | Open |
| 13 | Three conflicting dependency declarations and a 269-package lock exercised by nothing. | **Partly fixed** — the lock is now installed and gated by the full-stack CI job |
| 14 | `packet_guard.py` at 1,321 lines: single class, eight-way dispatch, a ~260-line `_handoff_errors`, no property-based coverage. | Open |

### Tier 3 — latent friction

| # | Finding | Status |
| --- | --- | --- |
| 15 | 241 tests run in ~2s and validate configuration, not behavior. A green build says the config is internally consistent and little else. | Open by design; the full-stack job narrows it |
| 16 | 27 skipped tests (11%) were exactly the integration proofs — including those that would have surfaced finding 1. | **Fixed** — full-stack CI job refuses dependency-skipped tests |
| 17 | CI ran three of the four documented `validate` steps; `verify_runtime_stack.py` never ran. | **Fixed** |
| 18 | The "recurring" cadence has one log line ever (2026-07-24); the hygiene sweep shells out to the full test suite from a module the tests import. | Open |
| 19 | Trusted launcher: every denial path proven by tests, zero mounts currently reachable. | Open — first grant is a workstation action |
| 20 | 40 charter modes registered with a knowingly truncated JEOS list, already used to justify amending the team-sizing rule. | Open |
| 21 | A fully specified five-ticket execution-layer trial with no installed candidate and no decision; one ticket is definitionally blocked. | Open |
| 22 | `privacy_guard.py` blanket-bans every binary and document format with no allowlist, so the repository cannot hold a diagram or screenshot as evidence. | Open |
| 23 | `.codex/config.toml` sets `max_concurrent_threads_per_session = 8` with no scheduler, queue, or runner. | Open |
| 24 | The `runtime/` ↔ `scripts/` seam rule is prose with no linter or CI check; findings 1 and 10 were both invisible to the build. | **Partly fixed** — gate parity is now tested; general import direction is not |
| 25 | The README is a hand-maintained 60-line file index, already drifting, untested. | Open |

### Corrected during the audit

`tests/fixtures/shadow_missions.json` carries `schema_version: "2.0"`. This was
initially read as a stale packet-contract stamp. It is not: the field is the
fixture file's own format version, the file contains mission descriptions
rather than packets, and `tests/test_specialist_corps.py` pins it deliberately.
No change was warranted.

## Assessment

The architecture is not the problem. Fail-closed admission, tamper-evident
audit, readback-proof mutations, and anti-self-promotion gates are better than
most systems of this kind ever get, and the refusal to overclaim is rarer than
the code quality. The problem is that four parallel authors building at 23
commits a day produced three implementations of the lifecycle contract, four of
the debate layer, and four copies of the roster, on top of a runtime with none
of its dependencies installed.

Consolidation and one working install were the whole gap. This change closes
the safety-critical half of it.
