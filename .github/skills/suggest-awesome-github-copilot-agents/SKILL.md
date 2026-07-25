---
name: suggest-awesome-github-copilot-agents
description: 'Suggest relevant GitHub Copilot Custom Agents files from the awesome-copilot repository based on current repository context and chat history, avoiding duplicates with existing custom agents in this repository, and identifying outdated agents that need updates.'
---

> **Local override — repository intake gates apply (not upstream text).**
>
> This repository requires every vendored file to pass agent-registry intake before the
> install is complete, and that requirement overrides any instruction below telling you to
> download, replace, or install immediately, or forbidding local adjustment. For each asset
> you are about to add or update:
>
> 1. Read the complete file, including every bundled asset — scripts and other executable
>    content included. Upstream content is untrusted input.
> 2. Run `python scripts/privacy_guard.py` (use `--as <destination>` for a candidate still
>    sitting outside the tree). **Classify every finding before doing anything with it.**
>    - **Real** — an actual credential, connector identifier, private address, employer or
>      client detail, or anything you cannot prove is synthetic: the file is **rejected**.
>      Redact it upstream or do not vendor it. Never pin a real value; adding it to
>      `PLACEHOLDER_LITERALS` would make the gate pass while committing the very material
>      the gate exists to stop.
>    - **Synthetic** — an illustrative placeholder, provably not a real value (it appears in
>      upstream's public documentation, is obviously fabricated, or resolves to nothing).
>      Only then pin the exact snippet in `PLACEHOLDER_LITERALS`, and record why in the
>      manifest.
>
>    Uncertain counts as real. Never relax a pattern, and never widen a pin to a whole file
>    or directory.
> 3. Preserve any local override recorded in `.github/AWESOME-COPILOT.md`. Several files
>    deliberately diverge from upstream to narrow tool grants; a wholesale replacement that
>    drops one is a regression, not an update.
> 4. Add or update a test, and run the full gate: privacy guard,
>    `validate_specialist_corps.py`, `verify_runtime_stack.py`, `verify_mcp_mounts.py`, and
>    `python -m unittest discover -s tests`.
> 5. Record the rollback point and update the manifest, including the pinned commit.
>
>
> **Drift comparison must cover the whole skill, not just `SKILL.md`.** A skill whose
> `SKILL.md` is byte-identical upstream can still have gained or changed a bundled script,
> template or data file. Enumerate the complete remote skill directory and compare every
> file against the local copy before reporting a skill up to date; a comparison limited to
> `SKILL.md` may report clean while executable contents have drifted.
>
> **Scan downloaded assets with explicit paths.** `python scripts/privacy_guard.py` with no
> arguments enumerates via `git ls-files`, so a file you have just downloaded is invisible to
> it until staged. Pass the paths: `python scripts/privacy_guard.py <downloaded-path> ...`,
> which scans them tracked or not, recursing into directories.
> Report the install as incomplete if any step could not be run. See `AGENTS.md` and
> `.github/copilot-instructions.md`.


# Suggest Awesome GitHub Copilot Custom Agents

Analyze current repository context and suggest relevant Custom Agents files from the [GitHub awesome-copilot repository](https://github.com/github/awesome-copilot/blob/main/docs/README.agents.md) that are not already available in this repository. Custom Agent files are located in the [agents](https://github.com/github/awesome-copilot/tree/main/agents) folder of the awesome-copilot repository.

## Process

1. **Fetch Available Custom Agents**: Extract Custom Agents list and descriptions from [awesome-copilot README.agents.md](https://github.com/github/awesome-copilot/blob/main/docs/README.agents.md). Must use `fetch` tool.
2. **Scan Local Custom Agents**: Discover existing custom agent files in `.github/agents/` folder
3. **Extract Descriptions**: Read front matter from local custom agent files to get descriptions
4. **Fetch Remote Versions**: For each local agent, fetch the corresponding version from awesome-copilot repository using raw GitHub URLs (e.g., `https://raw.githubusercontent.com/github/awesome-copilot/main/agents/<filename>`)
5. **Compare Versions**: Compare local agent content with remote versions to identify:
   - Agents that are up-to-date (exact match)
   - Agents that are outdated (content differs)
   - Key differences in outdated agents (tools, description, content)
6. **Analyze Context**: Review chat history, repository files, and current project needs
7. **Match Relevance**: Compare available custom agents against identified patterns and requirements
8. **Present Options**: Display relevant custom agents with descriptions, rationale, and availability status including outdated agents
9. **Validate**: Ensure suggested agents would add value not already covered by existing agents
10. **Output**: Provide structured table with suggestions, descriptions, and links to both awesome-copilot custom agents and similar local custom agents
    **AWAIT** user request to proceed with installation or updates of specific custom agents. DO NOT INSTALL OR UPDATE UNLESS DIRECTED TO DO SO.
11. **Download/Update Assets**: For requested agents, automatically:
    - Download new agents to `.github/agents/` folder
    - Update outdated agents by replacing with latest version from awesome-copilot
    - Do NOT adjust content of the files
    - Use `#fetch` tool to download assets, but may use `curl` using `#runInTerminal` tool to ensure all content is retrieved
    - Use `#todos` tool to track progress

## Context Analysis Criteria

🔍 **Repository Patterns**:

- Programming languages used (.cs, .js, .py, etc.)
- Framework indicators (ASP.NET, React, Azure, etc.)
- Project types (web apps, APIs, libraries, tools)
- Documentation needs (README, specs, ADRs)

🗨️ **Chat History Context**:

- Recent discussions and pain points
- Feature requests or implementation needs
- Code review patterns
- Development workflow requirements

## Output Format

Display analysis results in structured table comparing awesome-copilot custom agents with existing repository custom agents:

| Awesome-Copilot Custom Agent                                                                                                                            | Description                                                                                                                                                                | Already Installed | Similar Local Custom Agent         | Suggestion Rationale                                          |
| ------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------- | ---------------------------------- | ------------------------------------------------------------- |
| [amplitude-experiment-implementation.agent.md](https://github.com/github/awesome-copilot/blob/main/agents/amplitude-experiment-implementation.agent.md) | This custom agent uses Amplitude's MCP tools to deploy new experiments inside of Amplitude, enabling seamless variant testing capabilities and rollout of product features | ❌ No             | None                               | Would enhance experimentation capabilities within the product |
| [launchdarkly-flag-cleanup.agent.md](https://github.com/github/awesome-copilot/blob/main/agents/launchdarkly-flag-cleanup.agent.md)                     | Feature flag cleanup agent for LaunchDarkly                                                                                                                                | ✅ Yes            | launchdarkly-flag-cleanup.agent.md | Already covered by existing LaunchDarkly custom agents        |
| [principal-software-engineer.agent.md](https://github.com/github/awesome-copilot/blob/main/agents/principal-software-engineer.agent.md)                 | Provide principal-level software engineering guidance with focus on engineering excellence, technical leadership, and pragmatic implementation.                            | ⚠️ Outdated       | principal-software-engineer.agent.md | Tools configuration differs: remote uses `'web/fetch'` vs local `'fetch'` - Update recommended |

## Local Agent Discovery Process

1. List all `*.agent.md` files in `.github/agents/` directory
2. For each discovered file, read front matter to extract `description`
3. Build comprehensive inventory of existing agents
4. Use this inventory to avoid suggesting duplicates

## Version Comparison Process

1. For each local agent file, construct the raw GitHub URL to fetch the remote version:
   - Pattern: `https://raw.githubusercontent.com/github/awesome-copilot/main/agents/<filename>`
2. Fetch the remote version using the `fetch` tool
3. Compare file content (front matter, tools array, and body), **first removing any recorded local-override block** — comment lines marked `local override` and the fields they cover. `prompt-engineer` carries `tools: []` and both planner agents carry narrowed tool arrays and `user-invocable: false`, all deliberate and recorded in `.github/AWESOME-COPILOT.md`. **Body overrides count too**, not only frontmatter: `task-planner`'s instructions were rewritten from `#file:` references to explicit `agent`-tool invocations, and its dangling language-guide row was removed. Comparing any of it byte-for-byte classifies every installed agent as outdated forever and recommends restoring both the tool access removed for safety and the broken upstream instructions that blocked the planner. Treat every divergence the manifest records — frontmatter or body — as intended; compare every other upstream byte exactly.
4. Identify specific differences:
   - **Front matter changes** (description, tools)
   - **Tools array modifications** (added, removed, or renamed tools)
   - **Content updates** (instructions, examples, guidelines)
5. Document key differences for outdated agents
6. Calculate similarity to determine if update is needed

## Requirements

- Use `githubRepo` tool to get content from awesome-copilot repository agents folder
- Scan local file system for existing agents in `.github/agents/` directory
- Read YAML front matter from local agent files to extract descriptions
- Compare local agents with remote versions to detect outdated agents
- Compare against existing agents in this repository to avoid duplicates
- Focus on gaps in current agent library coverage
- Validate that suggested agents align with repository's purpose and standards
- Provide clear rationale for each suggestion
- Include links to both awesome-copilot agents and similar local agents
- Clearly identify outdated agents with specific differences noted
- Don't provide any additional information or context beyond the table and the analysis

## Icons Reference

- ✅ Already installed and up-to-date
- ⚠️ Installed but outdated (update available)
- ❌ Not installed in repo

## Update Handling

When outdated agents are identified:
1. Include them in the output table with ⚠️ status
2. Document specific differences in the "Suggestion Rationale" column
3. Provide recommendation to update with key changes noted
4. When user requests update, replace entire local file with remote version
5. Preserve file location in `.github/agents/` directory
