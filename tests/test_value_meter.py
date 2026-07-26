"""Behavioral tests for the value meter, including the refusals that matter.

Most of these assert that the meter says *no*. A value system that only knows how
to produce a favourable number is the failure mode AGENTS.md section 17 exists to
prevent, so the refusal paths carry more coverage than the happy path.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from runtime.value_meter import (
    POLICY_PATH,
    VERDICT_BELOW,
    VERDICT_BLOCKED,
    VERDICT_DEMOTE,
    VERDICT_INSUFFICIENT,
    VERDICT_MEETS,
    ObservationRejected,
    ValueLedger,
    ValuePolicy,
    build_observation,
    evaluate_mode,
)

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)


def payload(**overrides):
    base = {
        "mode": "delivery_control",
        "agent": "apex_delivery_commander",
        "mission_id": "M-TEST",
        "observed_at": NOW.isoformat(),
        "baseline_minutes": 60,
        "baseline_source": "joe_declared",
        "agent_minutes": 2.0,
        "review_minutes": 5.0,
        "correction_minutes": 1.0,
        "incident_minutes": 0.0,
        "maintenance_share_minutes": 1.0,
        "accepted_first_pass": True,
    }
    base.update(overrides)
    return base


class PolicyLoadingTests(unittest.TestCase):
    def test_policy_loads_from_the_repository_and_binds_35_percent(self):
        policy = ValuePolicy.load()
        self.assertEqual(policy.min_net_time_saved_ratio, 0.35)
        self.assertGreaterEqual(policy.min_observations, 2)
        self.assertTrue(POLICY_PATH.is_file())

    def test_threshold_is_not_relaxable_without_a_reviewed_exception_entry(self):
        policy = ValuePolicy.load()
        # No exceptions are declared, so every mode gets the binding threshold.
        self.assertEqual(policy.exceptions, {})
        for mode in ("delivery_control", "daily_capacity", "anything_at_all"):
            with self.subTest(mode=mode):
                self.assertEqual(policy.threshold_for(mode), 0.35)

    def test_declared_only_baselines_are_not_treated_as_measured(self):
        policy = ValuePolicy.load()
        # daily_capacity carries a manifest_declared baseline, which is a design
        # intent rather than an observation of Joe, so it is not usable.
        self.assertIsNone(policy.usable_baseline("daily_capacity"))
        self.assertIsNone(policy.usable_baseline("delivery_control"))


class ObservationRefusalTests(unittest.TestCase):
    def setUp(self):
        self.policy = ValuePolicy.load()

    def test_missing_cost_term_is_refused_not_defaulted_to_zero(self):
        for term in self.policy.required_cost_terms:
            with self.subTest(term=term):
                data = payload()
                data.pop(term)
                with self.assertRaises(ObservationRejected) as caught:
                    build_observation(self.policy, data)
                self.assertIn(term, str(caught.exception))

    def test_agent_supplied_baseline_is_refused(self):
        with self.assertRaises(ObservationRejected) as caught:
            build_observation(self.policy, payload(baseline_source="agent_estimated"))
        self.assertIn("may not supply its own baseline", str(caught.exception))

    def test_zero_or_missing_baseline_is_refused(self):
        with self.assertRaises(ObservationRejected):
            build_observation(self.policy, payload(baseline_minutes=0))

    def test_negative_cost_is_refused(self):
        with self.assertRaises(ObservationRejected):
            build_observation(self.policy, payload(review_minutes=-5))


class ArithmeticTests(unittest.TestCase):
    def setUp(self):
        self.policy = ValuePolicy.load()

    def test_review_and_correction_are_subtracted_from_benefit(self):
        obs = build_observation(self.policy, payload())
        # 60 baseline - (2 + 5 + 1 + 0 + 1) = 51 minutes net.
        self.assertAlmostEqual(obs.net_time_saved(self.policy), 51.0)
        self.assertAlmostEqual(obs.ratio(self.policy), 51.0 / 60.0)

    def test_fast_output_that_joe_must_check_can_fail_the_threshold(self):
        # 6 minutes of agent time but 30 minutes of Joe's review: 24/60 = 40%...
        obs = build_observation(
            self.policy,
            payload(agent_minutes=6, review_minutes=30, correction_minutes=0,
                    maintenance_share_minutes=0),
        )
        self.assertAlmostEqual(obs.ratio(self.policy), 24.0 / 60.0)
        # ...and with a little correction burden it drops under the binding 35%.
        worse = build_observation(
            self.policy,
            payload(agent_minutes=6, review_minutes=30, correction_minutes=6,
                    maintenance_share_minutes=0),
        )
        self.assertLess(worse.ratio(self.policy), 0.35)

    def test_rejected_output_carries_full_cost_and_zero_benefit(self):
        obs = build_observation(self.policy, payload(output_rejected=True))
        self.assertAlmostEqual(obs.net_time_saved(self.policy), -9.0)
        self.assertLess(obs.ratio(self.policy), 0)


class VerdictTests(unittest.TestCase):
    def setUp(self):
        self.policy = ValuePolicy.load()

    def observations(self, count, **overrides):
        return [
            build_observation(self.policy, payload(mission_id=f"M-{i}", **overrides))
            for i in range(count)
        ]

    def test_one_good_run_never_proves_value(self):
        verdict = evaluate_mode(
            "delivery_control", self.observations(1), self.policy, now=NOW
        )
        self.assertEqual(verdict.verdict, VERDICT_INSUFFICIENT)
        self.assertFalse(verdict.value_proven)

    def test_enough_strong_observations_meet_the_threshold(self):
        verdict = evaluate_mode(
            "delivery_control",
            self.observations(self.policy.min_observations),
            self.policy,
            now=NOW,
        )
        self.assertEqual(verdict.verdict, VERDICT_MEETS)
        self.assertTrue(verdict.value_proven)
        self.assertGreater(verdict.mean_ratio, 0.35)

    def test_weak_savings_report_below_threshold(self):
        verdict = evaluate_mode(
            "delivery_control",
            self.observations(self.policy.min_observations, review_minutes=40),
            self.policy,
            now=NOW,
        )
        self.assertEqual(verdict.verdict, VERDICT_BELOW)
        self.assertFalse(verdict.value_proven)

    def test_very_weak_savings_demote_a_mode_that_previously_passed(self):
        verdict = evaluate_mode(
            "delivery_control",
            self.observations(self.policy.min_observations, review_minutes=50),
            self.policy,
            now=NOW,
            previously_met=True,
        )
        self.assertEqual(verdict.verdict, VERDICT_DEMOTE)

    def test_a_mode_that_never_passed_is_not_demoted(self):
        """Demotion is a move down from a stage the mode actually reached."""
        verdict = evaluate_mode(
            "delivery_control",
            self.observations(self.policy.min_observations, review_minutes=50),
            self.policy,
            now=NOW,
        )
        self.assertEqual(verdict.verdict, VERDICT_BELOW)
        self.assertIn("nothing to demote it from", " ".join(verdict.reasons))

    def test_low_first_pass_acceptance_blocks_a_pass_on_minutes_alone(self):
        # Strong minutes, but Joe rarely accepts the first answer.
        verdict = evaluate_mode(
            "delivery_control",
            self.observations(self.policy.min_observations, accepted_first_pass=False),
            self.policy,
            now=NOW,
        )
        self.assertEqual(verdict.verdict, VERDICT_BELOW)
        self.assertIn("first-pass", " ".join(verdict.reasons).lower())

    def test_boundary_incident_blocks_any_verdict(self):
        observations = self.observations(self.policy.min_observations)
        observations.append(build_observation(self.policy, payload(boundary_incident=True)))
        verdict = evaluate_mode("delivery_control", observations, self.policy, now=NOW)
        self.assertEqual(verdict.verdict, VERDICT_BLOCKED)
        self.assertFalse(verdict.value_proven)

    def test_stale_observations_fall_out_of_the_window(self):
        old = NOW - timedelta(days=self.policy.observation_window_days + 5)
        stale = [
            build_observation(self.policy, payload(observed_at=old.isoformat()))
            for _ in range(self.policy.min_observations)
        ]
        verdict = evaluate_mode("delivery_control", stale, self.policy, now=NOW)
        self.assertEqual(verdict.verdict, VERDICT_INSUFFICIENT)
        self.assertEqual(verdict.observation_count, 0)


class LedgerTests(unittest.TestCase):
    def test_ledger_round_trips_and_reports(self):
        policy = ValuePolicy.load()
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ValueLedger(Path(tmp) / "value.jsonl")
            for i in range(policy.min_observations):
                ledger.record(build_observation(policy, payload(mission_id=f"M-{i}")))
            report = ledger.report(policy, now=NOW)
            self.assertEqual(report["total_observations"], policy.min_observations)
            self.assertEqual(report["threshold"], 0.35)
            self.assertEqual(report["value_proven_modes"], ["delivery_control"])

    def test_empty_ledger_proves_nothing(self):
        policy = ValuePolicy.load()
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ValueLedger(Path(tmp) / "value.jsonl")
            report = ledger.report(policy, modes=["delivery_control"], now=NOW)
            self.assertEqual(report["total_observations"], 0)
            self.assertEqual(report["value_proven_modes"], [])


if __name__ == "__main__":
    unittest.main()


class MeasurementIntegrityTests(unittest.TestCase):
    """Ways a value verdict could be manufactured without doing the work."""

    def setUp(self):
        self.policy = ValuePolicy.load()

    def test_nan_cost_is_refused(self):
        """NaN passes `< 0` and then fails every threshold comparison, landing on 'meets'."""
        for term in self.policy.required_cost_terms:
            with self.subTest(term=term):
                with self.assertRaises(ObservationRejected):
                    build_observation(self.policy, payload(**{term: float("nan")}))

    def test_infinite_cost_is_refused(self):
        with self.assertRaises(ObservationRejected):
            build_observation(self.policy, payload(agent_minutes=float("inf")))

    def test_nan_baseline_is_refused(self):
        with self.assertRaises(ObservationRejected):
            build_observation(self.policy, payload(baseline_minutes=float("nan")))

    def test_replaying_one_observation_does_not_satisfy_the_count(self):
        """Five copies of one run are one run."""
        replayed = [
            build_observation(self.policy, payload(mission_id="M-SAME"))
            for _ in range(self.policy.min_observations)
        ]
        verdict = evaluate_mode("delivery_control", replayed, self.policy, now=NOW)
        self.assertEqual(verdict.verdict, VERDICT_INSUFFICIENT)
        self.assertEqual(verdict.observation_count, 1)

    def test_future_dated_observations_do_not_count(self):
        ahead = NOW + timedelta(days=400)
        future = [
            build_observation(
                self.policy, payload(mission_id=f"M-{i}", observed_at=ahead.isoformat())
            )
            for i in range(self.policy.min_observations)
        ]
        verdict = evaluate_mode("delivery_control", future, self.policy, now=NOW)
        self.assertEqual(verdict.observation_count, 0)
        self.assertNotEqual(verdict.verdict, VERDICT_MEETS)

    def test_an_incident_does_not_clear_itself_by_ageing_out(self):
        """config/value_policy.toml says an incident blocks until reviewed."""
        old = NOW - timedelta(days=self.policy.observation_window_days + 10)
        observations = [
            build_observation(self.policy, payload(mission_id=f"M-{i}"))
            for i in range(self.policy.min_observations)
        ]
        observations.append(
            build_observation(
                self.policy,
                payload(
                    mission_id="M-INCIDENT",
                    boundary_incident=True,
                    observed_at=old.isoformat(),
                ),
            )
        )
        verdict = evaluate_mode("delivery_control", observations, self.policy, now=NOW)
        self.assertEqual(verdict.verdict, VERDICT_BLOCKED)


class ReportCoverageTests(unittest.TestCase):
    def test_a_fresh_ledger_still_reports_configured_modes(self):
        """Otherwise the documented no_baseline verdict never appears."""
        policy = ValuePolicy.load()
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ValueLedger(Path(tmp) / "value.jsonl")
            report = ledger.report(policy, now=NOW)
            reported = {entry["mode"] for entry in report["modes"]}
            self.assertTrue(reported)
            self.assertTrue(set(policy.baselines).issubset(reported))
            self.assertEqual(report["value_proven_modes"], [])
