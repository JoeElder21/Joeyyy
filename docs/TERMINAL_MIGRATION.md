# Claude Stocks Terminal — migration plan (legacy page to the store)

## What the migration does (non-destructive)

`python -m terminal.cli migrate --html <legacy page> --store <dir>` reads one
legacy page and writes 110 documents:

| Documents | From | Treatment |
| --- | --- | --- |
| `boards/*` (9) | Boards 01–06, 13, 16, 17 | rows carried with `legacy_zone`, `scorecard: null`, status `LEGACY_UNSCORED`; board status computed from the legacy stamp |
| `portfolios/*` (8) | account cards, optimizer books | totals and cash from the screenshot-marked cards; the two Schwab IRAs as distinct documents; the legacy pooled book carried and labelled |
| `recommendations/rec-legacy-*` (23) | Board 17 calls table | immutable, lens `legacy`, stance `WATCH`, no invented reference price |
| `outcomes/legacy-*` (50) | Board 07 calls ledger | status `LEGACY`, prose grade carried |
| `legacy/*` (14) | action, expiry, optimizer, accounts, X-ray, ledger, journal, signal, calendar, health, feed, ticker, capsule, gates | frozen text and tables |
| `learning/current` | capsule zone scorecards | one-day tier returns carried as windows; verdict computed |
| `runs/legacy-chain`, `runs/<migration run>` | run log | chain verified and reported; migration manifest |
| `policy/current` | defaults plus capsule models | legacy models recorded under `legacy_models`, never promoted |
| `health/current`, `snapshots/current` | computed | store mode `embedded-snapshot`; snapshot pointer |

Nothing is written to the live page or to any Routine. The legacy page remains
the system of record until cutover.

## Verified on 2026-09-11

- Migration of the V53 readback: 110 documents, `verify` clean (0 schema errors,
  every recommendation hash intact), rendered page under 1 MB.
- Legacy run chain: 89 records read; 38 links fail the base-equals-previous-
  result check; one chat key published three times. Reported on the health view
  and in `TERMINAL_AUDIT.md`.
- The Revamped Edition page was published as a **new, private artifact** with
  the `db` capability declared (`read: interact, write: admin`) and its store
  seeded from these documents. The live terminal artifact is untouched.

## Cutover (requires Joe's approval, step by step)

1. **Approve the policy document.** Confirm or change: 15% upside hurdle
   (prompt) versus 10% return goal (mandate record); the 12–36-month secondary
   lens; the equity rubric weights; the crypto rubric (proposed).
2. **Approve the schedule.** Either keep the fixed-UTC crons and the one-shot
   DST correctors, or move the daily run to an ET-anchored expression. Any
   change to a scheduled task is an always-gated action.
3. **Re-mark the accounts.** Send screenshots for both Schwab IRAs so the
   position split exists; the migration cannot invent it.
4. **Point the Routines at the store.** Replace the three Routine prompts with
   the runbook sequence (read policy and snapshot, idempotency key, lease,
   stages, gates, batch writes, snapshot swap, republish). Show the new prompts
   first; change nothing until approved.
5. **Freeze the legacy page.** Add a final RUN line and a banner naming the
   successor; stop writing to it.
6. **Rollback.** The legacy page and its Routines are unchanged until step 4;
   reverting means restoring the three prompts from the saved copies. The new
   artifact can be left in place or deleted; its store dies with it.

## Not migrated (by design)

- Legacy zone values as scores: they stay `legacy_zone`.
- Asset identities for legacy rows: `asset_id` is null until resolution.
- The one account sleeve carried at an older mark: labelled, not refreshed.
