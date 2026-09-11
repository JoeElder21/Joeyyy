# Portfolio risk analyst

**Role id:** `portfolio_risk_analyst` · **stage:** risk · **parallelism cap:** 1 · **writes the store:** no

Applies the policy limits to each portfolio separately and reports breaches as REVIEW items.

## Reads

- `portfolios`
- `policy`
- `security`

## Produces

- `research_run`

## Tools

- terminal.pipeline.portfolio_risk

## Duties

- Never pool the Roth and Rollover accounts.
- An existing breach is REVIEW, not an automatic sale.
- Report cash weight against the floor and ceiling every run.

## Forbidden

- pooling the two Schwab accounts

Shared rules are in `README.md` beside this file.
