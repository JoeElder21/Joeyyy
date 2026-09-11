"""Render the Revamped Edition page from store documents.

The page is built server-side from the documents, so everything a reader
needs is visible at rest without JavaScript. The embedded snapshot and the
optional artifact-db hookup let a viewer see whether the store holds a newer
snapshot than the one the page was built from.
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from typing import Any

from terminal import clock

TITLE = "Savage Terminal R2"
VIEWS: list[tuple[str, str]] = [
    ("today", "Today"),
    ("stocks", "Stock rankings"),
    ("crypto", "Crypto rankings"),
    ("portfolio-1", "Portfolio 1"),
    ("portfolio-2", "Portfolio 2"),
    ("accounts", "Other accounts"),
    ("assets", "Asset detail"),
    ("risk", "Risk and catalysts"),
    ("critic", "Critic"),
    ("performance", "Performance"),
    ("history", "History / as-built"),
    ("learning", "Memory / learning"),
    ("health", "Sources / health"),
]
LEGACY_CRYPTO_BOARDS = (
    "crypto",
    "memes",
    "pumpfun",
    "ton",
    "pulse",
    "allcoins",
    "allentry",
    "allcall",
)
MINUS = "−"


def esc(value: Any) -> str:
    if value is None:
        return "n/a"
    return html.escape(str(value), quote=True)


def money(value: float | None) -> str:
    if value is None:
        return "n/a"
    sign = MINUS if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def pct(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    sign = MINUS if value < 0 else "+"
    return f"{sign}{abs(value) * 100:.{digits}f}%"


def pill(status: str | None) -> str:
    status = status or "n/a"
    return f'<span class="pill s-{esc(status).lower().replace(" ", "-")}">{esc(status)}</span>'


def table(
    columns: list[str], rows: list[list[str]], *, wide: bool = False, board_id: str | None = None
) -> str:
    head = "".join(f"<th>{esc(c)}</th>" for c in columns)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    attr = f' data-board="{esc(board_id)}"' if board_id else ""
    cls = "tbl wide" if wide else "tbl"
    return f'<div class="tblwrap"><table class="{cls}"{attr}><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def kv(pairs: list[tuple[str, str]]) -> str:
    return '<dl class="kv">' + "".join(f"<dt>{esc(k)}</dt><dd>{v}</dd>" for k, v in pairs) + "</dl>"


def card(title: str, value: str, detail: str = "", tone: str = "") -> str:
    return f'<div class="card {tone}"><div class="c-name">{esc(title)}</div><div class="c-val">{value}</div><div class="c-d">{detail}</div></div>'


def note(text: str, tone: str = "") -> str:
    return f'<p class="note {tone}">{text}</p>'


def stamp_of(text: str | None) -> str:
    if not text:
        return "n/a"
    try:
        return clock.stamp(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        return esc(text)


def latest_run(docs: dict[str, dict]) -> dict | None:
    candidates = [d for p, d in docs.items() if p.startswith("runs/") and "idempotency_key" in d]
    if not candidates:
        return None
    return sorted(candidates, key=lambda d: d.get("started_at", ""))[-1]


def board_table(doc: dict) -> str:
    columns = [c for c in doc.get("columns", []) if c not in ("#",)]
    legacy = doc.get("rows") and doc["rows"][0].get("status") == "LEGACY_UNSCORED"
    symbol_col = columns[0] if legacy and columns else None
    case_col = (
        columns[-1] if legacy and columns and columns[-1].upper().startswith("THE ") else None
    )
    data_cols = [c for c in columns if c not in (symbol_col, case_col)]
    header = ["#", "ASSET", *data_cols, "STATUS"] + (["THE CASE"] if case_col else [])
    rows = []
    for row in doc.get("rows", []):
        cells = row.get("cells", {})
        sym = ("<b class='own'>●</b> " if row.get("owned") else "") + esc(row.get("symbol"))
        line = [esc(row.get("rank") or ""), sym]
        for col in data_cols:
            value = cells.get(col)
            if isinstance(value, float):
                value = f"{value:g}"
            line.append(
                esc(value).replace("-", MINUS)
                if col in ("DAY", "WEEK", "30D", "24h", "7d", "30d", "ATH")
                else esc(value)
            )
        status = row.get("status")
        zone = row.get("legacy_zone")
        line.append(
            pill(zone) + " <span class='muted'>legacy zone</span>"
            if status == "LEGACY_UNSCORED" and zone
            else pill(status)
        )
        if case_col:
            line.append(f"<div class='case'>{esc(row.get('case'))}</div>")
        rows.append(line)
    return table(header, rows, wide=True, board_id=doc.get("board_id"))


def board_section(doc: dict, heading: str | None = None) -> str:
    status = doc.get("status", "STALE")
    banner_cls = {"LIVE": "ok", "STALE": "warn", "DEGRADED": "bad"}.get(status, "warn")
    notes = "".join(note(esc(n), "muted") for n in doc.get("notes", []))
    rubric = doc.get("rubric")
    rubric_line = ""
    if rubric:
        rubric_line = note(
            f"Rubric {esc(rubric)}"
            + (" <b>(PROPOSED, not adopted)</b>" if "PROPOSED" in rubric else " (adopted)"),
            "muted",
        )
    elif doc.get("legacy_ordering"):
        rubric_line = note(
            f"Legacy ordering {esc(doc['legacy_ordering'])}; rows are carried unscored", "muted"
        )
    return (
        f'<article class="board" id="board-{esc(doc.get("board_id"))}">'
        f"<h3>{esc(heading or doc.get('title'))} {pill(status)}</h3>"
        f'<p class="banner {banner_cls}">{esc(doc.get("stamp"))}</p>'
        f"{rubric_line}{board_table(doc)}{notes}</article>"
    )


def legacy_tables(doc: dict | None, limit: int | None = None, heading: str = "") -> str:
    if not doc:
        return note("Not available in this snapshot.", "muted")
    out = []
    if heading:
        out.append(f"<h3>{esc(heading)}</h3>")
    if doc.get("stamp"):
        out.append(note(f"Carried from the legacy page as of {esc(doc['stamp'])}", "muted"))
    for tbl in doc.get("tables", []):
        rows = tbl.get("rows", [])
        shown = rows[:limit] if limit else rows
        out.append(table(tbl.get("header", []), [[esc(c) for c in r] for r in shown], wide=True))
        if limit and len(rows) > limit:
            out.append(note(f"{len(rows) - limit} more rows in the store document", "muted"))
    return "".join(out)


def view_today(docs: dict[str, dict]) -> str:
    run = latest_run(docs)
    health = docs.get("health/current", {})
    out = []
    if run:
        tone = {"PUBLISHED": "ok", "BLOCKED": "bad", "SKIPPED": "warn", "FAILED": "bad"}.get(
            run.get("status"), "warn"
        )
        out.append('<div class="cards">')
        out.append(
            card(
                "Latest run",
                pill(run.get("status")),
                f"{esc(run.get('kind'))} · {esc(run.get('idempotency_key'))} · writer {esc(run.get('writer'))}",
                tone,
            )
        )
        out.append(
            card(
                "Starts vs ready",
                esc(run.get("starts_vs_ready") or "n/a"),
                f"scheduled {stamp_of(run.get('scheduled_at'))}",
            )
        )
        out.append(
            card(
                "Run id",
                f"<code>{esc(run.get('run_id'))}</code>",
                f"result {esc((run.get('result_sha') or '')[:12])}",
            )
        )
        if run.get("failure_injected"):
            out.append(
                card(
                    "Failure injection",
                    esc(run["failure_injected"]),
                    "this run exercised a failure path on purpose",
                    "warn",
                )
            )
        out.append("</div>")
    boards = health.get("boards", {})
    if boards:
        out.append(
            "<h3>Board status</h3><p class='pills'>"
            + " ".join(
                f"<span class='bp'>{esc(b)} {pill(v.get('status'))}</span>"
                for b, v in sorted(boards.items())
            )
            + "</p>"
        )
    if run and run.get("gates"):
        out.append("<h3>Release gates</h3>")
        out.append(
            table(
                ["GATE", "RESULT", "DETAIL"],
                [
                    [esc(g["name"]), pill("PASS" if g["passed"] else "FAIL"), esc(g["detail"])]
                    for g in run["gates"]
                ],
            )
        )
    recs = [
        d
        for p, d in docs.items()
        if p.startswith("recommendations/")
        and run
        and d.get("run_id") == run.get("run_id")
        and d.get("lens") != "legacy"
    ]
    legacy_calls = [
        d
        for p, d in sorted(docs.items())
        if p.startswith("recommendations/") and d.get("lens") == "legacy"
    ]
    out.append("<h3>Recommendations from this run</h3>")
    if recs:
        rows = []
        for rec in sorted(recs, key=lambda r: -((r.get("scorecard") or {}).get("score") or 0)):
            sc = rec.get("scorecard") or {}
            rows.append(
                [
                    esc(rec["symbol"]),
                    pill(rec["stance"]),
                    esc(sc.get("score")),
                    esc(f"{sc.get('coverage', 0):.0%}" if sc else "n/a"),
                    esc(
                        "YES"
                        if rec.get("hurdle_cleared")
                        else ("NO" if rec.get("hurdle_cleared") is False else "n/a")
                    ),
                    esc(len(rec.get("evidence_ids", []))),
                    esc((rec.get("critic") or {}).get("verdict")),
                    stamp_of(rec.get("cooling_period_ends"))
                    if rec.get("cooling_period_ends")
                    else "n/a",
                ]
            )
        out.append(
            table(
                [
                    "ASSET",
                    "STANCE",
                    "SCORE",
                    "COVERAGE",
                    "HURDLE",
                    "SOURCES",
                    "CRITIC",
                    "COOLING ENDS",
                ],
                rows,
            )
        )
        out.append(
            note(
                "Research only. Nothing here is an order; BUY and ADD stances open a 24-hour cooling period before any purchase decision.",
                "muted",
            )
        )
    else:
        out.append(
            note(
                "No recommendation was issued by the latest run (blocked, skipped, or nothing cleared the ladder).",
                "warn",
            )
        )
    if run and run.get("risk"):
        out.append("<h3>Portfolio limits</h3>")
        out.append(
            table(
                ["PORTFOLIO", "STATUS", "POSITIONS", "LARGEST", "CASH", "BREACHES"],
                [
                    [
                        esc(r["label"]),
                        pill(r["status"]),
                        esc(r["positions"]),
                        esc(
                            f"{r['largest']['asset']} {pct(r['largest']['weight'])}"
                            if r["largest"]["asset"]
                            else "n/a"
                        ),
                        esc(pct(r.get("cash_weight"))),
                        esc("; ".join(r["breaches"]) or "none"),
                    ]
                    for r in run["risk"]
                ],
            )
        )
    if legacy_calls:
        out.append("<h3>Legacy calls carried (graded by date on the legacy board)</h3>")
        rows = [
            [
                esc(d["legacy"]["date"]),
                f"<div class='case'>{esc(d['legacy']['call'])}</div>",
                esc(d["legacy"]["expected"]),
                esc(d["legacy"]["check"]),
                pill(d["legacy"]["result"]),
            ]
            for d in legacy_calls
        ]
        out.append(table(["DATE", "THE CALL", "EXPECTED", "CHECK", "RESULT"], rows, wide=True))
    action = docs.get("legacy/action")
    if action and action.get("todos"):
        out.append(
            f"<h3>Carried from the legacy page</h3>{note('As of ' + esc(action.get('stamp')) + '. These items were written by the legacy run and are shown unchanged.', 'muted')}"
        )
        out.append(
            "<ol class='todos'>"
            + "".join(
                f"<li><b>{esc(t['title'])}</b><div class='case'>{esc(t['body'])}</div></li>"
                for t in action["todos"]
            )
            + "</ol>"
        )
    ticker = docs.get("legacy/ticker", {}).get("items", [])
    if ticker:
        out.append(
            "<h3>Legacy ticker</h3><ul class='ticker'>"
            + "".join(f"<li>{esc(t)}</li>" for t in ticker[:12])
            + "</ul>"
        )
    return "".join(out)


def view_stocks(docs: dict[str, dict]) -> str:
    out = []
    ranking = docs.get("boards/rankings-equity")
    out.append(
        board_section(ranking)
        if ranking
        else note("No scorecard ranking has been produced yet.", "warn")
    )
    legacy = docs.get("boards/stocks")
    if legacy:
        out.append(board_section(legacy, "Legacy Board 01 (unscored, carried)"))
    return "".join(out)


def view_crypto(docs: dict[str, dict]) -> str:
    out = []
    ranking = docs.get("boards/rankings-crypto")
    out.append(
        note(
            "The crypto rubric is PROPOSED and awaits approval; scores from it are shown for review, not for action.",
            "warn",
        )
    )
    out.append(
        board_section(ranking)
        if ranking
        else note("No crypto scorecard ranking has been produced yet.", "warn")
    )
    for board_id in LEGACY_CRYPTO_BOARDS:
        doc = docs.get(f"boards/{board_id}")
        if doc:
            out.append(board_section(doc, f"Legacy {doc.get('title')} (unscored, carried)"))
    return "".join(out)


def portfolio_block(docs: dict[str, dict], portfolio_id: str) -> str:
    doc = docs.get(f"portfolios/{portfolio_id}")
    if not doc:
        return note(f"Portfolio {esc(portfolio_id)} is not in this snapshot.", "warn")
    run = latest_run(docs) or {}
    risk = next((r for r in run.get("risk", []) if r["portfolio_id"] == portfolio_id), None)
    out = [f"<h3>{esc(doc.get('label'))}</h3>", '<div class="cards">']
    out.append(
        card(
            "Total value",
            esc(money(doc.get("total_value"))),
            f"{esc(doc.get('custodian'))} · {esc(doc.get('account_kind'))}",
        )
    )
    out.append(card("Cash", esc(money(doc.get("cash_value"))), esc(pct(doc.get("cash_weight")))))
    out.append(
        card(
            "Marked",
            stamp_of(doc.get("as_of")),
            f"{esc(doc.get('source'))} · {esc(doc.get('verification'))}",
        )
    )
    if risk:
        out.append(
            card(
                "Limits",
                pill(risk["status"]),
                esc("; ".join(risk["breaches"]) or "within policy"),
                "warn" if risk["breaches"] else "ok",
            )
        )
    out.append("</div>")
    if doc.get("distinct_from"):
        out.append(
            note("Kept distinct from: " + ", ".join(esc(x) for x in doc["distinct_from"]), "muted")
        )
    positions = doc.get("positions", [])
    if positions:
        out.append(
            table(
                ["ASSET", "VALUE", "WEIGHT", "LEGACY ACTION", "NOTE"],
                [
                    [
                        esc(p["symbol"]),
                        esc(money(p.get("market_value"))),
                        esc(pct(p.get("weight"))),
                        pill(p.get("legacy_zone")) if p.get("legacy_zone") else "n/a",
                        esc(p.get("note", "")),
                    ]
                    for p in positions
                ],
                wide=True,
            )
        )
    else:
        out.append(
            note(
                "No position rows in this document. Balances update only from screenshots; positions arrive on the next re-mark.",
                "warn",
            )
        )
    for text in doc.get("notes", []):
        out.append(note(esc(text), "muted"))
    return "".join(out)


def view_portfolio(docs: dict[str, dict], portfolio_id: str, pooled: str | None = None) -> str:
    out = [portfolio_block(docs, portfolio_id)]
    own_positions = docs.get(f"portfolios/{portfolio_id}", {}).get("positions")
    if pooled is None and "portfolios/schwab-combined" in docs and not own_positions:
        out.append(
            note(
                "The legacy pooled Schwab book is shown once, under Portfolio 1; this account's "
                "own positions arrive on the next screenshots.",
                "muted",
            )
        )
    if pooled and f"portfolios/{pooled}" in docs and not own_positions:
        out.append(
            "<h3>Pooled legacy book</h3>"
            + note(
                "The legacy page carried the Roth and Rollover positions as one book. Shown here "
                "for continuity; the split is not available until the next screenshots.",
                "warn",
            )
        )
        out.append(portfolio_block(docs, pooled))
    return "".join(out)


def view_accounts(docs: dict[str, dict]) -> str:
    ids = sorted(
        p.split("/")[1]
        for p in docs
        if p.startswith("portfolios/")
        and p.split("/")[1] not in ("schwab-roth", "schwab-rollover", "schwab-combined")
    )
    if not ids:
        return note("No other accounts in this snapshot.", "muted")
    return "".join(portfolio_block(docs, pid) for pid in ids)


def view_assets(docs: dict[str, dict]) -> str:
    securities = [d for p, d in sorted(docs.items()) if p.startswith("security/")]
    if not securities:
        return note("No security research documents in this snapshot.", "muted")
    out = []
    for sec in securities:
        sc = sec.get("scorecard")
        gate = sec.get("gate", {})
        out.append(
            f"<article class='asset'><h3>{esc(sec['symbol'])} <code>{esc(sec['asset_id'])}</code> {pill('GATE PASS' if gate.get('passed') else 'EXCLUDED')}</h3>"
        )
        out.append(
            kv(
                [
                    ("Class", esc(sec.get("asset_class"))),
                    ("Identity", esc(json.dumps(sec.get("identity", {})))),
                    ("As of", stamp_of(sec.get("as_of"))),
                    ("Failed gates", esc(", ".join(gate.get("failed", [])) or "none")),
                ]
            )
        )
        if sc:
            rows = [
                [esc(f), esc(v if v is not None else "unscored")]
                for f, v in sc.get("factors", {}).items()
            ]
            out.append(table(["FACTOR", "VALUE 0-1"], rows))
            out.append(
                note(
                    f"{esc(sc.get('rubric'))} ({esc(sc.get('rubric_status'))}) · status {esc(sc.get('status'))} · score {esc(sc.get('score'))} · coverage {sc.get('coverage', 0):.0%} · digest {esc(sc.get('input_digest'))}",
                    "muted",
                )
            )
        scen = sec.get("scenarios")
        if scen:
            out.append(
                table(
                    ["SCENARIO", "RETURN"],
                    [[esc(k), esc(pct(v))] for k, v in scen.get("by_scenario", {}).items()],
                )
            )
            out.append(
                note(
                    f"Expected {esc(pct(scen.get('expected')))} against a {scen.get('hurdle', 0):.0%} hurdle: {'clears' if scen.get('hurdle_cleared') else 'does not clear'}. Probabilities are stated assumptions, not measured frequencies.",
                    "muted",
                )
            )
        facts = sec.get("facts", [])
        if facts:
            out.append(
                table(
                    ["FACT", "VALUE", "LABEL", "EVIDENCE"],
                    [
                        [
                            esc(f["key"]),
                            esc(f["value"]),
                            pill(f["label"]),
                            esc(f.get("evidence_id")),
                        ]
                        for f in facts
                    ],
                )
            )
        cats = sec.get("catalysts", [])
        if cats:
            out.append(
                "<ul>"
                + "".join(
                    f"<li>{esc(c.get('date') or 'undated')}: {esc(c['text'])} <span class='muted'>{esc(c.get('evidence_id') or '')}</span></li>"
                    for c in cats
                )
                + "</ul>"
            )
        for text in sec.get("notes", []):
            out.append(note(esc(text), "muted"))
        out.append("</article>")
    return "".join(out)


def view_risk(docs: dict[str, dict]) -> str:
    run = latest_run(docs) or {}
    out = []
    if run.get("risk"):
        out.append("<h3>Portfolio limits, each portfolio on its own</h3>")
        out.append(
            table(
                ["PORTFOLIO", "STATUS", "LARGEST", "CASH", "BREACHES", "VERIFICATION"],
                [
                    [
                        esc(r["label"]),
                        pill(r["status"]),
                        esc(
                            f"{r['largest']['asset']} {pct(r['largest']['weight'])}"
                            if r["largest"]["asset"]
                            else "n/a"
                        ),
                        esc(pct(r.get("cash_weight"))),
                        esc("; ".join(r["breaches"]) or "none"),
                        esc(r.get("verification")),
                    ]
                    for r in run["risk"]
                ],
            )
        )
    excluded = [
        d
        for p, d in docs.items()
        if p.startswith("security/") and not d.get("gate", {}).get("passed", True)
    ]
    if excluded:
        out.append(
            "<h3>Fatal-risk exclusions</h3><ul>"
            + "".join(
                f"<li><b>{esc(d['symbol'])}</b>: {esc(', '.join(d['gate'].get('failed', [])))}</li>"
                for d in excluded
            )
            + "</ul>"
        )
    out.append(legacy_tables(docs.get("legacy/calendar"), heading="Exposure calendar (legacy)"))
    out.append(legacy_tables(docs.get("legacy/xray"), heading="Exposure stack (legacy X-ray)"))
    return "".join(out)


def view_critic(docs: dict[str, dict]) -> str:
    run = latest_run(docs) or {}
    debate = run.get("debate")
    if not debate:
        return note("No critic record in this snapshot.", "muted")
    out = [
        f"<h3>Verdict {pill(debate.get('verdict'))} after {esc(debate.get('rounds'))} round(s)</h3>"
    ]
    if debate.get("open_blocking"):
        out.append(
            note("Open blocking challenges: " + esc(", ".join(debate["open_blocking"])), "bad")
        )
    for rnd in debate.get("transcript", []):
        out.append(f"<h4>Round {esc(rnd.get('round'))}</h4>")
        out.append(
            table(
                ["TARGET", "OBJECTION", "SEVERITY", "EVIDENCE"],
                [
                    [
                        esc(c["target"]),
                        esc(c["objection"]),
                        pill(c["severity"]),
                        esc(", ".join(c.get("evidence_ids", [])) or "judgment"),
                    ]
                    for c in rnd.get("challenges", [])
                ]
                or [["n/a", "no challenges", "", ""]],
            )
        )
        if rnd.get("responses"):
            out.append(
                table(
                    ["TARGET", "DISPOSITION", "RATIONALE", "EVIDENCE"],
                    [
                        [
                            esc(r["target"]),
                            pill(r["disposition"]),
                            esc(r["rationale"]),
                            esc(", ".join(r.get("evidence_ids", []))),
                        ]
                        for r in rnd["responses"]
                    ],
                )
            )
    out.append(
        note(
            "The critic can challenge but never edit. After two rounds an unresolved blocking challenge stops the release.",
            "muted",
        )
    )
    return "".join(out)


def view_performance(docs: dict[str, dict]) -> str:
    learning = docs.get("learning/current", {})
    out = []
    rates = learning.get("hit_rates", {})
    if rates:
        out.append("<h3>Hit rates by run</h3>")
        out.append(
            table(
                ["RUN", "GRADED", "HITS", "MISSES", "HIT RATE", "OPEN", "VOID"],
                [
                    [
                        esc(k),
                        esc(v.get("graded")),
                        esc(v.get("hits")),
                        esc(v.get("misses")),
                        esc(pct(v.get("hit_rate"))),
                        esc(v.get("open")),
                        esc(v.get("void")),
                    ]
                    for k, v in rates.items()
                ],
            )
        )
    graded = [
        d
        for p, d in sorted(docs.items())
        if p.startswith("outcomes/") and d.get("status") != "LEGACY"
    ]
    if graded:
        out.append("<h3>Graded outcomes</h3>")
        out.append(
            table(
                [
                    "RECOMMENDATION",
                    "STATUS",
                    "REFERENCE",
                    "REALIZED",
                    "BENCHMARK",
                    "RELATIVE",
                    "NOTE",
                ],
                [
                    [
                        esc(d["recommendation_id"]),
                        pill(d["status"]),
                        esc(d.get("reference_price")),
                        esc(pct(d.get("realized_return"))),
                        esc(pct(d.get("benchmark_return"))),
                        esc(pct(d.get("relative_return"))),
                        esc(d.get("note", "")),
                    ]
                    for d in graded
                ],
            )
        )
    legacy_outcomes = [
        d
        for p, d in sorted(docs.items())
        if p.startswith("outcomes/") and d.get("status") == "LEGACY"
    ]
    if legacy_outcomes:
        out.append("<h3>Legacy calls ledger (graded in prose by the legacy run)</h3>")
        out.append(
            table(
                ["CALL", "WHAT WAS SAID", "WHAT HAPPENED", "SCORE"],
                [
                    [
                        esc(d["legacy"]["call"]),
                        f"<div class='case'>{esc(d['legacy']['said'])}</div>",
                        f"<div class='case'>{esc(d['legacy']['happened'])}</div>",
                        esc(d["legacy"]["score"]),
                    ]
                    for d in legacy_outcomes
                ],
                wide=True,
            )
        )
    out.append(legacy_tables(docs.get("legacy/journal"), heading="Decision journal (legacy)"))
    return "".join(out) or note("Nothing graded yet.", "muted")


def view_history(docs: dict[str, dict]) -> str:
    out = []
    snap = docs.get("snapshots/current")
    if snap:
        out.append(
            kv(
                [
                    ("Snapshot", esc(snap.get("version"))),
                    ("Generated", stamp_of(snap.get("generated_at"))),
                    ("Snapshot sha", f"<code>{esc(snap.get('sha'))}</code>"),
                    (
                        "Built on",
                        f"<code>{esc(snap.get('base_sha') or 'none (first snapshot)')}</code>",
                    ),
                    ("Documents", esc(len(snap.get("parts", {})))),
                ]
            )
        )
    run_docs = sorted(
        (d for p, d in docs.items() if p.startswith("runs/") and "idempotency_key" in d),
        key=lambda d: d.get("started_at", ""),
        reverse=True,
    )
    if run_docs:
        out.append("<h3>Runs</h3>")
        out.append(
            table(
                [
                    "RUN",
                    "KIND",
                    "KEY",
                    "WRITER",
                    "SCHEDULED",
                    "READY",
                    "STATUS",
                    "BASE",
                    "RESULT",
                    "ROWS",
                ],
                [
                    [
                        f"<code>{esc(d['run_id'])}</code>",
                        esc(d["kind"]),
                        esc(d["idempotency_key"]),
                        esc(d["writer"]),
                        stamp_of(d.get("scheduled_at")),
                        stamp_of(d.get("ready_at")),
                        pill(d["status"]),
                        esc((d.get("base_sha") or "")[:10]),
                        esc((d.get("result_sha") or "")[:10]),
                        esc(d.get("rows")),
                    ]
                    for d in run_docs
                ],
                wide=True,
            )
        )
    chain = docs.get("runs/legacy-chain")
    if chain:
        records = chain.get("records", [])
        out.append(
            f"<h3>Legacy run chain {pill('INTACT' if chain.get('chain_ok') else 'BROKEN')}</h3>"
        )
        out.append(
            note(
                f"{len(records)} RUN records carried from the legacy page; the last {min(15, len(records))} are shown.",
                "muted",
            )
        )
        out.append(
            table(
                ["RUN", "WRITER", "SCHEDULED", "KEY", "READY", "BASE", "RESULT", "STATUS"],
                [
                    [
                        esc(r["run_id"]),
                        esc(r["writer"]),
                        esc(r["scheduled_at"]),
                        esc(r["idempotency_key"]),
                        esc(r["ready_at"]),
                        esc(r["base_sha"][:10]),
                        esc(r["result_sha"][:10]),
                        pill(r["status"]),
                    ]
                    for r in records[-15:]
                ],
                wide=True,
            )
        )
    return "".join(out) or note("No run history.", "muted")


def view_learning(docs: dict[str, dict]) -> str:
    doc = docs.get("learning/current")
    if not doc:
        return note("No learning ledger yet.", "muted")
    out = [note(f"As of {stamp_of(doc.get('as_of'))}", "muted")]
    if doc.get("windows"):
        out.append("<h3>Zone scorecards</h3>")
        out.append(
            table(
                ["BOARD", "WINDOW", "BUCKETS", "VERDICT"],
                [
                    [
                        esc(w["board"]),
                        esc(w["window"]),
                        esc(
                            "; ".join(
                                f"{z} {pct(b.get('mean_return'))} (n={b.get('n')})"
                                for z, b in w.get("buckets", {}).items()
                            )
                        ),
                        esc(w["verdict"]),
                    ]
                    for w in doc["windows"]
                ],
                wide=True,
            )
        )
    if doc.get("lessons"):
        out.append(
            "<h3>Lessons</h3><ul>"
            + "".join(
                f"<li><b>{esc(le['date'])}</b> {esc(le['text'])}</li>" for le in doc["lessons"]
            )
            + "</ul>"
        )
    if doc.get("model_changes"):
        out.append("<h3>Model changes</h3>")
        out.append(
            table(
                ["DATE", "CHANGE", "APPROVED BY"],
                [
                    [
                        esc(m["date"]),
                        esc(m["change"]),
                        esc(m.get("approved_by") or "not yet approved"),
                    ]
                    for m in doc["model_changes"]
                ],
            )
        )
    return "".join(out)


def view_health(docs: dict[str, dict]) -> str:
    doc = docs.get("health/current")
    if not doc:
        return note("No health document.", "warn")
    out = ['<div class="cards">']
    store_mode = doc.get("store", {}).get("mode", "n/a")
    out.append(
        card(
            "Store",
            f'<span id="store-status">{esc(store_mode)}</span>',
            "the page checks the artifact store when it is available",
        )
    )
    chain = doc.get("chain", {})
    out.append(
        card(
            "Run chain",
            pill("INTACT" if chain.get("ok") else "BROKEN"),
            f"{esc(chain.get('length'))} records",
            "ok" if chain.get("ok") else "bad",
        )
    )
    out.append(
        card(
            "Calendar",
            esc(doc.get("calendar_covered_through")),
            "NYSE holidays are maintained by hand through this year",
        )
    )
    out.append(
        card(
            "Snapshot size",
            esc(f"{doc.get('page_bytes', 0):,} bytes"),
            "documents, before rendering",
        )
    )
    out.append("</div>")
    out.append("<h3>Boards</h3>")
    out.append(
        table(
            ["BOARD", "STATUS", "STAMP", "SOURCE"],
            [
                [esc(b), pill(v.get("status")), esc(v.get("stamp")), esc(v.get("source"))]
                for b, v in sorted(doc.get("boards", {}).items())
            ],
        )
    )
    out.append("<h3>Schedules (UTC cron, ET target, DST drift)</h3>")
    rows = []
    for s in doc.get("schedule", []):
        drift = (
            "; ".join(
                f"{w['starts']} to {w['ends']} fires at {w['fires_at_et']} ET"
                for w in s.get("dst_drift", [])
            )
            or "none this year"
        )
        rows.append(
            [
                esc(s["name"]),
                f"<code>{esc(s['cron_utc'])}</code>",
                esc(s["target_et"]),
                esc(drift),
                esc(s.get("last_starts_vs_ready")),
            ]
        )
    out.append(
        table(
            ["RUN", "CRON (UTC)", "TARGET (ET)", "DST DRIFT", "LAST STARTS VS READY"],
            rows,
            wide=True,
        )
    )
    for text in doc.get("notes", []):
        out.append(note(esc(text), "muted"))
    out.append(
        legacy_tables(docs.get("legacy/health"), limit=14, heading="Legacy sources and fire log")
    )
    return "".join(out)


CSS = """
:root{--bg:#EEF1F5;--panel:#FFFFFF;--ink:#101828;--muted:#5B6470;--line:#D5DAE1;--accent:#0F5C8C;--accent-ink:#FFFFFF;--pos:#1B7F4C;--neg:#B42318;--warn:#B54708;--stale:#6B7280;--chip:#E4EAF1;--code:#F3F5F8}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#0E1116;--panel:#161B22;--ink:#E6EAF0;--muted:#98A2B3;--line:#2A313B;--accent:#5AB0E8;--accent-ink:#0B1220;--pos:#4CC38A;--neg:#F97066;--warn:#F7B955;--stale:#8B93A1;--chip:#1F2630;--code:#0E1116}}
:root[data-theme="dark"]{--bg:#0E1116;--panel:#161B22;--ink:#E6EAF0;--muted:#98A2B3;--line:#2A313B;--accent:#5AB0E8;--accent-ink:#0B1220;--pos:#4CC38A;--neg:#F97066;--warn:#F7B955;--stale:#8B93A1;--chip:#1F2630;--code:#0E1116}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;font-size:14px;line-height:1.45}
.wrap{padding:0 16px 48px;max-width:1440px;margin:0 auto}
header.top{display:flex;flex-wrap:wrap;gap:8px 20px;align-items:baseline;padding:16px 0 8px;border-bottom:2px solid var(--accent)}
header.top h1{font-family:"Barlow Condensed","Arial Narrow",sans-serif;font-weight:700;font-size:30px;letter-spacing:.02em;margin:0;text-transform:uppercase;text-wrap:balance}
header.top .meta{color:var(--muted);font-size:13px}
nav.views{display:flex;gap:6px;overflow-x:auto;padding:10px 0;position:sticky;top:0;background:var(--bg);z-index:2;border-bottom:1px solid var(--line)}
nav.views button{flex:0 0 auto;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:4px;padding:6px 10px;font:inherit;cursor:pointer}
nav.views button[aria-current="true"]{background:var(--accent);color:var(--accent-ink);border-color:var(--accent)}
nav.views button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
section.view{display:none;padding-top:12px}section.view.active{display:block}
h2{font-family:"Barlow Condensed","Arial Narrow",sans-serif;font-size:24px;text-transform:uppercase;letter-spacing:.03em;margin:8px 0 12px}
h3{font-size:16px;margin:20px 0 8px}h4{font-size:14px;margin:14px 0 6px;color:var(--muted)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin:8px 0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:10px 12px}
.card.ok{border-left:4px solid var(--pos)}.card.warn{border-left:4px solid var(--warn)}.card.bad{border-left:4px solid var(--neg)}
.c-name{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}.c-val{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:20px;margin:4px 0}.c-d{font-size:12px;color:var(--muted)}
.tblwrap{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:4px;margin:6px 0}
table.tbl{border-collapse:collapse;width:100%;font-size:13px}
table.tbl th{text-align:left;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);padding:8px;border-bottom:1px solid var(--line);white-space:nowrap}
table.tbl td{padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top;font-variant-numeric:tabular-nums}
table.tbl tr:last-child td{border-bottom:0}
.case{max-width:60ch;white-space:normal;color:var(--ink)}
.pill{display:inline-block;font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:11px;padding:1px 6px;border-radius:3px;background:var(--chip);border:1px solid var(--line);white-space:nowrap}
.s-live,.s-published,.s-pass,.s-ok,.s-hit,.s-intact,.s-buy,.s-add,.s-upheld,.s-scored,.s-gate-pass,.s-confirmed,.s-source-backed{background:color-mix(in srgb,var(--pos) 18%,var(--panel));border-color:var(--pos)}
.s-stale,.s-warn,.s-review,.s-skipped,.s-partial,.s-hold,.s-watch,.s-wait,.s-revised,.s-material,.s-open,.s-revise,.s-judgment,.s-assumption,.s-calculated{background:color-mix(in srgb,var(--warn) 18%,var(--panel));border-color:var(--warn)}
.s-degraded,.s-blocked,.s-fail,.s-failed,.s-miss,.s-broken,.s-excluded,.s-insufficient,.s-avoid,.s-exit,.s-trim,.s-blocking,.s-conflict,.s-void{background:color-mix(in srgb,var(--neg) 18%,var(--panel));border-color:var(--neg)}
.banner{margin:4px 0 8px;padding:6px 10px;border-radius:4px;font-size:13px;border:1px solid var(--line);background:var(--panel)}
.banner.ok{border-left:4px solid var(--pos)}.banner.warn{border-left:4px solid var(--warn)}.banner.bad{border-left:4px solid var(--neg)}
.note{font-size:13px;margin:6px 0}.note.muted{color:var(--muted)}.note.warn{color:var(--warn)}.note.bad{color:var(--neg)}
.kv{display:grid;grid-template-columns:max-content 1fr;gap:4px 14px;font-size:13px;background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:10px}
.kv dt{color:var(--muted)}.kv dd{margin:0;overflow-wrap:anywhere}
code{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px;background:var(--code);padding:1px 4px;border-radius:3px;overflow-wrap:anywhere}
.own{color:var(--accent)}.muted{color:var(--muted)}
.pills .bp{display:inline-block;margin:2px 6px 2px 0;font-size:12px}
ol.todos li{margin:0 0 10px}ul.ticker{list-style:none;padding:0;margin:0;display:flex;flex-wrap:wrap;gap:6px}ul.ticker li{background:var(--panel);border:1px solid var(--line);border-radius:3px;padding:3px 8px;font-size:12px}
article.asset,article.board{margin:0 0 18px}
#store-banner{display:none;margin:8px 0;padding:8px 10px;border:1px solid var(--warn);border-left:4px solid var(--warn);border-radius:4px;background:var(--panel)}
@media (prefers-reduced-motion: reduce){*{transition:none!important}}
"""

JS = """
(function(){
  var buttons = Array.prototype.slice.call(document.querySelectorAll('nav.views button'));
  var sections = Array.prototype.slice.call(document.querySelectorAll('section.view'));
  function show(id){
    sections.forEach(function(s){ s.classList.toggle('active', s.id === 'view-' + id); });
    buttons.forEach(function(b){ b.setAttribute('aria-current', b.dataset.view === id ? 'true' : 'false'); });
    try { history.replaceState(null, '', '#' + id); } catch (e) {}
  }
  buttons.forEach(function(b){ b.addEventListener('click', function(){ show(b.dataset.view); }); });
  var initial = (location.hash || '#today').slice(1);
  if (!document.getElementById('view-' + initial)) initial = 'today';
  show(initial);

  var status = document.getElementById('store-status');
  var banner = document.getElementById('store-banner');
  var embedded = null;
  try { embedded = JSON.parse(document.getElementById('snapshot-data').textContent); } catch (e) { embedded = null; }
  function setStatus(text){ if (status) status.textContent = text; var s2 = document.getElementById('store-status-top'); if (s2) s2.textContent = text; }
  setStatus('embedded snapshot');
  if (!(window.claude && typeof window.claude.use === 'function')) return;
  window.claude.use('db').then(function(db){
    if (!db) { setStatus('embedded snapshot (store not available in this view)'); return; }
    return db.doc('snapshots/current').get().then(function(snap){
      if (!snap.exists) { setStatus('artifact db reachable, no snapshot document yet'); return; }
      var live = snap.data();
      var local = embedded && embedded['snapshots/current'];
      if (local && live.sha === local.sha) { setStatus('artifact db, in sync with this page (' + Object.keys(live.parts || {}).length + ' documents)'); return; }
      setStatus('artifact db holds a different snapshot (' + (live.version || 'unversioned') + ')');
      if (banner) { banner.style.display = 'block'; banner.textContent = 'The store holds snapshot ' + (live.version || '') + ' generated ' + (live.generated_at || 'n/a') + '; this page was built from ' + ((local && local.version) || 'n/a') + '. Ask for a republish to render it.'; }
    });
  }).catch(function(err){ setStatus('store check failed: ' + (err && err.code ? err.code : 'unknown')); });
})();
"""


def render(docs: dict[str, dict], *, title: str = TITLE, description: str | None = None) -> str:
    snap = docs.get("snapshots/current", {})
    health = docs.get("health/current", {})
    statuses = [v.get("status") for v in health.get("boards", {}).values()]
    overall = (
        "DEGRADED"
        if "DEGRADED" in statuses
        else ("STALE" if "STALE" in statuses else ("LIVE" if statuses else "n/a"))
    )
    generated = stamp_of(snap.get("generated_at"))
    parts = {
        "today": view_today(docs),
        "stocks": view_stocks(docs),
        "crypto": view_crypto(docs),
        "portfolio-1": view_portfolio(docs, "schwab-roth", "schwab-combined"),
        "portfolio-2": view_portfolio(docs, "schwab-rollover", None),
        "accounts": view_accounts(docs),
        "assets": view_assets(docs),
        "risk": view_risk(docs),
        "critic": view_critic(docs),
        "performance": view_performance(docs),
        "history": view_history(docs),
        "learning": view_learning(docs),
        "health": view_health(docs),
    }
    nav = "".join(
        f'<button type="button" data-view="{vid}" aria-current="false">{esc(label)}</button>'
        for vid, label in VIEWS
    )
    sections = "".join(
        f'<section class="view" id="view-{vid}"><h2>{esc(label)}</h2>{parts[vid]}</section>'
        for vid, label in VIEWS
    )
    # Every "<" in the payload is written as \u003c so no stored text can end the script
    # element or open a comment inside it; JSON.parse restores the character.
    payload = json.dumps(docs, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    noscript = "<noscript><style>section.view{display:block}</style></noscript>"
    return (
        f"<title>{esc(title)}</title><style>{CSS}</style>{noscript}"
        '<div class="wrap">'
        f'<header class="top"><h1>{esc(title)}</h1><span class="meta">snapshot {esc(snap.get("version") or "n/a")} · generated {generated}</span>'
        f'<span class="meta">freshness {pill(overall)}</span><span class="meta">store: <span id="store-status-top">embedded snapshot</span></span>'
        '<span class="meta">read-only research; no order is placed from this page</span></header>'
        '<div id="store-banner" role="status"></div>'
        f'<nav class="views" aria-label="Views">{nav}</nav>'
        f"<main>{sections}</main>"
        "</div>"
        f'<script id="snapshot-data" type="application/json">{payload}</script>'
        f"<script>{JS}</script>"
    )
