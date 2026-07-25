# Repository guidance for Claude-based runtimes

**`AGENTS.md` is the authoritative operating contract for this repository. Read it first
and follow it in full.** This file exists so Claude-based runtimes get the same guidance
Codex-based ones get from `AGENTS.md`; it deliberately does not restate those rules,
because a second copy is how the two drift apart.

Everything below is Claude-runtime-specific and additive.

## Before any commit

```bash
python scripts/privacy_guard.py
python scripts/validate_specialist_corps.py
ruff check .
python -m unittest discover -s tests -v
```

`AGENTS.md` requires TOML validation and the test suite before committing. `ruff check`
is the house Python standard for agent-generated code. `pre-commit install` wires all of
these to run automatically — see `CONTRIBUTING.md`.

Python 3.11 or 3.12. CI validates both.

## Non-obvious constraints

- **The privacy guard scans every tracked file, including anything you write.** It blocks
  email addresses, phone numbers, street addresses, Drive/Docs links, credential-shaped
  assignments, binaries, non-UTF-8 files, and Git LFS pointers. A doc that quotes an
  example credential or contact detail will fail CI.
- **Actions must be SHA-pinned.** New workflow steps need a full commit SHA with the
  version as a trailing comment. `tests/test_repo_hygiene.py` fails on floating tags.
- **`ruff-format` is enabled and enforced.** The tree was brought formatter-clean in one
  mechanical commit, and `ruff format --check --diff .` is now a required CI step with a
  matching pre-commit hook. Run `ruff format .` before committing; do not hand-format
  against it. CI and pre-commit both pin ruff to the same version, so a local pass means
  a CI pass — bump the two together or not at all.
- **Governance docs are tested.** `tests/test_governance_docs.py` and
  `tests/test_agent_contract.py` assert that documentation, templates, registry, and tests
  agree. Change them as a set.
- **Dated records are append-only in spirit.** Files like
  `docs/RECONCILIATION_2026-07-24.md` are point-in-time evidence. Write a new dated record
  rather than editing history.

## Claude-native surfaces in this repository

- `scripts/claude_runtime.py` — governed dispatch with typed Anthropic tool definitions and
  fail-closed `ToolUseBlock` handling.
- `scripts/governance_mcp_server.py` — makes the packet-only connector policy enforceable
  over MCP.
- `config/mcp_mounts.toml` + `scripts/verify_mcp_mounts.py` — approved MCP mounts. Adding a
  mount is a connector-policy decision, not a config edit.

## Where to start reading

`docs/README.md` indexes all repository records in reading order.
