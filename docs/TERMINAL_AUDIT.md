# Claude Stocks Terminal — audit of the live terminal (as-built, 2026-09-11)

Audit of the daily research terminal as it actually runs, made before any change.
Every row is labelled **VERIFIED** (read from the live page, its embedded state
capsule, its run log, the account's Routine list, or this repository),
**INFERRED** (a conclusion drawn from those readings), or **UNAVAILABLE** (could
not be established from this environment). Private specifics (balances,
holdings, wallet and artifact identifiers, Routine identifiers) are deliberately
absent from this public record; the audit workspace that holds them is
session-local and is described in `TERMINAL_HANDOFF.md`.

## What the live terminal is

- One private artifact page, republished in place. The page is the only durable
  store: an HTML comment carries a JSON "canonical state" capsule (schema `v43`,
  144 ranked rows, model definitions, integrity-gate records) and a second
  comment carries a hash-chained run log (89 `RUN|…|PUBLISHED` lines at V53).
  **VERIFIED** (page read back on 2026-09-11; capsule and run log parsed by
  `terminal/legacy.py`).
- Three cloud Routines write it: a 6 AM daily re-rank, an hourly rules sentinel,
  and a daily memecoin board, each in a fresh session with a long prompt.
  **VERIFIED** (Routine list: cron `0 10 * * *`, `26 * * * *`, `0 10 * * *`).
- The build pipeline that produced V50–V53 existed only in a chat session's
  scratchpad and is lost when that container is reclaimed. The page's own health
  card says so: "verify.py absent in this container — NOT VERIFIABLE by script".
  **VERIFIED** (V53 health card) — no terminal code existed in this repository
  before this change. **VERIFIED** (`git ls-files` at `6ff080b`).

## Audit matrix

| Feature / tab | Observed behavior | Source files | Data source | Persistence | Refresh mechanism | Test evidence | Gap | Preserve / fix / add |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Header, ticker | Version tag, ET stamp, headline prose, account totals written into prose. VERIFIED | none in repo (page only) | prior run output, screenshots | page HTML | daily Routine, hourly sentinel, chat rebuilds | none (UNAVAILABLE) | totals live in prose, not in a structured record | Migrate totals to portfolio documents; keep the headline as prose |
| Action page | Ten prose orders for the day. VERIFIED | page only | run reasoning | page HTML | daily Routine | none | orders have no recommendation id, no cooling clock, no evidence ids | Add immutable recommendations with ids, evidence and cooling; carry the legacy orders unchanged |
| Expiry desk (options) | Payoff table for two open puts. VERIFIED | page only | broker screenshot | page HTML | screenshots only | none | options are outside the written mandate (prohibited instrument) | Carry as a legacy view; never score |
| Optimizer (Board 21) | Six books; the two Schwab IRAs pooled as "one book". VERIFIED | page only | screenshots | page HTML | screenshots only | none | no Roth / Rollover position split anywhere on the page | Fix: two distinct portfolio documents with their own limits; pooled book carried and labelled |
| Accounts ledger | Cards per account, screenshot-marked; one sleeve carried at an older mark and labelled. VERIFIED | page only | screenshots | page HTML | screenshots only | none | freshness is prose, not a computed state | Preserve the screenshot-only rule; add per-field freshness states |
| Board 01 stocks | 58 rows, zone model from 5-day and 30-day windows, re-quoted at the close from a public quote site (per stamp). VERIFIED (stamp) / INFERRED (source reliability) | page only | public quote pages | page HTML | daily Routine | none | no rubric, no evidence ids, ordering carried by hand | Add the 100-point scorecard board; keep the legacy board unscored |
| Board 02 crypto | 32 rows priced by one aggregator call; ordering model `ENTRY_QUALITY_V44_2`, "re-implemented … after the original code was lost with the container" (capsule note). VERIFIED | page only | aggregator API | page HTML | daily Routine | none | the code is not durable; identity is by aggregator id | Move calculations into `terminal/`; contract-first identity |
| Board 03 PulseChain | Not re-fetched because rows are "pinned to pool addresses the page does not print". VERIFIED (capsule `boardNotRefreshed`) | page only | on-chain reads | page HTML | chat only | none | pool identity not stored | Store identity per row (`identity.py`); until then carry STALE |
| Board 04 TON | 10 rows re-priced. VERIFIED | page only | aggregator API | page HTML | daily Routine | none | as Board 02 | as Board 02 |
| Boards 05 / 06 memecoins | Roster audit with venue, pool and DEX gates recorded per candidate. VERIFIED (capsule `gates`) | page only | aggregator and DEX APIs | page HTML | daily Routine | none | gates keyed by aggregator id; not testable | Preserve gate logic as fatal flags and facts in security documents |
| Boards 13 / 16 / 17 | Overall (quality, conviction, understanding), entry, combined call. VERIFIED (formulas in capsule) | page only | judgment scores | page HTML | daily Routine | none | judgment factors carry no evidence ids | Migrate rows unscored; replace with the rubric only when scored from evidence |
| X-ray | Exposure stack across accounts. VERIFIED | page only | screenshots | page HTML | screenshots | none | none beyond staleness | Carry as legacy |
| Calls ledger (Board 07) | 50 calls graded in prose. VERIFIED | page only | run reasoning | page HTML | daily Routine | none | no tradable-reference convention; grades are prose | Add outcome documents graded from the next open |
| Decision journal (Board 14) | Dated decisions graded on a clock. VERIFIED | page only | Joe's messages | page HTML | chat | none | none beyond structure | Carry as legacy |
| Signal desk (Board 15) | External feed calls graded against O/H/L/C. VERIFIED | page only | feed posts | page HTML | chat | none | none beyond structure | Carry as legacy |
| Exposure calendar | Dated events touching the book. VERIFIED | page only | run research | page HTML | daily Routine | none | events carry no evidence ids | Carry; add evidence ids for new entries |
| System health | Sources table, zone scorecards, fire log, run cards. VERIFIED | page only | run self-report | page HTML | every writer | none | verification is read "by hand"; no script in any durable place | Fix: `python -m terminal.cli verify` |
| Canonical capsule | Schema `v43`; governance flags; models; 33 gate records. VERIFIED | page only | run output | HTML comment | every writer | none | the only structured store is embedded in a 0.8 MB page | Add the artifact database as the store (`store.py`) |
| Run log | 89 records. Under base-of-run-N = result-of-run-N−1, 38 of 88 links do not verify, almost all at sentinel runs; one chat key was published three times. VERIFIED (computed) / cause INFERRED | page only | writers | HTML comment | every writer | none | either two writers hash different representations of the page, or sentinels build on stale reads; not decidable from the log | One hashing rule over canonical JSON, enforced by the release gate; idempotency enforced on append |
| Scheduling | Daily and memecoin Routines at 10:00 UTC, sentinel at :26 hourly; two one-shot "DST corrector" Routines exist for fall 2026 and spring 2027. VERIFIED (Routine list) | none | Routine platform | platform | cron | none | a fixed-UTC cron fires at 5:00 AM ET in standard time unless the corrector fires; the corrector's behavior is not verified from here | Health view prints the drift windows; schedule changes are proposed, not made |
| Balances | Only from screenshots; on-chain reads are facts. VERIFIED (capsule governance flags) | none | screenshots, chain | page | chat | none | none | Preserve as a schema rule (`source`, `verification`) |
| Mandate figures | Ten stocks, 13% cash, 13% single-name ceiling, 24-hour cooling, 3–6-month horizon, 10% return goal. VERIFIED (`handoffs/perplexity_portfolio/`) | repo | mandate record | git | manual | `tests/test_terminal_pipeline.py` | the 15% upside hurdle in the implementation prompt conflicts with the recorded 10% return goal; the 12–36-month secondary lens is not recorded in the repository | Policy document records both with `conflict` and `assumption` labels for Joe's decision |
| Repository policy engine | `config/portfolio_policy.toml` scores momentum signals for the Market Operator. VERIFIED | `config/portfolio_policy.toml`, `.claude/agents/market-operator.md` | connector (not run here) | git | manual | existing suite | two scoring systems (repo momentum engine, page entry models) with no shared definition | Policy document names both; rubric adoption is an approval item |
| Build pipeline | Session scratchpad only. VERIFIED absent from the repository | none | n/a | none | n/a | none | lost with every container | Add `terminal/` with tests (this change) |

## Findings that change the design

1. **The store must leave the page.** A page-embedded capsule cannot be queried,
   locked, or verified without re-reading 0.8 MB of HTML. The artifact database
   (256 KiB per document, 5,000 documents, cooperative leases) is the smallest
   store that gives each writer a lock and each document a version.
2. **The run chain does not verify.** Whatever the cause, a chain whose links
   fail 38 times in 88 is not evidence of anything. The new manifest hashes
   canonical JSON of the documents, and the release gate refuses to publish
   over a base that is not the last published result.
3. **Idempotency was advisory.** The same chat key was published three times.
   The ledger now turns a duplicate key into `SKIPPED` on append.
4. **The two Schwab accounts were pooled.** The page carries their totals and
   cash separately but their positions as one book. The migration keeps two
   documents with `distinct_from`, and the release gate fails if a run drops it.
5. **"Verified by hand" is not verification.** The verify command is in the
   repository and in the release gates; the page's health view says which store
   it is reading and whether the chain holds.
6. **Schedules are UTC.** The health view prints the exact ET windows in which
   a fixed-UTC cron fires an hour early. Whether to move to an ET-anchored
   schedule is Joe's decision (a scheduled-task change is always gated).
7. **Scores without evidence ids are opinions.** Legacy zones are carried, not
   promoted: no row receives a scorecard value it did not earn from cited inputs.

## What was not audited

- The routine prompts' behavior under failure (no run was fired from here).
- The public quote and aggregator sources' accuracy (no independent re-fetch).
- The one-shot DST corrector Routines' effect (not fired yet). UNAVAILABLE.
