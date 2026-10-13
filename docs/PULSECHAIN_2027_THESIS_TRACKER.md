# PulseChain 2027 Thesis Tracker — METHODS

Created: 2026-09-15 by Drippy | Mode: JEOS

## Standing rule (Joe)

PulseChain is credible as a continuing niche ecosystem. Current momentum is not
strong enough to elevate it to a high-conviction, core long-term investment
thesis.

**Keep "the network will survive" separate from "these holdings deserve more
capital."** The two questions have different evidence and different answers, and
collapsing them is the failure this tracker exists to prevent.

## Columns

| Column | Reads |
|---|---|
| Review date | The date the row was measured, not the date it was written |
| Stablecoin supply | Total stablecoin supply on the chain |
| 30-day net bridge flows | Net, not gross — inflows minus outflows |
| 30-day DEX volume | All DEXes on the chain |
| Non-PulseX volume | The share not transacting on PulseX |
| Returning funded users | On-chain, funded, returning — not new-address counts |
| Independent releases/apps | Shipped by teams other than the core group |
| Net exit quote | What a real exit actually clears at, after slippage |
| Thesis status | The verdict for that month |

## Monthly flags

- **Adoption gains** — at least **2 of 5** improve against the prior month
  without an exit-quote blowout: stablecoin supply, net bridge inflows, DEX
  volume, returning funded users, independent releases.
- **Liquidity deterioration** — net outflows **and** DEX volume down **and** the
  exit quote worsens, or the non-PulseX share collapses.
- **Default status: NICHE / WATCH**, unless the data clearly upgrades or
  downgrades it. The default is not a placeholder to be filled in; it is the
  answer whenever the evidence does not compel another.
- **Never invent numbers. UNKNOWN when sources are missing.**

## Cadence

First Monday, 09:00 `America/New_York`.

**Not scheduled.** Creating a recurring task is an always-gated action under
section 9, so this cadence is recorded as the intended schedule and nothing has
been armed to run it. It runs when Joe approves it.

## Sources

DefiLlama, bridge explorers, the PulseX / other-DEX split, on-chain returning
funded users, ecosystem releases.

The working sheet is a private Google Sheets document held outside this
repository. Its URL is deliberately **not recorded here**: this repository is
public, and `scripts/privacy_guard.py` blocks raw Drive and Docs links as a
matter of standing policy. Joe holds the link.

## Why the exit-quote column carries the weight

This is not a generic liquidity metric. It is the column that already produced a
finding on this terminal, and the tracker inherits that result rather than
starting cold.

When the PulseChain wallet was read on 2026-09-14, nine material tokens were
named and valued, and **no ranking was published for any of them.** DefiLlama
resolved identifiers for 83.17% of the wallet by value, and every resolved
24-hour change disagreed with the wallet's own figure — PLS most starkly, at
**+1.24% on the wallet against −12.03% on DefiLlama**, opposite in sign. Two
candidate series existed for HEX and neither matched. Forks were not priced from
the assets they fork.

That is what the *Net exit quote* column is for. A position can be valued
confidently and still not be exitable at that value, and a chain can be healthy
on every adoption measure while its exit remains poor. The standing rule above
already separates survival from allocation; the exit quote is the column where
that separation becomes a number.

Recorded in full under **Ranking withheld — sources disagree on price** on the
Savage Investments terminal, and as an illiquidity breach in its limit register.

## Scope

**Analysis only.** Joe decides capital allocation and assumes the risk. Nothing
in this tracker is an instruction to trade, and no row of it authorises one.
