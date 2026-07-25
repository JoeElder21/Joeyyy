# Dependency Audit — 2026-07-25

First run of `google/osv-scanner` against this repository's pinned dependencies.
Now a standing CI job (`.github/workflows/security.yml`).

## Why this ran at all

`docs/REPO_OPTIMIZATION_2026-07-25.md` put osv-scanner in Tier 3 — "revisit when
the lockfile is authoritative" — reasoning that most Python dependencies here are
optional and loosely pinned, so signal would be low.

`requirements/lock-2026-07-24.txt` pins 266 packages exactly, which is
authoritative by any reasonable reading. So the condition was already met, and
the deferral was tested rather than assumed.

**The assumption was wrong.** The scan returned three known vulnerabilities,
including one critical, plus a resolution failure that is arguably the more
serious finding.

## Findings

| Severity | Package | Version | OSV | Fixed in |
| --- | --- | --- | --- | --- |
| **Critical (9.3)** | `chromadb` | 1.1.1 | [PYSEC-2026-311](https://osv.dev/PYSEC-2026-311), [GHSA-f4j7-r4q5-qw2c](https://osv.dev/GHSA-f4j7-r4q5-qw2c) | **no fix available** |
| High (7.2) | `click` | 8.2.0 | [PYSEC-2026-2132](https://osv.dev/PYSEC-2026-2132) | 8.3.3 |
| Medium (5.2) | `diskcache` | 5.6.3 | [PYSEC-2026-2447](https://osv.dev/PYSEC-2026-2447), [GHSA-w8v5-vhqr-4h9v](https://osv.dev/GHSA-w8v5-vhqr-4h9v) | **no fix available** |

`connectors/aps/package-lock.json` — 62 packages, **no issues found**.

## The lockfile does not resolve

Separate from the vulnerabilities, and probably worth more attention:

```
failed resolution: requirements conflict:
posthog: "==7.29.0,>=2.4.0,<6.0.0"
```

`lock-2026-07-24.txt` pins `posthog==7.29.0`, while `chromadb==1.1.1` in the same
file requires `posthog>=2.4.0,<6.0.0`. Those cannot both hold.

A lock file's entire purpose is to be a resolved, installable set. This one is
internally unsatisfiable, which means it has probably never been installed as
written — a fresh `pip install -r` against it should fail. That is a quiet
correctness problem the vulnerability scan surfaced as a side effect, and it
undercuts the value of every other pin in the file.

## Assessment

Severity in the abstract is not severity here. None of these three packages is
installed by repository validation: the file is a resolved snapshot of the
optional `requirements/runtime-*.txt` tiers, and CI installs only
`requirements.txt`. `chromadb` and `diskcache` arrive as transitive dependencies
of the memory/evaluation tiers, which are not deployed.

So the accurate framing is: **this is a workstation exposure, not a CI exposure.**
It matters when and if those tiers are installed on the Civil 3D machine, and it
matters more because `chromadb`'s critical has no fix available — an upgrade
cannot resolve it, only a decision about whether that tier is deployed at all.

## Recommended actions, for Joe

1. **`click` — bump to 8.3.3.** The only one with a fix; low risk, widely used.
2. **`chromadb` — decide, do not patch.** A 9.3 with no fix is a deployment
   question, not a version question. If the memory tier that pulls it in is not
   being deployed, drop it from the lock rather than carrying a critical.
3. **Fix or regenerate the lockfile.** The posthog conflict means the file cannot
   be installed as written. Resolving it will likely change the chromadb answer
   too, since chromadb is what constrains posthog.
4. **Leave `diskcache`** unless the tier deploys; medium, no fix, transitive.

Nothing was changed in the lockfile by this audit. Dated records are append-only
in spirit, and swapping pins inside a snapshot named for 2026-07-24 would falsify
the record it exists to be. A new lockfile is a new dated file.

## Method

```bash
go install github.com/google/osv-scanner/v2/cmd/osv-scanner@latest
osv-scanner scan source --lockfile=requirements/lock-2026-07-24.txt
osv-scanner scan source --lockfile=connectors/aps/package-lock.json
```

Built from source rather than fetched as a release binary, for the same reason
recorded in `docs/SECRET_HISTORY_SWEEP_2026-07-25.md`: no third party is trusted
to supply an executable that audits this repository's supply chain.

Now running in CI on push, pull request, and weekly, so this becomes a standing
gate rather than a one-time observation. Weekly matters here specifically —
vulnerability disclosures land against unchanged pins, so a dependency set that
was clean at merge does not stay clean, and only a scheduled scan notices.

## Rollback

Additive. Rolling back is deleting this file and the `dependency-audit` job in
`.github/workflows/security.yml`. No dependency, pin, or governance rule was
changed.
