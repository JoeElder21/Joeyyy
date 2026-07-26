# Security Policy

This repository defines an agent governance system. It contains **no credentials, connector
identifiers, model configuration, or private source records**, and `scripts/privacy_guard.py`
enforces that on every commit and every CI run.

## Reporting a vulnerability

Report privately through GitHub's **Security → Report a vulnerability** advisory flow on this
repository. Do not open a public issue for a security report.

Please include what an attacker could cause, the affected file or workflow, and a minimal
reproduction. Expect an initial response within seven days.

## What is in scope

This repository's threat model is **supply-chain and boundary compromise of an agent system**,
not a hosted service. In-scope findings include:

- A path that causes `scripts/privacy_guard.py` to miss data it is meant to block, or that
  would place private records, credentials, or client source material in the public tree.
- A bypass of a fail-closed boundary: `scripts/packet_guard.py` admission, writer-lease
  serialization (`runtime/writer_lease.py`), brain isolation between APEX and JEOS, or the
  one-time grant control in `scripts/trusted_launcher.py`.
- A CI weakness in `.github/workflows/` — script injection, credential persistence, cache
  poisoning, or an impostor action reference. These are audited by zizmor on every push, PR,
  and weekly; a finding zizmor misses is worth reporting.
- Prompt-injection or tool-poisoning content reachable through a repository file that an
  agent reads as instructions rather than as data.

## What is out of scope

- Vulnerabilities in third-party dependencies. Report those upstream; Dependabot tracks the
  pinned versions here.
- Missing hardening in software that is *documented as a candidate* but not deployed. The
  registers in `docs/EXTERNAL_RUNTIME_REGISTER_2026-07-24.md` and
  `docs/ECOSYSTEM_REPO_ANALYSIS.md` record evaluation, not installation.
- Absence of a runtime, model access, or connector. The repository deliberately makes no
  claim of continuous agent operation.

## Supply-chain posture

Because this system's purpose is absorbing external agent capabilities, inbound trust is the
primary risk. Standing controls:

- Every GitHub Action is pinned to a full commit SHA, with Dependabot keeping the pins fresh.
- `actions/checkout` runs with `persist-credentials: false`; workflow permissions are
  least-privilege and read-only.
- Provenance verification is required before any external repository is read for absorption
  (see `docs/FRONTIER_REPO_SCAN_2026-07-24.md` and the absorption-candidate issue form).
- Secret scanning runs locally pre-commit via gitleaks, alongside the house privacy guard.
