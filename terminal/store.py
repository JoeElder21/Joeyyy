"""Store adapters: in memory, a JSON directory, and write plans for the artifact db.

Documents live at ``collection/doc_id`` paths with the artifact db's grammar
(an even number of segments, one JSON object per document, 256 KiB each).
Recommendations are append-only: overwriting one raises here, and the
release gate re-checks the stored hashes because the db itself is
last-writer-wins.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Protocol

COLLECTIONS = (
    "policy",
    "portfolios",
    "evidence",
    "runs",
    "recommendations",
    "outcomes",
    "security",
    "learning",
    "health",
    "snapshots",
    "boards",
    "legacy",
)
IMMUTABLE = frozenset({"recommendations"})
MAX_DOC_BYTES = 256 * 1024
MAX_DOCS = 5000
BATCH_LIMIT = 50
SEGMENT = re.compile(r"^(?!\.\.?$)[A-Za-z0-9_\-.~:@+]{1,200}$")


class ImmutableDocumentError(RuntimeError):
    """A recommendation already exists at this path."""


def split_path(path: str) -> tuple[str, str]:
    parts = path.split("/")
    if len(parts) % 2 or any(not SEGMENT.match(p) for p in parts):
        raise ValueError(f"not a document path: {path!r}")
    return "/".join(parts[:-1]), parts[-1]


def doc_bytes(data: dict[str, Any]) -> int:
    return len(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def check_document(path: str, data: Any) -> list[str]:
    problems: list[str] = []
    try:
        collection, _ = split_path(path)
    except ValueError as error:
        return [str(error)]
    if collection.split("/")[0] not in COLLECTIONS:
        problems.append(f"{path}: unknown collection {collection!r}")
    if not isinstance(data, dict):
        problems.append(f"{path}: document body must be an object")
        return problems
    size = doc_bytes(data)
    if size > MAX_DOC_BYTES:
        problems.append(f"{path}: {size:,} bytes exceeds the {MAX_DOC_BYTES:,}-byte document limit")
    return problems


class Store(Protocol):
    def get(self, path: str) -> dict[str, Any] | None: ...
    def set(self, path: str, data: dict[str, Any]) -> None: ...
    def delete(self, path: str) -> None: ...
    def list(self, collection: str) -> list[tuple[str, dict[str, Any]]]: ...


class MemoryStore:
    def __init__(self) -> None:
        self._docs: dict[str, dict[str, Any]] = {}

    def get(self, path: str) -> dict[str, Any] | None:
        split_path(path)
        doc = self._docs.get(path)
        return json.loads(json.dumps(doc)) if doc is not None else None

    def set(self, path: str, data: dict[str, Any]) -> None:
        problems = check_document(path, data)
        if problems:
            raise ValueError("; ".join(problems))
        collection, _ = split_path(path)
        if collection in IMMUTABLE and path in self._docs and self._docs[path] != data:
            raise ImmutableDocumentError(path)
        if path not in self._docs and len(self._docs) >= MAX_DOCS:
            raise RuntimeError("document quota reached")
        self._docs[path] = json.loads(json.dumps(data))

    def delete(self, path: str) -> None:
        collection, _ = split_path(path)
        if collection in IMMUTABLE:
            raise ImmutableDocumentError(path)
        self._docs.pop(path, None)

    def list(self, collection: str) -> list[tuple[str, dict[str, Any]]]:
        prefix = collection + "/"
        return sorted(
            (path[len(prefix) :], json.loads(json.dumps(doc)))
            for path, doc in self._docs.items()
            if path.startswith(prefix) and "/" not in path[len(prefix) :]
        )

    def paths(self) -> list[str]:
        return sorted(self._docs)


class JsonDirStore(MemoryStore):
    """One JSON file per document under ``root``; the development store."""

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        for file in self.root.rglob("*.json"):
            path = file.relative_to(self.root).with_suffix("").as_posix()
            try:
                split_path(path)
            except ValueError:
                continue  # reports and other non-document files may sit beside the store
            self._docs[path] = json.loads(file.read_text(encoding="utf-8"))

    def set(self, path: str, data: dict[str, Any]) -> None:
        super().set(path, data)
        target = self.root / f"{path}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8"
        )
        tmp.replace(target)

    def delete(self, path: str) -> None:
        super().delete(path)
        target = self.root / f"{path}.json"
        if target.exists():
            target.unlink()


def write_plan(
    docs: dict[str, dict[str, Any]], batch_limit: int = BATCH_LIMIT
) -> list[list[dict[str, Any]]]:
    """Batches of ``set`` writes for the artifact db, each at most ``batch_limit`` long."""
    entries = []
    for path in sorted(docs):
        problems = check_document(path, docs[path])
        if problems:
            raise ValueError("; ".join(problems))
        collection, doc_id = split_path(path)
        entries.append(
            {"op": "set", "collection": collection, "doc_id": doc_id, "data": docs[path]}
        )
    return [entries[i : i + batch_limit] for i in range(0, len(entries), batch_limit)]


def immutable_violations(
    before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]
) -> list[str]:
    """Recommendation paths whose content changed between two states."""
    violations = []
    for path, doc in before.items():
        collection, _ = split_path(path)
        if collection in IMMUTABLE and path in after and after[path] != doc:
            violations.append(path)
    return sorted(violations)
