#!/usr/bin/env bash
set -euo pipefail

# One-shot setup for the governed execution host (docs/RUNTIME_HOST_DECISION.md:
# Joe's workstation is the only host authorized to run real missions). Safe to
# re-run; every step is idempotent. This script installs and verifies — it never
# touches credentials, grants, or the trusted-launcher signing key, which are
# created by Joe outside this script (see docs/MONDAY_ACTIVATION_RUNBOOK.md).

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "error: run this inside the repository worktree" >&2
  exit 1
}
cd "${repo_root}"

version="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
case "${version}" in
  3.11 | 3.12) ;;
  *)
    echo "error: repository validation requires Python 3.11 or 3.12; found ${version}" >&2
    exit 1
    ;;
esac

echo "==> Submodules (vendor derivation checks skip without them)"
git submodule update --init

echo "==> Full runtime stack from the committed lock"
python3 -m pip install -r requirements/lock-2026-07-24.txt

echo "==> Every declared dependency must import (fails on absence)"
python3 scripts/verify_runtime_stack.py --require-tier all >/dev/null

echo "==> Generated agent projections match their canonical sources"
python3 scripts/generate_claude_agents.py --check

echo "==> Validation surface"
python3 scripts/privacy_guard.py
python3 scripts/validate_specialist_corps.py >/dev/null
python3 -m unittest discover -s tests

cat <<'DONE'

Workstation setup complete. Still yours to do, in order (none of it scriptable):
  1. Create the trusted-launcher signing key outside the repository, mode 0600.
  2. Credential the mounts you will use (config/mcp_mounts.toml): gdrive OAuth,
     github/postgres tokens, civil3d needs a live session.
  3. Run missions: all 39 modes are prepared in config/mission_catalog.toml.
     Coverage at any time:
       python -c "from runtime.mission_runner import MissionRunner; \
                  import json; print(json.dumps(MissionRunner().promotion_status(), indent=2))"
DONE
