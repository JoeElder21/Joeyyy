# Specialist Delegation and Handoff

## Delegation packet

- `schema_version`: `2.0`
- `delegation_id`:
- `mission_id`:
- `resource_id`:
- `agent`:
- `owner_brain`: APEX / JEOS
- `memory_namespace`:
- `roundtable_namespace`:
- `mission`:
- `definition_of_done`:
- `allowed_evidence`: structured source reference / owner brain / source type / Agent 007 scope verifier / sensitivity
- `allowed_read_namespaces`:
- `allowed_write_targets`: zero or one exact manifest target
- `prohibited_scope`:
- `allowed_actions`:
- `writer_agent`: `apex_chief_of_staff` or null
- `writer_lease_id`:
- `deadline`:
- `dependencies`:
- `risk_flags`:
- `approval_level`:
- `sensitivity`:
- `return_schema`: `schemas/handoff_packet.schema.json`

Validate with [delegation_packet.schema.json](../schemas/delegation_packet.schema.json) and `scripts/packet_guard.py`, including the live writer-lease and constraint ledgers.

## Specialist return

- `schema_version`: `2.0`
- `delegation_id`: copied from the packet; null only in direct-read-only mode
- `mission_id`:
- `resource_id`:
- `agent`:
- `owner_brain`:
- `memory_namespace`:
- `invocation_mode`: delegated / direct_read_only
- `external_actions_performed`: false
- `status`: completed / partial / blocked / boundary_blocked
- `findings`:
- `evidence`: structured, delegation-bounded evidence references
- `tests`:
- `assumptions`:
- `blockers`:
- `challenges`:
- `proposed_writes`: zero or one target / expected state / validation readback / rollback / Agent 007 writer / writer lease ID
- `validation`:
- `confidence`:
- `sensitivity`:
- `recommended_next_handoff`:

Validate with [handoff_packet.schema.json](../schemas/handoff_packet.schema.json), the originating delegation, and the live writer-lease and constraint ledgers.

For `boundary_blocked`, use only `blockers: ["BOUNDARY_SCOPE_REJECTED"]`; keep `findings`, `evidence`, `tests`, `assumptions`, `challenges`, `proposed_writes`, and `validation` empty. For `completed`, provide nonempty findings, tests, source-linked evidence, and one validation entry per definition-of-done criterion, with no unresolved blockers.
