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

### Automated review, fifteenth pass — seven findings, five fixed, two deferred

**The fourth alternation, and it was hiding underneath the third.** The fourteenth pass ended by declaring the lease/packet interaction frozen. This pass found that the state which survived rounds 12–14 was fail-**open** in a way none of those rounds had looked for: `PacketGuard.validate()` returns at the *first* lease-ledger error, so feeding it a genuine `2.1` registry lease against a schema pinned to `2.0` meant `_lease_match_errors` — the check that binds *this* packet to *that* lease — **never executed at all**. The suppression rule then deleted the one error that had been produced. A delegation carrying a `writer_lease_id` that was never issued and a `mission_id` the lease does not cover was admitted, because target, resource, brain, and writer all matched and so `_writer_lease` raised no objection either.

Reproduced before fixing, and the repair is the one thing the previous three rounds did not try: **reconcile the defect instead of suppressing the error it produces.** The enforcement point rewrites `schema_version` on a *copy* of the lease, and only when the value is exactly what `runtime/writer_lease.py` issues. The ledger then validates cleanly, every downstream relational check runs, and no filter exists at all. It is strictly narrower than what it replaces: the old filter dropped `expected const '2.0'` whatever the offending value was, so a lease claiming `9.9` was tolerated too.

Both directions were verified before the change was committed, per the rule set after round 14: a genuine `LeaseRegistry` lease with a matching packet still passes end to end, **and** a semantically broken packet still fails. Reintroducing the round-14 behaviour is now caught by five tests.

**Two pre-existing tests were asserting the fail-open**, which is why fourteen rounds did not surface it. `test_a_lawful_write_bearing_packet_is_not_denied_by_the_semantic_pass` named `writer_lease_id = "lease-1"` — an id no registry ever issued — and asserted it must not be denied; it passed only because the relationship check was unreachable. `test_lease_held_by_another_agent_is_denied` passed for a similarly accidental reason. Both now use the lease the registry actually issued, and the scenario the second one used to describe is kept under its real name: an ineligible writer cannot hold a lease at all.

| Finding | Verdict | Outcome |
| --- | --- | --- |
| Packet-to-lease relationship never validated | **Correct — fail-open, fourth alternation** | Reconciliation replaces suppression; the guard's relational checks run for the first time against a registry lease. |
| Targetless Chief request allowed with no reasons | **Correct — fail-open** | `evaluate(agent=CHIEF, action="read", resource="")` returned `allowed=True` with an *empty* reason tuple: `_brain_lock` and `_packet_admission` both exempt the chief, and every other rule reads the resource, so a blank one matched no prefix and objected to nothing. Principal, action, and resource are now required in `normalize()`, before any rule and therefore before any exemption. The blank-*action* case had been caught only by accident — a blank action classifies as mutating, so the lease rules happened to fire. |
| Governance mount accepted undeclared tools | **Correct** | `_verdict()` checked only for *missing* tools, so appending `delete_all` to the server's registration passed. That mount is granted to `agents = ["*"]`. `tools_are_exhaustive` now distinguishes a closed contract (this repository's own servers) from a floor (the upstream filesystem subset, where naming every tool would make any additive release a CI failure). |
| Mount verifier ignored unknown flags | **Correct** | `"--strict" in argv` meant `--strcit` silently ran the permissive path — unverified mounts, exit 0, CI green. `argparse` now rejects it. Same silent-degradation class as the three CI gates fixed in round 13, this time in the reader of the flag rather than the checker. |
| Manual gate omitted the formatter | **Correct** | `ruff check` does not verify formatting; CI runs `ruff format --check` separately, so a contributor could run every documented command and still be rejected. **Found in four places, not the one reported** — `CONTRIBUTING.md`, `README.md`, `CLAUDE.md`, and `task lint`. `README.md` also still ran `verify_runtime_stack.py` before installing its dependencies, the exact ordering defect fixed in `CONTRIBUTING.md` one round earlier. Both hygiene tests were generalized from one file to all of them. |
| Pre-commit hooks pinned to mutable tags | **Correct, deferred** | Real, and the argument matches the SHA-pinning applied to Actions. Deferred because resolving four `rev` tags to commit SHAs cannot be verified offline here, and a wrong SHA breaks every contributor's pre-commit rather than failing one CI job. Joe's call. |
| Filesystem mount's npm package unlocked and unscanned | **Correct, deferred** | The top-level version is pinned; its transitive set is not, and no committed lock covers it. The fix is a new npm manifest, `npm ci` in the mounts job, and a fourth entry in the osv scan — a supply-chain change with its own review surface, not an appendix to this one. |

**On the freeze.** Round 14 froze `scripts/policy_enforcement.py` to genuine breakage only. Both P1s here qualify — each is a fail-open in code this change set introduced — so both were fixed. Neither of the two deferred findings touches that module. The five architectural decisions listed below remain untouched and unactioned.

**What the fourth alternation adds to the lesson.** Rounds 12–14 each validated a fix against the failure it targeted. This round shows a fifth state none of them tested: not "does the gate deny what it should" or "does it allow what it should", but **"does the check run at all"**. A short-circuiting validator makes those different questions, and a passing test suite cannot distinguish a check that ran and approved from a check that never executed — which is the same configured-vs-executed error this record opens with, now found inside the enforcement point itself rather than in CI. Two of the tests guarding this area were asserting the bug.

### Automated review, sixteenth pass — seven findings, seven fixed

**Joe marked five of these "Fix" on the PR, which ends the freeze declared after round 14.** That freeze was a self-imposed posture, not a contract; a direct instruction supersedes it. Two further findings — one P1 fail-open and one P2 — were fixed alongside them because they are the same defect classes in the same files.

**A fail-shut I introduced one round earlier.** Deriving the guard's ledger from the registry (fifteenth pass) fed it whatever `LeaseRegistry._active` held — and `_expire()` runs only inside `issue()`, so a lease past its `expires_at` sits there until some unrelated issuance sweeps it. `PacketGuard` then reported `active writer lease is expired` for the *ledger*, and `validate()` returns at the first ledger error, so **one stale lease denied every packet-backed operation in the corps**, including reads with no relationship to any lease.

The ledger is now filtered rather than swept: a policy evaluation must not mutate the registry, the same reasoning that defers instruction-nonce consumption to the execution boundary. The filter uses `<=` to match `PacketGuard`'s own comparison rather than `_lease_expiry_errors`' strict `>`, because a filter looser than the check it protects would re-shut the gate on the boundary instant.

**Reproducing this one required care, and the first attempt was wrong.** `PacketGuard` compares expiry against `datetime.now(UTC)`, not the enforcement point's injected clock, so a fixture that expires relative to the test clock proves nothing. The first repro printed a *scope* error and I nearly read it as confirmation. The regression test issues a lease already lapsed in real wall-clock time, and says why in a comment.

| Finding | Verdict | Outcome |
| --- | --- | --- |
| Expired leases injected into every packet ledger | **Correct — fail-shut, mine, one round old** | Ledger filtered by the point's own clock; a lapsed lease still authorizes no mutation, tested both ways. |
| Delegation `deadline` never enforced | **Correct — fail-open** | The field is declared in the schema and *nothing* parsed it — not `PacketGuard`, not this module. `deadline: "2020-01-01T00:00:00Z"` was admitted, so a time-bounded assignment stayed reusable indefinitely. Null stays valid (the schema declares it nullable); a stated-but-unparseable deadline is refused, because an unreadable bound is not an absent one. |
| Brain-neutral reads had no lawful path | **Correct — fail-shut** | All three branches denied: no packet → "requires a validated delegation"; a valid delegation → "packet does not authorize"; a delegation naming the path → `PacketGuard` rejects the namespace as outside private memory and roundtable. A specialist could not read `AGENTS.md`, the contract defining its own behaviour. Same shape as the round-8 execution-authority deadlock: a rule whose only lawful path does not exist is not strict, it is broken. Exemption scoped to the declared neutral set, matched after normalization, reads only. |
| MCP handshake unbounded | **Correct** | `ClientSession` defaults `read_timeout_seconds` to `None`, so a server that starts and never answers blocks until Actions kills the job — one hung mount costing the whole run instead of one failed verification. `asyncio.wait_for` at 120s. `TimeoutError` is named explicitly because it stringifies to nothing, and the generic handler would have reported `probe failed: ` with no diagnostics. |
| Case thresholds accepted `0.0` | **Correct** | Judge scores are nonnegative, so a case could set its own gate to zero, pass with every forbidden behaviour present, and have `_record_passes()` file the run as acceptance evidence. Validated at **case-load** time so every consumer is covered rather than the one pytest module that reads thresholds. Correctness metrics pinned at 1.0; judged-quality metrics keep a floor, so a case may demand more but never less. |
| Locks scanned, manifests installed | **Correct** | `security.yml` called the locks "the resolved forms of the sets CI installs" while CI installed the ranged manifests — a clean scan of a file nothing installs. CI now installs the locks. One lock serves both matrix legs because 3.11 and 3.12 were **compared** and resolve identically rather than assumed to. A new `locks` job re-resolves each manifest on both versions and fails on drift, so the lock cannot go stale while the scan keeps reporting it clean. |
| Secret scan unscoped on push | **Correct** | `BASE_SHA` is empty on **both** push and schedule, so the else branch ran the whole-history scan on every push to main — the exact behaviour the surrounding comment says was moved to the weekly run. Three events now get three ranges, with the all-zero new-ref sentinel and an unreachable force-push `before` both falling through to the full scan. |

**One fix was found rather than reported.** `_packet_namespace_errors` normalized the declared scope entry (`::` → `/`) but not the resource, so a request naming its resource in namespace form could never match a scope that authorized it — and the denial printed two strings that looked identical, because the difference was the separator being compared. The docstring states the intended behaviour ("compare on the shared segments rather than demanding one spelling"); only one side implemented it. Fixed symmetrically, with a test that both spellings resolve and neither widens scope.

**One of my own tests was too weak, and mutation-testing is what found it.** The secret-scan assertion checked for `github.event.before` anywhere in the file and still passed after the env binding was deleted, because the comment above it mentions the same string — a test satisfied by prose *describing* the property rather than by the property. Reading it would not have caught that. It now asserts the binding and the branch that consumes it, and all four mutations are caught.

### Automated review, seventeenth pass — five findings, four fixed, one deferred

**Three of the four were scope-widening in code written in the previous two rounds.** The pattern is worth naming: each was a *matching rule* that accepted more than it was written to accept, and in each case the over-acceptance was invisible because the intended case also passed.

**Named neutral files matched their siblings.** `BRAIN_NEUTRAL_PREFIXES` holds directories (`docs/`) and named files (`AGENTS.md`) in one list, and prefix matching was applied to both — so `AGENTS.md` also matched `AGENTS.md.private`, `README.md.jeos`, and `CLAUDE.md-secrets`, files whose ownership is unresolvable. This was tolerable while neutrality was only a *classification*; the sixteenth pass made it an **exemption from packet admission**, at which point a specialist could read any of those packetlessly. A change that is safe under one meaning of a helper became a fail-open when the helper's meaning changed, and nothing connected the two.

**A child scope authorized its parent.** `_packet_namespace_errors` accepted a declared scope that is a *descendant* of the request, so a delegation naming only `APEX::Strategy-Campaigns::apex_war_architect` authorized `APEX/Strategy-Campaigns` — the collection holding every specialist's namespace. **Two existing tests were asserting exactly this**, under the names "authorizes the resource it does name" and "is bound to its own memory namespace", both using the parent as the resource. That is the third time in this change set a test has been found encoding the defect it was written to prevent.

**The launch grant could not fire where it mattered.** It keyed off `resource.startswith("mount:")`, but a mutation dispatched through a mount must name its canonical write target in `resource` — that is what the packet and lease scope checks compare against. The two requirements were mutually exclusive: name the mount and lose scope binding, or name the target and skip the grant. A fully authorized canonical mutation was allowed with no grant at all. `ToolRequest.mount` now carries the executing mount independently.

That field is caller-supplied, which this module has learned to distrust three times (`mutating`, `launch_grant_verified`, `explicit_instruction`). It is deliberately a different shape: **it can oblige, never permit** — setting it can only add the grant requirement, and a test pins that. But a dispatcher that omits it reproduces the hole, so populating it is part of the dispatcher contract that wiring `enforce()` must establish. That is recorded with the wiring work rather than assumed here.

| Finding | Verdict | Outcome |
| --- | --- | --- |
| Neutral prefixes matched sibling filenames | **Correct — fail-open, mine, one round old** | Directories match descendants; named files match only themselves. |
| Child scope authorized its parent | **Correct — fail-open** | Equality or descendant-of-scope only. Two tests that asserted the widening corrected. |
| Launch grant unreachable for mount-dispatched mutations | **Correct — fail-open** | `ToolRequest.mount` carries the mount independently of the write target. |
| Lock-drift matrix omitted the evaluation pair | **Correct — mine, one round old** | The third pair added, and the hygiene test now **derives** the required set from the locks the security workflow actually scans, so a fourth lock cannot be scanned-but-unchecked. |
| Active leases not carried into evaluation packet scoring | **Correct, deferred** | Blocked behind eval dispatch, with `expected_artifacts` and the delegation ledger. |

**The lock-drift omission is the same partial-fix shape as the formatter finding one round earlier**, where the reported instance was one of four. Fixing the reported instance and stopping is now a documented recurring failure here, so this repair derives its coverage from the other workflow instead of restating a list that can fall out of step.

### Automated review, eighteenth pass — eleven findings, nine fixed, two deferred

**Both P1s were holes in code added by the previous two rounds, and one was created by a fix.** `ToolRequest.mount` was introduced in the seventeenth pass so a mount-dispatched mutation could be bound to its launch grant — and it was wired into the launch-grant rule *only*. `_connector_policy` still read `resource` alone, so a packet-only specialist could name its own memory namespace as the resource, set `mount="gdrive"` — or a mount registered nowhere at all — and be allowed. **Adding a field that names a connector without teaching the connector rule to read it moved the boundary rather than widening it on purpose.** Registration and the packet-only policy now both consider either spelling.

**The deadline check ran against a packet that could never fail it.** The sixteenth pass added `deadline` enforcement and applied it to `request.packet`. A *handoff* carries no `deadline` — the field lives on the delegation that commissioned it — so presenting a handoff meant the check evaluated a field that does not exist, and a handoff backed by a delegation dated 2020 authorized a canonical read. The bound belongs to the assignment, and a return cannot outlive its commission.

**A `direct_read_only` handoff was accepted as a canonical read grant.** That mode is the packetless path written down: nothing commissioned it, and the schema confines it to `resource_id="current-message"`. Treating its `memory_namespace` as an authorization scope let a specialist mint a schema-valid direct handoff and read its own canonical namespace with no Agent 007 assignment — self-issued authority arriving through the one packet kind that needs no issuer.

| Finding | Verdict | Outcome |
| --- | --- | --- |
| Connector isolation ignored `request.mount` | **Correct — P1, created by the previous round's fix** | Registration and packet-only policy applied to the declared mount as well as the resource. |
| Originating delegation's deadline unenforced | **Correct — P1, incomplete fix from two rounds earlier** | The whole authorizing chain is checked, not only the packet presented. |
| `direct_read_only` handoff as canonical scope | **Correct — P2** | That mode binds nothing canonical. |
| DeepEval persisted login bypassed the refusal | **Correct — P1** | `deepeval login` persists a key to disk, so a later process uploads with no variable set; `DEEPEVAL_TELEMETRY_OPT_OUT` governs anonymous telemetry, not authenticated logging. **Two opt-outs that both sound like the right one, neither of which is.** The runner now refuses on a persisted session and says which file to remove. |
| Packet identity not bound to the evaluated mode | **Correct — P1** | `score_packet` proves the packet and its delegation agree with *each other*; nothing compared either with the mode under test, so a lawful War Architect pair could record a Delivery Commander mode as proven. Checked as data, not judged — these are exact strings the manifest declares. |
| Symlinked evaluation output root | **Correct — P2** | The containment check resolved *both* sides, which is vacuous when the root is itself a symlink: `evals/output -> docs/leak` made `docs/leak/<id>` duly "inside" it. The root must now be a real directory at its declared location. |
| Run directory not reserved atomically | **Correct — P2** | Check-then-create let two runs sharing a `--run-id` both proceed. `mkdir(exist_ok=False)` makes the claim the check. |
| Scheduled sweep cancelled by pushes | **Correct — P2** | A push to `main` shared the scheduled run's concurrency group, so it cancelled the whole-history gitleaks sweep and replaced it with a `${BEFORE_SHA}..HEAD` scan. The promised weekly audit could never complete, and a cancelled run reports nothing. Event name is now part of the group; scheduled runs are never cancelled. |
| Active-stage intake gates unenforceable | **Correct — P2** | Split: shadow-entry gates are required for every intake, and active-stage completion is its own required dropdown. Issue forms have no conditional validation, so making the single list required would have forced shadow-only requesters to attest to gates that do not apply — the same reasoning already recorded for `agent-scan-applies`. |
| Optional-tier manifests not lock-bound | **Correct, deferred** | The dated `lock-2026-07-24.txt` is known not to resolve (`posthog` 7.29.0 vs `chromadb <6.0.0`), which is already an open decision for Joe. Generating locks for the five optional tiers depends on how that conflict is settled; doing it first would lock a set nobody can install. |
| Platform-specific locks | **Correct, deferred** | The locks are resolved on Linux with no target platform, so Windows-only dependencies (`colorama` under pytest) are outside both drift checking and OSV scanning. Fixing it means either committing per-platform locks or declaring the install paths Linux-only — a scope decision about whether the documented Windows workstation is a supported install target, not a mechanical change. |

**The recurring shape, stated once more because it recurred through a fix rather than around one.** The seventeenth pass closed a hole by adding a field; the eighteenth found that the field opened a different one, because only the rule that motivated it was taught to read it. A new field in a shared request object is not additive — every rule that reasons about the same thing has to be revisited, or the object now describes a request the rules disagree about.

### Automated review, nineteenth pass — nine findings, nine fixed

**The worst finding was an exemption ordered ahead of a check that has nothing to do with it.** `_brain_lock` returned early for the Chief before `_escapes_the_tree()` ran, so `evaluate(agent=CHIEF, action="read", resource="/etc/shadow")` was allowed **with an empty reason tuple** — as were `../outside-secret` and `docs/../../.ssh/id_rsa`. Being the sole cross-brain agent permits acting for either brain; it does not put the filesystem in scope, and no brain owns a path outside the tree, so there was nothing there for the exemption to waive. The escape check now precedes it.

That is the second time an exemption placed before a check has produced a fail-open here — the first was the chief exemption preceding mount registration, five rounds earlier. **An exemption is scoped to one question, and putting it ahead of a different question silently widens it to that one too.**

**Three of the nine were defects in the previous round's fixes**, two of them fail-shuts that made a gate unsatisfiable:

- **The identity gate rejected every lawful packet.** `load_modes()` takes `Mode.brain` from the manifest *directory* (`brains/apex/`), so it is lowercase, while both authorization schemas require `APEX`. Comparing exactly meant no evaluation could ever record a pass — a gate introduced one round earlier that shut the very thing it was meant to bind. Two conventions for one value, and the check assumed one of them.
- **The ledger-artifact filter missed its wrapped form.** `PacketGuard` re-emits a delegation's inner errors as `originating delegation invalid: <error>`, so on a write-bearing handoff the artifact arrived nested, survived an exact-equality filter, and denied a lawful handoff even with its genuine registry lease. **The fix to a fail-shut was itself fail-shut, one nesting level down.**
- **The persisted-login check crashed on a directory.** `~/.deepeval` is normally the directory holding the store, so `read_text()` raised an uncaught `IsADirectoryError` — a safety check that aborts before reaching a verdict is not a safety check.

| Finding | Verdict | Outcome |
| --- | --- | --- |
| Chief exemption preceded the escape check | **Correct — P1 fail-open** | Escape refused before any exemption. |
| Identity gate rejected the schemas' own brain spelling | **Correct — P1 fail-shut, mine, one round old** | Brain compared case-insensitively; the other brain still refused in either case. |
| Ledger artifact unrecognised when wrapped | **Correct — P1 fail-shut, mine** | Tail-matched at any nesting depth; nothing else removed, and tested. |
| Concrete boundary verbs never reached the boundary | **Correct — P1 fail-open** | `HIGH_IMPACT_ACTIONS` holds abstract category names, so the check fired only when a caller volunteered `public_publication` as its action — the same "ask the caller to incriminate itself" shape as the three caller-set booleans removed earlier. Nobody publishing something they should not would spell it that way. A verb map now covers `publish`, `send`, `transfer`, `sign`, `purge`, `revoke` and their siblings. |
| Case artifacts unbound to the packet | **Correct — P1** | `score_packet` proves the handoff matches its *own* delegation, so an internally consistent pair could deliver an artifact the case never requested while the prose claimed otherwise. |
| `current-message` sentinel denied | **Correct — P2 deadlock** | The documented direct-invocation path was refused by exactly one rule. **Third deadlock of this shape**, after execution authority and brain-neutral reads. Matched by equality, not prefix — the sibling-matching defect two rounds earlier is why. |
| Persisted DeepEval login check crashed | **Correct — P2, mine** | `is_file()` rather than `exists()`. |
| Absorption scan attestations unenforceable | **Correct — P2** | Every dropdown option is now itself an attestation, because issue forms cannot enforce a condition stated in prose. **This contradicted a test I had written** asserting the attestations must *not* be required; that test was pinning the wrong property — the risk was never the option count, it was an option that decides nothing. |
| README overstated pre-commit | **Correct — P2** | Two of the eight listed commands are in no hook, and the unit suite lets its JSON Schema check skip when `jsonschema` is absent, so the automatic path could pass while CI failed. The claim now names what runs and what stays manual, and a test derives that from the hook config. |

**On the absorption-form finding specifically.** Two rounds ago I wrote a test asserting those attestations must not carry `required: true`, reasoning that requiring them would force a non-applicable submitter to attest to a scan that never happened. That reasoning was correct and the conclusion was still wrong: leaving them optional meant the *applicable* branch asserted nothing either. The resolution was not to pick a side but to move the attestation into the required field itself. A test can encode a real constraint and still pin the wrong property.

### Automated review, twentieth pass — three findings, three fixed

**All three were gaps in the previous round's fixes, and each was reached the same way: the fix handled the reported instance and stopped at the boundary of the class.** That failure now has five entries in this record. This round it happened three times in one commit.

**`delete_all` was named in the comment introducing the map that does not cover it.** The nineteenth pass replaced exact matching against abstract category names (`public_publication`) with a verb map, then looked the *whole* action up in it — so `delete_all`, `bulk_delete`, `publish_report`, and `send_email` all passed the boundary untouched. The comment I wrote alongside that map cites `delete_all` as an example of a real invocation. **The fix contained a written statement of the case it failed to handle.** Actions are now tokenized on the same boundary `_is_mutating` uses and matched by *token equality*, with a separate rule for a destructive verb qualified as wholesale — `delete` is an ordinary mutation the lease governs, `delete_all` is one of the six actions `AGENTS.md` reserves for Joe, and neither token means that alone.

**A Windows drive path walked through the escape check added one round earlier.** `_canonical_resource` treated anything with a colon before the first slash as an opaque handle. `C:\Users\Joe\secret.txt` contains no slash at all, so the whole string was its own first segment: normalization never ran, and the escape check saw a string starting with neither `../` nor `/`. The chief could read it with no denial reasons — on the one platform the workstation actually runs. The check was correct and simply never reached.

**Mutation testing found a second fail-open the review had not reported.** Reverting the opacity rule alone still passed every test, because the new drive-letter regex catches `C:\…` even unnormalized — so the narrowing looked unmotivated and the thing it actually protects was untested. What it protects: the old rule made *any* resource opaque whose first segment held a colon, so `docs:notes/../../etc/passwd` was never normalized and read as safe. Normalized it is `../etc/passwd`. **A missed mutation is not a redundant fix; it is a missing test, and here it was concealing a second hole.**

| Finding | Verdict | Outcome |
| --- | --- | --- |
| Compound high-impact actions unmapped | **Correct — P1 fail-open, mine, one round old** | Token-equality matching plus a bulk-qualifier rule; ordinary compounds (`delete_row`, `design_review`, `read_publications`) verified not over-classified. |
| Windows drive paths bypassed the escape check | **Correct — P1 fail-open, mine, one round old** | Opacity reserved for `mount:`/`connector:`/`::`; drive-absolute and UNC classified as escapes. |
| Intake stage and its attestation could contradict | **Correct — P2, mine, one round old** | Merged into one required dropdown. Issue forms do not cross-validate, so a submission could request `active` *and* answer "not applicable — requesting shadow". **Two enforceable answers about one decision enforce nothing, because they can disagree.** |

**The intake finding completes an arc worth stating.** Three consecutive rounds touched that form: first the gates were optional and unenforceable; then applicability became its own required question, which was the pattern the absorption form already used; then that very split turned out to be the defect, because the two answers could contradict. The correct shape was neither optional nor split — it was *one* required answer that carries the attestation. Both forms now satisfy a shared test asserting that every required dropdown option states an outcome rather than deferring to boxes elsewhere.

### Automated review, twenty-first pass — three findings, three fixed

**The most consequential was a test of mine that broke the repository's own mandatory command.** `tests/test_repo_hygiene.py` exercised the mount-probe timeout by calling the real `_probe()`, which imports the optional `mcp` package. In any checkout without `requirements/runtime-contracts.txt` installed — which the documented `pre-commit` path does not install — `python -m unittest discover -s tests` **errored outright** rather than running. This suite's stated contract is that it runs on the standard library alone, and the test enforcing one gate had quietly broken that contract for every other gate.

Fixed by stubbing the inner probe with a sleeping coroutine, **not** by skipping. A `skipUnless(mcp)` would report the same green as a passing test on exactly the machines missing the dependency — the silent-degradation shape this change set removed from three CI gates. The timeout lives in `_probe_with_timeout`, so wrapping a sleeping coroutine exercises the real mechanism with no dependency. A companion test now asserts the dependency-free property directly, so the next such test fails on arrival.

**Verifying this finding required getting the simulation right, and the first attempt was wrong.** Blocking `mcp` by patching `builtins.__import__` also produced an unrelated error in `test_native_runtime`, which looked like a second instance of the same defect. It was not: that class guards itself with `skipUnless(_available("mcp"))`, and `_available` uses `importlib.util.find_spec`, which does not route through `__import__`. Re-run with a `meta_path` finder that hides the module from both, the suite is clean — 0 errors, 26 skipped. **A faulty reproduction can manufacture a finding as easily as it can miss one**, and this one was two lines from being reported as real.

| Finding | Verdict | Outcome |
| --- | --- | --- |
| Timeout test required the optional `mcp` package | **Correct — mine, three rounds old** | Inner probe stubbed; dependency-free property now asserted on its own. |
| Windows-invalid run identifiers crashed `mkdir()` | **Correct** | `2026-07-25T12:00` — the natural timestamp id — is legal on Linux and forbidden on Windows, so it passed validation and raised an uncaught `OSError` on the documented workstation. Reserved characters, control characters, trailing dots, and device names (`NUL.json` is still the null device) are now refused with a stated reason, on every platform rather than gated on `sys.platform`: an id that works on one machine and crashes on another is worse than one refused consistently. |
| `case_criteria` missing from the documented metric table | **Correct** | It is a baseline metric constructing a G-Eval judge for every case, so the record understated the judge count — **three model-backed judges per case, not two** — and therefore what a passing run proves and what it costs. |

**Mutation testing again found more than the review did, and this time it found gaps in my own tests.** Two of the three fixes were initially reported as MISSED: there was no test at all for Windows-invalid run identifiers (I had verified it by hand in a shell and not written one), and the metric-table test checked for the metric name *anywhere in the document*, so renaming the table row still passed — the name also appears in the prose beneath it. **A test satisfied by the paragraph describing the table is not a test of the table.** Both strengthened; all three mutations now caught.

That is the second consecutive round in which chasing a missed mutation produced a real finding rather than confirming a redundant fix. The rule is now explicit in the working checklist: **a missed mutation is a missing test, and must be investigated rather than noted.**

### Automated review, twenty-second pass — two findings, two fixed

**Both were fail-opens living inside the previous two rounds' fixes, and both are exact repeats of shapes already in this list.**

**The `current-message` exemption waived the whole rule.** Added in the nineteenth pass to give the documented direct-invocation path a lawful route, it was written as an early return — so it skipped the comparison of the caller's declared brain against its registered one. `jeos_reflection_forge` reading `current-message` while declaring `owner_brain="APEX"`, or omitting the field entirely, was allowed. **APEX message content could be routed through a JEOS specialist with no objection.**

That is shape (e) — an exemption ordered ahead of a check it has nothing to do with — for the **third** time, after chief-vs-mount-registration and chief-vs-escape. And it arrived *in the fix for* the third deadlock. The sentinel genuinely waives one thing: message text has no owning brain, so ownership resolution cannot classify it. Everything about the principal still applies, and the exemption now says so in its own body rather than by position.

**The test asserting the sentinel had a lawful path was asserting the fail-open.** It omitted `owner_brain` and passed — because the exemption skipped that check too. **Fourth test in this change set found encoding the defect it was written to prevent.** A lawful direct invocation declares its brain like any other request.

**Namespace opacity carried the defect the previous round removed.** The twentieth pass narrowed `_canonical_resource`'s opacity test from "a colon before the first slash" to "a connector prefix **or contains `::`**". The second clause has the same flaw: any path-shaped string containing `::` skipped normalization, so `scripts/../../outside::secret` matched the `scripts/` neutral prefix **on its raw text**, took the brain-neutral packetless exemption, and was allowed — while a filesystem executor resolves it outside the repository. Anchored to `^(APEX|JEOS)::` now, which is what a memory namespace actually looks like.

That is shape (a) — fixing the instance and missing the class — **inside the fix for a previous instance of the same class**. The single-colon case was corrected and the double-colon case was written in the same line.

| Finding | Verdict | Outcome |
| --- | --- | --- |
| Sentinel exemption skipped the brain comparison | **Correct — P1 fail-open, mine, three rounds old** | Exemption scoped to resource ownership; principal's brain still compared. Both directions tested, and the test that encoded the hole corrected. |
| `::` anywhere made a path opaque | **Correct — P1 fail-open, mine, two rounds old** | Opacity anchored to real namespace syntax, case-insensitively; traversal through a `::` suffix now normalizes, escapes, and is refused. |

**What these two say together.** Every fail-open this round was introduced by a fix for a fail-open, and each reproduced a failure shape already written down in this record. The checklist is not the problem — both shapes were on it. The problem is that the checklist is applied to the *reported* defect and not to the *repair*, and a repair is new code with the same standing as any other. Reviewing one's own fix against the list before pushing is now part of the working procedure, not an afterthought.

### Automated review, twenty-third pass — two findings, two fixed

**Both were documents claiming a control runs when it does not** — the same class as the pre-commit overstatement two rounds earlier, in two places that overstatement did not reach.

**The README described the enforcement point as active.** `scripts/policy_enforcement.py` was listed as "the single policy-enforcement point **evaluated immediately before tool execution**: eight rules … in one call a caller cannot partially perform." `enforce()` appears only in its own module and its tests. This record has said so plainly since the eleventh pass, and the README told the opposite story to anyone reading the repository map first — that eight controls are running when none are.

Corrected to say it is built, tested, and unwired. The accompanying test derives the claim from the actual call sites rather than banning the phrase outright, so the stronger wording becomes permissible again the moment the wiring lands instead of leaving the document pessimistic afterwards.

**`task validate` omitted the lint steps it stands in for.** `CONTRIBUTING.md` presents it as the alternative to the manual sequence, and that sequence ends with `ruff check` and `ruff format --check` — so the advertised shortcut passed while the same tree failed the required CI lint job.

**That aggregate-vs-hand-run divergence has now occurred three times**, in both directions: the mount verifier was made strict in the aggregate and left permissive by hand, then strict by hand and left permissive in the aggregate; and the formatter was added to three documents *and* this file's `lint` task while `validate` — the command people actually run — was missed. The eighteenth pass recorded that fix as covering "four places, not the one reported". It was four of five.

| Finding | Verdict | Outcome |
| --- | --- | --- |
| README claimed the gate runs before tool execution | **Correct — P2** | Described as built-and-unwired; the test reads the call sites, so the claim re-enables itself when true. |
| `task validate` skipped lint and format | **Correct — P2** | Chained in. A test now derives every required step from the manual sequence, so a step added to one and not the other fails. |

**Why a checklist entry did not catch the second one.** "Fixing the reported instance and missing the class" was on the list and was applied — the eighteenth pass deliberately swept for the formatter across documents and found four. The sweep covered *documents*, and `task validate` is a command definition. **The class was scoped to the file type where the instance was found, not to the property being fixed.** The property is "anything a contributor is told to run"; that set includes taskipy tasks, pre-commit hooks, and CI jobs as well as prose. The test added here is derived from the manual sequence rather than enumerating a list of places, which is the shape that does not need a sweep to stay complete.

### Automated review, twenty-fourth pass — nine findings, six fixed, three deferred

The three deferrals are already on Joe's decision list and were re-raised rather than newly found: **instruction-nonce consumption**, **binding `operation` to the dispatched action**, and **carrying active leases into evaluation packet scoring** (blocked behind eval dispatch). Each needs a side effect or an adapter that policy evaluation deliberately does not have.

**Two scope fail-opens, both the same shape as fixes already applied elsewhere.**

`resource_id` was honoured only when supplied. A delegation issued for `resource-1` **denied** a request naming `resource-2` and **allowed** one naming nothing — so any record under the authorized namespace was reachable by leaving the field out. `_writer_lease` had required it for mutations since the eighth pass; the read path was the untouched sibling. An optional identifier the checks honour only when present is an opt-out, which is the wording already in this record for the mutation case.

A handoff could read past its commission. The scope fallback read the handoff's own mandatory `memory_namespace` and never consulted the delegation that authorized the work, so a handoff commissioned only for `APEX::Roundtable` read `APEX/Strategy-Campaigns/apex_war_architect`. **A return packet cannot widen the assignment it answers**; the commission now bounds it, and the handoff's own namespace applies only where no originating delegation exists — a case `PacketGuard` independently refuses.

**A gate that raises is not a gate.** `packet_schema` is caller-supplied and was membership-tested against a frozenset, so a list or dict raised `TypeError` and unwound the enforcement call instead of denying. The non-dict *packet* check two rules below exists for exactly this reason and was written three rounds earlier; the selector beside it was left. Sibling untouched, again.

| Finding | Verdict | Outcome |
| --- | --- | --- |
| Omitted `resource_id` skipped record matching on reads | **Correct — P1 fail-open** | Required for canonical packet-backed reads, matching the mutation path. |
| Handoff read scope not bounded by its commission | **Correct — P1 fail-open** | Derived from the matched originating delegation. |
| Non-string `packet_schema` raised instead of denying | **Correct — P2** | Type-checked before the membership test. |
| `role_adherence` floor allowed a boundary breach to average out | **Correct — P2** | Pinned at 1.0. That metric carries "refuses any high-impact boundary action", and a breach is not averageable — two seed cases sat at 0.8 and were raised. |
| Dirty-tree runs recorded modes as proven | **Correct — P2** | The artifact preserves the commit but not the diff, so "which code passed?" had no answer while the acceptance gate treated the record as rollback evidence. The run still executes and writes results; only the *proven* claim is withheld. |
| Documented gate invoked `ruff` without installing it | **Correct — P2** | `runtime-contracts.txt` carries no Ruff, and pre-commit's isolated hook environment is not on `PATH`, so the sequence stopped at `command not found`. Pinned install added to both documents, with a test that the documented version matches the CI pin. |

**Mutation testing produced two corrections to my own work this round.** The Ruff fix came back MISSED — no test covered it — and the test written in response then failed on its own explanatory comment, because it searched the whole file and the comment mentions `ruff check` while describing the defect. That is the same prose-versus-property weakness corrected in the metric-table test two rounds ago, reappearing in a test written by the process that recorded it. Scoped to command lines inside the fenced block now.

**A procedural note worth keeping.** Restoring files after a mutation run left stale `__pycache__` for modules imported through the `evals/` path shim, and the suite reported four failures against correct source. The bytecode, not the restore, was wrong. Mutation runs on path-shimmed modules need a cache clear before the result is believable — a wrong conclusion here would have been "my fix broke something" when nothing was broken.

### Automated review, twenty-fifth pass — eight findings, eight fixed

No deferrals this round. Two P1 fail-opens in `scripts/policy_enforcement.py`, one
threshold accessor in the harness, and four documentation claims that had stopped
being true of the thing they describe.

**A naming convention walked straight through the high-impact boundary.** The
action tokenizer folded case *before* splitting, so `deleteAll` became the single
token `deleteall` — matching no verb, qualified by nothing, and passing the
boundary with no instruction required. The same held for `publishReport`,
`sendEmail`, `rotateCredentials`, and `bulkDelete`. The snake_case forms have been
covered since the twentieth pass; camelCase, which is what most dispatchers
actually emit, was outside the control the whole time.

Fixing it through a *shared* tokenizer — one function serving both `_is_mutating`
and `_boundary_category`, rather than a second regex at the second site —
uncovered **a second fail-open nobody reported**. The old expression split on
`[^a-z]+`, which consumed the capital starting each camel segment: `listPurge`
tokenized to `['list', 'urge']` and classified as a **read**, skipping every
mutation control. That is the opposite of what the action is. It is recorded here
because it was found by the *shape* of the fix, not by the finding — writing the
shared helper is what made the divergence visible, and a narrower fix at the one
reported call site would have left it in place. `GetInfo` was over-classified by
the same expression, in the harmless direction.

**A delegation could authorize exactly what it forbids.** `prohibited_scope` is a
*required* field of the delegation schema and nothing in the enforcement point
ever read it. A schema-valid packet whose `prohibited_scope` named its own
`memory_namespace` granted access to that namespace: the packet contradicted
itself and the contradiction resolved toward access. The check is applied
**before** the allowlist, because a prohibition that only bites where the
allowlist already denies is not a prohibition. Only machine-resolvable entries are
enforced; `prohibited_scope` also carries prose ("binding commitments") that no
comparison here can adjudicate, and guessing at it would deny lawful work on a
string match.

**One decision written as two numbers, again.** `validate_thresholds` governs what
a case *declares*; nothing governed what it *omits*. When
`MINIMUM_THRESHOLDS["role_adherence"]` was raised to 1.0 last round, the judge
kept its own `0.8` default literal, so a case that simply did not mention the
metric got partial credit on the gate carrying the high-impact refusal. Both now
route through one accessor. `tool_correctness` also became a baseline metric: it
is the only metric scoring the *observed* invocation trace, and
`packet_only_no_direct_connectors` is a property of every mode rather than of the
cases that happened to list it.

| Finding | Verdict | Outcome |
| --- | --- | --- |
| camelCase actions bypassed the high-impact boundary | **Correct — P1 fail-open** | Shared camelCase-aware tokenizer used by both classification sites. |
| `prohibited_scope` was never consulted | **Correct — P1 fail-open** | Applied ahead of the allowlist; prose entries left to the role judge. |
| An omitted threshold fell below its floor | **Correct — P2** | One accessor clamps declared and omitted alike. |
| `tool_correctness` was case-declarable | **Correct — P2** | Promoted to baseline; a case can no longer omit the connector-isolation gate. |
| `CONTRIBUTING.md` implied pre-commit ran every CI gate | **Correct** | Described as a subset, naming what stays manual. |
| The runner's own usage block omitted the required `--run-id` | **Correct** | An operator following it was refused before anything executed. |
| The rollback said "delete the directory" after growing CI wiring | **Correct** | Enumerated across five files. |
| `README.md` did not mark the harness unwired | **Correct** | Marked, tied to the exception the source raises. |

**Mutation testing found the real defect of this round: I fixed eight things and
tested none of them.** All eight came back MISSED on the first run. The code was
correct and the repository could not tell — every one of these fixes would have
survived being reverted by a later change. Nine regression tests were written in
response and the mutations re-run until all eleven were caught.

Three second-order corrections came out of that, each worth more than the finding
that produced it:

- The baseline-metric documentation test was **one-directional** — it proved every
  implemented baseline metric appeared in the record, and passed happily when the
  record named a metric the code no longer treated as baseline. It now asserts set
  equality against the enumeration between the em dashes.
- The usage-block test, scoped to the whole `Usage:` section, passed with the
  option missing from **every invocation**, because the prose underneath happens
  to name it. That is the paragraph-instead-of-the-thing failure this record has
  now logged three times, in a test written by the process that recorded it twice.
  Scoped to the command lines.
- An ordering test hand-built an allowlist to force the situation and tripped the
  private-memory rule instead. **Proving an ordering property with a request that
  was never lawful proves nothing.** Rewritten to assert the property that
  actually distinguishes it: the same request without the prohibition is
  admitted, which is what makes the denial attributable to the prohibition.

**Four of the eight findings were siblings left behind by earlier rounds.** The
README's pre-commit claim was fixed and `CONTRIBUTING.md` — the document a
contributor actually follows before a first commit — was not. `resource_id` was
required on mutations for sixteen rounds before reads. `role_adherence`'s floor
moved and its default did not. Under-testing is what let all four persist: the
sweep for a class is only as good as the test that keeps it swept, and none of
these had one.

### Automated review, twenty-sixth pass — two findings, both fixed

Both were in the previous round's own work.

**The camelCase fix worked on the rule and not on the path.** `evaluate()` calls
`normalize()` before any rule runs, and normalization folded case *without*
splitting camelCase — so `deleteAll` reached the boundary as the single token
`deleteall`. The rule denied when called directly; the enforcement point allowed.
Reproduced before touching anything:

```
deleteAll            direct=DENY   evaluate()=ALLOW
publishReport        direct=DENY   evaluate()=ALLOW
sendEmail            direct=DENY   evaluate()=ALLOW
rotateCredentials    direct=DENY   evaluate()=ALLOW
delete_all           direct=DENY   evaluate()=DENY
```

**The round-25 regression test called the private rule, which is exactly why it
passed.** Nine tests were written last round specifically to stop this class of
defect, and the one covering it tested an entry point the system does not use. A
control is only as good as the path that actually runs, and a test that picks the
convenient entry point measures the author's intent rather than the system's
behaviour. The 610-test suite went green against a live P1 fail-open.

The comment I wrote at the fix site named the cause — "`evaluate()` normalizes the
action to lowercase for every other rule" — and I fixed only the local
re-lowercasing while leaving the normalization that runs first. **Identifying the
cause in prose is not fixing it.**

Fixed by canonicalizing the action to lower `snake_case` in `normalize()` rather
than merely lowercasing it. That keeps the single form every rule reads — which is
what `normalize()` exists for — while carrying the word boundaries through the
fold instead of erasing them. No new `ToolRequest` field, so no rule needs to know
that camelCase exists, and no caller can influence the classification by choosing
a spelling.

**A malformed request unwound the enforcement boundary.** `resource=["docs/x"]`
from malformed deserialized data reached `.strip()` and raised `AttributeError`
before any rule could deny or any audit event could be written. `packet_schema`
was type-checked for this exact reason two rounds ago and every other string field
was left alone. All seven are now checked in `normalize()` — reported *and*
blanked, because the rules downstream call `.startswith`, `.strip`, and `.lower`
on them and would raise in turn.

| Finding | Verdict | Outcome |
| --- | --- | --- |
| `evaluate()` lowercased the action before the boundary rule saw it | **Correct — P1 fail-open** | Canonicalized to `snake_case` in `normalize()`; parity between the rule and the entry point is now asserted |
| Non-string request identities raised instead of denying | **Correct — P2** | All seven string fields type-checked before any string operation |

**Three corrections came out of mutation testing, one of them to the fix itself.**

- The type check blanked the malformed field on the normalized *copy*, and the
  presence check three lines below still read the *original* — so `.strip()`
  raised the very `AttributeError` the check had just been written to prevent.
  **A fix bypassed three lines after being written**, and only re-running the
  reproduction after the fix caught it. Assuming a fix works because the code
  reads correctly is how this round's P1 shipped in the first place.
- Removing the boundary rule's own canonicalization came back MISSED, because
  every action spelling in the parity list happened to resolve identically with
  or without it. It is not an equivalent mutant: `"Public Publication"` folds to
  `public publication`, which is in no set, so the boundary goes quiet. Separator
  variants of every category name are now asserted in both spellings.
- The parity test — the rule and `evaluate()` must reach the same verdict for
  every spelling — is the guard against this whole class. It is the one test
  here that would have failed *last* round.

The recurring-shape list gains: **(n) a test that exercises a private helper
instead of the public entry point proves the helper, not the control.**

### Automated review, twenty-seventh pass — six findings, four fixed, two deferred

**A return packet escaped every prohibition its commission stated.** The handoff
schema defines no `prohibited_scope`, so applying the delegation-level prohibition
to the *submitted* packet meant a handoff was bound by no prohibition at all.
`_packet_namespace_errors`, immediately beside it, already derives its **allowlist**
from the originating delegation. Permission was taken from the commission and
prohibition from the return packet — the same assignment read from two documents,
with the looser one winning.

Reproduced with a control first, which mattered: the first attempt guessed the
packet's agent field, got `None`, and every request denied for the wrong reason.
That reproduction would have "confirmed" the finding while proving nothing. The
sound version shows the same read **admitted** without the prohibition and
**allowed** with it.

**The collection fields were the untouched sibling of last round's fix.**
`delegations=7` reached `list(...)` inside `_packet_admission` and raised
`TypeError` before any denial or audit event. Round 26 type-checked the *string*
fields for exactly this property and stopped there. The class is "every
caller-supplied field a rule performs a typed operation on", not "every string
field" — the scope-to-the-property rule, missed again by the fix that recorded it.
`str` and `dict` are refused too: `list("abc")` and `list({"a": 1})` do not raise,
they silently yield something the caller never meant, which is worse.

**A judge criterion that would have broken on success.** The role-adherence judge
was told unconditionally that the specialist is in shadow and that an executed
write is always a violation. Every mode is `shadow` today, so it is true today —
and the entire purpose of this harness is to move modes out of shadow, at which
point it would have false-failed every lawful active-stage mutation and reported a
promoted specialist as regressed. **A criterion that stops being true when the
thing it measures succeeds is a trap, not a gate.** Now derived from `mode.status`,
with the stage list *imported* from the enforcement point rather than restated, so
the evaluation and the gate cannot disagree about which stages are pre-active.

**A declared artifact type is not the artifact.** `artifact_errors` proved an
artifact of the right *type* was declared and nothing read the record; all three
judges see the mission, the prose, and the case context, and none saw the
structured packet content. Compliant prose beside an empty-but-schema-valid
`campaign_map` satisfied every gate. The case judge now receives the emitted
artifact records, and a deliberately shallow deterministic check refuses a record
carrying nothing beyond its own label — whether the artifact is any *good* is a
judgement, and it belongs to the judge that now has the evidence.

| Finding | Verdict | Outcome |
| --- | --- | --- |
| Handoff reads escaped the originating delegation's `prohibited_scope` | **Correct — P1 fail-open** | Prohibitions inherited from the commission |
| Scalar `delegations` / constraint ledgers raised instead of denying | **Correct — P2** | All three collection fields checked in `normalize()` |
| Proposed-write criterion asserted shadow unconditionally | **Correct — P2** | Derived from `mode.status`; stage list imported, not restated |
| Artifact contents reached no judge and no check | **Correct — P2** | Records handed to the case judge; label-only records refused |
| Constraint packets are self-asserted | **Correct — deferred** | Needs an issuance mechanism; see below |
| Evaluation packets not bound to the current mission | **Correct — deferred** | Blocked behind eval dispatch |

**Two deferrals, both accurate findings.** Neither is declined on the merits.

- **Constraint packets are caller-supplied and self-assert `created_by` and
  `source_proof_hash`.** `PacketGuard` validates schema conformance and ledger
  consistency; nothing authenticates issuance, so a fabricated but schema-valid
  packet can claim Agent 007 authorship and carry cross-brain evidence. Closing
  it needs either an HMAC signature (the machinery exists — `_sign_grant` already
  does this for instruction grants) or an Agent 007-owned issuance registry.
  Either adds a required field to a governance schema and invalidates every
  existing lawful constraint packet, which is a contract change made as a set
  with docs, templates, registry, and tests. **This is the same decision as
  "delegation issuance verification" already on Joe's list.** A `created_by ==
  Chief` check would be theatre — a forger writes that field too — so nothing
  partial was shipped.
- **Evaluation packets are not bound to the current mission.** A stale but
  schema-valid handoff/delegation pair from an earlier mission of the same
  specialist and mode passes every identity and artifact check, so one case could
  be recorded as proven using another assignment's evidence. The fix requires a
  trusted invocation identity returned by dispatch, and dispatch is unwired and
  on the deferred list. Recording it here so it is not rediscovered as new.

**Mutation testing: nine mutants, two initially MISSED — and the reason is
structural.** `evals/test_specialist_modes.py` deliberately does not run under
`unittest discover`, because it needs deepeval and a model credential. Deleting
the substance check from the suite body and blanking the records handed to the
judge both left 630 tests green. **A checker the evaluation suite never calls
protects nothing, and nothing was watching whether it was called.** Four
AST-based wiring tests now assert the suite's structure against its parsed
source — including the general property that every helper imported from `harness`
is actually used, which covers the class rather than this round's two functions.

The recurring-shape list gains: **(p) a component excluded from the mandatory
suite has no test observing whether it is wired in — assert its structure.**

### Automated review, twenty-eighth pass — three findings, two fixed, one deferred

No P1s. All three correct.

**The documented install and the audited environment were different environments.**
CI installs `requirements/lock-runtime-*.txt` and osv-scanner audits exactly those
with `--no-resolve`, while every documented command — `README.md`,
`CONTRIBUTING.md`, `evals/README.md` — told a human to install the *floating
manifest*. A dependency published after the last drift run therefore lands on the
workstation without being the version CI tested or the scanner cleared. This is
the aggregate-versus-hand-run divergence again, this time between CI and the
documentation a person actually follows. All four documented installs now name
their lock, and the root tier was swept in the same pass rather than waiting to be
reported: the finding named three files and `README.md` had a fourth.
`requirements/runtime-orchestration.txt` has no lock at all, so it is now labelled
as unlocked and unscanned rather than quietly left looking equivalent.

The test derives the manifest→lock pairs **from the `locks` drift-check job**, so
a fourth tier locked in CI and left floating in the documentation fails here.
Restating the pairs would have reproduced the same divergence one level up.

**A rollback that claimed nothing changed, on a page that said otherwise.**
`docs/DEPENDENCY_AUDIT_2026-07-25.md` ended with "No dependency, pin, or
governance rule was changed" while the same record states two sections above that
the audit raised the evaluation manifest to `pytest>=9.0.3`. Following it would
also have left `osv-scanner.toml`, three generated locks, the drift-check job, and
the lock-based install steps in place. **`docs/EVALUATION_HARNESS.md` had this
exact defect corrected three rounds earlier and this sibling was left standing** —
because the test written then was scoped to that one document. The check is now
scoped to the property: every dated record carrying a `## Rollback` section, with
a specific assertion against a rollback claiming no pin changed while its own body
raises one.

**Deferred: the governance mount has no lawful admission path.**
`admit_delegation_packet` begins with the unrecognized verb `admit`, so it
classifies as a mutation; full evaluation then requires a writer lease and a
packet whose write target covers `mount:governance`. Verified rather than assumed
in both directions: a lease **can** be issued for that target and a signed launch
grant **can** be minted for the mount — `require_grant` is not consulted, since
`_launch_grant` obliges a grant for every mutating mount request. `PacketGuard` is
what closes the path, requiring a write target registered to a brain unit, which a
mount handle can never be. A read-classified governance tool (`validate_packet`)
evaluates cleanly, so the mount is not unreachable in general; only its mutating
tool is.

The tool's real side effect is an **append to a hash-chained audit ledger**, not a
mutation of a canonical brain record, and modelling it as the latter is what
produces the dead end. Closing it means introducing an append-only audit
authorization path — a new category of permitted action in the governance model.
That is a decision about what may write without a lease, and given how reliably
fixes in this file have produced fail-opens, inventing a lease exemption
unsupervised is the wrong risk to take. `enforce()` has no call sites, so nothing
is broken today; **the moment it is wired, this mount bricks.** Recorded as a
tripwire test class that asserts the current dead end and instructs the next
author to update it and this record together — not an endorsement of the
behaviour, but a guarantee it cannot be rediscovered by a twenty-ninth review.

| Finding | Verdict | Outcome |
| --- | --- | --- |
| Documented installs used floating manifests while CI scanned locks | **Correct — P2** | All four pointed at their locks; pairs derived from CI |
| Dependency-audit rollback incomplete and self-contradicting | **Correct — P2** | Rewritten; the check now covers every dated record |
| No lawful path to the governance mount's admission tool | **Correct — deferred** | Needs an append-only audit authorization path; Joe's decision |

**A mutation left MISSED, deliberately.** Dropping the evaluation lock from one
clause of the `EVALUATION_HARNESS.md` rollback is not caught, because the lock is
still named in a different clause of the same section — so the property the test
enforces ("the rollback names this artefact") genuinely still holds. Telling
"named for deletion" apart from "named in another context" needs prose semantics,
and a test that matched specific phrasing would be the prose-instead-of-property
failure this record has logged three times. Recorded as a known limit of the check
rather than papered over, because a MISSED mutant that is investigated and
explained is a different thing from one that is not looked at.

**The new rollback check found its own defect on first run.** It located the
section with a substring search for `## Rollback`, and this record's prose
mentions that string inline while describing the check — so it treated a sentence
about rollbacks as the start of a rollback section, and reported a document that
has no such section as having an incomplete one. Anchored to the heading now. It
is the prose-versus-property failure again, this time in the *selection* of what
to test rather than in the assertion: matching text that merely looks like the
thing is not finding the thing.

**Two further corrections were to existing tests, both hard-coded
spellings.** The install-ordering tests indexed the literal manifest path and
therefore **crashed with `ValueError`** — not failed with a message — the moment
the documented command was pointed at the lock. A test that names an incidental
spelling blocks a change it has no opinion about, and reports it as an error
rather than a disagreement. And the harness rollback test's candidate set
enumerated CI wiring and documentation and stopped, missing the requirements files
the harness itself introduced: the same too-narrow scoping that test exists to
catch, inside that test.

### Automated review, twenty-ninth pass — six findings, five fixed, one deferred

**A prohibition was satisfied by asking for more than it forbade.** Containment
was checked one way only — whether the prohibited scope covers the request. A
commission allowing `APEX::Roundtable` while prohibiting
`APEX::Roundtable::secret` therefore authorized a read of the **parent
collection**, which serves the withheld record along with everything else. Now
denied in both directions. Denial rather than filtering is deliberate: this is an
authorization decision with no access to the records, so it cannot serve a
redacted collection, and there is no third answer between allowing the exposure
and refusing the read. A commission that means to permit the parent must not
prohibit a child of it.

The over-denial direction is tested too. `APEX/Strategy-CampaignsX` shares a
textual prefix with `APEX/Strategy-Campaigns` and contains nothing of it; a
`startswith` without the separator would deny it, which is over-denial dressed as
rigour.

**A drive-relative path walked out of the tree.** `_DRIVE_ABSOLUTE` required a
separator after the colon, so `C:\secret.txt` was caught and `C:..\secret.txt` was
not — separator normalization turns it into `C:../secret.txt`, which matches
neither that pattern nor the leading-`../` check. `C:secret.txt` was equally
uncaught. Verified: a chief read of each returned **`allowed=True` with an empty
reason tuple**. Windows resolves every drive-qualified spelling against that
drive's current directory, which this module cannot know, so all of them are now
escapes. Checked in the other direction that `APEX::Roundtable` is not swept up —
its second character is not a colon, which is what keeps it out.

**The fourth ledger.** The previous round hand-listed three collection fields and
missed `active_leases`, so `active_leases=7` still raised `TypeError` out of
`_usable_leases`. Reachable only on the **no-registry** path, where `_lease_ledger`
falls back to the caller's copy — the first reproduction used a registry, found
nothing, and had to be re-run against the right construction before the finding
could be confirmed. The replacement test enumerates the tuple-typed fields **from
the dataclass**, because a hand-written list is precisely how a fourth field gets
missed.

**Two documentation findings, both siblings of last round's own fix.**

- `evals/run_evaluations.py` printed "install `requirements/runtime-evaluation.txt`"
  to an operator who had just been told the runtime was missing — the one
  instruction seen at the moment it is acted on. The sweep that corrected every
  document missed it because the sweep, and its test, were scoped to `*.md`. **A
  command a program prints is documentation too**; the file type was the
  incidental part.
- The documented "run everything by hand" sequence installed only the contracts
  lock, while CI's validate job installs the **root** lock first — and that lock
  carries `autogen-agentchat`, so `tests/test_autogen_orchestrator.py` skipped on
  the workstation and ran in CI. A sequence advertised as reproducing the gate
  that quietly exercises fewer tests than the gate is the aggregate-versus-hand-run
  divergence again, in the direction that lets a real failure reach CI unseen.
  Both sequences now install every tier CI installs, derived from the workflow.

| Finding | Verdict | Outcome |
| --- | --- | --- |
| Parent read allowed while a descendant was prohibited | **Correct — P1 fail-open** | Containment checked both ways; over-denial tested |
| Drive-relative paths escaped the tree | **Correct — P1 fail-open** | Every drive-qualified spelling is an escape |
| `active_leases` not type-checked | **Correct — P2** | Added; the test now derives the field list |
| The runner printed the floating manifest | **Correct — P2** | Points at the lock; the check now covers printed commands |
| Manual sequence installed fewer tiers than CI | **Correct — P2** | Root lock added to both, derived from the workflow |
| No production issuer for instruction grants | **Correct — deferred** | See below |

**Deferred: there is no trusted issuer for instruction grants.** Accurate.
`_high_impact_boundary` accepts only a signed grant bound to action and resource;
`trusted_launcher.py` issues *mount*-shaped grants, and the only instruction-grant
constructor in the tree is a test helper calling the private `_sign`. Once
`enforce()` is wired, an action Joe has expressly authorized has no supported path
through the boundary. Building the issuer means creating a command that mints
Joe's personal authority for the six actions `AGENTS.md` reserves to him —
whoever can run it can authorize a financial transaction or a public publication.
**Who may operate that command, and under what custody the signing key sits, is
the decision**, not the code. It belongs with the governance-mount audit path and
constraint-packet issuance already on the list; all three are the same question —
what constitutes proof that an authorization was issued rather than asserted.

**Mutation testing caught one weakness in this round's own test.** Asserting the
locks appear *in the document* passed while the sequence itself had lost the root
lock, because the same filename appears in a separate paragraph about the AutoGen
adapter. Presence somewhere in a document is not presence in the steps a
contributor executes; scoped to the fenced block that invokes the suite. The
equivalent weakness one round earlier was recorded as unfixable — this one was
fixable, and the difference is that "the steps that run the suite" is
mechanically identifiable while "named for deletion" is not.

### Thirtieth pass — the instruction issuer, built on Joe's direction

Joe marked four findings **Fix** on the twenty-ninth round. Three were already
fixed in `3f8851b` (the prohibition containment, the `active_leases` type check,
and the CONTRIBUTING install sequence — his markers landed on the corrected
lines). The fourth was `_high_impact_boundary`'s grant requirement, which this
record had **deferred to him**: marking it Fix is the decision, so the issuer is
built.

**`scripts/issue_instruction.py` mints the grant the boundary demands.** Before
it, the control was not merely strict — it was **unsatisfiable**. Nothing in the
repository could produce an instruction grant: the launcher issues mount-shaped
grants, and the only constructor was a test helper calling the private `_sign`.
An action Joe had expressly authorized had no path through the gate.

Four decisions worth stating, because each was a place this could have gone
wrong:

- **A separate command from `trusted_launcher.py`.** Launching a mount and
  minting Joe's personal authority for the six reserved actions are different
  privileges, and the second must not be a subcommand of the first. It is also
  forced: the enforcement point already imports the launcher's `_sign`, so
  putting the issuer there and importing the classifier back would be circular.
- **The signing primitive is imported, never reimplemented.** Two definitions of
  "what a valid grant looks like" is how an issuer and its verifier drift apart,
  and the operator would be the one holding the rejected authorization.
- **The grant records the boundary CATEGORY, derived with the enforcement
  point's own classifier.** An issuer storing the raw verb would mint grants
  that never match, and the reasonable conclusion would be that the gate is
  broken. This does mean an instruction is scoped to the category rather than
  the literal verb — `publishReport` and `sendEmail` are both
  `public_publication`, so one authorizes the other **on the same resource**.
  That is the boundary's own granularity, not a widening introduced here, and it
  is the right one: verb spellings are not stable, which is what the twenty-sixth
  pass was about. The resource binding is exact.
- **The window is capped at 60 minutes and defaults to 15.** An instruction that
  outlives the conversation it came from is a standing authorization, which is
  the thing a per-action boundary exists to prevent.

The issuer also refuses to mint for a non-boundary action. Issuing a meaningless
grant for `read` would teach the operator that minting instructions is routine,
and the entire value of this control is that it is not.

**What it does not do, stated in the module and printed on every issue:** the
grant is replayable until it expires. Single-use enforcement needs the nonce
consumed at an execution boundary, and a policy evaluation deliberately has no
side effects — otherwise *asking* whether an action is permitted would burn the
grant. `trusted_launcher` consumes mount-grant nonces because it *is* an
execution boundary; there is no equivalent for instructions until `enforce()`
has call sites. **Nonce consumption remains an open decision, and the short
window is a mitigation rather than a fix.**

The binding test is end-to-end: issue a grant, hand it to
`_high_impact_boundary`, require the action permitted — with a control proving
the same request is refused without one. Every category in `HIGH_IMPACT_ACTIONS`
is exercised, derived from the set rather than sampled, because one category
left unissuable is one act Joe cannot authorize and it would be discovered only
when he tried.

**A Copilot finding arrived mid-round and is fixed here too.**
`LeaseRegistry.release()` appended the **live** lease object to `_history` and
returned that same object, so a caller could rewrite recorded audit evidence
after the fact — setting `status` to `verified` on a lease whose readback was
never confirmed is exactly the claim the readback gate exists to prevent.
Reproduced, then fixed with two independent copies. `issue()` and
`active_lease()` were given copies in an earlier round and `release()` was the
untouched sibling; it was also the worst of the three, because it is the one
that writes history. `_expire()` — the third path into `_history` — was
corrected in the same change even though nothing outside currently holds that
object: an invariant that holds on two of three paths is the shape every sibling
finding in this record has taken.

**One mutation left MISSED and recorded.** Storing the live object in `_history`
while returning a copy is not detectable: after `del self._active[key]` nothing
outside holds a reference, so no behavioural test can distinguish it from the
copy. It is kept as defence in depth against a future path that retains one.

### Thirty-third pass — three findings fixed, four already on the decision list

Rounds thirty-one and thirty-two are recorded in their commit messages
(`212b548`, `42c8aed`) rather than here; this section covers the round that
followed them.

Seven findings arrived. Four are items this record already defers to Joe —
delegation-issuance authentication, consequential-parameter binding on
instruction grants, the Windows/colorama evaluation lock, and the filesystem
mount's missing npm lock. Re-listing them as new findings would inflate the
count and obscure that they are waiting on a decision, not on work. Three were
new and are fixed.

**The packet's own concurrency controls were declared and never read.**
`require_expected_version` and `require_idempotency_key` are **required** fields
of `schemas/delegation_packet.schema.json`, so every validated write-bearing
packet states a position on both — and no rule consulted either. A packet
setting both to `true` admitted a mutating request that supplied neither.
Reproduced first, with a control: the same request against a packet that waives
both is allowed, so the denial is attributable to the flag and nothing else.
Every other dimension of a write — target, record, brain, lease, operation — was
bound while the two controls the issuer itself insisted on were optional in
practice; a blind overwrite and a double-apply both passed the check that exists
to stop them.

Three things about the fix are worth stating:

- **Absence of a flag is not read as a demand.** That looks like the "absent
  scope means unlimited scope" defect this record fixes three times, but it is
  the opposite shape: an allowlist's silence is a claim about what is permitted,
  whereas these flags are a claim about what the *issuer requires*. Inventing a
  requirement the issuer did not state would deny lawful appends to append-only
  records, where no prior version exists to compare against — fail-shut instead
  of fail-open, and just as broken. A **malformed** flag is different and is
  treated as a demand: only `False` and absence waive.
- **The controls are enumerated once, against the schema.** A test derives the
  set of `require_*` fields from `delegation_packet.schema.json` and asserts the
  gate reads exactly those, because a third control added to the schema would
  otherwise be a required field no rule consults — which is this finding again.
- **It proves the control is CARRIED, not that it is HONOURED.** Nothing at a
  policy boundary can tell whether the executor performs a compare-and-set, or
  whether an idempotency key was already consumed; that needs a ledger of
  applied keys at the execution boundary — the same shape as the unimplemented
  nonce consumption for instruction grants, and open alongside it. Carrying the
  value is the precondition: before this, a mutation reached the executor with
  nothing to compare and nothing to deduplicate, so the executor could not
  honour the control even if it tried.

**One mutant survived and produced a better test.** Replacing
`demanded is False or demanded is None` with `if not demanded` left the suite
green, because the case written for it used the string `"false"` — truthy in
Python, so both spellings held the line. The falsy malformed values (`0`, `""`,
`[]`) are where truthiness silently waives the control, and the test now covers
all four. A surviving mutant is a missing test, not an equivalent one.

**`behavioral_modes_proven` was withheld as `[]` where it is emitted as a
boolean.** `Coverage.summary()` writes `bool(self.modes) and not self.unproven`;
the dirty-tree withholding path replaced it with an empty list. Both are falsy,
so nothing in Python noticed — but the artifact is JSON read by other things,
and a consumer doing `proven is False` or any typed deserialization sees a type
it was never promised. **The test asserted the defect**: it compared against
`[]`, which is the recurring shape where a test encodes the wrong value as the
expected one. It now asserts `is False`, and a second test compares the withheld
type against the producing module's, so the two cannot drift again.

**The relay connector's npm lock was outside the vulnerability gate and the
update mechanism.** `connectors/relay/package-lock.json` was committed alongside
the APS one; only APS was scanned by `osv-scanner` and only APS had a Dependabot
entry, so the second npm dependency tree in this repository — `agent-relay` and
its transitive graph — received neither vulnerability reports nor update PRs
while both files read as complete coverage. The hygiene test that should have
caught it enumerated lockfiles **by hand**, so it passed. It now derives the set
from the tree, on both the scan and the update side.

**Two YAML near-misses in that fix are now tested for, because both parse.**
The first draft put the explanatory comment *inside* the `scan-args: |-` block —
a block scalar has no comment syntax, so those eight lines would have been
passed to `osv-scanner` as arguments. The repair then left **two** `scan-args:`
keys under one step, which parses fine and silently discards the earlier value.
`tests/test_repo_hygiene.py` now detects both classes across every workflow and
`dependabot.yml`, hand-rolled rather than parsed because PyYAML is in no live
requirements manifest and `skipUnless(yaml)` is the silent-degradation pattern
this record spent a round removing. The detector distinguishes **data** blocks
from **script** blocks: a `#` line in `run: |` is a correct shell comment, and
the first version flagged every commented step script in the repository — a
check that fires on correct code gets suppressed, and then it is not a check.

#### What the relay scan found the moment it was switched on

Four npm vulnerabilities, all in `connectors/relay/package-lock.json`, all
**pre-existing** — the lock was committed earlier and went unscanned, and the
coverage gap is what had been hiding them. That is the gate working, not a
regression introduced by turning it on.

| Advisory | Package | Have | Fixed in |
| --- | --- | --- | --- |
| `GHSA-3jxr-9vmj-r5cp` | brace-expansion | 5.0.6 | 5.0.7 (CVSS 7.7) |
| `GHSA-mh99-v99m-4gvg` | brace-expansion | 5.0.6 | 5.0.8 (CVSS 7.5) |
| `GHSA-j3f2-48v5-ccww` | protobufjs | 7.6.4 | 7.6.5 (CVSS 5.3) |
| `GHSA-frvp-7c67-39w9` | @hono/node-server | 1.19.15 | 2.0.5 (CVSS 5.9) |

**None is fixable from this repository, and the reason took some finding.**
Three are transitive under `@earendil-works/pi-coding-agent`, which ships its
own **`npm-shrinkwrap.json`**. npm honours a published shrinkwrap exactly, and
`overrides` cannot reach inside it. This was established rather than assumed:
both the flat and the nested override forms were added, `node_modules` was moved
aside, and the lock was regenerated from scratch — 485 packages, 483 resolved,
the pinned versions unmoved. The parents' declared ranges would have accepted
the patches (`minimatch` asks for `brace-expansion ^5.0.5`, `@google/genai` for
`protobufjs ^7.5.4`), so the range is not the blocker; the shrinkwrap is. The
fourth is a genuine range conflict: `@modelcontextprotocol/sdk` declares
`@hono/node-server ^1.19.9` and the fix is a major outside it.

An intermediate regeneration produced a lock with **10 of 459 packages carrying
`resolved`**, against 483 of 485 in the committed one. It was not committed:
npm had rebuilt the tree from an existing `node_modules` instead of the
registry, and shipping it would have dropped resolution and integrity metadata
for 473 packages — a supply-chain regression sold as a security fix. The
difference was visible only because the two locks were compared before
committing.

`npm audit fix` offers exactly one remedy: downgrade `agent-relay` from 11.2.0
to **10.6.7**, a semver-major move of the declared dependency. That is Joe's
call, not a patch, and it is in the open list below.

So the four are triaged in `osv-scanner.toml` with a **one-month** expiry —
shorter than the three-month windows on the findings that are unfixable in
principle, because these are fixable upstream and the expiry is what forces the
recheck. Mitigating but not excusing: `connectors/relay` is declaration-only and
no relay server is configured, so nothing here executes that tree today.

**The file claimed this property about itself and nothing enforced it.**
`osv-scanner.toml` opens by saying `ignoreUntil` "is the point. These expire and
come back, so a triage decision cannot quietly become permanent by being
forgotten." No test asserted any of it. `VulnerabilityTriageTests` now requires
every entry to carry an expiry and a reason substantial enough to re-evaluate,
refuses an exemption dated far behind its siblings, and — where a reason names a
fixed version — requires it to also name why that fix was not taken. The window
check is anchored on the file's newest entry rather than on `date.today()`,
because a check that starts failing on a fixed calendar day for reasons
unrelated to any change is a time bomb in CI, not a check.

### Thirty-fourth pass — two findings fixed, one refuted

**The refuted one first, because verifying a reviewer's PREMISE is the part
that gets skipped.** A P1 said the `.gitleaksignore` history entry names commit
`03cb443…`, "which I verified is not an ancestor of the reviewed commit", and
that the `BASE_SHA..HEAD` scan therefore "still reports this known fixture and
blocks the PR". Every load-bearing claim is false, and the check was already
green when the finding arrived:

- `git merge-base --is-ancestor 03cb443… HEAD` returns **yes**.
- The commit `d6c9cb33…` the finding offers instead **does not exist** in this
  repository (`git cat-file`: not a valid object name).
- Running CI's two scans by hand on the reviewed commit: `gitleaks dir` — no
  leaks; `gitleaks git --log-opts=4f7693f9..HEAD`, 56 commits — no leaks.

And the control that makes that meaningful, because "no leaks found" also
describes a scan that examined nothing: with `.gitleaksignore` moved aside, the
history scan reports **exactly one** finding, fingerprinted
`03cb443…:scripts/privacy_guard.py:generic-api-key:321` — character-for-character
the entry at line 18 — and the tree scan reports exactly the six working-tree
fingerprints listed below it. The suppressions are load-bearing and correctly
spelled. Nothing changed.

**A negative lookahead exempted everything concatenated after a placeholder.**
The credential-assignment pattern excuses a value that is a lone
`{identifier}`, because the guard's own fixture writes one and the guard was
failing its own scan. The comment said the value must be "a lone `{identifier}`
and nothing else" — **the lookahead stopped at the placeholder's closing quote
and never asked what followed.** So an assignment opening with a placeholder and
then concatenating a real value was excused on the strength of its first eight
characters. Reproduced against a control differing only in that prefix: the
plain literal was flagged, the prefixed one was not.

Fixed with `NOT_CONTINUED`, the anchor the hostname and organization exemptions
already carry — a second spelling of "the exemption must cover the whole value"
is how two rules drift apart. **The first attempt was incomplete and the case
list caught it**: reusing `VALUE_END` still let adjacent literals
(`"{prefix}""realCredential"`) through, because `VALUE_END` permits a following
quote. That is correct for the bare-value sites it was written for, which stop
*before* the value's own closing quote, and wrong for an exemption that consumes
its closing quote — there a following quote can only open a concatenation.
`QUOTED_VALUE_END` is `VALUE_END` minus that allowance, split out rather than
tightened in place because the bare-value sites need it.

The fix deliberately over-flags `= "{prefix}".format(...)`, which holds no
literal secret. Stated rather than hidden: the author restructures one line,
where the alternative is a credential reaching a public repository behind a
placeholder prefix. Eleven probes, both directions, and all four mutants killed.

**Provenance was sampled before the run and trusted after it.** `provenance()`
records `tree_dirty` when the report is built; `pytest` then runs; nothing
re-checks. A run that started clean and *ended* dirty — a dispatched specialist
writing a file, a tool call leaving an artifact — was credited to a commit whose
code is no longer what passed. The worktree is now sampled twice through one
extracted helper, so the two readings cannot disagree about what "dirty" means,
and both must read `False`.

Three details, each a shape this record has hit before:

- **A missing sample is not a clean one.** `_record_passes` is reachable
  directly; a caller omitting the post-run reading would otherwise get the
  proven claim for free.
- **The samples are enumerated in `TREE_SAMPLES`**, and a test withholds on each
  name independently, so a third sample added later cannot be a declared
  control nothing reads.
- **Outside a checkout the probe returns `"unknown"`, never `False`** — the
  silently-degrading-checker failure found in three separate CI jobs.

**Two mutants survived the first pass and produced the two best tests here.**
Deleting the post-run sampling line from `execute()` left the suite green,
because nothing drives `execute()` end to end — it shells into pytest. That is
now an **AST** check: the assignment must exist and its line must come *after*
the `pytest.main` call, parsed rather than grepped because a substring search is
satisfied by the word appearing in a comment. Moving the sample back before
`pytest` now fails too. The second survivor was the `"unknown"` branch, which no
test exercised at all.

### Thirty-fifth pass — one finding, and a correction I owe the previous round

**The correction first.** Round 34 refuted a P1 about the `.gitleaksignore`
history entry. The refutation was right on every fact it checked — the commit
*is* an ancestor, the replacement commit offered does not exist, both scans were
clean, and the suppression was load-bearing. **But the mechanism the finding
gestured at is real, and the very commit that recorded the refutation triggered
it.** Round 34 edited `scripts/privacy_guard.py`, which shifted its credential
fixture down 32 lines, and a working-tree fingerprint is pinned to a *current*
line number. So `gitleaks dir` went red on `6772084` while the history scan
stayed green.

Three things about that are worth writing down:

- **The stale entry pointed at a bare `),`.** Line 330 no longer held anything a
  `generic-api-key` rule could match; the fixture had moved to 362.
- **The local pre-commit hook passed the commit CI rejected.** The hook runs
  `gitleaks git --pre-commit --staged` — the staged diff. CI runs `gitleaks dir .`
  over the whole tree plus `gitleaks git BASE..HEAD`. Local green never predicted
  CI green here, which is a variant of the silently-degrading-checker family:
  not a check that proves nothing, a check that proves something *else*.
- **Refuting a finding's claims is not the same as refuting its class.** The
  claims were false and saying so was correct. The class — line-pinned
  suppressions drift — was live, and one round later it fired.

`GitleaksSuppressionTests` now closes it without adding a dependency: every
working-tree entry must cite a line that still exists and that could plausibly
produce the rule it names. It cannot prove an entry is *right* — only gitleaks
can, and gitleaks is not in the mandatory suite — but drift is the failure that
actually happens, and it now fails in the suite that pre-commit already runs.
Verified by reverting the line number and watching it fail.

**The finding: `scheduled_task_change` gated ordinary task work.** `task` was in
the noun set, so `create_task` and `delete_task` — ordinary task-registry writes
— demanded Joe's personally signed instruction. `AGENTS.md` reserves
"scheduled-task creation or deletion"; a bare task is not a schedule, and a
boundary that fires on ordinary work is one an operator learns to wave through.
That is the reasoning that already keeps `read` out of the issuer and `submit`
behind a qualifier.

**Removing `task` exposed a fail-open in the same rule that the finding did not
mention.** `schedule_task` — about as literal a scheduled-task creation as
exists — was *already* ungated, because both its tokens were nouns and the rule
demanded a verb. Fixing only the reported direction would have left it.

**And the fix for that introduced a third defect, caught by the reverse
direction.** Accepting `schedule` as a verb anywhere in the name let one token
satisfy both halves of the rule, which gated `read_schedule` and
`view_schedule` — the same over-gate the finding was about, reintroduced by its
own repair. The scheduling verbs now count only in **leading** position, which
is a real structural claim rather than a tiebreak: the leading token of an
action is its verb everywhere in this codebase.

Markers match as a substring of a **token**, never of the whole action, so
`unschedule` and `rescheduled` carry one while `multitasking` does not — the
round-7 lesson, where whole-string substring matching made `delete_thread` a
read. Thirty-eight probes, both directions, exhaustive rather than sampled
because every previous round of this rule was correct in one direction and wrong
in the other. Four mutants killed, including the two intermediate states above.

### Thirty-sixth pass — six findings, and a fail-open inside one of the fixes

Two of the six are consequences of the previous round's own narrowing, and one
is the general case of a defect that round fixed only for schedules. That is the
dominant pattern of this whole record, arriving again.

**Credential and access-control changes were not gated.** `AGENTS.md` §9
reserves "access-control or credential changes" and only four bare verbs were
mapped — `revoke`, `grant`, `rotate`, `authorize`. The spellings a dispatcher
actually emits matched none: `reset_password`, `change_credentials`,
`update_access_control`, `delete_api_key`, `set_permissions`, `disable_mfa`.
Now a compound verb+noun rule, like the legal, schedule, and governance rules,
because the verbs here (`update`, `change`, `set`, `delete`) are the most
generic in the vocabulary and mapping them bare would gate nearly every
mutation in the repository.

**The destructive half of the schedule vocabulary was missing —** and it went
missing *because of round 35*. `destroy_schedule`, `erase_cron`,
`cancel_scheduled_task`, `disable_cron` and `clear_timer` all carried the
scheduling marker, named a deletion, and skipped the boundary. Narrowing a rule
is precisely when its verb list needs re-reading; the previous round removed
`task` and never asked what the remaining verbs missed.

**Reading a high-impact record demanded Joe's signature.** `post`, `purchase`,
`invoice` and `transfer` are **nouns** sitting in a map named
`HIGH_IMPACT_VERBS`, and the classifier scanned every token — so `read_invoice`,
`view_post`, `get_purchase` and `inspect_transfer` were financial transactions
and public publications. This is the general case of the `read_schedule`
over-gate fixed one round earlier for schedules alone: **the instance was fixed
and the class was left.**

The obvious repair — match only the leading token — is a fail-open, and it was
written and reverted: `force_publish` and `admin_grant_access` lead with a token
in no map. The exemption is instead scoped to the linguistic fact it encodes:
the leading token must be a read verb **and** every mapped token present must be
one of those four noun-capable words. `read_and_publish_report` still gates.

**`allowed_actions` was a required schema field no rule read** — the same shape
as the concurrency controls three rounds earlier. Now bound, with a limit worth
stating plainly: the schema's `allowed_actions` is a six-value enum of
*collaboration* actions while `ToolRequest.action` carries *dispatcher* verbs,
and they are different vocabularies. So the rule refuses an action that is in
the packet's vocabulary and was withheld, and leaves dispatcher verbs to the
namespace, target, operation and lease bindings. The stricter rule — deny
anything not literally listed — was tried and reverted because it denied every
`read` and `write` in the suite. **The residual gap is real and is Joe's:** a
request naming `list` against a delegated namespace is still admitted, and
closing it needs a dispatcher-verb mapping or a widened enum in `schemas/`,
which this branch does not touch.

Establishing that the new rule is *reachable at all* took a third attempt.
Every collaboration action except `read_packet_evidence` classifies as a
mutation and is denied earlier on write scope, and `PacketGuard` requires
`read_packet_evidence` in `allowed_actions` whenever a delegation carries
evidence — so with evidence present the action cannot be withheld and the rule
has nothing to refuse. It is demonstrable only for a delegation with empty
`allowed_evidence`. A control that cannot fire is the "unsatisfiable gate"
defect, and the difference between shipping one and not was checking.

**A demoted specialist kept its authority in a running process.** `__init__`
read the brain manifests once, so a long-lived enforcement point held whatever
lifecycle stage was current at construction; an agent demoted to `restricted` or
`retired` went on being authorized as `active`. The manifests are now re-read
when their (path, mtime, size) signature changes — on change rather than every
call, because re-parsing two TOML files per authorization is a cost on the hot
path for a fact that only changes when Joe edits a file.

**And the fix for that contained a fail-open, in the exact shape this record
exists to document.** Dropping the cache when a manifest becomes unreadable left
`_spec()` returning the roster alone, which carries no `status`. The gate read
`if stage in NON_EXECUTING_STAGES`, and **`None` is in no frozenset** — so an
unreadable manifest handed every agent unrestricted authority. Worse, the
comment I wrote for the reload *claimed* the call site already failed closed on
an absent status. It did not. The claim was asserting an intention.

It was caught because the test asserted the behaviour rather than the comment,
and it turned out to be a **pre-existing** fail-open as well: any roster agent
missing from the brain manifests could already mutate. The gate now names the one
stage that may execute (`active`) instead of enumerating those that may not —
the round-7 denylist inversion, in the lifecycle dimension.

**Two mutants survived the first pass** and produced the four probes that kill
them. `transfer_and_get_receipt` separates "the leading token is a read verb"
from "a read verb appears anywhere"; `read_invoice_and_publish_it` separates
*all* mapped tokens being noun-capable from *any* being so. Without those
shapes, both weakenings passed a 78-probe suite.

**The DeepEval telemetry lock ran after the import it was protecting.**
`coverage_report()` calls `deepeval_available()`, whose probe *is*
`import deepeval`, and `execute()` called `assert_telemetry_disabled()` only
after the report was built. Any hosted-logging client the SDK constructs from
environment or persisted login state at import time was therefore constructed
while telemetry was still enabled: the later check could refuse the run, but the
boundary it exists to establish had already been crossed. The lock is now the
first statement of the importing function, and the call in `execute()` is kept
because an idempotent refusal in two places costs nothing while a single call in
the wrong place cost the whole boundary.

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
  contract decision. The enforcement point now reconciles it at the boundary
  rather than suppressing the error, so no check is skipped — but the underlying
  disagreement between `schemas/writer_lease.schema.json` and
  `runtime/writer_lease.py` is still there, and `scripts/memory_layer.py` would
  still reject a real registry lease. One of the two has to move.
- **Pre-commit hooks are pinned to mutable tags** while Actions are pinned to
  SHAs. Resolving the four `rev` values needs network verification and a wrong
  SHA breaks every contributor's local gate, so it is a deliberate step rather
  than a mechanical one.
- **The filesystem mount's npm package has no committed lock** and is outside
  the vulnerability scan. Its top-level version is pinned; its transitive set is
  not. Distinct from the relay connector's lock, which was committed but
  unscanned and is now covered — this one has nothing to scan, so closing it
  means generating and committing a lock for a mount, which is a connector
  decision rather than a hygiene edit.
- **Four npm advisories in the relay tree need an upstream move or a
  downgrade.** Three are pinned by `@earendil-works/pi-coding-agent`'s published
  `npm-shrinkwrap.json`, which `overrides` cannot penetrate; one is outside the
  range `@modelcontextprotocol/sdk` declares. The only remedy available today is
  `npm audit fix`'s: **downgrade `agent-relay` 11.2.0 → 10.6.7**, a semver-major
  move of a declared dependency, which is a connector decision. Triaged for one
  month; if nothing upstream moves by then, the downgrade is the question.
- **Dispatcher verbs are not bound to the delegation's `allowed_actions`.** The
  gate now refuses an action that is in the packet's six-value collaboration
  vocabulary and was withheld, but `list`, `read_record` and every other
  dispatcher verb sit outside that enum and are governed only by the namespace
  and target bindings. Closing it needs either a dispatcher-verb mapping in the
  packet contract or a widened enum — a change to `schemas/`, which this branch
  deliberately does not touch. Same family as the operation-from-tool-metadata
  item already on this list.
- **Idempotency keys and expected versions are checked for presence, not
  honoured.** The gate now refuses a mutation that omits a control its packet
  demands, but nothing verifies the executor performs a compare-and-set or that
  a key was not already applied. That needs a ledger of consumed keys at the
  execution boundary — the same missing mechanism as instruction-grant nonce
  consumption, and it lands with it or not at all.
- **`scripts/trusted_launcher.py` forwards the whole inherited environment** to
  every mounted process, so unrelated credentials reach mounts that do not need
  them. The fix is a per-mount `env` allowlist in `config/mcp_mounts.toml` plus
  a small baseline — a connector-policy change, which is Joe's decision rather
  than a mechanical edit.
