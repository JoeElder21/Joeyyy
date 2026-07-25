# Lessons

Learning artifacts maintained by the [.NET Self-Learning Architect](../agents/dotnet-self-learning-architect.agent.md) custom agent (and any subagents it spawns). When a mistake or correction occurs during a task, the agent records it here as one markdown file per lesson.

Every lesson must carry the governance metadata (`PatternId`, `PatternVersion`, `Status`, `Supersedes`) and follow the dedupe, conflict-resolution, and safety-gate rules defined in the agent file.

## Template

```markdown
# Lesson: <short-title>

## Metadata

- PatternId:
- PatternVersion:
- Status: active | deprecated | blocked
- Supersedes:
- CreatedAt:
- LastValidatedAt:
- ValidationEvidence:

## Task Context

- Triggering task:
- Date/time:
- Impacted area:

## Mistake

- What went wrong:
- Expected behavior:
- Actual behavior:

## Root Cause Analysis

- Primary cause:
- Contributing factors:
- Detection gap:

## Resolution

- Fix implemented:
- Why this fix works:
- Verification performed:

## Preventive Actions

- Guardrails added:
- Tests/checks added:
- Process updates:

## Reuse Guidance

- How to apply this lesson in future tasks:
```
