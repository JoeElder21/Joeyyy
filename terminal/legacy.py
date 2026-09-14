"""Read the legacy terminal page (capsule schema v43 and its boards) into store documents.

The migration is non-destructive and honest: legacy zones are carried as
``legacy_zone`` on rows whose ``scorecard`` is null and whose status is
``LEGACY_UNSCORED``. No scorecard value is invented for a row the new rubric
has not scored. Balances come only from the page's own screenshot-marked
cards, and the two Schwab accounts are kept as distinct documents even where
the legacy page pooled their positions into one book.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser

from terminal import clock, runs

CAPSULE_MARKER = "<!--ACX_CANONICAL_STATE"
RUNLOG_MARKER = "<!--ACX_RUNLOG"
MONEY = re.compile(r"\$\s?(-?[\d,]+(?:\.\d+)?)")
PERCENT = re.compile(r"(-?[\d.]+)%")
WS = re.compile(r"\s+")

BOARD_SPECS: dict[str, tuple[str, str]] = {
    "stocks": ("Board 01: stocks", "equity"),
    "crypto": ("Board 02: crypto", "crypto"),
    "pulse": ("Board 03: PulseChain", "crypto"),
    "ton": ("Board 04: TON", "crypto"),
    "memes": ("Board 05: memecoins", "meme"),
    "pumpfun": ("Board 06: pump.fun", "meme"),
    "allcoins": ("Board 13: all coins, overall", "crypto"),
    "allentry": ("Board 16: all coins, entry", "crypto"),
    "allcall": ("Board 17: the combined call", "crypto"),
}
LEGACY_SECTIONS = (
    "action",
    "expiry",
    "optimizer",
    "accounts",
    "xray",
    "ledger",
    "journal",
    "signal",
    "calendar",
    "health",
    "feed",
)
ACCOUNT_IDS: list[tuple[str, str, str, str]] = [
    ("SCHWAB ROTH", "schwab-roth", "Charles Schwab", "Roth IRA"),
    ("SCHWAB ROLLOVER", "schwab-rollover", "Charles Schwab", "Rollover IRA"),
    ("SOFI", "sofi", "SoFi", "self-directed"),
    ("PULSECHAIN", "pulsechain", "self-custody wallet", "PulseChain"),
    ("TON", "ton", "self-custody wallet", "TON"),
    ("COINBASE", "coinbase", "Coinbase", "exchange account"),
    ("PUMP.FUN", "pumpfun", "self-custody wallet", "Solana / pump.fun"),
]
BOOK_KEYWORDS: list[tuple[str, str]] = [
    ("SCHWAB", "schwab-combined"),
    ("COINBASE", "coinbase"),
    ("PULSECHAIN", "pulsechain"),
    ("TON", "ton"),
    ("PUMP.FUN", "pumpfun"),
    ("SOFI", "sofi"),
]


def has_word(text: str, needle: str) -> bool:
    """``needle`` as a whole word inside ``text`` (upper-cased comparison)."""
    return re.search(rf"(?<![A-Z]){re.escape(needle)}(?![A-Z])", text.upper()) is not None


def clean(text: str) -> str:
    return WS.sub(" ", text).strip()


@dataclass
class Table:
    header: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    row_attrs: list[dict[str, str]] = field(default_factory=list)
    heading: str = ""  # the nearest preceding h3, so tables are matched by name not position


@dataclass
class Section:
    section_id: str
    h2: str = ""
    stamp: str = ""
    sub: str = ""
    h3: list[str] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    cards: list[dict[str, str]] = field(default_factory=list)
    chips: list[str] = field(default_factory=list)
    todos: list[dict[str, str]] = field(default_factory=list)


class _PageParser(HTMLParser):
    """A small stateful walk over the legacy markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sections: dict[str, Section] = {}
        self.ticker: list[str] = []
        self.current: Section | None = None
        self.stack: list[tuple[str, str | None, list[str]]] = []
        self.table: Table | None = None
        self.row: list[str] | None = None
        self.row_attrs: dict[str, str] = {}
        self.row_is_header = False
        self.card: dict[str, str] | None = None
        self.todo: dict[str, str] | None = None
        self.last_h3 = ""

    @staticmethod
    def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        for name, value in attrs:
            if name == "class" and value:
                return set(value.split())
        return set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        classes = self._classes(attrs)
        role: str | None = None
        if tag == "section" and attr.get("id"):
            self.current = Section(attr["id"])
            self.sections[attr["id"]] = self.current
        elif self.current is not None:
            if tag == "h2":
                role = "h2"
            elif tag == "h3":
                role = "h3"
            elif tag == "span" and attr.get("data-stamp") == self.current.section_id:
                role = "stamp"
            elif tag == "div" and "sub" in classes and not self.current.sub:
                role = "sub"
            elif tag == "table":
                self.table = Table(heading=self.last_h3)
            elif tag == "tr" and self.table is not None:
                self.row = []
                self.row_attrs = {k: v for k, v in attr.items() if k.startswith("data-") and v}
                self.row_is_header = False
            elif tag in ("th", "td") and self.row is not None:
                role = tag
                if tag == "th":
                    self.row_is_header = True
            elif tag == "div" and "card" in classes:
                self.card = {"name": "", "val": "", "d": ""}
                role = "card"
            elif self.card is not None and tag == "div" and classes & {"name", "val", "d"}:
                role = "card." + sorted(classes & {"name", "val", "d"})[0]
            elif tag in ("div", "span") and "chip" in classes:
                role = "chip"
            elif tag == "div" and "todo" in classes:
                self.todo = {"title": "", "body": ""}
                role = "todo"
            elif self.todo is not None and tag == "div" and "tt" in classes:
                role = "todo.title"
            elif self.todo is not None and tag == "div" and "tw" in classes:
                role = "todo.body"
        if tag == "span" and "tk" in classes:
            role = "tk"
        if tag == "br":
            for _, r, buf in self.stack:
                if r:
                    buf.append(" ")
            return
        self.stack.append((tag, role, []))

    def handle_data(self, data: str) -> None:
        for _, role, buf in self.stack:
            if role:
                buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("br", "meta", "link", "img"):
            return
        while self.stack:
            open_tag, role, buf = self.stack.pop()
            if role:
                self._finish(role, clean("".join(buf)))
            if open_tag == tag:
                break
        if tag == "tr" and self.table is not None and self.row is not None:
            if self.row_is_header and not self.table.header:
                self.table.header = self.row
            elif not self.row_is_header:
                self.table.rows.append(self.row)
                self.table.row_attrs.append(self.row_attrs)
            self.row = None
        elif tag == "table" and self.table is not None and self.current is not None:
            self.current.tables.append(self.table)
            self.table = None

    def _finish(self, role: str, text: str) -> None:
        section = self.current
        if role == "tk":
            self.ticker.append(text)
            return
        if section is None:
            return
        if role == "h2":
            section.h2 = text
        elif role == "h3":
            section.h3.append(text)
            self.last_h3 = text
        elif role == "stamp":
            section.stamp = text
        elif role == "sub":
            section.sub = text
        elif role in ("th", "td") and self.row is not None:
            self.row.append(text)
        elif role == "card" and self.card is not None:
            section.cards.append(self.card)
            self.card = None
        elif role.startswith("card.") and self.card is not None:
            self.card[role[5:]] = text
        elif role == "chip":
            section.chips.append(text)
        elif role == "todo" and self.todo is not None:
            section.todos.append(self.todo)
            self.todo = None
        elif role == "todo.title" and self.todo is not None:
            self.todo["title"] = text
        elif role == "todo.body" and self.todo is not None:
            self.todo["body"] = text


def parse_page(html: str) -> tuple[dict[str, Section], list[str]]:
    parser = _PageParser()
    parser.feed(html)
    parser.close()
    return parser.sections, parser.ticker


def extract_capsule(html: str) -> dict:
    start = html.find(CAPSULE_MARKER)
    if start < 0:
        raise ValueError("no canonical-state capsule in the page")
    end = html.find("-->", start)
    body = html[start:end]
    brace = body.find("{")
    if brace < 0 or end < 0:
        raise ValueError("capsule is not terminated")
    return json.loads(body[brace:])


def extract_run_lines(html: str) -> list[str]:
    start = html.find(RUNLOG_MARKER)
    if start < 0:
        return []
    end = html.find("-->", start)
    return [line for line in html[start:end].splitlines() if line.startswith("RUN|")]


def money(text: str) -> float | None:
    match = MONEY.search(text)
    return float(match.group(1).replace(",", "")) if match else None


def percent(text: str) -> float | None:
    match = PERCENT.search(text.replace("−", "-"))
    return float(match.group(1)) / 100.0 if match else None


def money_text(value: float | None) -> str:
    return "n/a" if value is None else f"${value:,.2f}"


def symbol_of(cell: str) -> str:
    """``"● AAA"`` -> ``AAA``; ``"BBB L1/L2 · $1.0B"`` -> ``BBB``."""
    text = cell.replace("●", " ").strip()
    return text.split()[0] if text else ""


def _board_status(section_id: str, stamp: str, capsule: dict) -> str:
    refresh = capsule.get("lastRefresh", {})
    not_refreshed = refresh.get("boardNotRefreshed", {})
    if not_refreshed.get("board") == section_id:
        return "STALE"
    match = re.search(r"(\d+) of (\d+) (?:priced|re-priced|re-quoted)", stamp)
    if match and int(match.group(1)) < int(match.group(2)):
        return "STALE"
    reordered = set(refresh.get("boardsReordered", [])) | set(
        refresh.get("boardsRepricedInPlace", [])
    )
    if section_id in reordered or match:
        return "LIVE"
    return "STALE"


def board_doc(section_id: str, section: Section, capsule: dict, as_of: str) -> dict:
    title, kind = BOARD_SPECS[section_id]
    rows: list[dict] = []
    columns: list[str] = []
    for table in section.tables:
        header = table.header
        if not header or header[0] != "#":
            continue
        if not columns:
            columns = header
        for cells in table.rows:
            if len(cells) != len(header) or not cells[0].isdigit():
                continue
            named = dict(zip(header, cells, strict=True))
            zone = named.get("ZONE")
            case_key = header[-1]
            rows.append(
                {
                    "rank": int(cells[0]),
                    "asset_id": None,
                    "symbol": symbol_of(cells[1]),
                    "owned": "●" in cells[1],
                    "cells": {k: v for k, v in named.items() if k not in ("#", case_key)},
                    "legacy_zone": zone,
                    "scorecard": None,
                    "status": "LEGACY_UNSCORED",
                    "case": named.get(case_key),
                }
            )
    return {
        "board_id": section_id,
        "title": title,
        "kind": kind,
        "as_of": as_of,
        "status": _board_status(section_id, section.stamp, capsule),
        "stamp": section.stamp or section.h2,
        "columns": columns,
        "rows": rows,
        "notes": [
            "Migrated from the legacy page: zones and ordering are the legacy models' output, "
            "carried as legacy_zone; no row has been scored by the new rubric.",
            "asset_id is null until identity resolution assigns an exchange or contract to each row.",
        ],
        "rubric": None,
        "legacy_ordering": (capsule.get("models", {}).get("ordering", {}) or {}).get("id"),
    }


def portfolio_docs(sections: dict[str, Section], as_of: str) -> dict[str, dict]:
    accounts = sections.get("accounts")
    optimizer = sections.get("optimizer")
    docs: dict[str, dict] = {}
    if accounts is None:
        return docs
    for card in accounts.cards:
        name = card["name"].upper()
        for needle, portfolio_id, custodian, kind in ACCOUNT_IDS:
            if has_word(name, needle) and portfolio_id not in docs:
                detail = card["d"]
                cash_match = re.search(
                    r"cash\s*\$([\d,]+(?:\.\d+)?)\s*(?:=\s*[\d.]+%|\u2014\s*fully invested)",
                    detail,
                    re.IGNORECASE,
                )
                docs[portfolio_id] = {
                    "portfolio_id": portfolio_id,
                    "label": clean(card["name"]),
                    "custodian": custodian,
                    "account_kind": kind,
                    "as_of": as_of,
                    "source": "screenshot",
                    "verification": "screenshot-verified",
                    "total_value": money(card["val"]),
                    "cash_value": float(cash_match.group(1).replace(",", ""))
                    if cash_match
                    else None,
                    "cash_weight": None,
                    "day_change": None,
                    "unrealized": None,
                    "positions": [],
                    "notes": [clean(detail)],
                    "distinct_from": [],
                    "excluded_from_book": "SEP 1" in detail.upper() and "COINBASE" in name,
                }
                break
    for doc in docs.values():
        if doc["total_value"] and doc["cash_value"] is not None:
            doc["cash_weight"] = round(doc["cash_value"] / doc["total_value"], 4)
    if "schwab-roth" in docs and "schwab-rollover" in docs:
        docs["schwab-roth"]["distinct_from"] = ["schwab-rollover"]
        docs["schwab-rollover"]["distinct_from"] = ["schwab-roth"]
    if optimizer is not None:
        tables = [t for t in optimizer.tables if t.header and t.header[:2] == ["#", "POSITION"]]
        for table in tables:
            portfolio_id = next(
                (pid for needle, pid in BOOK_KEYWORDS if has_word(table.heading, needle)), None
            )
            if portfolio_id is None:
                continue
            positions = []
            for cells in table.rows:
                if len(cells) < 6:
                    continue
                now_cell = cells[2]
                positions.append(
                    {
                        "asset_id": None,
                        "symbol": symbol_of(cells[1]),
                        "quantity": None,
                        "market_value": money(now_cell),
                        "weight": percent(now_cell),
                        "cost_basis": None,
                        "unrealized": None,
                        "note": f"legacy optimizer target {cells[3]} ({cells[4]}); action {cells[6]}",
                        "legacy_zone": cells[6],
                    }
                )
            if portfolio_id == "schwab-combined":
                stated = money(table.heading)
                row_sum = round(sum(p["market_value"] or 0.0 for p in positions), 2)
                docs[portfolio_id] = {
                    "portfolio_id": portfolio_id,
                    "label": "Schwab: two IRAs pooled by the legacy optimizer",
                    "custodian": "Charles Schwab",
                    "account_kind": "legacy pooled book",
                    "as_of": as_of,
                    "source": "screenshot",
                    "verification": "screenshot-verified" if stated else "stated-unverified",
                    "total_value": stated,
                    "cash_value": None,
                    "cash_weight": None,
                    "positions": positions,
                    "notes": [
                        f"Legacy heading total {money_text(stated)}; the position rows sum to {money_text(row_sum)}.",
                        "The legacy page pooled the Roth and Rollover positions into one book; the "
                        "per-account split is not available in V53. The Roth and Rollover documents "
                        "carry their own screenshot totals and cash and take positions on the next re-mark.",
                    ],
                    "distinct_from": ["schwab-roth", "schwab-rollover"],
                }
            elif portfolio_id in docs:
                docs[portfolio_id]["positions"] = positions
    return docs


def _parse_legacy_date(text: str, year: int) -> str | None:
    match = re.match(r"([A-Z][a-z]{2}) (\d{1,2})", text.strip())
    if not match:
        return None
    try:
        moment = datetime.strptime(f"{match.group(1)} {match.group(2)} {year}", "%b %d %Y")
    except ValueError:
        return None
    return moment.date().isoformat()


def recommendation_docs(
    sections: dict[str, Section], run_id: str, as_of: str, skipped: list[str] | None = None
) -> dict[str, dict]:
    """Legacy calls as immutable WATCH records; rows whose date cannot be read are skipped
    (and listed in ``skipped``) rather than given an invented date."""
    docs: dict[str, dict] = {}
    skipped = skipped if skipped is not None else []
    allcall = sections.get("allcall")
    if allcall is None:
        return docs
    year = int(as_of[:4])
    for table in allcall.tables:
        if table.header[:2] != ["DATE", "THE CALL"]:
            continue
        for index, cells in enumerate(table.rows, start=1):
            if len(cells) != 6:
                continue
            issued = _parse_legacy_date(cells[0], year)
            if issued is None:
                skipped.append(cells[0])
                continue
            if issued > as_of[:10]:  # a December call read in January: the prior year
                issued = _parse_legacy_date(cells[0], year - 1) or issued
            check = _parse_legacy_date(cells[4], year)
            horizon = 30
            if check:
                delta = (datetime.fromisoformat(check) - datetime.fromisoformat(issued)).days
                horizon = max(1, delta)
            body = {
                "recommendation_id": f"rec-legacy-{index:03d}",
                "run_id": run_id,
                "issued_at": f"{issued}T00:00:00Z",
                "asset_id": "cash:legacy:basket",
                "symbol": f"CALL-{index:03d}",
                "portfolio_id": None,
                "stance": "WATCH",
                "horizon_days": horizon,
                "lens": "legacy",
                "reference_price": None,
                "reference_convention": "legacy: as written on the board, no tradable reference recorded",
                "scorecard": None,
                "scenarios": None,
                "hurdle_cleared": None,
                "rationale": cells[2],
                "evidence_ids": [],
                "risks": [],
                "invalidation": [],
                "critic": None,
                "cooling_period_ends": None,
                "legacy": {
                    "date": cells[0],
                    "call": cells[1],
                    "basis": cells[2],
                    "expected": cells[3],
                    "check": cells[4],
                    "result": cells[5],
                },
            }
            body["content_sha"] = runs.sha256_of(body)
            docs[body["recommendation_id"]] = body
    return docs


def outcome_docs(sections: dict[str, Section], as_of: str) -> dict[str, dict]:
    docs: dict[str, dict] = {}
    ledger = sections.get("ledger")
    if ledger is None:
        return docs
    for table in ledger.tables:
        if table.header[:2] != ["CALL", "WHAT WAS SAID"]:
            continue
        for index, cells in enumerate(table.rows, start=1):
            if len(cells) != 4:
                continue
            docs[f"legacy-{index:03d}"] = {
                "outcome_id": f"legacy-{index:03d}",
                "recommendation_id": f"rec-legacy-ledger-{index:03d}",
                "graded_at": as_of,
                "status": "LEGACY",
                "benchmark": "n/a (legacy ledger; graded in prose)",
                "note": cells[3],
                "legacy": {
                    "call": cells[0],
                    "said": cells[1],
                    "happened": cells[2],
                    "score": cells[3],
                },
            }
    return docs


def learning_doc(capsule: dict, as_of: str) -> dict:
    last = capsule.get("lastAction", {})
    windows = []
    for board, buckets in (last.get("scorecard") or {}).items():
        parsed = {}
        for zone, pair in buckets.items():
            mean, n = (pair + [None, None])[:2] if isinstance(pair, list) else (None, None)
            parsed[zone] = {"mean_return": mean, "n": int(n or 0)}
        buy = (parsed.get("BUY") or {}).get("mean_return")
        wait = (parsed.get("WAIT") or {}).get("mean_return")
        if buy is None or wait is None:
            verdict = "NOT COMPARABLE (a tier has no observations)"
        else:
            verdict = "INVERTED (BUY trailed WAIT)" if buy < wait else "ALIGNED (BUY led WAIT)"
        windows.append(
            {
                "board": board,
                "window": "legacy one-day zone scorecard at migration",
                "buckets": parsed,
                "verdict": verdict,
                "streak": None,
            }
        )
    return {
        "as_of": as_of,
        "windows": windows,
        "hit_rates": {},
        "brier": None,
        "lessons": [
            {
                "date": as_of[:10],
                "text": "Legacy zone scorecards were one-day tier returns; the new loop grades each "
                "recommendation against a tradable reference and the benchmark over its horizon.",
                "evidence_ids": [],
            }
        ],
        "model_changes": [
            {
                "date": as_of[:10],
                "change": "Migration: legacy models recorded under policy.legacy_models; no model promoted.",
                "approved_by": None,
            }
        ],
        "legacy_scorecard_record": last.get("scorecardRecord"),
    }


def legacy_section_docs(sections: dict[str, Section], ticker: list[str]) -> dict[str, dict]:
    docs: dict[str, dict] = {}
    for section_id in LEGACY_SECTIONS:
        section = sections.get(section_id)
        if section is None:
            continue
        docs[section_id] = {
            "section_id": section_id,
            "h2": section.h2,
            "stamp": section.stamp,
            "sub": section.sub,
            "h3": section.h3,
            "tables": [{"header": t.header, "rows": t.rows} for t in section.tables],
            "cards": section.cards,
            "chips": section.chips,
            "todos": section.todos,
        }
    docs["ticker"] = {"section_id": "ticker", "items": list(dict.fromkeys(ticker))}
    return docs


def migrate(html: str, now: datetime, writer: str = "CHAT") -> dict[str, dict]:
    """Every document the migration produces, keyed by store path."""
    capsule = extract_capsule(html)
    sections, ticker = parse_page(html)
    generated = capsule.get("meta", {}).get("generatedAtUTC") or clock.to_utc(now).isoformat()
    as_of = generated.replace("+00:00", "Z")
    run_lines = extract_run_lines(html)
    records = [runs.parse_run_line(line) for line in run_lines]
    chain = runs.verify_chain(records)
    key = runs.idempotency_key(
        "migration", now, f"v43-{capsule.get('meta', {}).get('artifactVersion', 'unknown')}"
    )
    migration_run = runs.run_id("migration", key)

    docs: dict[str, dict] = {}
    for section_id in BOARD_SPECS:
        if section_id in sections:
            docs[f"boards/{section_id}"] = board_doc(
                section_id, sections[section_id], capsule, as_of
            )
    for portfolio_id, doc in portfolio_docs(sections, as_of).items():
        docs[f"portfolios/{portfolio_id}"] = doc
    skipped_calls: list[str] = []
    for rec_id, doc in recommendation_docs(sections, migration_run, as_of, skipped_calls).items():
        docs[f"recommendations/{rec_id}"] = doc
    for outcome_id, doc in outcome_docs(sections, as_of).items():
        docs[f"outcomes/{outcome_id}"] = doc
    for section_id, doc in legacy_section_docs(sections, ticker).items():
        docs[f"legacy/{section_id}"] = doc
    docs["learning/current"] = learning_doc(capsule, as_of)
    docs["runs/legacy-chain"] = {
        "records": records,
        "chain_ok": chain.ok,
        "breaks": chain.breaks,
        "duplicates": chain.duplicates,
        "source": "legacy ACX_RUNLOG region",
    }
    docs["legacy/capsule"] = {
        "schema_version": capsule.get("meta", {}).get("schemaVersion"),
        "artifact_version": capsule.get("meta", {}).get("artifactVersion"),
        "generated_at": as_of,
        "governance": capsule.get("governance", {}),
        "models": capsule.get("models", {}),
        "opportunity_quality": capsule.get("opportunityQuality", {}),
        "counts": capsule.get("counts", {}),
        "last_refresh": capsule.get("lastRefresh", {}),
        "page_invariants": capsule.get("pageInvariants", {}),
        "ranked_rows": capsule.get("rows", []),
    }
    docs["legacy/gates"] = {
        "gates": capsule.get("gates", {}),
        "gates_this_run": capsule.get("gatesThisRun", {}),
    }
    manifest = runs.RunManifest(
        run_id=migration_run,
        kind="migration",
        idempotency_key=key,
        writer=writer,
        scheduled_at=clock.to_utc(now).isoformat().replace("+00:00", "Z"),
        started_at=clock.to_utc(now).isoformat().replace("+00:00", "Z"),
        ready_at=clock.to_utc(now).isoformat().replace("+00:00", "Z"),
        base_sha=next(
            (r["result_sha"] for r in reversed(records) if r["status"] == "PUBLISHED"), None
        ),
        status="PUBLISHED",
        rows=sum(len(d.get("rows", [])) for p, d in docs.items() if p.startswith("boards/")),
        notes=[
            f"migrated from {capsule.get('meta', {}).get('artifactVersion')} capsule {capsule.get('meta', {}).get('schemaVersion')}"
        ]
        + (
            [f"legacy calls skipped (unreadable date): {', '.join(skipped_calls)}"]
            if skipped_calls
            else []
        ),
    )
    boards_status = {
        p.split("/")[1]: d["status"] for p, d in docs.items() if p.startswith("boards/")
    }
    docs["policy/current"] = migration_policy(capsule, as_of)
    docs["health/current"] = {
        "as_of": as_of,
        "run_id": migration_run,
        "boards": {
            board_id: {
                "status": status,
                "stamp": docs[f"boards/{board_id}"]["stamp"],
                "rows_total": len(docs[f"boards/{board_id}"]["rows"]),
                "source": "legacy page (carried unscored)",
            }
            for board_id, status in boards_status.items()
        },
        "schedule": [
            {
                "name": entry["name"],
                "cron_utc": entry["cron_utc"],
                "target_et": entry["target_et"],
                "dst_drift": _drift_for(entry, now),
                "last_starts_vs_ready": None,
            }
            for entry in docs["policy/current"]["schedule"]["runs"]
        ],
        "calendar_covered_through": clock.calendar_covered_through(),
        "store": {"mode": "embedded-snapshot", "documents": len(docs) + 3},
        "page_bytes": 0,
        "chain": {"ok": chain.ok, "length": chain.length, "breaks": chain.breaks[:10]},
        "notes": [
            "Migrated snapshot: every board is carried from the legacy page and none has been "
            "re-fetched; statuses reflect the legacy stamps at migration time.",
            f"Legacy run chain: {len(chain.breaks)} of {max(chain.length - 1, 0)} links do not verify "
            "under base = previous result; see docs/TERMINAL_AUDIT.md.",
        ],
    }
    manifest.result_sha = runs.sha256_of(dict(docs))
    docs[f"runs/{migration_run}"] = manifest.as_dict() | {
        "starts_vs_ready": clock.starts_vs_ready(now, now).label,
        "boards": boards_status,
        "stages": [{"name": "migration", "status": "OK", "detail": "legacy page parsed"}],
    }
    parts = {path: doc for path, doc in docs.items() if not path.startswith("snapshots/")}
    version = f"{capsule.get('meta', {}).get('artifactVersion', 'legacy')}-migration"
    docs["snapshots/current"] = runs.build_snapshot(parts, now, version, manifest.base_sha) | {
        "run_id": migration_run,
        "starts_vs_ready": clock.starts_vs_ready(now, now).label,
    }
    return docs


def _drift_for(entry: dict, now: datetime) -> list[dict]:
    parts = entry["cron_utc"].split()
    if len(parts) != 5 or not (parts[0].isdigit() and parts[1].isdigit()):
        return []
    if ":" not in entry["target_et"]:
        return []
    hour, minute = (int(x) for x in entry["target_et"].split(":"))
    target = datetime.min.time().replace(hour=hour, minute=minute)
    year = clock.to_et(now).year
    return [
        {"starts": w.starts.isoformat(), "ends": w.ends.isoformat(), "fires_at_et": w.fires_at_et}
        for w in clock.dst_drift(int(parts[1]), int(parts[0]), target, year)
    ]


def migration_policy(capsule: dict, as_of: str) -> dict:
    """The default policy with the legacy models recorded beside it, never promoted."""
    from terminal import pipeline  # local import: pipeline does not import this module

    policy = pipeline.default_policy(as_of)
    policy["legacy_models"] = {
        "capsule_schema": capsule.get("meta", {}).get("schemaVersion"),
        "models": capsule.get("models", {}),
        "opportunity_quality": capsule.get("opportunityQuality", {}),
        "note": "Recorded for continuity; the new rubric does not use these weights.",
    }
    return policy
