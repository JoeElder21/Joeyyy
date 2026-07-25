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
git add vendor/<name> && git commit
```

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
isolated environment. Provenance at intake: all four remotes were resolved and
cloned directly from their canonical URLs; `relay`'s identity is additionally
corroborated by npm registry linkage (`agent-relay` declares
`repository.url = AgentWorkforce/relay`) and by its published `latest` version
matching the pinned tag.

## Scanner exclusion

`vendor/` is excluded from this repository's public-source privacy contract
and TOML contract — see `is_vendored()` in `scripts/privacy_guard.py`,
`enforce_toml()` in `scripts/verify_runtime_stack.py`, and the guard tests in
`tests/test_vendor.py`. The exclusion is correct because submodule contents
are never published by this repository; upstream placeholder addresses and
maintainer contacts are the upstream project's concern. The exclusion is
scoped to `vendor/` alone and must not be widened.
