#!/usr/bin/env bash
set -euo pipefail

readonly REQUIRED_OCR_VERSION="1.7.17"
export OCR_NO_UPDATE=1

if ! command -v ocr >/dev/null 2>&1; then
  echo "error: ocr is not installed; run scripts/install_open_code_review.sh" >&2
  exit 1
fi

installed="$(ocr version | sed -n '1s/^open-code-review v\([^ ]*\).*/\1/p')"
if [[ "${installed}" != "${REQUIRED_OCR_VERSION}" ]]; then
  echo "error: Open Code Review ${REQUIRED_OCR_VERSION} is required; found ${installed:-unknown}" >&2
  exit 1
fi

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "error: run this command inside a Git worktree" >&2
  exit 1
}

case "${1:-preview}" in
  preview)
    shift || true
    exec ocr delegate preview --repo "${repo_root}" "$@"
    ;;
  rules)
    shift
    if [[ "$#" -eq 0 ]]; then
      echo "usage: scripts/open_code_review.sh rules <path> [path ...]" >&2
      exit 2
    fi
    exec ocr delegate rule --repo "${repo_root}" "$@"
    ;;
  review)
    shift
    # Direct mode calls the configured provider. Credentials remain in the
    # approved environment or ~/.opencodereview, never in this repository.
    exec ocr review --repo "${repo_root}" --audience agent "$@"
    ;;
  *)
    echo "usage: scripts/open_code_review.sh {preview|rules|review} [ocr flags]" >&2
    exit 2
    ;;
esac
