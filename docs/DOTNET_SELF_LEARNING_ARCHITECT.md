# .NET Self-Learning Architect — Install Record (2026-07-25)

Joe supplied two repositories and one custom-agent definition for installation. This documents what was installed, where it came from, and how to use it.

## 1. Custom agent: `.github/agents/dotnet-self-learning-architect.agent.md`

- **Source:** [github/awesome-copilot](https://github.com/github/awesome-copilot) — `agents/dotnet-self-learning-architect.agent.md`, installed verbatim per that repository's documented install method for custom agents ("download the `*.agent.md` file and add it to your repository").
- **What it is:** A principal-level .NET architect agent for GitHub Copilot (VS Code chat / Copilot coding agent). It designs .NET systems, chooses between parallel-subagent and orchestrated-team execution, and enforces a self-learning contract on itself and every subagent it spawns.
- **Self-learning storage:** The agent writes governed learning artifacts to:
  - `.github/Lessons/` — one file per mistake/correction (root cause, fix, prevention).
  - `.github/Memories/` — one file per durable insight (decisions, constraints, pitfalls).
  Both directories are scaffolded with READMEs containing the required templates. All entries carry `PatternId` / `PatternVersion` / `Status` / `Supersedes` metadata with dedupe, conflict-resolution (deprecate, never fork), and `blocked`-pattern safety gates.
- **Provenance:** Installed from upstream commit `aa280f28b1b73f9b6e6917b607eb92127b67b419` — the same pin the rest of the vendored awesome-copilot set uses. The body was verified byte-identical to that commit by sha256 (`adf94660…`), checked against the pin rather than against `main`. The frontmatter since carries two local overrides (`user-invocable: false`, `disable-model-invocation: true`), recorded in `.github/AWESOME-COPILOT.md` and the registry's local-overrides section; the `tools` list is untouched.
- **Registration:** `docs/AGENT_REGISTRY.md`, "Vendored Copilot custom agents", status `candidate`. Manifest row in `.github/AWESOME-COPILOT.md`. Registered 2026-07-30; see the amendment note below.
- **Activation:** Select the ".NET Self-Learning Architect" agent in VS Code Copilot Chat, or assign it to the Copilot coding agent. Whether the four models in its `model:` frontmatter are offered, and whether every declared tool resolves, is a property of the invoking Copilot client and has not been verified here.
- **Fit with this system:** The Lessons/Memories governance model (versioned patterns, supersession, blocked-pattern gate) parallels Agent 007's error ledger and absorbed-patterns records — that transferable governance shape, plus the parallel-vs-orchestration mode policy, is the reason to keep a .NET agent in a Python repository at all.
- **Boundary:** `.github/Lessons/` and `.github/Memories/` are editor-plane scratch directories. They sit outside every brain namespace, carry no packet, route, or writer lease, and reach no governed resource. Agent 007 remains the sole write-capable native agent.

## 2. Tool: richawo/minimal-llm-ui

- **Source:** [richawo/minimal-llm-ui](https://github.com/richawo/minimal-llm-ui) — minimal React/Next.js/Tailwind chat UI for local Ollama models (model toggling mid-conversation, saved conversations, prompt templates, configurable Ollama endpoint).
- **Install:** `scripts/install_minimal_llm_ui.sh` clones it alongside this repository and runs `npm install`. Verified 2026-07-25: `npm install` and `npm run build` both succeed (Node 20, npm 10). Not vendored into this repository — it is an external tool, kept at its upstream.
- **Run:** `ollama serve`, then `npm run dev` in the clone (UI at `http://localhost:3000`, Ollama at `http://localhost:11434`).

## 3. Reference library: github/awesome-copilot

- Community library of Copilot custom agents, instructions, skills, hooks, and plugins. Used here as the install source for the architect agent.
- A pinned copy now lives at `third_party/awesome-copilot/`, and the curated selection installed into `.github/` is recorded in `.github/AWESOME-COPILOT.md`. Both arrived after this document was first written; the original note that "no vendored copy is kept" was true on 2026-07-25 and is not any more.

## Amendment — 2026-07-30

This record was written when the agent was installed but before it was registered, which the `AGENTS.md` intake rule requires. That gap was found during a repository audit (PR #56) and is now closed: the agent is registered in `docs/AGENT_REGISTRY.md` and listed in `.github/AWESOME-COPILOT.md`.

Three statements in the original text were corrected rather than left standing:

- It claimed unavailable tools and models "degrade gracefully." Nothing here verified that, and it is client behavior this repository does not control.
- It claimed the Lessons/Memories stores were governed by the one-designated-writer rule. They are not — that rule covers brain-owned resources, and these are editor-plane scratch directories outside every namespace. The boundary is real but it is not that rule.
- It stated no vendored copy of awesome-copilot is kept. One now is.

Registering it also exposed a live defect, which is the point of the intake rule. `tests/test_agent_contract.py` requires every agent the registry lists as `candidate` to be closed to **both** invocation paths; the test reads the registry rather than a fixed list, so it began checking this agent the moment it was registered — and failed. Installed verbatim, the agent had neither `user-invocable: false` nor `disable-model-invocation: true`, so it was selectable in the picker *and* routable by another model. The second path is the one that matters: no human sees one agent route to another, and this is the only agent in the section that both spawns subagents and holds edit and terminal tools. Both flags are now set. Five days of that gap trace to skipping registration at install time.

One question is deliberately left open, in `docs/AGENT_REGISTRY.md`: the agent retains file-editing and terminal tools that the other three vendored Copilot agents had removed. That one is not a lifecycle gate but a change of function — an agent whose purpose is maintaining lessons and memories presumes it can write something — so it is recorded for decision rather than made unilaterally.
