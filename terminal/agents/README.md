# Terminal agent roles

`roles.toml` is the manifest; each role has a one-page brief beside it. These
are role definitions for the research workflow described in
`docs/TERMINAL_ARCHITECTURE.md`. They are not registered specialists: the
repository's specialist corps lives in `config/specialist_corps.toml` and its
generated projections in `.claude/agents/`, which this directory does not touch.

Rules every role shares:

- JEOS-owned; read-only toward brokers, wallets and exchanges. No order, no
  signature, no credential, no spending authority.
- Balances come only from screenshots Joe sends (on-chain reads are factual
  data, not estimates). A number that cannot be sourced is written as
  "not available", never estimated.
- Roles return documents to the orchestrator, the designated writer. No role
  writes to the store or the live artifact on its own.
- Every factor score cites evidence ids; an unscored factor stays unscored.
- The critic may challenge for at most two rounds and may not edit.
- The `parallelism` value is a cap on concurrent instances per run.
