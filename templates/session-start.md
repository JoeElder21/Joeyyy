# Agent 007 session-start template

Paste at the top of a task, or reproduce inline. Keep the **shape** stable across
sessions — edit the items, not the headings — so the audit trail stays
comparable session to session. That comparability is the point.

Activation is bidirectional: `Activate Agent 007` and `Awesome Copilot` are the
same activation, and the opening line is always
`Agent 007 activated. Awesome Copilot layer active.`

---

## Ops brief

Five lines, in this order, before any edit.

```
1. Objective:            <the outcome, one sentence>
2. Constraints:          <what must not change; scope limits>
3. Authority boundaries: <delegated here | needs Joe>
4. Validation commands:  <the exact commands that will prove this>
5. Rollback point:       <commit / branch / file state to return to>
```

Worked example:

```
1. Objective:            Register Terraform and Azure as approved MCP mounts.
2. Constraints:          No JEOS access; no mount activated; tool surface pinned.
3. Authority boundaries: Registration delegated. Activation needs Joe's grant.
4. Validation commands:  verify_mcp_mounts.py; privacy_guard.py; unittest discover
5. Rollback point:       <pre-change commit, e.g. `git rev-parse HEAD` before editing>
                         plus the rollback section in the build-out doc
```

---

## Progress checklist

Reuse verbatim. Mark `[x]` when done, `[-]` when deliberately skipped with a
reason, `[ ]` when outstanding. Do not delete lines — a skipped line with a
reason is audit evidence; a missing line is a gap.

```
- [ ] Ops brief posted (5 lines, before first edit)
- [ ] Awesome Copilot layer read (.github/AWESOME-COPILOT.md)
- [ ] Discovery skill RUN (not listed) on any of its triggers: the mission
      changes a capability upstream may cover, touches `.github/instructions|agents|skills`,
      asks what is available or has drifted, or reaches a weekly audit
- [ ] Drift check reported as UNRUN when no fetch-capable tool is verified
- [ ] Ownership classified (APEX | JEOS | shared | governance | unknown)
- [ ] Mission staffed from the full registered corps, scaled to the mission,
      one designated writer per shared resource (AGENTS.md; `[-]` with the
      reason if Agent 007 ran it alone)
- [ ] Existing contract/registry/tests read before changing them
- [ ] First meaningful edit made
- [ ] VALIDATION RUN #1 — immediately after that edit, not at the end
- [ ] Policy changes separated from behavioral changes (distinct commits)
- [ ] Docs, templates, registry, and tests updated together
- [ ] Recurrence test added or updated for any repeatable failure
- [ ] Full gate green (privacy, corps, runtime stack, unittest)
- [ ] Readback done for every mutation
- [ ] Rollback point recorded in the commit or build-out doc
- [ ] Unrun checks reported as unrun, never as clean
```

---

## Validation block

Run after the **first meaningful edit**, then again before committing.

A bare `privacy_guard.py` enumerates via `git ls-files`, so a file created by the
edit you are about to validate is **invisible to it** — it reports success without
ever opening the new file. Pass the changed and untracked paths explicitly, or
stage them first; running only the bare form before committing is how a new
credential-bearing file reaches a commit with a green gate behind it.

```bash
# Scans tracked files AND anything new this session has written.
python scripts/privacy_guard.py $(git diff --name-only; git ls-files --others --exclude-standard)
python scripts/privacy_guard.py            # tracked tree, after the above
python scripts/validate_specialist_corps.py
python scripts/verify_runtime_stack.py
python -m unittest discover -s tests -v
python scripts/verify_mcp_mounts.py   # when config/mcp_mounts.toml changed
```

---

## CI triage macro

Two fixed steps before any local hypothesis:

```
1. List workflow runs        -> identify the failing run and job
2. Fetch failed job logs     -> read the actual error
3. Only now form a hypothesis and reproduce locally
```

Never theorize from a red badge alone.

---

## Close-out

End substantive work with:

- **Actions Completed** — what changed, with evidence.
- **Unresolved Blockers** — including anything deliberately skipped and why.
- **Joe's Next Move** — at most three ordered actions, only if Joe still has something to do.

State plainly what was verified and what was not. An unrun check is reported as
unrun.
