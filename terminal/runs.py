"""Run manifests, idempotency keys, the hash chain, the lock, atomic snapshots.

A run is identified by its idempotency key (``daily:2026-09-11``): a second
firing with the same key is SKIPPED, not re-run. Each published result records
the hash of the state it was built on and the hash it produced; the chain is
verifiable by anyone with the run documents.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from terminal import clock

KINDS = ("daily", "sentinel", "weekly", "chat", "migration", "dryrun")
STATUSES = ("STARTED", "PUBLISHED", "SKIPPED", "FAILED", "BLOCKED")


def canonical_json(payload: object) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )


def sha256_of(payload: object) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def idempotency_key(kind: str, moment: datetime, label: str | None = None) -> str:
    """``daily:YYYY-MM-DD`` (ET date), ``sentinel:YYYY-MM-DDTHH`` (ET hour), else ``kind:label``."""
    if kind not in KINDS:
        raise ValueError(f"unknown run kind {kind!r}")
    local = clock.to_et(moment)
    if kind == "daily":
        return f"daily:{local:%Y-%m-%d}"
    if kind == "weekly":
        return f"weekly:{local:%G-W%V}"
    if kind == "sentinel":
        return f"sentinel:{local:%Y-%m-%dT%H}"
    if not label:
        raise ValueError(f"{kind} runs need a label")
    return f"{kind}:{label}"


def run_id(kind: str, key: str, salt: str = "") -> str:
    return f"{kind}-{hashlib.sha256(f'{key}|{salt}'.encode()).hexdigest()[:10]}"


@dataclass
class RunManifest:
    run_id: str
    kind: str
    idempotency_key: str
    writer: str
    scheduled_at: str
    started_at: str
    ready_at: str | None = None
    base_sha: str | None = None
    result_sha: str | None = None
    inputs_sha: str | None = None
    status: str = "STARTED"
    rows: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)

    def line(self) -> str:
        """The compact RUN line the legacy terminal appended to its log."""
        return "|".join(
            [
                "RUN",
                self.run_id,
                self.writer,
                self.scheduled_at,
                self.idempotency_key,
                self.ready_at or "",
                self.base_sha or "",
                self.result_sha or "",
                str(self.rows),
                self.status,
            ]
        )


def parse_run_line(line: str) -> dict:
    parts = line.strip().split("|")
    if len(parts) != 10 or parts[0] != "RUN":
        raise ValueError(f"not a RUN line: {line[:60]!r}")
    return {
        "run_id": parts[1],
        "writer": parts[2],
        "scheduled_at": parts[3],
        "idempotency_key": parts[4],
        "ready_at": parts[5],
        "base_sha": parts[6],
        "result_sha": parts[7],
        "rows": int(parts[8]) if parts[8].isdigit() else 0,
        "status": parts[9],
    }


@dataclass(frozen=True)
class ChainReport:
    ok: bool
    length: int
    breaks: list[str]
    duplicates: list[str]


def verify_chain(records: list[dict]) -> ChainReport:
    """Each PUBLISHED record's base hash must equal the previous PUBLISHED result."""
    breaks: list[str] = []
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    previous: str | None = None
    for record in records:
        key = record.get("idempotency_key", "")
        if record.get("status") == "PUBLISHED":
            if key in seen:
                duplicates.append(key)
            seen[key] = record.get("run_id", "")
            if previous is not None and record.get("base_sha") != previous:
                breaks.append(
                    f"{record.get('run_id')} built on {str(record.get('base_sha'))[:12]}, expected {previous[:12]}"
                )
            previous = record.get("result_sha") or previous
    return ChainReport(not breaks and not duplicates, len(records), breaks, duplicates)


class RunLedger:
    """An append-only list of manifests with idempotency enforced on append."""

    def __init__(self, records: list[dict] | None = None) -> None:
        self.records: list[dict] = list(records or [])

    def keys(self) -> set[str]:
        return {r["idempotency_key"] for r in self.records if r.get("status") == "PUBLISHED"}

    def already_published(self, key: str) -> bool:
        return key in self.keys()

    def append(self, manifest: RunManifest) -> str:
        if manifest.status == "PUBLISHED" and self.already_published(manifest.idempotency_key):
            manifest.status = "SKIPPED"
            manifest.notes.append("idempotency key already published")
        self.records.append(manifest.as_dict())
        return manifest.status

    def last_published_sha(self) -> str | None:
        for record in reversed(self.records):
            if record.get("status") == "PUBLISHED":
                return record.get("result_sha")
        return None


@dataclass
class Lease:
    holder: str
    expires_at: datetime


class RunLock:
    """Cooperative single-writer lease, mirroring the store's ``acquire``.

    Busy is a normal outcome (``False``), never an error; leases expire on their
    own so a crashed run cannot hold the lock forever.
    """

    def __init__(self) -> None:
        self._lease: Lease | None = None

    def acquire(self, holder: str, now: datetime, ttl_seconds: int = 900) -> bool:
        now = clock.to_utc(now)
        ttl = max(1, min(ttl_seconds, 600 * 10))
        if self._lease is None or self._lease.expires_at <= now or self._lease.holder == holder:
            self._lease = Lease(holder, now + timedelta(seconds=ttl))
            return True
        return False

    def holder(self, now: datetime) -> str | None:
        if self._lease is None or self._lease.expires_at <= clock.to_utc(now):
            return None
        return self._lease.holder

    def release(self, holder: str) -> None:
        if self._lease is not None and self._lease.holder == holder:
            self._lease = None


def build_snapshot(
    parts: dict[str, dict], generated_at: datetime, version: str, base_sha: str | None
) -> dict:
    """Assemble one complete, self-describing snapshot. Publishing swaps the
    ``snapshots/current`` pointer to it in one write: readers see the old whole
    or the new whole, never a mixture."""
    body = {
        "version": version,
        "generated_at": clock.to_utc(generated_at).isoformat().replace("+00:00", "Z"),
        "base_sha": base_sha,
        "parts": {
            name: {"sha": sha256_of(doc), "keys": sorted(doc)} for name, doc in parts.items()
        },
    }
    body["sha"] = sha256_of({"parts": body["parts"], "version": version, "base_sha": base_sha})
    return body
