#!/usr/bin/env python3
"""Run the first executable APEX slice and print VERIFY / REPORT.

Usage:
    python scripts/run_first_apex_slice.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.first_apex_slice import report_json, run_first_apex_slice  # noqa: E402


def main() -> int:
    run = run_first_apex_slice()
    verify = run.report["verify"]
    print("VERIFY")
    print(json.dumps(verify, indent=2, sort_keys=True))
    print("REPORT")
    print(report_json(run.report))
    if run.report["lifecycle"]["specialist_status"] != "shadow":
        print("error: specialist left shadow; first slice must not promote", file=sys.stderr)
        return 2
    if run.report["unknown_identities"]:
        print(
            f"error: non-v2.1 identities in report: {run.report['unknown_identities']}",
            file=sys.stderr,
        )
        return 2
    return 0 if verify["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
