"""Governed evidence indexes on llama_index.

Incorporates run-llama/llama_index (pinned `llama-index-core` in
requirements/runtime-memory.txt) as the actual index behind the evidence
write targets: APEX/Source-Index and APEX/Reusable-Playbooks for
apex_intelligence_forge, and JEOS/Reflection-Ledger for
jeos_reflection_forge (namespace owners per the brain manifests).

Governance at the index boundary:

- Writes are designated-writer-only: only the namespace's owner agent may
  add documents, and every write is audit-logged.
- Reads are brain-locked: an index is readable by agents of its own brain
  plus Agent 007; cross-brain retrieval must route through 007.
- Offline by default: indexes use SimpleKeywordTableIndex with regex
  keyword extraction and the "simple" retriever — no embeddings, no LLM,
  no network. Semantic VectorStoreIndex mode is an activation-time swap
  once runtime credentials exist; the governance wrapper is identical.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.agent_runtime import CHIEF, AuditLedger

ROOT = Path(__file__).resolve().parents[1]

# Namespace owners per brains/apex/agents.toml and brains/jeos/agents.toml.
DEFAULT_INDEXES = {
    "APEX/Source-Index": {"brain": "APEX", "writer": "apex_intelligence_forge"},
    "APEX/Reusable-Playbooks": {"brain": "APEX", "writer": "apex_intelligence_forge"},
    "JEOS/Reflection-Ledger": {"brain": "JEOS", "writer": "jeos_reflection_forge"},
}


class IndexAccessDenied(Exception):
    """A read or write violated the index's governance rules."""


try:  # degrade cleanly when the runtime stack is not installed
    from llama_index.core import Document, Settings, SimpleKeywordTableIndex
    from llama_index.core.llms import MockLLM

    # Offline default: keyword indexing with the simple retriever never calls
    # an LLM, but index construction resolves one — pin a mock so no network
    # or key is ever touched. Activation replaces this with a real config.
    Settings.llm = MockLLM()

    LLAMA_INDEX_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised in stdlib CI
    LLAMA_INDEX_AVAILABLE = False


if LLAMA_INDEX_AVAILABLE:

    class EvidenceIndex:
        """One governed, namespace-scoped keyword index."""

        def __init__(
            self,
            namespace: str,
            brain: str,
            writer: str,
            roster: dict[str, dict[str, Any]],
            ledger: AuditLedger | None = None,
        ):
            self.namespace = namespace
            self.brain = brain
            self.writer = writer
            self.roster = roster
            self.ledger = ledger
            self._documents: list[Document] = []
            self._index: SimpleKeywordTableIndex | None = None

        def _log(self, event: str, detail: dict[str, Any]) -> None:
            if self.ledger is not None:
                self.ledger.append(event, {"namespace": self.namespace, **detail})

        def add_document(
            self, agent: str, text: str, metadata: dict[str, Any] | None = None
        ) -> None:
            if agent != self.writer:
                self._log("index_write_denied", {"agent": agent})
                raise IndexAccessDenied(
                    f"{agent!r} is not the designated writer for {self.namespace!r} "
                    f"({self.writer!r} holds it)"
                )
            self._documents.append(Document(text=text, metadata=metadata or {}))
            self._index = None  # rebuilt lazily on next retrieve
            self._log("index_write", {"agent": agent, "chars": len(text)})

        def retrieve(self, agent: str, query: str, top_k: int = 3) -> list[dict[str, Any]]:
            reader_brain = self.roster.get(agent, {}).get("brain")
            if agent != CHIEF and reader_brain != self.brain:
                self._log("index_read_denied", {"agent": agent})
                raise IndexAccessDenied(
                    f"{agent!r} ({reader_brain}) may not read {self.brain} index "
                    f"{self.namespace!r}; route cross-brain retrieval through {CHIEF}"
                )
            if not self._documents:
                return []
            if self._index is None:
                self._index = SimpleKeywordTableIndex.from_documents(self._documents)
            retriever = self._index.as_retriever(
                retriever_mode="simple", similarity_top_k=top_k
            )
            nodes = retriever.retrieve(query)
            self._log("index_read", {"agent": agent, "query": query, "hits": len(nodes)})
            return [
                {"text": node.get_content(), "metadata": dict(node.metadata or {})}
                for node in nodes[:top_k]
            ]

    def build_indexes(
        roster: dict[str, dict[str, Any]],
        ledger: AuditLedger | None = None,
        registry: dict[str, dict[str, str]] | None = None,
    ) -> dict[str, EvidenceIndex]:
        """Build the governed index set from the namespace registry."""
        registry = registry or DEFAULT_INDEXES
        return {
            namespace: EvidenceIndex(
                namespace, spec["brain"], spec["writer"], roster, ledger
            )
            for namespace, spec in registry.items()
        }
