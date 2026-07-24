# External Runtime Register — Category 4–9 Intake

This register reconciles the repositories named in the current mission.  The
message says “12” but enumerates repository IDs **11 through 24**, which is 14
distinct repositories.  This record keeps all 14 visible without claiming
deployment, connector access, or specialist activation that has not been
verified.

| ID | Repository | Role | Current disposition | Promotion condition |
| --- | --- | --- | --- | --- |
| 11 | `modelcontextprotocol/python-sdk` | Typed MCP client/server boundary | Declared dependency; no server configured | Local fake-server isolation test, then approved server config |
| 12 | `openai/openai-agents-python` | Typed Agent 007 handoffs and traces | Declared dependency; no runtime adapter | Packet-bound handoff adapter and controlled test |
| 13 | `anthropics/anthropic-sdk-python` | Native tool-use/model client | Declared dependency; no credential or tool use | Approved runtime credential and typed-tool isolation test |
| 14 | `arize-ai/phoenix` | Trace and evaluator service | OTEL client declared; server unconfigured | Privacy-reviewed workstation deployment |
| 15 | `langfuse/langfuse` | Prompt versions, trace scores | Candidate only | Privacy-reviewed service and prompt version policy |
| 16 | `open-telemetry/opentelemetry-python` | Distributed trace context | SDK declared; no exporter configured | No-content local span test and exporter privacy review |
| 17 | `taskipy/taskipy` | Repeatable local task commands | Task definitions added in `pyproject.toml` | Install taskipy in target environment and run tasks |
| 18 | `apache/airflow` | DAG scheduling | Deferred; Prefect is the recorded current choice | Explicit orchestration decision superseding the conflict |
| 19 | `celery/celery` | Writer-lease queueing | Declared dependency; no broker or worker | Broker, per-resource serialization test, and rollback runbook |
| 20 | `logseq/logseq` | JEOS knowledge graph | Workstation candidate | Approved personal-machine install and MCP-only access test |
| 21 | `twenty-crm/twenty` | APEX opportunity data | Candidate system of record | Data-privacy review and approved deployment |
| 22 | `makeplane/plane` | APEX delivery data | Candidate system of record | Data-privacy review and approved deployment |
| 23 | `autodesk-platform-services/aps-sdk-node` | APEX Civil 3D cloud data | Candidate; separate Node deployment | APS sandbox scopes and read-only model test |
| 24 | `modelcontextprotocol/servers` | Reference filesystem/GitHub/Postgres servers | Workstation deployment candidate | Per-server configuration, isolation test, and target authorization |

## Operating rule

Every specialist remains `shadow` and uses
`packet_only_no_direct_connectors`.  An external system becomes usable only
through a configured MCP boundary or an equally restrictive, tested proxy; a
package declaration, a repository record, or a dashboard account never grants
direct access.  Apache Airflow remains deferred rather than duplicating the
recorded Prefect scheduling direction.

The first implemented item is the AutoGen preflight documented in
`docs/AUTOGEN_CHALLENGE_PAIR_TRIAL.md`.  The next safe item is an MCP
fake-server isolation test, not a production connector.
