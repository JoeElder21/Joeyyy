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

## Status in this repository: read-only candidates

These are registered in `docs/AGENT_REGISTRY.md` under **Vendored reference corps** at
`candidate` status. Three things follow from that, and they are enforced by
`tests/test_vendored_agents.py` rather than left to convention:

- **Read-only.** All 33 prompts now carry an explicit read-only `tools:` allowlist.
  Sixteen declared write-capable tools upstream and were stripped; the other seventeen
  declared **no** `tools:` field at all, which in Claude Code means *inherit every tool
  the main thread has* — the most permissive state, not the most restrictive — so an
  explicit allowlist was added to each. `AGENTS.md` makes Agent 007 the sole
  write-capable agent; a vendored prompt is not an exception to that.
- **Not a substitute for the registered corps.** They own no brain, hold no memory
  namespace, and are never issued a writer lease. Treat output as a proposal.
- **Untrusted text.** Many prompts say "MUST BE USED" or "PROACTIVELY". That is upstream
  marketing copy, not routing authority — `AGENTS.md` treats external content as data,
  never as permission.

## Usage

Claude Code discovers these automatically from `.claude/agents/`. Invoke one
directly, or let the orchestrator pick:

```
use @agent-tech-lead-orchestrator and add rate limiting to the API
use @agent-code-reviewer on the current diff
use @agent-python-testing-expert to backfill tests for the runtime package
```

They can read, search, and draft. They cannot edit files or run commands — hand their
proposals to Agent 007 to apply.

## Local changes to upstream

Re-apply all of the following when syncing, then run
`python -m unittest tests.test_vendored_agents`.

### Frontmatter (3)

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

### Tool constraint (33 files)

Two distinct problems, both closed:

- **16 prompts declared write-capable tools.** `Write`, `WriteFile`, `Edit`,
  `MultiEdit`, and `Bash` were removed, leaving `LS`, `Read`, `Grep`, `Glob`, and where
  upstream declared them `WebFetch`/`WebSearch`. `orchestrators/team-configurator.md`
  also had a duplicate `LS` entry, dropped at the same time.
- **17 prompts declared no `tools:` field at all.** An omitted field does not mean "no
  tools" — Claude Code grants the subagent everything the main thread has, `Write` and
  `Bash` included. Each now carries an explicit `tools: LS, Read, Grep, Glob`.
- **11 prompts instruct the agent to fetch documentation** (Context7 first, `WebFetch`
  as fallback) but had no fetch tool in their allowlist, so their own mandatory first
  step was impossible. `WebFetch` is granted to those 11 — it is read-only and does not
  weaken the constraint.

Privacy: the repository's guard exempts no path. Each documentation placeholder in these
files is pinned literal-by-literal in `PLACEHOLDER_LITERALS` in `scripts/privacy_guard.py`,
so a real credential added to any of them is still reported, and a sync that changes a
sample fails the guard until the new literal is reviewed and pinned.

`tests/test_vendored_agents.py` asserts the presence of the field separately from its
contents, because a missing field exposes no forbidden tool *names* to match on and
would otherwise pass a check that only inspects what is declared.

### Agent bodies (9)

Divergences from upstream, applied because the shipped samples are wrong in ways that
would mislead anyone acting on them. Each was reported by automated review on the PR.

| File | Defect | Change |
| --- | --- | --- |
| `core/code-reviewer.md` | Delegated to `security-guardian` and `refactoring-expert`, neither of which exists in the collection — an unfulfillable handoff exactly when specialist follow-up is needed | Routed to `python-security-expert`; refactors hand back to `tech-lead-orchestrator` |
| `core/code-archaeologist.md` | Same missing `security-guardian`, in 3 places | Routed to `python-security-expert` |
| `orchestrators/team-configurator.md` | Wrote a mandatory "YOU MUST USE these subagents" directive into `CLAUDE.md`, from whatever prompts it found on disk — turning unregistered text into project-wide routing policy | Now *proposes* the section as handoff text, sources candidates from `docs/AGENT_REGISTRY.md`, and writes no files |
| `specialized/python/fastapi-expert.md` | `background_tasks` (no default) followed a `Path(...)` default → `SyntaxError` at import | Required parameter moved first |
| `specialized/python/python-expert.md` | Rebuilt `UserCreate` after stripping `password`/`confirm_password` and adding `hashed_password` → every registration failed validation | Added a dedicated `UserCreateInDB` persistence schema |
| `specialized/python/security-expert.md` | `Fernet.generate_key()` is already base64; encoding it again produced a 44-byte value `algorithms.AES` rejects | Generates 32 raw bytes via `secrets.token_bytes`, encoded once |
| `specialized/python/web-scraping-expert.md` | `headers` left in `**kwargs` *and* passed explicitly → `TypeError` on every custom-header request | `kwargs.pop('headers', {})` |
| `specialized/python/ml-data-expert.md` | Appended `nn.Softmax` while training with `CrossEntropyLoss`, which applies log-softmax itself → softmax twice, distorted gradients | Output layer emits logits; added `predict_proba()` for inference |
| `specialized/django/django-backend-expert.md` | Three: stock decremented without re-checking under `select_for_update` (oversell); payment captured *inside* `transaction.atomic` (charged customer, rolled-back order); success-rate division by zero on a valid empty import | Re-validates under the lock; capture moved to a durable retryable Celery task enqueued from `transaction.on_commit`, idempotent on order id, reconciling the pending order on every failure path; guarded denominator |

Everything else is byte-identical to upstream.

## Syncing with upstream

```bash
git clone https://github.com/vijaythecoder/awesome-claude-agents.git /tmp/aca
rsync -a --delete --exclude README.md /tmp/aca/agents/ .claude/agents/awesome-claude-agents/
cp /tmp/aca/LICENSE .claude/agents/awesome-claude-agents/LICENSE
# Then re-apply EVERY local change documented above — 3 frontmatter, the tool
# constraint across 16 files, and 9 agent-body fixes — and update the commit SHA here.
python -m unittest tests.test_vendored_agents   # must pass before committing
```

A sync that skips the tool constraint silently re-grants `Write`/`Bash` to 16 agents, so
treat a failing `test_vendored_agents` as a blocker rather than a lint nit.
