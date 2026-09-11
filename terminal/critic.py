"""The independent ranking critic: two rounds, evidence-cited, then a verdict.

The critic cannot edit a recommendation; it can only challenge it. The
responder may accept, rebut with evidence, or revise. Only a revision or an
evidence-backed rebuttal resolves a challenge: ``accept`` records agreement
without action, so accepting a blocking challenge leaves it open. After the
second round any blocking challenge still open BLOCKS the release. A challenge
without an evidence id is recorded as judgment and cannot block on its own.
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
    open_blocking: dict[tuple[str, str], Challenge] = {}
    for round_number in range(1, MAX_ROUNDS + 1):
        challenges = critic(current, round_number)
        if not challenges:
            record.transcript.append({"round": round_number, "challenges": [], "responses": []})
            record.rounds = round_number
            break
        current, responses = responder(current, challenges, round_number)
        _validate(challenges, responses)
        by_target: dict[str, list[Response]] = {}
        for response in responses:
            by_target.setdefault(response.target, []).append(response)
        seen: dict[str, int] = {}
        for challenge in challenges:
            # Responses answer a target's challenges in order, so two challenges on one
            # target are resolved one by one instead of by a single reply.
            position = seen.get(challenge.target, 0)
            seen[challenge.target] = position + 1
            candidates = by_target.get(challenge.target, [])
            response = candidates[position] if position < len(candidates) else None
            key = (challenge.target, challenge.objection)
            if response is not None and response.disposition == "revise":
                revised = True
            resolved = response is not None and (
                response.disposition == "revise"
                or (response.disposition == "rebut" and bool(response.evidence_ids))
            )
            if challenge.severity == "blocking" and not challenge.is_judgment and not resolved:
                open_blocking[key] = challenge
            elif resolved:
                open_blocking.pop(key, None)
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
    record.open_blocking = sorted(f"{target}: {objection}" for target, objection in open_blocking)
    if record.open_blocking:
        record.verdict = BLOCKED
    elif revised:
        record.verdict = REVISED
    else:
        record.verdict = UPHELD
    return current, record
