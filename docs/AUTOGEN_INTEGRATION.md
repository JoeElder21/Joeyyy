# Microsoft AutoGen integration — controlled runtime adapter

## Status and scope

This is the first implementation record in the eight-repository incorporation program. The repository now contains `runtime/autogen_orchestrator.py`, a tested adapter for the Microsoft AutoGen 0.2 `ConversableAgent`, `GroupChat`, and `GroupChatManager` APIs. It converts the existing, versioned brain manifests into a bounded group-chat plan; it does **not** promote a shadow specialist or claim that a model, connector, Google Drive, or AutoGen runtime is available.

The official legacy `autogen-agentchat` 0.2 distribution supports Python 3.8 through versions below 3.13. This repository requires Python 3.11 or newer because the adapter and PacketGuard use the standard-library `tomllib` module, so the supported combination is Python 3.11–3.12. `requirements.txt` pins Microsoft's official distribution to the legacy 0.2 API. An operator installs it only in a verified runtime and supplies the authorized `llm_config`; no credential, model configuration, connector identifier, or private source data belongs in this repository.

## Runtime behavior

1. Agent 007 calls `plan_cadence(brain, cadence)`. The adapter reads the matching brain manifest, uses `cadence_routes.order` as the specialist-only speaking order, and requires the route's `integrator` to match the governed Agent 007 identity.
2. `validate_delegations()` materializes the supplied iterable once and requires exactly one new, schema-valid v2.1 delegation packet for every selected specialist. Duplicate, missing, extra, or mixed-brain packets fail before AutoGen objects are built.
3. `build_group_chat()` creates one `ConversableAgent` per selected specialist with no human input and no code execution. The supplied system-message factory must expose only packet-authorized evidence. Every eligible manifest challenge group and its purpose is appended to the affected specialists' mandatory prompt policy.
4. The `GroupChat` ignores the external Agent 007 mission and manager notes when counting specialist turns. It selects each specialist object once in manifest order, budgets one entry round plus one round per specialist, and terminates without model-based `"auto"` fallback. Agent 007 remains outside the brain-private `GroupChat`.
5. `initiate_chat()` verifies the completed specialist order, then explicitly invokes the manifest-declared Agent 007 for a terminal integration turn and returns both the raw group result and the integration in `MissionResult`.
6. Specialist messages remain untrusted advisory output. The verified host and Agent 007 must parse and PacketGuard-validate outbound handoff packets before any mutation; writer leases, readback, rollback, and high-impact approval rules are host/integrator obligations and are not inferred from transcript completion.

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
result = orchestrator.initiate_chat(agent_007, manager, mission, plan=plan)
final_output = result.integration
```

This call is intentionally unavailable until the caller has a verified AutoGen installation, model configuration, manifest-matching Agent 007 runtime object, and packet-authorized evidence. The adapter supplies no scheduler, connector, or mutation function and does not validate free-form specialist text as a handoff packet. Any capability registered separately on the caller-supplied Agent 007 object remains the verified host's responsibility.

## Evidence, validation, and rollback

- Unit tests exercise generator-backed delegation input, duplicate rejection, manifest-integrator drift, forged-plan rejection, deterministic specialist selection after the external mission, every eligible challenge policy, full round budgeting, incomplete transcript rejection, and the explicit terminal Agent 007 turn. CI also runs the lifecycle through the installed official AutoGen 0.2 classes with deterministic synthetic replies and no model or connector.
- The complete repository suite remains the static and synthetic validation baseline. A controlled real mission for each material specialist mode is still required for lifecycle promotion.
- Rollback: revert the follow-up fix commit, or remove `runtime/autogen_orchestrator.py`, `tests/test_autogen_orchestrator.py`, this record, and the `autogen-agentchat` requirement. The adapter itself provisions no source-memory or external-mutation capability; separately registered Agent 007 callbacks remain outside this guarantee.

## Google Drive record

No Google Drive connector or authenticated Drive destination was verified in this session, so no external documentation upload is claimed. This file is the sanitized source record intended for the authorized Agent 007/Drive writer to copy to the approved governance folder, with the resulting Drive link, owner, timestamp, and readback recorded only in the authorized private system—not in this public repository.
