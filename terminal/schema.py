"""A stdlib-only validator for the terminal's document schemas.

The repository's runtime lock does not carry ``jsonschema``, and the validation
surface must run on a bare Python 3.11. This module implements the subset of
JSON Schema draft-07 the terminal's schemas use: ``type``, ``enum``, ``const``,
``properties``, ``required``, ``additionalProperties``, ``items``, ``minItems``,
``maxItems``, ``minimum``, ``maximum``, ``exclusiveMinimum``,
``exclusiveMaximum``, ``minLength``, ``maxLength``, ``pattern``, ``anyOf``,
``allOf``, ``oneOf`` and local ``$ref`` (``#/definitions/...``).

Anything outside the subset raises rather than silently passing, so a schema
cannot claim a constraint this validator does not enforce.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Any

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
SUPPORTED_KEYWORDS = frozenset(
    {
        "$schema",
        "$id",
        "$ref",
        "title",
        "description",
        "definitions",
        "examples",
        "default",
        "type",
        "enum",
        "const",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "minItems",
        "maxItems",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "pattern",
        "anyOf",
        "allOf",
        "oneOf",
    }
)


class SchemaError(ValueError):
    """Raised by :func:`require` when an instance fails validation."""


@cache
def load_schema(name: str) -> dict[str, Any]:
    """Load ``terminal/schemas/<name>.schema.json``."""
    path = SCHEMA_DIR / f"{name}.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def schema_names() -> list[str]:
    suffix = ".schema.json"
    return sorted(p.name[: -len(suffix)] for p in SCHEMA_DIR.glob(f"*{suffix}"))


def _is_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    raise SchemaError(f"unsupported type keyword {expected!r}")


def _resolve_ref(ref: str, root: dict[str, Any]) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise SchemaError(f"only local $ref is supported, got {ref!r}")
    node: Any = root
    for part in ref[2:].split("/"):
        if not isinstance(node, dict) or part not in node:
            raise SchemaError(f"unresolvable $ref {ref!r}")
        node = node[part]
    return node


def validate(
    instance: Any,
    schema: dict[str, Any],
    root: dict[str, Any] | None = None,
    path: str = "$",
) -> list[str]:
    """Return every violation as ``"<json path>: <message>"``; empty means valid."""
    root = schema if root is None else root
    unknown = set(schema) - SUPPORTED_KEYWORDS
    if unknown:
        raise SchemaError(f"{path}: schema uses unsupported keywords {sorted(unknown)}")
    if "$ref" in schema:
        return validate(instance, _resolve_ref(schema["$ref"], root), root, path)

    errors: list[str] = []
    if "type" in schema:
        expected = schema["type"]
        options = expected if isinstance(expected, list) else [expected]
        if not any(_is_type(instance, option) for option in options):
            errors.append(f"{path}: expected type {expected}, got {type(instance).__name__}")
            return errors
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} is not one of {schema['enum']}")
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected the constant {schema['const']!r}")

    if isinstance(instance, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in instance:
                errors.append(f"{path}: missing required property {name!r}")
        for name, value in instance.items():
            if name in properties:
                errors.extend(validate(value, properties[name], root, f"{path}.{name}"))
            else:
                extra = schema.get("additionalProperties", True)
                if extra is False:
                    errors.append(f"{path}: unexpected property {name!r}")
                elif isinstance(extra, dict):
                    errors.extend(validate(value, extra, root, f"{path}.{name}"))

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: more than {schema['maxItems']} items")
        if "items" in schema:
            for index, item in enumerate(instance):
                errors.extend(validate(item, schema["items"], root, f"{path}[{index}]"))

    if isinstance(instance, int | float) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: {instance} is below the minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: {instance} is above the maximum {schema['maximum']}")
        if "exclusiveMinimum" in schema and instance <= schema["exclusiveMinimum"]:
            errors.append(f"{path}: {instance} is not above {schema['exclusiveMinimum']}")
        if "exclusiveMaximum" in schema and instance >= schema["exclusiveMaximum"]:
            errors.append(f"{path}: {instance} is not below {schema['exclusiveMaximum']}")

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: shorter than {schema['minLength']} characters")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: longer than {schema['maxLength']} characters")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: {instance!r} does not match {schema['pattern']!r}")

    if "allOf" in schema:
        for index, sub in enumerate(schema["allOf"]):
            errors.extend(validate(instance, sub, root, f"{path}<allOf[{index}]>"))
    if "anyOf" in schema:
        branches = [validate(instance, sub, root, path) for sub in schema["anyOf"]]
        if all(branches):
            errors.append(f"{path}: matches none of the anyOf branches")
    if "oneOf" in schema:
        matches = sum(1 for sub in schema["oneOf"] if not validate(instance, sub, root, path))
        if matches != 1:
            errors.append(f"{path}: matches {matches} oneOf branches, expected exactly 1")
    return errors


def require(instance: Any, schema_name: str) -> None:
    """Validate against a named schema and raise :class:`SchemaError` on failure."""
    errors = validate(instance, load_schema(schema_name))
    if errors:
        raise SchemaError(f"{schema_name}: " + "; ".join(errors[:8]))
