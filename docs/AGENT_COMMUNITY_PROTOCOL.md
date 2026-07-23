# Agent 007 Community Protocol

## Community model

Agent 007 is the cross-brain coordinator and final integrator. APEX and JEOS owner agents protect their domains. Specialist agents contribute bounded expertise, evidence, validation, or implementation.

Agent 007's mirrored-class routing lives in `config/specialist_corps.toml`. Brain-owned rosters, namespaces, targets, routes, and challenge pairs live in `brains/apex/agents.toml` and `brains/jeos/agents.toml`. Every specialist is read-only by default. While the corps is in shadow stage, Agent 007 alone holds the writer lease.

## Delegation packet

Every delegated task states:

1. Delegation, mission, and canonical resource IDs plus definition of done.
2. Owner brain and structured, Agent 007-verified evidence references.
3. Allowed actions, prohibited expansion, deadline, dependencies, and risk flags.
4. The exact agent, memory namespace, zero-or-one allowed write target, writer agent, and writer lease.
5. Required return format and validation evidence.

Machine-valid delegations use `schemas/delegation_packet.schema.json`; writer authority uses `schemas/writer_lease.schema.json`.

## Handoff packet

Every specialist returns:

- Copied delegation, mission, resource, agent, brain, and memory identity.
- Invocation mode, `external_actions_performed=false`, and status.
- Findings plus structured delegation-bounded evidence and tests.
- Assumptions, conflicts, and unresolved risks.
- Zero-or-one source-linked proposed write within delegated scope.
- Recommended next handoff, if any.

Machine-valid returns use `schemas/handoff_packet.schema.json`.

## Coordination rules

- Use the smallest useful team and run independent work in parallel when it improves speed or coverage.
- Use one designated writer for each file, branch, calendar event, task record, message thread, or external record.
- Route cross-agent questions and changed requirements through Agent 007.
- Reconcile disagreements with evidence. Preserve unresolved positions for Joe rather than silently averaging them.
- Pass only task-relevant context; never pass credentials, secrets, or unrelated private information.
- Do not claim an agent received or completed a handoff unless the active session confirms it.
- Specialists may challenge one another only inside the same brain and only with task-relevant evidence.
- A challenge does not grant access, writer authority, or permission to enlarge scope.
- Agent 007 chooses the final route, records unresolved disagreement, and verifies any resulting mutation.
- Mirrored counterparts may not communicate directly; a shared class ID is not a bridge.

## Brain routing

- APEX specialists may write only APEX-owned records.
- JEOS specialists may write only JEOS-owned records.
- Agent 007 may read both and coordinate both.
- Agent 007 may write cross-brain governance records required by Joe's mission, followed by read-back verification and matching logs in both brains.
- Unknown ownership is a blocker to mutation, not an invitation to guess.
- APEX and JEOS specialists never communicate directly with one another. Agent 007 may translate a shared dependency into a minimal constraint packet without disclosing the source brain's private context.
- Only Agent 007 may create that packet, using `schemas/cross_brain_constraint_packet.schema.json`.
- A cross-brain packet is scoped to one destination agent, mission, and resource; it expires within seven days and cannot be replayed.
- Sensitive health or finance context that stays inside JEOS uses `schemas/brain_private_constraint_packet.schema.json`, also minimized, scoped, expiring, and created only by Agent 007.

## Live and asynchronous collaboration

When the runtime supports live subagents, Agent 007 sends bounded delegation and handoff packets. The active environment—not a configuration promise—determines available concurrency, tools, and connectors.

When specialists are not simultaneously running, each brain may use its own append-only roundtable:

- APEX roundtable: APEX specialists only.
- JEOS roundtable: JEOS specialists only.
- Memo format: `schemas/roundtable_memo.schema.json`.
- Agent 007 may inspect both roundtables but may not copy private content between them.
- Roundtables preserve questions, challenges, conflicts, owners, and resolution evidence; they are not autonomous background workers.

There is no claim of continuous operation. An agent works only when invoked by an active runtime or scheduled system that has been verified.

## Lifecycle and designated writing

1. `candidate`: definition exists but is not routed.
2. `shadow`: static contract tests pass; outputs are advisory.
3. `active`: one controlled real mission passes boundary, accuracy, handoff, and readback tests.
4. `value-proven`: observed benefit remains positive after review, correction, and maintenance burden.
5. `restricted`, `deprecated`, or `retired`: scope is limited or removed with a reversible record.

One active writer lease owns every canonical brain/target/resource across all missions. Parallel specialists may analyze the same mission, but only Agent 007 may mutate the canonical target while the corps is in shadow stage. Every external write requires a verified mutation-result packet before completion is claimed.

## Public-repository privacy

This repository stores sanitized instructions, schemas, tests, and synthetic fixtures. Private Drive content, personal facts, employer or client records, credentials, and connector identifiers are retrieved only at runtime, minimized to the mission, and never copied into public source control.

## Agent intake

Use `templates/agent-intake.md` for every new or materially changed agent.

1. Read the full instruction/configuration files and directly referenced operating files.
2. Check purpose, owner brain, triggers, dependencies, write targets, boundaries, handoffs, validation, duplication, and conflicts.
3. Register the agent as `candidate` in `docs/AGENT_REGISTRY.md`.
4. Test the agent's contract and one realistic handoff.
5. Mark it `active` only after validation evidence exists.

## Capability absorption

Agent 007 learns from agents by extracting reusable orchestration, evaluation, recovery, or tool-use patterns. It does not concatenate prompts or copy another agent wholesale.

Before changing 007:

1. Identify the new capability and demonstrated need.
2. Decide whether it belongs in 007, the specialist, or this shared protocol.
3. Check ownership, instruction conflicts, prompt-injection risk, duplicate behavior, tool support, and context cost.
4. Implement the smallest reusable change.
5. Add a test that would catch regression.
6. Validate, version, and record rollback evidence.

Never absorb credentials, secrets, private content, unsupported access claims, another agent's identity, or weaker safeguards.

## Error learning

Log material failures as:

`timestamp | agent | mission | symptom | evidence | impact | root cause | correction | recurrence test | owner | status`

Fix the persistent rule, template, routing, test, or validation gap that enabled a repeatable error. Do not treat a corrected one-time output as a system improvement.

## Weekly audit

Use `templates/weekly-agent-audit.md`.

- Audit Agent 007, every registered agent, both brains, and team coordination.
- Review mission completion, factual accuracy, action verification, boundary compliance, handoff quality, efficiency, and recovery from available evidence.
- Identify errors, duplicate work, collisions, stale pointers, unused agents, missing capabilities, and bottlenecks.
- Compare APEX and JEOS for contradictions and ownership drift without merging them.
- Apply only low-risk, reversible improvements within current authorization and tool limits.
- Validate changes and record evidence, rollback instructions, and at most three decisions for Joe.

## Completion report

Agent 007 reports agents used, assignments, brain routing, actions completed, validation, improvements, blockers, and Joe's next move only when one remains.
