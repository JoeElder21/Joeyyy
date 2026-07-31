# Joe Investment Mandate

**Effective date:** 2026-07-28
**Mandate type:** Complete research mandate and normalized model portfolio
**Decision authority:** Joe alone authorizes any real transaction. Perplexity researches, updates evidence, and recommends; it never executes.

## Objective

- **Primary return goal:** seek a 10% total return over a rolling 3–6-month decision horizon.
- **Relative goal:** outperform the S&P 500 Total Return Index by at least 3 percentage points over the same measurement window.
- **Benchmark:** S&P 500 Total Return Index; use `SPY` total return, including distributions, as the practical comparison series when index data are unavailable.
- **Risk tolerance:** moderate-aggressive but unlevered. Accept ordinary equity volatility, while managing the portfolio to a 15% maximum peak-to-trough drawdown review threshold.
- **Construction target:** ten stocks at 8.7% of total portfolio value each and 13% cash. The stock sleeve totals 87%.
- **Rebalancing band:** a core position may range from 6% to 11%; 13% is a hard single-name ceiling. Cash may range from 10% to 25% as opportunities and risk change.

These are decision targets, not promises. If evidence does not support the return goal within the risk limits, hold additional cash rather than lower the five-tenet standard.

## Decision philosophy

1. **Capital preservation before participation.** Missing a rally is preferable to owning an unverified thesis.
2. **Quality at a sensible price.** Prefer liquid, financially resilient industry leaders with observable demand and multiple ways to win; reject narrative-only upside.
3. **Evidence before outcome.** Record every recommendation in `06_Thesis_Ledger.csv` before later price action can bias the rationale. Primary sources govern company facts.
4. **Probability, not certainty.** Use bear/base/bull scenarios, explicit probabilities, falsifiable invalidation conditions, and expected value. Never convert model confidence into fact.
5. **Portfolio contribution over isolated attractiveness.** Compare each idea with cash, the benchmark, and existing factor/theme exposure. Size from plausible downside and correlation.
6. **Rules override urgency.** Any five-tenet failure, automatic rejection, or risk-limit breach overrides technical momentum, analyst enthusiasm, and fear of missing out.
7. **Human authority remains final.** A recommendation is decision support, not fiduciary, tax, or legal advice and never constitutes an order.

## 24-hour cooling rule

- The clock begins only when a complete ledger record contains the thesis, five-tenet result, entry method, target weight, scenarios, catalysts, risks, and invalidation conditions.
- Wait at least 24 hours before any new position, addition, or discretionary re-entry. A material thesis change restarts the clock.
- There is no exception for price movement, earnings, analyst action, social-media urgency, or fear of missing out.
- Risk-reducing review of an existing position may begin immediately, but any transaction remains Joe’s decision and must be journaled from broker-confirmed data.

## Exclusions

Exclude options, margin, leverage, short selling, futures, swaps, contracts for difference, inverse or leveraged funds, penny stocks, blank-check companies, illiquid/unlisted securities, rumor-dependent theses, paid promotion, and binary-event speculation with unmeasured downside. Also exclude any security that fails a tenet, breaches a risk limit, lacks reliable market data, or cannot be explained and valued from current evidence.

## Perplexity operating instructions

1. Treat `02_Current_Portfolio.csv` as the complete **normalized model baseline**, not as a broker statement. Do not ask Joe for holdings before beginning research.
2. At the start of each run, retrieve current prices, company filings, investor-relations releases, earnings dates, consensus context, and benchmark total return. Timestamp every retrieved figure and link its source.
3. Convert each relative entry rule in `05_Watchlist.csv` into a dollar range from the same timestamped live price. Do not treat stale values as executable quotes.
4. Re-score all five tenets, update scenarios, and calculate post-recommendation position, sector, theme, speculative, and cash exposures.
5. Return exactly one status per security: `REJECT`, `WATCH`, `CANDIDATE`, `HOLD`, `TRIM`, or `EXIT-REVIEW`. `CANDIDATE` means research-qualified after the cooling period; it is not a trade instruction.
6. Preserve ledger history. Add a superseding row rather than modifying the original pre-outcome record.
7. Write actual transactions to `07_Trade_Journal.csv` only when a broker confirmation is present. Never infer that a model allocation was executed.

For every conclusion, label source-backed facts, calculations, judgment, assumptions, and unknowns separately. Include what would change the conclusion and a counter-case strong enough to falsify the thesis.
