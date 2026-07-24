# Microsoft AutoGen integration — controlled runtime adapter

## Status and scope

This is the first implementation record in the eight-repository incorporation program. The repository now contains `runtime/autogen_orchestrator.py`, a tested adapter for the Microsoft AutoGen 0.2 `ConversableAgent`, `GroupChat`, and `GroupChatManager` APIs. It converts the existing, versioned brain manifests into a bounded group-chat plan; it does **not** promote a shadow specialist or claim that a model, connector, Google Drive, or AutoGen runtime is available.

The optional runtime dependency is pinned in `requirements.txt` for Python 3.8–3.12, the supported range for the legacy AutoGen API used by this adapter. An operator installs it only in a verified runtime and supplies the authorized `llm_config`; no credential, model configuration, connector identifier, or private source data belongs in this repository.

## Runtime behavior

1. Agent 007 calls `plan_cadence(brain, cadence)`. The adapter reads the matching brain manifest and uses its `cadence_routes.order` as the specialist speaking order.
2. `validate_delegations()` requires exactly one new, schema-valid v2.1 delegation packet for every selected specialist. Packets must belong to the requested brain; mixed-brain chats fail before AutoGen objects are built.
3. `build_group_chat()` creates one `ConversableAgent` per selected specialist with no human input and no code execution. The supplied system-message factory must expose only packet-authorized evidence.
4. The `GroupChat` uses the cadence order as its deterministic speaker selector. Manifest-defined same-brain challenge pairs are carried into the plan for the runtime prompt/policy layer; no APEX/JEOS specialist can debate directly.
5. Agent 007 calls `initiate_chat()` against the `GroupChatManager`, then integrates the advisory handoffs. Existing PacketGuard, writer-lease, readback, rollback, and high-impact approval rules remain authoritative.

## Operational invocation

```python
from runtime.autogen_orchestrator import AutoGenMissionOrchestrator

orchestrator = AutoGenMissionOrchestrator()
plan = orchestrator.plan_cadence("APEX", "daily")
specialists, manager = orchestrator.build_group_chat(
    plan,
    delegations=validated_delegation_packets,
    llm_config=verified_runtime_llm_config,
    system_message_factory=packet_to_brain_locked_prompt,
)
result = orchestrator.initiate_chat(agent_007, manager, mission)
```

This call is intentionally unavailable until the caller has a verified AutoGen installation, model configuration, Agent 007 runtime object, and packet-authorized evidence. It does not schedule background work and it does not write to Drive.

## Evidence, validation, and rollback

- Unit tests assert the APEX daily route, the terminal Agent 007 integration turn, eligible same-brain challenge pair, invalid brain/cadence rejection, exact participant matching, and cross-brain packet rejection.
- The complete repository suite remains the static and synthetic validation baseline. A controlled real mission for each material specialist mode is still required for lifecycle promotion.
- Rollback: remove `runtime/autogen_orchestrator.py`, `tests/test_autogen_orchestrator.py`, this record, and the `pyautogen` requirement; restore this integration's commit parent. No source-memory or external mutation is made by the adapter.

## Google Drive record

No Google Drive connector or authenticated Drive destination was verified in this session, so no external documentation upload is claimed. This file is the sanitized source record intended for the authorized Agent 007/Drive writer to copy to the approved governance folder, with the resulting Drive link, owner, timestamp, and readback recorded only in the authorized private system—not in this public repository.
