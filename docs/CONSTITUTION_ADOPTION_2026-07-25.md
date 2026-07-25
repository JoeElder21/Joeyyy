# Constitution Adoption Record — 2026-07-25

Dated decision record. Append-only; do not rewrite. Supersessions get a new dated entry.

## Decision

On 2026-07-25 Joe delivered the **JOEYYY Global Agent Engineering Constitution** as the repository's new project charter and governance policy. Per its own section 18, it is installed as the single canonical cross-runtime repository policy in the repository-root `AGENTS.md`, replacing the previous "Agent 007 Repository Guidance" document. Repository-scoped operating guidance from the previous document (machine-readable source pointers, validation surface) is preserved in a clearly subordinate Repository Operating Annex inside `AGENTS.md`.

- Authority: Joe's explicit task-level instruction, 2026-07-25 (normative authority level 2).
- Canonical home: repository-root `AGENTS.md` (single copy; no other surface may carry an editable copy).
- Runtime adapters created per section 18: `CLAUDE.md` (Claude Code) and `.github/copilot-instructions.md` (GitHub Copilot), both thin pointers to `AGENTS.md`.

## Supersession: staffing rule

- **Superseded:** the 2026-07-24 staffing amendment "Staff each mission from the full registered corps, scaling the team to the mission" (recorded in the previous `AGENTS.md` and encoded in `.codex/agents/apex_chief_of_staff.toml` and `tests/test_agent_contract.py`).
- **Superseding rule:** constitution section 6 — "Activate the smallest evidence-justified team whose independent contributions materially change the result," after discovering the full eligible roster within the classified, authorized brain and governance scope.
- **Basis:** section 6 is Joe's newer explicit instruction (2026-07-25 vs 2026-07-24); the constitution requires staffing amendments to update all policy, contracts, protocols, registries, and tests that encode the rule.
- **Not superseded:** the 2026-07-24 roles-as-modes decision. Dream-team roles remain charter modes of the ten registered specialists (`config/dream_team_roster.toml`, `docs/AGENT_REGISTRY.md` "Dream-team charter modes"), consistent with constitution section 7.
- **Cascade applied in this change:** `AGENTS.md` (rule text and supersession note), `.codex/agents/apex_chief_of_staff.toml` operating_method step 6, `tests/test_agent_contract.py` phrase assertion. `docs/AGENT_COMMUNITY_PROTOCOL.md` and `docs/SPECIALIST_CORPS_PROTOCOL.md` already carried smallest-team language (they were never updated for the 2026-07-24 amendment) and are now consistent with the constitution without edits.

## Drift resolved

Before this adoption, the staffing rule existed in two contradictory forms: `AGENTS.md` and `.codex/agents/apex_chief_of_staff.toml` operating_method said "full registered corps" (2026-07-24 amendment), while `docs/AGENT_COMMUNITY_PROTOCOL.md`, `docs/SPECIALIST_CORPS_PROTOCOL.md`, and the same TOML's specialist_corps section said smallest useful team (pre-amendment text). This adoption resolves the drift in one direction: smallest evidence-justified team, everywhere.

## Enforcement

`tests/test_repository_policy.py` validates: the constitution's presence and section headings in `AGENTS.md`; exactly one copy of the constitution in the repository; both runtime adapters existing, pointing to `AGENTS.md`, and staying thin (no constitution sections restated); and the staffing-rule supersession (old phrase absent from the Codex contract, new phrase present in policy and contract).

## Truth status at adoption

- Constitution text in `AGENTS.md`: exists, configured (adapters point to it), statically valid (tests executed).
- Staffing cascade: behaviorally verified only to the static-contract level (phrase assertions and TOML parse); no controlled mission has exercised the new staffing rule yet.
- Value: hypothesis — controlled compound improvement with lower review burden; unmeasured at adoption.

## Rollback

Revert the adoption commit(s) on the task branch (`git revert <sha>`), which restores the previous "Agent 007 Repository Guidance" `AGENTS.md`, the "full registered corps" contract text, the prior test assertion, and removes the adapters, this record, and the policy test together. No runtime behavior, roster, schema, or lifecycle stage changes in this adoption, so no agent can be stranded mid-promotion by the revert.

## Known open overlaps at adoption time (proposals, not law)

- PR #26 proposes a different `.github/copilot-instructions.md` (Awesome Copilot activation layer). PR #31 proposes a `CLAUDE.md`. Both were open and unmerged at adoption; whichever merges second must be reconciled to keep the adapters thin and pointed at `AGENTS.md` per section 18.
