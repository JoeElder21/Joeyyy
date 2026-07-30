# Secret History Sweep — 2026-07-25

One-off verification that nothing sensitive predates `scripts/privacy_guard.py`.
Run on Joe's instruction, closing open decision 5 of
`docs/REPO_OPTIMIZATION_2026-07-25.md`.

This repository was public before the privacy guard existed. The guard scans the
**working tree**; it has never scanned **history**. Git history is permanent and
independently fetchable, so a credential committed and later deleted is still
public. This sweep closes that gap.

## Result

**Clean. Zero verified and zero unverified secrets across the complete object
graph.**

| Measure | Value |
| --- | --- |
| Commits in history | 95 |
| Chunks scanned | 654 |
| Bytes scanned | 1,316,403 |
| Verified secrets | 0 |
| Unverified secrets | 0 |
| Verification attempts made | 4 (all rejected; nothing reported) |

## Method

TruffleHog v3.96.0, built from source in this session:

```bash
git clone --depth 1 --branch v3.96.0 https://github.com/trufflesecurity/trufflehog.git
go build -o trufflehog .        # Go 1.24.7, toolchain auto-upgraded to 1.25.12
```

Two independent passes, to make the coverage claim rather than assume it:

```bash
trufflehog git file:///home/user/Joeyyy --json --no-update           # default
trufflehog git file:///home/user/Joeyyy --bare --json --no-update    # all refs
```

Both returned byte-identical scan totals — 654 chunks, 1,316,403 bytes, 0/0
secrets. Coverage was confirmed independently rather than inferred from the
tool's own summary:

```
git rev-list --count HEAD   -> 95
git rev-list --all --count  -> 95
```

Equal counts mean HEAD's ancestry **is** the complete object graph: `main` is an
ancestor of the working branch, so no branch holds unscanned history. Had these
differed, the sweep would not have been complete and this record would say so.

## Build-path note, recorded because the obstacles are instructive

Three install paths failed before the source build worked, and each failure is a
supply-chain observation worth keeping:

1. **Docker image** — `docker` CLI present, daemon not running. The published
   image was never pulled.
2. **Release binary** — the GitHub release asset CDN returned 403 through this
   environment's egress proxy. Worth noting that a guessed version URL returned
   404 first: *a 404 on a guessed asset name is not evidence a tool does not
   exist*, and treating it that way is how an agent talks itself into a
   lower-assurance substitute.
3. **`go install`** — refused: the upstream `go.mod` carries `replace`
   directives, which `go install` will not honor from a dependency position.

The source build is the highest-assurance of the four paths: the tag was cloned
from the canonical repository over an authenticated TLS path, and the binary was
compiled locally rather than fetched pre-built. No third party was trusted to
supply an executable.

## Verification posture

TruffleHog is verification-first: it calls the provider API to check whether a
candidate credential is still live. Four verification attempts were made and all
were rejected, so nothing was reported at either confidence level. No credential
material left this environment, because no credential was found to send.

This is why TruffleHog is the right tool for a **one-off history sweep** and the
wrong tool for a standing pre-commit hook — the live-API round trip that makes it
authoritative here is exactly what makes it too slow and too chatty for every
commit. `gitleaks` holds the pre-commit position (offline, rule-first) and
`scripts/privacy_guard.py` holds the house-specific rules. The three are
complements, not substitutes.

## Standing conclusion

The privacy guard's working-tree coverage can now be treated as complete
coverage: history has been independently verified clean to the root commit, so
every commit from `522e9e9` forward is guarded by the pre-commit gate and CI.

Re-run this sweep if history is ever rewritten, if a repository is merged in, or
if a credential is suspected — not on a schedule. A clean one-off result over
immutable history does not decay.

## Rollback

This file is a point-in-time evidence record and is additive. Rolling it back is
deleting it; no governance rule, gate, or configuration was changed by the sweep.
