"""Gate measurement helpers for the awesome-copilot selection report.

These live apart from scripts/build_awesome_copilot_report.py because that
module builds the PDF at import time: importing it to test a helper would run
every gate and rewrite the document. Keeping the measurement logic here makes
the honesty rules below directly testable.

The rule these enforce: never render an unrun check as a clean one.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]


def unverified_note(output: str) -> str:
    """Name the items a passing gate did not actually probe.

    `"valid": true` only means the registry is internally consistent. A mount
    declaring verify_offline = true whose probe could not run comes back with a
    status of "unverified (...)", and collapsing that to a bare "passed"
    publishes an unrun check as a clean one. Surface it in the same row.
    """
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        # Non-JSON gate output: report the literal marker rather than claiming
        # there is nothing unverified.
        return (" (output reports unverified items)"
                if "unverified" in output else "")

    if not isinstance(payload, dict):
        return ""
    # "registered" is ALSO an unprobed state, and the larger one: every
    # verify_offline = false mount reports it. Naming only the "unverified"
    # ones published a row reading "not probed: filesystem, governance" while
    # github, postgres, gdrive, civil3d, terraform and azure had equally never
    # been contacted -- an incomplete clean scope, which is the same defect as
    # a bare "passed" one level down.
    def unprobed(entry: dict) -> bool:
        status = str(entry.get("status", ""))
        return status.startswith("unverified") or status == "registered"

    names = sorted(
        str(entry.get("name", "unnamed"))
        for section in payload.values() if isinstance(section, list)
        for entry in section
        if isinstance(entry, dict) and unprobed(entry)
    )
    return f" (not probed: {', '.join(names)})" if names else ""


def missing_dependency_note(output: str) -> str:
    """Say when a passing gate ran against an empty runtime.

    `verify_runtime_stack.py` validates TOML and schemas, which can all pass on
    a machine where none of the declared runtime packages is installed -- it
    reports `installed_count: 0` with 20 entries in `missing` and still exits 0
    with `"valid": true`. Rendering that as a clean runtime-stack pass presents
    a machine with no orchestration runtime as a verified one.
    """
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    missing = payload.get("missing")
    if not isinstance(missing, list) or not missing:
        return ""
    installed = payload.get("installed_count")
    total = (installed + len(missing)) if isinstance(installed, int) else None
    scope = f"{len(missing)} of {total}" if total else f"{len(missing)}"
    return (f" (runtime not installed: {scope} declared packages missing, "
            "so this checks declarations only)")


def failure_detail(completed) -> str:
    """The most informative line available from a failed gate.

    These gates print JSON, so the first output line is "{" -- taking it
    produced rows reading `FAILED (exit 1) — {`, which names nothing. Prefer a
    parsed error, then a substantive stderr line, and fall back to raw output
    only when neither exists.
    """
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        for key in ("errors", "error", "failures", "problems"):
            value = payload.get(key)
            if isinstance(value, list) and value:
                return "; ".join(str(item) for item in value[:3])
            if isinstance(value, str) and value.strip():
                return value.strip()
        # The actionable reason for a failed mount probe lives only in
        # mounts[*].status as "probe failed: ...". With no top-level error key
        # the substantive-line fallback then filtered out every quoted status
        # line and returned "{", so the row read `FAILED (exit 1) — {` -- the
        # exact uninformative output that fallback was added to prevent.
        failures = [
            f"{entry.get('name', 'unnamed')}: {entry['status']}"
            for section in payload.values() if isinstance(section, list)
            for entry in section
            if isinstance(entry, dict)
            and isinstance(entry.get("status"), str)
            and ("fail" in entry["status"].lower()
                 or "error" in entry["status"].lower())
        ]
        if failures:
            return "; ".join(failures[:3])

    def substantive(stream: str) -> str | None:
        lines = [line.strip() for line in stream.splitlines() if line.strip()]
        useful = [line for line in lines
                  if line not in "{}[]," and not line.startswith('"')]
        if not useful:
            return None
        # A traceback's informative line is its last, not its first: "Traceback
        # (most recent call last):" names nothing.
        if useful[0].startswith("Traceback (most recent call last)"):
            return useful[-1]
        return useful[0]

    found = substantive(completed.stderr) or substantive(completed.stdout)
    if found:
        return found
    remainder = (completed.stderr + completed.stdout).strip()
    return remainder.splitlines()[0] if remainder else "no output"


def run_gate(script: str) -> str:
    """Run one validation script and report its real outcome.

    These rows used to be hardcoded "Passed" / '"valid": true', so a report
    regenerated while a gate was failing still published success -- in the one
    document meant to serve as verification evidence.
    """
    path = ROOT / "scripts" / script
    try:
        completed = subprocess.run(
            [sys.executable, str(path)],
            cwd=ROOT,
            capture_output=True, text=True, timeout=600, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"not measured at build time ({type(error).__name__})"

    # Paragraph() parses its input as XML-ish markup, so a finding naming a real
    # file such as docs/R&D<draft>.pdf would raise a parse error and destroy the
    # very PDF meant to record the failure. Escape anything derived from output.
    if completed.returncode != 0:
        return escape(
            f"FAILED (exit {completed.returncode}) — "
            f"{failure_detail(completed)[:110]}")

    output = completed.stdout.strip()
    if not output:
        return "passed"
    note = unverified_note(output) + missing_dependency_note(output)
    if '"valid": true' in output:
        checked = re.search(r'"(\w+_checked)":\s*(\d+)', output)
        detail = (f" — {checked.group(2)} {checked.group(1).replace('_', ' ')}"
                  if checked else "")
        return escape(f'passed, "valid": true{detail}{note}')
    return escape(f"passed — {output.splitlines()[-1][:90]}{note}")


def measure_test_suite() -> str:
    """Run the suite and report what it actually did.

    The count was previously hardcoded, so every regenerated report published a
    stale figure the moment a test was added -- in a document whose whole
    purpose is to be change evidence. Never fabricate a result here: if the
    suite cannot run, say so.
    """
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
            cwd=ROOT,
            capture_output=True, text=True, timeout=900, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"not measured at build time ({type(error).__name__})"

    output = completed.stderr + completed.stdout
    ran = re.search(r"Ran (\d+) tests?", output)
    if not ran:
        return "not measured at build time (unrecognised output)"
    count = ran.group(1)
    if completed.returncode != 0:
        failures = re.search(r"(FAILED \([^)]*\))", output)
        return escape(
            f"{count} tests, {failures.group(1) if failures else 'FAILED'}")
    skipped = re.search(r"skipped=(\d+)", output)
    tail = f" ({skipped.group(1)} skipped)" if skipped else ""
    return f"{count} tests, OK{tail}"
