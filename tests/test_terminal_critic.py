"""The two-round critic protocol."""

import unittest

from terminal import critic


def blocking(target, evidence=("ev-1",)):
    return critic.Challenge(target, "objection", "blocking", tuple(evidence))


class CriticTests(unittest.TestCase):
    def test_no_challenges_is_upheld_in_one_round(self):
        proposal, record = critic.run_debate({"x": 1}, lambda p, r: [], lambda p, c, r: (p, []))
        self.assertEqual(record.verdict, critic.UPHELD)
        self.assertEqual(record.rounds, 1)
        self.assertEqual(proposal, {"x": 1})

    def test_revision_resolves_and_is_recorded(self):
        def critic_fn(proposal, round_number):
            return (
                [critic.Challenge("rec-1", "coverage", "material", ("ev-1",))]
                if round_number == 1
                else []
            )

        def responder(proposal, challenges, round_number):
            return {"x": 2}, [critic.Response("rec-1", "revise", "fixed", ("ev-1",))]

        proposal, record = critic.run_debate({"x": 1}, critic_fn, responder)
        self.assertEqual(record.verdict, critic.REVISED)
        self.assertEqual(record.rounds, 2)
        self.assertEqual(proposal, {"x": 2})

    def test_unresolved_blocking_challenge_blocks_after_two_rounds(self):
        calls = []

        def critic_fn(proposal, round_number):
            calls.append(round_number)
            return [blocking("rec-1")]

        def responder(proposal, challenges, round_number):
            return proposal, [critic.Response("rec-1", "rebut", "no evidence", ())]

        _, record = critic.run_debate({}, critic_fn, responder)
        self.assertEqual(record.verdict, critic.BLOCKED)
        self.assertEqual(record.open_blocking, ["rec-1: objection"])
        self.assertEqual(calls, [1, 2])

    def test_accepting_a_blocking_challenge_does_not_resolve_it(self):
        _, record = critic.run_debate(
            {},
            lambda p, r: [blocking("rec-1")],
            lambda p, c, r: (
                p,
                [critic.Response("rec-1", "accept", "agreed, nothing changed", ())],
            ),
        )
        self.assertEqual(record.verdict, critic.BLOCKED)

    def test_two_challenges_on_one_target_are_resolved_separately(self):
        def critic_fn(proposal, round_number):
            if round_number == 1:
                return [
                    critic.Challenge("rec-1", "sources", "blocking", ("ev-1",)),
                    critic.Challenge("rec-1", "coverage", "blocking", ("ev-2",)),
                ]
            return []

        def responder(proposal, challenges, round_number):
            return proposal, [critic.Response("rec-1", "rebut", "sources are fine", ("ev-9",))]

        _, record = critic.run_debate({}, critic_fn, responder)
        self.assertEqual(record.verdict, critic.BLOCKED)
        self.assertEqual(record.open_blocking, ["rec-1: coverage"])

    def test_rebuttal_with_evidence_resolves(self):
        _, record = critic.run_debate(
            {},
            lambda p, r: [blocking("rec-1")],
            lambda p, c, r: (p, [critic.Response("rec-1", "rebut", "here", ("ev-9",))]),
        )
        self.assertEqual(record.verdict, critic.UPHELD)

    def test_judgment_without_evidence_cannot_block(self):
        _, record = critic.run_debate(
            {}, lambda p, r: [blocking("rec-1", ())], lambda p, c, r: (p, [])
        )
        self.assertEqual(record.verdict, critic.UPHELD)
        self.assertEqual(record.open_blocking, [])

    def test_invalid_severity_or_disposition_raise(self):
        with self.assertRaises(ValueError):
            critic.run_debate(
                {}, lambda p, r: [critic.Challenge("t", "o", "fatal")], lambda p, c, r: (p, [])
            )
        with self.assertRaises(ValueError):
            critic.run_debate(
                {},
                lambda p, r: [blocking("t")],
                lambda p, c, r: (p, [critic.Response("t", "ignore", "")]),
            )


if __name__ == "__main__":
    unittest.main()
