"""Validate the public, non-networked ecosystem integration registry."""
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "config" / "ecosystem_runtime.toml"
REQUIRED = {"id", "repository", "role", "stage", "requires_mcp_boundary"}
ALLOWED_STAGES = {"planned", "configured", "shadow", "active", "restricted", "retired"}


def main() -> None:
    with PATH.open("rb") as source:
        config = tomllib.load(source)
    assert config["connector_boundary"] == "mcp_packet_only"
    records = config["integrations"]
    assert len(records) == 15, "All 15 supplied repository integrations must be tracked."
    ids = [record["id"] for record in records]
    assert len(ids) == len(set(ids)), "Integration IDs must be unique."
    for record in records:
        missing = REQUIRED - record.keys()
        assert not missing, f"{record.get('id', '<unknown>')} missing {sorted(missing)}"
        assert record["stage"] in ALLOWED_STAGES
        assert "/" in record["repository"]
        assert isinstance(record["requires_mcp_boundary"], bool)
    print(f"Validated {len(records)} ecosystem integration records; no connector was contacted.")


if __name__ == "__main__":
    main()
