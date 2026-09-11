# Claude Stocks Terminal — architecture of the revamped edition

Two workflows, one store, one page.

## Development workflow (this repository)

```
edit terminal/*.py  ->  python -m unittest discover -s tests -p "test_terminal_*.py"
                    ->  python -m terminal.cli dry-run --inputs terminal/fixtures/synthetic_inputs.json --store /tmp/run --render /tmp/run.html
                    ->  python -m terminal.cli verify --store /tmp/run
                    ->  task validate  (the repository's full surface)  ->  pull request
```

Nothing in the development workflow touches a broker, a wallet, a Routine, or
the live page. The fixture is synthetic; the dry run exercises every stage and
every failure injection without a model or the network.

## Daily research workflow (production, per run)

```
Routine fires (UTC cron)  ->  fresh session reads policy/current and the last snapshot
  1 orchestrator      acquire the lease on runs/lock (store adapter NOT BUILT: the package
                      ships an in-memory lock with the same semantics); refuse a published key
  2 data steward      validate inputs; freshness per field; identity contract-first
  3 analysts          bounded fan-out by tier (T1 owned, T2 mandate, T3 screened, T4 mentions)
  4 quant             scorecards, scenarios, probability-weighted return, hurdle
  5 risk              limits per portfolio, the two Schwab IRAs never pooled
  6 recommendations   immutable, evidence-cited, cooling clock on BUY/ADD
  7 critic            two rounds at most; unresolved blocking challenge blocks
  8 outcomes/learning grade prior recommendations from the next open; ledger
  9 release/QA        schema, chain, size, freshness labels, immutability, invariants, critic
  -> write documents  -> swap snapshots/current  -> render  -> republish (url + file_path + label only)
```

`terminal/pipeline.py` is the reference implementation of stages 1–9. In
production the analyst stages are filled by the roles in `terminal/agents/`;
their outputs are documents, and only the orchestrator writes. Two adapters are
not built yet and are labelled so in `TERMINAL_HANDOFF.md`: the store-backed
lease (the package's `RunLock` is in-memory and protects one process only) and
the artifact-db reader/writer inside a Routine session (today the publishing
tool's `read_db`/`write_db` calls carry the documents).

Crypto rows are ranked and shown, but while the crypto rubric is `PROPOSED`
the pipeline issues no stance and no recommendation for them.

## The store

Collections (`terminal/store.py`):

| Collection | Document | Mutability | Schema |
| --- | --- | --- | --- |
| `policy` | `current` | replaced by approval only | `policy` |
| `portfolios` | one per account | replaced on re-mark from a screenshot | `portfolio_state` |
| `evidence` | one per record | append | `evidence` |
| `security` | one per asset (canonical id) | replaced per run | `security_research` |
| `boards` | one per ranking or legacy board | replaced per run | `board` |
| `recommendations` | one per recommendation | **immutable** (store refuses edits and deletions; `verify` re-checks content hashes) | `recommendation` |
| `outcomes` | one per graded recommendation | append / update as horizons pass | `outcome` |
| `learning` | `current` | replaced per run, lessons append | `learning` |
| `runs` | one per run, plus `legacy-chain` | append | `research_run` |
| `health` | `current` | replaced per run | `health` |
| `snapshots` | `current` | swapped last, atomically | `snapshot` |
| `legacy` | one per carried section | frozen at migration | none |

Three adapters share one interface: `MemoryStore` (tests), `JsonDirStore`
(development, one file per document), and the artifact database reached through
the publishing tool's `write_db`/`read_db` calls using `write_plan()` batches of
at most 50 writes. The page itself embeds the snapshot it was built from and,
when the `db` capability resolves in the viewer, compares it with
`snapshots/current` and says whether the store holds something newer.

## Identity, freshness, time

- `identity.py`: equities are `eq:<MIC>:<TICKER>`; tokens are
  `cx:<chain>:<contract>` with EVM addresses lower-cased and base58 preserved.
  Symbol collisions are reported, never resolved by guessing.
- `freshness.py`: equity prices are fresh at or after the last regular close;
  other fields carry wall-clock limits. Boards are `LIVE`, `STALE` or
  `DEGRADED` by computation.
- `clock.py`: America/New_York with the NYSE calendar for 2026 and 2027 (a
  date past the table is a FAILED run, not a guess); `dst_drift`
  names the days a fixed-UTC cron fires at the wrong ET hour;
  `starts_vs_ready` is the honest stamp ("starts 6:00 AM, ready 6:41 AM").

## Rankings

`scorecard.py` holds the adopted 100-point equity rubric (fundamentals 20,
valuation 20, catalysts and revisions 15, downside protection 15, portfolio fit
10, technicals and liquidity 10, evidence quality 10). Unscored factors leave
the denominator; a missing core factor makes the asset `INSUFFICIENT`. The
crypto rubric is `PROPOSED` (see `TERMINAL_CRYPTO_RUBRIC_PROPOSAL.md`) and every
result from it says so. `scenarios.py` defines total return once and requires
probabilities that sum to one. `outcomes.py` grades from the first regular
open on the next session date after publication (or the first same-session
print when published during the session), requires the benchmark reference on
the same session, and accepts the horizon print only within five days of the
horizon end; a WATCH or PASS carries no position and is VOID.

## Views

Today · Stock rankings · Crypto rankings · Portfolio 1 · Portfolio 2 · Other
accounts · Asset detail · Risk and catalysts · Critic · Performance · History /
as-built · Memory / learning · Sources / health. `render.py` builds all
thirteen server-side; without JavaScript every view is shown stacked, and no
external font or script is loaded.

## Boundaries

Read-only research. No order, no signature, no credential, no spending
authority. Balances update only from screenshots. The live page and its
Routines are not modified by anything in this package; cutover is a separate,
approved step (`TERMINAL_MIGRATION.md`).
