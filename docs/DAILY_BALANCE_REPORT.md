# Daily balance report

A one-page, print-ready balance sheet of every account, produced each morning
by a scheduled Claude Code session from live prices. This document is the
runbook. It contains no holdings: the ledger that drives the report is private
and lives outside this repository.

## What the report shows

For every account: each holding, its quantity, the live price, today's value,
the change in dollars and percent against the tracking baseline, the change
against the broker's cost basis where that is known, and a source code with the
time the price was fetched. Account subtotals, the household total, the change
since the baseline and the change since the prior report sit in the header.
The page prints to a single US Letter sheet.

## Components

| Piece | Where | Privacy class |
|---|---|---|
| `scripts/daily_balance_report.py` | this repository | public, generic: no symbols, quantities or addresses |
| `scripts/render_report_pdf.mjs` | this repository | public: Playwright Letter PDF renderer |
| `tests/test_daily_balance_report.py` | this repository | public: synthetic fixtures only |
| `ledger.json` | private artifact file (the owner's claude.ai account) | private: quantities, baselines, source specs |
| `history.json` | private artifact file | private: one entry per report |
| `report.html`, `report.pdf`, `archive/<date>.pdf` | private artifact | private |

Never commit `ledger.json`, `history.json`, a rendered report or a screenshot
to this repository (AGENTS.md section 4). `scripts/privacy_guard.py` is part of
the validation surface for exactly this reason.

## Sourcing rules

* Every holding carries a **primary** and, normally, a **secondary** price
  source. Both are fetched; the gap is compared with the tolerance for the
  asset class (`tolerance_pct` in the ledger). A gap above tolerance keeps the
  primary price and flags the row `‡` (DISAGREE).
* A failed primary falls back to the secondary and flags the row `§`.
* If neither source answers, **no price is invented**: the row is flagged `*`
  (STALE), the last known value (prior report, else baseline) is carried into
  the totals, and the footer states how many rows were carried.
* DEX-priced tokens use the deepest-liquidity pool for the exact contract
  address on the chain actually held; a pool under the liquidity floor flags
  `†` (THIN).
* Perpetual futures are marked as unrealized P&L
  `(mark − entry) × contracts × contract size`. Without an entry price the
  baseline P&L is carried and the row flags `¶`.
* Quantities derived from a screenshot rather than an exact statement are
  marked `~` until exact figures replace them.

Fetcher types available in a ledger `price` spec:

| `type` | fields | source code |
|---|---|---|
| `yahoo_chart` | `symbol` | `Y` |
| `json` | `url`, `path` (dotted, `[i]` indexes), optional `code` | `J` / `code` |
| `coinbase_spot` | `pair` such as `BTC-USD` | `CB` |
| `coinbase_ticker` | `product` | `CBX` |
| `coingecko` | `id` | `CG` |
| `dexscreener` | `chain`, `address`, optional `pair_address`, `min_liquidity_usd` | `DS` |
| `geckoterminal` | `network`, `address` | `GT` |
| `static` | `value` | `FIX` |
| `manual` | `value`, `asof` | `MAN` |

All endpoints are public and key-free. Requests are paced
(`DAILY_BALANCE_PACE_SECONDS`, default 0.6 s) and retried with backoff, with a
longer wait on HTTP 429.

## Ledger schema (synthetic example)

```json
{
  "schema": "savage-daily-balance/1",
  "owner_label": "Example Household",
  "baseline": {"date": "2026-01-01", "time_et": "18:00", "note": "statement screenshots"},
  "tolerance_pct": {"equity": 1.5, "major_crypto": 1.0, "dex_token": 6.0, "default": 2.0},
  "notes": ["free-text lines printed in the footer"],
  "accounts": [
    {
      "id": "broker", "name": "Example Brokerage", "venue": "Broker A",
      "cash": [{"label": "Cash", "amount": 100.0, "apy": null, "asof": "2026-01-01"}],
      "positions": [
        {"symbol": "AAA", "name": "Alpha Fund", "kind": "etf", "asset_class": "equity",
         "qty": 10, "qty_status": "exact", "baseline_price": 100.0, "baseline_value": 1000.0,
         "cost_basis_total": 900.0, "note": "",
         "price": {"primary": {"type": "yahoo_chart", "symbol": "AAA"},
                   "secondary": {"type": "json", "code": "NQ",
                                 "url": "https://api.nasdaq.com/api/quote/AAA/info?assetclass=etf",
                                 "path": "data.primaryData.lastSalePrice"}}}
      ],
      "perps": [
        {"symbol": "AAA PERP", "side": "long", "contracts": 2, "contract_size": 0.5,
         "entry_price": 100.0, "baseline_pnl": 5.0,
         "mark": {"primary": {"type": "coinbase_spot", "pair": "AAA-USD"}}}
      ]
    }
  ]
}
```

`baseline_value` is the holding's value on the baseline date; gains are
measured against it. `cost_basis_total` is optional and drives the "vs cost"
column.

## Running by hand

```bash
python scripts/daily_balance_report.py \
  --ledger /private/ledger.json --history /private/history.json \
  --out-dir /private/out --download-fonts
node scripts/render_report_pdf.mjs /private/out/report.html /private/out/report.pdf
```

Outputs: `report.html` (self-contained, fonts inlined when available),
`report.json` (the computed model), `prices.json` (every quote with URL, time,
flags and errors), and the updated `history.json`. `--no-history-write` makes a
dry run. `--now 2026-01-15T14:35:00Z` pins the clock for reproducible output.

## Scheduled run

The owner's Routine fires a fresh Claude Code session each weekday and weekend
morning at 09:35 America/New_York. The session:

1. fetches this branch and reads the private artifact's `ledger.json` and
   `history.json` with the Artifact tool;
2. runs the two commands above;
3. checks the console summary: no `NO PRICE` rows, no account moving more than
   25% without a visible market reason, account totals reconciling to their
   rows;
4. republishes the private artifact with the new page, `history.json`,
   `report.pdf` and `archive/<date>.pdf`, sends the PDF to the owner, and
   replies with the console summary only.

The run is read-only against every venue. It never places, modifies or cancels
an order, never estimates a balance, never writes private data to this
repository, and never contacts a third party (AGENTS.md section 9).

## Updating holdings

Tell any Claude Code session what changed (a trade, a transfer, exact share or
token counts, a perp entry price). The session edits the private
`ledger.json`, sets the new position's `baseline_value` to its value on the day
it was added (so its gain starts at zero), republishes the artifact file, and
the next morning's report reflects it. Screenshots of the broker's list view
and the exchange's asset pages are the fastest way to supply exact figures.
