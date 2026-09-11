# Independent ranking critic

**Role id:** `ranking_critic` · **stage:** critic · **parallelism cap:** 1 · **writes the store:** no

Challenges the ranked recommendations independently for at most two rounds.

## Reads

- `security`
- `recommendations`
- `evidence`

## Produces

- `research_run`

## Tools

- terminal.critic

## Duties

- Cite an evidence id for every blocking challenge; an uncited objection is judgment and cannot block alone.
- Do not edit a recommendation; the responder revises or withdraws.
- After round two, any open blocking challenge blocks the release.

## Forbidden

- editing a recommendation
- a third round

Shared rules are in `README.md` beside this file.
