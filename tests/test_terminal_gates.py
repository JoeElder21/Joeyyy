"""Fatal-risk gates for assets and release gates for a run."""

import unittest

from terminal import gates


class GateTests(unittest.TestCase):
    def test_asset_gate_lists_what_failed_and_what_was_checked(self):
        result = gates.asset_gate({"going_concern": True, "honeypot": False})
        self.assertFalse(result.passed)
        self.assertEqual(result.failed, ["going_concern"])
        self.assertEqual(result.checked, ["going_concern", "honeypot"])
        self.assertEqual(len(result.unchecked), len(gates.FATAL_FLAGS) - 2)
        empty = gates.asset_gate({})
        self.assertFalse(empty.passed)
        self.assertEqual(empty.unchecked, sorted(gates.FATAL_FLAGS))
        self.assertTrue(gates.asset_gate(dict.fromkeys(gates.FATAL_FLAGS, False)).passed)
        with self.assertRaises(ValueError):
            gates.asset_gate({"vibes": True})

    def _checks(self, **overrides):
        base = {
            "schema_errors": [],
            "chain_ok": True,
            "page_bytes": 10_000,
            "boards_with_status": {"a": "LIVE"},
            "immutable_violations": [],
            "invariant_failures": [],
            "critic_verdict": "UPHELD",
        }
        return gates.release_gates(**(base | overrides))

    def test_no_boards_is_not_a_labelled_run(self):
        checks = self._checks(boards_with_status={})
        self.assertEqual([c.name for c in checks if not c.passed], ["freshness_labelled"])

    def test_release_gates_pass_together(self):
        checks = self._checks()
        self.assertEqual(len(checks), 7)
        self.assertTrue(gates.all_passed(checks))

    def test_each_release_gate_fails_on_its_own_condition(self):
        failing = {
            "schema": {"schema_errors": ["x"]},
            "run_chain": {"chain_ok": False},
            "size_ceiling": {"page_bytes": gates.HARD_CEILING_BYTES + 1},
            "freshness_labelled": {"boards_with_status": {"a": "unknown"}},
            "recommendations_immutable": {"immutable_violations": ["recommendations/r1"]},
            "invariants": {"invariant_failures": ["schwab pooled"]},
            "critic": {"critic_verdict": ""},
        }
        for name, override in failing.items():
            with self.subTest(gate=name):
                checks = self._checks(**override)
                failed = [c.name for c in checks if not c.passed]
                self.assertEqual(failed, [name])


if __name__ == "__main__":
    unittest.main()
