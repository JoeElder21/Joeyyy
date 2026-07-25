# Changelog

Repository-level changes. Agent-contract and roster history lives in
`docs/AGENT_REGISTRY.md` and the dated records in `docs/`.

## 2026-07-25 — Repository engineering substrate

Record: `docs/REPO_OPTIMIZATION_2026-07-25.md`. No governance rule, packet contract,
schema, or agent definition changed.

### Added

- Supply-chain and workflow security: `.github/workflows/security.yml` runs zizmor static
  analysis over the workflows on push, PR, and weekly.
- `.github/dependabot.yml` — grouped weekly updates for pip, npm (`connectors/aps`), and
  GitHub Actions.
- `.pre-commit-config.yaml` — gitleaks, ruff, hygiene hooks, plus `privacy_guard.py` and
  `validate_specialist_corps.py` as local hooks.
- Contributor surface: `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `.editorconfig`,
  `.github/CODEOWNERS`, `.github/pull_request_template.md`.
- Issue forms converting existing paper workflows to structured intake:
  `.github/ISSUE_TEMPLATE/agent-intake.yml` and `absorption-candidate.yml`. The absorption
  form makes the FakeGit provenance check a required field.
- `docs/README.md` — index of all 31 documentation records.
- `CLAUDE.md` — repository guidance for Claude-based runtimes, pointing at `AGENTS.md`.
- `tests/test_repo_hygiene.py` — 14 tests asserting the substrate cannot silently regress,
  including that no GitHub Action is referenced by a floating tag.

### Changed

- `.github/workflows/validate-agent.yml` — added `verify_runtime_stack.py` and
  `verify_mcp_mounts.py` to validation; added `lint` (ruff) and `connectors` (Node) jobs;
  pinned all actions to full commit SHAs; set `persist-credentials: false`; added a
  cancel-in-progress concurrency group.
- `pyproject.toml` — added `[tool.ruff]` (house Python standard) and a `lint` task; the
  `validate` task now includes `verify_mcp_mounts.py`.

### Fixed

- Four pre-existing lint findings, with no behavior change: unused `re` import in
  `tests/test_specialist_corps.py`; ambiguous variable `l` in `scripts/trusted_launcher.py`
  and `tests/test_trusted_launcher.py`; unused-import annotation on the OpenTelemetry
  availability probe in `scripts/observability.py`.

### Open decisions

Recorded in `docs/REPO_OPTIMIZATION_2026-07-25.md`: license selection, DeepEval adoption
for the behavioral acceptance gate, `snyk/agent-scan` under the connector policy, whether to
enable `ruff-format`, and a one-off TruffleHog history sweep.
