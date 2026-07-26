"""Value measurement for governed missions — the enforcement half of AGENTS.md section 17.

Answers one question honestly: **is this actually saving Joe time, net of what it
costs him to supervise?**

The arithmetic is deliberately unflattering. Gross automation time is not savings.
Review, correction, incident response, and amortized maintenance are subtracted,
because Joe pays those minutes too. A mode that "runs in 20 seconds" but takes him
four minutes to check has not saved four minutes.

Refusals are as important as the number:

* A missing cost term is **not** treated as zero — the observation is rejected.
  Defaulting costs to zero is precisely how gross time is passed off as net.
* A baseline the agent invented is refused. Baselines are measured or declared by
  Joe; a runtime that estimates its own baseline is grading its own homework.
* One good run proves nothing (constitution section 13). Below the configured
  observation count the verdict is ``insufficient_data``, never ``meets``.
* A rejected output carries its full cost and zero benefit.
* A boundary incident blocks the verdict outright until reviewed.

Read the policy from ``config/value_policy.toml``; never hardcode a threshold.
"""

from __future__ import annotations

import hashlib
import json
import math
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "value_policy.toml"

VERDICT_MEETS = "meets_threshold"
VERDICT_BELOW = "below_threshold"
VERDICT_DEMOTE = "demote"
VERDICT_INSUFFICIENT = "insufficient_data"
VERDICT_BLOCKED = "blocked_by_incident"
VERDICT_NO_BASELINE = "no_baseline"


class ObservationRejected(ValueError):
    """An observation is unusable and must not silently become a zero-cost datapoint."""


@dataclass(frozen=True)
class ValuePolicy:
    """The reviewed policy. Thresholds come from disk, never from a caller."""

    min_net_time_saved_ratio: float
    min_observations: int
    observation_window_days: int
    demotion_ratio: float
    required_cost_terms: tuple[str, ...]
    baseline_sources: tuple[str, ...]
    rejected_output_counts_as_zero_benefit: bool
    min_first_pass_acceptance: float
    boundary_incident_blocks_verdict: bool
    baselines: dict[str, dict[str, Any]]
    exceptions: dict[str, Any]

    @classmethod
    def load(cls, path: Path = POLICY_PATH) -> "ValuePolicy":
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        threshold = raw["threshold"]
        measurement = raw["measurement"]
        quality = raw["quality"]
        baselines = {entry["mode"]: entry for entry in raw.get("baseline", [])}
        return cls(
            min_net_time_saved_ratio=float(threshold["min_net_time_saved_ratio"]),
            min_observations=int(threshold["min_observations"]),
            observation_window_days=int(threshold["observation_window_days"]),
            demotion_ratio=float(threshold["demotion_ratio"]),
            required_cost_terms=tuple(measurement["required_cost_terms"]),
            baseline_sources=tuple(measurement["baseline_sources"]),
            rejected_output_counts_as_zero_benefit=bool(
                quality["rejected_output_counts_as_zero_benefit"]
            ),
            min_first_pass_acceptance=float(quality["min_first_pass_acceptance"]),
            boundary_incident_blocks_verdict=bool(quality["boundary_incident_blocks_verdict"]),
            baselines=baselines,
            exceptions=dict(raw.get("exceptions", {})),
        )

    def threshold_for(self, mode: str) -> float:
        """The binding ratio for a mode; an exception must be a reviewed table entry."""
        exception = self.exceptions.get(mode)
        if isinstance(exception, dict) and "min_net_time_saved_ratio" in exception:
            return float(exception["min_net_time_saved_ratio"])
        return self.min_net_time_saved_ratio

    def usable_baseline(self, mode: str) -> int | None:
        """Return the baseline minutes only if it is real; ``None`` otherwise."""
        entry = self.baselines.get(mode)
        if not entry:
            return None
        if entry.get("source") not in self.baseline_sources:
            return None
        minutes = int(entry.get("baseline_minutes", 0))
        return minutes if minutes > 0 else None


@dataclass(frozen=True)
class Observation:
    """One measured run of one mode. Every cost term is mandatory."""

    mode: str
    agent: str
    mission_id: str
    observed_at: str
    baseline_minutes: int
    baseline_source: str
    agent_minutes: float
    review_minutes: float
    correction_minutes: float
    incident_minutes: float
    maintenance_share_minutes: float
    accepted_first_pass: bool
    output_rejected: bool = False
    boundary_incident: bool = False
    notes: str = ""
    # Appending a clearance record is how a reviewed incident is resolved.
    # Blocking forever on any historical incident, with no way to clear it,
    # would force a rewrite of an append-only ledger to ever recover.
    clears_incident_for_mission: str = ""
    cleared_by: str = ""

    @property
    def is_clearance(self) -> bool:
        """Administrative clearance records are not measured runs.

        Counting one as an observation let a clearance become the fifth
        favourable sample and produce meets_threshold from four actual runs.
        """
        return bool(self.clears_incident_for_mission)

    @property
    def total_cost_minutes(self) -> float:
        return (
            self.agent_minutes
            + self.review_minutes
            + self.correction_minutes
            + self.incident_minutes
            + self.maintenance_share_minutes
        )

    def net_time_saved(self, policy: ValuePolicy) -> float:
        if self.output_rejected and policy.rejected_output_counts_as_zero_benefit:
            # Zero benefit, full cost: a wrong answer delivered fast is a loss.
            return -self.total_cost_minutes
        return self.baseline_minutes - self.total_cost_minutes

    def ratio(self, policy: ValuePolicy) -> float:
        if self.baseline_minutes <= 0:
            raise ObservationRejected(f"{self.mode}: baseline_minutes must be positive")
        return self.net_time_saved(policy) / self.baseline_minutes

    def to_json(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "agent": self.agent,
            "mission_id": self.mission_id,
            "observed_at": self.observed_at,
            "baseline_minutes": self.baseline_minutes,
            "baseline_source": self.baseline_source,
            "agent_minutes": self.agent_minutes,
            "review_minutes": self.review_minutes,
            "correction_minutes": self.correction_minutes,
            "incident_minutes": self.incident_minutes,
            "maintenance_share_minutes": self.maintenance_share_minutes,
            "accepted_first_pass": self.accepted_first_pass,
            "output_rejected": self.output_rejected,
            "boundary_incident": self.boundary_incident,
            "notes": self.notes,
            "clears_incident_for_mission": self.clears_incident_for_mission,
            "cleared_by": self.cleared_by,
        }


def build_observation(policy: ValuePolicy, payload: dict[str, Any]) -> Observation:
    """Validate a raw payload into an Observation, or refuse it.

    Refusing beats defaulting. A cost term that is absent is unknown, and unknown
    cost silently becoming zero is the single easiest way to fake a value claim.
    """
    missing = [term for term in policy.required_cost_terms if payload.get(term) is None]
    if missing:
        raise ObservationRejected(
            f"{payload.get('mode', '<unknown mode>')}: missing required cost terms: "
            f"{', '.join(sorted(missing))}"
        )

    mode = payload.get("mode")
    if not mode:
        raise ObservationRejected("observation has no mode")

    baseline_source = payload.get("baseline_source")
    if baseline_source not in policy.baseline_sources:
        raise ObservationRejected(
            f"{mode}: baseline_source {baseline_source!r} is not one of "
            f"{list(policy.baseline_sources)}; an agent may not supply its own baseline"
        )

    raw_baseline = float(payload.get("baseline_minutes", 0))
    if not math.isfinite(raw_baseline):
        raise ObservationRejected(f"{mode}: baseline_minutes must be a finite number")
    baseline_minutes = int(raw_baseline)
    if baseline_minutes <= 0:
        raise ObservationRejected(f"{mode}: no usable baseline recorded")

    for term in policy.required_cost_terms:
        try:
            value = float(payload[term])
        except (TypeError, ValueError) as exc:
            # MissionRunner.complete() catches ObservationRejected only. A raw
            # ValueError here aborts the mission before its rejected evidence is
            # written, instead of failing closed through the documented path.
            raise ObservationRejected(
                f"{mode}: {term} is not a number ({payload[term]!r})"
            ) from exc
        # NaN slips past `< 0` because every NaN comparison is false, and a NaN
        # ratio then fails every threshold comparison too, falling through to a
        # "meets_threshold" verdict. Reject non-finite measurements outright.
        if not math.isfinite(value):
            raise ObservationRejected(f"{mode}: {term} must be a finite number")
        if value < 0:
            raise ObservationRejected(f"{mode}: {term} may not be negative")

    for flag in ("accepted_first_pass", "output_rejected", "boundary_incident"):
        if flag in payload and not isinstance(payload[flag], bool):
            # bool("false") is True, so a JSON-ish string would flip a quality
            # gate the payload explicitly set to false.
            raise ObservationRejected(
                f"{mode}: {flag} must be a real boolean, got {type(payload[flag]).__name__}"
            )

    if payload.get("output_rejected") and payload.get("accepted_first_pass"):
        # Three strong runs plus two rejected-but-marked-accepted runs would
        # report 100% acceptance while 40% of outputs were rejected.
        raise ObservationRejected(
            f"{mode}: output_rejected and accepted_first_pass cannot both be true"
        )

    return Observation(
        mode=mode,
        agent=payload.get("agent", "unknown"),
        mission_id=payload.get("mission_id", "unknown"),
        observed_at=payload.get("observed_at") or datetime.now(timezone.utc).isoformat(),
        baseline_minutes=baseline_minutes,
        baseline_source=baseline_source,
        agent_minutes=float(payload["agent_minutes"]),
        review_minutes=float(payload["review_minutes"]),
        correction_minutes=float(payload["correction_minutes"]),
        incident_minutes=float(payload["incident_minutes"]),
        maintenance_share_minutes=float(payload["maintenance_share_minutes"]),
        accepted_first_pass=bool(payload.get("accepted_first_pass", False)),
        output_rejected=bool(payload.get("output_rejected", False)),
        boundary_incident=bool(payload.get("boundary_incident", False)),
        notes=str(payload.get("notes", "")),
        clears_incident_for_mission=str(payload.get("clears_incident_for_mission", "")),
        cleared_by=str(payload.get("cleared_by", "")),
    )


@dataclass
class ModeVerdict:
    """What the evidence actually supports for one mode — no rounding up."""

    mode: str
    verdict: str
    observation_count: int
    threshold: float
    mean_ratio: float | None = None
    mean_net_minutes: float | None = None
    first_pass_acceptance: float | None = None
    reasons: list[str] = field(default_factory=list)

    @property
    def value_proven(self) -> bool:
        return self.verdict == VERDICT_MEETS

    def to_json(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "verdict": self.verdict,
            "observation_count": self.observation_count,
            "threshold": self.threshold,
            "mean_ratio": self.mean_ratio,
            "mean_net_minutes": self.mean_net_minutes,
            "first_pass_acceptance": self.first_pass_acceptance,
            "reasons": self.reasons,
            "value_proven": self.value_proven,
        }


def _within_window(observation: Observation, policy: ValuePolicy, now: datetime) -> bool:
    """Inside the measurement window, and not dated in the future.

    Checking only the lower bound let a clock error or an edited ledger supply
    observations stamped years ahead, which would then stay eligible for that
    whole interval — five of them would prove value before the runs happened.
    """
    try:
        stamp = datetime.fromisoformat(observation.observed_at)
    except ValueError:
        return False
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    if stamp > now:
        return False
    return stamp >= now - timedelta(days=policy.observation_window_days)


def evaluate_mode(
    mode: str,
    observations: Iterable[Observation],
    policy: ValuePolicy,
    now: datetime | None = None,
    previously_met: bool = False,
) -> ModeVerdict:
    """Return the verdict the evidence supports for one mode."""
    now = now or datetime.now(timezone.utc)
    threshold = policy.threshold_for(mode)
    for_mode = [obs for obs in observations if obs.mode == mode]

    # Deduplicate by mission identity. Appending one successful observation five
    # times would otherwise satisfy min_observations from a single real run.
    seen_missions: set[str] = set()
    deduped = []
    for obs in for_mode:
        if obs.mission_id in seen_missions:
            continue
        seen_missions.add(obs.mission_id)
        deduped.append(obs)
    for_mode = deduped

    relevant = [
        obs
        for obs in for_mode
        if _within_window(obs, policy, now) and not obs.is_clearance
    ]

    verdict = ModeVerdict(
        mode=mode,
        verdict=VERDICT_INSUFFICIENT,
        observation_count=len(relevant),
        threshold=threshold,
    )

    # Only claim "no baseline" when the mode has genuinely never been observed.
    # If observations exist but have aged out, the honest answer is that the
    # evidence is stale, not that the baseline is missing.
    if policy.usable_baseline(mode) is None and not for_mode:
        verdict.verdict = VERDICT_NO_BASELINE
        verdict.reasons.append(
            "No usable baseline in config/value_policy.toml and no observations; "
            "Joe must measure or declare the baseline before value can be claimed."
        )
        return verdict

    # An incident blocks until reviewed and cleared. Checking every observation
    # (not just the window) stops it ageing itself out; honouring explicit
    # clearance records stops it blocking forever with no route to recovery.
    cleared = {
        obs.clears_incident_for_mission
        for obs in for_mode
        if obs.clears_incident_for_mission and obs.cleared_by
    }
    unresolved = [
        obs for obs in for_mode if obs.boundary_incident and obs.mission_id not in cleared
    ]
    if policy.boundary_incident_blocks_verdict and unresolved:
        verdict.verdict = VERDICT_BLOCKED
        verdict.reasons.append(
            "A boundary incident was recorded for this mode; no value verdict until reviewed."
        )
        return verdict

    if not relevant:
        if for_mode:
            verdict.reasons.append(
                f"{len(for_mode)} observation(s) exist but all fall outside the "
                f"{policy.observation_window_days}-day window; the evidence is stale."
            )
        else:
            verdict.reasons.append("No observations recorded for this mode.")
        return verdict

    ratios = [obs.ratio(policy) for obs in relevant]
    nets = [obs.net_time_saved(policy) for obs in relevant]
    accepted = sum(1 for obs in relevant if obs.accepted_first_pass)

    verdict.mean_ratio = sum(ratios) / len(ratios)
    verdict.mean_net_minutes = sum(nets) / len(nets)
    verdict.first_pass_acceptance = accepted / len(relevant)

    if len(relevant) < policy.min_observations:
        verdict.reasons.append(
            f"{len(relevant)} observation(s); policy requires {policy.min_observations} "
            "before any verdict other than insufficient_data."
        )
        return verdict

    if verdict.first_pass_acceptance < policy.min_first_pass_acceptance:
        verdict.verdict = VERDICT_BELOW
        verdict.reasons.append(
            f"First-pass acceptance {verdict.first_pass_acceptance:.0%} is below the "
            f"required {policy.min_first_pass_acceptance:.0%}; time saved on output Joe "
            "has to redo is not time saved."
        )
        return verdict

    if verdict.mean_ratio < policy.demotion_ratio:
        # Demotion is a lifecycle move *down* from a stage the mode reached.
        # A brand-new shadow mode has nothing to be demoted from, so weak first
        # results are reported as below-threshold rather than recommending an
        # impossible transition.
        if previously_met:
            verdict.verdict = VERDICT_DEMOTE
            verdict.reasons.append(
                f"Mean net saving {verdict.mean_ratio:.0%} is below the demotion floor "
                f"{policy.demotion_ratio:.0%} after previously meeting the threshold."
            )
        else:
            verdict.verdict = VERDICT_BELOW
            verdict.reasons.append(
                f"Mean net saving {verdict.mean_ratio:.0%} is below the demotion floor "
                f"{policy.demotion_ratio:.0%}, but this mode has never met the "
                "threshold, so there is nothing to demote it from."
            )
        return verdict

    if verdict.mean_ratio < threshold:
        verdict.verdict = VERDICT_BELOW
        verdict.reasons.append(
            f"Mean net saving {verdict.mean_ratio:.0%} is below the binding threshold "
            f"{threshold:.0%}."
        )
        return verdict

    verdict.verdict = VERDICT_MEETS
    verdict.reasons.append(
        f"Mean net saving {verdict.mean_ratio:.0%} over {len(relevant)} observations "
        f"meets the binding {threshold:.0%} threshold, with "
        f"{verdict.first_pass_acceptance:.0%} first-pass acceptance."
    )
    return verdict


def _previously_met(
    mode: str,
    observations: Iterable[Observation],
    policy: ValuePolicy,
    now: datetime | None,
) -> bool:
    """Did this mode ever meet the threshold over an earlier window?

    Reconstructed from the ledger rather than stored, so it survives a fresh
    process and cannot drift from the observations it summarises.
    """
    now = now or datetime.now(timezone.utc)
    history = sorted(
        (obs for obs in observations if obs.mode == mode),
        key=lambda obs: obs.observed_at,
    )
    if len(history) <= policy.min_observations:
        return False
    # Walk earlier prefixes; if any complete prefix met the threshold, the mode
    # reached a stage it can now be demoted from.
    for end in range(policy.min_observations, len(history)):
        prefix = history[:end]
        stamps = [obs.observed_at for obs in prefix]
        try:
            as_of = datetime.fromisoformat(max(stamps))
        except ValueError:
            continue
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        earlier = evaluate_mode(mode, prefix, policy, now=as_of)
        if earlier.verdict == VERDICT_MEETS:
            return True
    return False


class ValueLedger:
    """Append-only JSONL store of observations, with per-line integrity.

    The mission ledger is hash-chained; this one was not, so a structurally
    valid edit to a cost, baseline, acceptance, or incident field would change a
    verdict with no warning at all. Each line now carries a digest over its own
    content, and ``report()`` refuses to issue verdicts over records that fail it.
    """

    def __init__(self, path: Path):
        self.path = path

    @staticmethod
    def _digest(record: dict[str, Any]) -> str:
        body = {key: value for key, value in record.items() if key != "_digest"}
        return hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def integrity_errors(self) -> list[str]:
        """Lines whose contents no longer match their recorded digest."""
        if not self.path.exists():
            return []
        errors: list[str] = []
        for index, raw in enumerate(self.path.read_text(encoding="utf-8").splitlines()):
            raw = raw.strip()
            if not raw:
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError:
                errors.append(f"line {index}: not valid JSON")
                continue
            if not isinstance(record, dict):
                # `[]` is valid JSON. Calling .get() on it raised AttributeError
                # and crashed the report that exists to fail closed.
                errors.append(f"line {index}: record is not a JSON object")
                continue
            recorded = record.get("_digest")
            if not recorded:
                errors.append(f"line {index}: no integrity digest")
            elif recorded != self._digest(record):
                errors.append(f"line {index}: contents do not match digest")
        return errors

    def record(self, observation: Observation) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = observation.to_json()
        payload["_digest"] = self._digest(payload)
        with self.path.open("a", encoding="utf-8") as sink:
            sink.write(json.dumps(payload, sort_keys=True) + "\n")

    def observations(self, policy: ValuePolicy) -> list[Observation]:
        if not self.path.exists():
            return []
        found = []
        for raw in self.path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if raw:
                found.append(build_observation(policy, json.loads(raw)))
        return found

    def report(
        self,
        policy: ValuePolicy,
        modes: Iterable[str] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        integrity = self.integrity_errors()
        if integrity:
            # Fail closed: a tampered or unverifiable value store must not
            # produce a verdict at all.
            return {
                "policy_version": "config/value_policy.toml",
                "threshold": policy.min_net_time_saved_ratio,
                "min_observations": policy.min_observations,
                "total_observations": 0,
                "modes": [],
                "value_proven_modes": [],
                "integrity_errors": integrity,
                "ledger_trustworthy": False,
            }

        observations = self.observations(policy)
        # Deriving targets only from recorded observations meant a fresh ledger
        # reported no modes at all, so the documented `no_baseline` verdict never
        # appeared until after a run. Configured modes are always in scope.
        target_modes = sorted(
            set(modes)
            if modes
            else {o.mode for o in observations} | set(policy.baselines)
        )
        verdicts = []
        for mode in target_modes:
            # Demotion is only reachable when the mode previously passed, so the
            # report has to reconstruct that instead of always passing False —
            # which made `demote` unreachable from the documented path.
            verdicts.append(
                evaluate_mode(
                    mode,
                    observations,
                    policy,
                    now=now,
                    previously_met=_previously_met(mode, observations, policy, now),
                ).to_json()
            )
        return {
            "policy_version": "config/value_policy.toml",
            "threshold": policy.min_net_time_saved_ratio,
            "min_observations": policy.min_observations,
            "total_observations": len(observations),
            "modes": verdicts,
            "value_proven_modes": [v["mode"] for v in verdicts if v["value_proven"]],
            "integrity_errors": [],
            "ledger_trustworthy": True,
        }
