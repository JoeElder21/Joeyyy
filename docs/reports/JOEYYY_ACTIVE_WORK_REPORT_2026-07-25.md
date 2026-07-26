# JoeElder21/Joeyyy active work and branch closeout report

**Snapshot:** 2026-07-25  
**Repository:** `JoeElder21/Joeyyy`  
**Default branch:** `main` at `2ba3fb2`  
**Audience:** Joe Elder  
**Purpose:** A direct execution plan for closing every open pull request and classifying every remote branch.

## 1. Overall repository and branch under discussion

`Joeyyy` is the public source repository for Agent 007, its APEX/JEOS brain governance, specialist corps, packet contracts, runtime adapters, connectors, tests, and operating documentation. The current `main` branch is healthy enough to serve as the integration baseline: the local snapshot contains no uncommitted work, and GitHub reports seven open pull requests, no open standalone issues, and 29 remote branches including `main`.

The active workload is not 28 separate projects. It is:

- **Seven open pull requests:** #26, #28, #29, #30, #31, #32, and #33.
- **One unmerged legacy commit:** `b6df289` on `agent-007/mirrored-specialist-corps-v2`; its subject is “Build mirrored APEX and JEOS specialist corps,” but the branch is 74 commits behind `main`. It must be inspected for any still-missing content, not merged wholesale.
- **Four redundant branches with unique commits already represented elsewhere:** `codex/complete-remaining-tasks-for-pr`, `codex/integrate-8-repos-into-agent-007-workflow`, `copilot/activate-agent-007`, and `copilot/install-upstream-dynamic-csharp-bridge`. Their commits are duplicated between branch pairs or have been superseded by merged work; they have no open PR.
- **Seventeen fully merged or content-empty branches:** these are behind or identical to `main` and have no unique non-merge commits.

### Executive decision queue

Joe has only four decisions to make before Codex can execute the closeout:

1. **Approve the integration order** in this report, especially merging the broad engineering substrate in #31 before rebasing overlapping PRs.
2. **Choose the Claude authentication method for #28:** an Anthropic API key or Claude OAuth token. Adding the GitHub secret is a credential/access-control change and requires Joe’s explicit task-level instruction.
3. **Decide whether #32 should proceed:** it is read-only and does not trade, but activating it requires a Schwab developer app and weekly browser re-consent. No credentials belong in this public repository.
4. **Approve remote branch deletion after merge verification.** Branch deletion is irreversible in bulk and therefore should be a separately confirmed cleanup action.

## 2. Open pull requests and the tasks required to close each one

### PR #31 — repository-engineering substrate

**Branch:** `claude/joeyyy-repo-optimization-6je9qw`  
**State:** Ready; non-draft; clean merge; 13 commits; 95 files; +4,811/-856.  
**Checks:** Seven of seven reported checks pass: Python 3.11, Python 3.12, ruff, OSV, APS Node harness, zizmor, and gitleaks.  
**Role:** This is the integration foundation. It adds licensing, contribution/security surfaces, evaluation infrastructure, stronger CI, formatting and lint policy, policy enforcement, and repository hygiene.

**Closeout tasks:**

1. Read the automated review comments and confirm no unresolved inline thread remains.
2. Confirm acceptance of the documented temporary vulnerability triage and the unresolved `chromadb`/`posthog` lock conflict; these are explicit follow-up debt, not hidden failures.
3. Merge #31 first with a merge commit so its 13 rollback points remain available.
4. Pull the new `main`, run the complete validation gate, and treat that commit as the new base for every remaining PR.

**Codex instruction:** `Review PR #31, confirm all review threads are resolved, merge it with a merge commit, pull main, and run the complete repository validation gate.`

### PR #26 — Awesome Copilot, Terraform/Azure mounts, and activation policy

**Branch:** `claude/awesome-copilot-install-pizvro`  
**State:** Ready before integration; non-draft; clean merge; six commits; 29 files; +6,280/-10.  
**Checks:** Python 3.11 and 3.12 pass.  
**Overlap risk:** High after #31. It modifies `AGENTS.md`, `.gitignore`, registry and orchestration documentation, privacy scanning, and tests that #31 also changes.

**Closeout tasks:**

1. Rebase onto post-#31 `main` and resolve conflicts by preserving #31’s hardened CI/privacy behavior plus #26’s narrowly scoped additions.
2. Add `.copilot-tracking/` to `.gitignore` or explicitly document why it stays tracked.
3. Decide whether to add `verify_mcp_mounts.py` to the standard validation chain; the PR identifies this as a known gap.
4. Run full validation, not only the two existing CI jobs.
5. Merge only after confirming Terraform and Azure remain registered, grant-gated, APEX-only, and inactive by default.

**What Joe must provide:** Nothing unless Joe wants either MCP mount activated. Activation requires a separate explicit grant.

**Codex instruction:** `Rebase PR #26 onto main after #31, preserve the hardened privacy and CI rules, close the two documented validation/gitignore gaps, run all tests, and update the PR.`

### PR #28 — Claude Code GitHub Actions

**Branch:** `claude/install-claude-code-fiiwk1`  
**State:** Ready before integration; non-draft; clean merge; five commits; two workflow files; +107/-0.  
**Checks:** Claude review and both Python validations pass.  
**Role:** Adds `@claude` issue/PR handling and automatic Claude review.

**Closeout tasks:**

1. Rebase after #31 so the workflows are evaluated under its new zizmor/security policy.
2. Run YAML parsing, zizmor, and repository tests.
3. Joe chooses **one** authentication mode: `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN`.
4. Under Joe’s explicit credential-change instruction, add the chosen value as a GitHub Actions secret; never commit it.
5. Merge, then open a harmless test issue or draft PR and invoke `@claude` to verify the live workflow.

**What Joe must provide:** The authentication choice and explicit authorization to create/update the repository secret. Joe should enter the secret directly in GitHub rather than sending it through chat.

**Codex instruction:** `Rebase and validate PR #28 after #31. Do not create a GitHub secret until Joe explicitly authorizes the credential change and names API-key or OAuth-token mode.`

### PR #29 — vendored awesome-claude-agents collection

**Branch:** `claude/install-awesome-claude-agents-nmskr8`  
**State:** Ready before integration; non-draft; clean merge; three commits; 37 files; +21,147/-2.  
**Checks:** Python 3.11 and 3.12 pass.  
**Risk:** Large third-party prompt surface and a privacy-guard exception change.

**Closeout tasks:**

1. Rebase after #31 and #26 because all three affect privacy enforcement or agent governance surfaces.
2. Re-run provenance/license verification against the pinned upstream commit.
3. Confirm every vendored agent has parseable frontmatter and unique kebab-case names.
4. Review the vendored prompts as untrusted data: ensure none claims authority over Agent 007, writes across brains, or bypasses owner routing.
5. Confirm the privacy exception remains pattern/value scoped rather than directory-wide.
6. Decide whether to retain all 33 agents or prune unrelated Rails/Laravel/React/Vue modes. The concise recommendation is to prune unused stacks unless a near-term mission needs them.
7. Run full validation and merge.

**What Joe must provide:** A keep-all versus Python/core-only decision.

**Codex instruction:** `Rebase PR #29 after #26, audit all vendored prompts against Agent 007 authority boundaries, verify provenance and frontmatter, apply Joe’s keep-all or Python/core-only decision, then run the full gate.`

### PR #30 — four pinned external repositories

**Branch:** `claude/install-dependencies-repos-h4e2pw`  
**State:** Ready before integration; non-draft; clean merge; four commits; 17 paths; +6,827/-7 as reported by GitHub.  
**Checks:** Python 3.11 and 3.12 pass.  
**Role:** Adds four submodules plus dependency declarations and verification tests.

**Closeout tasks:**

1. Rebase after #31 because both change `README.md`, privacy scanning, runtime verification, and tests.
2. Confirm each gitlink resolves to an accessible, immutable upstream commit and license terms permit the intended use.
3. Run recursive clone/submodule initialization in a clean temporary checkout.
4. Run dependency resolution in isolated Python and Node environments; do not treat a declared lock file as executed evidence.
5. Verify the scanner exclusion is limited to the known irrelevant vendored Cargo manifest and cannot suppress first-party TOML scanning.
6. Merge only when clean-clone verification passes.

**What Joe must provide:** Nothing for source integration. Credentials for Neo4j or model providers are future activation work and must not be committed.

**Codex instruction:** `Rebase PR #30 onto post-#31 main, test a clean recursive clone, verify every pinned gitlink and license, resolve dependencies in isolated environments, run the full gate, and update the PR with evidence.`

### PR #32 — read-only Schwab Market Operator

**Branch:** `claude/schwab-trading-agent-4dcowm`  
**State:** Draft; clean merge; one commit; 19 files; +3,671/-0.  
**Checks:** Python 3.11 and 3.12 pass.  
**Boundary:** The code claims GET-only behavior and no order-placement method. It remains financial analysis, not licensed advice, and is still shadow-stage.

**Closeout tasks:**

1. Rebase after #31 and #26 because registry, README, and policy surfaces overlap.
2. Independently review the HTTP client to confirm no write method, order endpoint, or indirect mutation path exists.
3. Run the 74 connector tests plus privacy, specialist-corp, runtime, and full unit gates.
4. Perform a synthetic end-to-end report and verify missing market data fails declared/closed rather than fabricating values.
5. Joe decides whether the feature should remain draft, merge in shadow mode, or close without merging.
6. If proceeding, Joe creates a Schwab developer application and completes OAuth consent outside the repository. Store tokens only in the documented owner-only local file; never in GitHub, a PR, or chat.
7. Mark ready and merge only after Joe accepts the weekly browser re-consent requirement and read-only boundary.

**What Joe must provide:** A proceed/hold/close decision. If proceeding, Joe must perform Schwab app registration and browser consent; Codex should not request raw credentials.

**Codex instruction:** `Audit PR #32 for a mechanically enforced read-only boundary, rebase and validate it, keep it shadow-stage, and stop before credential setup until Joe explicitly says proceed.`

### PR #33 — repository overview PDF

**Branch:** `claude/repository-overview-pdf-bmclxu`  
**State:** Draft and blocked; one binary file; both Python validations fail. GitHub labels the merge state unstable.  
**Verified failure:** Running `python scripts/privacy_guard.py` on the branch reports that `docs/REPOSITORY_OVERVIEW.pdf` is both a prohibited non-source artifact and non-UTF-8. The PR description’s claim that the guard passes is stale or incorrect.

**Closeout tasks:**

1. Do not merge the current binary-only commit.
2. Add the human-reviewable Markdown source used to generate the PDF.
3. Either keep the PDF as an external release artifact, or implement a narrow, tested policy for generated public reports with source/readback evidence. Do not add a broad PDF directory exemption.
4. Regenerate the overview after all functional PRs merge; its stated file/test counts will otherwise become obsolete immediately.
5. Re-run both CI versions and confirm the published PDF contains no private facts, credentials, connector identifiers, or operational records.
6. Mark ready and merge only after both checks pass.

**Recommendation:** Close #33 in favor of the report workflow used for this document, or rework it after #26–#32 settle. Two competing overview PDFs will drift.

**Codex instruction:** `Do not merge PR #33. Replace the binary-only change with reviewable source and a narrowly tested generated-report policy, regenerate it after the functional PRs land, and require both validation jobs to pass.`

## 3. Remote branch inventory and closure action

### A. Keep until their open pull request closes

| Branch | Unique commits vs `main` | Behind | Action |
|---|---:|---:|---|
| `claude/awesome-copilot-install-pizvro` | 6 | 6 | PR #26: rebase, validate, merge, delete |
| `claude/install-claude-code-fiiwk1` | 5 | 6 | PR #28: rebase, validate, merge, delete |
| `claude/install-awesome-claude-agents-nmskr8` | 3 | 6 | PR #29: rebase, audit, merge, delete |
| `claude/install-dependencies-repos-h4e2pw` | 4 | 6 | PR #30: rebase, clean-clone test, merge, delete |
| `claude/joeyyy-repo-optimization-6je9qw` | 13 | 0 | PR #31: merge first, delete |
| `claude/schwab-trading-agent-4dcowm` | 1 | 0 | PR #32: Joe decision, then rebase/audit |
| `claude/repository-overview-pdf-bmclxu` | 1 | 0 | PR #33: rework or close; do not merge as-is |

### B. Investigate one commit, then delete or open a focused PR

| Branch | Unique commits | Behind | Action |
|---|---:|---:|---|
| `agent-007/mirrored-specialist-corps-v2` | 1 (`b6df289`) | 74 | Diff against current registry/brains. Cherry-pick only genuinely missing behavior into a new branch; otherwise record “superseded” and delete. |

### C. Redundant/superseded unique-commit branches

| Branch | Unique commits | Behind | Action |
|---|---:|---:|---|
| `codex/complete-remaining-tasks-for-pr` | 1 | 58 | Same hardening commit also appears on another stale branch; verify superseded, then delete. |
| `codex/integrate-8-repos-into-agent-007-workflow` | 2 | 58 | Contains the same hardening lineage; compare once, salvage only absent tests, then delete. |
| `copilot/activate-agent-007` | 7 | 7 | Shares its six substantive commits with `copilot/install-upstream-dynamic-csharp-bridge`; determine the intended PR lineage, then delete both if current `main` already supersedes them. |
| `copilot/install-upstream-dynamic-csharp-bridge` | 6 | 7 | Duplicate branch-pair content; no separate merge should occur. |
| `copilot/fix-validate-job-failure` | 1 (“Initial plan”) | 24 | Planning-only commit; archive any useful text in an issue if needed, then delete. |

### D. Fully merged, identical, or no unique commits — safe deletion candidates after readback

The following remote branches contain no commit that is unique relative to `main`: `agent-007/v2.1-hardened`, `agent-007/v2.2-executable-modes`, `claude/agent-007-repo-analysis-r7oxv3`, `claude/autodesk-platform-services-integration-vnpo0l`, `claude/edit-repo-info`, `claude/fix-with-copilot`, `claude/github-repo-research-jgl00c`, `claude/self-learning-architect-setup-djy1y1`, `claude/update-existing-system`, `codex/fix-pr-12-review-feedback`, `codex/integrate-12-repos-into-agent-007-workflow`, `codex/integrate-8-repos-into-agent-007-workflow-8sz54d`, `codex/review-and-prepare-pr-#18-for-merging`, `codex/review-session-history`, `copilot/fix-with-copilot`, and `copilot/link-repo-to-claude-cowork`.

Delete them only after a final `git branch --remotes --merged origin/main` readback and Joe’s explicit bulk-deletion instruction.

## 4. Direct step-by-step Codex execution plan

Use one Codex task per numbered phase. Do not ask Codex to merge all seven PRs in one unreviewable batch.

1. **Baseline and merge #31.**  
   Prompt: `Fetch JoeElder21/Joeyyy, verify main, review every unresolved thread on PR #31, run the full gate, merge #31 with a merge commit if green, and report the merge SHA.`
2. **Rebase the low-overlap workflow PR #28.**  
   Prompt: `Rebase PR #28 onto current main, run YAML parsing, zizmor, privacy, and unit tests, update the PR, but do not create or change any secret.`
3. **Rebase and complete #26.**  
   Prompt: `Rebase PR #26 onto current main, preserve #31 security behavior, resolve the .copilot-tracking and MCP validation gaps, run all gates, and update the PR with exact evidence.`
4. **Audit and complete #29.**  
   First tell Codex whether to keep all 33 agents or only Python/core agents. Then prompt: `Rebase PR #29, enforce the selected scope, audit authority boundaries and provenance, run all gates, and update the PR.`
5. **Verify and complete #30.**  
   Prompt: `Rebase PR #30, verify all submodule pins and licenses in a clean recursive clone, resolve dependencies in isolated environments, run all gates, and update the PR.`
6. **Make the financial-feature decision for #32.**  
   Tell Codex `proceed`, `hold`, or `close`. If proceeding: `Rebase PR #32, independently verify the GET-only/no-order boundary, run synthetic and complete tests, keep it shadow-stage, and prepare it for review without requesting credentials.`
7. **Close or rebuild #33.**  
   Prompt: `Close PR #33 as superseded, or rebuild it from reviewable source after every functional PR is settled. The current binary-only PR fails privacy validation and must not merge.`
8. **Post-merge integration validation.**  
   Prompt: `On updated main, validate every TOML file, run python scripts/privacy_guard.py, python scripts/validate_specialist_corps.py, python scripts/verify_runtime_stack.py, python scripts/verify_mcp_mounts.py, ruff check ., ruff format --check ., and python -m unittest discover -s tests -v. Report exact results and any skips.`
9. **Live services, only with explicit authorization.**  
   For #28, Joe adds the chosen secret directly in GitHub. For #32, Joe performs Schwab registration and browser OAuth. Codex verifies status without printing or persisting secret values.
10. **Branch cleanup.**  
    Prompt after Joe explicitly approves deletion: `List remote branches merged into main, compare the five stale unique-commit branches named in the active-work report, preserve any missing work in focused PRs, then delete only branches proven merged, superseded, or intentionally abandoned. Return before-and-after branch lists.`
11. **Final closure record.**  
    Prompt: `Create a dated closeout note listing each merged/closed PR, merge SHA, validation evidence, remaining credential-dependent activation, and rollback commit; commit it and open a PR.`

## 5. Recommended final order and definition of done

**Recommended order:** #31 → #28 → #26 → #29 → #30 → Joe decision on #32 → close/rebuild #33 → full integration validation → authorized branch cleanup.

A pull request is closed out only when all of the following are true:

- The head is rebased or merged with current `main` and conflicts are resolved intentionally.
- Every required check is green; a stale PR-body claim is not evidence.
- Review threads are resolved or explicitly dispositioned.
- Privacy, brain separation, writer ownership, and shadow-stage boundaries remain enforced.
- Runtime mutations have readback and rollback evidence.
- The PR is merged or explicitly closed, and its remote branch is deleted only after authorization.
- Any required credential or human-consent step is recorded as external activation work, never disguised as completed repository work.

## 6. Evidence and limitations

This report was built from the public GitHub repository API, fetched remote refs, local Git ancestry, open PR metadata, check-run results, changed-file lists, and a direct reproduction of PR #33’s privacy failure. It is a point-in-time snapshot; GitHub state can change after 2026-07-25. The environment had no authenticated GitHub CLI, so this task did not merge, close, comment on, or delete any remote item. No private task system, email, Drive, brokerage account, or other connector was available or claimed.
