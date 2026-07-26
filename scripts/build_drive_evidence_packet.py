"""Render a credential-free evidence packet for a verified Google Drive connector."""
from pathlib import Path
import argparse
import tomllib

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "ecosystem_runtime.toml"
OUTPUT = ROOT / "docs" / "DRIVE_ECOSYSTEM_EVIDENCE_PACKET.md"


def render() -> str:
    with CONFIG.open("rb") as source:
        config = tomllib.load(source)
    lines = [
        "# Google Drive Evidence Packet — Ecosystem Runtime",
        "",
        "This credential-free packet is the exact record to upload through the **verified Google Drive MCP server** to the configured evidence target. It has not been uploaded and is intentionally not an assertion that Drive access or an upload occurred.",
        "",
        f"- Intended target: `{config['drive_evidence_target']}`.",
        f"- Connector boundary: `{config['connector_boundary']}`.",
        "- Credentials, Drive IDs, customer data, and connector identifiers are excluded from this public repository.",
        "",
        "## Integration inventory",
        "",
        "| ID | Repository | Role | Lifecycle stage | MCP boundary required |",
        "| --- | --- | --- | --- | --- |",
    ]
    for record in config["integrations"]:
        lines.append("| {id} | `{repository}` | {role} | {stage} | {requires_mcp_boundary} |".format(**record))
    lines += [
        "",
        "## Activation evidence required",
        "",
        "Before any record may move to `active`, capture a dated deployment record, a least-privilege connector configuration check, a successful packet-only dry run, a trace identifier or equivalent audit artifact, a schema-valid readback for mutations, and a rollback instruction. Agent 007 remains the only cross-brain integrator and mutation executor until the specialist lifecycle gate is met.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = render()
    if args.check:
        assert OUTPUT.is_file() and OUTPUT.read_text(encoding="utf-8") == content, "Drive evidence packet is stale; regenerate it."
        print("Google Drive evidence packet is current; no Drive connector was contacted.")
    else:
        OUTPUT.write_text(content, encoding="utf-8")
        print(f"Wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
