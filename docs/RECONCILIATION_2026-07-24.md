# Runtime Stream Reconciliation — 2026-07-24

Two parallel work streams landed runtime code in `main` the same day: the Claude stream (`runtime/` package, PRs #9/#17) and the Codex stream (`scripts/` five-wave layer, PRs #10/#13). Both are green — 213 tests pass combined — but two implementations of one contract will drift. This record assigns ownership, closes the duplicated ticket, and locks the seams with tests.

## Ownership decision

| Concern | Canonical home | Rationale |
| --- | --- | --- |
| Lifecycle gates and stage machine | `runtime/lifecycle.py` (+ `lifecycle_graph.py`) | Stdlib-pure fail-closed gate engine, testable in CI without the stack; the graph wiring is a thin layer over it. `scripts/orchestration_graphs.py` keeps its lifecycle graph as the SDK-integration surface but must converge on `runtime.lifecycle` gate functions in its next change rather than re-implementing gate logic. |
| Cadence route construction | `runtime/cadence.py` | Loads routes from the brain manifests with brain-lock/single-mode/integrator enforcement and partial-run honesty. `scripts/cadence_flows.py` keeps the audit-ledger Prefect flows; both read the same manifests today and `tests/test_reconciliation.py` fails the build if their orders ever diverge. |
| Writer leases and mutation serialization | `runtime/writer_lease.py` (+ `lease_queue.py`) | New in ticket 3; emits schema-shaped lease dicts (`schemas/writer_lease.schema.json`) so PacketGuard and the `scripts/` gateways consume them unchanged. |
| Governed dispatch, MCP mounts, evidence/memory gateways, observability, trusted launcher | `scripts/` (Codex stream) | Not duplicated in `runtime/`; canonical as built. |

Rule going forward: contract *enforcement logic* lives in `runtime/` (stdlib-pure, CI-proven); SDK/service *integration* lives in `scripts/`. A change that adds gate logic to `scripts/` or service clients to `runtime/` is on the wrong side of the seam.

## Ticket 4 — closed as absorbed

The AutoGen challenge-pair debate (build ticket 4) is delivered by the Codex stream: `scripts/group_debate.py` (challenge-pair debates, cadence chats, dynamic selector per brain) and `scripts/autogen_challenge_pair.py`. No second implementation will be built. Ticket 4 is closed.

## Memory-layer contention — recorded, not merged

The memory slot now has two live approaches:

- `scripts/memory_layer.py` — mem0-scope governed gateway (leased writes, verify-before-write, brain-locked reads) with a stdlib fallback backend; activation-gated on an LLM key.
- `runtime/memory_trial.py` — the ticket-5 graphiti trial harness per frontier-scan decision #2 (temporal validity, first-party MCP server, one brain namespace first).

Decision rule (unchanged from the frontier scan and the roadmap's kody criteria): the memory layer that activates must demonstrate verify-before-write, source provenance, namespace isolation matching the manifests, and readback on every mutation. The graphiti trial runs on the workstation when FalkorDB and an LLM key exist; until its evidence lands, the mem0 gateway remains the governance reference and **no memory layer is active**. Joe picks after trial evidence, not before.

## Drift locks

`tests/test_reconciliation.py` enforces this record:

1. For all six cadence routes, `runtime.cadence.build_cadence_run` order equals the manifest order `scripts/cadence_flows.py` consumes — the two streams cannot silently diverge on who runs when.
2. The ticket-4 absorption is real: the Codex debate modules exist and expose their builders.
3. Lease dicts from `runtime/writer_lease.py` carry every field `schemas/writer_lease.schema.json` requires.
