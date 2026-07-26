#!/usr/bin/env bash
set -euo pipefail

readonly SKILL_UP_VERSION="0.7.0"
readonly RELEASE_BASE="https://github.com/alibaba/skill-up/releases/download/v${SKILL_UP_VERSION}"
readonly INSTALL_DIR="${SKILL_UP_INSTALL_DIR:-${HOME}/.local/bin}"

case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) archive="skill-up_${SKILL_UP_VERSION}_linux_amd64.tar.gz"; checksum="8b5f24e2d585e1f4513720f1f1542a462526c033f218d0c4998c445fe47b55e3" ;;
  Linux-aarch64|Linux-arm64) archive="skill-up_${SKILL_UP_VERSION}_linux_arm64.tar.gz"; checksum="f90da121539d7842b1ff88401bf07e0a9da38183335c5290f8df6d740e90d013" ;;
  Darwin-x86_64) archive="skill-up_${SKILL_UP_VERSION}_darwin_amd64.tar.gz"; checksum="e107d436f311a1be1e80005a43682aabbd97b57612968a90bdd1cd2a5d3c7400" ;;
  Darwin-arm64) archive="skill-up_${SKILL_UP_VERSION}_darwin_arm64.tar.gz"; checksum="39412b903847ab148bfd32510edc524f61ad3c2ccef9bda4eb7c33c31e5b74df" ;;
  *) echo "error: unsupported platform $(uname -s)/$(uname -m)" >&2; exit 1 ;;
esac

for command in curl sha256sum tar; do
  command -v "${command}" >/dev/null 2>&1 || { echo "error: ${command} is required" >&2; exit 1; }
done

tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT
curl --fail --silent --show-error --location "${RELEASE_BASE}/${archive}" --output "${tmp}/${archive}"
printf '%s  %s\n' "${checksum}" "${tmp}/${archive}" | sha256sum --check --status
tar -xzf "${tmp}/${archive}" -C "${tmp}" skill-up
mkdir -p "${INSTALL_DIR}"
install -m 0755 "${tmp}/skill-up" "${INSTALL_DIR}/skill-up"

actual="$("${INSTALL_DIR}/skill-up" --version | sed -n 's/^skill-up version //p')"
[[ "${actual}" == "${SKILL_UP_VERSION}" ]] || { echo "error: expected ${SKILL_UP_VERSION}, got ${actual:-unknown}" >&2; exit 1; }
printf 'skill-up %s installed at %s\n' "${actual}" "${INSTALL_DIR}/skill-up"
