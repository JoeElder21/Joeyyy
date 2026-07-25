# Awesome Copilot — installed customizations

This repository vendors a curated subset of [github/awesome-copilot](https://github.com/github/awesome-copilot),
a community collection of GitHub Copilot agents, instructions, and skills.

- **Source:** `https://github.com/github/awesome-copilot`
- **Pinned at commit:** `aa280f28b1b73f9b6e6917b607eb92127b67b419`
- **Upstream license:** MIT (see the upstream `LICENSE`)

Files are copied in verbatim so Copilot picks them up from the standard locations. Nothing here
changes runtime behaviour of Agent 007 — these are editor/agent-side authoring aids only.

## Instructions — `.github/instructions/`

Applied automatically to matching files via each file's `applyTo` glob.

| File | Applies to | Why it's here |
| --- | --- | --- |
| `agent-safety.instructions.md` | `**` | Safety, policy enforcement, and auditability for multi-agent orchestration — the core concern of this repo. |
| `agents.instructions.md` | `**/*.agent.md` | Conventions for authoring custom agent definitions. |
| `agent-skills.instructions.md` | `**/skills/**/SKILL.md` | Conventions for authoring portable Agent Skills. |
| `github-actions-ci-cd-best-practices.instructions.md` | `.github/workflows/*.y[a]ml` | Hardening guidance for `validate-agent.yml` and future workflows. |
| `markdown.instructions.md` | `**/*.md` | CommonMark 0.31.2 formatting — this repo is markdown-heavy (contracts, plans, registries). |
| `security-and-owasp.instructions.md` | `**` | Secure-coding standards including AI/LLM-specific guidance. |
| `self-explanatory-code-commenting.instructions.md` | `**` | Keeps generated Python comments purposeful rather than redundant. |
| `code-review-generic.instructions.md` | `**` | Baseline review checklist; excluded from the Copilot coding agent by its own front matter. |

## Agents — `.github/agents/`

| File | What it does |
| --- | --- |
| `meta-agentic-project-scaffold.agent.md` | Discovery agent: finds and pulls further awesome-copilot assets into the right folders. Pins `model: GPT-4.1` upstream. |
| `prompt-engineer.agent.md` | Treats every input as a prompt to analyse and rewrite. |
| `task-planner.agent.md` | Produces actionable implementation plans into `.copilot-tracking/`. Initially held out because it declares `terraform` and `azure_get_schema_for_Bicep` tools this repo had no home for; both are now registered mounts, so it is installed. See `docs/TERRAFORM_AZURE_MCP_BUILDOUT.md`, including the remaining `Microsoft Docs` gap. |

## Skills — `.github/skills/`

The three upstream discovery skills, so the collection can be re-queried from inside a Copilot session
instead of hand-copying files:

- `suggest-awesome-github-copilot-instructions/`
- `suggest-awesome-github-copilot-agents/`
- `suggest-awesome-github-copilot-skills/`

Each compares what is already in this repo against upstream, flags drift, and suggests additions.
They need a `#fetch`-capable tool to reach raw.githubusercontent.com.

## Selection report

`scripts/build_awesome_copilot_report.py` generates a 5-page PDF covering the full
upstream inventory considered (190 instructions / 221 agents / 391 skills), the measured
repository profile the selection was made against, every adopted file with its rationale,
the excluded groups and why, the privacy-guard interaction, and the verification gates.

```bash
pip install reportlab
python scripts/build_awesome_copilot_report.py   # -> docs/reports/ (gitignored)
```

The PDF is not tracked: `scripts/privacy_guard.py` rejects non-source artifact types and
non-UTF-8 files in this public tree. The generator is the source of truth.

## Updating

Re-run the discovery skills, or refresh a single file directly:

```bash
curl -fsSL -o .github/instructions/markdown.instructions.md \
  https://raw.githubusercontent.com/github/awesome-copilot/main/instructions/markdown.instructions.md
```

Bump the pinned commit above whenever you refresh.

## Alternative: the plugin marketplace

Awesome Copilot is a default plugin marketplace in Copilot CLI and VS Code, which installs into your
personal Copilot config rather than into this repository:

```bash
copilot plugin install awesome-copilot@awesome-copilot
```

Register the marketplace first if your client reports it as unknown:

```bash
copilot plugin marketplace add github/awesome-copilot
```

The `awesome-copilot` plugin also bundles an MCP server that requires Docker. That route was not used
here because the vendored files need to be visible to every collaborator and to the Copilot coding
agent, not just to one developer's client.

## Interaction with the privacy guard

`scripts/privacy_guard.py` scans every tracked text file for secret-like patterns. Two of the
vendored instruction files are secure-coding guides, so they legitimately contain illustrative
credential handling and placeholder addresses. Installing them required two narrow adjustments:

1. **Two low-confidence heuristics** — `credential assignment` and `email address` — are skipped for
   files under `.github/instructions/` only. These fire on any assignment whose left-hand side is a
   credential-like name, which is unavoidable in OWASP documentation showing the *correct* way to read
   a secret. Every high-confidence check (real-looking secret tokens, cloud
   access keys, private key blocks, phone numbers, street addresses, Drive links) remains fully
   enforced in that directory.
2. **Two placeholder API keys** that do trip the high-confidence secret-token pattern are pinned as
   exact literals in `PLACEHOLDER_LITERALS`, one literal to one file. A real credential in the same
   file still fails the scan.

Both live in `scripts/privacy_guard.py`; `tests/test_privacy.py` imports them so the guard and the
test cannot drift apart. If you drop the vendored security instructions, revert both adjustments.

## Provenance note

Upstream content is authored by third-party contributors. Review any file before relying on it —
particularly the agents, which declare broad tool permissions.
