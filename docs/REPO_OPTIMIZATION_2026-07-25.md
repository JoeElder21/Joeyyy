# Repository Optimization Review — 2026-07-25

Agent 007 review of the Joeyyy repository itself: what the build is missing, what would
enhance it, and which external repositories fit the remaining gaps. This is a
**repository-engineering** review, deliberately distinct from the three existing
external-sourcing records:

| Existing record | Scope | This document's relationship |
| --- | --- | --- |
| `docs/ECOSYSTEM_REPO_ANALYSIS.md` | 14 repos Joe supplied (orchestration, memory, CAD) | Not repeated |
| `docs/FRONTIER_REPO_SCAN_2026-07-24.md` | Web-sourced frontier scan (execution, memory, MCP, CAD, governance) | Not repeated |
| `docs/EXTERNAL_RUNTIME_REGISTER_2026-07-24.md` | Declared runtime dependencies 11–24 | Not repeated |

Every candidate below sits in a gap **none of those three cover**: the software-engineering
substrate under the agent civilization — quality gates, supply-chain defense, and
output-quality evaluation.

## Verification honesty

Candidates were sourced by web search, then the top four were verified by reading their
canonical repository pages this session. Per the FakeGit finding in
`docs/FRONTIER_REPO_SCAN_2026-07-24.md`, each is labelled with how far verification went.
No Build verdict below is a deployment authorization; registry intake and an adversarial
verification pass still apply.

**One provenance finding, recorded because it is exactly what the FakeGit rule exists to
catch:** `invariantlabs-ai/mcp-scan` — the tool named in the frontier scan's security
discussion — now redirects to `snyk/agent-scan`. Invariant Labs was absorbed into Snyk, so
the redirect is legitimate succession, not a typosquat. But the old URL is now a dangling
name that an impostor could claim if the redirect were ever released. **Cite
`snyk/agent-scan` as canonical from now on; treat any future `mcp-scan` repo under any
other org as unverified.**

---

## Part 1 — What the repository is missing

The governance layer here is unusually mature: 241 tests, 8 JSON schemas, packet contracts,
writer leases, lifecycle gates, a privacy guard. The gaps are all on the **engineering
substrate** side, and they cluster into five findings.

### Finding 1 — Nothing tests whether the agents are any *good* (highest severity)

`README.md` states this plainly and honestly:

> The harness parses the configuration and validates synthetic v2.1 packets and fail-closed
> boundary probes. It does not invoke named agents, call connectors, complete real missions,
> or prove output quality.

That honesty is correct, and it is also the system's single largest structural gap. Every
one of the 241 tests is a **structural** test — schema validity, isolation, routing,
fail-closed admission. Zero are **behavioral** — did the specialist produce a correct
answer, call the right tool, stay in role, or refuse what it should refuse.

This matters most because of the acceptance gate the repository already defines. All ten
v2.1 specialists sit in `shadow`, and `docs/SPECIALIST_ACCEPTANCE_TESTS.md` requires "a
controlled real mission with evidence" before activation. Today that gate can only be
satisfied by Joe reading output and judging it by hand — which does not scale to ten
specialists across forty charter modes, and produces no regression signal when a prompt
changes. **The shadow-to-active pipeline is bottlenecked on a missing evaluation harness,
not on missing governance.**

### Finding 2 — CI is one job doing three of the six checks that exist

`.github/workflows/validate-agent.yml` runs `privacy_guard.py`,
`validate_specialist_corps.py`, and the unittest suite. The repository also ships
`verify_runtime_stack.py` and `verify_mcp_mounts.py` — **neither runs in CI**. Uncovered
entirely:

- **Python linting.** No linter, formatter, or style config exists, despite
  `docs/ECOSYSTEM_REPO_ANALYSIS.md` itself concluding "at most: PEP 8 + a linter step in CI
  as the house standard for agent-generated Python." Agent-generated Python is the majority
  of `scripts/` and `runtime/` — this is the house standard the repo prescribed for itself
  and never installed.
- **The Node connector.** `connectors/aps/` has a `package.json`, a lockfile, and real
  dependencies, and no CI job ever installs or checks it.
- **Dependency updates.** No `dependabot.yml`. Five `@aps_sdk/*` packages and eight Python
  runtime packages drift unwatched.
- **Workflow security.** Actions are floating tags (`@v4`, `@v5`), not SHA pins, and
  `actions/checkout` leaves credentials in the runner by default.

### Finding 3 — Supply-chain defense is documented but not enforced

`docs/FRONTIER_REPO_SCAN_2026-07-24.md` derived a hard rule from the FakeGit campaign:
verify provenance before any external repo is read for absorption. That rule currently
lives only in prose. There is no gate — no scanner, no checklist artifact, no CI step —
that can fail when it is skipped. For a repository whose entire premise is *absorbing
external agent capabilities*, this is the highest-leverage unclosed loop after Finding 1.

`scripts/privacy_guard.py` is genuinely good (regex secret classes, binary/LFS rejection,
tracked-file enumeration), but it is one homegrown scanner covering one direction:
preventing *outbound* leakage of Joe's data. Nothing covers *inbound* risk.

### Finding 4 — Contributor and consumer surface is absent

The repository is public and has none of: `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`,
`CODEOWNERS`, PR template, issue templates, `CHANGELOG.md`, `.editorconfig`, or
`.pre-commit-config.yaml`.

The **license is the consequential one**. A public repository with no license is
"all rights reserved" by default — nobody may copy, modify, or reuse it. That is a
legitimate choice for a personal governance system, but right now it is an *unstated
default* rather than a decision, and it silently blocks the repository from being cited,
forked, or built on. **This is left as Joe's decision — see Open Decisions below.**

The issue-template gap is a specific missed opportunity: `templates/agent-intake.md` and
`templates/weekly-agent-audit.md` are already-designed intake workflows sitting as loose
markdown. As GitHub issue forms they would become structured, trackable, required-field
workflows instead of documents someone must remember to copy.

### Finding 5 — 31 documents in `docs/` with no index

`docs/` holds 31 markdown records with no entry point. `README.md` carries a flat repository
map that has grown to ~50 bullets and now mixes protocol docs, runtime modules, config, and
dated records in one list. A reader — or an agent doing registry intake — has no ordered
path in. There is also no `CLAUDE.md`, so Claude-based runtimes get no repository guidance
while Codex-based ones get `AGENTS.md`.

---

## Part 2 — External repositories that fit these gaps

### Tier 1 — Adopt

#### 1. `confident-ai/deepeval` — closes Finding 1. Score 9/10, medium effort. **Verified.**

Apache-2.0, ~17.1k stars, ~9,900 commits, actively maintained. Pytest-shaped LLM evaluation:
test cases, reusable metrics, assertions, thresholds, and a CI-capable runner. The agent
metrics map almost one-to-one onto the acceptance criteria this repository has already
written down:

| DeepEval metric | Existing repository requirement |
| --- | --- |
| Tool Correctness — right tools, right arguments | `packet_only_no_direct_connectors`; connector-isolation verification |
| Task Completion / Goal Accuracy | `docs/SPECIALIST_ACCEPTANCE_TESTS.md` value gate |
| Role Adherence (multi-turn) | Brain locks; "specialists do not expand their own authority" |
| Knowledge Retention (multi-turn) | Memory-layer readback rules |
| Step Efficiency / Plan Adherence | Cadence-plan validation in `runtime/cadence.py` |

**Fit:** this is the missing half of the acceptance gate. Structural tests prove a
specialist *can't* misbehave; DeepEval proves it *does the job*. Recommended shape: a
`evals/` tree parallel to `tests/`, one suite per specialist material mode, run on demand
(not on every push) because judging costs model calls.

**Cautions, stated honestly:** most useful metrics are LLM-as-judge and need a model key, so
this cannot run in the public CI job without a secret — run it locally on the workstation
and commit only the scored results as acceptance evidence. It auto-logs to Confident AI's
cloud by default; **that must be disabled** before any APEX-brain evaluation touches it, per
`docs/PRIVACY_AND_DATA_BOUNDARIES.md`. Evaluation inputs are exactly the private material
that boundary document exists to protect.

**Alternative considered:** `promptfoo` — strong red-teaming, YAML-declarative, Node-based.
OpenAI agreed to acquire it in 2026 and plans to fold it into a commercial product; for a
system that deliberately keeps a governed local boundary, betting the acceptance gate on a
tool mid-acquisition is the weaker choice. Revisit if DeepEval's judge costs prove painful.

#### 2. `zizmorcore/zizmor` — closes part of Findings 2 and 3. Score 8/10, low effort. **Verified.**

MIT, ~5.9k stars, ~1,476 commits, Rust, actively maintained; audited by Trail of Bits in
May 2026. Static analysis for GitHub Actions with 38 audit rules: template injection,
credential persistence, cache poisoning, impostor commits, dangerous triggers. Runs as CLI,
pre-commit hook, or GitHub Action.

**Fit:** the repository's threat model is *supply-chain compromise of an agent system*, and
CI is the one place in this repo that executes third-party code with write-capable tokens.
The March 2026 `trivy-action` incident — a `pull_request_target` misconfiguration used to
exfiltrate secrets and then backdoor a package on PyPI — is precisely the class zizmor
catches. **Adopted in this change** (see Part 3); zero credentials, zero cloud, and it
already flags the two real issues in the current workflow.

#### 3. `gitleaks/gitleaks` — hardens Finding 3. Score 7/10, low effort. **Corroborated.**

Offline, regex-rule-first secret scanner; instant, no network calls, first-class pre-commit
hook. Complements rather than replaces `privacy_guard.py`: the homegrown guard encodes
Joe-specific rules (Drive links, street addresses, phone numbers, binary artifacts) that no
generic scanner has; gitleaks brings a maintained corpus of provider credential formats the
homegrown regexes don't cover. **Adopted as a pre-commit hook in this change** — local and
offline, so it adds no CI license dependency and no outbound calls.

`trufflesecurity/trufflehog` is the complement, not a substitute: it is verification-first
(live API calls to check whether a found credential is still active). Right tool for a
one-time full-history sweep, wrong tool for a pre-commit gate. Recommended as a **one-off
audit** of this repository's history, not a standing hook.

**Executed, not just configured.** The first version of this record said gitleaks was
"adopted as a pre-commit hook" when `pre-commit` had never been installed,
`.git/hooks/pre-commit` did not exist, and gitleaks had never run once. Both are now built
and executed: gitleaks is clean on the working tree (1.67 MB) and across history (69
non-merge commits — fewer than TruffleHog's 95 because `git log -p` produces no diff for
merge commits), and all 14 hooks pass. Running them immediately paid for itself by
surfacing a conflict between the whitespace hooks and the ezdxf-generated APS test fixture;
generated fixtures are now excluded rather than being rewritten on every regeneration.

The general lesson is worth more than the specific fix: **a configured tool and an executed
tool are different claims, and only the second is evidence.** A `.pre-commit-config.yaml`
in the tree proves a hook was written down, not that it runs or passes.

### Tier 2 — Evaluate

#### 4. `snyk/agent-scan` — closes the inbound half of Finding 3. Score 7/10, low effort. **Verified.**

Apache-2.0, ~2.8k stars, ~676 commits. The successor to Invariant Labs' `mcp-scan` (see the
provenance finding above). Scans MCP servers, agent skills, and agent applications for
prompt injection, tool poisoning, tool shadowing, toxic flows, malware payloads, and
hardcoded secrets — across Claude Desktop/Code, Cursor, VS Code, and others, on Windows.

**Fit:** this is the enforceable gate the FakeGit rule is missing. It scans exactly the
artifact classes this system absorbs, on the workstation OS the Civil 3D machine runs.
Natural home: a required step in `templates/agent-intake.md` and in the capability-absorption
checklist, before any external MCP server or skill is installed.

**Blocking caution:** it requires a Snyk API token and **transmits skill content, agent
application data, tool names, and descriptions to Snyk's servers** for validation. Under
`docs/PRIVACY_AND_DATA_BOUNDARIES.md` that is an outbound disclosure decision, not a tooling
decision. Scanning a *third-party candidate* before install is likely fine; pointing it at
Joe's configured agent estate would ship his roster off-box. **Verdict: evaluate under the
connector-policy review, scoped to pre-install candidate scanning only.**

#### 5. `cedar-policy/cedar` — formalizes the boundary layer. Score 6/10, high effort. **Corroborated.**

Open-source policy language and evaluation engine (AWS-originated) for fine-grained
permissions decoupled from application logic. 2026 saw working demonstrations of
Cedar-as-policy-decision-point for agent tool calls, including an AWS sample explicitly
targeting least-privilege in **multi-agent delegation chains** and OWASP Agentic ASI03
(Identity & Privilege Abuse).

**Fit:** this repository has already hand-built a policy engine — `packet_guard.py`,
`trusted_launcher.py`, writer leases, brain locks, `high-impact boundaries`. Cedar is what
that becomes when the rules are declarative and independently testable rather than
distributed across Python. The mapping is direct: brains as principals, connectors and write
targets as resources, packet types as actions.

**Verdict: absorb the pattern, do not replatform.** The current guards work and are tested;
a rewrite would trade proven code for a new dependency and a policy language to learn. The
extractable idea now, worth taking regardless: **a single explicit policy-enforcement point
immediately before tool execution**, rather than checks spread across the call path. Revisit
Cedar itself only if the boundary rules outgrow readable Python.

**Built: `scripts/policy_enforcement.py`.** Cedar's vocabulary transferred directly —
principal (acting agent and its brain lock), action (tool invocation and packet mode),
resource (connector, mount, or write target), context (writer lease, lifecycle stage, launch
grant). Eight rules, evaluated in full rather than short-circuiting, so a caller fixing a
denial sees every reason at once. It decides nothing new; every rule already existed and is
still owned by the module that implemented it. What changed is that a caller can no longer
perform the check set *partially*.

That distinction stopped being theoretical during the build. The first draft read lifecycle
stage and connector policy from `load_roster`, which reads `.codex/agents/*.toml` — files
carrying neither field. Both rules silently returned "no objection" for every agent: no
error, no failure, the checks simply never ran. **Two of eight rules were decorative and
nothing said so.** That is precisely the fail-open-by-omission the consolidation exists to
eliminate, it survived code review, and it died the moment the module was actually executed.
`tests/test_policy_enforcement.py::test_no_rule_silently_no_ops` now fails if any rule
becomes unable to deny anything.

### Tier 3 — Reference, no action

| Repository / project | Verification | Note |
| --- | --- | --- |
| `astral-sh/ruff` | Verified (in use) | Adopted in this change, lint-only at first because the formatter would have reformatted 46 files and made the diff unreviewable. Both were enabled the same day per decision 4 below — the reformat landed as its own mechanical commit, and the widened rule set as another. |
| `google/osv-scanner` | Corroborated | Vulnerability scanning against the OSV database for both Python and npm trees. Cheap and credential-free, but most Python deps here are optional and loosely pinned, so signal would be low until `requirements/lock-*.txt` governs the real install. Revisit when the lockfile is authoritative. |
| `arize-ai/phoenix` | Already registered (ID 14) | Already in `EXTERNAL_RUNTIME_REGISTER`; noted here only because it is OpenTelemetry-native and `scripts/observability.py` already emits OTEL spans — it is the shortest path from existing instrumentation to evaluation traces if DeepEval's own tracing is not wanted. |
| `trufflesecurity/trufflehog` | Corroborated | One-off history sweep, per Tier 1 #3. Not a standing gate. |

---

## Part 3 — What was implemented in this change

Everything below is reversible, tested, and additive. No governance rule, packet contract,
schema, or agent definition was modified.

**Closing Finding 2 (CI coverage):**
- `.github/workflows/validate-agent.yml` — added `verify_runtime_stack.py` and
  `verify_mcp_mounts.py` to the validation job; added a `lint` job (ruff); added a
  `connectors` job that installs and syntax-checks the APS Node harness; pinned every action
  to a full commit SHA; set `persist-credentials: false`; added least-privilege `permissions`
  and a `concurrency` group that cancels superseded runs.
- `.github/workflows/security.yml` — new: zizmor static analysis of the workflows
  themselves, on push, PR, and a weekly schedule.
- `.github/dependabot.yml` — new: weekly updates for pip, npm (`connectors/aps`), and
  GitHub Actions, grouped to keep PR volume low and keep the new SHA pins current. Each
  ecosystem carries a cooldown (7 days, 14 for majors) before a brand-new version is
  adopted — see the note below.

**zizmor earned its place on its first run.** The initial CI run reported zero findings
against the hardened workflows and three against the brand-new `dependabot.yml`:
`dependabot-cooldown`, high confidence, all three fixed here. The audit's point is
specific and correct for this threat model — a compromised package release is typically
detected and yanked within days, so an update bot that adopts new versions the moment they
publish is the one way automation makes supply-chain risk *worse*. A cooldown converts
Dependabot from an exposure into a defense. This is the finding class that would have
mattered in the March 2026 `trivy-action` → PyPI incident, and it was caught by a tool
adopted in the same change.

**Closing Finding 3 (supply chain):**
- `.pre-commit-config.yaml` — new: gitleaks, ruff, generic hygiene hooks, plus
  `privacy_guard.py` and `validate_specialist_corps.py` as local hooks so the house gates run
  before a commit exists rather than after it is pushed.

**Closing Finding 4 (contributor surface):**
- `SECURITY.md`, `CONTRIBUTING.md`, `.editorconfig`, `CHANGELOG.md`, `.github/CODEOWNERS`,
  `.github/pull_request_template.md`.
- `.github/ISSUE_TEMPLATE/agent-intake.yml` and `absorption-candidate.yml` — the existing
  paper workflows converted to structured issue forms. The absorption form makes the FakeGit
  provenance check a **required field** rather than a paragraph in a document.

**Closing Finding 5 (navigation):**
- `docs/README.md` — new: the 31 documents indexed by purpose, in reading order.
- `CLAUDE.md` — new: repository guidance for Claude-based runtimes, pointing at `AGENTS.md`
  as the single source of truth rather than duplicating it (duplication is how the two
  drift apart).

**Closing the gap between recorded and running (2026-07-25, second pass):**

An audit of this record against the repository found several Part 2 verdicts were paper.
Each is now executed rather than described:

| Item | Was | Is |
| --- | --- | --- |
| gitleaks | In `.pre-commit-config.yaml`; never installed, never run | Built and run. Clean on working tree and on 69 non-merge commits of history |
| pre-commit | Config committed; `.git/hooks/pre-commit` absent | Installed and passing all 14 hooks; fires on every commit |
| `packet_validity` | A sentence in the metric contract | `evals/packet_validity.py`, running the live `PacketGuard`; proven 1.0 on a valid v2.1 handoff and 0.0 on malformed, absent, and legacy packets |
| Cedar absorption | "Worth taking regardless" — not taken | `scripts/policy_enforcement.py`, 8 rules, 19 tests |
| `snyk/agent-scan` | Approved and wired into intake | Still unrun — needs a Snyk credential this environment does not hold. Honest status: **approved, not yet exercised** |

**Quality baseline:**
- `[tool.ruff]` config in `pyproject.toml`; the 4 pre-existing lint errors fixed
  (3 unused imports, 1 ambiguous variable name). No behavior changed.
- `tests/test_repo_hygiene.py` — new: 15 tests asserting the substrate cannot silently
  regress. Notably, one test fails if any GitHub Action is referenced by floating tag
  instead of a SHA pin — the SHA-pinning rule is now enforced, not just applied once.

## Decisions — all five resolved 2026-07-25 on Joe's instruction

Every open decision from the original review was answered the same day. Nothing in
Part 1 or Part 2 above was revised; this section records the outcomes.

1. **License — Apache-2.0, and the governance patterns are to be citable.**
   `LICENSE` carries the verbatim Apache-2.0 text (fetched from apache.org,
   sha256 `cfc7749b…`), `NOTICE` states the copyright and scopes what the grant
   does and does not cover, and `CITATION.cff` gives GitHub a "Cite this
   repository" entry. The citation abstract names the reusable contribution
   explicitly — the enforcement layer, not the roster — so a citation points at
   the patterns rather than at Joe's personal agent lineup.
   Apache-2.0 over MIT for the patent grant, which matters for a system whose
   reusable surface is architectural.

2. **DeepEval — adopted; results go to the Evaluations folder on Drive.**
   Built in `evals/`; full record in `docs/EVALUATION_HARNESS.md`. The Drive
   folder was created and the first artifacts published there. The harness makes
   the acceptance-gate backlog a number for the first time: **39 material modes,
   3 covered.** Results never enter this tree, and publication is a connector
   action rather than a library call — no script in `evals/` holds a Drive
   credential.

3. **`snyk/agent-scan` — approved for pre-install candidate scanning only.**
   Wired as a required section in
   `.github/ISSUE_TEMPLATE/absorption-candidate.yml` and as a provenance block in
   `templates/agent-intake.md`. Both state the scope limit in the same breath as
   the requirement: scan the candidate, never Joe's configured estate, because
   the tool transmits skill content and tool descriptions to Snyk's servers and
   the estate is his roster.

4. **`ruff-format` — enabled.** Applied as one mechanical commit, and enforced
   from then on in CI and pre-commit. Joe's instruction was explicit that the
   repository should keep evolving rather than settle at lint-only, so the
   expanded rule set (`I`, `UP`, `B`, `C4`, `SIM`) was adopted alongside it in a
   separate reviewable commit rather than deferred again.

5. **TruffleHog history sweep — run, clean.** Record:
   `docs/SECRET_HISTORY_SWEEP_2026-07-25.md`. Zero verified and zero unverified
   secrets across all 95 commits, confirmed by two independent passes with
   coverage verified against `git rev-list` rather than taken from the tool's own
   summary. The privacy guard's working-tree coverage can now be treated as
   complete coverage.

### Automated review, 2026-07-25 — nine findings, seven fixed

A Codex review of this PR raised nine findings. Seven were correct and are fixed;
two are carried forward deliberately. Recording them because several caught the
work doing precisely what this record criticises elsewhere.

| Finding | Verdict | Outcome |
| --- | --- | --- |
| `promotion_ready` derived from case files, not passed runs | **Correct, and the worst of the nine** | Split `cases_complete` (inventory) from `promotion_ready` (evidence); the latter now needs a recorded passing run per mode. Three tests pin it. |
| Brain lock treated an omitted `owner_brain` as no objection | **Correct** | A non-chief agent must now declare its brain; silence is not consent. |
| Writer lease trusted two matching strings | **Correct** | Lease is validated against its schema, status, expiry, brain, and resource id. A forged dict fails as a lease before any field is read. |
| DeepEval cloud logging documented but unenforced | **Correct** | The runner now sets the opt-out and refuses to run if telemetry is on or `CONFIDENT_API_KEY` is set. |
| `packet_validity` never received a packet | **Correct** | Dispatch returns `(output, packet)`; the packet travels in `additional_metadata`. |
| Case `expected_`/`forbidden_behaviors` fed no metric | **Correct** | New `case_criteria` metric, threshold 1.0 — a forbidden behaviour is not averageable. |
| Runs without `--run-id` overwrote each other | **Correct** | `--run-id` is required, and a non-empty output directory refuses rather than overwrites. |
| gitleaks only in pre-commit | **Correct** | Added to CI over working tree and history. A local hook protects nobody who uses the web UI or `--no-verify`. |
| `enforce()` not wired into execution paths | **Correct, carried forward** | See below. |

**Two things worth stating plainly.**

The `promotion_ready` bug is the one that matters. This record spends paragraphs
insisting that inventory is not evidence and that an unproven mode must read as
unproven — and then computed promotion readiness from JSON files existing.
Authoring 39 case files would have reported the corps promotable with zero
evaluations run. The principle was stated correctly and implemented wrongly, and
a reviewer caught it rather than the design.

**A defect surfaced while fixing the lease check, and it is not this PR's to
fix.** `runtime/writer_lease.py` issues `schema_version: "2.1"`, but
`schemas/writer_lease.schema.json` pins `const: "2.0"` — so **every lease the
registry produces fails its own schema**. Nothing caught it because the only test
spanning both checks required-field presence rather than the const, and the
packet-contract fixtures hand-build 2.0 leases. `scripts/memory_layer.py` would
already reject a real registry lease today. The enforcement point tolerates
exactly that one error string and nothing else, so forged leases still fail.
Resolving it means changing a schema — a contract decision, and this change set
promised to touch none.

### Automated review, second pass — eight findings, five fixed

A second Codex review went deeper than the first, into the enforcement point's
trust model. Five fixed, three carried forward.

| Finding | Verdict | Outcome |
| --- | --- | --- |
| `mutating` trusted from the caller | **Correct, and the worst of the eight** | Derived from the action; the flag can now only add strictness, never remove it. An `action="write"` with the flag left default previously skipped lease, lifecycle, and launch-grant entirely. |
| Lease never checked against the issuing registry | **Correct** | Lease id verified against `LeaseRegistry.active_lease`. A fully-populated fabricated lease now fails, and with no registry supplied no mutation authorizes at all. |
| Packet not bound to the invocation | **Correct** | Packet agent, brain, and resource are bound to the request, as `admit_delegation()` already did. A delegation for one specialist no longer authorizes another. |
| Case artifacts not in the manifests | **Correct, factual** | `qa_findings` and `reflection_note` were invented; corrected to `qa_risk_packet` and `reflection_synthesis`, with a test that every case artifact exists in its brain manifest. |
| `--run-id` accepted Windows separators | **Correct** | `..\..\name` escaped the gitignored tree on the documented Windows workstation. All separators and traversal components rejected, plus a resolved-path containment check. |
| `coverage.json` written before pytest, so `modes_proven` stays 0 | **Correct, carried forward** | Populating `passed` needs the JUnit result parsed back after the run. Real gap; no evidence is currently published, so nothing is misreported today. |
| Delegation ledger not passed to `packet_validity` | **Correct, carried forward** | `_validated_delegation` needs the originating delegation. Latent until dispatch is wired. |
| osv-scanner scans a lock that is not what CI installs | **Correct, carried forward** | `requirements.txt` resolves `autogen-agentchat>=0.2.35,<0.3` while the scanned lock pins 0.7.5, and the evaluation tier is absent entirely. Needs locks generated per install manifest — which the unresolvable lockfile blocks anyway. |

**The `mutating` finding deserves naming.** This module's entire argument is that
a caller must not be able to perform the check set partially — and its own
signature let a caller decline every mutation control by omitting one boolean.
The failure was in the interface, not the rules.

**Two fixes made the code more paranoid about itself.** A lease too malformed to
key used to raise out of the enforcement point; an enforcement point that throws
on hostile input is a denial of service on every legitimate caller sharing the
process. It now denies. And the artifact-type test closes the gap that let the
seed cases drift: the harness derives modes from the manifests precisely so they
cannot drift, and artifacts were the one field still hand-written — which drifted
immediately.

### Automated review, third pass — seven findings, six fixed

| Finding | Verdict | Outcome |
| --- | --- | --- |
| Brain lock compared the caller against itself | **Correct** | An APEX specialist could read `JEOS/Weekly` by declaring "APEX". Resource ownership is now resolved from manifest-declared prefixes and compared too. |
| Only `lease_id` checked against the registry | **Correct** | A genuine lease could be copied and its `writer_agent`, status, or expiry rewritten. Every field now reads the registry's object; the id is the lookup key, not the authorization. |
| `launch_grant_verified` was a caller boolean | **Correct** | HMAC-verified grant material required instead. Signature only — nonce consumption stays with the launcher, since a policy evaluation must not have side effects. |
| gitleaks binary downloaded unverified | **Correct** | Replaced with `go install` at a pinned version, verified through the Go checksum database. Pinning actions to SHAs and then executing an unverified binary in the same job was a contradiction. |
| Unit suite missing from pre-commit | **Correct** | Added. The block claimed to be the house gate while omitting the one check `AGENTS.md` names explicitly. |
| `node --check` never resolves imports | **Correct** | Now imports all five APS SDKs on a credential-free path, so a breaking upstream change fails in CI rather than first on the workstation. |
| `tools_called` never supplied | **Correct** | Dispatch returns the trace. `ToolCorrectnessMetric` was comparing against an empty observed list, so it would have certified exactly the connector isolation it could not see. |

**The pattern across three rounds is the finding.** Round two fixed a
caller-asserted `mutating` boolean; round three found `launch_grant_verified`,
the identical defect two rules away, untouched. Round two bound the packet;
round three found the tool trace unbound in the same file. Fixing an instance is
not fixing a class, and reviewing my own work did not surface the siblings.

**Two fixes also improved the tests that covered them.** The expiry and
closed-lease tests had been mutating the caller's copy — which the registry fix
now correctly ignores, meaning those tests had been asserting against a value
the code no longer consults. They now change registry state, which is what they
always claimed to test.

### Automated review, fourth pass — twelve findings, eleven fixed

The fourth round found three more P1s in the enforcement point, all of the same
shape: an authorization that stretched further than it was issued.

| Finding | Verdict | Outcome |
| --- | --- | --- |
| `packet_schema` was caller-controlled | **Correct** | A mutating request could set it to `writer_lease.schema.json` and pass admission with a schema-valid object that authorizes nothing. Admission now accepts only delegation and handoff schemas; a test asserts every other schema in `schemas/` is refused. |
| Writer-lease targets matched by `startswith` | **Correct** | A lease for `APEX/Strategy-Campaigns` covered `APEX/Strategy-Campaigns-Evil` — and any target reachable by appending characters. Exact equality now, matching `PacketGuard`. There is no declared resource hierarchy here, so prefix containment was inventing an authorization relationship rather than reading one. |
| Action casing bypassed the high-impact boundary | **Correct** | `_is_mutating()` lowercased; `_high_impact_boundary()` compared a raw string against a lowercase set, so `FINANCIAL_TRANSACTION` was classified as a mutation *and* walked past the explicit-instruction requirement. The request is now normalized once, before any rule runs. |
| Specialists could read connectors directly | **Correct** | Only the mutating path was guarded, so a shadow specialist could read `mount:gdrive` and be allowed — the exact access `packet_only_no_direct_connectors` names. Reads are denied too; Agent 007 does connector work on the corps' behalf. |
| A naive clock raised `TypeError` instead of denying | **Correct** | `datetime.datetime.now()` is the obvious thing to write, and against a timezone-aware lease expiry it crashed the evaluation rather than failing closed. Naive clocks are now a denial reason. |
| `enforce()` logged the caller's `mutating`, not the derived one | **Correct** | The audit trail described an inferred mutation as non-mutating — disagreeing with the decision it was recording, exactly during incident review. `Decision` now carries the normalized request and the ledger reads from it. |
| Judged metrics were "gated" by list order | **Correct** | `assert_test` runs every metric it is handed, so putting `packet_validity` first bought a full set of G-Eval calls on a packet the runtime would refuse. The gate is now an explicit branch before any judge runs. |
| `packet_validity` never received the originating delegation | **Correct** | `PacketGuard` refuses a handoff whose `delegation_id` does not resolve to exactly one validated delegation, so scoring the handoff alone failed every lawful packet — a metric that could only ever return zero. Dispatch now returns the delegations and they travel with the packet. |
| Brain-isolation judge could not see the case context | **Correct** | The JEOS weekly-reflection seed permits a professional-deadline reference only via its context; without it the judge was told to reject that reference as detail beyond the mission. A false failure built into the metric. `CONTEXT` is now an evaluation param. |
| Role judge read `class_id`, not `responsibility` | **Correct** | Mirrored specialists share generic class ids by design — both architects are `strategy` — so the judge could not tell professional campaigns from personal outcomes. `Mode` now carries the manifest's responsibility sentence. |
| `promotion_ready` ignored the longitudinal gates | **Correct** | One pass per mode is not what `docs/SPECIALIST_ACCEPTANCE_TESTS.md` requires. Renamed to `behavioral_modes_proven`, and every summary now emits `gates_not_modelled` naming what it excludes. Modelling those gates as data would duplicate the acceptance document and drift from it; naming the exclusion is the honest option. |
| `coverage.json` written before pytest, so `modes_proven` stayed 0 | **Correct** | Every published run permanently reported zero proven modes, so the harness could never produce the evidence its own gate demands. The runner now folds the JUnit results back in — skips and errors record nothing, because the whole suite skips when no runtime is installed. |
| Ruff unpinned in CI while pre-commit pinned `v0.14.6` | **Correct** | Pinned to match. An unchanged commit could otherwise start failing on a ruff release, and a contributor's local gate could disagree with CI about the same file. |
| MCP mount verification degraded to "unverified" and still exited 0 | **Correct** | The `mcp` package was never installed in CI, so the step launched nothing and went green regardless. Added `--strict`, installed `requirements/runtime-contracts.txt`, and moved it to its own job — probing the filesystem mount fetches from npm, and a registry outage should name itself rather than fail "Contracts and tests" twice over. |
| osv-scanner scanned a lock CI does not install | **Correct, and it found something immediately** | The lock pins `autogen-agentchat` 0.7.5; `requirements.txt` asks for `>=0.2.35,<0.3`. All three Python manifests are scanned now, and the first expanded run turned up `pytest` 8.0 (PYSEC-2026-1845, CVSS 6.8) in `runtime-evaluation.txt` — a documented install path that had been reporting clean. Fixed, not triaged: the floor moved to `>=9.0.3`. A scanner aimed at a file nobody installs reports clean for the same reason a scanner that never runs does. |

**The class, not the instance — again, and this time it was anticipated.** The
three P1s here are one defect wearing three hats: a check that reads a
caller-supplied value where it should read a constrained one. Rounds two and
three had already taught this (`mutating`, then `launch_grant_verified`), so this
round each fix was followed by a search for the same shape elsewhere in the file
— which is how the connector-read hole was found, since no reviewer had raised
it. The tests assert the property (every non-authorization schema is refused,
every high-impact action resists casing) rather than the reported example.

**One finding carried forward, unchanged from round one.** `enforce()` still has
no live call site. It remains the top follow-up, for the reason given below.

### Automated review, fifth pass — six findings, six fixed

| Finding | Verdict | Outcome |
| --- | --- | --- |
| `explicit_instruction` was a caller-set boolean | **Correct, and the worst finding of all five rounds** | See below. |
| Unresolvable resource ownership meant "no objection" | **Correct** | The brain lock held only over resources whose names matched a manifest prefix; `brains/jeos/agents.toml` resolved to nothing, so an APEX specialist reading it passed. Ownership now resolves brain-owned repository paths, and an unclassifiable resource is refused. A declared `BRAIN_NEUTRAL_PREFIXES` set is what makes fail-closed viable rather than an outage — without it a specialist could not read the contract defining the classification it is held to. |
| No authorization ledgers reached `PacketGuard` | **Correct** | `validate()` accepts `active_leases`, `delegations`, `constraint_packets`, and `private_constraint_packets`; the enforcement point passed none, so the guard refused any delegation referencing a validated constraint or carrying a real lease. The separate lease rule cannot lift a denial raised during admission, so lawful work was unpassable. The request now carries the ledgers and forwards them. |
| A scalar packet crashed the evaluation | **Correct** | `.get()` on `1` or `"bad"` raised `AttributeError` instead of denying. A gate that raises on caller-controlled input is a denial of service on every other caller in the process. Type-checked, and scope binding now runs only on a packet that survived validation. |
| The filesystem MCP package was unpinned | **Correct** | `npx -y @modelcontextprotocol/server-filesystem` with no version fetches whatever the registry currently serves — the FakeGit-class exposure this repository has a scan for, in a package it launches on purpose, in a job that had just been made required. Pinned to `2026.7.10`. |
| Evaluation runs recorded no provenance | **Correct** | A run directory held the case inventory and a caller-chosen id, and nothing about what produced the scores. After a prompt edit or model change a passing artifact could not name the implementation it attested to. Runs now record commit, tree-dirty state, Python, deepeval and pytest versions, and the judge model — with `dispatch_wired: false` stated in the artifact, so no reader mistakes today's runs for specialist evidence. |

**The boolean defect, third and worst instance.** `mutating` (round 2) → `launch_grant_verified` (round 3) → `explicit_instruction` (round 5). Each is the same shape: a control that asks the caller whether the caller is authorized. This one guarded the six actions `AGENTS.md` reserves for Joe personally — financial transactions, credential changes, binding commitments, public publication — and any caller could clear it by setting a flag on its own request.

It is worth being precise about why it survived. After round 4 this record claimed that each fix was followed by "a search for the same shape elsewhere in the file". That search found the connector-read hole and missed a `bool = False` field sitting in the same dataclass as the two already-fixed booleans. The search was real but shallow: it looked for the *pattern of the fix* rather than enumerating every caller-supplied field and asking what each one authorizes. The instruction grant is now signed material bound to a specific action and resource, so an instruction to publish one document cannot be replayed as a financial transaction against another.

**`config/mcp_mounts.toml` is no longer untouched.** Earlier rounds stated this change set modified no file under `config/`. Pinning the filesystem server's version changes it. This is not a connector-policy decision — no mount was added, no agent's access changed, no policy string moved — it makes an existing approved mount reproducible. Recorded here rather than left as a silent contradiction of the earlier claim.

### Automated review, seventh pass — four findings, four fixed

| Finding | Verdict | Outcome |
| --- | --- | --- |
| `MUTATING_ACTION_VERBS` missed `edit` and `move` | **Correct, and the list was the wrong shape** | See below. |
| Ownership classified before path normalization | **Correct** | `scripts/../brains/jeos/agents.toml` matched the `scripts/` neutral prefix while a filesystem executor resolving the same string opens the JEOS manifest. Resources are normalized before either prefix check, and one that escapes the tree is refused rather than classified. |
| Canonical reads required no delegation | **Correct** | `apex_war_architect` could read `APEX/Intel-Sources` — another specialist's canonical source — with no packet and no recorded reason. `AGENTS.md` confines packetless direct invocation to current-message text; a memory namespace, write target, mount, or repository path is none of those. Reads of canonical resources now require a validated delegation. The chief is exempt, because it issues them. |
| `case_criteria` judge never got `CONTEXT` | **Correct** | Round 4 added `CONTEXT` to `brain_isolation` and `role_adherence` and left the third judge reading only mission and output. It matters most here: `technical_qa` requires naming the two disagreeing sources, and their identities live only in `case["context"]`, so the judge would have accepted an output naming any two sources at all. |

**The denylist was the defect, not its contents.** `MUTATING_ACTION_VERBS` enumerated mutating verbs and treated everything else as a read — fail-open by construction, protecting against the verbs someone thought of and waving through every verb they did not. The configured filesystem mount exposes `edit_file` and `move_file`; neither `edit` nor `move` was listed, so both skipped the lease, lifecycle, and launch-grant rules entirely.

Adding two entries would have fixed the instance and left the class intact, which is the mistake this record has now documented four separate times. The classification is inverted instead: `READ_ONLY_ACTION_VERBS` is an allowlist, and an action nobody anticipated is a mutation. That costs a lease on an unrecognised read — the correct direction of error, and the one the original comment claimed to be taking while implementing its opposite.

**Third traversal defect in one change set.** The `--run-id` output escape (round 2), its Windows-separator sibling (round 2), and now unnormalised resource paths in the brain lock. Comparing a caller-supplied path against a prefix without canonicalising it first is evidently a reflex worth distrusting on sight.

**Third time a sibling was left untouched.** `CONTEXT` was added to two of three G-Eval judges in round 4. The pattern this record has been naming since round 3 recurred inside the very fix that was supposed to demonstrate the lesson.

### Automated review, eighth pass — ten findings, ten fixed

| Finding | Verdict | Outcome |
| --- | --- | --- |
| Read-verb allowlist matched substrings | **Correct — the previous round's fix was itself fail-open** | `delete_thread` contains "read". So does `spreadsheet_update`. `update_status` contains "status"; `remove_from_list` contains "list". Inverting the denylist was right and the matching was still wrong. Now matched as a leading token, with a tail sweep so `list_purge` cannot hide behind a read verb. |
| `launch_key_path` was caller-supplied | **Correct** | A caller could write its own key, sign a `financial_transaction` instruction with it, point the request at it, and be believed. Verifying a signature against a key the signer chose proves only that the signer can sign. The trust anchor moved to the enforcement point's constructor. |
| `resource_id` optional on mutations | **Correct** | Omitting it skipped record-level matching in both the lease rule and packet scope, so a lease and packet issued for record A authorized writing record B under the same write target. Required now. |
| Chief execution blocked by the addressee check | **Correct, and it deadlocked the only lawful mutation path** | See below. |
| Canonical reads unbound to the delegated namespace | **Correct** | Requiring a packet stopped packetless access but accepted any valid same-brain packet, so a delegation scoped to `APEX::Strategy-Campaigns` authorized reading `APEX/Intel-Sources`. Reads are matched against `allowed_read_namespaces` / `allowed_write_targets`. |
| `expected_artifacts` never compared to the emitted packet | **Correct** | Recorded; the deterministic check validates the handoff against its delegation's requested types, not the case's. |
| `trailing-whitespace` destroyed Markdown hard breaks | **Correct, and it had already done damage** | See below. |
| `task validate` ran the mount verifier without `--strict` | **Correct** | The dedicated CI job was made strict and the aggregate local command was left permissive, so the documented validation could pass with both mounts unverified. |
| APS smoke test accepted any nonempty namespace | **Correct** | Now asserts the exact symbols `gate.mjs` constructs. Note: `@aps_sdk/autodesk-sdkmanager` is resolved but asserts no symbol, because grep confirms the gate never destructures it — requiring one would invent a contract. |
| `uvx snyk-agent-scan@latest` in the intake template | **Correct** | An unreviewed release getting code execution inside the supply-chain verification step. Pinned. |

**The fix to a fail-open check was itself fail-open.** Round 7 replaced a mutating denylist with a read allowlist — the right direction — and kept substring matching, which fails open just as badly in the new direction. This is the fourth distinct way the "fix the class, not the instance" lesson has failed here, and the most instructive: getting the *direction* right is not the same as getting the *mechanism* right, and the round-7 entry above claims the class was closed when only half of it was.

**The gate deadlocked the system it governs.** Requiring `packet.agent == request.agent` meant the chief could not execute a shadow specialist's proposed mutation, because every valid packet names the specialist. The specialist is blocked by `_lifecycle_stage`; addressing the packet to the chief fails `PacketGuard`, which expects a registered specialist. So the only lawful mutation path in the architecture had no actor who could take it. Execution authority now comes from the writer lease — which the registry already verifies — rather than from the addressee. Worth noting that seven rounds of adversarial review found holes that let the wrong actor through before anyone noticed the right actor could not get through at all.

**A formatting hook rewrote a dated record, and the damage was already committed.** `trailing-whitespace` stripped the hard line breaks from `docs/ROSTER_MIGRATION_2026-07-23.md`, collapsing its Date / Governor / verified-parent block into one rendered paragraph — in a repository whose own rule is that dated records are append-only in spirit. It also flattened the empty numbered slots (`1. ` → `1.`) that are the fill-in structure of three templates, and reflowed an unrelated master-plan document this change set had no business touching. All restored; `--markdown-linebreak-ext=md` handles hard breaks and `templates/` is excluded, because that flag only preserves the *double* trailing space of a break, not the single one an empty list slot needs.

### Automated review, ninth pass — two findings, two fixed

| Finding | Verdict | Outcome |
| --- | --- | --- |
| Dependabot watched only the repository root | **Correct** | The root holds `requirements.txt` alone, which does not include the tiered manifests — so deepeval, pytest, mcp, and anthropic sat outside the update mechanism while the file claimed Python coverage. `/requirements` added. Same shape as the dependency-scan gap two rounds earlier: a mechanism pointed at a file that is not the one anyone installs. |
| Chief mutations could omit `owner_brain` | **Correct** | `_brain_lock` exempts the chief as the sole cross-brain agent, which left the brain comparison in both `_writer_lease` and `_packet_scope_errors` conditional on a field the chief could simply leave out. A schema-valid JEOS handoff paired with a genuine APEX lease for the same `resource_id` then authorized an APEX write — cross-brain leakage through the one agent permitted to see both sides, which is precisely the actor the isolation rules exist to constrain. Required on mutations now, and matched across packet, lease, and request. |

**The volume moved.** Nine rounds: 9, 8, 7, 12, 6, 3, 4, 10, 2 findings. This round produced no P1s and both findings were narrow. That is the first round that looks like convergence rather than a fresh seam, and it is worth recording alongside the two rounds where a fix introduced the next round's defect — the loop has been productive throughout, but "still finding things" and "still finding *serious* things" stopped being the same statement here.

**An exemption is not a hole until someone omits the field.** The chief's cross-brain exemption was correct in `_brain_lock` and wrong everywhere it silently propagated. Being permitted to act for either brain is not the same as being permitted to act for an unstated one — a distinction that reads as obvious once written down and was invisible while the field was merely optional.

### Automated review, tenth pass — seven findings, seven fixed

**The ninth round's convergence reading was wrong.** That entry called round 9 "the first round that looks like convergence." Round 10 returned five P1s, three of them in code the previous two rounds had just rewritten. Two data points do not make a trend, and saying so in a record that spends its length insisting on evidence over inference was the same error in miniature.

| Finding | Verdict | Outcome |
| --- | --- | --- |
| Grant expiry read `ToolRequest.now` | **Correct** | The clock was supplied by the caller requesting authorization, so a genuinely signed instruction that expired years ago could be replayed by backdating the request. `ToolRequest.now` is gone; the clock lives on the enforcement point, injectable only so tests can pin it. Same class as `launch_key_path` two rounds earlier: a trust input taken from the party being checked. |
| PacketGuard's lease ledger came from the request | **Correct** | A caller knowing a genuine active lease id could submit a fabricated ledger entry carrying that id but a different `mission_id`, have the guard validate a write-bearing packet against the fabricated mission, then pair it with the real registry lease — two checks, each satisfied by a different object. The ledger is now built from the registry. |
| Operation never bound to the packet | **Correct** | Target, resource id, brain, and lease could all match while the executed operation was strictly more destructive than the packet proposed: a packet restricted to `append` raised no objection against `replace`. Binding everything about *where* a write lands and nothing about *what it does* is not a bound authorization. |
| Read scope conferred write authority | **Correct** | The two allow-lists were unioned, so a delegation granting only `allowed_read_namespaces` authorized a write when paired with a genuine lease. Scope is selected by operation kind now. |
| A handoff with no scope authorized everything | **Correct** | Absent allow-lists reached an unconditional success path — "declares no scope" read as "unrestricted scope", the fail-open shape this module keeps rediscovering in new places. Handoffs bind to their own `memory_namespace` and `proposed_writes`, and an unscoped packet is refused. |
| `--no-resolve` applied to floating manifests | **Correct, and the first fix for it was wrong** | One global flag applied to inputs of two kinds: right for a lockfile, wrong for a file with `>=`. The first fix enabled resolution, which failed in CI with `rpc error: code = Unavailable` while printing "0 packages, 0 vulnerabilities" — a scan covering nothing, whose output was indistinguishable from a pass. Replaced with generated locks (`requirements/lock-runtime-{root,contracts,evaluation}.txt`) scanned with `--no-resolve`. Details and one reassessed triage in `docs/DEPENDENCY_AUDIT_2026-07-25.md`. |
| Metric scores absent from the run artifact | **Correct** | pytest's default `junit_logging=no` omits captured output for *passing* tests, so every judge score and reason on a successful run was discarded — while `evals/README.md` calls the published directory the "scored result". |

**Three of five P1s were in code rewritten during rounds 8 and 9.** The scope binding added in round 7 unioned read and write lists; the handoff path added alongside it treated missing scope as unrestricted; the clock hardened in round 4 was still caller-supplied for the grant check added in round 5. Each fix was locally correct and left an adjacent surface in the state the fix was meant to eliminate.

That is the fifth distinct failure mode of the same lesson, and the most specific: **a fix that adds a new code path must be reviewed as new code, not as a patch.** The scope checks, the handoff branch, and the operation binding were all *introduced* by earlier fixes in this change set — they were never reviewed as fresh surface, only as remedies.

### Automated review, eleventh pass — eight findings, five fixed, three deferred

**This round is the stop signal, and it was declared in advance.** After round 10 the recommendation to Joe was to freeze, and to treat "a new round finds new P1s in the previous round's code" as the point to stop regardless of severity. Round 11 did exactly that: three of its four P1s are in code round 10 wrote, and one of them broke the gate outright.

| Finding | Verdict | Outcome |
| --- | --- | --- |
| Registry leases failed packet admission on `schema_version` | **Correct, and it broke the gate** | Deriving the guard's lease ledger from the registry (round 10) began feeding it genuine `2.1` leases against a schema pinned to `2.0`. Admission rejected **every mutation backed by the real `LeaseRegistry`**, and `_writer_lease`'s tolerance cannot lift an error raised earlier. Fixed by applying the same narrow tolerance at admission. |
| Read-only handoffs authorized writes | **Correct — two bugs in one line** | The handoff schema names the field `target`; round 10 read `write_target`, so no proposed write was ever found. The mutating path then fell through to `memory_namespace`, which is where a specialist *reads*. A read-only handoff plus a genuine lease authorized a `replace`. Mutating scope now comes only from `proposed_writes[].target`. |
| Scalar grants raised instead of denying | **Correct** | The packet path was type-checked in round 8 and both grant paths were left alone. Sibling untouched, again. |
| `CONTRIBUTING.md` / `README.md` mount command permissive | **Correct** | The aggregate `task validate` was made strict and the hand-run commands were not, so "run everything by hand" passed without launching either mount. |
| Intake attestation not required | **Correct** | Every checkbox was optional, so a candidate could be submitted with the scan, its results, its scope confirmation, and the N/A choice all blank. A structured intake enforcing nothing is a longer version of the prose rule it replaced. |
| **Delegations have no issuance proof** | **Correct, deferred** | See below. |
| Locks are scanner inputs, not install inputs | **Correct, deferred** | Nothing verifies the generated locks match their source manifests, so a Dependabot manifest bump could install versions absent from the scanned locks. Needs either install-from-lock or a freshness check in CI. |
| `packet_validity` needs the active-lease ledger | **Correct, deferred** | Same shape as the delegation fix two rounds earlier; blocked behind dispatch being wired. |

**The deferred P1 is the honest one to name.** A delegation packet is still authority-by-shape: `PacketGuard` proves it is well-formed, and nothing proves Agent 007 issued it. A specialist can manufacture its own bounded assignment. That is the same defect the lease check had in round 3, and closing it properly needs an issuance registry or signature — a genuine architectural addition, in a file that has been rewritten eleven times in one day, where the last two rewrites each introduced a P1 and one produced an outage. Adding a trust anchor under those conditions is how the *next* fail-shut bug gets written. It belongs with the `enforce()` wiring decision, which is already Joe's.

**Two fail-shut defects, both introduced by fixes.** Round 8 found that the addressee check made the only lawful mutation path unreachable. Round 11 found that the lease ledger made every registry-backed mutation unreachable. Adversarial review reliably finds fail-open bugs because that is what it looks for; nothing in this loop was watching for the gate becoming unusable, and it happened twice.

### Automated review, twelfth pass — thirteen findings, four fixed, nine deferred

**The eleventh-pass repair was itself a fail-open bypass.** That entry describes fixing a fail-shut defect by tolerating one lease-schema error string at packet admission. `PacketGuard` returns the lease-ledger error and *short-circuits*, so a packet with a genuine semantic defect produced exactly one error — the version mismatch — which the filter then deleted. Reproduced against the repository's own valid fixture:

```
delegation with another specialist's memory namespace
  without ledger : ["agent apex_war_architect must use memory namespace
                     APEX::Strategy-Campaigns::apex_war_architect"]
  with 2.1 lease : ["leases[0]: $.schema_version: expected const '2.0'"]
  after filter   : []            -> allowed
```

So the round-11 commit, whose message says it repaired the gate, converted a gate that denied everything into one that admitted a semantically invalid delegation. **A suppression rule must never be able to remove a finding it was not written for.** Semantics are now established on a pass the ledger cannot short-circuit, and the tolerance applies only to errors the ledger itself introduced.

| Finding | Verdict | Outcome |
| --- | --- | --- |
| Version tolerance suppressed semantic errors | **Correct — fail-open introduced by the previous fix** | Two-pass validation; the unfiltered pass is authoritative for semantics. |
| Empty `allowed_operations: []` read as unrestricted | **Correct** | `replace`, `disable`, and an invented `destroy` all passed. An explicit empty set authorizes nothing — the absent-scope-means-unlimited-scope defect again, in the operation dimension. |
| Unregistered mount handles allowed | **Correct** | The chief exemption returned before checking registration, so `mount:shadow_it_server` was allowed outright. Registration is checked first now, for every principal. |
| `LeaseRegistry` returned live mutable records | **Correct, and it undercuts three earlier fixes** | `issue()` and `active_lease()` handed out the stored object, so the authoritative source could be rewritten by anyone holding an issued lease. Reproduced: assigning `writer_agent` on the returned dict changed the registry. Both now return copies. |
| Operation not derived from the tool action | **Correct, deferred** | `action="delete_file", operation="append"` passes. Needs governed tool metadata. |
| Mount identity conflated with write target | **Correct, deferred** | A mount-backed write has two governed resources and `ToolRequest.resource` names one. Needs a separate validated mount field. |
| High-impact grants omit consequential parameters | **Correct, deferred** | A signed instruction for one financial transaction is indistinguishable from another amount or payee on the same account. |
| Six further P2s (intake requirements, eval stage/dirty-tree/run-id/metric dedup, README pre-commit claim) | **Correct, deferred** | Recorded, not actioned. |

**Nine deferrals, and the reason is now empirical rather than cautious.** Rounds 10, 11, and 12 each found defects introduced by the previous round's fix, and the severity escalated each time: round 10's fix broke CI, round 11's fix broke the gate shut, round 11's *repair* broke it open. Continuing to make architectural changes to this module at this rate is not converging on correctness — it is generating new defects at roughly the rate it removes them.

What was fixed this round is bounded to: the fail-open the previous round created, two narrow fail-opens of the same shape, and a two-line immutability fix in `runtime/writer_lease.py`. Everything requiring a new field, a new registry, or a new trust anchor is deferred to Joe alongside the `enforce()` wiring and the schema decision.

**`runtime/writer_lease.py` is no longer unchanged.** Earlier rounds claimed it was. Returning copies from `issue()` and `active_lease()` alters it. No lease semantics changed — the same records, the same statuses, the same expiry — but the claim was standing and is now false.

### Automated review, thirteenth pass — four findings, two fixed, two deferred

| Finding | Verdict | Outcome |
| --- | --- | --- |
| The `validate` job never installed its validators | **Correct, and it is the configured-vs-executed lesson again** | `verify_runtime_stack.enforce_schemas()` returns `([], [])` when `jsonschema` is absent — indistinguishable from "every schema compiled cleanly". `requirements.txt` supplies pydantic but neither `jsonschema` nor `rtoml`, so JSON Schema and TOML enforcement never ran in CI and an invalid schema could merge with the step green. The `mounts` job installed the right dependency set and never ran this verifier. Fixed by installing `requirements/runtime-contracts.txt` in the job that needs it. |
| The intake's required box established neither branch | **Correct — the previous fix was a half-measure** | Round 11 made one checkbox required with an "either the boxes above are ticked, or this is out of scope" label. A submitter could tick that box alone and leave the scan and all three safety results blank. Applicability is now its own required dropdown, so the two decisions cannot be conflated. |
| `expected_version` / `idempotency_key` not carried on the request | **Correct, deferred** | A caller can obtain an allowed decision for the same target and operation while omitting the optimistic-concurrency and retry identity the validated packet required. Needs new request fields — the category deferred in round 12. |
| `enforce()` still has no live call site | **Correct, deferred — sixth round raising it** | Unchanged blocker: neither execution adapter carries a principal, and `enforce()` fails closed without a `LeaseRegistry` the launcher does not have. |

**Three CI steps have now been found proving nothing, in three separate rounds.** The MCP mount job ran without `mcp` and reported "unverified" while exiting 0 (round 6). osv-scanner resolved nothing during an RPC outage and printed "0 packages, 0 vulnerabilities" (after round 10). `verify_runtime_stack` compiled no schemas because `jsonschema` was absent (this round). Each was added *as* a gate, each looked green, and none of them was executing the check it named.

The generalisation is sharper than the one recorded earlier in this document. It is not only that a configured tool differs from an executed one — it is that **a checker which degrades silently reports success in the same shape as a checker that passed**, so the failure is invisible precisely where verification was supposed to be strongest. A degradation path that returns an empty result set is the dangerous form; one that raises, or exits non-zero, is not.

**The fix for this finding broke CI, and the repair is the same lesson a third time.** Installing the validators made the schema check real; the failure was elsewhere — a test written in the same commit imported PyYAML, which is in no live requirements manifest. The obvious repair was `skipUnless(yaml)`, and that is exactly the pattern this round removed from three CI steps: a test that skips itself reports the same green as a test that passed. Asserted per-block against the file text instead, with no new dependency, and mutation-tested by reintroducing the round-11 half-measure to confirm the assertion actually fails on it. The previous version of that test counted `required: true` across the whole file, which is why a required box in the wrong group had satisfied it.

### Automated review, fourteenth pass — five findings, three fixed, two deferred

**Third alternation in one area, all three in my own repairs.** Round 11 made registry leases fail admission (shut). Round 12 suppressed the guard's short-circuit and let semantic defects through (open). Round 12's two-pass repair then retained `write-bearing packet requires the active writer-lease ledger` from the deliberately ledger-free pass — so **no governed mutation could pass at all** (shut again). Reproduced before fixing: a valid v2.1 `L2` delegation with a matching registry lease, denied solely for the omitted ledger.

The repair, and the rule that should have been applied the first time: a suppression is safe only when the thing it removes is **provably uninformative in the pass it applies to** *and* some other pass still covers the underlying property. The ledger-absent error is guaranteed on a pass that never supplies a ledger, so it carries zero information there; the bound pass runs with the ledger and still reports genuine lease-match failures. Both directions are now tested — a lawful write-bearing packet passes, a tampered memory namespace still fails.

| Finding | Verdict | Outcome |
| --- | --- | --- |
| Semantic pass rejected every write-bearing packet | **Correct — fail-shut, third alternation** | Ledger-absent artifact dropped from the ledger-free pass only. |
| Governance mount's inspection tools classified as mutations | **Correct** | `validate_packet`, `validate_handoff_return`, and `verify_audit_ledger` led with verbs absent from the read allowlist, so three of five tools on the one deliberately grant-free mount were denied for lacking a packet, lease, and grant. `validate`/`verify`/`audit`/`check` added; `admit_delegation_packet` correctly stays a mutation, and a test pins that. |
| `CONTRIBUTING.md` ran the verifier before installing it | **Correct** | The same silent-degradation shape as the CI job fixed one round earlier — the documented manual gate passed while validating nothing. Install moved ahead of the audit, with a test asserting the order. |
| Instruction nonces never consumed | **Correct, deferred** | The same signed grant can be replayed within its expiry window. Consuming it requires a side effect at the execution boundary, which this module deliberately does not have — a policy evaluation that burns a grant means *asking* whether an action is permitted performs it. The consumption ledger belongs with `enforce()` wiring. |
| `expected_artifacts` not compared to the emitted packet | **Correct, deferred** | Eval-harness category, blocked behind dispatch. |

**What the alternation means, stated once.** Three consecutive attempts to correct this one interaction produced, in order, a gate that denied everything, a gate that admitted invalid packets, and a gate that denied every mutation. Each fix was locally reasoned and locally tested. The failure is not carelessness in any single change — it is that this interaction has more states than the tests written alongside each fix were covering, and each repair was validated against the failure it targeted rather than against the whole space. That is a signal to stop patching and let a human decide the shape, which is what the deferrals now reflect.

### What remains open after this round

Not a decision backlog — the actual work the harness exposed:

- **36 of 39 material modes have no evaluation case**, and none can leave
  `shadow` until they do. This is now the top of the queue and it is measurable.
- **Specialist dispatch is unwired** (`_invoke_specialist` raises). Connecting it
  needs a verified model credential and a connector-isolation decision that is a
  separate, deliberate step.
- **Confident AI cloud logging** is now enforced by the runner rather than only
  documented — it refuses to run while telemetry is on.
- **`enforce()` is built and tested but not yet called by any execution path.**
  `scripts/claude_runtime.py`, `scripts/governance_mcp_server.py`,
  `scripts/trusted_launcher.py`, and `runtime/lease_queue.py` still go straight
  to admission. Until one of them calls it, the consolidated gate constrains
  nothing at runtime — the same "configured, not executed" failure this record
  spends a section on. Wiring it changes behaviour in tested governance code, so
  it belongs in its own reviewed change rather than appended to this one. It is
  the top follow-up.
- **The writer-lease schema mismatch** (`2.1` issued vs `2.0` required) needs a
  contract decision before the enforcement point can validate leases without a
  scoped exception.
