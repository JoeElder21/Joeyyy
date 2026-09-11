"""The independent ranking critic: two rounds, evidence-cited, then a verdict.

The critic cannot edit a recommendation; it can only challenge it. The
responder may accept, rebut with evidence, or revise. After the second round
any blocking challenge still open BLOCKS the release. A challenge without an
evidence id is recorded as judgment and cannot block on its own.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

MAX_ROUNDS = 2
UPHELD, REVISED, BLOCKED = "UPHELD", "REVISED", "BLOCKED"
SEVERITIES = ("blocking", "material", "minor")
DISPOSITIONS = ("accept", "rebut", "revise")


@dataclass(frozen=True)
class Challenge:
    target: str
    objection: str
    severity: str
    evidence_ids: tuple[str, ...] = ()

    @property
    def is_judgment(self) -> bool:
        return not self.evidence_ids


@dataclass(frozen=True)
class Response:
    target: str
    disposition: str
    rationale: str
    evidence_ids: tuple[str, ...] = ()


@dataclass
class DebateRecord:
    verdict: str
    rounds: int
    transcript: list[dict] = field(default_factory=list)
    open_blocking: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "rounds": self.rounds,
            "transcript": list(self.transcript),
            "open_blocking": list(self.open_blocking),
        }


CriticFn = Callable[[dict, int], list[Challenge]]
ResponderFn = Callable[[dict, list[Challenge], int], tuple[dict, list[Response]]]


def _validate(challenges: list[Challenge], responses: list[Response]) -> None:
    for challenge in challenges:
        if challenge.severity not in SEVERITIES:
            raise ValueError(f"unknown severity {challenge.severity!r}")
    for response in responses:
        if response.disposition not in DISPOSITIONS:
            raise ValueError(f"unknown disposition {response.disposition!r}")


def run_debate(
    proposal: dict, critic: CriticFn, responder: ResponderFn
) -> tuple[dict, DebateRecord]:
    """Run at most two rounds and return the (possibly revised) proposal and record."""
    record = DebateRecord(UPHELD, 0)
    current = proposal
    revised = False
    open_blocking: dict[str, Challenge] = {}
    for round_number in range(1, MAX_ROUNDS + 1):
        challenges = critic(current, round_number)
        if not challenges:
            record.transcript.append({"round": round_number, "challenges": [], "responses": []})
            record.rounds = round_number
            break
        current, responses = responder(current, challenges, round_number)
        _validate(challenges, responses)
        answered = {r.target: r for r in responses}
        for challenge in challenges:
            response = answered.get(challenge.target)
            if response is not None and response.disposition == "revise":
                revised = True
            resolved = response is not None and (
                response.disposition == "revise"
                or (response.disposition == "rebut" and bool(response.evidence_ids))
            )
            if challenge.severity == "blocking" and not challenge.is_judgment and not resolved:
                open_blocking[challenge.target] = challenge
            elif resolved:
                open_blocking.pop(challenge.target, None)
        record.transcript.append(
            {
                "round": round_number,
                "challenges": [
                    c.__dict__ | {"evidence_ids": list(c.evidence_ids)} for c in challenges
                ],
                "responses": [
                    r.__dict__ | {"evidence_ids": list(r.evidence_ids)} for r in responses
                ],
            }
        )
        record.rounds = round_number
    record.open_blocking = sorted(open_blocking)
    if record.open_blocking:
        record.verdict = BLOCKED
    elif revised:
        record.verdict = REVISED
    else:
        record.verdict = UPHELD
    return current, record
