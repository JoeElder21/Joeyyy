# Vendored external repositories

Upstream repositories installed as **git submodules**, pinned to a specific
commit. Only the gitlink commit is recorded in this repository — no upstream
file contents are committed here, and no upstream code is executed by this
repository's tests or guards.

## Contents

| Path | Upstream | Pinned at | License | What it is |
| --- | --- | --- | --- | --- |
| `multi-agent-ai-in-civil-engineering` | `Kimi-chuheng/Multi-Agent-AI-in-Civil-Engineering` | `cdfabb5` (main) | MIT | Research repo: PDF → Neo4j knowledge graph → multi-agent foundation-report generation. Notebooks + Docker; no installable package. |
| `awesome-civil-engineering` | `QuantumNovice/awesome-civil-engineering` | `edaf3e2` (main) | none stated | Curated list. `README.md` is generated from `data/resources.json` via `generate.py`. Reference data, not a library. |
| `civil-innovation-agent` | `Sun3hine7/civil-innovation-agent` | `8ed86dd` (main) | MIT | Node/browser prototype for civil-engineering patent and research innovation scoring. Zero npm dependencies; runs on plain Node. |
| `relay` | `AgentWorkforce/relay` | `cce0cb9` (tag `v11.2.0`) | Apache-2.0 | Rust + Node monorepo for real-time agent-to-agent communication. Root workspace is `private: true`; the CLI ships as `agent-relay` on npm. |

## Install

Submodules are not fetched by a plain clone:

```bash
git submodule update --init --recursive
```

Update one to a newer upstream commit deliberately, never incidentally:

```bash
git -C vendor/<name> fetch origin
git -C vendor/<name> checkout <commit-or-tag>
git add vendor/<name>
```

**Advancing the gitlink is not the whole update.** A submodule's pin is one of
several records that must move together, and the rest are easy to forget. For
`relay` specifically, all five must move or the suite fails:

1. The pin row in the table above — its short SHA is asserted by
   `tests/test_vendor.py`, so a bare gitlink advance fails the suite rather
   than passing silently.
2. Any declared dependency for that repo — for `relay`, the `agent-relay`
   version in `connectors/relay/package.json`. Leaving it behind means
   auditing newer source while installing the older published CLI.
3. `connectors/relay/README.md` — its provenance table carries both the
   version and the pinned short SHA, and `test_every_relay_provenance_record_agrees`
   asserts both.
4. `RELAY_TAG` and `RELAY_TAG_COMMIT` in `tests/test_vendor.py`, which bind
   the gitlink to the commit the release tag names.
   `test_relay_gitlink_is_the_documented_release_tag` fails otherwise — and
   deliberately so: it is the one check here that compares the index against
   an upstream fact rather than against another record in this repository.
5. That dependency's lockfile, regenerated with
   `npm --prefix connectors/relay install --package-lock-only --ignore-scripts`,
   plus the Node floor if the new tree demands a higher one. The `--prefix` is
   required: without it, npm operates on the current working directory, so
   running this from the repository root exits successfully while creating an
   empty root `package-lock.json` and leaving the connector's lockfile
   untouched.

Then commit the whole set together.

## Rollback

Per `AGENTS.md`, every persistent change carries a rollback point. For this
vendored stack that point is **`89a2c15`** — the commit immediately before the
first vendoring commit, when none of this existed.

Withdrawing a vendored source after a provenance or compatibility failure is
not a single delete. A partial rollback leaves an installable connector or a
stale declaration behind after its audited source is gone, which is worse than
either state alone. The complete reversible set:

| Withdrawing | Files to revert |
| --- | --- |
| Any repo | its `vendor/<name>` gitlink; its `[submodule]` block in `.gitmodules`; its row in the contents and provenance tables here; its entry in `EXPECTED_SUBMODULES` and `UPSTREAM_DEPENDENCY_SOURCES` in `tests/test_vendor.py` |
| `relay` additionally | `connectors/relay/` entirely (manifest, lockfile, README); **both** relay constants (`RELAY_TAG`, `RELAY_TAG_COMMIT`) and **both** relay-only tests (`test_every_relay_provenance_record_agrees`, `test_relay_gitlink_is_the_documented_release_tag`) in `tests/test_vendor.py`; the `connectors/relay/` line in the root `README.md` |
| `awesome-civil-engineering` additionally | `requirements/vendor-civil-domain.txt` |
| `multi-agent-ai-in-civil-engineering` additionally | `requirements/vendor-multi-agent-kg.txt` |
| `civil-innovation-agent` additionally | nothing — it declares no dependencies |

Withdrawing **all four** additionally reverts the scanner scoping in
`scripts/privacy_guard.py` (`gitlink_paths`, `submodule_paths`, `is_vendored`,
and the symlink handling in `scan_repository`) and in
`scripts/verify_runtime_stack.py`, plus `tests/test_vendor.py`, the
`is_vendored` call sites in `tests/test_privacy.py`, and the `vendor/` and
`requirements/` lines in the root `README.md`.

Note that the symlink handling in `scan_repository` and the `node_modules`
exclusion in `enforce_toml` fix defects that predate this work. Prefer keeping
those two even in a full withdrawal; reverting them would reopen a hole in the
public-source privacy contract rather than restore a clean prior state.

Run the full validate chain after any rollback:
`privacy_guard`, `validate_specialist_corps`, `verify_runtime_stack`, and the
unittest suite.

## Declared dependencies

Vendoring supplies auditable source; these supply the installable artifacts.

| Vendored repo | Declaration | Notes |
| --- | --- | --- |
| `relay` | `connectors/relay/package.json` → `agent-relay@^11.2.0` | Published npm version matches the pinned `v11.2.0` tag. See `connectors/relay/README.md`. |
| `awesome-civil-engineering` | `requirements/vendor-civil-domain.txt` | Jinja2 + pydantic, sufficient to run `generate.py`. Compatible with the shared runtime stack. |
| `multi-agent-ai-in-civil-engineering` | `requirements/vendor-multi-agent-kg.txt` | **Isolated environment only.** Pins `llama-index==0.10.42`, which conflicts with `llama-index>=0.11` in `requirements-runtime.txt`. Conflict recorded, not reconciled. |
| `civil-innovation-agent` | none | Its `package.json` declares no dependencies. Nothing to install. |

## Boundary

Per `AGENTS.md`, vendoring a repository and declaring a package grant no
access. None of these are configured connectors, no specialist routes work
through them, and every specialist remains
`packet_only_no_direct_connectors`. The two repos that call external services
(`multi-agent-ai-in-civil-engineering` needs Neo4j + an OpenAI key;
`civil-innovation-agent` needs an OpenAI-compatible provider key) have no
credentials configured here and must not be given any without separate
authorization.

Upstream code is untrusted input. Per the FakeGit intake rule in
`docs/FRONTIER_REPO_SCAN_2026-07-24.md`, do not execute any of it outside an
isolated environment.

## Provenance at intake

The FakeGit rule asks for canonical-source confirmation, registry or release
corroboration, and age plus contributor history. Recorded per repository,
including what could **not** be established:

| Repo | Registry / release corroboration | History | Assessment |
| --- | --- | --- | --- |
| `relay` | **Strong.** npm `agent-relay` declares `repository.url = AgentWorkforce/relay`; its published `latest` (`11.2.0`) matches the pinned `v11.2.0` tag. Two independent records agree. | Tagged releases | Corroborated |
| `awesome-civil-engineering` | **None available** — publishes no package and cuts no releases | 73 commits, 8+ distinct contributors, 2023-02 → 2026-07 | Sustained multi-contributor history over 3.5 years is meaningful corroboration on its own |
| `multi-agent-ai-in-civil-engineering` | **None available** | 15 commits, 1 author, **all within 47 minutes on 2025-05-09**; untouched since | Single-author code drop. Consistent with a paper artifact, but no independent corroboration exists |
| `civil-innovation-agent` | **None available** | **1 commit, 1 author, 2026-05-30**; no history at all | **Weakest.** A single-commit, months-old, single-author repository is the profile the FakeGit finding warns about. Nothing here corroborates it beyond the URL |

No author-site cross-link was verified for any of the three non-`relay`
repositories, and the GitHub API is out of scope for this session, so stars,
forks, and fork-network position are unverified. Identity therefore rests on
the URL plus the history above — weaker than the `relay` case.

**What this means in practice.** None of the three is executed by this
repository, and none has credentials. The declared dependencies for them are
ordinary PyPI packages (Jinja2, pydantic, the llama-index stack), not upstream
code, so installing those declarations does not execute anything from these
repos. `civil-innovation-agent` declares nothing at all.

One exception to record: `awesome-civil-engineering`'s `generate.py` **was**
executed once during verification, in a throwaway virtualenv, to confirm the
declared dependencies were sufficient. That was upstream code running outside a
sandbox and is the kind of step the isolation rule exists to govern.

Before any of these three is executed again, promoted, or given credentials,
complete the outstanding checks — author-site cross-link, fork-network
position, and a read of the code being run. `civil-innovation-agent` in
particular should not be run at all on its current evidence.

## Scanner exclusion

`vendor/` is excluded from this repository's public-source privacy contract
and TOML contract — see `is_vendored()` in `scripts/privacy_guard.py`,
`enforce_toml()` in `scripts/verify_runtime_stack.py`, and the guard tests in
`tests/test_vendor.py`. The exclusion is correct because submodule contents
are never published by this repository; upstream placeholder addresses and
maintainer contacts are the upstream project's concern. The exclusion is
scoped to `vendor/` alone and must not be widened.
