#!/usr/bin/env bash
set -euo pipefail

# The WSL layer beneath scripts/workstation_setup.sh. The governed execution
# host (docs/RUNTIME_HOST_DECISION.md: Joe's workstation, no third host) is a
# Windows machine, so the environment that actually runs missions is an Ubuntu
# distribution under WSL with this repository at /root/Joeyyy. This script
# takes a fresh distribution to the point where scripts/workstation_setup.sh
# can run, then runs it, so the end state is one command away from a mission:
#
#   wsl -d Ubuntu --cd /root/Joeyyy -- claude
#
# Safe to re-run; every step is idempotent. It installs and verifies — it
# never touches credentials, grants, or the trusted-launcher signing key.
# docs/WSL_UBUNTU_SETUP.md records the full runbook, the one floating-channel
# trust decision this script makes, and what stays manual.

# Printed with the distribution this run is actually inside, so the recovery
# path onto Ubuntu-24.04 reports a command that targets it rather than the
# canonical default.
launch_command="wsl -d ${WSL_DISTRO_NAME:-Ubuntu} --cd /root/Joeyyy -- claude"

if ! grep -qiE 'microsoft|wsl' /proc/version; then
  echo "error: not a WSL kernel; this script provisions the WSL layer only." >&2
  echo "On a Linux host, run scripts/workstation_setup.sh directly." >&2
  exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "error: run as root — the governed clone lives at /root/Joeyyy." >&2
  echo "From Windows: wsl -d Ubuntu -u root" >&2
  exit 1
fi

# Derived from this script's location, not from git: on a fresh distribution
# git is one of the packages this script exists to install, and a tree copied
# in without .git should still provision rather than fail at the first line.
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [ ! -f "${repo_root}/AGENTS.md" ]; then
  echo "error: ${repo_root} does not look like the repository root" >&2
  exit 1
fi
cd "${repo_root}"

echo "==> OS packages (git, curl, build tools, Python 3.12, Node.js for the npx mounts)"
export DEBIAN_FRONTEND=noninteractive
apt-get update
if ! apt-cache show python3.12 >/dev/null 2>&1; then
  echo "error: this Ubuntu release does not package Python 3.12, which the" >&2
  echo "validation surface requires (AGENTS.md). Install the Ubuntu-24.04" >&2
  echo "distribution instead — wsl --install -d Ubuntu-24.04 — and use that" >&2
  echo "name after -d in the launch command." >&2
  exit 1
fi
apt-get install -y git curl ca-certificates build-essential \
  python3.12 python3.12-venv nodejs npm

echo "==> Default WSL user (the launch command assumes root)"
wsl_conf_changed=0
default_user_is_root=1
if [ -f /etc/wsl.conf ] && grep -qi '^[[:space:]]*\[user\]' /etc/wsl.conf; then
  # Last default= wins, matching how WSL reads the file. A default= key in a
  # section other than [user] would be misread here; wsl.conf has no such key
  # elsewhere today, and full INI parsing in shell is not worth that corner.
  current_default="$(sed -n 's/^[[:space:]]*default[[:space:]]*=[[:space:]]*//Ip' /etc/wsl.conf | tail -n1 | tr -d '[:space:]')"
  if [ "${current_default}" = "root" ]; then
    echo "    /etc/wsl.conf already sets default=root; nothing to do."
  else
    echo "    /etc/wsl.conf sets default=${current_default:-<unset>}, not root; leaving it"
    echo "    alone. The launch command below is adjusted with -u root; for the plain"
    echo "    form, set default=root in the [user] section yourself."
    default_user_is_root=0
  fi
else
  printf '\n[user]\ndefault=root\n' >>/etc/wsl.conf
  wsl_conf_changed=1
fi

echo "==> Claude Code CLI"
if command -v claude >/dev/null 2>&1 || [ -x "${HOME}/.local/bin/claude" ]; then
  echo "    already installed; leaving it to manage its own updates."
else
  # Anthropic's official installer — a floating channel, accepted deliberately:
  # the CLI self-updates after any install, so a pin here would claim a control
  # that does not exist. Recorded in docs/WSL_UBUNTU_SETUP.md.
  curl -fsSL https://claude.ai/install.sh | bash
fi
# The launch command runs claude through a non-login shell whose PATH is the
# WSL default — system directories only. ~/.profile is what adds ~/.local/bin,
# and non-login shells never read it, so the CLI must be reachable from
# /usr/local/bin or the launch command dies with "command not found".
# -f so a stale or broken symlink is replaced on re-run; a real file there
# (say, an npm-managed install) is left alone.
if [ -x "${HOME}/.local/bin/claude" ]; then
  if [ -L /usr/local/bin/claude ] || [ ! -e /usr/local/bin/claude ]; then
    ln -sf "${HOME}/.local/bin/claude" /usr/local/bin/claude
  fi
fi

if [ "${repo_root}" != "/root/Joeyyy" ]; then
  echo "note: this clone is at ${repo_root}, not /root/Joeyyy — adjust --cd in" >&2
  echo "the launch command accordingly." >&2
fi

echo "==> Virtual environment (Python 3.12 per docs/RUNTIME_HOST_DECISION.md)"
if [ -x "${repo_root}/.venv/bin/python" ]; then
  venv_version="$("${repo_root}/.venv/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  if [ "${venv_version}" != "3.12" ]; then
    echo "error: the existing .venv is Python ${venv_version}; the full stack resolves" >&2
    echo "for 3.12 only (docs/RUNTIME_HOST_DECISION.md). Remove ${repo_root}/.venv" >&2
    echo "and re-run." >&2
    exit 1
  fi
else
  python3.12 -m venv "${repo_root}/.venv"
fi
. "${repo_root}/.venv/bin/activate"
# No pip upgrade: the venv's bundled pip is enough for the committed lock —
# proven by a fresh-venv run against lock-runtime-contracts.txt — and the CLI
# installer above stays the only floating channel in this layer.

echo "==> Hand off to the governed-host setup"
bash "${repo_root}/scripts/workstation_setup.sh"

# Never advertise a command this run just determined will not work: with a
# non-root default user the plain form dies at --cd /root/Joeyyy.
effective_launch="${launch_command}"
if [ "${default_user_is_root}" -eq 0 ]; then
  effective_launch="wsl -d ${WSL_DISTRO_NAME:-Ubuntu} -u root --cd /root/Joeyyy -- claude"
fi

cat <<DONE

WSL layer complete. Launch from Windows with:

  ${effective_launch}

The first launch asks you to authenticate and to trust this folder; later
launches drop straight in. Validation commands run inside the virtual
environment: activate it with  . .venv/bin/activate
DONE
if [ "${wsl_conf_changed}" -eq 1 ]; then
  cat <<'NOTE'

/etc/wsl.conf now sets the default user to root. From Windows, run
`wsl --terminate Ubuntu` once; the next launch picks it up.
NOTE
fi
