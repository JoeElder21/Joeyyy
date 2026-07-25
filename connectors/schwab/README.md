# Schwab connector

Read-only client for the Charles Schwab Trader and Market Data APIs, plus the
portfolio analytics that feed the Market Operator agent.

Setup runbook: [`docs/SCHWAB_TRADING_AGENT.md`](../../docs/SCHWAB_TRADING_AGENT.md).

## Read-only guarantee

`client.py` issues `GET` requests only and defines no order-placement method.
`tests/test_schwab_connector.py::CliTests` asserts both facts, so removing the
guarantee breaks the build rather than passing quietly.

## Modules

| Module | Responsibility |
|---|---|
| `config.py` | Settings from the environment layered over a git-ignored `.env` |
| `transport.py` | Injectable HTTP callable, retry with backoff on `429`/`5xx` |
| `oauth.py` | Consent URL, code exchange, renewal, owner-only token store |
| `client.py` | Accounts, positions, quotes, price history, orders, transactions |
| `portfolio.py` | Schwab payloads to holdings, weights, cost basis, concentration |
| `indicators.py` | SMA, EMA, RSI, MACD, ATR, realized volatility, drawdown |
| `signals.py` | Policy-driven scoring, guardrails, verdicts, research questions |
| `report.py` | Markdown daily brief |
| `cli.py` | `login`, `status`, `accounts`, `positions`, `brief` |

## Design notes

**Zero dependencies.** Standard library only, so the connector runs anywhere
Python 3.11 does without a package install.

**No network at import.** Every module imports cleanly with no credential
present, which is what lets the test suite run offline in CI.

**Injectable transport.** `SchwabClient(settings, store, transport)` takes any
`(method, url, headers, body) -> HttpResponse` callable. Tests pass a fake
that records requests and replays canned responses.

**Missing data is `None`, never `0`.** An indicator without enough history
returns `None` and the brief prints `—`. A 200-day average computed from 40
sessions would silently corrupt a hold-or-sell decision, so it is refused.

**Renewal never extends the refresh deadline.** Schwab's 7-day refresh window
belongs to the original consent. `renew()` carries the original deadline
forward, and a test pins that behavior — if it ever reset, the agent would
miss its weekly re-consent and fail at the worst moment.

**Weights are shares of invested capital**, not of account equity, so a large
cash balance does not make every position look artificially small.
