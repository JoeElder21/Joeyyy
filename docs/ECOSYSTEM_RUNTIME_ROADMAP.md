# Ecosystem Runtime Roadmap

This is the implementation record for the repositories supplied on 2026-07-24. It deliberately distinguishes a **tracked integration** from an **active service**. A repository or SDK cannot be called active until its dependency, account or self-hosted service, least-privilege MCP server, and controlled mission have been verified in the target runtime. No such external verification occurred in this source-only change.

The canonical machine-readable inventory is `config/ecosystem_runtime.toml`; `scripts/validate_ecosystem_runtime.py` validates all 15 supplied repositories without network access. The supplied request says both “12” and names 15 repositories, so the inventory records every named repository rather than silently dropping three.

## Non-negotiable runtime boundary

1. Specialist code receives a validated delegation/handoff packet and named MCP tool capabilities only. It does not receive raw HTTP clients, account credentials, or arbitrary filesystem access.
2. Agent 007 validates packet version, brain ownership, and writer lease before selecting an MCP capability. The MCP layer enforces the tool allowlist and least-privilege account scope.
3. Every mutation returns the existing `mutation_result` record with schema-valid readback and rollback evidence. An unavailable connector fails closed; it never falls back to direct HTTP.
4. Cross-brain source content remains prohibited. OpenTelemetry trace context may cross an orchestration boundary, but it must not embed source payloads or connector identifiers.

## Implementation sequence

### 1. Microsoft AutoGen — first runtime experiment

Build an Agent 007 coordinator plus ten read-only specialist adapters. The coordinator chooses the already-defined specialist only after PacketGuard validation and sends a typed projection of `handoff_packet.schema.json`; it remains the sole cross-brain caller and mutation executor. Configure AutoGen tools solely as MCP-client wrappers. Success is a synthetic same-brain handoff and an opposite-brain denial; it is not a production agent promotion.

### 2. MCP foundation

Use `modelcontextprotocol/python-sdk` to build the client wrapper and custom server interfaces. Deploy the reference `modelcontextprotocol/servers` filesystem, GitHub, and Google Drive servers only after their scopes are verified. Then add separate custom MCP servers for Logseq, Twenty, Plane, and APS. Each server has an explicit tool allowlist, per-brain credentials, audit log, and a disable/rollback procedure.

### 3. Model runtimes and typed handoffs

Use `openai/openai-agents-python` only as a typed Agent/Runner/handoff execution adapter; its handoff context must be the validated packet projection. Use `anthropics/anthropic-sdk-python` tool definitions only through the same MCP wrappers and parse structured tool-use responses. Neither SDK is a credential source or a connector bypass.

### 4. Observability and evaluation

Instrument the coordinator, each MCP tool invocation, and handoff boundaries with `open-telemetry/opentelemetry-python`. Export to `arize-ai/phoenix` for trace/evaluator review and `langfuse/langfuse` for prompt-version and score records. Trace attributes contain packet IDs, lifecycle stage, tool name, and outcome—not private evidence or raw prompts. Promotion evidence includes trace references and evaluator results.

### 5. Execution and scheduling

`taskipy/taskipy` is configured in `pyproject.toml` for repository validation. Add `apache/airflow` only after the daily/weekly cadence routes are mapped to explicit no-write DAG tasks and an owner-run integration task. Add `celery/celery` after a broker and result backend are provisioned; route mutation jobs to one queue per canonical brain/write-target/resource so writer leases remain serialized.

### 6. Systems of record

- `logseq/logseq`: JEOS pages are retrieved and proposed through its dedicated MCP server; no JEOS graph is mirrored into this public repo.
- `twenty-crm/twenty`: APEX opportunity and follow-up operations are exposed as narrow MCP tools for `apex_deal_engine`.
- `makeplane/plane`: APEX delivery status and risk issue operations are exposed as narrow MCP tools for `apex_delivery_commander`.
- `autodesk-platform-services/aps-sdk-node`: APEX project-file and model-property reads are exposed through a read-only APS MCP server first. Design Automation or any model mutation requires a separate controlled mission and explicit task-level authorization where applicable.

## Per-integration activation gate

For every record in the inventory, retain the following evidence in the Drive target after its Google Drive MCP server is verified: dependency/version check, configuration fingerprint without secrets, owner/brain scope, tool allowlist, packet-only dry-run trace, denied-boundary test, mutation readback and rollback test where applicable, operator, date, and removal procedure. Move the stage from `planned` to `shadow` only with that evidence; move to `active` only under the specialist lifecycle rules in `docs/SPECIALIST_ACCEPTANCE_TESTS.md`.

## Google Drive evidence

`scripts/build_drive_evidence_packet.py` renders `docs/DRIVE_ECOSYSTEM_EVIDENCE_PACKET.md`, a credential-free upload packet. It has **not** been uploaded because this session has no verified Google Drive connector, account, or destination identifier. Upload it only through the Google Drive MCP server after its scope and target are verified; record the resulting Drive evidence reference outside this public repository.

## Rollback

Set the affected inventory record to `restricted` or `retired`, disable the MCP server or remove its tool from the allowlist, revoke the runtime credential in the secret manager, preserve the sanitized trace/evidence reference, and run a denied-tool test. The source-only rollback point for this initial registry is the commit that introduces `config/ecosystem_runtime.toml`.
