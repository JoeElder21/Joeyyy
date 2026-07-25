# Market Operator — Schwab portfolio agent

End-to-end setup for connecting a Charles Schwab brokerage account to the
Market Operator agent, and the daily operating routine once it is connected.

The agent reads holdings, scores them, researches them, and recommends. It
does not trade. That boundary is enforced in code, not just in the prompt:
`connectors/schwab/client.py` issues `GET` only and has no order-placement
method, and `tests/test_schwab_connector.py` asserts that this stays true.

---

## 1. What only you can do

Four things require your identity and cannot be delegated to any agent:

| Step | Why it is yours |
|---|---|
| Create a Schwab developer account | Identity verification against your Schwab login |
| Register an app and wait for approval | Schwab reviews each app before enabling it |
| Approve the OAuth consent in a browser | Your Schwab credentials, entered only on schwab.com |
| Re-approve every 7 days | Schwab caps the refresh window at 7 days, with no extension |

Everything after that is automatic.

---

## 2. Register the app

1. Go to [developer.schwab.com](https://developer.schwab.com) and create a
   developer account. It is separate from your brokerage login.
2. Create an app. Select **both** API products:
   - **Accounts and Trading Production** — holdings, balances, orders
   - **Market Data Production** — quotes and price history
   Without the second one there is no price history, and without price
   history there are no signals.
3. Set the callback URL to exactly:
   ```
   https://127.0.0.1:8182
   ```
   Schwab only accepts `127.0.0.1` as the callback host, it must be HTTPS,
   and it must match what you configure locally byte for byte. Omitting the
   port means port 443, which is a different URL.
4. Submit. The app first shows **Approved — Pending**, then moves to
   **Ready For Use**, typically after a few days. Nothing below will work
   until it reaches *Ready For Use*.
5. Copy the **App Key** and **App Secret** from the portal.

---

## 3. Configure locally

> Run this on a machine you control — your laptop, or a small always-on box.
> A Claude Code web session runs in a throwaway container that is wiped when
> the session ends, so a token stored there would not survive, and the OAuth
> step needs a real browser anyway.

```bash
git clone <this repo>
cd Joeyyy
cp .env.example .env
```

Fill in `.env`:

```
SCHWAB_APP_KEY=<App Key from the portal>
SCHWAB_APP_SECRET=<App Secret from the portal>
SCHWAB_CALLBACK_URL=https://127.0.0.1:8182
```

`.env`, `secrets/`, and `runtime-memory/` are all git-ignored. The
repository's privacy guard (`python scripts/privacy_guard.py`) fails the
build if a credential ever reaches a tracked file.

No third-party packages are required — the connector uses only the Python
3.11+ standard library.

---

## 4. Authorize

```bash
python -m connectors.schwab.cli login
```

The command prints a Schwab URL. Open it, sign in, and choose which accounts
the agent may read.

Your browser will then land on an **error page** at `127.0.0.1:8182`. That is
expected and correct — nothing is listening there, and the data you need is
in the address bar. Copy the entire URL and paste it back into the prompt.

The token is written to `secrets/schwab-token.json` with `0600` permissions.

Verify:

```bash
python -m connectors.schwab.cli status
```

```
Access valid:     yes (29 min remaining)
Refresh valid:    yes (7.0 days remaining)
```

---

## 5. The 7-day wall

This is the single most important operational fact about the Schwab API.

- The **access credential lasts 30 minutes**. The connector renews it
  automatically, so you will never notice this one.
- The **refresh credential lasts 7 days and cannot be extended.** There is no
  setting, no scope, and no plan that changes this.

So once a week you must re-run `login` in a browser. Everything in between is
hands-off. `status` warns when fewer than 2 days remain, and the agent is
instructed to put that warning at the top of the brief.

Put a weekly recurring reminder on your calendar now. If you miss it, the
next brief fails with `ReconsentRequired` and tells you exactly what to run.

---

## 6. Daily use

```bash
# Human-readable brief
python -m connectors.schwab.cli brief

# Structured output for the agent, also saved to runtime-memory/portfolio/
python -m connectors.schwab.cli brief --json --save

# Just the holdings
python -m connectors.schwab.cli positions

# A specific account, by its last four digits
python -m connectors.schwab.cli brief --account 4321
```

The brief reports, per position: weight, cost basis, unrealized return,
1-week / 1-month / 3-month returns, RSI, MACD, moving-average posture,
realized volatility, distance from the 52-week high, any guardrail breach,
and a composite score resolved to **ADD / HOLD / WATCH / TRIM / EXIT**.

At the book level it reports concentration, cash weight, and largest
position against the caps in `config/portfolio_policy.toml`.

### Then run the agent

The CLI is the mechanical half. The agent is the half that reads the news.

In Claude Code:

```
Use the market-operator agent to run today's brief.
```

The agent runs the commands above, then takes every position flagged
`needs_corroboration` and researches it on the open web — earnings, filings,
guidance changes, analyst revisions, sector context — before committing to a
recommendation. Its contract is `.claude/agents/market-operator.md`.

A momentum score reads price and nothing else. Price does not know a company
lost its CFO yesterday. That is the entire reason the research pass exists,
and why the agent is forbidden from presenting a raw score as a
recommendation.

---

## 7. Scheduling it daily

**Option A — cron on your own machine** (most reliable, since the token lives
there):

```cron
# Weekdays at 8:15am, before the US open
15 8 * * 1-5 cd /path/to/Joeyyy && /usr/bin/python3 -m connectors.schwab.cli brief --save >> runtime-memory/portfolio/cron.log 2>&1
```

**Option B — a Claude Routine** for the analysis layer. Ask in a Claude Code
session:

> Create a routine that runs the market-operator agent every weekday at 8:15am.

Option B still depends on the token from Option A's machine being reachable,
so most setups run the CLI locally and let the routine handle research and
delivery.

---

## 8. Tuning the agent

`config/portfolio_policy.toml` is the rulebook. Every verdict traces back to
a number in that file, so if you disagree with the agent, change the file
rather than arguing with the model. The guardrails worth setting first:

| Setting | Default | Meaning |
|---|---|---|
| `max_position_weight` | 0.15 | Single-name cap, as a share of invested capital |
| `stop_loss_pct` | -0.15 | Unrealized loss that forces a review |
| `trailing_stop_from_high_pct` | -0.25 | Decline from the 52-week high that forces a review |
| `min_cash_weight` | 0.02 | Dry-powder floor |
| `max_annualized_volatility` | 0.65 | Realized volatility ceiling |

A guardrail breach overrides the momentum score. A winner that has grown to
40% of the book is still a trim — that is the point of a guardrail, and it is
the rule most likely to save real money.

---

## 9. Honest limits

Read this section before relying on any of it.

- **Not advice.** This is a rules engine plus a research agent. It is not a
  licensed investment adviser and cannot account for your tax situation, time
  horizon, or obligations.
- **No trading.** By design. If you ever want execution, that is a separate,
  deliberate decision with its own confirmation gates — not a flag on this
  connector.
- **Crypto is not covered by this connector.** Schwab's Trader API serves
  equities, ETFs, and options. Schwab does not offer spot crypto trading, so
  no Schwab API exposes a spot crypto position. Crypto-linked ETFs and
  futures held in the account *do* appear as ordinary positions. For spot
  crypto market data, use a dedicated source — the Crypto.com MCP server
  available in Claude sessions covers tickers, order books, and candles.
- **Technical signals are weak predictors on their own.** Moving averages and
  RSI describe what price has already done. They are used here to *triage*
  which positions deserve research attention, not to forecast.
- **One year of daily candles.** Enough for a 200-day average and a 52-week
  range; not enough for multi-year regime analysis.
- **Delayed or indicative quotes** are possible depending on your app's market
  data entitlement. Check a price against Schwab's own app before acting on
  anything time-sensitive.
- **The agent can be wrong.** It is required to state its counter-case and
  what would change its mind. Read that part.

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ReconsentRequired` | 7-day window closed | `python -m connectors.schwab.cli login` |
| `HTTP 400` on login | Callback URL mismatch | Make `.env` match the portal exactly, including the port |
| `HTTP 401` on every call | App reset or credentials rotated | Re-copy the key and secret, then `login` again |
| `HTTP 403` on market data | Market Data product not enabled | Add it to the app in the portal |
| `HTTP 429` | Throttled | The client already retries with backoff; reduce run frequency |
| Empty account list | App approved but accounts not linked | Re-run `login` and tick the accounts at the consent screen |
| `no price history returned` for a symbol | Delisted, or a non-equity instrument | Expected for cash sweeps; investigate otherwise |

---

## 11. Validation

```bash
python scripts/privacy_guard.py          # no credential reached a tracked file
python -m unittest tests.test_schwab_connector -v
```

74 offline tests cover the OAuth lifecycle (including that renewal never
silently extends the 7-day deadline), payload parsing, indicator math,
verdict resolution, guardrail overrides, and the read-only guarantee. None of
them contacts Schwab.
