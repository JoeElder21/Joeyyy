# awesome-claude-agents (vendored)

A vendored copy of the [awesome-claude-agents](https://github.com/vijaythecoder/awesome-claude-agents)
sub-agent collection, checked in so every clone of this repository picks the
agents up automatically — no per-machine setup step.

- **Source:** https://github.com/vijaythecoder/awesome-claude-agents
- **Upstream commit:** `2050f3c60fcfea497f7b6b3ec6566cc316367a7e` (2025-10-29)
- **License:** MIT — see `LICENSE` in this directory
- **Agents:** 33

## Layout

| Directory | Contents |
| --- | --- |
| `core/` | Language-agnostic reviewers and analyzers (code review, performance, docs, code archaeology) |
| `orchestrators/` | Routing agents that delegate to the specialists (`tech-lead-orchestrator`, `project-analyst`, `team-configurator`) |
| `specialized/` | Framework experts — `python/`, `django/`, `rails/`, `laravel/`, `react/`, `vue/` |
| `universal/` | Stack-neutral builders (`api-architect`, `backend-developer`, `frontend-developer`, `tailwind-frontend-expert`) |

Because this repository is Python, the agents under `specialized/python/`,
`specialized/django/`, `core/`, and `universal/` are the ones that will
actually fire. The Rails, Laravel, React, and Vue agents are kept so the set
matches upstream and so `tech-lead-orchestrator` can route without hitting
missing references; they will simply never match a Python task.

## Usage

Claude Code discovers these automatically from `.claude/agents/`. Invoke one
directly, or let the orchestrator pick:

```
use @agent-tech-lead-orchestrator and add rate limiting to the API
use @agent-code-reviewer on the current diff
use @agent-python-testing-expert to backfill tests for the runtime package
```

## Local changes to upstream

Three upstream frontmatter bugs are patched here. Re-apply them when syncing.

1. **`specialized/vue/vue-state-manager.md`** declared `name: vue-component-architect`,
   a copy-paste duplicate of its sibling. Two agents sharing one name means one
   silently shadows the other. Corrected to `name: vue-state-manager`.

2. **Five `specialized/python/` agents** used prose display names with spaces and
   slashes (`Python Security Expert`, `Python DevOps/CI-CD Expert`, …). Agent
   names are slugs used to build the `@agent-<name>` handle, so these were not
   addressable. Renamed to kebab-case:

   | File | Was | Now |
   | --- | --- | --- |
   | `security-expert.md` | `Python Security Expert` | `python-security-expert` |
   | `web-scraping-expert.md` | `Python Web Scraping Expert` | `python-web-scraping-expert` |
   | `devops-cicd-expert.md` | `Python DevOps/CI-CD Expert` | `python-devops-cicd-expert` |
   | `testing-expert.md` | `Python Testing Expert` | `python-testing-expert` |
   | `performance-expert.md` | `Python Performance Expert` | `python-performance-expert` |

3. **`universal/frontend-developer.md`** had a malformed frontmatter block: a
   blank line immediately after the opening `---`, and a 56-character dash rule
   (`-----…`) where the closing `---` delimiter belonged. The block did not parse,
   so the agent never registered. Normalized to a well-formed `---` … `---` block.

Only frontmatter was touched — the `name:` field in fixes 1 and 2, the block
delimiters in fix 3. Agent bodies, descriptions, and tool lists are unmodified.

## Syncing with upstream

```bash
git clone https://github.com/vijaythecoder/awesome-claude-agents.git /tmp/aca
rsync -a --delete --exclude README.md /tmp/aca/agents/ .claude/agents/awesome-claude-agents/
cp /tmp/aca/LICENSE .claude/agents/awesome-claude-agents/LICENSE
# then re-apply the two fixes above and update the commit SHA in this file
```
