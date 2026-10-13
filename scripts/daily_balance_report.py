#!/usr/bin/env python3
"""Daily balance report generator.

Reads a PRIVATE ledger file (quantities, baselines, price-source specs; it is
never committed to this public repository), fetches live prices from public,
key-free endpoints with a primary/secondary cross-check, computes the value and
gain of every holding, appends one entry to a history file, and renders a
one-page HTML report that prints to a single Letter page.

Sourcing rules (see docs/DAILY_BALANCE_REPORT.md):

* every price is fetched from a primary and, when configured, a secondary
  source; the two are compared and a gap above the tolerance is flagged;
* a price that cannot be fetched is never invented: the row is marked STALE,
  the last known value is carried forward and the report says so;
* every number on the page carries the source code and time it came from.

The script has no third-party dependencies. Network access happens only
through ``fetch_text``; tests replace the fetcher table with fakes.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

SCHEMA = "savage-daily-balance/1"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) savage-daily-balance/1.0"
DEFAULT_TIMEOUT = 20
DEFAULT_RETRIES = 3
MINUS = "−"

try:  # the system tz database is normally present; fall back to a fixed offset
    from zoneinfo import ZoneInfo

    EASTERN = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover - only on images without tzdata
    EASTERN = dt.timezone(dt.timedelta(hours=-5), "ET?")


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
PACE_SECONDS = float(os.environ.get("DAILY_BALANCE_PACE_SECONDS", "0.6"))  # polite spacing for free APIs


def fetch_text(url: str, timeout: int = DEFAULT_TIMEOUT, retries: int = DEFAULT_RETRIES) -> str:
    """GET ``url`` and return the body as text, retrying with backoff (longer on HTTP 429)."""
    last: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/csv,*/*"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", "replace")
            if PACE_SECONDS:
                time.sleep(PACE_SECONDS)
            return body
        except urllib.error.HTTPError as exc:
            last = exc
            if attempt < retries - 1:
                time.sleep((6 if exc.code == 429 else 2) * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            if attempt < retries - 1:
                time.sleep(2**attempt)
    raise RuntimeError(f"fetch failed after {retries} attempts: {url}: {last}")


def fetch_json(url: str, **kw: Any) -> Any:
    return json.loads(fetch_text(url, **kw))


# --------------------------------------------------------------------------- #
# Quotes and fetchers
# --------------------------------------------------------------------------- #
@dataclass
class Quote:
    price: float
    asof_utc: str  # ISO-8601 in UTC
    source: str  # short code shown on the report, e.g. "Y", "CB", "DS"
    url: str
    note: str = ""
    meta: dict = field(default_factory=dict)


def _utcnow_iso(now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now(dt.timezone.utc)
    return now.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat()


def _epoch_iso(ts: Any) -> str:
    return dt.datetime.fromtimestamp(int(ts), dt.timezone.utc).replace(microsecond=0).isoformat()


def _walk(obj: Any, path: str) -> Any:
    """Resolve a dotted path such as ``data.amount`` or ``chart.result[0].meta``."""
    cur = obj
    for part in [p for p in re.split(r"\.(?![^\[]*\])", path) if p]:
        m = re.fullmatch(r"([^\[]*)((?:\[\d+\])*)", part)
        key, idx = m.group(1), m.group(2)
        if key:
            cur = cur[key]
        for i in re.findall(r"\[(\d+)\]", idx):
            cur = cur[int(i)]
    return cur


def fetch_yahoo_chart(spec: dict, now: dt.datetime | None = None) -> Quote:
    sym = spec["symbol"]
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range=5d&interval=1d"
    data = fetch_json(url)
    meta = data["chart"]["result"][0]["meta"]
    price = float(meta["regularMarketPrice"])
    asof = _epoch_iso(meta.get("regularMarketTime")) if meta.get("regularMarketTime") else _utcnow_iso(now)
    keep = {k: meta.get(k) for k in ("longName", "shortName", "fullExchangeName", "marketState", "previousClose", "postMarketPrice", "preMarketPrice", "currency")}
    return Quote(price, asof, "Y", url, note=str(keep.get("marketState") or ""), meta=keep)


def fetch_coinbase_spot(spec: dict, now: dt.datetime | None = None) -> Quote:
    pair = spec["pair"]
    url = f"https://api.coinbase.com/v2/prices/{urllib.parse.quote(pair)}/spot"
    data = fetch_json(url)
    return Quote(float(data["data"]["amount"]), _utcnow_iso(now), "CB", url, meta={"base": data["data"].get("base")})


def fetch_coinbase_ticker(spec: dict, now: dt.datetime | None = None) -> Quote:
    product = spec["product"]
    url = f"https://api.exchange.coinbase.com/products/{urllib.parse.quote(product)}/ticker"
    data = fetch_json(url)
    asof = data.get("time") or _utcnow_iso(now)
    asof = asof.replace("Z", "+00:00")
    try:
        asof = dt.datetime.fromisoformat(asof[:26] + "+00:00" if "+" not in asof else asof).astimezone(dt.timezone.utc).replace(microsecond=0).isoformat()
    except ValueError:
        asof = _utcnow_iso(now)
    return Quote(float(data["price"]), asof, "CBX", url, meta={"bid": data.get("bid"), "ask": data.get("ask")})


def fetch_coingecko(spec: dict, now: dt.datetime | None = None) -> Quote:
    cid = spec["id"]
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={urllib.parse.quote(cid)}&vs_currencies=usd&include_last_updated_at=true"
    data = fetch_json(url)
    row = data[cid]
    asof = _epoch_iso(row["last_updated_at"]) if row.get("last_updated_at") else _utcnow_iso(now)
    return Quote(float(row["usd"]), asof, "CG", url)


def fetch_dexscreener(spec: dict, now: dt.datetime | None = None) -> Quote:
    chain, address = spec["chain"], spec["address"]
    url = f"https://api.dexscreener.com/tokens/v1/{urllib.parse.quote(chain)}/{urllib.parse.quote(address)}"
    pairs = fetch_json(url)
    if isinstance(pairs, dict):
        pairs = pairs.get("pairs") or []
    pairs = [p for p in pairs if str(p.get("baseToken", {}).get("address", "")).lower() == address.lower() and p.get("priceUsd")]
    want = spec.get("pair_address")
    if want:
        pairs = [p for p in pairs if str(p.get("pairAddress", "")).lower() == want.lower()] or pairs
    if not pairs:
        raise RuntimeError(f"dexscreener: no priced pair for {chain}:{address}")
    best = max(pairs, key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0))
    liq = float((best.get("liquidity") or {}).get("usd") or 0)
    vol = float((best.get("volume") or {}).get("h24") or 0)
    note = ""
    if liq < float(spec.get("min_liquidity_usd", 25000)):
        note = "THIN"
    return Quote(float(best["priceUsd"]), _utcnow_iso(now), "DS", url, note=note,
                 meta={"pair": best.get("pairAddress"), "dex": best.get("dexId"), "quote": (best.get("quoteToken") or {}).get("symbol"), "liquidity_usd": liq, "volume_24h_usd": vol})


def fetch_geckoterminal(spec: dict, now: dt.datetime | None = None) -> Quote:
    network, address = spec["network"], spec["address"]
    url = f"https://api.geckoterminal.com/api/v2/networks/{urllib.parse.quote(network)}/tokens/{urllib.parse.quote(address)}"
    data = fetch_json(url)
    attrs = data["data"]["attributes"]
    return Quote(float(attrs["price_usd"]), _utcnow_iso(now), "GT", url, meta={"name": attrs.get("name"), "symbol": attrs.get("symbol")})


def fetch_json_path(spec: dict, now: dt.datetime | None = None) -> Quote:
    """Generic fetcher: ``url`` plus a dotted ``path`` to the price field."""
    data = fetch_json(spec["url"])
    price = float(str(_walk(data, spec["path"])).replace("$", "").replace(",", "").strip())
    asof = _utcnow_iso(now)
    if spec.get("asof_path"):
        try:
            raw = _walk(data, spec["asof_path"])
            asof = _epoch_iso(raw) if isinstance(raw, (int, float)) else str(raw)
        except Exception:
            pass
    return Quote(price, asof, spec.get("code", "J"), spec["url"])


def fetch_static(spec: dict, now: dt.datetime | None = None) -> Quote:
    return Quote(float(spec["value"]), _utcnow_iso(now), spec.get("code", "FIX"), "", note="static")


def fetch_manual(spec: dict, now: dt.datetime | None = None) -> Quote:
    return Quote(float(spec["value"]), str(spec.get("asof", _utcnow_iso(now))), "MAN", "", note="manual")


FETCHERS: dict[str, Callable[[dict, dt.datetime | None], Quote]] = {
    "yahoo_chart": fetch_yahoo_chart,
    "coinbase_spot": fetch_coinbase_spot,
    "coinbase_ticker": fetch_coinbase_ticker,
    "coingecko": fetch_coingecko,
    "dexscreener": fetch_dexscreener,
    "geckoterminal": fetch_geckoterminal,
    "json": fetch_json_path,
    "static": fetch_static,
    "manual": fetch_manual,
}


# --------------------------------------------------------------------------- #
# Price resolution policy
# --------------------------------------------------------------------------- #
@dataclass
class Resolved:
    price: float | None
    asof_utc: str | None
    source: str
    flags: list[str]
    gap_pct: float | None
    primary: Quote | None
    secondary: Quote | None
    errors: list[str]


def _try(spec: dict | None, fetchers: dict, now: dt.datetime | None) -> tuple[Quote | None, str | None]:
    if not spec:
        return None, None
    kind = spec.get("type")
    fn = fetchers.get(kind)
    if fn is None:
        return None, f"unknown fetcher type {kind!r}"
    try:
        return fn(spec, now), None
    except Exception as exc:  # noqa: BLE001 - every failure becomes a flag, never a crash
        return None, f"{kind}: {exc}"


def resolve_price(price_spec: dict, tolerance_pct: float, fetchers: dict | None = None, now: dt.datetime | None = None) -> Resolved:
    fetchers = fetchers or FETCHERS
    flags: list[str] = []
    errors: list[str] = []
    p, perr = _try(price_spec.get("primary"), fetchers, now)
    s, serr = _try(price_spec.get("secondary"), fetchers, now)
    for e in (perr, serr):
        if e:
            errors.append(e)
    gap = None
    if p and s and s.price:
        gap = abs(p.price - s.price) / s.price * 100.0
        if gap > tolerance_pct:
            flags.append("DISAGREE")
    if p and p.note == "THIN":
        flags.append("THIN")
    if p:
        return Resolved(p.price, p.asof_utc, p.source, flags, gap, p, s, errors)
    if s:
        flags.append("SECONDARY")
        if s.note == "THIN":
            flags.append("THIN")
        return Resolved(s.price, s.asof_utc, s.source, flags, None, None, s, errors)
    flags.append("NO PRICE")
    return Resolved(None, None, "", flags, None, None, None, errors)


# --------------------------------------------------------------------------- #
# Computation
# --------------------------------------------------------------------------- #
def _pct(new: float | None, base: float | None) -> float | None:
    if new is None or base in (None, 0):
        return None
    return (new / base - 1.0) * 100.0


def _last_known(history: list[dict], key: str) -> tuple[float | None, str | None]:
    for entry in reversed(history):
        pos = (entry.get("positions") or {}).get(key)
        if pos and pos.get("value") is not None and not pos.get("stale"):
            return float(pos["value"]), entry.get("date_et")
    return None, None


def compute(ledger: dict, history: list[dict], now: dt.datetime, fetchers: dict | None = None) -> dict:
    """Price every holding and build the report model (pure data, no HTML)."""
    tol = ledger.get("tolerance_pct", {})
    baseline = ledger.get("baseline", {})
    accounts_out = []
    quotes_audit = []
    household = 0.0
    household_baseline = 0.0
    stale_rows = 0
    flagged_rows = 0
    entry_missing = 0
    for acct in ledger["accounts"]:
        rows = []
        acct_total = 0.0
        acct_baseline = 0.0
        for pos in acct.get("positions", []):
            key = f"{acct['id']}:{pos['symbol']}"
            tolerance = float(pos.get("tolerance_pct", tol.get(pos.get("asset_class", "default"), tol.get("default", 2.0))))
            res = resolve_price(pos["price"], tolerance, fetchers, now)
            qty = float(pos["qty"])
            value = qty * res.price if res.price is not None else None
            stale_from = None
            if value is None:
                last, last_date = _last_known(history, key)
                if last is None:
                    last, last_date = pos.get("baseline_value"), baseline.get("date")
                value = float(last) if last is not None else None
                stale_from = last_date
                stale_rows += 1
            if res.flags and set(res.flags) - {"NO PRICE"}:
                flagged_rows += 1
            bval = pos.get("baseline_value")
            cost = pos.get("cost_basis_total")
            row = {
                "symbol": pos["symbol"],
                "name": pos.get("name", pos["symbol"]),
                "kind": pos.get("kind", ""),
                "qty": qty,
                "qty_status": pos.get("qty_status", "exact"),
                "price": res.price,
                "price_asof_utc": res.asof_utc,
                "source": res.source,
                "flags": list(res.flags),
                "gap_pct": res.gap_pct,
                "value": value,
                "stale": res.price is None,
                "stale_from": stale_from,
                "baseline_value": bval,
                "baseline_price": pos.get("baseline_price"),
                "delta_vs_baseline": (value - float(bval)) if (value is not None and bval is not None) else None,
                "pct_vs_baseline": _pct(value, float(bval) if bval is not None else None),
                "cost_basis_total": cost,
                "pct_vs_cost": _pct(value, float(cost) if cost is not None else None),
                "note": pos.get("note", ""),
                "errors": res.errors,
            }
            rows.append(row)
            if value is not None:
                acct_total += value
            if bval is not None:
                acct_baseline += float(bval)
            quotes_audit.append({"key": key, "primary": res.primary.__dict__ if res.primary else None, "secondary": res.secondary.__dict__ if res.secondary else None, "used": res.price, "flags": res.flags, "errors": res.errors})
        cash_rows = []
        for cash in acct.get("cash", []):
            amt = float(cash["amount"])
            cash_rows.append({"label": cash.get("label", "Cash"), "amount": amt, "apy": cash.get("apy"), "asof": cash.get("asof", baseline.get("date"))})
            acct_total += amt
            acct_baseline += float(cash.get("baseline_amount", amt))
        perp_rows = []
        for perp in acct.get("perps", []):
            key = f"{acct['id']}:{perp['symbol']}"
            tolerance = float(perp.get("tolerance_pct", tol.get("major_crypto", tol.get("default", 2.0))))
            res = resolve_price(perp["mark"], tolerance, fetchers, now)
            size = float(perp["contract_size"])
            n = float(perp["contracts"])
            sign = -1.0 if str(perp.get("side", "long")).lower() == "short" else 1.0
            entry = perp.get("entry_price")
            pnl = None
            flags = list(res.flags)
            if res.price is not None and entry is not None:
                pnl = (res.price - float(entry)) * n * size * sign
            else:
                pnl = perp.get("baseline_pnl")
                if entry is None:
                    flags.append("ENTRY n/a")
                    entry_missing += 1
                if res.price is None:
                    stale_rows += 1
            perp_rows.append({
                "symbol": perp["symbol"], "side": perp.get("side", "long"), "contracts": n, "contract_size": size,
                "notional": (res.price * n * size) if res.price is not None else None,
                "entry_price": entry, "mark": res.price, "mark_asof_utc": res.asof_utc, "source": res.source,
                "pnl": pnl, "baseline_pnl": perp.get("baseline_pnl"), "flags": flags,
                "stale": res.price is None, "entry_missing": entry is None,
                "tp": perp.get("take_profit"), "sl": perp.get("stop_loss"), "note": perp.get("note", ""),
            })
            if pnl is not None:
                acct_total += float(pnl)
            if perp.get("baseline_pnl") is not None:
                acct_baseline += float(perp["baseline_pnl"])
            quotes_audit.append({"key": key, "primary": res.primary.__dict__ if res.primary else None, "secondary": res.secondary.__dict__ if res.secondary else None, "used": res.price, "flags": flags, "errors": res.errors})
        accounts_out.append({
            "id": acct["id"], "name": acct["name"], "venue": acct.get("venue", ""), "group": acct.get("group", ""),
            "positions": rows, "cash": cash_rows, "perps": perp_rows,
            "total": acct_total, "baseline_total": acct_baseline,
            "delta_vs_baseline": acct_total - acct_baseline, "pct_vs_baseline": _pct(acct_total, acct_baseline),
            "note": acct.get("note", ""),
        })
        household += acct_total
        household_baseline += acct_baseline
    prior = history[-1] if history else None
    prior_total = float(prior["household_total"]) if prior and prior.get("household_total") is not None else None
    model = {
        "schema": SCHEMA,
        "generated_utc": _utcnow_iso(now),
        "generated_et": now.astimezone(EASTERN).strftime("%a %d %b %Y, %I:%M %p %Z").replace(" 0", " "),
        "date_et": now.astimezone(EASTERN).strftime("%Y-%m-%d"),
        "owner_label": ledger.get("owner_label", "Daily balance"),
        "baseline": baseline,
        "accounts": accounts_out,
        "household_total": household,
        "household_baseline": household_baseline,
        "delta_vs_baseline": household - household_baseline,
        "pct_vs_baseline": _pct(household, household_baseline),
        "prior_date_et": prior.get("date_et") if prior else None,
        "prior_total": prior_total,
        "delta_vs_prior": (household - prior_total) if prior_total is not None else None,
        "pct_vs_prior": _pct(household, prior_total),
        "stale_rows": stale_rows,
        "flagged_rows": flagged_rows,
        "entry_missing": entry_missing,
        "notes": list(ledger.get("notes", [])),
        "quotes": quotes_audit,
    }
    return model


def history_entry(model: dict) -> dict:
    positions = {}
    for acct in model["accounts"]:
        for row in acct["positions"]:
            positions[f"{acct['id']}:{row['symbol']}"] = {"value": row["value"], "price": row["price"], "stale": row["stale"]}
        for perp in acct["perps"]:
            positions[f"{acct['id']}:{perp['symbol']}"] = {"value": perp["pnl"], "price": perp["mark"], "stale": perp["stale"]}
    return {
        "date_et": model["date_et"], "generated_utc": model["generated_utc"],
        "household_total": model["household_total"],
        "accounts": {a["id"]: {"total": a["total"]} for a in model["accounts"]},
        "positions": positions, "stale_rows": model["stale_rows"],
    }


def append_history(history: list[dict], entry: dict) -> list[dict]:
    """Replace a same-day entry (re-runs) or append; keep chronological order."""
    out = [e for e in history if e.get("date_et") != entry["date_et"]]
    out.append(entry)
    out.sort(key=lambda e: (e.get("date_et") or "", e.get("generated_utc") or ""))
    return out


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #
def fmt_money(x: float | None, decimals: int = 2) -> str:
    if x is None:
        return "n/a"
    s = f"{abs(x):,.{decimals}f}"
    return f"{MINUS}${s}" if x < 0 else f"${s}"


def fmt_signed_money(x: float | None) -> str:
    if x is None:
        return "n/a"
    s = f"{abs(x):,.2f}"
    return f"+${s}" if x >= 0 else f"{MINUS}${s}"


def fmt_pct(x: float | None) -> str:
    if x is None:
        return "n/a"
    s = f"{abs(x):.2f}%"
    return f"+{s}" if x >= 0 else f"{MINUS}{s}"


def fmt_price(x: float | None) -> str:
    if x is None:
        return "n/a"
    if x >= 1000:
        return f"${x:,.2f}"
    if x >= 1:
        return f"${x:,.2f}"
    if x >= 0.01:
        return f"${x:.4f}"
    if x >= 0.0001:
        return f"${x:.6f}"
    return f"${x:.8f}"


def fmt_qty(x: float | None) -> str:
    if x is None:
        return "n/a"
    if x >= 1_000_000:
        return f"{x/1_000_000:,.3f}M"
    if x >= 10_000:
        return f"{x/1000:,.2f}K"
    if x >= 100:
        return f"{x:,.2f}"
    if float(x).is_integer():
        return f"{int(x):,}"
    return f"{x:,.4f}".rstrip("0").rstrip(".")


def fmt_time_et(iso_utc: str | None) -> str:
    if not iso_utc:
        return ""
    try:
        t = dt.datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return t.astimezone(EASTERN).strftime("%m/%d %H:%M")


SOURCE_LEGEND = {
    "Y": "Yahoo Finance chart API", "CB": "Coinbase spot price", "CBX": "Coinbase Exchange ticker", "CG": "CoinGecko",
    "DS": "DexScreener best-liquidity pair", "GT": "GeckoTerminal", "J": "JSON endpoint", "FIX": "fixed", "MAN": "manual",
}
FLAG_GLYPH = {"STALE": "*", "DISAGREE": "‡", "THIN": "†", "SECONDARY": "§", "NO PRICE": "*", "ENTRY n/a": "¶"}


def _flag_glyphs(flags: list[str], stale: bool) -> str:
    out = []
    if stale:
        out.append("*")
    for f in flags:
        g = FLAG_GLYPH.get(f)
        if g and g not in out:
            out.append(g)
    return "".join(out)


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _font_face_css(fonts_dir: Path | None) -> str:
    """Inline the IBM Plex woff2 files as data URIs when present; else rely on Google Fonts / system fonts."""
    faces = [
        ("IBM Plex Sans", 400, "normal", "PlexSans-Regular.woff2"),
        ("IBM Plex Sans", 500, "normal", "PlexSans-Medium.woff2"),
        ("IBM Plex Sans", 600, "normal", "PlexSans-SemiBold.woff2"),
        ("IBM Plex Mono", 400, "normal", "PlexMono-Regular.woff2"),
        ("IBM Plex Mono", 600, "normal", "PlexMono-SemiBold.woff2"),
    ]
    css = []
    if fonts_dir:
        for family, weight, style, fname in faces:
            p = fonts_dir / fname
            if p.exists():
                b64 = base64.b64encode(p.read_bytes()).decode("ascii")
                css.append(f"@font-face{{font-family:'{family}';font-weight:{weight};font-style:{style};font-display:swap;src:url(data:font/woff2;base64,{b64}) format('woff2');}}")
    return "\n".join(css)


CSS = r"""
:root{--paper:#FBFAF7;--ink:#161B26;--ink-2:#4A5262;--ink-3:#7B8494;--rule:#D9D4C8;--rule-2:#ECE8DF;--amber:#B8781A;--amber-soft:#F6EAD2;--blue:#1B7FB8;--up:#1E7F4A;--down:#B8431A;--card:#FFFFFF;--chip:#F1EEE6}
:root:not([data-theme="light"]){color-scheme:light dark}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#121419;--ink:#ECEAE3;--ink-2:#B9B6AD;--ink-3:#8A8A86;--rule:#2C3140;--rule-2:#22262F;--amber:#D9A24A;--amber-soft:#3A2E16;--blue:#5FB0E0;--up:#5FC98B;--down:#E4825C;--card:#181B22;--chip:#22262F}}
:root[data-theme="dark"]{--paper:#121419;--ink:#ECEAE3;--ink-2:#B9B6AD;--ink-3:#8A8A86;--rule:#2C3140;--rule-2:#22262F;--amber:#D9A24A;--amber-soft:#3A2E16;--blue:#5FB0E0;--up:#5FC98B;--down:#E4825C;--card:#181B22;--chip:#22262F}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:var(--paper);color:var(--ink);font-family:'IBM Plex Sans',-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;font-size:8.6pt;line-height:1.3;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.page{max-width:8.5in;margin:0 auto;padding:16px}
header{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:end;border-bottom:2px solid var(--amber);padding-bottom:8px;margin-bottom:10px}
.brand{font-weight:600;letter-spacing:.14em;text-transform:uppercase;font-size:7.5pt;color:var(--amber)}
h1{font-size:15pt;margin:2px 0 0;font-weight:600;letter-spacing:-.01em;text-wrap:balance}
.stamp{font-family:'IBM Plex Mono',Menlo,Consolas,monospace;font-size:7.2pt;color:var(--ink-3);margin-top:2px}
.kpis{display:grid;grid-auto-flow:column;gap:14px;text-align:right}
.kpi .l{font-size:6.8pt;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3)}
.kpi .v{font-family:'IBM Plex Mono',Menlo,Consolas,monospace;font-size:12.5pt;font-weight:600;font-variant-numeric:tabular-nums;letter-spacing:-.01em}
.kpi .s{font-family:'IBM Plex Mono',Menlo,Consolas,monospace;font-size:7.4pt;color:var(--ink-2)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px 12px;align-items:start}
.acct{background:var(--card);border:1px solid var(--rule);border-radius:4px;padding:6px 8px 4px;break-inside:avoid}
.acct.wide{grid-column:1/-1}
.acct h2{display:flex;justify-content:space-between;align-items:baseline;gap:8px;margin:0 0 3px;font-size:9pt;font-weight:600}
.acct h2 .v{font-family:'IBM Plex Mono',Menlo,Consolas,monospace;font-variant-numeric:tabular-nums;font-size:9.4pt}
.acct h2 .sub{font-weight:400;color:var(--ink-3);font-size:7.2pt;margin-left:4px}
.acct .d{font-family:'IBM Plex Mono',Menlo,Consolas,monospace;font-size:7.2pt;color:var(--ink-2);margin-bottom:3px}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th{font-size:6.6pt;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3);font-weight:500;text-align:right;padding:1px 3px;border-bottom:1px solid var(--rule);white-space:nowrap}
th:first-child,td:first-child{text-align:left;padding-left:0}
td{padding:1.5px 3px;border-bottom:1px solid var(--rule-2);text-align:right;white-space:nowrap;font-family:'IBM Plex Mono',Menlo,Consolas,monospace;font-size:7.4pt}
td.n{font-family:'IBM Plex Sans',sans-serif;font-size:8pt}
td.n small{color:var(--ink-3);font-size:6.8pt;margin-left:3px}
tr.sum td{border-bottom:none;border-top:1px solid var(--rule);font-weight:600;padding-top:2px}
.up{color:var(--up)}.down{color:var(--down)}.na{color:var(--ink-3)}
.src{color:var(--ink-3);font-size:6.6pt}
.flag{color:var(--amber);font-weight:600}
.chip{display:inline-block;background:var(--chip);border-radius:3px;padding:0 4px;font-size:6.6pt;color:var(--ink-2);font-family:'IBM Plex Mono',monospace}
footer{margin-top:8px;border-top:1px solid var(--rule);padding-top:5px;font-size:6.9pt;color:var(--ink-2);display:grid;grid-template-columns:1.1fr 1fr;gap:6px 14px}
footer p{margin:0 0 2px}
footer ul{margin:0;padding-left:12px}
footer li{margin:0 0 1px}
.legend span{white-space:nowrap;margin-right:6px}
@page{size:Letter;margin:0.4in 0.45in}
@media print{:root{--paper:#FFFFFF;--ink:#161B26;--ink-2:#4A5262;--ink-3:#7B8494;--rule:#D9D4C8;--rule-2:#ECE8DF;--amber:#B8781A;--amber-soft:#F6EAD2;--blue:#1B7FB8;--up:#1E7F4A;--down:#B8431A;--card:#FFFFFF;--chip:#F1EEE6}body{font-size:8.2pt}.page{padding:0;max-width:none}.acct{border-color:#D9D4C8}}
@media (max-width:640px){.grid{grid-template-columns:1fr}header{grid-template-columns:1fr}.kpis{text-align:left}td,th{white-space:normal}}
"""


def _cls(x: float | None) -> str:
    if x is None:
        return "na"
    return "up" if x >= 0 else "down"


def render_html(model: dict, fonts_dir: Path | None = None) -> str:
    e = html.escape
    b = model["baseline"]
    bdate = b.get("date", "baseline")
    try:
        bshort = dt.date.fromisoformat(bdate).strftime("%d %b").lstrip("0")
    except ValueError:
        bshort = bdate
    head = []
    head.append(f"<div><div class='brand'>{e(model['owner_label'])}</div><h1>Daily balance</h1><div class='stamp'>{e(model['generated_et'])} &middot; baseline {e(bdate)} {e(str(b.get('time_et','')))} ET</div></div>")
    kp = []
    kp.append(f"<div class='kpi'><div class='l'>Household</div><div class='v'>{fmt_money(model['household_total'])}</div><div class='s'>{len(model['accounts'])} accounts</div></div>")
    kp.append(f"<div class='kpi'><div class='l'>Since {e(bshort)}</div><div class='v {_cls(model['delta_vs_baseline'])}'>{fmt_signed_money(model['delta_vs_baseline'])}</div><div class='s'>{fmt_pct(model['pct_vs_baseline'])} of {fmt_money(model['household_baseline'])}</div></div>")
    if model.get("prior_total") is not None:
        kp.append(f"<div class='kpi'><div class='l'>Since prior ({e(str(model.get('prior_date_et')))})</div><div class='v {_cls(model['delta_vs_prior'])}'>{fmt_signed_money(model['delta_vs_prior'])}</div><div class='s'>{fmt_pct(model['pct_vs_prior'])}</div></div>")
    head.append(f"<div class='kpis'>{''.join(kp)}</div>")

    cards = []
    for acct in model["accounts"]:
        rows = []
        rows.append(f"<tr><th>Holding</th><th>Qty</th><th>Price</th><th>Value</th><th>&Delta; vs {e(bshort)}</th><th>&Delta;%</th><th>vs cost</th><th>Src</th></tr>")
        for r in acct["positions"]:
            gl = _flag_glyphs(r["flags"], r["stale"])
            qmark = "~" if r["qty_status"] != "exact" else ""
            src = f"{e(r['source'])} {e(fmt_time_et(r['price_asof_utc']))}" if r["source"] else (f"stale {e(str(r['stale_from'] or ''))}" if r["stale"] else "")
            rows.append(
                "<tr>"
                f"<td class='n'>{e(r['symbol'])}<small>{e(r['name'])}</small></td>"
                f"<td>{e(fmt_qty(r['qty']))}{qmark}</td>"
                f"<td>{e(fmt_price(r['price']))}</td>"
                f"<td>{e(fmt_money(r['value']))}<span class='flag'>{gl}</span></td>"
                f"<td class='{_cls(r['delta_vs_baseline'])}'>{e(fmt_signed_money(r['delta_vs_baseline']))}</td>"
                f"<td class='{_cls(r['pct_vs_baseline'])}'>{e(fmt_pct(r['pct_vs_baseline']))}</td>"
                + (f"<td class='{_cls(r['pct_vs_cost'])}'>{e(fmt_pct(r['pct_vs_cost']))}</td>" if r["cost_basis_total"] is not None else "<td class='na'>&mdash;</td>")
                + f"<td class='src'>{src}</td></tr>"
            )
        for c in acct["cash"]:
            apy = f"<small>{e(str(c['apy']))}% APY</small>" if c.get("apy") not in (None, "") else ""
            rows.append(f"<tr><td class='n'>{e(c['label'])}{apy}</td><td></td><td></td><td>{e(fmt_money(c['amount']))}</td><td class='na'>&mdash;</td><td class='na'>&mdash;</td><td class='na'>&mdash;</td><td class='src'>as of {e(str(c.get('asof') or ''))}</td></tr>")
        for p in acct["perps"]:
            gl = _flag_glyphs(p["flags"], p["stale"])
            entry = fmt_price(p["entry_price"]) if p["entry_price"] is not None else "entry n/a"
            src = f"{e(p['source'])} {e(fmt_time_et(p['mark_asof_utc']))}" if p["source"] else ""
            d = (p["pnl"] - p["baseline_pnl"]) if (p["pnl"] is not None and p["baseline_pnl"] is not None and not p["entry_missing"] and not p["stale"]) else None
            rows.append(
                "<tr>"
                f"<td class='n'>{e(p['symbol'])}<small>{e(p['side'])} {int(p['contracts']) if float(p['contracts']).is_integer() else p['contracts']} &times; {e(fmt_qty(p['contract_size']))}</small></td>"
                f"<td>{e(fmt_money(p['notional'],0)) if p['notional'] is not None else 'n/a'}</td>"
                f"<td>{e(fmt_price(p['mark']))}<small> / {e(entry)}</small></td>"
                f"<td class='{_cls(p['pnl'])}'>{e(fmt_signed_money(p['pnl']))}<span class='flag'>{gl}</span></td>"
                f"<td class='{_cls(d)}'>{e(fmt_signed_money(d))}</td>"
                f"<td class='na'>P&amp;L</td><td class='na'>&mdash;</td>"
                f"<td class='src'>{src}</td></tr>"
            )
        rows.append(f"<tr class='sum'><td class='n'>Account total</td><td></td><td></td><td>{e(fmt_money(acct['total']))}</td><td class='{_cls(acct['delta_vs_baseline'])}'>{e(fmt_signed_money(acct['delta_vs_baseline']))}</td><td class='{_cls(acct['pct_vs_baseline'])}'>{e(fmt_pct(acct['pct_vs_baseline']))}</td><td></td><td></td></tr>")
        wide = " wide" if acct.get("group") == "wide" else ""
        sub = f"<span class='sub'>{e(acct['venue'])}</span>" if acct.get("venue") else ""
        note = f"<div class='d'>{e(acct['note'])}</div>" if acct.get("note") else ""
        cards.append(f"<section class='acct{wide}'><h2><span>{e(acct['name'])}{sub}</span><span class='v'>{e(fmt_money(acct['total']))}</span></h2>{note}<table>{''.join(rows)}</table></section>")

    used_codes = set()
    for q in model["quotes"]:
        for side in ("primary", "secondary"):
            quote = q.get(side) or {}
            if quote.get("source"):
                used_codes.add(quote["source"])
    legend = " ".join(f"<span><b>{e(k)}</b> {e(SOURCE_LEGEND.get(k, k))}</span>" for k in sorted(used_codes, key=lambda c: (c not in SOURCE_LEGEND, c)))
    flags_legend = "<span><b>*</b> stale: price unavailable, last known value carried</span> <span><b>&Dagger;</b> sources disagree beyond tolerance</span> <span><b>&dagger;</b> thin liquidity</span> <span><b>&sect;</b> secondary source used</span> <span><b>&para;</b> entry price unknown</span> <span><b>~</b> quantity derived from a screenshot</span>"
    notes = "".join(f"<li>{e(n)}</li>" for n in model.get("notes", []))
    bits = []
    if model["stale_rows"]:
        bits.append(f"<b>{model['stale_rows']} row(s) carried forward</b> because no price could be fetched; totals include them.")
    else:
        bits.append("Every holding priced live; no carried-forward values.")
    if model.get("entry_missing"):
        bits.append(f"{model['entry_missing']} perp row(s) carry their baseline P&amp;L because the entry price is not on file.")
    stale = "<p>" + " ".join(bits) + "</p>"
    foot = (
        f"<div>{stale}<p class='legend'>Sources: {legend}</p><p class='legend'>{flags_legend}</p>"
        f"<p>&Delta; columns compare today's value with the {e(bdate)} baseline (the tracking start). &ldquo;vs cost&rdquo; is against the broker's cost basis where it is known. Times are ET. Prices are the last trade or best-liquidity pool at fetch time; this is a balance report, not advice.</p></div>"
        f"<div>{'<ul>' + notes + '</ul>' if notes else ''}</div>"
    )
    fonts_link = "<link rel='preconnect' href='https://fonts.googleapis.com'><link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap'>"
    doc = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{e(model['owner_label'])} Daily Balance</title>{fonts_link}<style>{_font_face_css(fonts_dir)}{CSS}</style></head>"
        f"<body><div class='page'><header>{''.join(head)}</header><div class='grid'>{''.join(cards)}</div><footer>{foot}</footer></div></body></html>"
    )
    return doc


# --------------------------------------------------------------------------- #
# Fonts (optional download of IBM Plex woff2 files for self-contained output)
# --------------------------------------------------------------------------- #
GOOGLE_CSS = "https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;600&display=swap"
FONT_FILES = {("IBM Plex Sans", 400): "PlexSans-Regular.woff2", ("IBM Plex Sans", 500): "PlexSans-Medium.woff2", ("IBM Plex Sans", 600): "PlexSans-SemiBold.woff2", ("IBM Plex Mono", 400): "PlexMono-Regular.woff2", ("IBM Plex Mono", 600): "PlexMono-SemiBold.woff2"}


def download_fonts(dest: Path) -> list[str]:
    """Fetch the latin woff2 files via the Google Fonts CSS API. Best effort; returns the files written."""
    dest.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    try:
        req = urllib.request.Request(GOOGLE_CSS, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"})
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            css = resp.read().decode("utf-8", "replace")
    except Exception:
        return written
    for block in re.findall(r"@font-face\s*{[^}]*}", css):
        fam = re.search(r"font-family:\s*'([^']+)'", block)
        wt = re.search(r"font-weight:\s*(\d+)", block)
        url = re.search(r"url\(([^)]+\.woff2)\)", block)
        if not (fam and wt and url) or "U+0000-00FF" not in block:
            continue
        name = FONT_FILES.get((fam.group(1), int(wt.group(1))))
        if not name or (dest / name).exists():
            continue
        try:
            with urllib.request.urlopen(urllib.request.Request(url.group(1), headers={"User-Agent": USER_AGENT}), timeout=DEFAULT_TIMEOUT) as resp:
                (dest / name).write_bytes(resp.read())
            written.append(name)
        except Exception:
            continue
    return written


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def console_summary(model: dict) -> str:
    lines = [f"{model['owner_label']} daily balance {model['generated_et']}", f"household {fmt_money(model['household_total'])} ({fmt_signed_money(model['delta_vs_baseline'])}, {fmt_pct(model['pct_vs_baseline'])} vs baseline)"]
    if model.get("prior_total") is not None:
        lines.append(f"vs prior report {model['prior_date_et']}: {fmt_signed_money(model['delta_vs_prior'])} ({fmt_pct(model['pct_vs_prior'])})")
    for a in model["accounts"]:
        lines.append(f"  {a['name']:<32} {fmt_money(a['total']):>14} {fmt_signed_money(a['delta_vs_baseline']):>12} {fmt_pct(a['pct_vs_baseline']):>9}")
        for r in a["positions"]:
            fl = ",".join(r["flags"]) if r["flags"] else ""
            lines.append(f"      {r['symbol']:<10} {fmt_qty(r['qty']):>12} {fmt_price(r['price']):>14} {fmt_money(r['value']):>12} {fmt_pct(r['pct_vs_baseline']):>9} {r['source']:<4} {fl}")
        for p in a["perps"]:
            fl = ",".join(p["flags"]) if p["flags"] else ""
            lines.append(f"      {p['symbol']:<10} {int(p['contracts'])}x{p['contract_size']:g} mark {fmt_price(p['mark']):>12} pnl {fmt_signed_money(p['pnl']):>10} {fl}")
    lines.append(f"stale rows: {model['stale_rows']}  flagged rows: {model['flagged_rows']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ledger", required=True, type=Path, help="private ledger JSON (never commit)")
    ap.add_argument("--history", required=True, type=Path, help="history JSON; created if missing, updated in place")
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--fonts-dir", type=Path, default=None, help="directory holding IBM Plex woff2 files to inline")
    ap.add_argument("--download-fonts", action="store_true", help="fetch the woff2 files into --fonts-dir (or out-dir/fonts) first")
    ap.add_argument("--now", default=None, help="ISO-8601 UTC timestamp for deterministic runs")
    ap.add_argument("--no-history-write", action="store_true")
    args = ap.parse_args(argv)

    ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
    if ledger.get("schema") != SCHEMA:
        print(f"ledger schema {ledger.get('schema')!r} is not {SCHEMA!r}", file=sys.stderr)
        return 2
    history = load_json(args.history, [])
    now = dt.datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)

    fonts_dir = args.fonts_dir or (args.out_dir / "fonts")
    if args.download_fonts:
        got = download_fonts(fonts_dir)
        print(f"fonts downloaded: {got or 'none (using fallbacks)'}", file=sys.stderr)

    model = compute(ledger, history, now)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "report.html").write_text(render_html(model, fonts_dir if fonts_dir.exists() else None), encoding="utf-8")
    (args.out_dir / "report.json").write_text(json.dumps(model, indent=1, default=str), encoding="utf-8")
    (args.out_dir / "prices.json").write_text(json.dumps(model["quotes"], indent=1, default=str), encoding="utf-8")
    if not args.no_history_write:
        new_history = append_history(history, history_entry(model))
        args.history.write_text(json.dumps(new_history, indent=1), encoding="utf-8")
    print(console_summary(model))
    return 0


if __name__ == "__main__":
    sys.exit(main())
