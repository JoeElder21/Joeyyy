#!/usr/bin/env bash
set -euo pipefail

# Audited repository integration pin. OCR_NO_UPDATE prevents the npm wrapper
# from silently replacing this version after installation.
readonly OCR_VERSION="1.7.17"
export OCR_NO_UPDATE=1

if ! command -v npm >/dev/null 2>&1; then
  echo "error: npm is required to install Open Code Review" >&2
  exit 1
fi

npm install --global "@alibaba-group/open-code-review@${OCR_VERSION}"

installed="$(ocr version | sed -n '1s/^open-code-review v\([^ ]*\).*/\1/p')"
if [[ "${installed}" != "${OCR_VERSION}" ]]; then
  echo "error: expected Open Code Review ${OCR_VERSION}, got ${installed:-unknown}" >&2
  exit 1
fi

printf 'Open Code Review %s installed at %s\n' "${installed}" "$(command -v ocr)"
