# First APEX slice — Delivery Commander technical QA

2026-09-12. Makes **one** end-to-end APEX path executable without promoting
anyone out of shadow.

## What runs

Agent 007 (`apex_chief_of_staff`) prepares catalog entry `sheet_qa_review`
(`apex_delivery_commander` / `technical_qa`), the packet-only worker returns a
typed `qa_risk_packet`, `MissionRunner.complete()` is VERIFY, and the printed
payload is REPORT.

```bash
python scripts/run_first_apex_slice.py
```

Identities on this path are v2.1 roster only: Agent 007 and
`apex_delivery_commander`. Absorbed capability names from older contracts
(GRADEMASTER, COUNTWISE, SIGNALKEEPER) are lineage, not callable agents.

## What this proves

- PREPARE produces a PacketGuard-valid 2.1 delegation.
- EXECUTE analyzes only `allowed_evidence` and calls no connector.
- VERIFY checks typed return, connector isolation, and definition-of-done ids.
- REPORT states lifecycle `shadow`, `qualifies_mode=false` (synthetic
  evidence), and `shadow_to_active_flip=false`.

## What this does not prove

- A controlled *real* mission. Synthetic fixtures cannot cover a mode.
- Behavioral quality for the other 38 modes. Those still raise
  `NotImplementedError` from `_invoke_specialist`.
- Value. `technical_qa` has no Joe-declared baseline in
  `config/value_policy.toml`.

## Rollback

Revert this change set. Delete `runtime/specialist_dispatch.py`,
`runtime/first_apex_slice.py`, `scripts/run_first_apex_slice.py`,
`tests/test_first_apex_slice.py`, and this file; restore the previous
`_invoke_specialist` refusal and the README / evals harness wording. No
lifecycle stage, roster identity, or schema is modified by the slice.
