# Terminal ranking upgrade — audit and implementation record

Status date: 2026-09-12. Code version: the commit that adds `terminal/quant.py`,
`terminal/features.py`, `terminal/entry.py`, `terminal/ledger.py`,
`terminal/ranking.py` and `tests/test_terminal_ranking.py`.

This document is the Phase A audit and the Phase B implementation record for the
quantitative ranking directive. It states what was inspected, what was found,
what changed, what was tested, and what remains blocked. Anything that could not
be inspected is marked **NOT VERIFIED** rather than assumed.

## 1. Current-state audit

Traced the ranking path from ingestion to render before changing anything.

| # | Finding | Evidence | Severity | Disposition |
|---|---|---|---|---|
| 1 | Ranking ran on hand-assigned `[0, 1]` judgment values | `terminal/scorecard.py` — `_score()` consumes a `factors` dict of floats supplied by the caller; nothing derives them from an observation | HIGH | **REPLACED** by `terminal/ranking.py` |
| 2 | Entry price played no part in the score | no cost, spread, depth, notional or venue term appears anywhere in `scorecard.py` | HIGH | **FIXED** — `terminal/entry.py` |
| 3 | One score, no horizons | `scorecard.rank()` returns a single ordering; no 24h/7d/30d distinction exists | HIGH | **FIXED** — horizons held separate, never averaged |
| 4 | No forecast/outcome ledger | `terminal/outcomes.py` grades a *stance* against a reference price. There is no store of published rows, no lineage, no correction mechanism, and no column contract | HIGH | **FIXED** — `terminal/ledger.py`, 39 declared columns |
| 5 | No cross-sectional normalisation | factors are scored on an absolute `[0, 1]` scale; one extreme asset could not be contained because nothing compares assets to each other | MEDIUM | **FIXED** — rank and median/MAD in `terminal/quant.py` |
| 6 | No separation of estimate uncertainty from volatility | neither quantity existed | MEDIUM | **FIXED** — `quant.standard_error` vs `quant.ewma_volatility`, charged separately |
| 7 | Correlated indicators would vote independently | weights are per-factor with no grouping | MEDIUM | **FIXED** — group budgets in `ranking.GROUP_WEIGHTS` |
| 8 | **No scheduler or notification code exists in the package** | `grep -rn "cron\|schedule\|notif\|push" terminal/*.py` returns only policy **strings** inside a document built by `pipeline.py`, plus DST commentary in `clock.py` | HIGH | **NOT VERIFIED** — see §5 |
| 9 | Clock is `America/New_York`; the directive specifies `America/Indiana/Indianapolis` | `terminal/clock.py` line 15 — `ET = ZoneInfo("America/New_York")` | MEDIUM | **OPEN** — needs Joe's confirmation before changing; the two zones agree on DST rules but are not the same identifier |
| 10 | A fixed-UTC cron drifts an hour across DST | `pipeline.py` publishes `cron_utc "0 10 * * *"`, which is 06:00 EDT but 05:00 EST | MEDIUM | **OPEN** — documented, awaiting the schedule decision |

### What is real data versus fixture

- `terminal/fixtures/synthetic_inputs.json` is synthetic and labelled as such.
- The crypto ranking published in the 2.0 artifact uses **live DexScreener
  observations** pulled in-session.
- The equity ranking uses **screenshot-derived** prices, quantities and weights.
  It carries `data_confidence: SCREENSHOT`, and the coverage gate withholds every
  composite because the inputs a return-based model needs are absent.

## 2. The ranking contract

Backward-looking returns and forward-looking forecasts are separate concepts and
separate fields. Prospective rankings exist for 24h, 7d and 30d, held apart;
`ranking.multi_horizon` deliberately returns a mapping rather than a blend,
because averaging a one-day view with a thirty-day view answers no question
anyone asked. 7d is the default.

Per asset the engine reports **opportunity rank**, **entry readiness**,
**structural quality**, **risk flags** and **data/model confidence** as five
distinct fields. The score type is `within_universe_percentile` and the
published note says in terms that it is not a probability of profit.

Universe: preserved as-is — the assets actually held, with verified contract
addresses. Counts for screened / eligible / excluded / scored are published on
every run. No claim of exhaustive coverage is made anywhere.

## 3. The most important design decision

The decision functional requires a `shrunk_expected_gross_return`. A validated
model supplies one. **V1 has no validated model, so V1 supplies none.**

The engine will not convert a composite of percentile ranks into an expected
percentage return. A weighted average of ranks is not a return forecast, and
presenting one as such is the specific failure this rebuild exists to remove.

The consequence is visible and intended: with no external forecast,
`gross_forecast` and `net_edge` are null, and **no asset anywhere reaches
ACTIONABLE**. The engine still does real work — it ranks structural quality,
measures round-trip cost against a stated notional, estimates tail loss and
estimate uncertainty where a return series exists, applies hard blocks, and
reports coverage — but it reports the absence of a validated edge rather than
manufacturing one. `tests/test_terminal_ranking.py::GateNoForcedRecommendations`
asserts this, so the behaviour cannot regress quietly.

When a validated forecast becomes available it is passed to
`rank_universe(..., forecasts=...)` and the functional prices it.

## 4. What changed

### `terminal/quant.py`
Robust cross-sectional statistics. Rank normalisation (van der Waerden normal
scores and fractional ranks on the open interval, ties averaged) and median/MAD
z-scores clipped at three robust sigmas. Small samples are labelled
`LOW_SAMPLE`; zero dispersion returns `ZERO_DISPERSION` and the feature is
removed from the weights rather than contributing a constant. Also expected
shortfall as a **non-negative magnitude** with a 30-observation adequacy gate,
EWMA volatility, downside deviation, max drawdown, James-Stein shrinkage, and a
standard error of the mean kept deliberately distinct from volatility.

### `terminal/features.py`
The feature registry: 16 crypto features, 12 equity features, 8 shared. Each
declares formula, units, lookback, economic rationale, expected direction,
dependencies, availability lag, missing-data policy and evidence status
(`LITERATURE` / `MECHANICAL` / `HYPOTHESIS`). Nothing can reach a score without
a declaration here. Features name the asset classes they are meaningful for,
which is what makes applying a funding rate to an equity, or an earnings yield
to a memecoin, a refused category error rather than a reviewer's catch.

Missing-data policies are `OMIT`, `PENALISE` (absence scores worst observed) and
`BLOCK` (absence stops an actionable rank outright — currently
`liquidity_depth`).

### `terminal/entry.py`
Round-trip cost itemised into spread, fees, square-root impact against a stated
notional, gas and financing. The spread is **not** charged twice when executable
quotes already embed it. The decision functional publishes the gross forecast
and each deduction separately. Missing risk inputs are charged conservative
stand-ins rather than treated as zero risk, so absent data can never improve
actionability. States: `ACTIONABLE`, `WAIT`, `WATCH`, `NO_QUALIFYING_ENTRY`,
`EXCLUDE`. Lambda and kappa are declared risk policy, versioned and published —
not constants presented as findings.

Standardised research notionals are $100 / $1,000 / $10,000. They are sizes for
comparing execution cost across assets, not assumptions about anyone's balances.

### `terminal/ledger.py`
Append-only across 39 declared columns. Corrections are appended carrying
`corrects`; the superseded row keeps its numbers and only its lifecycle marker
moves, so the original stays readable forever. Outcomes are `PENDING` until the
horizon matures. `grade()` raises if handed a fill earlier than
`earliest_entry_at`, which is `published_at` plus a 15-minute execution latency
— making back-dated evidence structurally impossible rather than discouraged.
Excluded assets and passes are retained, because a ledger that records only the
picks cannot say what the process missed.

### `terminal/ranking.py`
Deterministic V1. Weight is budgeted to correlation **groups** then split within
them, so a feature that drops out returns its weight to its own group rather
than to the model at large. Hard blocks are evaluated before scoring, and
cross-sections are computed over the eligible set only, so an unexecutable token
cannot set the percentile scale. Contributions are rounded before accumulation
so the published column sums exactly to the published composite — a reader can
add it up and check.

## 5. NOT VERIFIED — the 06:00 job and the phone push

The directive asks that these not be asserted before inspection. They were
inspected.

`terminal/` contains **no scheduler code and no notification code at all**. The
only trace of a schedule is a set of cron strings inside a policy document
constructed by `pipeline.py`. The live pages are republished by cloud Routines
that live outside this package; their execution logs were not readable from this
session.

Therefore: no claim is made that an unattended 06:00 production job exists, that
a phone push fires on publication, or that a notification was ever received.
Hourly polling would not be continuous monitoring even if it were running, and a
schedule description is not a running job. Building that pipeline is Phase C/D
work and needs deployment approval.

## 6. Validation status

**NO DEMONSTRATED EDGE.** Nothing here has been walk-forward validated. There is
no point-in-time history store yet, so the leakage-resistant validation in
section 8 of the directive (chronological folds, label-overlap purging,
embargoes, reconstructed universe membership, Spearman IC, rank-bucket
performance, calibration, Deflated Sharpe) is **NOT RUN** — correctly, because
running it on reconstructed-from-today data would produce a contaminated result
that looks like evidence.

The ledger is the prerequisite. It starts accumulating rows from the first
published edition; validation becomes possible once enough have matured.

## 7. Acceptance gates

All 12 gates from section 14 are covered by `tests/test_terminal_ranking.py`
(48 tests, passing). Each `test_gate_*` is written adversarially — it attempts
the dishonest behaviour and asserts the refusal. Section 8 records what these
gates do **not** reach.

| Gate | Test class |
|---|---|
| Identical frozen inputs reproduce identical ranks | `GateReproducibility` |
| Future observations cannot alter a published ranking | `GateNoLookahead` |
| Same ticker, different identity, cannot merge | `GateIdentity` |
| Missing/stale data cannot improve actionability | `GateMissingDataNeverHelps` |
| A worse entry cannot improve net opportunity | `GateEntryEconomics` |
| A quality asset can be marked WAIT at a poor entry | `GateEntryEconomics` |
| Zero qualified entries is legal | `GateNoForcedRecommendations` |
| One asset traceable raw inputs → displayed rank | `GateTraceability` |
| Probabilities withheld; percentiles never mislabelled | `GateProbabilityDiscipline` |
| Latency, fills and pending outcomes handled honestly | `GateOutcomeHonesty` |
| Horizons never averaged | `GateHorizonSeparation` |
| Asset classes kept separate | `GateAssetClassSeparation` |

## 8. Where the gates stop: the feed boundary

The gates above constrain **the engine**. They cannot constrain what is handed
to it, and that distinction turned out to matter in practice rather than in
principle.

A live crypto feed built on a DexScreener snapshot was found to be doing two
things the registry forbids, neither of which any gate could see:

1. **Substituting a value the declared formula cannot produce.**
   `ewma_volatility` declares `sqrt(EWMA variance of log returns, half-life 10
   bars)` over a trailing window and carries the largest single group weight at
   25%. It was being fed the absolute value of one 24-hour price change. One
   observation is not an EWMA over ten bars. `residual_momentum` declares a
   beta-adjusted return and was being fed the raw return with no market leg,
   which additionally made it rank-identical to
   `relative_strength_vs_market` — two features casting one vote, inside the
   group budget designed to prevent exactly that.

2. **Substituting `0.0` for an absent observation.** Where the venue published
   no 24-hour change, the feed supplied a zero. Because `ewma_volatility` is
   lower-is-better, a fabricated zero is the *best possible* reading; in a
   falling cross-section the asset with the least data was scored the calmest
   and the strongest, and ranked first. Just over half its composite rested on
   an observation that did not exist.

The engine behaved correctly throughout. It received floats and scored floats.
`GateMissingDataNeverHelps` passes, and passed while this was happening,
because the fabricated value never presented as missing.

**The obligation therefore sits on the feed, and it is not optional:**

- A feature may only be supplied when its **declared formula and lookback are
  actually computable** from the available inputs. If they are not, the feed
  passes `None` and the feature is absent. A value that shares a feature's name
  but not its definition is worse than no value, because it is unfalsifiable
  once it reaches a score.
- An absent observation is passed as `None`. **Never** `0.0`, never a neutral
  midpoint, never a carried-forward previous reading. `None` routes to the
  declared missing policy (`OMIT` / `PENALISE` / `BLOCK`), costs coverage, and
  raises a risk flag. A substituted value does none of that and leaves the
  reader no signal that anything was wrong.
- The horizon label must match the observations behind it. A ranking built
  entirely from 24h inputs is a 24h ranking, whatever horizon the caller
  prefers to publish.

`GateMissingDataNeverHelps::test_gate_substituted_zero_is_indistinguishable_from_a_measurement`
pins this hazard: it asserts that a substituted zero **outranks** an honest
`None` and raises no flag. It is deliberately not a test that the engine is
wrong — it is the standing evidence for why the rule above exists, so the
obligation stays visible to whoever writes the next feed, including the
production job in §5 that does not exist yet.

The consequence of applying the rule to that snapshot feed was that the whole
risk group emptied, coverage fell to 50%, the 60% floor fired, and every crypto
composite was withheld. That is the correct outcome for a snapshot with no
return series, and it is the same outcome the equity view already had for the
same reason.

## 9. Continuation scoring: persistence against exhaustion

`terminal/continuation.py` answers a question the composite in §2 does not:
not *how good is this asset* but *is the move it is making still running*.
The distinction is the one a level cannot make. An asset 30% above its base
because it is trending and an asset 30% above its base because it spiked and
stopped show the same extension and differ only in their rate of change. The
`decay` term measures that rate directly — the recent window's daily pace
against the trend window's — and it is the input that most reorders a ranking
relative to one built on current state.

Three commitments, each of which had a concrete alternative that was rejected:

**Persistence and exhaustion are scored separately, then netted.** A single
blended number cannot distinguish "nothing happening" from "strong trend
fighting a stretched tape", and those call for opposite actions. `Score`
returns both component lists so a caller can display the disagreement rather
than average it away.

**Horizon reweights the same inputs; it does not change them.** Short-horizon
reversal and intermediate-horizon momentum are separately documented effects
with opposite signs, so exhaustion carries 1.40 at 3d and 0.50 at 30d while
persistence runs the other way. A name reading PULLBACK at 3d and CONTINUE at
30d is the model working. These weights are asserted for economic plausibility
and have not been fitted or tested out of sample — the ordering is the claim,
the number is a label on it, and §3 governs: no expected return is produced.

**Exhaustion is divided by the full weight in play, not by the weight
present.** This is not a stylistic choice. Averaging exhaustion over only the
terms that were measured means each additional zero-valued term dilutes the
average and *raises* the score — so a feed could improve any asset by
reporting `0.0` for readings it never took. Under the earlier arithmetic a
missing input scored ten points **better** than the worst real measurement,
which inverts §8 exactly. Two tests pin it: one asserting the score never rises
as any exhaustion input worsens, one asserting a gap is charged as the worst
case.

The last point needs a distinction §8 does not draw. An asset that alone cannot
produce a reading has told you something about itself; a feed outage has told
you something about your pipeline. Charging the second as if it were the first
ranks a whole asset class below another for the analyst's missing API key. So
`score()` takes `systemic_gaps` — terms the caller has established are absent
for the entire cross-section — and drops those for everyone instead of
charging them, while still counting them against coverage. Establishing that a
gap is systemic is the caller's obligation and is not checkable here; naming a
merely inconvenient gap as systemic silently restores the failure this guards.

## 10. Status summary

- **IMPLEMENTED and TESTED** — quant primitives, feature registry, entry
  economics, decision functional, forecast/outcome ledger, deterministic V1
  ranking, continuation scoring (§9), all acceptance gates.
- **IMPLEMENTED, NOT VALIDATED** — the V1 weights and the §9 horizon weights.
  They are hypotheses.
- **NOT RUN** — walk-forward validation, paper portfolio, calibration, challenger
  models. Blocked on point-in-time history that does not exist yet.
- **NOT VERIFIED** — the 06:00 scheduler and the phone push. No such code exists
  in this package.
- **KNOWN LIMIT** — the gates constrain the engine, not what is fed to it. The
  feed-boundary obligations in §8 are enforced by discipline and one pinning
  test, not by the type system. A caller that fabricates an input can still
  produce a confident wrong number.
- **BLOCKED, needs Joe** — the timezone identifier change; the fixed-UTC versus
  ET-anchored cron decision; connecting a price-history and fundamentals feed,
  without which the equity view stays coverage-gated.
- **NEEDS APPROVAL** — any production cutover. The 2.0 page is published as a
  separate versioned artifact; the existing terminals are untouched.
