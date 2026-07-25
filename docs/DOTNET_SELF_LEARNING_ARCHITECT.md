# .NET Self-Learning Architect — Install Record (2026-07-25)

Joe supplied two repositories and one custom-agent definition for installation. This documents what was installed, where it came from, and how to use it.

## 1. Custom agent: `.github/agents/dotnet-self-learning-architect.agent.md`

- **Source:** [github/awesome-copilot](https://github.com/github/awesome-copilot) — `agents/dotnet-self-learning-architect.agent.md`, installed verbatim per that repository's documented install method for custom agents ("download the `*.agent.md` file and add it to your repository").
- **What it is:** A principal-level .NET architect agent for GitHub Copilot (VS Code chat / Copilot coding agent). It designs .NET systems, chooses between parallel-subagent and orchestrated-team execution, and enforces a self-learning contract on itself and every subagent it spawns.
- **Self-learning storage:** The agent writes governed learning artifacts to:
  - `.github/Lessons/` — one file per mistake/correction (root cause, fix, prevention).
  - `.github/Memories/` — one file per durable insight (decisions, constraints, pitfalls).
  Both directories are scaffolded with READMEs containing the required templates. All entries carry `PatternId` / `PatternVersion` / `Status` / `Supersedes` metadata with dedupe, conflict-resolution (deprecate, never fork), and `blocked`-pattern safety gates.
- **Activation:** Select the ".NET Self-Learning Architect" agent in VS Code Copilot Chat, or assign it to the Copilot coding agent. The `model` and `tools` frontmatter lists are honored by Copilot; unavailable tools/models degrade gracefully.
- **Fit with this system:** The Lessons/Memories governance model (versioned patterns, supersession, blocked-pattern gate) parallels Agent 007's error ledger and absorbed-patterns records. The `.github/Lessons` and `.github/Memories` stores are owned by this Copilot agent — under the one-designated-writer rule, other agents read but do not write them.

## 2. Tool: richawo/minimal-llm-ui

- **Source:** [richawo/minimal-llm-ui](https://github.com/richawo/minimal-llm-ui) — minimal React/Next.js/Tailwind chat UI for local Ollama models (model toggling mid-conversation, saved conversations, prompt templates, configurable Ollama endpoint).
- **Install:** `scripts/install_minimal_llm_ui.sh` clones it alongside this repository and runs `npm install`. Verified 2026-07-25: `npm install` and `npm run build` both succeed (Node 20, npm 10). Not vendored into this repository — it is an external tool, kept at its upstream.
- **Run:** `ollama serve`, then `npm run dev` in the clone (UI at `http://localhost:3000`, Ollama at `http://localhost:11434`).

## 3. Reference library: github/awesome-copilot

- Community library of Copilot custom agents, instructions, skills, hooks, and plugins. Used here as the install source for the architect agent; browse it for further agents worth absorbing. No vendored copy is kept — install individual `*.agent.md` files as needed, as done in §1.
