"""Run manifests, idempotency keys, the hash chain, the writer lock, snapshots."""

import unittest
from datetime import UTC, datetime

from terminal import runs


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


class RunTests(unittest.TestCase):
    def test_idempotency_keys_use_eastern_dates(self):
        self.assertEqual(
            runs.idempotency_key("daily", utc("2026-09-12T02:00:00")), "daily:2026-09-11"
        )
        self.assertEqual(
            runs.idempotency_key("sentinel", utc("2026-09-11T09:26:00")), "sentinel:2026-09-11T05"
        )
        self.assertEqual(
            runs.idempotency_key("chat", utc("2026-09-11T09:26:00"), "v53"), "chat:v53"
        )
        self.assertEqual(
            runs.idempotency_key("weekly", utc("2026-09-11T09:26:00")), "weekly:2026-W37"
        )
        with self.assertRaises(ValueError):
            runs.idempotency_key("chat", utc("2026-09-11T09:26:00"))
        with self.assertRaises(ValueError):
            runs.idempotency_key("hourly", utc("2026-09-11T09:26:00"))
        self.assertEqual(
            runs.run_id("daily", "daily:2026-09-11"), runs.run_id("daily", "daily:2026-09-11")
        )
        self.assertNotEqual(
            runs.run_id("daily", "daily:2026-09-11"), runs.run_id("daily", "daily:2026-09-12")
        )

    def test_run_line_round_trip(self):
        manifest = runs.RunManifest(
            "daily-abc",
            "daily",
            "daily:2026-09-11",
            "DAILY",
            "s",
            "t",
            "r",
            "b" * 64,
            "c" * 64,
            None,
            "PUBLISHED",
            12,
        )
        parsed = runs.parse_run_line(manifest.line())
        self.assertEqual(parsed["run_id"], "daily-abc")
        self.assertEqual(parsed["rows"], 12)
        self.assertEqual(parsed["status"], "PUBLISHED")
        with self.assertRaises(ValueError):
            runs.parse_run_line("nope")

    def test_chain_verification_finds_breaks_and_duplicates(self):
        records = [
            {
                "run_id": "r1",
                "idempotency_key": "daily:1",
                "status": "PUBLISHED",
                "base_sha": "a",
                "result_sha": "b",
            },
            {
                "run_id": "r2",
                "idempotency_key": "daily:2",
                "status": "PUBLISHED",
                "base_sha": "b",
                "result_sha": "c",
            },
            {
                "run_id": "r3",
                "idempotency_key": "daily:3",
                "status": "SKIPPED",
                "base_sha": "zzz",
                "result_sha": "",
            },
            {
                "run_id": "r4",
                "idempotency_key": "daily:2",
                "status": "PUBLISHED",
                "base_sha": "x",
                "result_sha": "d",
            },
        ]
        report = runs.verify_chain(records)
        self.assertFalse(report.ok)
        self.assertEqual(report.duplicates, ["daily:2"])
        self.assertEqual(len(report.breaks), 1)
        self.assertTrue(runs.verify_chain(records[:3]).ok)

    def test_ledger_skips_a_published_key(self):
        ledger = runs.RunLedger()
        first = runs.RunManifest(
            "r1", "daily", "daily:1", "DAILY", "s", "t", status="PUBLISHED", result_sha="abc"
        )
        self.assertEqual(ledger.append(first), "PUBLISHED")
        again = runs.RunManifest("r2", "daily", "daily:1", "DAILY", "s", "t", status="PUBLISHED")
        self.assertEqual(ledger.append(again), "SKIPPED")
        self.assertEqual(ledger.last_published_sha(), "abc")

    def test_lock_is_cooperative_and_expires(self):
        lock = runs.RunLock()
        t0 = utc("2026-09-11T10:00:00")
        self.assertTrue(lock.acquire("a", t0, ttl_seconds=60))
        self.assertFalse(lock.acquire("b", t0))
        self.assertTrue(lock.acquire("a", t0, ttl_seconds=60))
        self.assertEqual(lock.holder(t0), "a")
        self.assertTrue(lock.acquire("b", utc("2026-09-11T10:02:00")))
        lock.release("b")
        self.assertIsNone(lock.holder(t0))

    def test_snapshot_is_self_describing_and_stable(self):
        parts = {"boards/x": {"rows": [1]}, "policy/current": {"v": 1}}
        one = runs.build_snapshot(parts, utc("2026-09-11T10:41:00"), "v1", None)
        two = runs.build_snapshot(dict(parts), utc("2026-09-11T11:00:00"), "v1", None)
        self.assertEqual(one["sha"], two["sha"])
        self.assertEqual(one["generated_at"], "2026-09-11T10:41:00Z")
        self.assertEqual(set(one["parts"]), set(parts))
        three = runs.build_snapshot(parts, utc("2026-09-11T10:41:00"), "v1", "abc")
        self.assertNotEqual(one["sha"], three["sha"])


if __name__ == "__main__":
    unittest.main()
