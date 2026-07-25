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
    names = sorted(
        str(entry.get("name", "unnamed"))
        for section in payload.values() if isinstance(section, list)
        for entry in section
        if isinstance(entry, dict)
        and str(entry.get("status", "")).startswith("unverified")
    )
    return f" (not probed: {', '.join(names)})" if names else ""


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
        first = next(
            (line.strip() for line in
             (completed.stdout + completed.stderr).splitlines() if line.strip()),
            "no output",
        )
        return escape(f"FAILED (exit {completed.returncode}) — {first[:110]}")

    output = completed.stdout.strip()
    if not output:
        return "passed"
    note = unverified_note(output)
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
