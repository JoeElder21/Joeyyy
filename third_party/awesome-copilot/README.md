# Upstream notice — github/awesome-copilot

This repository vendors agents, instructions, and skills from
[github/awesome-copilot](https://github.com/github/awesome-copilot), pinned at
commit `aa280f28b1b73f9b6e6917b607eb92127b67b419`.

`LICENSE` in this directory is the upstream MIT licence text, reproduced verbatim.
The MIT terms require the copyright notice and permission notice to accompany
copies or substantial portions of the software, so it is tracked here rather than
linked externally.

## What is covered

Only the files **named in the manifest** are vendored from upstream. These
directories are not exclusively upstream: `.github/agents/` also holds
repository-authored agents (for example `dotnet-self-learning-architect` and
`market-operator`), which were never in `github/awesome-copilot` and carry no
upstream provenance or licence obligation. Treating the whole directory as
vendored would send a drift check or a licence review at first-party work.

| Location | Contents |
|---|---|
| `.github/instructions/` | Instruction files listed in the manifest |
| `.github/agents/` | Custom agents listed in the manifest — **not** every file here |
| `.github/skills/` | Discovery skills listed in the manifest |

`.github/AWESOME-COPILOT.md` is the manifest: per-file rationale, the pinned
commit, local overrides, and how to refresh. `docs/AGENT_REGISTRY.md` records the
agents' lifecycle status.

## Local modifications

Vendored files are byte-identical to upstream except where `.github/AWESOME-COPILOT.md`
records a deliberate local override. Those overrides exist for safety reasons — narrowing
tool grants — and are listed there with rationale. The MIT licence permits modification;
this note exists so the divergence is documented rather than silent.
