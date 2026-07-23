# Specialist Delegation and Handoff

## Delegation packet

- `schema_version`: `2.1`
- `delegation_id`:
- `mission_id`:
- `resource_id`:
- `agent`:
- `owner_brain`: APEX / JEOS
- `memory_namespace`:
- `roundtable_namespace`:
- `mode`: one exact registered mode from the selected agent's brain manifest
- `mission`:
- `definition_of_done`:
- `definition_of_done_ids`: one unique stable ID per criterion, in matching order
- `required_artifact_types`: one or more artifact types registered to the selected agent
- `allowed_evidence`: structured source reference / owner brain / source type / Agent 007 scope verifier / sensitivity
- `allowed_read_namespaces`:
- `allowed_write_targets`: zero or one exact manifest target
- `prohibited_scope`:
- `allowed_actions`:
- `writer_agent`: `apex_chief_of_staff` or null
- `writer_lease_id`:
- `mutation_contract`: allowed operations / idempotency-key requirement / expected-version requirement
- `deadline`:
- `dependencies`:
- `risk_flags`:
- `approval_level`:
- `sensitivity`:
- `return_schema`: `schemas/handoff_packet.schema.json`

Validate with [delegation_packet.schema.json](../schemas/delegation_packet.schema.json) and `scripts/packet_guard.py`, including the live writer-lease and constraint ledgers. All new specialist missions use `2.1`; PacketGuard rejects `2.0` delegation and handoff packets. Version `2.0` is archival-only — validate archived packets by passing `--historical` (CLI) or `historical=True` (API), never for new work.

## Specialist return

- `schema_version`: `2.1`
- `delegation_id`: copied from the packet; null only in direct-read-only mode
- `mission_id`:
- `resource_id`:
- `agent`:
- `owner_brain`:
- `memory_namespace`:
- `mode`: copied from the validated delegation; `direct_read_only` only for contained direct invocation
- `invocation_mode`: delegated / direct_read_only
- `external_actions_performed`: false
- `status`: completed / partial / blocked / boundary_blocked
- `findings`:
- `artifacts`: registered artifact type / typed records
  - record: `record_id` / `record_type` / `source_refs` / `as_of` / `source_locator` / `revision` / `content_hash` / typed `fields` / `confidence`
- `evidence`: structured, delegation-bounded evidence references
- `tests`:
- `assumptions`:
- `blockers`:
- `challenges`:
- `proposed_writes`: zero or one deterministic proposal
  - `target`:
  - `operation`: append / upsert / patch / replace / disable
  - `record_type`:
  - `artifact_record_ids`:
  - `idempotency_key`:
  - `expected_version`:
  - `expected_state`:
  - `validation_readback`:
  - `rollback`:
  - `writer_agent`:
  - `writer_lease_id`:
- `validation`:
- `criterion_validation`: criterion ID / passed, failed, or blocked / evidence record IDs / note
- `confidence`:
- `sensitivity`:
- `recommended_next_handoff`:

Validate with [handoff_packet.schema.json](../schemas/handoff_packet.schema.json), the originating delegation, and the live writer-lease and constraint ledgers.

For `boundary_blocked`, use only `blockers: ["BOUNDARY_SCOPE_REJECTED"]`; keep `findings`, `artifacts`, `evidence`, `tests`, `assumptions`, `challenges`, `proposed_writes`, `validation`, and `criterion_validation` empty. For `completed`, provide every delegated artifact type, nonempty findings, tests, source-linked evidence, and exactly one criterion-validation entry per stable definition-of-done ID, with no unresolved blockers.
