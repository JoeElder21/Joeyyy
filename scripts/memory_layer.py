"""Governed memory gateway on the mem0 scope model.

Incorporates mem0ai/mem0 (pinned `mem0ai` in requirements/runtime-memory.txt)
as the memory layer's scope model, with this repository's governance enforced
at the gateway rather than trusted to the backend:

- Namespaces map to mem0 `agent_id` scoping exactly as the manifests define
  them (`APEX::Strategy-Campaigns::apex_war_architect`); the namespace's
  final segment names its owner agent.
- `user_id="joe"` is the cross-brain user scope: readable by every agent,
  writable only by Agent 007.
- Reads are open within a brain (plus Agent 007 across brains). Writes are
  leased: `add()` requires the caller to be the namespace owner AND present
  a valid active writer lease naming it — the writer_lease_required rule,
  executable.
- Verify-before-write (absorbed kody pattern): every add searches first and
  refuses an exact duplicate rather than silently re-adding.

The backend is duck-typed (`add/search/get_all`). `KeywordMemoryBackend` is
the stdlib fallback so governance runs and tests offline; the real
`mem0.Memory` client drops in at activation with the same gateway unchanged
(mem0 itself needs an LLM for fact extraction, so it is activation-gated).
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from scripts.agent_runtime import CHIEF, AuditLedger
from scripts.packet_guard import PacketGuard

ROOT = Path(__file__).resolve().parents[1]
USER_SCOPE = "joe"


class MemoryAccessDenied(Exception):
    """A memory read or write violated governance rules."""


class KeywordMemoryBackend:
    """Stdlib mem0-compatible backend: JSON store with token-overlap search."""

    def __init__(self, path: Path):
        self.path = path

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, entries: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(entries, indent=1, sort_keys=True), encoding="utf-8"
        )

    def add(self, text: str, **scopes: Any) -> dict[str, Any]:
        entries = self._load()
        entry = {"id": str(uuid.uuid4()), "memory": text,
                 **{k: v for k, v in scopes.items() if v}}
        entries.append(entry)
        self._save(entries)
        return entry

    def get_all(self, **scopes: Any) -> list[dict[str, Any]]:
        wanted = {k: v for k, v in scopes.items() if v}
        return [
            entry for entry in self._load()
            if all(entry.get(k) == v for k, v in wanted.items())
        ]

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", text.lower()))

    def search(self, query: str, limit: int = 5, **scopes: Any) -> list[dict[str, Any]]:
        tokens = self._tokens(query)
        scored = []
        for entry in self.get_all(**scopes):
            overlap = len(tokens & self._tokens(entry["memory"]))
            if overlap:
                scored.append((overlap, entry))
        scored.sort(key=lambda item: -item[0])
        return [entry for _, entry in scored[:limit]]


def namespace_owner(agent_id: str) -> str:
    return agent_id.rsplit("::", 1)[-1]


def namespace_brain(agent_id: str) -> str:
    return agent_id.split("::", 1)[0]


class GovernedMemory:
    """The governance gateway every agent's memory access goes through."""

    def __init__(
        self,
        backend: Any,
        roster: dict[str, dict[str, Any]],
        guard: PacketGuard | None = None,
        ledger: AuditLedger | None = None,
    ):
        self.backend = backend
        self.roster = roster
        self.guard = guard or PacketGuard(ROOT)
        self.ledger = ledger

    def _log(self, event: str, detail: dict[str, Any]) -> None:
        if self.ledger is not None:
            self.ledger.append(event, detail)

    def add(
        self,
        text: str,
        *,
        writer: str,
        agent_id: str | None = None,
        user_id: str | None = None,
        run_id: str | None = None,
        lease: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if user_id is not None and writer != CHIEF:
            raise MemoryAccessDenied(
                f"user-scope memory is written only by {CHIEF}; {writer!r} denied"
            )
        if agent_id is not None:
            owner = namespace_owner(agent_id)
            if writer != owner:
                self._log("memory_write_denied", {"writer": writer, "agent_id": agent_id})
                raise MemoryAccessDenied(
                    f"{writer!r} is not the owner of namespace {agent_id!r} ({owner!r})"
                )
            if lease is None:
                raise MemoryAccessDenied(
                    f"namespace write to {agent_id!r} requires an active writer lease"
                )
            errors = self.guard.validate("writer_lease.schema.json", lease, [lease])
            if not errors and lease.get("writer_agent") != writer:
                errors = [f"lease names {lease.get('writer_agent')!r}, not {writer!r}"]
            if errors:
                self._log("memory_write_denied", {"writer": writer, "errors": errors})
                raise MemoryAccessDenied("; ".join(errors))
        duplicates = self.backend.search(
            text, agent_id=agent_id, user_id=user_id, run_id=run_id
        )
        if any(entry["memory"] == text for entry in duplicates):
            raise MemoryAccessDenied(
                "verify-before-write: identical memory exists; choose update or skip"
            )
        entry = self.backend.add(
            text, agent_id=agent_id, user_id=user_id, run_id=run_id
        )
        self._log("memory_write", {"writer": writer, "agent_id": agent_id,
                                   "user_id": user_id, "id": entry.get("id")})
        return entry

    def search(
        self,
        query: str,
        *,
        reader: str,
        agent_id: str | None = None,
        user_id: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        if agent_id is not None and reader != CHIEF:
            reader_brain = self.roster.get(reader, {}).get("brain")
            if reader_brain != namespace_brain(agent_id):
                self._log("memory_read_denied", {"reader": reader, "agent_id": agent_id})
                raise MemoryAccessDenied(
                    f"{reader!r} ({reader_brain}) may not read {agent_id!r}; "
                    f"cross-brain reads route through {CHIEF}"
                )
        results = self.backend.search(query, limit=limit, agent_id=agent_id, user_id=user_id)
        self._log("memory_read", {"reader": reader, "agent_id": agent_id,
                                  "user_id": user_id, "hits": len(results)})
        return results
