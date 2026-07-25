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

### Two CI corrections the first run forced

The job failed on its first run, and neither cause was a vulnerability:

1. **Exit 127, `could not determine extractor`.** The scanner cannot infer a
   parser from the filename `lock-2026-07-24.txt`. The local run had used the
   explicit `requirements.txt:` prefix and the CI args had dropped it, so CI
   exited before scanning anything. Worth noting that this failure mode is
   silent-looking: a scanner that never scans reports no vulnerabilities.
2. **Exit 127 again, resolver RPC failure.** By default the requirements
   extractor re-resolves the transitive graph over the network, which fails both
   on this lockfile's internal posthog conflict and on any resolver outage.
   `--no-resolve` is the correct setting regardless: a lockfile already *is* the
   resolved set, and re-deriving it makes the job's result depend on a third-party
   service being up.

### Triage, not suppression

`osv-scanner.toml` carries the three findings with a stated reason and an
`ignoreUntil` of 2026-08-25 each. Verified in both directions before merge: with
the config the job exits 0, and with the config removed it exits 1 on the same
three findings. **The gate is still hard** — anything not explicitly triaged
fails CI.

The expiry is the load-bearing part. These entries come back on their own, so a
triage decision cannot become permanent by being forgotten, which is the usual
fate of a suppression list.

## Addendum — the lock was not the set CI installs (found in review)

The scan above pointed only at `requirements/lock-2026-07-24.txt`. Review pointed
out that this is **not** the set either documented installation path produces:

- the validation workflow installs `requirements.txt`, which asks for
  `autogen-agentchat>=0.2.35,<0.3` while the lock pins 0.7.5 — a different
  package set entirely;
- the evaluation path installs `requirements/runtime-evaluation.txt`, whose
  `deepeval` and `pytest` appear nowhere in the lock.

So the job could report a clean Python audit while every set anyone actually
installs carried a vulnerable dependency. The scan now covers `requirements.txt`,
`requirements/runtime-contracts.txt`, and `requirements/runtime-evaluation.txt`
alongside the lock.

**It found something on the first run.**

| Severity | Package | Version | OSV | Fixed in | Source |
| --- | --- | --- | --- | --- | --- |
| Medium (6.8) | `pytest` | 8.0 | [PYSEC-2026-1845](https://osv.dev/PYSEC-2026-1845), [GHSA-6w46-j5rx-g56g](https://osv.dev/GHSA-6w46-j5rx-g56g) | 9.0.3 | `requirements/runtime-evaluation.txt` |

Fixed rather than triaged: the floor moved to `pytest>=9.0.3`. This file is a
live manifest, not a dated snapshot, so editing it falsifies no record — the
reason `click` in the lock was carried forward instead does not apply here.
`deepeval` declares `pytest` with no upper bound, so nothing conflicts.

The general point is the one worth keeping: **a scanner aimed at a file nobody
installs is the same failure as a scanner that never runs.** Both report clean.

## Addendum 2 — locks generated for the floating tiers

The first attempt at scanning the floating manifests enabled resolution, so the
scanner would derive concrete versions from `>=` ranges. It failed in CI:

```
failed resolution for .../runtime-contracts.txt: rpc error: code = Unavailable
...
Total 0 packages affected by 0 known vulnerabilities
Exit code: 127
```

**Note what that says.** The resolver was down, so the scan covered nothing — and
still printed a clean total. It exited 127 rather than 0, so the gate held, but
the output it produced was indistinguishable from a genuine pass. That is the
third appearance in this file of the same failure: *a scanner that does not scan
reports no vulnerabilities.*

Resolved by generating locks instead of resolving at scan time:

| Lock | Source | Packages |
| --- | --- | --- |
| `requirements/lock-runtime-root.txt` | `requirements.txt` | resolved set |
| `requirements/lock-runtime-contracts.txt` | `requirements/runtime-contracts.txt` | resolved set |
| `requirements/lock-runtime-evaluation.txt` | `requirements/runtime-evaluation.txt` | resolved set |

Generated with `uv pip compile <source> -o <lock> --python-version 3.12
--no-header`, scanned with `--no-resolve` for the same reason the dated lock is:
a lock already *is* the resolved set, so the scan needs no third-party service
and cannot go quiet when one is unavailable.

These are explicitly **not** dated evidence records. They are meant to be
regenerated, and pins in them may be edited to take a fix — the constraint that
keeps `click` unfixed in `lock-2026-07-24.txt` does not apply here.

### One triage reassessed as a result

Querying OSV directly for all 92 pinned packages across the three new locks
returned exactly one finding: `diskcache 5.6.3` (PYSEC-2026-2447, CVSS 5.2).

It was already triaged — but **the stated reason was wrong**, and generating the
locks is what exposed that. The reason said diskcache sat "in the same undeployed
tier as chromadb", which held when the only scanned input was the dated lock. The
evaluation lock shows it resolving into the evaluation tier, a documented
workstation install path. The finding stays triaged because no upstream fix
exists, but the justification is now "no fix exists" alone rather than "nothing
installs it", and `osv-scanner.toml` says so.

A triage reason is a claim like any other. This one was accurate when written and
became false when the scanned surface widened, without anything failing.

## Rollback

Additive. Rolling back is deleting this file and the `dependency-audit` job in
`.github/workflows/security.yml`. No dependency, pin, or governance rule was
changed.
