"""Typed packet models generated from the canonical JSON schemas.

Incorporates pydantic (pinned in requirements/runtime-contracts.txt) as the
typed in-Python face of the packet contracts. The JSON schemas in schemas/
remain the single source of truth: every model here is built dynamically from
its schema at import time with pydantic.create_model, never hand-written, so
the models cannot drift from the contracts.

Division of labor: pydantic enforces shape (field presence, base types, no
extra fields) and gives IDE typing and coercion; PacketGuard remains the
authority on relational rules (leases, brain locks, evidence, legacy gating).
`validate_with_guard()` runs both.

Degrades cleanly: without pydantic installed the module still imports and
exposes the raw schemas; model classes are simply absent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.packet_guard import PacketGuard

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"

MODEL_SCHEMAS = {
    "DelegationPacket": "delegation_packet.schema.json",
    "HandoffPacket": "handoff_packet.schema.json",
    "WriterLease": "writer_lease.schema.json",
    "MutationResult": "mutation_result.schema.json",
    "RoundtableMemo": "roundtable_memo.schema.json",
    "MemoryRecord": "memory_record.schema.json",
    "CrossBrainConstraintPacket": "cross_brain_constraint_packet.schema.json",
    "BrainPrivateConstraintPacket": "brain_private_constraint_packet.schema.json",
}


def load_schema(schema_name: str) -> dict[str, Any]:
    with (SCHEMA_DIR / schema_name).open("r", encoding="utf-8") as source:
        return json.load(source)


try:  # degrade cleanly when the runtime stack is not installed
    from pydantic import BaseModel, ConfigDict, create_model

    PYDANTIC_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised in stdlib CI
    PYDANTIC_AVAILABLE = False


if PYDANTIC_AVAILABLE:

    _TYPE_MAP = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
        "null": type(None),
    }

    def _python_type(spec: dict[str, Any]) -> Any:
        declared = spec.get("type")
        if isinstance(declared, list):
            kinds = [_TYPE_MAP.get(item, Any) for item in declared]
            joined = kinds[0]
            for kind in kinds[1:]:
                joined = joined | kind
            return joined
        if isinstance(declared, str):
            return _TYPE_MAP.get(declared, Any)
        if "enum" in spec or "const" in spec:
            return Any
        return Any

    class GovernedPacket(BaseModel):
        """Base class: shape-valid packet that can request full governance."""

        model_config = ConfigDict(extra="forbid")

        __schema_name__: str = ""

        def validate_with_guard(
            self, guard: PacketGuard | None = None, **kwargs: Any
        ) -> list[str]:
            """Run PacketGuard's relational validation on this packet."""
            guard = guard or PacketGuard(ROOT)
            return guard.validate(self.__schema_name__, self.model_dump(), **kwargs)

    def _model_from_schema(model_name: str, schema_name: str) -> type[GovernedPacket]:
        schema = load_schema(schema_name)
        required = set(schema.get("required", []))
        fields: dict[str, Any] = {}
        for field_name, spec in schema.get("properties", {}).items():
            annotation = _python_type(spec)
            if field_name in required:
                fields[field_name] = (annotation, ...)
            else:
                fields[field_name] = (annotation | None, None)
        model = create_model(model_name, __base__=GovernedPacket, **fields)
        model.__schema_name__ = schema_name
        return model

    _generated = {
        model_name: _model_from_schema(model_name, schema_name)
        for model_name, schema_name in MODEL_SCHEMAS.items()
    }
    DelegationPacket = _generated["DelegationPacket"]
    HandoffPacket = _generated["HandoffPacket"]
    WriterLease = _generated["WriterLease"]
    MutationResult = _generated["MutationResult"]
    RoundtableMemo = _generated["RoundtableMemo"]
    MemoryRecord = _generated["MemoryRecord"]
    CrossBrainConstraintPacket = _generated["CrossBrainConstraintPacket"]
    BrainPrivateConstraintPacket = _generated["BrainPrivateConstraintPacket"]

    def parse_packet(schema_name: str, data: dict[str, Any]) -> GovernedPacket:
        """Parse raw data into the typed model for the given schema."""
        for model_name, candidate in MODEL_SCHEMAS.items():
            if candidate == schema_name:
                return _generated[model_name].model_validate(data)
        raise KeyError(f"no model registered for schema {schema_name!r}")
