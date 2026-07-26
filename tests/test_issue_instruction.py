"""The instruction issuer must produce grants the enforcement point accepts.

A grant that the boundary rejects is worse than no issuer at all: the operator
holds a signed authorization, the gate refuses it, and the reasonable
conclusion is that the gate is broken. So the binding assertion here is
end-to-end -- issue a grant, hand it to `_high_impact_boundary`, and require
that the action is permitted.
"""

import json
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


class GrantFileTests(unittest.TestCase):
    """A written authorization is a credential on disk."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.key = Path(self.tmp.name) / "launch_key"
        self.out = Path(self.tmp.name) / "instructions"

    def test_the_grant_file_is_not_world_readable(self):
        path = issue_instruction(
            "publishReport", RESOURCE, key_path=self.key, out_dir=self.out, now=NOW.timestamp()
        )
        self.assertEqual(path.stat().st_mode & 0o077, 0, "the grant is readable by other users")

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


if __name__ == "__main__":
    unittest.main()
