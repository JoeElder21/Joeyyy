# Contributing

This repository is Joe Elder's agent governance system. `AGENTS.md` is the authoritative
operating contract — this document covers only the mechanics of getting a change landed.

## Before you commit

```bash
python -m pip install pre-commit && pre-commit install   # once
```

That installs **most** of the gates CI runs — the privacy guard, corps validation, the
unit suite, gitleaks, `ruff check`, and `ruff format --check` — so those failures surface
before a push rather than after. It does **not** install `verify_runtime_stack.py` or the
strict MCP mount probe, and the unit suite lets its JSON Schema check skip when
`jsonschema` is absent. A contributor relying on the hooks alone can therefore pass
locally and still fail CI on an invalid schema or a broken mount, so run the full manual
sequence below before pushing.

To run everything by hand:

```bash
# Install first. verify_runtime_stack.py catches the ImportError for jsonschema
# and rtoml and then reports zero schemas and zero TOML files checked -- exiting
# 0, so the audit passes while validating nothing. The install has to precede
# the verifier, not follow it.
# The LOCK, not the manifest. CI installs the resolved lock and osv-scanner
# audits it with --no-resolve, so installing the floating manifest here puts a
# resolution on the workstation that nothing scanned and CI never tested.
python -m pip install -r requirements/lock-runtime-contracts.txt  # jsonschema, rtoml, mcp
# Ruff too: runtime-contracts.txt does not carry it, and installing
# pre-commit builds Ruff an isolated hook environment whose executable is
# not on PATH -- so this sequence reached `ruff check .` with no `ruff`
# command and stopped there. Pinned to the version CI and the hook use.
python -m pip install ruff==0.14.6
python scripts/privacy_guard.py            # public-repository boundary
python scripts/validate_specialist_corps.py # roster, isolation, schema, registry
python scripts/verify_runtime_stack.py     # dependency and contract audit
python scripts/verify_mcp_mounts.py --strict  # approved MCP mounts, launched not assumed
ruff check .                               # house Python standard
ruff format --check .                      # CI enforces this separately from `check`
python -m unittest discover -s tests -v    # full suite
```

Or, with taskipy installed: `task validate`.

Python 3.11 or 3.12 is required. CI validates both.

## Standards

These come from `AGENTS.md` and are enforced by tests, not convention:

- **Small, reviewable, reversible changes with an audit trail.** Every persistent
  improvement must be evidence-led, tested, versioned, and recorded with a rollback point.
- **Change the contract as a set.** When the agent contract changes, update documentation,
  templates, registry, and tests together — `tests/test_governance_docs.py` and
  `tests/test_agent_contract.py` will fail if they drift apart.
- **Nothing private, ever.** This repository is public. No raw Drive content, private facts,
  credentials, connector identifiers, or employer/client source records. The privacy guard
  blocks binaries, non-UTF-8 files, and Git LFS pointers as well.
- **No impossible claims.** Do not describe an agent, connector, or capability as available
  unless it is verified in the session. Do not claim continuous background operation.
- **Actions are SHA-pinned.** New workflow steps must reference a full commit SHA with the
  version in a trailing comment. `tests/test_repo_hygiene.py` fails on floating tags.

## Adding an agent, or absorbing an external capability

Use the issue forms — `.github/ISSUE_TEMPLATE/agent-intake.yml` and
`absorption-candidate.yml`. They encode the required steps, including the provenance check
that the FakeGit finding made mandatory. Then follow `docs/AGENT_COMMUNITY_PROTOCOL.md` and
register the result in `docs/AGENT_REGISTRY.md`.

## Branches and pull requests

Work on a topic branch and open a pull request against `main`. Fill in the PR template; the
validation checklist is the one CI runs, and the rollback line is required by the change
standards. Keep unrelated reformatting out of the diff.
