"""Tests for the writer-lease registry, mutation admission, and Celery queues."""

from __future__ import annotations

import datetime
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime.writer_lease import (  # noqa: E402
    LeaseError,
    LeaseRegistry,
    MutationAdmission,
    canonical_key,
)

NOW = datetime.datetime(2026, 7, 24, 12, 0, tzinfo=datetime.timezone.utc)


def _issue(registry: LeaseRegistry, **overrides):
    kwargs = dict(
        mission_id="m-001",
        owner_brain="APEX",
        writer_agent="apex_chief_of_staff",
        write_target="APEX/Strategy-Campaigns",
        resource_id="campaign-alpha",
        expected_state="campaign record absent",
        rollback="delete created record",
        now=NOW,
    )
    kwargs.update(overrides)
    return registry.issue(**kwargs)


class CanonicalKeyTests(unittest.TestCase):
    def test_rejects_whitespace_unicode_aliases_and_unknown_brains(self):
        for brain, target, resource in [
            ("APEX", "APEX/Strategy Campaigns", "r"),   # whitespace
            ("APEX", "APEX/Ｓtrategy", "r"),             # fullwidth alias (NFKC changes it)
            ("APEX", "APEX/Stratégy", "r"),              # non-ASCII
            ("BOTH", "X/Y", "r"),                        # unknown brain
            ("APEX", "", "r"),                           # empty part
        ]:
            with self.assertRaises(LeaseError, msg=(brain, target, resource)):
                canonical_key(brain, target, resource)
        self.assertEqual(
            canonical_key("APEX", "APEX/Strategy-Campaigns", "campaign-alpha"),
            "APEX/APEX/Strategy-Campaigns/campaign-alpha",
        )


class LeaseRegistryTests(unittest.TestCase):
    def test_single_active_lease_per_canonical_key_across_missions(self):
        registry = LeaseRegistry()
        _issue(registry)
        with self.assertRaises(LeaseError):
            _issue(registry, mission_id="m-002", writer_agent="apex_systems_blacksmith")
        # A different resource on the same target is a different key: allowed.
        _issue(registry, resource_id="campaign-beta")

    def test_leases_expire_within_24_hours_and_free_the_key(self):
        registry = LeaseRegistry()
        with self.assertRaises(LeaseError):
            _issue(registry, hours=25)
        _issue(registry, hours=24)
        later = NOW + datetime.timedelta(hours=24, minutes=1)
        _issue(registry, mission_id="m-003", now=later)  # old lease expired, key free

    def test_release_verified_requires_confirmed_readback(self):
        registry = LeaseRegistry()
        lease = _issue(registry)
        closed = registry.release(lease["lease_id"], readback_confirmed=True)
        self.assertEqual(closed["status"], "verified")
        self.assertEqual(closed["validation_readback"], "confirmed")

        lease2 = _issue(registry, mission_id="m-004")
        closed2 = registry.release(lease2["lease_id"], readback_confirmed=False)
        self.assertEqual(closed2["status"], "released_unverified")

    def test_lease_dict_carries_every_schema_required_field(self):
        schema = json.loads(
            (ROOT / "schemas" / "writer_lease.schema.json").read_text(encoding="utf-8")
        )
        lease = _issue(LeaseRegistry())
        for field_name in schema["required"]:
            self.assertIn(field_name, lease)


class MutationAdmissionTests(unittest.TestCase):
    def test_mutation_requires_matching_active_lease_and_serializes(self):
        registry = LeaseRegistry()
        admission = MutationAdmission(registry=registry)
        forged = dict(_issue(LeaseRegistry()))  # lease from a different registry
        with self.assertRaises(LeaseError):
            admission.admit(forged)

        lease = _issue(registry, mission_id="m-005")
        key = admission.admit(lease)
        with self.assertRaises(LeaseError):
            admission.admit(lease)  # second in-flight mutation on same key
        closed = admission.complete(key, readback_confirmed=True)
        self.assertEqual(closed["status"], "verified")


@unittest.skipUnless(
    importlib.util.find_spec("celery") is not None, "celery not installed"
)
class LeaseQueueTests(unittest.TestCase):
    def test_eager_queue_runs_admission_and_readback_end_to_end(self):
        from runtime.lease_queue import make_app, queue_name

        bundle = make_app(eager=True)
        lease = bundle["registry"].issue(
            mission_id="m-006",
            owner_brain="APEX",
            writer_agent="apex_chief_of_staff",
            write_target="APEX/Systems-Registry",
            resource_id="sop-001",
            expected_state="sop absent",
            rollback="delete sop record",
            now=NOW,
        )
        self.assertEqual(queue_name(lease), "mut.apex.apex.systems-registry.sop-001")
        outcome = bundle["submit_mutation"](lease, "create SOP record", lambda o: True)
        self.assertEqual(outcome["lease_status"], "verified")
        # Lease is closed: a second mutation without a new lease fails.
        with self.assertRaises(Exception):
            bundle["submit_mutation"](lease, "second write", lambda o: True)


if __name__ == "__main__":
    unittest.main()
