# JEOS Memory Boundary

The logical prefix for JEOS specialist memory is `JEOS::`.

- Every specialist has one unique namespace in `../agents.toml`.
- A specialist may read only mission-authorized JEOS evidence.
- Private runtime memory stays in the authorized JEOS command center and is never copied into this public repository.
- Proposed writes identify a JEOS target, source evidence, expected state, validation, rollback, and writer lease.
- Agent 007 alone performs and reads back canonical mutations while the specialists remain in shadow stage.
- No namespace, roundtable, artifact, or raw source crosses into APEX.

This directory records policy only; it must never become a store for live journals, relationships, health, finance, addresses, schedules, messages, or connector data.
