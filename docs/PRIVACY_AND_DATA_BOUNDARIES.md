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
- Specialists receive only task-scoped evidence and never open opposite-brain or unknown sources.
- Cross-brain dependencies use a minimized constraint packet created by Agent 007; raw source payloads do not cross.
- Health or finance constraints that remain inside JEOS use a separate, expiring brain-private constraint packet created by Agent 007.
- A writer lease names the only agent authorized to mutate a resource for a mission.
- `scripts/packet_guard.py` rejects manifest, namespace, target, roundtable, and lease mismatches before execution.
- Completion requires a schema-valid mutation result containing an affirmed expected-state match, observed state, readback evidence, a lease-bounded verification time, rollback method, verified rollback test, and rollback evidence.

## Repository hygiene

- `.env*`, private keys and certificates, local databases, credentials, and runtime-memory directories are ignored.
- Automated scans cover likely tokens, credentials, private links, contact details, and common private-data filenames.
- `scripts/privacy_guard.py` scans every tracked UTF-8 text file regardless of extension and rejects binary/non-UTF-8 payloads, Git LFS pointers, common document/media/archive types, credentials, and bearer tokens in this public source tree; CI runs it before the contract suite.
- Shadow fixtures are synthetic. Runtime records are never copied into tests.

Prompt contracts strengthen isolation, but hard connector isolation depends on runtime credentials, scopes, and write proxies. Agent 007 must verify the active environment before claiming that stronger guarantee.
