# Privacy and Data Boundaries

This repository is public. It stores only agent contracts, logical namespaces, sanitized manifests, schemas, tests, migration records, and synthetic examples.

## Never commit

- Raw Google Drive or Docs content and identifiers
- Employer, client, project, lead, proposal, contact, quantity, schedule, or financial records
- Journals, relationships, health, medications, personal finance, addresses, schedules, or private messages
- Email addresses, phone numbers, credentials, secrets, tokens, cookies, connector identifiers, or access-control data
- Live memory records or roundtable content

## Runtime handling

- Private runtime memory remains inside its authorized brain-owned system.
- Agent 007 supplies the minimum authorized evidence required for the mission.
- Evidence references declare owner brain, source type, Agent 007 scope verification, and sensitivity; sensitivity may never be downgraded downstream.
- APEX evidence stays in APEX namespaces and targets.
- JEOS evidence stays in JEOS namespaces and targets.
- Specialists receive only task-scoped, PacketGuard-validated evidence and no direct connector handles under this contract; Agent 007 or a runtime-enforced brain-scoped proxy performs retrieval.
- Cross-brain dependencies use a minimized constraint packet created by Agent 007; raw source payloads do not cross.
- Private constraints that remain inside JEOS use a separate, expiring brain-private constraint packet created by Agent 007. Its `constraint_type:use_mode` pair must match the destination agent's exact manifest profile.
- A writer lease names the only agent authorized to mutate a resource for a mission.
- `scripts/packet_guard.py` rejects manifest, namespace, target, roundtable, and lease mismatches before execution.
- Completion requires a schema-valid mutation result containing an affirmed expected-state match, observed state, readback evidence, a lease-bounded verification time, rollback method, verified rollback test, and rollback evidence.

## Third-party telemetry in the runtime stack

An installed dependency that phones home is an outbound data flow, and it is subject to the same boundaries as any connector. Runtime libraries may not export mission data, packet content, prompts, or trace spans to a vendor endpoint.

- **crewAI ships telemetry enabled by default**, POSTing spans to `telemetry.crewai.com`. Observed 2026-07-24 during a full-stack test run, where it failed only because the sandbox blocked the host — on a workstation it would have succeeded. `scripts/crew_bridge.py` therefore sets `CREWAI_DISABLE_TELEMETRY`, `CREWAI_TELEMETRY_OPT_OUT`, and `OTEL_SDK_DISABLED` before importing crewai, since the library reads them at import time. `setdefault` is used so an explicit environment decision by Joe still wins, and `tests/test_data_memory_layers.py` asserts the opt-out is in force.
- Agent 007's own OpenTelemetry tracing (`scripts/observability.py`) is local by default: spans go to an in-memory exporter and the hash-chained ledger, never to a network collector. Pointing it at a collector — including a self-hosted Phoenix — is an activation decision, and any collector outside Joe's control is a connector requiring the same authorization as any other.
- **At intake, every new runtime dependency must be checked for default-on telemetry**, and any found must be disabled in code at the import boundary and recorded here. Treat an undisclosed outbound flow from a dependency as an error-ledger entry, not a footnote.

## Repository hygiene

- `.env*`, private keys and certificates, local databases, credentials, and runtime-memory directories are ignored.
- Automated scans cover likely tokens, credentials, private links, contact details, and common private-data filenames.
- `scripts/privacy_guard.py` scans every tracked UTF-8 text file regardless of extension and rejects binary/non-UTF-8 payloads, Git LFS pointers, common document/media/archive types, credentials, and bearer tokens in this public source tree; CI runs it before the contract suite.
- Shadow fixtures are synthetic. Runtime records are never copied into tests.

Prompt contracts strengthen isolation, but hard connector isolation depends on runtime credentials, scopes, and write proxies. No specialist may become `active` until Agent 007 verifies that an opposite-brain connector request cannot reach a connector in the selected runtime.
