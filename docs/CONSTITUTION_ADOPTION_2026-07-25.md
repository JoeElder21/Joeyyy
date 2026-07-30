# Constitution Adoption Record — 2026-07-25

Dated decision record. Append-only after merge; supersessions get a new dated entry.

## Decision

On 2026-07-25 Joe delivered the **JOEYYY Global Agent Engineering Constitution** as the repository's new project charter and governance policy. Per its own section 18, it is installed as the single canonical cross-runtime repository policy in the repository-root `AGENTS.md`, replacing the previous "Agent 007 Repository Guidance" document. Repository-scoped operating guidance from the previous document (machine-readable source pointers, validation surface) is preserved in a clearly subordinate Repository Operating Annex inside `AGENTS.md`.

- Authority: Joe's explicit task-level instruction, 2026-07-25 (normative authority level 2).
- Canonical home: repository-root `AGENTS.md` (single copy; no other surface may carry an editable copy).
- Runtime adapters created per section 18: `CLAUDE.md` (Claude Code) and `.github/copilot-instructions.md` (GitHub Copilot), both thin pointers to `AGENTS.md`.

## Supersession 1: staffing rule

- **Superseded:** the 2026-07-24 staffing amendment "Staff each mission from the full registered corps, scaling the team to the mission" (previously in `AGENTS.md` and `.codex/agents/apex_chief_of_staff.toml` operating_method), and the older pre-amendment "smallest useful team" phrasing that survived in the same TOML's specialist_corps section, `docs/AGENT_COMMUNITY_PROTOCOL.md`, and `docs/SPECIALIST_CORPS_PROTOCOL.md`.
- **Superseding rule:** constitution section 6 — "Activate the smallest evidence-justified team whose independent contributions materially change the result," after discovering the full eligible roster within the classified, authorized brain and governance scope.
- **Basis:** section 6 is Joe's newer explicit instruction (2026-07-25 vs 2026-07-24); the constitution requires staffing amendments to update all policy, contracts, protocols, registries, and tests that encode the rule.
- **Not superseded:** the 2026-07-24 roles-as-modes decision. Dream-team roles remain charter modes of the ten registered specialists (`config/dream_team_roster.toml`, `docs/AGENT_REGISTRY.md` "Dream-team charter modes"), consistent with constitution section 7.
- **Cascade applied in this change:** `AGENTS.md` (rule text and supersession note), `.codex/agents/apex_chief_of_staff.toml` (operating_method step 6 and the specialist_corps team-selection line), `docs/AGENT_COMMUNITY_PROTOCOL.md`, `docs/SPECIALIST_CORPS_PROTOCOL.md`, and `tests/test_agent_contract.py` / `tests/test_repository_policy.py` phrase assertions. Dated historical records that quote the old rules remain unchanged as history.

## Supersession 2: LARE ownership

- **Superseded:** the prior contract instruction "Preserve the current recorded LARE ownership conflict until Joe resolves it; do not silently choose or merge the competing records" (`.codex/agents/apex_chief_of_staff.toml` brain_governance) and its drift-lock in `tests/test_agent_contract.py`.
- **Superseding rule:** constitution section 5 — apply the current valid LARE amendment: logistics, CLARB, PSI, KBLA, fees, deadlines, and professional administration belong to APEX; study content, habit, cadence, and personal learning behavior belong to JEOS; the interface runs through Joe and Agent 007.
- **Basis:** the constitution is Joe's newest explicit instruction and states the LARE amendment as current valid law; brain law is Joe-owned, so this record treats his delivered text as the resolution of the previously recorded conflict. If the private canon still records the conflict as live, Joe's confirmation is requested (see decisions below).
- **Cascade applied in this change:** contract brain_governance line, `tests/test_agent_contract.py` (test renamed to `test_lare_amendment_is_applied`). Historical documents that describe the conflict as live at their date (`docs/REPOSITORY_OVERVIEW.md`, `trial/TICKET-004-blocked-on-missing-input.md`) remain unchanged as dated history; TICKET-004's rubric predates this supersession.

## Supersession 3: always-gated actions

- **Superseded:** the six-item explicit-instruction list (irreversible bulk deletion, financial transactions, credential/access-control changes, signing or certifying, binding legal commitments, public publication in Joe's name) in the prior `AGENTS.md`, `.codex/agents/apex_chief_of_staff.toml` delegated_authority, and `docs/APEX_CHIEF_OF_STAFF.md`.
- **Superseding rule:** constitution section 9's live-approval list, which adds final permit or agency submission; scheduled-task creation or deletion; modification of Separation governance or canonical brain masters and snapshots; and overwrite of originals.
- **Cascade applied in this change:** contract delegated_authority line (now citing root `AGENTS.md` section 9), `docs/APEX_CHIEF_OF_STAFF.md`, and new phrase assertions in `tests/test_agent_contract.py`.

## Known gaps recorded at adoption

- **Value policy (section 17):** ~~no machine-readable value policy exists~~ — **closed 2026-07-26** by `config/value_policy.toml` and `runtime/value_meter.py`. The 35% minimum is now binding and enforced. What remains open is data, not machinery: most per-mode baselines are `unset`, and a mode with no measured or Joe-declared baseline reports `no_baseline` rather than passing. Joe supplies baselines as missions run.
- **Enforcement scope:** `tests/test_repository_policy.py` guards the canonical-copy rule, adapter thinness, and superseded-phrase reintroduction across tracked Markdown and TOML surfaces; it does not (and cannot) verify private-canon state.

## Enforcement

`tests/test_repository_policy.py` validates: the constitution's presence and section headings in `AGENTS.md`; exactly one copy of the constitution in the repository (gitlink-aware scan that proves it actually scanned the tree); both runtime adapters existing, pointing to `AGENTS.md`, and staying thin; and that the superseded staffing phrases do not reappear in any tracked Markdown or TOML surface outside this record and the `AGENTS.md` supersession notes. `tests/test_agent_contract.py` drift-locks the new staffing, LARE, and always-gated phrases in the Codex contract.

## Truth status at adoption

- Constitution text in `AGENTS.md`: exists, configured (adapters point to it), statically valid (tests executed).
- Contract cascades (staffing, LARE, gates): statically valid (phrase assertions and TOML parse); no controlled mission has exercised the new rules yet.
- Value: hypothesis — controlled compound improvement with lower review burden; unmeasured at adoption.

## Rollback

Revert the adoption commits on the task branch (`git revert <sha>`), which restores the previous "Agent 007 Repository Guidance" `AGENTS.md`, the prior staffing, LARE, and gate text in the contract and docs, the prior test assertions, and removes the adapters, this record, and the policy test together. No runtime behavior, roster, schema, or lifecycle stage changes in this adoption, so no agent can be stranded mid-promotion by the revert.

## Known open overlaps at adoption time (proposals, not law)

- PR #26 proposes a different `.github/copilot-instructions.md` (Awesome Copilot activation layer). PR #31 proposes a `CLAUDE.md`. Both were open and unmerged at adoption; whichever merges second must be reconciled to keep the adapters thin and pointed at `AGENTS.md` per section 18.
