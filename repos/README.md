# First-party sub-repositories

JoeElder21 repositories installed as **git submodules**, pinned to a specific
commit, so this repository serves as the umbrella for the account without
merging their trees. Only the gitlink commit is recorded here — each
sub-repository keeps its own history, issues, CI, and deployment, and is
governed by its own contracts, not by this repository's guards.

This mirrors the discipline in `vendor/` (see `vendor/README.md`), with one
difference: these are Joe's own repositories, so there are no
upstream-dependency intake records — the pin table below is the whole
provenance.

## Contents

| Path | Repository | Pinned at | What it is |
| --- | --- | --- | --- |
| `elder-command-center` | `JoeElder21/Elder-Command-Center` | `946a545` (main) | Elder Command Center operating standard: prompts, templates, examples, and Python tooling for JEDS / Savage Investments deliverables. |
| `antigravity-sdk-python` | `JoeElder21/antigravity-sdk-python` | `9e47a90` (main) | Joe's fork of the Antigravity Python SDK. |

Planned: `elder-briefing-app` (the Next.js Daily Executive Briefing app) will be
added here once its repository is transferred from the old account to
JoeElder21. Until that transfer lands there is nothing to pin.

## Install

Submodules are not fetched by a plain clone:

```bash
git submodule update --init --recursive
```

Update a pin deliberately, never incidentally, and move the table row above in
the same commit — `tests/test_vendor.py` asserts every declared submodule is a
pinned gitlink rather than committed content:

```bash
git -C repos/<name> fetch origin
git -C repos/<name> checkout <commit>
git add repos/<name>
```
