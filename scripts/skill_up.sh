#!/usr/bin/env bash
set -euo pipefail

readonly REQUIRED_VERSION="0.7.0"
repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "error: run inside the JOEYYY worktree" >&2; exit 1; }
export PATH="${HOME}/.local/bin:${PATH}"

command -v skill-up >/dev/null 2>&1 || { echo "error: run scripts/install_skill_up.sh" >&2; exit 1; }
actual="$(skill-up --version | sed -n 's/^skill-up version //p')"
[[ "${actual}" == "${REQUIRED_VERSION}" ]] || { echo "error: skill-up ${REQUIRED_VERSION} required; found ${actual:-unknown}" >&2; exit 1; }

eval_file="${SKILL_UP_EVAL_FILE:-${repo_root}/.agents/skills/skill-upper/evals/eval.yaml}"
[[ -f "${eval_file}" ]] || { echo "error: eval file not found: ${eval_file}" >&2; exit 1; }

case "${1:-validate}" in
  validate) shift || true; exec skill-up validate "${eval_file}" "$@" ;;
  list) shift || true; exec skill-up list-cases "${eval_file}" "$@" ;;
  run)
    shift || true
    report_root="${SKILL_UP_REPORT_ROOT:-${repo_root}/.state/skill-up}"
    mkdir -p "${report_root}"
    exec skill-up run "${eval_file}" --output-dir "${report_root}" "$@"
    ;;
  *) echo "usage: scripts/skill_up.sh {validate|list|run} [skill-up flags]" >&2; exit 2 ;;
esac
