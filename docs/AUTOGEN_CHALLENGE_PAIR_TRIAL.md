# AutoGen Challenge-Pair Trial — 2026-07-24

## Purpose

This is the first executable integration step requested for
`microsoft/autogen`.  It turns the existing same-brain challenge-pair
declarations into a deterministic preflight.  It does **not** invoke a model,
connect to a tool, read a brain record, or promote a specialist.

## Runtime entry point

Run:

```bash
python scripts/autogen_challenge_pair.py \
  --brain APEX \
  --agents apex_war_architect apex_intelligence_forge \
  --mission-id synthetic-autogen-preflight \
  --evidence-ref synthetic://apex/challenge-input
```

The command succeeds only when the ordered pair is registered in
`config/specialist_corps.toml`, both agents are in the requested owner brain,
the pair is a declared challenge pair, and at least one packet evidence
reference is provided.  Its JSON result is intentionally `preflight_only`,
with `tool_access: none` and `external_actions_performed: false`.

## Execution gate

An AutoGen `AssistantAgent` or group-chat execution adapter may be added only
after all of the following are true:

1. Agent 007 has issued one schema-valid v2.1 delegation packet per
   specialist through `PacketGuard`.
2. A model client is configured outside this public repository, with no
   credential or connector identifier stored here.
3. The proposed runtime exposes no direct tools to shadow specialists; it
   passes only packet-validated, brain-scoped evidence.
4. Each returned handoff validates against
   `schemas/handoff_packet.schema.json` and is integrated by Agent 007.
5. The named specialists have independently passed the controlled real-mission
   and runtime-isolation gates required for `active` status.

Installing AutoGen does not satisfy any of these gates.  The preflight is
therefore useful as a repeatable routing test, not evidence of an active
specialist or an operational connector.

## Evidence and rollback

- **Evidence:** `tests/test_autogen_challenge_pair.py` exercises an allowed
  APEX pair and rejects cross-brain and undeclared pairs.
- **Rollback:** remove `scripts/autogen_challenge_pair.py`, its test, this
  trial record, and the Taskipy command.  The preflight has no persistent
  state and creates no external effects.

## Google Drive record

No Google Drive connector, account, target folder, or authorization was
verified in this session.  Consequently no Drive write was attempted or
claimed.  When an authorized MCP Drive server is available, Agent 007 must
create a sanitized record of this trial (no raw APEX or JEOS evidence), read it
back, and attach the resulting mutation and rollback evidence to the relevant
owner-brain ledgers.
