# APS Connector — Validation-Gate Harness

Runs steps 2–5 of the six-step validation gate defined in `docs/APS_SDK_BUILDOUT.md` against the
official `@aps_sdk` Node.js packages. The connector stays `candidate` in `docs/AGENT_REGISTRY.md`
until every step has recorded evidence.

## Prerequisite — gate step 1 (human step, cannot be automated)

Create an APS app at https://aps.autodesk.com (Applications → Create Application, type
"Traditional Web App" or "Server-to-Server"; enable the Data Management, Model Derivative, and
Data Exchange APIs), then export its credentials in the shell that runs the gate:

```
export APS_CLIENT_ID=...      # never commit, never paste into chat
export APS_CLIENT_SECRET=...
```

Credentials are read only from the environment. The runner fails closed with exit code 2 when they
are absent, before any network call.

## Running the gate

```
npm install
npm run gate            # steps 2..5 in order, stops on first failure
npm run gate:auth       # step 2 only: two-legged token
npm run gate:dm         # step 3 only: hub/project enumeration (read-only)
npm run gate:translate  # step 4 only: OSS upload + Model Derivative translate
npm run gate:properties # step 5 only: element properties vs generator ground truth
```

Evidence for each run is written to `evidence/gate-<timestamp>.json` (gitignored — hub, project,
and file names are private data and must not reach this public repository). Tokens are never
written; only a SHA-256 prefix appears in evidence.

## Test model

`testdata/aps_test_model.dxf` is synthetic (parcel boundary, building pad, easements on named
layers) and is regenerated — never hand-edited — via:

```
pip install ezdxf && python testdata/make_test_model.py
```

The generator validates its own output (entity counts by layer, closed-polyline flags, units) and
step 5 spot-checks the properties APS returns against this same ground truth.

## Scope boundaries

Two-legged auth with `data:read`/`viewables:read`; step 4 additionally uses
`data:write data:create bucket:create bucket:read` against a transient sandbox OSS bucket only.
No employer/client ACC hub is ever touched by this harness; hub access requires explicit
task-level authorization per `docs/APS_SDK_BUILDOUT.md`.
