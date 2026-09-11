"""Fatal-risk gates for assets and release gates for a run.

An asset with a fatal flag is EXCLUDED before any score is computed; a run
that fails a release gate is not published. Both lists are explicit so a
reviewer can see what was checked, not only what passed.
"""

from __future__ import annotations

from dataclasses import dataclass

FATAL_FLAGS: dict[str, str] = {
    "going_concern": "auditor going-concern warning",
    "liquidity_cliff_in_horizon": "unaddressed refinancing or liquidity cliff inside the horizon",
    "unresolved_audit_issue": "material reporting weakness or auditor issue unresolved",
    "fraud_allegation_unresolved": "unresolved fraud or misconduct allegation material to the thesis",
    "delisting_notice": "exchange delisting notice outstanding",
    "honeypot": "contract cannot be sold (honeypot)",
    "open_mint_authority": "token supply can be minted by a live authority",
    "unverified_contract": "contract source is not verified on the explorer",
    "owner_can_freeze_or_blacklist": "owner can freeze transfers or blacklist holders",
    "insider_supply_over_half": "team or insider control of more than half the supply",
    "no_reliable_market_data": "no reliable price or volume series",
}
SOFT_CEILING_BYTES = 900_000
HARD_CEILING_BYTES = 1_000_000


@dataclass(frozen=True)
class GateResult:
    passed: bool
    failed: list[str]
    checked: list[str]

    def as_dict(self) -> dict:
        return {"passed": self.passed, "failed": list(self.failed), "checked": list(self.checked)}


def asset_gate(flags: dict[str, bool]) -> GateResult:
    unknown = set(flags) - set(FATAL_FLAGS)
    if unknown:
        raise ValueError(f"unknown fatal flags: {sorted(unknown)}")
    failed = sorted(name for name, tripped in flags.items() if tripped)
    return GateResult(not failed, failed, sorted(flags))


@dataclass(frozen=True)
class GateCheck:
    name: str
    passed: bool
    detail: str

    def as_dict(self) -> dict:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


def release_gates(
    *,
    schema_errors: list[str],
    chain_ok: bool,
    page_bytes: int,
    boards_with_status: dict[str, str],
    immutable_violations: list[str],
    invariant_failures: list[str],
    critic_verdict: str,
) -> list[GateCheck]:
    """Every gate a run must pass before its snapshot may be published."""
    checks = [
        GateCheck(
            "schema",
            not schema_errors,
            "all documents validate" if not schema_errors else "; ".join(schema_errors[:5]),
        ),
        GateCheck(
            "run_chain",
            chain_ok,
            "hash chain intact" if chain_ok else "base hash does not match the prior result",
        ),
        GateCheck(
            "size_ceiling",
            page_bytes <= HARD_CEILING_BYTES,
            f"{page_bytes:,} bytes (soft {SOFT_CEILING_BYTES:,}, hard {HARD_CEILING_BYTES:,})",
        ),
        GateCheck(
            "freshness_labelled",
            all(status in {"LIVE", "STALE", "DEGRADED"} for status in boards_with_status.values()),
            "every board carries a computed status",
        ),
        GateCheck(
            "recommendations_immutable",
            not immutable_violations,
            "no prior recommendation was altered"
            if not immutable_violations
            else ", ".join(immutable_violations),
        ),
        GateCheck(
            "invariants",
            not invariant_failures,
            "all page invariants hold" if not invariant_failures else "; ".join(invariant_failures),
        ),
        GateCheck("critic", critic_verdict != "BLOCKED", f"critic verdict {critic_verdict}"),
    ]
    return checks


def all_passed(checks: list[GateCheck]) -> bool:
    return all(check.passed for check in checks)
