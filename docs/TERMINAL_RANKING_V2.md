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

### 8.1 The period that has not closed

A second feed defect of the same family was found twice in one refresh cycle,
and reached a published ranking both times. It is not a substituted value: the
number is real, computed by the declared formula, from the venue's own data.
The problem is that **the market has not finished producing it**.

A calendar-aligned daily bar opens at a fixed time and is stamped with that
open. Requested part-way through its day, a feed returns it alongside closed
bars, indistinguishable in shape — same fields, same spacing, a plausible
close. It is not a session. Its close is the last trade, not the day's close.

Features computed over sessions ask a **categorical** question of each bar —
was this an up day or a down day? — and a forming bar has no settled answer.
`up_volume_share`, the volume-weighted read on buyers against sellers, is
computed by exactly that bucketing. In the observed case one asset's forming
bar crossed its open mid-session, its up-volume share moved nine points, and it
moved nine places in the published ranking. No new information arrived; only
the clock moved.

What makes this a ranking defect rather than noise is its direction. A forming
bar is **systematically biased toward the session's drift so far, across the
whole cross-section at once**. On a broad up day every asset's forming bar
lands in the up bucket together and every up-volume share is inflated together,
so the error does not cancel between assets — the ranking reads a market-wide
intraday drift as though it were thirty sessions of evidence.

**The rule:** a period that has not closed is not a session, and is excluded
from any feature computed over sessions. `terminal/sessions.py` implements it
and `tests/test_sessions.py` pins it, including
`ExhaustsTheClock::test_a_forming_bar_can_flip_the_feature_it_feeds`, which
asserts the hazard rather than the fix: a one-cent difference in a bar the
market can still reverse moves the feature by more than forty points.

Two boundaries on the rule, both of which have bitten:

- **Not every feed is exposed.** The rule is about calendar-aligned periods. A
  rolling series of samples spaced one period apart, each taken at the same
  offset from request time, has **no** forming member — every point closes a
  full window ending at the sample. Both shapes are in use in this repository's
  crypto sources and they look alike in a list of timestamps. `completed()`
  therefore takes the period explicitly and refuses to infer it.
- **The stamp convention must be established, not assumed.** Reading a bar
  stamped with its *close* as though it were stamped with its *open* discards
  good bars — conservative and wrong. The mirror error, subtracting a period
  from stamps that were already opens, readmits precisely the forming bar the
  rule exists to remove. `start_of` exists to make the choice explicit, and
  both directions are tested.

Correcting a live crypto board under this rule moved 3 of 14 names and changed
no verdict, so the effect is bounded — but it is bounded *on that day's tape*,
and the FIL episode is what it looks like when it is not. The correction was
also gated: the rebuild was required to reproduce the published numbers exactly
with the forming bar left in before its output was trusted. A recomputation
that cannot reproduce what it claims to be correcting is not a correction.

### 8.2 The range that is not the range

A 52-week high is an **intraday print**. Computing it as `max(closes)` — the
only thing a close-only feed permits — names a different, always-smaller number
the same thing, and a position measured inside that narrowed band always reads
higher than the truth. Across 200 US equities the inflation had a median of
**+0.70 percentage points**, which would be cosmetic anywhere else.

It is not cosmetic here, because `continuation.py` charges a `topped` term that
climbs from nothing to its maximum across the band from 0.95 to 1.00. A name
whose close-based position reads 1.00 and whose real position is 0.9529 collects
a charge of 100 against a true charge of 5.8. Three of 201 names crossed that
threshold on the definition alone, and three of seven positions on a live
holdings board fell a whole verdict band because of it — MIXED to PULLBACK RISK,
published, on a measurement artefact.

The rule, in both directions:

* **Where a feed serves intraday high and low, use them.** `connectors/schwab/
  indicators.trading_range` does, and falls back to a candle's close only for
  the candles that lack detail, so a partial feed still yields the widest range
  its own data supports. An incomplete bar's high and low are dropped with the
  rest of it, per §8.1 — a forming bar's extremes are as partial as its close.
* **Where a feed serves no intraday range at all, say so.** DefiLlama returns a
  price series and nothing else, so a crypto board measured this way is using
  the definition the equity board was corrected away from. The honest response
  is to record it as a known asymmetry between boards, not to substitute a
  number from somewhere else: the direction of the bias is knowable even where
  its size is not, so the disclosure is specific rather than a general caveat.

The general form is the one §8 already states. A feature is defined by what the
feed can actually measure, and a definition silently swapped for the nearest
available one is a measurement error wearing the right label.

### 8.3 The baseline that is the wrong capture

§8.1 and §8.2 are both about the *new* observation. This one is about the old
one, and it is harder to see because nothing in the arriving data is wrong.

A source that reports a change reports two numbers: the value now, and the value
it changed from. The second is the one nobody checks. When a source is read more
than once in a day — as a screenshot-fed venue routinely is — its own stated
prior value can be a reading that has already been **superseded** by a later one
this terminal holds. The arriving figures are then all individually correct, the
change is internally consistent with them, and the comparison still steps
straight over a capture.

The case that produced this rule had an update state a prior value for **eight
of eight venues**, and all eight matched an *earlier* same-day capture rather
than the later one that had replaced it sixteen hours before. The stated
portfolio change was two orders of magnitude smaller than the change against the
marks actually held, and the largest single component of the difference was one
venue's own published day change — a figure that had been reconciled, recorded
and carried on the terminal for three days.

Two properties made it invisible to every check that existed:

* **Nothing is out of range.** A superseded baseline is a real reading. It fails
  no bounds test, no type check, no reconciliation between the figures the
  source itself supplies, because internally the source is consistent.
* **The error is in the comparison, not the data.** Both endpoints can be
  correct and the interval between them still be wrong, which is why freshness
  grading of the arriving observation cannot catch it: the new reading was
  perfectly fresh.

The rule: **a stated baseline is an input and gets checked like one.** Before
any change figure is reported, locate the stated prior value among the
observations held for that venue and say which one it is.
`terminal/freshness.baseline_match` returns `CURRENT`, `SUPERSEDED` or
`UNKNOWN`, matching to the cent, and on `SUPERSEDED` it carries the drift — the
exact amount of change the source's own figure steps over. `UNKNOWN` is a
distinct answer and not a softer `SUPERSEDED`: a baseline that matches nothing
held is one we cannot check at all, and saying so is the finding.

On a mismatch the terminal keeps **its own later marks on both sides** and
restates the change. The source's figure is not corrected in place and not
discarded — it is reported beside the restated one with the reason, because a
reader who has seen the source's number needs to know why this page shows a
different one.

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

## 10. Source policy: DefiLlama first for crypto, and where that stops

The owner's standing instruction is to pull most of the refresh from
DefiLlama. This section records what that means precisely, because a source
policy stated loosely becomes a source policy quietly broken.

**Why it earns the primary slot.** Not breadth — the property that matters is
how it fails. Asked for an address it does not know, `coins.llama.fi` returns
`{"coins":{}}`: empty, not a fabricated price. That is §8's requirement
imposed by the source itself rather than by the caller's discipline, and it is
the opposite of the behaviour observed from a DEX aggregator's search endpoint
earlier in this work, which returned invented chain names and volumes for real
tickers. A source that answers "I don't know" is worth more than a source with
wider coverage that answers anyway.

**What it supplies** (verified live against the full twelve-coin universe):
current price batched, 12/12 covered including two the exchange feed does not
list at all; current price **by contract address**, which prices the memecoin
wallet without touching the aggregator above; up to 300 daily price points per
coin, which is enough for the 50- and 200-day averages, RSI, range position,
extension and `decay`; and upstream N-day percentage change. Every quote
carries a `confidence` field, which the terminal reports and which gates
scoring below 0.90.

**Where it stops, and what must NOT happen there.** Two hard limits:

* **No per-coin volume.** `coins.llama.fi/chart` returns `{price, timestamp}`
  and nothing more; the DEX endpoints aggregate by protocol, not by asset. So
  the up-day volume share — the volume-weighted buys-versus-sells — cannot
  come from DefiLlama. It stays on exchange candles, and for a coin no
  exchange in the set lists, the feature is `None` and coverage falls. It must
  never be approximated from price alone: a price-derived stand-in wearing a
  volume-weighted label is precisely the substitution §8 forbids.
* **No equities.** DefiLlama is crypto-only. The stock board takes nothing
  from it, and "most of the data" cannot be read as "all of it" without
  inventing coverage that does not exist.

**Two different doors, and only one of them is open.** `docs/DEFILLAMA_MCP_MOUNT.md`
registers DefiLlama's hosted *MCP server* as a governed mount. This section
describes its *public REST API* (`coins.llama.fi`, `api.llama.fi`), and the two
are not interchangeable: the mount is registered but **not verified**, because
the endpoint requires OAuth and a paid subscription and answers the probe with
HTTP 401, while the REST path needs no credential and is what the verification
above actually exercised. So the refresh runs on REST today. If the mount is
ever authenticated, this section is what has to be revisited — not silently
superseded, because the two paths do not serve identical data.

**Changing the primary source moves numbers, and that is not a defect.** On
the first parallel run, one asset's trend alignment read `0` against DefiLlama
and `1` against the exchange series, because the two carry different history
depths — 235 daily points versus 300 for that coin — so the 200-day window
spans different dates. Derived values are a function of their series, so every
board states which source produced it and how many points backed it. Two
sources disagreeing is information; presenting either as *the* number without
naming it is not.

## 11. Status summary

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
  without which the equity view stays coverage-gated. §10 does not relieve
  this: DefiLlama is crypto-only, so the equity gap it names is exactly the
  gap that remains.
- **NEEDS APPROVAL** — any production cutover. The 2.0 page is published as a
  separate versioned artifact; the existing terminals are untouched.
