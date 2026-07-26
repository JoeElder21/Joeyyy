"""Deterministic packet-validity metric.

The one metric in the contract that needs no model. It runs `PacketGuard` — the
same guard that governs real admission — over the packet a specialist emitted, so
an evaluation and a live handoff are judged by identical rules. A metric that
graded packets by its own reimplemented logic would drift from the runtime and
start certifying packets the runtime would reject.

Ordering matters: this runs *before* any judged metric. A malformed packet is a
structural failure, and paying an LLM judge to grade prose attached to a packet
the runtime would refuse is wasted money and a misleading score.

Importable and runnable with no evaluation runtime and no credential — the same
degradation contract as the rest of `evals/`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.packet_guard import PacketGuard  # noqa: E402

# Which schema a mode's emitted packet is judged against. Specialists return
# handoff packets; the other schemas are reachable through `schema_name`.
DEFAULT_SCHEMA = "handoff_packet.schema.json"


@dataclass(frozen=True)
class PacketVerdict:
    """Score plus the reasons, so a failure is actionable rather than a number."""

    score: float
    errors: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.score >= 1.0

    def reason(self) -> str:
        if self.passed:
            return "packet is schema-valid and consistent with the deployed manifests"
        listed = "; ".join(self.errors[:5])
        more = f" (+{len(self.errors) - 5} more)" if len(self.errors) > 5 else ""
        return f"packet rejected by PacketGuard: {listed}{more}"


def score_packet(
    packet: object,
    *,
    schema_name: str = DEFAULT_SCHEMA,
    guard: PacketGuard | None = None,
    **guard_kwargs: object,
) -> PacketVerdict:
    """Binary by design.

    Packet validity is not a matter of degree — the runtime either admits the
    packet or refuses it. Returning a partial score would let a specialist
    average its way past a boundary the runtime enforces absolutely.
    """
    if packet is None:
        return PacketVerdict(0.0, ("$: specialist emitted no packet",))
    guard = guard or PacketGuard(ROOT)
    errors = tuple(guard.validate(schema_name, packet, **guard_kwargs))
    return PacketVerdict(0.0 if errors else 1.0, errors)


def build_metric(threshold: float = 1.0):
    """Wrap the check as a DeepEval metric when a runtime is present.

    Returns None without deepeval installed, so callers degrade instead of
    failing to import.
    """
    try:
        from deepeval.metrics import BaseMetric
    except ImportError:
        return None

    class PacketValidityMetric(BaseMetric):
        """Deterministic; never calls a model, so it costs nothing to run."""

        def __init__(self, threshold: float = 1.0) -> None:
            self.threshold = threshold
            self.evaluation_model = "deterministic (PacketGuard)"
            self.async_mode = False
            self.strict_mode = True
            self.score = 0.0
            self.reason = ""
            self.success = False

        def measure(self, test_case) -> float:
            meta = getattr(test_case, "additional_metadata", None) or {}
            # The delegations are not optional colour. `PacketGuard` refuses a
            # handoff whose `delegation_id` does not resolve to exactly one
            # validated originating delegation, so scoring the handoff alone
            # rejected every lawful delegated packet as "not uniquely
            # validated" -- a metric that could only ever return zero, which is
            # as useless as one that only ever returns one.
            kwargs = {
                name: meta[name] for name in ("delegations", "active_leases") if meta.get(name)
            }
            verdict = score_packet(meta.get("packet"), **kwargs)
            self.score = verdict.score
            self.reason = verdict.reason()
            self.success = verdict.score >= self.threshold
            return self.score

        async def a_measure(self, test_case) -> float:
            return self.measure(test_case)

        def is_successful(self) -> bool:
            return self.success

        @property
        def __name__(self) -> str:
            return "packet_validity"

    return PacketValidityMetric(threshold=threshold)
