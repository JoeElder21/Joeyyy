"""Mission observability: OpenTelemetry spans over governed operations.

Incorporates the observability tier (opentelemetry-sdk now; arize-phoenix
at activation — pinned in requirements/runtime-observability.txt) so the
weekly audit reviews real traces instead of reconstructed narratives.

`MissionTracer` wraps the governed operations (admission, specialist
return) in spans carrying packet metadata — never packet content or
credentials — alongside the hash-chained audit ledger. Offline today via
an in-memory exporter; pointing the provider at a Phoenix collector
(`arize-phoenix-otel`) is the activation step and changes no call sites.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any

from scripts.agent_runtime import (
    AuditLedger,
    HandoffRejected,
    admit_delegation,
    validate_specialist_return,
)
from scripts.packet_guard import PacketGuard

ROOT = Path(__file__).resolve().parents[1]

try:  # degrade cleanly when the runtime stack is not installed
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised in stdlib CI
    OTEL_AVAILABLE = False


if OTEL_AVAILABLE:

    class MissionTracer:
        """Spans + audit ledger around governed operations.

        With no exporter argument, spans collect in memory (offline,
        inspectable for the weekly review). At activation, pass the
        Phoenix-registered provider instead; call sites are unchanged.
        """

        def __init__(self, ledger: AuditLedger | None = None, exporter=None):
            self.exporter = exporter or InMemorySpanExporter()
            provider = TracerProvider()
            provider.add_span_processor(SimpleSpanProcessor(self.exporter))
            self.tracer = provider.get_tracer("agent007.missions")
            self.ledger = ledger

        @contextmanager
        def _span(self, name: str, attributes: dict[str, Any]):
            with self.tracer.start_as_current_span(name) as span:
                for key, value in attributes.items():
                    if value is not None:
                        span.set_attribute(key, str(value))
                yield span

        def traced_admission(
            self,
            packet: dict[str, Any],
            target: str,
            roster: dict[str, dict[str, Any]],
            guard: PacketGuard,
            **kwargs: Any,
        ) -> None:
            attributes = {
                "packet.delegation_id": packet.get("delegation_id"),
                "packet.mode": packet.get("mode"),
                "handoff.target": target,
            }
            with self._span("delegation.admission", attributes) as span:
                try:
                    admit_delegation(
                        packet, target, roster, guard, self.ledger, **kwargs
                    )
                    span.set_attribute("outcome", "admitted")
                except HandoffRejected as rejection:
                    span.set_attribute("outcome", "rejected")
                    span.set_attribute("errors", "; ".join(rejection.errors))
                    raise

        def traced_return(
            self,
            handoff_packet: dict[str, Any],
            guard: PacketGuard,
            **kwargs: Any,
        ) -> list[str]:
            attributes = {
                "packet.delegation_id": handoff_packet.get("delegation_id"),
                "packet.status": handoff_packet.get("status"),
                "handoff.agent": handoff_packet.get("agent"),
            }
            with self._span("specialist.return", attributes) as span:
                errors = validate_specialist_return(
                    handoff_packet, guard, self.ledger, **kwargs
                )
                span.set_attribute("outcome", "valid" if not errors else "invalid")
                return errors

        def weekly_review(self) -> dict[str, Any]:
            """Aggregate captured spans for the weekly audit: counts by
            operation and outcome, plus every rejection's recorded errors."""
            spans = self.exporter.get_finished_spans()
            summary: dict[str, Any] = {"total_spans": len(spans), "by_outcome": {}}
            rejections = []
            for span in spans:
                key = f"{span.name}:{span.attributes.get('outcome', '?')}"
                summary["by_outcome"][key] = summary["by_outcome"].get(key, 0) + 1
                if span.attributes.get("outcome") == "rejected":
                    rejections.append({
                        "target": span.attributes.get("handoff.target"),
                        "errors": span.attributes.get("errors"),
                    })
            summary["rejections"] = rejections
            return summary
