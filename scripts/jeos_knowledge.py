"""JEOS knowledge graph in Logseq format.

Incorporates logseq/logseq per Joe's directive: the JEOS brain's knowledge
write targets (JEOS/Reflection-Ledger, JEOS/Pattern-Hypotheses,
JEOS/Life-Architecture, JEOS/Lessons-and-Rules) live as a Logseq graph.
Because a Logseq graph is a directory of Markdown files with [[links]] and
#tags, this layer is fully operational offline — the desktop app opens the
same directory, and the HTTP API becomes an alternative transport at
activation without changing the format.

Governance at the graph boundary:

- Writes are designated-writer-only per knowledge target and audit-logged.
- Reads are JEOS-locked: JEOS specialists and Agent 007 only. APEX agents
  never read the personal graph; cross-brain use routes through 007.
- Queries ("all #pattern-hypothesis pages from the last 30 days") run over
  stored pages — retrieval, not recall.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

from scripts.agent_runtime import CHIEF, AuditLedger

ROOT = Path(__file__).resolve().parents[1]

# Knowledge-target owners per the JEOS manifest write targets.
KNOWLEDGE_TARGETS = {
    "JEOS/Reflection-Ledger": "jeos_reflection_forge",
    "JEOS/Pattern-Hypotheses": "jeos_reflection_forge",
    "JEOS/Lessons-and-Rules": "jeos_reflection_forge",
    "JEOS/Life-Architecture": "jeos_life_architect",
}


class GraphAccessDenied(Exception):
    """A read or write violated the knowledge graph's governance rules."""


class JeosKnowledgeGraph:
    """A governed Logseq-format graph rooted at a directory."""

    def __init__(
        self,
        graph_dir: Path,
        roster: dict[str, dict[str, Any]],
        ledger: AuditLedger | None = None,
        targets: dict[str, str] | None = None,
    ):
        self.graph_dir = Path(graph_dir)
        self.roster = roster
        self.ledger = ledger
        self.targets = targets or KNOWLEDGE_TARGETS
        (self.graph_dir / "pages").mkdir(parents=True, exist_ok=True)
        (self.graph_dir / "journals").mkdir(parents=True, exist_ok=True)

    def _log(self, event: str, detail: dict[str, Any]) -> None:
        if self.ledger is not None:
            self.ledger.append(event, detail)

    def _check_reader(self, agent: str) -> None:
        if agent == CHIEF:
            return
        if self.roster.get(agent, {}).get("brain") != "JEOS":
            self._log("graph_read_denied", {"agent": agent})
            raise GraphAccessDenied(
                f"{agent!r} may not read the JEOS knowledge graph; "
                f"cross-brain use routes through {CHIEF}"
            )

    @staticmethod
    def _slug(title: str) -> str:
        return re.sub(r"[^A-Za-z0-9 \-]", "", title).strip().replace(" ", "_")

    def write_page(
        self,
        agent: str,
        target: str,
        title: str,
        body: str,
        tags: list[str] | None = None,
        links: list[str] | None = None,
        date: dt.date | None = None,
    ) -> Path:
        """Write one dated page under a governed knowledge target."""
        owner = self.targets.get(target)
        if owner is None:
            raise GraphAccessDenied(f"unknown knowledge target {target!r}")
        if agent != owner:
            self._log("graph_write_denied", {"agent": agent, "target": target})
            raise GraphAccessDenied(
                f"{agent!r} is not the designated writer for {target!r} ({owner!r})"
            )
        date = date or dt.date.today()
        tag_line = " ".join(f"#{tag}" for tag in tags or [])
        link_line = " ".join(f"[[{link}]]" for link in links or [])
        content = (
            f"target:: {target}\n"
            f"author:: {agent}\n"
            f"date:: {date.isoformat()}\n\n"
            f"# {title}\n\n{body}\n\n{tag_line}\n{link_line}\n"
        )
        path = self.graph_dir / "pages" / f"{date.isoformat()}__{self._slug(title)}.md"
        path.write_text(content, encoding="utf-8")
        self._log("graph_write", {"agent": agent, "target": target, "page": path.name})
        return path

    def journal(self, agent: str, body: str, date: dt.date | None = None) -> Path:
        """Append to the dated journal page (Logseq daily-journal format)."""
        self._check_reader(agent)  # journal writes are JEOS/007 only as well
        date = date or dt.date.today()
        path = self.graph_dir / "journals" / f"{date.strftime('%Y_%m_%d')}.md"
        with path.open("a", encoding="utf-8") as sink:
            sink.write(f"- {body} (by {agent})\n")
        self._log("graph_journal", {"agent": agent, "page": path.name})
        return path

    def query_by_tag(
        self, agent: str, tag: str, since_days: int | None = None
    ) -> list[dict[str, Any]]:
        """All pages carrying #tag, optionally within the last N days."""
        self._check_reader(agent)
        cutoff = (
            dt.date.today() - dt.timedelta(days=since_days) if since_days else None
        )
        results = []
        for path in sorted((self.graph_dir / "pages").glob("*.md")):
            text = path.read_text(encoding="utf-8")
            if f"#{tag}" not in text:
                continue
            match = re.search(r"^date:: (\d{4}-\d{2}-\d{2})", text, re.MULTILINE)
            page_date = dt.date.fromisoformat(match.group(1)) if match else None
            if cutoff and page_date and page_date < cutoff:
                continue
            results.append({"page": path.name, "date": page_date, "text": text})
        self._log("graph_query", {"agent": agent, "tag": tag, "hits": len(results)})
        return results

    def backlinks(self, agent: str, title: str) -> list[str]:
        """Pages that link to [[title]]."""
        self._check_reader(agent)
        needle = f"[[{title}]]"
        return [
            path.name
            for path in sorted((self.graph_dir / "pages").glob("*.md"))
            if needle in path.read_text(encoding="utf-8")
        ]
