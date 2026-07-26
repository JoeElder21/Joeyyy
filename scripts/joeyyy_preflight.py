#!/usr/bin/env python3
"""Emit a public-safe, read-only JOEYYY repository preflight as JSON."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def git(*args: str) -> tuple[bool, str]:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.returncode == 0, (result.stdout or result.stderr).strip()


def applicable_instructions() -> list[str]:
    """Return repository instruction paths; never scan outside this repository."""
    return sorted(str(path.relative_to(ROOT)) for path in ROOT.rglob("AGENTS.md"))


def latest_public_record() -> str | None:
    """Select the newest dated public-safe reconciliation/integration record by name."""
    candidates = {
        *ROOT.glob("docs/RECONCILIATION_*.md"),
        *ROOT.glob("docs/INTEGRATION_BUILDOUT_*.md"),
    }
    if not candidates:
        return None
    return str(max(candidates, key=lambda path: path.name).relative_to(ROOT))


def build_report() -> dict[str, object]:
    branch_ok, branch = git("branch", "--show-current")
    sha_ok, sha = git("rev-parse", "HEAD")
    status_ok, status = git("status", "--short")
    remote_ok, remotes = git("remote", "-v")
    default_ok, default_ref = git("symbolic-ref", "refs/remotes/origin/HEAD")
    constitution = ROOT / "docs" / "JOEYYY_GLOBAL_AGENT_ENGINEERING_CONSTITUTION.md"
    agent_007 = ROOT / ".codex" / "agents" / "apex_chief_of_staff.toml"
    manifests = [ROOT / "brains" / brain / "agents.toml" for brain in ("apex", "jeos")]
    return {
        "repository_root": str(ROOT),
        "branch": branch if branch_ok else None,
        "sha": sha if sha_ok else None,
        "worktree_status": status.splitlines() if status_ok and status else [],
        "remotes": remotes.splitlines() if remote_ok and remotes else [],
        "default_branch_ref": default_ref if default_ok else None,
        "remote_freshness": "unknown" if not default_ok else "ref-only-not-fetched",
        "instructions": applicable_instructions(),
        "constitution_exists": constitution.is_file(),
        "agent_007_contract_exists": agent_007.is_file(),
        "brain_manifests_exist": all(path.is_file() for path in manifests),
        "latest_public_system_record": latest_public_record(),
        "private_memory_provider": "unverified",
        "memory_notice": (
            "The public record is sanitized system history, not private APEX or JEOS "
            "memory. Classify scope and verify an authorized provider before progressive retrieval."
        ),
    }


if __name__ == "__main__":
    print(json.dumps(build_report(), indent=2, sort_keys=True))
