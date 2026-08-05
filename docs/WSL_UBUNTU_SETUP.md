# WSL Ubuntu Setup — 2026-08-05

`docs/RUNTIME_HOST_DECISION.md` names Joe's workstation the only governed
execution host and rules out any third host. That workstation runs Windows,
which the decision record left implicit. This record makes the host concrete:
an Ubuntu distribution under WSL, with this repository at `/root/Joeyyy`, so
that one command on the Windows side drops into Claude Code inside the
governed clone:

```
wsl -d Ubuntu --cd /root/Joeyyy -- claude
```

`scripts/wsl_ubuntu_setup.sh` provisions a fresh distribution up to the point
where `scripts/workstation_setup.sh` — the existing one-shot for the governed
host — can take over, then runs it. Everything below the launch command is
that script's job; nothing here changes what the workstation setup installs
or verifies.

## Windows side, once

In an elevated PowerShell:

```powershell
wsl --install -d Ubuntu
wsl --update
```

Reboot if the installer asks. Complete Ubuntu's first-launch prompt with any
username — the setup script makes `root` the distribution's default user
afterward, which the launch command depends on (see below).

## Inside the distribution, once

```powershell
wsl -d Ubuntu -u root
```

then, in the distribution:

```bash
apt-get update && apt-get install -y git
git clone https://github.com/JoeElder21/Joeyyy.git /root/Joeyyy
cd /root/Joeyyy
bash scripts/wsl_ubuntu_setup.sh
```

The first line matters on a minimal image: the setup script installs git as
an OS package, but the clone is how the script arrives, so git cannot wait
for it. On an image that already ships git the line is a no-op.

The script is idempotent and safe to re-run. In order, it:

1. Refuses to run outside a WSL kernel or as a non-root user.
2. Installs OS packages: `git`, `curl`, `ca-certificates`, `build-essential`,
   `python3.12`, `python3.12-venv`, and `nodejs`/`npm`. Node is not optional:
   the two offline-verifiable mounts in `config/mcp_mounts.toml` launch via
   `npx`, so without it `scripts/verify_mcp_mounts.py` and the mount tests in
   the suite fail on this host. On an Ubuntu release that does not package
   Python 3.12 it stops with instructions to install the `Ubuntu-24.04`
   distribution instead, because the validation surface requires Python 3.11
   or 3.12 and this script will not add a third-party package archive to get
   one.
3. Appends a `[user] default=root` section to `/etc/wsl.conf` if no `[user]`
   section exists, and says so. The canonical clone lives in root's home, so
   the launch command only works when the distribution's default user is
   root; an existing `[user]` section is reported and left alone. The change
   takes effect after `wsl --terminate Ubuntu` from Windows.
4. Installs the Claude Code CLI if absent — the one floating channel, see
   below — and links it into `/usr/local/bin`.
5. Creates `.venv` with Python 3.12 (the full-stack interpreter per
   `docs/RUNTIME_HOST_DECISION.md`), activates it, and hands off to
   `scripts/workstation_setup.sh`, which installs the committed lock and runs
   the validation surface.

## The one floating channel, and why

Every other install above is either an Ubuntu archive package or the
repository's committed lock. The CLI is installed from Anthropic's official
installer at `claude.ai/install.sh`, which is a floating channel: it fetches
whatever Anthropic currently ships. That is accepted deliberately rather than
pinned, because the CLI self-updates after any install — a pinned version
here would document a control that does not exist. The trust boundary does
not move either way: the CLI's publisher is the same vendor whose agent the
launch command hands this host to.

The symlink in step 4 is load-bearing, not cosmetic. `wsl -- <command>` runs
through a non-login shell whose PATH is the WSL default — system directories
only. The installer places the binary in `~/.local/bin` and adds it to PATH
via `~/.profile`, which non-login shells never read. Without the
`/usr/local/bin/claude` link, the launch command fails with
`command not found` while an interactive shell inside the distribution finds
`claude` perfectly — a mismatch worth documenting once instead of
rediscovering.

## First launch

The first `wsl -d Ubuntu --cd /root/Joeyyy -- claude` asks you to
authenticate and to trust the folder; later launches drop straight in. From
there, `docs/MONDAY_ACTIVATION_RUNBOOK.md` is the operating guide. Validation
commands run inside the virtual environment — `. .venv/bin/activate` first.

## What this does not authorize

The same boundaries as `scripts/workstation_setup.sh`, restated because a
provisioning script is where boundary creep would be quietest: no credential
is created, stored, or read; no `require_grant` mount becomes reachable — that
still takes a Joe-signed, single-use grant through
`scripts/trusted_launcher.py`; the trusted-launcher signing key remains a
manual creation outside the repository at mode 0600; and no agent moves out
of `shadow`. A provisioned host is a precondition for earning promotion
evidence, not evidence.

## Rollback

Repository side: revert the commit that added this record. It touched
`scripts/wsl_ubuntu_setup.sh`, this file, `tests/test_wsl_bootstrap.py`, the
index row in `docs/README.md`, the pointer in
`docs/MONDAY_ACTIVATION_RUNBOOK.md`, the suite figures in
`docs/REPOSITORY_OVERVIEW.md`, and the `CHANGELOG.md` entry — nothing else.

Host side, each independently reversible: remove `/usr/local/bin/claude`
only if it is the symlink this setup created — a link into
`/root/.local/bin` — since the script leaves a pre-existing binary or
foreign link alone and removing one of those would destroy an installation
this change never made
(`[ "$(readlink /usr/local/bin/claude)" = /root/.local/bin/claude ] && rm /usr/local/bin/claude`);
`rm -rf /root/Joeyyy/.venv` removes the environment. The `[user]` section:
only if the setup appended it — it prints a notice when it does, and reports
an existing section untouched — delete that appended block from
`/etc/wsl.conf` (then `wsl --terminate` the distribution) to restore the
previous default user; a section the setup left alone is your configuration,
not this change's, and stays. Full teardown is
`wsl --unregister <distribution>` from Windows — `Ubuntu` in the canonical
path, and whichever distribution you actually provisioned otherwise —
destructive to that distribution's entire disk, including anything in it
that never reached this repository, so it is a deliberate last step, not a
cleanup.
