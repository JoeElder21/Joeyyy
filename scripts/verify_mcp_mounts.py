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


def _verdict(mount: dict, tools: list[str]) -> str:
    """A completed handshake is not a working mount.

    `status = "verified"` was set the moment `list_tools()` returned, whatever
    it returned. A server whose tool registration had regressed -- or which
    registered nothing at all -- completed the handshake, listed zero tools, and
    was reported as verified, so CI stayed green while claiming the connector
    had been confirmed. That is the same "configured, not executed" error this
    script exists to catch, one level in: probed, but not actually checked.

    `expected_tools` in config/mcp_mounts.toml is the declared contract. Where a
    mount declares it, every named tool must be present; where it does not, an
    empty list is still refused, because a mount offering no tools cannot be
    what any agent was granted.
    """
    if not tools:
        return "probe returned no tools; a mount that offers nothing is not verified"
    expected = set(mount.get("expected_tools", []))
    missing = sorted(expected - set(tools))
    if missing:
        return f"missing declared tools: {', '.join(missing)}"
    return "verified"


async def _probe(command: list[str]) -> list[str]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    executable = sys.executable if command[0] == "python" else command[0]
    params = StdioServerParameters(command=executable, args=command[1:], cwd=str(ROOT))
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        listed = await session.list_tools()
        return sorted(tool.name for tool in listed.tools)


def main(argv: list[str] | None = None) -> int:
    # `--strict` treats a degraded verification as a failure. Without it the
    # script reported "unverified (mcp package not installed)" and exited 0,
    # which in CI -- where the dependency is installed deliberately -- means the
    # probe silently did not run and a broken MCP server stays green.
    strict = "--strict" in (argv if argv is not None else sys.argv[1:])
    report: dict = {"mounts": [], "strict": strict}
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
                tools = asyncio.run(_probe(mount["command"]))
                entry["tools"] = tools
                entry["status"] = _verdict(mount, tools)
            except Exception as error:  # report, never crash the audit
                entry["status"] = f"probe failed: {error}"
        report["mounts"].append(entry)

    acceptable = ("verified", "registered")
    report["valid"] = all(
        entry["status"] in acceptable or (not strict and entry["status"].startswith("unverified"))
        for entry in report["mounts"]
    )
    if strict:
        report["degraded"] = [
            entry["name"] for entry in report["mounts"] if entry["status"].startswith("unverified")
        ]
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
