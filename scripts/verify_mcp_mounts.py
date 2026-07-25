"""Verify the approved MCP mounts: launch each offline-verifiable server
over stdio and list its tools through a real MCP ClientSession.

Prints a JSON report. Mounts with `verify_offline = false` are reported as
registered-not-verified with their activation requirement — never as
working. Degrades cleanly: without the `mcp` package, reports that the
runtime stack is required.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOUNTS = ROOT / "config" / "mcp_mounts.toml"


def load_mounts() -> list[dict]:
    with MOUNTS.open("rb") as source:
        return tomllib.load(source)["mounts"]


async def _probe(command: list[str]) -> list[str]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    executable = sys.executable if command[0] == "python" else command[0]
    params = StdioServerParameters(
        command=executable, args=command[1:], cwd=str(ROOT)
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            return sorted(tool.name for tool in listed.tools)


def main() -> int:
    report: dict = {"mounts": []}
    try:
        import mcp  # noqa: F401
        mcp_available = True
    except ImportError:
        mcp_available = False

    for mount in load_mounts():
        entry = {
            "name": mount["name"],
            "agents": mount["agents"],
            "verify_offline": mount.get("verify_offline", False),
        }
        if not mount.get("verify_offline"):
            entry["status"] = "registered"
            entry["activation"] = mount.get("activation", "")
        elif not mcp_available:
            entry["status"] = "unverified (mcp package not installed)"
        else:
            try:
                entry["tools"] = asyncio.run(_probe(mount["command"]))
                entry["status"] = "verified"
            except Exception as error:  # report, never crash the audit
                entry["status"] = f"probe failed: {error}"
        report["mounts"].append(entry)

    report["valid"] = all(
        entry["status"] in ("verified", "registered")
        or entry["status"].startswith("unverified")
        for entry in report["mounts"]
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
