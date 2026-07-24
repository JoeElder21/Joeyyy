# Agent Runtime Bridge — Governed Handoffs on the OpenAI Agents SDK

Runtime record, 2026-07-24. Incorporates `openai/openai-agents-python` (verified: official OpenAI SDK, pinned `openai-agents==0.18.3` in `requirements/runtime-orchestration.txt` and the lock) per Joe's directive: the `handoff()` primitive and typed-context transfer pattern are now the runtime implementation of this repository's packet contracts.

Code: `scripts/agent_runtime.py` · Tests: `tests/test_agent_runtime.py`

## What the contracts gain at runtime

| Governance contract (before) | Runtime enforcement (now) |
| --- | --- |
| `delegation_packet.schema.json` validated on demand via CLI | `governed_handoff()` — every Agent 007 → specialist transfer carries a typed payload; PacketGuard admission runs inside `on_handoff` and an invalid packet **cannot transfer control** (fail-closed `HandoffRejected`) |
| Addressee and brain ownership checked by convention | `admit_delegation()` — addressee match and the brain lock are checked at the transfer point, after full schema + relational validation (which includes the v2.1 legacy gate) |
| Handoff returns validated manually | `validate_specialist_return()` — PacketGuard runs on the returned handoff packet (including the passed-criteria-need-evidence and source-evidence rules) with the outcome logged |
| Error ledger as a hand-written line format | `AuditLedger` — append-only, hash-chained JSONL (absorbed block/buzz pattern): every admission, rejection, and return validation is auto-logged; `verify()` detects any historical edit |
| "Agent 007 routes to specialists" as prose | `build_governed_graph()` — the topology is constructed from the native TOML roster: 007 → all ten specialists; each specialist → 007 only; no specialist-to-specialist handoffs exist in either brain |

## Design decisions

- **The JSON schemas stay canonical.** The SDK payload (`DelegationHandoffInput`) carries the packet as a JSON string rather than re-modeling the schema in pydantic — one source of truth, no drift, and compatible with the SDK's strict-schema mode.
- **Degrade cleanly.** The stdlib core (roster, ledger, admission) imports with no third-party dependencies; the SDK layer activates only when `openai-agents` is installed, matching the runtime-stack convention. CI stays green without the stack.
- **Offline by construction.** Building the governed graph makes no network calls and needs no API key. Only `Runner.run()` executes models; nothing in this bridge invokes it. Live runs are a separate activation step under the shadow-stage acceptance gates.

## Efficiency, measured honestly

Metric: **manual steps per governed delegation** (the defined unit of system operating cost; no other figure is claimed).

Before the bridge, one lawful delegation required six manual steps: (1) compose the packet by hand, (2) run the PacketGuard CLI on it, (3) deliver the instruction to the specialist, (4) collect the return, (5) run PacketGuard on the returned handoff packet, (6) hand-write the audit/ledger entry. With the bridge, the same lawful delegation is **one step** — invoke the governed handoff; admission validation, addressee/brain checks, transfer, return validation, and tamper-evident audit logging are automatic and fail-closed.

6 → 1 manual steps = **83% reduction in dispatch overhead per delegation**, which exceeds the 75% target for the operation this system performs most. The claim covers exactly this metric and nothing else; model-quality and wall-clock effects are unmeasured until live shadow missions run.

## Running it

```bash
# stdlib environment (CI): bridge core tests run, SDK tests skip
python -m unittest tests.test_agent_runtime -v

# full stack: install the orchestration tier, then everything runs
pip install -r requirements/runtime-orchestration.txt
python -m unittest tests.test_agent_runtime -v
```

Verified 2026-07-24: full suite 131 tests OK (stdlib, 5 skips by design); 39/39 OK in an isolated venv with `openai-agents==0.18.3`, including live `on_invoke_handoff` fail-closed rejection of a legacy packet and admission of a valid v2.1 packet.

## Boundaries and rollback

- No API keys are stored or read by this bridge; live execution (`Runner.run`) is out of scope until Joe activates it, and model calls then use the runtime's own credential store.
- The audit ledger contains packet metadata (IDs, modes, error strings) — never credentials or client-sensitive content, per the error-learning rules.
- Rollback: delete `scripts/agent_runtime.py`, `tests/test_agent_runtime.py`, and this document; no other file depends on them and no persistent state exists beyond audit ledgers you created.
