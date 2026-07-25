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

import json
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
            """Open a span and mirror its final attribute set to the ledger.

            The identical key set lands on the span and on the durable
            record, so a span and its ledger entry match each other and
            both group back to the mission. The ledger write happens in a
            finally block, so a rejection that raises is still recorded.
            """
            record = {k: v for k, v in attributes.items() if v is not None}
            with self.tracer.start_as_current_span(name) as span:
                for key, value in record.items():
                    span.set_attribute(key, str(value))

                class _Recorder:
                    @staticmethod
                    def set(key: str, value: Any) -> None:
                        if value is None:
                            return
                        span.set_attribute(key, str(value))
                        record[key] = value

                try:
                    yield _Recorder
                finally:
                    if self.ledger is not None:
                        self.ledger.append("span", {"operation": name, **record})

        @staticmethod
        def _keys(packet: dict[str, Any], **extra: Any) -> dict[str, Any]:
            """Correlation keys carried on every record: the mission it
            belongs to, its delegation, the agent, that agent's brain, and
            the record it descends from. Identifiers only — never content.
            """
            return {
                "mission_id": packet.get("mission_id"),
                "resource_id": packet.get("resource_id"),
                "delegation_id": packet.get("delegation_id"),
                "agent": packet.get("agent"),
                "owner_brain": packet.get("owner_brain"),
                **extra,
            }

        def traced_admission(
            self,
            packet: dict[str, Any],
            target: str,
            roster: dict[str, dict[str, Any]],
            guard: PacketGuard,
            **kwargs: Any,
        ) -> None:
            attributes = self._keys(
                packet,
                mode=packet.get("mode"),
                target=target,
                parent_id=packet.get("mission_id"),
            )
            with self._span("delegation.admission", attributes) as record:
                try:
                    admit_delegation(
                        packet, target, roster, guard, self.ledger, **kwargs
                    )
                    record.set("outcome", "admitted")
                except HandoffRejected as rejection:
                    record.set("outcome", "rejected")
                    record.set("errors", "; ".join(rejection.errors))
                    raise

        def traced_return(
            self,
            handoff_packet: dict[str, Any],
            guard: PacketGuard,
            **kwargs: Any,
        ) -> list[str]:
            attributes = self._keys(
                handoff_packet,
                status=handoff_packet.get("status"),
                parent_id=handoff_packet.get("delegation_id"),
            )
            with self._span("specialist.return", attributes) as record:
                errors = validate_specialist_return(
                    handoff_packet, guard, self.ledger, **kwargs
                )
                record.set("outcome", "valid" if not errors else "invalid")
                return errors

        def weekly_review(
            self, since: str | None = None, until: str | None = None
        ) -> dict[str, Any]:
            """Aggregate the audit's evidence over a stated date window.

            Reads the durable ledger when one is attached, so a review
            spanning a week of separate runs actually sums — reading the
            in-process exporter would only ever see its own run. The
            window is reported alongside every count so a number can never
            be read as covering more than it does. An empty window is
            reported as empty, never as zeros.
            """
            records: list[dict[str, Any]] = []
            if self.ledger is not None and self.ledger.path.exists():
                source = "ledger"
                for raw in self.ledger.path.read_text(encoding="utf-8").splitlines():
                    if not raw.strip():
                        continue
                    entry = json.loads(raw)
                    if entry.get("event") != "span":
                        continue
                    at = entry.get("at", "")
                    if since and at < since:
                        continue
                    if until and at > until:
                        continue
                    records.append({"at": at, **entry.get("detail", {})})
            else:
                source = "memory"
                for span in self.exporter.get_finished_spans():
                    records.append({
                        "operation": span.name,
                        **{k: v for k, v in dict(span.attributes or {}).items()},
                    })

            summary: dict[str, Any] = {
                "source": source,
                "window": {"since": since, "until": until},
                "total_records": len(records),
                "by_outcome": {},
                "by_brain": {},
                "rejections": [],
            }
            if not records:
                summary["note"] = "no records in window"
                return summary
            for record in records:
                outcome = record.get("outcome", "?")
                key = f"{record.get('operation', '?')}:{outcome}"
                summary["by_outcome"][key] = summary["by_outcome"].get(key, 0) + 1
                brain = record.get("owner_brain", "unknown")
                summary["by_brain"][brain] = summary["by_brain"].get(brain, 0) + 1
                if outcome in ("rejected", "invalid"):
                    summary["rejections"].append({
                        "mission_id": record.get("mission_id"),
                        "target": record.get("target") or record.get("agent"),
                        "owner_brain": record.get("owner_brain"),
                        "errors": record.get("errors"),
                    })
            return summary
