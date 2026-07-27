"""Writer-lease registry and serialized mutation admission — build ticket #3, core.

Executes acceptance gate 8 (docs/SPECIALIST_ACCEPTANCE_TESTS.md):

    One active writer lease exists per canonical ASCII brain/target/resource
    across all missions, expires within 24 hours, and rejects whitespace or
    Unicode-alias collisions.

and gate 9/14 mechanics: a mutation admitted through the queue must carry a
matching active lease, and completion requires readback confirmation before
the lease releases as ``verified``.

Leases are plain dicts shaped exactly like ``schemas/writer_lease.schema.json``
so they interoperate with PacketGuard and the scripts/ gateway layer.
Stdlib-pure; ``runtime/lease_queue.py`` adds the Celery per-target queues.
"""

from __future__ import annotations

import datetime as _dt
import unicodedata
import uuid
from dataclasses import dataclass, field

MAX_LEASE_HOURS = 24
_BRAINS = {"APEX", "JEOS"}


class LeaseError(PermissionError):
    """Fail-closed lease violation."""


def canonical_key(owner_brain: str, write_target: str, resource_id: str) -> str:
    """Build the canonical ASCII lease key, rejecting alias-capable input.

    Gate 8: whitespace anywhere, non-ASCII, or text that changes under NFKC
    normalization (a Unicode alias) is rejected outright — aliases cannot
    collide because they cannot enter.

    The ``resource_id`` is case-folded to match ``PacketGuard._canonical_identifier``
    (NFKC + casefold). Without this, ``"Playbook"`` and ``"playbook"`` produced
    two distinct keys here but a single canonical resource in PacketGuard's
    lease-ledger collision check, so the registry — the sole single-writer gate
    on the ``memory_layer``/``lease_queue`` write path — would issue two active
    leases on one resource. The reject checks above guarantee each part is
    already whitespace-free and NFKC-stable, so casefold is the only remaining
    transform needed to align the two canonical forms.
    """
    parts = (owner_brain, write_target, resource_id)
    for part in parts:
        if not part:
            raise LeaseError("lease key parts must be non-empty")
        if part != unicodedata.normalize("NFKC", part):
            raise LeaseError(f"Unicode alias rejected in lease key part: {part!r}")
        if not part.isascii():
            raise LeaseError(f"non-ASCII lease key part rejected: {part!r}")
        if any(ch.isspace() for ch in part):
            raise LeaseError(f"whitespace in lease key part rejected: {part!r}")
    if owner_brain not in _BRAINS:
        raise LeaseError(f"unknown owner brain: {owner_brain!r}")
    return "/".join((owner_brain, write_target, resource_id.casefold()))


@dataclass
class LeaseRegistry:
    """Single-writer enforcement across all missions."""

    _active: dict[str, dict] = field(default_factory=dict)
    _history: list[dict] = field(default_factory=list)

    def issue(
        self,
        *,
        mission_id: str,
        owner_brain: str,
        writer_agent: str,
        write_target: str,
        resource_id: str,
        expected_state: str,
        rollback: str,
        issued_by: str = "apex_chief_of_staff",
        sensitivity: str = "internal",
        now: _dt.datetime | None = None,
        hours: float = MAX_LEASE_HOURS,
    ) -> dict:
        if hours <= 0 or hours > MAX_LEASE_HOURS:
            raise LeaseError(f"lease duration must be within (0, {MAX_LEASE_HOURS}] hours")
        key = canonical_key(owner_brain, write_target, resource_id)
        now = now or _dt.datetime.now(_dt.UTC)
        self._expire(now)
        if key in self._active:
            holder = self._active[key]["writer_agent"]
            raise LeaseError(f"active lease already held on {key} by {holder}")
        lease = {
            "schema_version": "2.1",
            "lease_id": f"lease_{uuid.uuid4().hex[:16]}",
            "mission_id": mission_id,
            "resource_id": resource_id,
            "owner_brain": owner_brain,
            "writer_agent": writer_agent,
            "write_target": write_target,
            "issued_by": issued_by,
            "issued_at": now.isoformat(),
            "expires_at": (now + _dt.timedelta(hours=hours)).isoformat(),
            "status": "active",
            "expected_state": expected_state,
            "validation_readback": "pending",
            "rollback": rollback,
            "sensitivity": sensitivity,
        }
        self._active[key] = lease
        # A COPY. Returning the stored object made the registry mutable through
        # its own return value: issuing a lease to one agent and then assigning
        # `writer_agent` on the returned dict rewrote the registry's record, so
        # the "authoritative source" that policy enforcement consults could be
        # edited by anyone holding an issued lease. Reproduced before fixing.
        return dict(lease)

    def active_lease(self, key: str) -> dict | None:
        """A copy, for the same reason `issue` returns one: a lookup must not
        hand out a handle that can rewrite what it looked up."""
        lease = self._active.get(key)
        return dict(lease) if lease is not None else None

    def release(self, lease_id: str, *, readback_confirmed: bool) -> dict:
        """Close a lease. ``verified`` requires confirmed readback (gate 14).

        Returns a copy, and stores a SEPARATE copy in history -- the untouched
        sibling of the fix applied to `issue()` and `active_lease()`. This
        method appended the live object to `_history` and handed the caller the
        same object, so setting `status` or `writer_agent` on the returned dict
        rewrote the registry's recorded history. That history is the audit
        evidence for a completed mutation, which makes it the one record a
        caller must not be able to edit after the fact: a closed lease saying
        `verified` when the readback was never confirmed is exactly the claim
        gate 14 exists to prevent. Reproduced before fixing.
        """
        for key, lease in list(self._active.items()):
            if lease["lease_id"] == lease_id:
                lease["status"] = "verified" if readback_confirmed else "released_unverified"
                lease["validation_readback"] = (
                    "confirmed" if readback_confirmed else "not_confirmed"
                )
                del self._active[key]
                # Two independent copies: one for the record, one for the
                # caller. Appending `lease` and returning `dict(lease)` would
                # still leave the stored object reachable by anything else
                # holding it, and `_expire` also appends here.
                self._history.append(dict(lease))
                return dict(lease)
        raise LeaseError(f"no active lease with id {lease_id}")

    def _expire(self, now: _dt.datetime) -> None:
        for key, lease in list(self._active.items()):
            if _dt.datetime.fromisoformat(lease["expires_at"]) <= now:
                lease["status"] = "expired"
                del self._active[key]
                # A copy here too. Nothing outside currently holds this object,
                # so this path is not reachable today -- but "history stores
                # its own copy" is the invariant, and an invariant that holds
                # on two of three paths is the shape every sibling finding in
                # this record has taken.
                self._history.append(dict(lease))


@dataclass
class MutationAdmission:
    """Serialized mutation gate: one in-flight mutation per canonical key."""

    registry: LeaseRegistry
    _in_flight: dict[str, str] = field(default_factory=dict)

    def admit(self, lease: dict) -> str:
        key = canonical_key(lease["owner_brain"], lease["write_target"], lease["resource_id"])
        active = self.registry.active_lease(key)
        if active is None or active["lease_id"] != lease["lease_id"]:
            raise LeaseError(f"mutation on {key} has no matching active lease")
        if key in self._in_flight:
            raise LeaseError(f"a mutation is already in flight on {key}")
        self._in_flight[key] = lease["lease_id"]
        return key

    def complete(self, key: str, *, readback_confirmed: bool) -> dict:
        lease_id = self._in_flight.pop(key, None)
        if lease_id is None:
            raise LeaseError(f"no in-flight mutation on {key}")
        return self.registry.release(lease_id, readback_confirmed=readback_confirmed)
