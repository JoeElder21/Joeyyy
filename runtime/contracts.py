"""Typed, fail-closed packet boundary helpers for Agent 007 runtimes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel, ConfigDict

ROOT = Path(__file__).resolve().parents[1]


class PacketModel(BaseModel):
    """Strict transport model; schema-specific rules remain the source of truth."""

    model_config = ConfigDict(extra="forbid")


def schema_validator(schema_name: str) -> Draft202012Validator:
    """Load a repository schema and verify it before accepting a packet."""
    path = ROOT / "schemas" / schema_name
    if not path.is_file():
        raise ValueError(f"Unknown packet schema: {schema_name}")
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def structural_errors(schema_name: str, packet: Any) -> list[str]:
    """Return every JSON Schema failure in stable path order."""
    return [
        f"{error.json_path}: {error.message}"
        for error in sorted(schema_validator(schema_name).iter_errors(packet), key=lambda item: list(item.path))
    ]


def validate_packet(schema_name: str, packet: Any, **ledgers: Any) -> None:
    """Apply JSON Schema validation then Agent 007 relational PacketGuard checks."""
    errors = structural_errors(schema_name, packet)
    if errors:
        raise ValueError("; ".join(errors))
    # Import lazily so this module stays usable by external runtimes with only schemas.
    from scripts.packet_guard import PacketGuard

    relational_errors = PacketGuard(ROOT).validate(schema_name, packet, **ledgers)
    if relational_errors:
        raise ValueError("; ".join(relational_errors))
