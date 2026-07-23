# Agent 007 Community Protocol

## Community model

Agent 007 is the cross-brain coordinator and final integrator. APEX and JEOS owner agents protect their domains. Specialist agents contribute bounded expertise, evidence, validation, or implementation.

## Delegation packet

Every delegated task states:

1. Mission and definition of done.
2. Owner brain and allowed evidence.
3. Allowed actions, prohibited expansion, deadline, dependencies, and risk flags.
4. Whether the specialist is advisory, verifier, or designated writer.
5. Required return format and validation evidence.

## Handoff packet

Every specialist returns:

- Status: completed, partial, or blocked.
- Findings and actions completed.
- Evidence, sources, tests, and tool results.
- Assumptions, conflicts, and unresolved risks.
- Recommended next handoff, if any.

## Coordination rules

- Use the smallest useful team and run independent work in parallel when it improves speed or coverage.
- Use one designated writer for each file, branch, calendar event, task record, message thread, or external record.
- Route cross-agent questions and changed requirements through Agent 007.
- Reconcile disagreements with evidence. Preserve unresolved positions for Joe rather than silently averaging them.
- Pass only task-relevant context; never pass credentials, secrets, or unrelated private information.
- Do not claim an agent received or completed a handoff unless the active session confirms it.

## Brain routing

- APEX specialists may write only APEX-owned records.
- JEOS specialists may write only JEOS-owned records.
- Agent 007 may read both and coordinate both.
- Agent 007 may write cross-brain governance records required by Joe's mission, followed by read-back verification and matching logs in both brains.
- Unknown ownership is a blocker to mutation, not an invitation to guess.

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
