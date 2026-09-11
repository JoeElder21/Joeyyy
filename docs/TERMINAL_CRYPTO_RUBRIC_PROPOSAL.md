# Proposed crypto scorecard (PROPOSED, awaiting approval)

The equity rubric does not transfer to tokens: there are no filings, and the
risks that end a position are supply and liquidity events, not earnings. This
100-point rubric is implemented in `terminal/scorecard.py` as
`CRYPTO_SCORECARD_100_PROPOSED_V0`; every result it produces carries
`rubric_status: PROPOSED`, and the page says so on the crypto view. It is not
used for a stance until approved.

| Factor | Weight | Scored from | Fatal flags that exclude before scoring |
| --- | ---: | --- | --- |
| Liquidity and realizability | 25 | router quote for the full position, constant-product impact, pool depth on the pinned pool, independent venue count | honeypot, no reliable market data |
| Supply integrity | 15 | mint authority, freeze or blacklist rights, proxy upgradability, verified source, insider share of supply | open mint authority, owner can freeze or blacklist, unverified contract, insider supply over half |
| Holder structure | 15 | holder count, top-10 concentration, holder growth, exchange-held share | — |
| Trend and entry | 15 | 7-day and 30-day windows, distance from 24-hour range, invalidation level | — |
| Venue quality | 10 | trusted venue share of volume, DEX-to-reported volume ratio, listing depth | — |
| Catalyst | 10 | dated listing, unlock, protocol event with an evidence id | — |
| Evidence quality | 10 | derived: share of scored factors with at least one evidence id | — |

Core factors: liquidity and realizability, supply integrity. A token with either
unscored is `INSUFFICIENT` and is listed, not ranked.

Open questions for Joe:

1. Should memecoins and large-cap tokens be ranked in separate classes (the
   legacy page ranked them separately)?
2. Is a 25-point liquidity weight enough, given that realizable value on thin
   PulseChain pools has differed from spot by several percent?
3. Should the hurdle for tokens be the same 15% probability-weighted upside as
   for equities, or higher to reflect the drawdown profile?
