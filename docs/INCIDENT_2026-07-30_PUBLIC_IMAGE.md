# Incident — screenshot committed to the public repository (2026-07-30)

## What happened

Commit `173fbe9` ("Add files via upload") added `IMG_2794.png` — a 3.3 MB, 864×1821 PNG, the aspect ratio of a phone screenshot — to this public repository. `scripts/privacy_guard.py` rejected it on two rules (non-source artifact type; binary file in a public source tree) and the `Validate Agent 007 and Mirrored Corps` workflow went red on `main` and stayed red.

The guard worked. Nothing bypassed it; the failure was simply not acted on until it was noticed.

Timeline evidence: the workflow was green at `573ee44` and red at `173fbe9`. Removed from `HEAD` in PR #54 (`4c0f46e`), which restored the workflow to green.

## Decision: no history rewrite

Delegated to Agent 007 on 2026-07-30 ("do what's best for the system"). The decision is **not** to rewrite `main`'s history, for three reasons in order of weight:

1. **A rewrite would not actually remove it.** GitHub retains unreachable objects after a force-push; the blob stays fetchable by its SHA until GitHub Support purges it server-side. A rewrite would produce the *appearance* of removal without the substance — the worst possible outcome for a system whose core discipline is not claiming more than is true.
2. **The cost is high and lands on other work.** `main` currently carries concurrent branches from several parallel agent sessions. A force-push invalidates every open branch, every open pull request, and every existing clone, to buy the appearance in (1).
3. **The effective remedy is different.** If the screenshot shows anything sensitive, the correct response is to treat it as disclosed: rotate anything credential-like that appears in it, and request a cache purge from GitHub Support. That is a disclosure-handling task, not a git task.

Only Joe knows the image's contents; this record does not assess them, and the image was never opened here. **If it shows credentials, tokens, account numbers, client data, or personal information, act on point 3 — the git history is not the control that protects you there.**

Supporting evidence: the `Secret scan (gitleaks)` check passes on this repository, so no *detected* credential pattern is present. That is corroboration, not proof — gitleaks does not read pixels.

## Recurrence prevention

- `.gitignore` now excludes `*.png`, `*.jpg`, `*.jpeg`, so an accidental upload cannot silently re-enter the tree. The ignore rules and the privacy guard's policy now agree rather than only the guard catching it after the fact.
- The guard itself was already correct and is unchanged.

## Standing lesson

A red gate on `main` is an unresolved incident, not background noise. This one sat red across several merges because attention was on feature branches. The cheapest detection is that any session picking up work re-runs `scripts/privacy_guard.py` against `main` before starting, which is already the documented validation surface.
