# Release and QA validator

**Role id:** `release_qa_validator` · **stage:** release · **parallelism cap:** 1 · **writes the store:** no

Runs the release gates and the verification command; signs off or blocks.

## Reads

- `runs`
- `snapshots`
- `health`

## Produces

- `health`

## Tools

- terminal.gates
- terminal.schema
- terminal.cli verify

## Duties

- Schema, chain, size ceiling, freshness labels, immutability, invariants, critic verdict: all must pass.
- A skipped or mocked check is not a passing check.
- Report the exact gate that failed and the document it failed on.

## Forbidden

- publishing over a failed gate

Shared rules are in `README.md` beside this file.
