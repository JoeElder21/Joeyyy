"""Validate the public integration contracts without installing external packages."""
from __future__ import annotations

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "autogen", "langgraph", "crewai", "prefect", "mem0", "llama_index", "langchain", "jsonschema", "pydantic"
}


def main() -> int:
    with (ROOT / "config" / "framework_integrations.toml").open("rb") as source:
        data = tomllib.load(source)
    integrations = data["integrations"]
    if set(integrations) != EXPECTED:
        raise SystemExit(f"expected integrations {sorted(EXPECTED)}, got {sorted(integrations)}")
    for name, item in integrations.items():
        for field in ("repository", "role", "status", "owner_brain", "validation_gate", "rollback"):
            if not item.get(field):
                raise SystemExit(f"{name}: missing {field}")
        if item["status"] != "configured_not_validated":
            raise SystemExit(f"{name}: unverified integrations must remain configured_not_validated")
    print("framework integration contracts valid: 9 configured, 0 runtime-validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
