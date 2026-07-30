"""The instruction issuer must produce grants the enforcement point accepts.

A grant that the boundary rejects is worse than no issuer at all: the operator
holds a signed authorization, the gate refuses it, and the reasonable
conclusion is that the gate is broken. So the binding assertion here is
end-to-end -- issue a grant, hand it to `_high_impact_boundary`, and require
that the action is permitted.
"""

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.issue_instruction import (  # noqa: E402
    DEFAULT_INSTRUCTION_MINUTES,
    MAX_INSTRUCTION_MINUTES,
    InstructionRefused,
    issue_instruction,
    main,
)
from scripts.policy_enforcement import (  # noqa: E402
    CHIEF,
    HIGH_IMPACT_ACTIONS,
    PolicyEnforcementPoint,
    ToolRequest,
)
from tests.test_policy_enforcement import NOW, registry_and_lease  # noqa: E402

RESOURCE = "APEX/Strategy-Campaigns"


class IssuedGrantSatisfiesTheBoundaryTests(unittest.TestCase):
    """The property the issuer exists for, asserted through the rule itself."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.key = Path(self.tmp.name) / "launch_key"
        self.key.write_bytes(b"test-signing-key")
        self.key.chmod(0o600)
        self.out = Path(self.tmp.name) / "instructions"
        registry, _ = registry_and_lease()
        self.pep = PolicyEnforcementPoint(
            ROOT, registry=registry, launch_key_path=self.key, clock=lambda: NOW
        )

    def _request(self, action, grant=None, resource=RESOURCE):
        return ToolRequest(
            agent=CHIEF,
            action=action,
            resource=resource,
            owner_brain="APEX",
            mutating=True,
            instruction_grant=grant,
        )

    def _issue(self, action, resource=RESOURCE, **kwargs):
        kwargs.setdefault("now", NOW.timestamp())
        path = issue_instruction(action, resource, key_path=self.key, out_dir=self.out, **kwargs)
        return json.loads(path.read_text(encoding="utf-8")), path

    def test_without_a_grant_the_action_is_refused(self):
        # The control. Without it, "the grant was accepted" says nothing --
        # the boundary might not have been objecting in the first place.
        self.assertTrue(self.pep._high_impact_boundary(self._request("publishReport")))

    def test_an_issued_grant_is_accepted_by_the_boundary(self):
        grant, _ = self._issue("publishReport")
        self.assertEqual(self.pep._high_impact_boundary(self._request("publishReport", grant)), [])

    def test_every_boundary_category_can_be_authorized(self):
        # One category left unissuable is one act Joe cannot authorize, and it
        # would be found only when he tried. Derived from HIGH_IMPACT_ACTIONS
        # rather than a hand-picked example.
        for category in sorted(HIGH_IMPACT_ACTIONS):
            with self.subTest(category=category):
                grant, _ = self._issue(category)
                self.assertEqual(self.pep._high_impact_boundary(self._request(category, grant)), [])

    def test_the_grant_records_the_category_not_the_raw_verb(self):
        grant, _ = self._issue("publishReport")
        self.assertEqual(grant["action"], "public_publication")

    def test_a_grant_does_not_authorize_another_resource(self):
        grant, _ = self._issue("publishReport", resource=RESOURCE)
        errors = self.pep._high_impact_boundary(
            self._request("publishReport", grant, resource="APEX/Roundtable")
        )
        self.assertTrue(errors, "an instruction was replayed against another target")

    def test_a_grant_does_not_authorize_another_category(self):
        grant, _ = self._issue("publishReport")
        errors = self.pep._high_impact_boundary(self._request("transfer_funds", grant))
        self.assertTrue(errors, "a publication instruction authorized a transaction")

    def test_an_expired_grant_is_refused(self):
        grant, _ = self._issue("publishReport", minutes=1, now=NOW.timestamp() - 3600)
        self.assertTrue(self.pep._high_impact_boundary(self._request("publishReport", grant)))

    def test_a_grant_signed_with_another_key_is_refused(self):
        # The issuer must not be usable as a way to mint authority for a gate
        # holding a different key -- and, read the other way, a grant from
        # anyone else's key must not pass this gate.
        other = Path(self.tmp.name) / "other_key"
        other.write_bytes(b"a-different-signing-key")
        other.chmod(0o600)
        grant, _ = self._issue("publishReport")
        foreign = issue_instruction(
            "publishReport",
            RESOURCE,
            key_path=other,
            out_dir=self.out,
            now=NOW.timestamp(),
        )
        errors = self.pep._high_impact_boundary(
            self._request("publishReport", json.loads(foreign.read_text(encoding="utf-8")))
        )
        self.assertTrue(any("signature" in error for error in errors), errors)


class IssuanceRefusalTests(unittest.TestCase):
    """What the issuer must not mint. One variable at a time.

    The first version of this probe varied the action AND the window together,
    so every case refused for the window and the action check was never
    exercised -- a construction that would have reported a working refusal for
    a check that did nothing.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.key = Path(self.tmp.name) / "launch_key"
        self.key.write_bytes(b"test-signing-key")
        self.key.chmod(0o600)
        self.out = Path(self.tmp.name) / "instructions"

    def _issue(self, **kwargs):
        kwargs.setdefault("action", "publishReport")
        kwargs.setdefault("resource", RESOURCE)
        return issue_instruction(key_path=self.key, out_dir=self.out, **kwargs)

    def test_the_lawful_case_is_issued(self):
        # The control for every refusal below.
        self.assertTrue(self._issue().exists())

    def test_a_non_boundary_action_is_refused(self):
        # Issuing a meaningless grant for `read` would teach the operator that
        # minting instructions is routine, and the entire value of this
        # boundary is that it is not.
        for action in ("read", "append_record", "validate_packet"):
            with self.subTest(action=action), self.assertRaises(InstructionRefused) as raised:
                self._issue(action=action)
            self.assertIn("not a high-impact boundary", str(raised.exception))

    def test_a_resource_outside_the_tree_is_refused(self):
        for resource in ("C:..\\secret.txt", "../outside", "//host/share"):
            with self.subTest(resource=resource), self.assertRaises(InstructionRefused):
                self._issue(resource=resource)

    def test_an_unbounded_window_is_refused(self):
        for minutes in (0, -5, MAX_INSTRUCTION_MINUTES + 1, 1440):
            with self.subTest(minutes=minutes), self.assertRaises(InstructionRefused) as raised:
                self._issue(minutes=minutes)
            self.assertIn("standing authorization", str(raised.exception))

    def test_the_ceiling_itself_is_allowed(self):
        # A boundary condition asserted in both directions: the ceiling is a
        # ceiling, not one past it.
        self.assertTrue(self._issue(minutes=MAX_INSTRUCTION_MINUTES).exists())

    def test_a_boolean_is_not_a_window(self):
        # `True` is 1 under `isinstance(x, int)`, so it would otherwise mint a
        # one-minute grant from what is plainly a caller error.
        with self.assertRaises(InstructionRefused):
            self._issue(minutes=True)

    def test_an_empty_action_or_resource_is_refused(self):
        for kwargs in ({"action": "  "}, {"resource": ""}, {"action": None}, {"resource": None}):
            with self.subTest(kwargs=kwargs), self.assertRaises(InstructionRefused):
                self._issue(**kwargs)

    def test_the_default_window_is_within_the_ceiling(self):
        self.assertLessEqual(DEFAULT_INSTRUCTION_MINUTES, MAX_INSTRUCTION_MINUTES)
        self.assertGreater(DEFAULT_INSTRUCTION_MINUTES, 0)


class KeyCustodyTests(unittest.TestCase):
    """The issuer must exercise Joe's authority, never manufacture it."""

    def test_a_missing_signing_key_refuses_rather_than_creating_one(self):
        # `_load_or_create_key` mints a key on first use. Using it here meant
        # any process able to WRITE the key path could create a key and then
        # sign grants the enforcement point accepts -- bootstrapping the
        # authority the boundary exists to reserve. `trusted_launcher.authorize`
        # already refuses when no key exists; the issuer must not undercut it.
        with tempfile.TemporaryDirectory() as tmp:
            absent = Path(tmp) / "no_such_key"
            with self.assertRaises(InstructionRefused) as raised:
                issue_instruction(
                    "publishReport", RESOURCE, key_path=absent, out_dir=Path(tmp) / "i"
                )
            self.assertIn("no signing key", str(raised.exception))
            self.assertFalse(absent.exists(), "the issuer created a signing key")

    def test_the_cli_offers_no_confirmation_skip_flag(self):
        # `--yes` was an escape hatch through the only confirmation there is:
        # an unattended process can allocate a pseudo-terminal, satisfy
        # isatty(), pass the flag, and mint a grant with nobody present. A
        # control with an opt-out is the caller-set-boolean defect wearing a
        # different costume, and this module removed three of those.
        source = (ROOT / "scripts" / "issue_instruction.py").read_text(encoding="utf-8")
        self.assertNotIn('"--yes"', source)
        self.assertNotIn("args.yes", source)

    def test_the_cli_refuses_without_a_terminal(self):
        # An unattended agent process running under the same account must not
        # be able to mint a publication or transaction grant. This does not
        # prove the human is Joe -- nothing here can -- and the real bound is
        # key custody, which is recorded as Joe's open decision.
        self.assertEqual(
            main(["--action", "publishReport", "--resource", RESOURCE]),
            2,
            "the CLI minted an instruction from a non-interactive process",
        )


class GrantFileTests(unittest.TestCase):
    """A written authorization is a credential on disk."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.key = Path(self.tmp.name) / "launch_key"
        self.key.write_bytes(b"test-signing-key")
        self.key.chmod(0o600)
        self.out = Path(self.tmp.name) / "instructions"

    def test_the_grant_file_is_not_world_readable(self):
        path = issue_instruction(
            "publishReport", RESOURCE, key_path=self.key, out_dir=self.out, now=NOW.timestamp()
        )
        self.assertEqual(path.stat().st_mode & 0o077, 0, "the grant is readable by other users")

    def test_the_grant_is_created_private_not_tightened_afterwards(self):
        # `write_text()` creates with 0666 & ~umask -- 0644 under the common 0022
        # -- and the old `chmod(0o600)` closed that window only after the signed
        # bearer grant was already on disk and world-readable. A crash between
        # the write and the chmod left it 0644 permanently.
        #
        # Asserted under an explicit permissive umask, because the process umask
        # is what made the old code look correct in a 0077 environment. Restored
        # in a finally: umask is process-global and leaking it would silently
        # change how every later test's files are created.
        original = os.umask(0o022)
        try:
            path = issue_instruction(
                "publishReport",
                RESOURCE,
                key_path=self.key,
                out_dir=self.out,
                now=NOW.timestamp(),
            )
        finally:
            os.umask(original)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        # And the directory, which `mkdir(exist_ok=True)` would otherwise leave
        # at 0755: listing it enumerates the category and nonce prefix of every
        # live authorization even when the contents are unreadable.
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o700)

    def test_an_existing_permissive_directory_is_tightened(self):
        # `mkdir(exist_ok=True)` does not change the mode of a directory it did
        # not create, so a folder made once under a permissive umask stays that
        # way for every grant afterwards.
        self.out.mkdir(mode=0o755)
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o755)
        issue_instruction(
            "publishReport", RESOURCE, key_path=self.key, out_dir=self.out, now=NOW.timestamp()
        )
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o700)

    def test_the_grant_write_refuses_to_clobber_an_existing_path(self):
        # O_EXCL. A nonce collision, or a symlink pre-planted at the predictable
        # path, must fail rather than write Joe's authority through it.
        #
        # The first version of this test called `os.open` on the path ITSELF and
        # asserted FileExistsError -- which tests the standard library, not this
        # module, and passed with O_EXCL removed from the issuer. Pinning the
        # nonce so two issuances collide is what actually exercises the flag.
        from scripts import issue_instruction as module

        original = module.secrets.token_hex
        module.secrets.token_hex = lambda _n: "f" * 32
        try:
            first = issue_instruction(
                "publishReport",
                RESOURCE,
                key_path=self.key,
                out_dir=self.out,
                now=NOW.timestamp(),
            )
            self.assertTrue(first.exists())
            with self.assertRaises(FileExistsError):
                issue_instruction(
                    "publishReport",
                    RESOURCE,
                    key_path=self.key,
                    out_dir=self.out,
                    now=NOW.timestamp(),
                )
        finally:
            module.secrets.token_hex = original

    def test_two_grants_do_not_collide_or_share_a_nonce(self):
        # The nonce is what single-use enforcement will key on once it exists,
        # so a repeated one would silently make two authorizations into one.
        grants = [
            issue_instruction(
                "publishReport",
                RESOURCE,
                key_path=self.key,
                out_dir=self.out,
                now=NOW.timestamp(),
            )
            for _ in range(5)
        ]
        self.assertEqual(len({path.name for path in grants}), 5)
        nonces = {json.loads(path.read_text(encoding="utf-8"))["nonce"] for path in grants}
        self.assertEqual(len(nonces), 5)


class IssuerHonestyTests(unittest.TestCase):
    """The module must not claim a property it does not have."""

    SOURCE = ROOT / "scripts" / "issue_instruction.py"

    def test_replayability_is_stated_not_implied(self):
        # Nonce consumption is a recorded open decision. A tool that issued
        # "single-use" grants without consuming them would be making exactly
        # the impossible claim AGENTS.md forbids.
        text = self.SOURCE.read_text(encoding="utf-8")
        self.assertIn("replayable", text)
        self.assertNotIn("single-use", text.replace("single-use enforcement", ""))


class SigningKeyCustodyTests(unittest.TestCase):
    """A key any local user can read is a key that can forge Joe's authority.

    The check was existence-only. `docs/AGENT_REGISTRY.md:182` states the signing
    key lives outside the repository at `0600`, and nothing verified it -- so a
    key restored from a backup or written under a permissive umask sat at `0644`
    and any other local user could read it and mint grants
    `_high_impact_boundary` accepts. Custody IS the control, and the previous
    round's own note said so while checking only that the file existed.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.out = self.root / "instructions"

    def _key(self, mode):
        key = self.root / f"key_{mode:o}"
        key.write_bytes(b"test-signing-key")
        key.chmod(0o600)
        key.chmod(mode)
        return key

    def _issue(self, key):
        return issue_instruction(
            "publishReport", RESOURCE, key_path=key, out_dir=self.out, now=NOW.timestamp()
        )

    def test_an_owner_only_key_is_accepted(self):
        # The control for every refusal below, and both owner-only modes: 0400 is
        # stricter than the documented 0600 and must not be refused for it.
        for mode in (0o600, 0o400):
            with self.subTest(mode=oct(mode)):
                self.assertTrue(self._issue(self._key(mode)).exists())

    def test_a_world_readable_key_is_refused(self):
        with self.assertRaises(InstructionRefused) as raised:
            self._issue(self._key(0o644))
        message = str(raised.exception)
        self.assertIn("0644", message)
        # The advice matters as much as the refusal: a key that HAS been readable
        # should be rotated, not merely tightened, and only Joe can judge whether
        # the exposure mattered.
        self.assertIn("ROTATE", message)

    def test_a_group_readable_key_is_refused(self):
        # 0640 exposes nothing to "other" and is still wrong on a box with a
        # shared group, which is the normal shape of a shared workstation.
        with self.assertRaises(InstructionRefused):
            self._issue(self._key(0o640))

    def test_a_group_writable_key_is_refused(self):
        # Write access is worse than read: the key can be REPLACED with one the
        # attacker holds, and every grant after that verifies against it.
        with self.assertRaises(InstructionRefused):
            self._issue(self._key(0o620))

    def test_a_symlinked_key_is_refused(self):
        # Judged by lstat, on its own terms rather than its target's. A link is a
        # path another process can repoint between the check and the read.
        target = self._key(0o600)
        link = self.root / "link"
        link.symlink_to(target)
        with self.assertRaises(InstructionRefused) as raised:
            self._issue(link)
        self.assertIn("not a regular file", str(raised.exception))

    def test_a_directory_is_refused_rather_than_read(self):
        directory = self.root / "key_dir"
        directory.mkdir(mode=0o700)
        with self.assertRaises(InstructionRefused):
            self._issue(directory)


# Last statement in the file, deliberately. This guard used to sit mid-module,
# so `python -m tests.test_issue_instruction` called unittest.main() and exited before the
# classes below it were defined -- running a subset and reporting "OK".
# `unittest discover` imports the module rather than executing it as __main__,
# so those tests ran in CI and the gap was invisible there.
if __name__ == "__main__":
    unittest.main()
