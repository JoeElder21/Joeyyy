# Runtime Host Decision — 2026-07-30

Answers the question the repository has been blocked on since the integration
build-out: **where does the runtime actually run?** Recorded on Joe's
instruction to decide it rather than return it as an open question.

Until this record, every `scripts/` integration module and half of `runtime/`
were written against a host that did not exist. `scripts/verify_runtime_stack.py`
reported `installed_count: 0` — zero of twenty declared dependencies importable
— and reported `valid: true` anyway, because it had no way to fail on absence.
Nothing could be promoted out of `shadow`, because promotion requires real
missions and real missions require a runtime.

## Decision

**Two hosts, split by what each is for. No third.**

| Host | Role | What runs there |
| --- | --- | --- |
| **Joe's workstation** | The only *governed execution* host | Full stack from `requirements/lock-2026-07-24.txt`; all MCP mounts; trusted-launcher signing key; real missions; memory backend |
| **GitHub Actions** | The *proving* host — no authority | Both CI jobs: the stdlib contract floor and the `full-stack` job that installs the lock and runs the dependency-gated tests |

**No cloud or container runtime is authorized.** An ephemeral container cannot
hold the trusted-launcher signing key, cannot reach a live Civil 3D session,
and would need the workstation's credentials copied into it — which the
connector policy and `docs/PRIVACY_AND_DATA_BOUNDARIES.md` both forbid.

## Why the workstation

1. **Four of six MCP mounts require it regardless.** `civil3d` needs a live
   Civil 3D session; `gdrive` needs a one-time OAuth flow on Joe's machine;
   `filesystem` and `github` are grant-gated writes. A second host would not
   remove that requirement, only duplicate it.
2. **The trusted launcher already assumes it.** `scripts/trusted_launcher.py`
   requires a signing key living outside the repository at `0600` on a machine
   Joe controls. That is a workstation property, not a container property.
3. **Private context never has to move.** APEX and JEOS source records stay in
   their authorized command centers. A cloud runtime would mean copying private
   evidence to a host Joe does not own.
4. **The memory decision (A-2) lands there either way.** Both candidates need
   workstation infrastructure — graphiti needs FalkorDB, mem0 needs a provider
   key held locally.

## Why GitHub Actions is a prover and not a runtime

The `full-stack` job installs the resolved lock and runs the suite with
`--require-tier all`, so the ~27 dependency-gated tests execute somewhere on
every push. That closes the hole where an integration module could diverge from
its `runtime/` authority and no test would notice — the exact failure that let
`scripts/orchestration_graphs.py` promote `shadow → active` with no human
checkpoint.

CI holds **no credentials, no grants, and no writer leases.** It proves code,
never missions. A green CI run is not activation evidence: gate 21 in
`runtime/lifecycle.py` already refuses to let a harness pass promote an agent,
and that applies to this job too.

## Setup on the workstation

Python 3.11 or 3.12, in a virtual environment dedicated to this repository:

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements/lock-2026-07-24.txt
```

Verify, in order — each command fails loudly rather than degrading:

```bash
python scripts/verify_runtime_stack.py --require-tier all
python scripts/privacy_guard.py
python scripts/validate_specialist_corps.py
python -m unittest discover -s tests -v
python scripts/verify_mcp_mounts.py
```

The suite is correct on this host only when no test skips for a missing
dependency. A skip here means the stack is not actually installed.

## What this record does NOT authorize

- **No credentials are created or stored by this decision.** APS, GitHub,
  Postgres, and Drive activation remain separate steps, each gated as recorded
  in `docs/AGENT_REGISTRY.md`.
- **No mount becomes reachable.** `require_grant` mounts still start only
  through `scripts/trusted_launcher.py` with a Joe-signed, single-use grant.
- **No agent is promoted.** All ten specialists remain `shadow`. Installing the
  stack satisfies none of the `active` gates; it only makes it possible to
  begin earning them.
- **No memory layer is selected.** The contention recorded in
  `docs/RECONCILIATION_2026-07-24.md` stands until trial evidence exists.

## Rollback

Delete the virtual environment and this file. The repository returns to
stdlib-only operation with the `validate` CI job still green — the stdlib floor
was preserved precisely so this is reversible. Removing the `full-stack` CI job
is a separate, independently reversible edit to
`.github/workflows/validate-agent.yml`.
