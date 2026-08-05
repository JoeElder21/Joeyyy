"""Drift locks between the WSL layer, the workstation setup, and their runbook.

The launch command `wsl -d Ubuntu --cd /root/Joeyyy -- claude` is a contract
spread across three surfaces: the provisioning script that makes it work, the
runbook that tells Joe to type it, and the index that makes the runbook
findable. Any one of them can be edited alone, which is exactly how a
documented command stops matching the machine it documents.
"""

import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "wsl_ubuntu_setup.sh"
WORKSTATION = ROOT / "scripts" / "workstation_setup.sh"
RUNBOOK = ROOT / "docs" / "WSL_UBUNTU_SETUP.md"
LAUNCH = "wsl -d Ubuntu --cd /root/Joeyyy -- claude"


class WslBootstrapTests(unittest.TestCase):
    def test_script_and_runbook_agree_on_the_launch_command(self) -> None:
        # The command is the deliverable. A script that provisions for one
        # path while the runbook advertises another fails at the last step,
        # on the machine, where no CI run will see it.
        for path in (SCRIPT, RUNBOOK):
            with self.subTest(surface=path.name):
                self.assertIn(LAUNCH, path.read_text(encoding="utf-8"))

    def test_the_wsl_layer_delegates_rather_than_reimplements(self) -> None:
        # workstation_setup.sh is the one place the governed stack is
        # installed from its committed lock, and the CLI installer is this
        # layer's ONLY floating channel — so the WSL layer runs no pip install
        # of any kind, not even a pip self-upgrade, and hands off instead.
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("workstation_setup.sh", text)
        self.assertNotIn("pip install", text)

    def test_both_setup_scripts_fail_fast_and_are_executable(self) -> None:
        # The workstation script had no coverage at all before this module;
        # the WSL script chains to it, so both carry the same floor: strict
        # mode, a bash shebang, and the executable bit.
        for path in (SCRIPT, WORKSTATION):
            text = path.read_text(encoding="utf-8")
            with self.subTest(script=path.name):
                self.assertTrue(text.startswith("#!/usr/bin/env bash"))
                self.assertIn("set -euo pipefail", text)
                self.assertTrue(os.access(path, os.X_OK), f"{path.name} is not executable")

    def test_guards_precede_any_mutation(self) -> None:
        # Refusals must come before apt writes anything: a non-WSL host or a
        # non-root user should exit with the message, not with a half-changed
        # system. Asserted by position, since prose order is the only order a
        # shell script has.
        text = SCRIPT.read_text(encoding="utf-8")
        first_mutation = text.index("apt-get")
        self.assertLess(text.index("/proc/version"), first_mutation)
        self.assertLess(text.index("id -u"), first_mutation)

    def test_the_path_mechanism_is_enforced_not_just_described(self) -> None:
        # The runbook explains that `wsl -- <command>` runs a non-login shell
        # and needs the CLI reachable from /usr/local/bin. The explanation is
        # only true while the script actually creates that link.
        script = SCRIPT.read_text(encoding="utf-8")
        runbook = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("/usr/local/bin/claude", runbook)
        self.assertIn("ln -s", script)
        self.assertIn("/usr/local/bin/claude", script)

    def test_the_floating_channel_is_guarded_and_recorded(self) -> None:
        # claude.ai/install.sh is the one floating install this layer makes.
        # It must stay behind an already-installed guard in the script, and
        # the runbook must record the trust decision — an unrecorded floating
        # channel is how supply-chain posture erodes one convenience at a
        # time.
        script = SCRIPT.read_text(encoding="utf-8")
        runbook = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("claude.ai/install.sh", runbook)
        self.assertIn("claude.ai/install.sh", script)
        self.assertLess(
            script.index("command -v claude"),
            script.index("claude.ai/install.sh"),
            "the installer must run only after checking for an existing CLI",
        )

    def test_the_runbook_is_indexed_and_reachable(self) -> None:
        # A runbook nobody is routed to is dead weight: the docs index and the
        # Monday runbook (the operating doc a fresh workstation reads first)
        # must both point at it.
        for index in ("docs/README.md", "docs/MONDAY_ACTIVATION_RUNBOOK.md"):
            with self.subTest(index=index):
                self.assertIn(
                    "WSL_UBUNTU_SETUP.md",
                    (ROOT / index).read_text(encoding="utf-8"),
                )


if __name__ == "__main__":
    unittest.main()
