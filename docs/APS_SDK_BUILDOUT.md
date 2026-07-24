# APS Node SDK Build-Out Guide — autodesk-platform-services/aps-sdk-node

Integration and validation guide for the Autodesk Platform Services (APS) cloud connector, registered as
candidate infrastructure in `docs/AGENT_REGISTRY.md`. Upstream verified by direct read on 2026-07-24;
re-verify before executing, since package maturity is mixed GA/beta and coverage is still expanding.

Upstream: https://github.com/autodesk-platform-services/aps-sdk-node

## What it is

The official Autodesk Platform Services (formerly Forge) SDK for Node.js — Autodesk's cloud APIs for
project files and model data, with no open Civil 3D session required. It is the cloud leg of the Civil 3D /
engineering MCP layer; the Civil 3D MCP connector (`docs/CIVIL3D_MCP_BUILDOUT.md`) is the workstation leg.

Packages shipped under the `@aps_sdk` npm scope (Apache-2.0, Node 16.16+, npm 8.11+):

| Package | Covers |
| --- | --- |
| `authentication` | OAuth2 two-legged and three-legged token flows |
| `autodesk-sdkmanager` | Shared client/config plumbing required by the other packages |
| `oss` | Object Storage Service (buckets, uploads) |
| `data-management` | Hubs, projects, folders, items, versions (BIM 360/ACC file tree) |
| `model-derivative` | Translate models to viewables; extract metadata and element properties |
| `webhooks` | Event subscriptions |
| `construction-account-admin`, `construction-issues` | ACC account admin and issues |
| `secure-service-account` | Service-account credentials flow |

## Capability corrections (verified against upstream, 2026-07-24)

Two capabilities commonly attributed to this SDK are **not** in it:

- **No `design-automation` package.** Running scripts on models headlessly in the cloud remains
  REST-only for Node (Autodesk's official sample: `aps-design-automation-nodejs`). The headless-report
  play stays feasible — routed through the Design Automation v3 REST API, not this SDK.
- **No ACC Model Properties package.** Element-level properties and quantities are instead reachable
  through the `model-derivative` package (metadata/properties and specific-properties endpoints) once a
  model version is translated. Quantity extraction without manual takeoff stays feasible — via Model
  Derivative.

Agents must not claim an SDK surface that does not exist; cite this section when routing work.

## Agent integration plan

- **Data Management (read)** → `apex_intelligence_forge`: enumerate hubs/projects/folders/items/versions,
  know what files exist and when they last changed, trigger derivative extraction.
- **Model Derivative properties** → `apex_delivery_commander`: element-level properties and quantities
  from published models, spot-checked against Civil 3D's own reports before any figure is trusted.
- **Design Automation (REST, later)** → `apex_systems_blacksmith`: headless drawing/report jobs in the
  cloud. Separate build-out with its own validation gate; not part of this connector's gate.

## Governance boundaries

- APS `client_id`/`client_secret` live only in the runtime's env/secret store. They never appear in chat,
  in this repository, or in any agent-readable durable record.
- Employer/client BIM 360/ACC hubs are employer/client data: no connection to them without explicit
  task-level authorization. All validation runs against a personally owned APS app and sandbox hub with
  test models or copies only.
- Read-only first: two-legged auth with `data:read`/`viewables:read` scopes. Any write scope falls under
  the one-designated-writer rule, with the writer lease held by Agent 007 until the connector is
  validated.

## Validation gate (registry requirement)

The registry entry stays `candidate` until every step below has recorded evidence:

1. APS app created at aps.autodesk.com; credentials placed in the local env store (never chat).
2. Two-legged token obtained via `@aps_sdk/authentication`.
3. `data-management`: list hubs/projects/folders/items on the sandbox hub; readback matches the UI.
4. `oss` upload of a test Civil 3D model and a `model-derivative` translate job completing.
5. Element properties/quantities pulled via `model-derivative` and spot-checked against
   Civil 3D-reported values.
6. Only after 1–5: decide the Design Automation REST build-out and any employer-hub connection — each
   gated separately with explicit task-level instruction.

## Rollback

Remove the connector configuration and revoke/delete the APS app credentials at aps.autodesk.com. The
connector holds no persistent state in this repository; sandbox buckets and test derivatives can be
deleted from the APS account.
