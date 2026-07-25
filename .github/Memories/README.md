# Memories

Durable project context maintained by the [.NET Self-Learning Architect](../agents/dotnet-self-learning-architect.agent.md) custom agent (and any subagents it spawns). When durable context is discovered — architecture decisions, constraints, recurring pitfalls — the agent records it here as one markdown file per memory.

Every memory must carry the governance metadata (`PatternId`, `PatternVersion`, `Status`, `Supersedes`) and follow the dedupe, conflict-resolution, and safety-gate rules defined in the agent file.

## Template

```markdown
# Memory: <short-title>

## Metadata

- PatternId:
- PatternVersion:
- Status: active | deprecated | blocked
- Supersedes:
- CreatedAt:
- LastValidatedAt:
- ValidationEvidence:

## Source Context

- Triggering task:
- Scope/system:
- Date/time:

## Memory

- Key fact or decision:
- Why it matters:

## Applicability

- When to reuse:
- Preconditions/limitations:

## Actionable Guidance

- Recommended future action:
- Related files/services/components:
```
