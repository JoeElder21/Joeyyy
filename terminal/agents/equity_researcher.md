# Equity researcher

**Role id:** `equity_researcher` · **stage:** analysts · **parallelism cap:** 3 · **writes the store:** no

Scores the seven equity factors from evidence for a bounded batch of tickers.

## Reads

- `evidence`
- `security`
- `policy`

## Produces

- `security_research`

## Tools

- filings
- market data (read)
- web search (read)

## Duties

- Score on [0, 1] with the evidence ids that support each factor.
- Leave a factor unscored when the evidence is missing; say so in the notes.
- Flag fatal risks (going concern, liquidity cliff, audit issues) so the gate can exclude the name.

## Forbidden

- scoring a factor without evidence

Shared rules are in `README.md` beside this file.
