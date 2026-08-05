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

# Derived from this script's location, not from git, so root-finding works
# before git is installed and a copied-in tree gets the clear refusal below
# instead of a confusing git error.
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [ ! -f "${repo_root}/AGENTS.md" ]; then
  echo "error: ${repo_root} does not look like the repository root" >&2
  exit 1
fi
# Refused HERE, before the first mutation: deriving repo_root without git
# gives a copied-in tree a clear error, but the handoff target
# (workstation_setup.sh) and the submodule steps genuinely need a git clone —
# discovering that after apt, wsl.conf, and the venv would leave a
# half-provisioned host.
if [ ! -e "${repo_root}/.git" ]; then
  echo "error: ${repo_root} is not a git clone (no .git). The governed-host" >&2
  echo "setup needs one — clone per docs/WSL_UBUNTU_SETUP.md and re-run." >&2
  exit 1
fi
cd "${repo_root}"

# Built from what this run actually resolved — the distribution it is inside
# and the clone it provisioned — so the completion message never names a
# path or distro this run did not verify. The canonical form is
# wsl -d Ubuntu --cd /root/Joeyyy -- claude (docs/WSL_UBUNTU_SETUP.md).
launch_command="wsl -d ${WSL_DISTRO_NAME:-Ubuntu} --cd ${repo_root} -- claude"

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
# -e follows symlinks, so this is true exactly for a missing entry or a
# broken link — the two states worth repairing. Anything that already
# resolves (a real file, or a valid link from some other installation)
# satisfies the launch path and is left alone; -f clears the dangling name.
if [ -x "${HOME}/.local/bin/claude" ] && [ ! -e /usr/local/bin/claude ]; then
  ln -sf "${HOME}/.local/bin/claude" /usr/local/bin/claude
fi
# Completion is a claim about the command Joe will run, not about this shell:
# resolve claude against the WSL default (non-login) PATH and require it to be
# executable, so a stale or permission-broken entry fails here instead of at
# the first launch.
wsl_default_path='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
resolved_claude="$(PATH="${wsl_default_path}" command -v claude || true)"
if [ -z "${resolved_claude}" ] || [ ! -x "${resolved_claude}" ]; then
  echo "error: claude does not resolve to an executable on the WSL default PATH." >&2
  echo "A stale /usr/local/bin/claude from an earlier install would cause this:" >&2
  echo "inspect it, remove it if it is not an installation you want, and re-run." >&2
  exit 1
fi

if [ "${repo_root}" != "/root/Joeyyy" ]; then
  echo "note: this clone is at ${repo_root}, not the canonical /root/Joeyyy;" >&2
  echo "the launch command printed at the end reflects this clone." >&2
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

echo "==> Launch the offline-verifiable MCP mounts (the layer Node was installed for)"
# workstation_setup.sh runs the validation surface but not the strict mount
# probe; the canonical task runner and the mounts CI job both treat the probe
# as the check that actually launches the offline-verifiable mounts. Without
# it, a host whose npx layer is broken reports a usable governed host and
# discovers otherwise at the first mission. The report is captured and shown
# on failure — which mount refused and why is the whole point of probing.
if ! mount_report="$(python "${repo_root}/scripts/verify_mcp_mounts.py" --strict)"; then
  printf '%s\n' "${mount_report}" >&2
  echo "error: the offline-verifiable MCP mounts did not launch; the report" >&2
  echo "above names the mount and reason." >&2
  exit 1
fi

# Never advertise a command this run just determined will not work: with a
# non-root default user the plain form dies at --cd /root/Joeyyy.
effective_launch="${launch_command}"
if [ "${default_user_is_root}" -eq 0 ]; then
  effective_launch="wsl -d ${WSL_DISTRO_NAME:-Ubuntu} -u root --cd ${repo_root} -- claude"
fi

cat <<DONE

WSL layer complete. Launch from Windows with:

  ${effective_launch}

The first launch asks you to authenticate and to trust this folder; later
launches drop straight in. Validation commands run inside the virtual
environment: activate it with  . .venv/bin/activate
DONE
if [ "${wsl_conf_changed}" -eq 1 ]; then
  cat <<NOTE

/etc/wsl.conf now sets the default user to root. From Windows, run
  wsl --terminate ${WSL_DISTRO_NAME:-Ubuntu}
once; the next launch picks it up.
NOTE
elif [ "${default_user_is_root}" -eq 1 ]; then
  # A prior run may have appended the block and then failed before printing
  # the restart note; keying the reminder on "changed this run" would lose it
  # exactly then. Phrased conditionally because whether the restart already
  # happened is not observable from inside the distribution.
  cat <<NOTE

/etc/wsl.conf sets the default user to root. If this distribution has not
been restarted since that line was added, run
  wsl --terminate ${WSL_DISTRO_NAME:-Ubuntu}
from Windows once; the next launch picks it up.
NOTE
fi
