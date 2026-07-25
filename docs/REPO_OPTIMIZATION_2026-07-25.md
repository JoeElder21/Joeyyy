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

### Tier 3 — Reference, no action

| Repository / project | Verification | Note |
| --- | --- | --- |
| `astral-sh/ruff` | Verified (in use) | Already adopted in this change. The formatter is deliberately *not* enabled — it would reformat 45 of 54 files and make this diff unreviewable. Enable separately as a single mechanical commit if wanted. |
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

### What remains open after this round

Not a decision backlog — the actual work the harness exposed:

- **36 of 39 material modes have no evaluation case**, and none can leave
  `shadow` until they do. This is now the top of the queue and it is measurable.
- **Specialist dispatch is unwired** (`_invoke_specialist` raises). Connecting it
  needs a verified model credential and a connector-isolation decision that is a
  separate, deliberate step.
- **Confident AI cloud logging must be disabled** before any real mission is
  evaluated. This is the one setting that turns an approved tool into an
  unapproved disclosure.
