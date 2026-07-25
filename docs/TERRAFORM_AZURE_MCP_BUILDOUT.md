# Terraform and Azure MCP Build-Out

Registers infrastructure-as-code and cloud-resource tooling as approved MCP
mounts, under the same `packet_only_no_direct_connectors` policy as every other
tool. Both are **registered, not active** — nothing reaches Azure or Terraform
until Joe activates it.

Origin: the `task-planner` Copilot agent in the awesome-copilot collection
declares `terraform`, `Microsoft Docs`, and `azure_get_schema_for_Bicep` in its
tool list. It was held out of the install (see `.github/AWESOME-COPILOT.md`)
because those tools had no home in this repository. This build-out gives them
one.

## Mounts

Both are appended to `config/mcp_mounts.toml`, which is the executable form of
the connector policy: a specialist's entire tool surface is the servers mounted
for it there, and anything unlisted is unreachable.

| Mount | Server | Transport |
|---|---|---|
| `terraform` | `hashicorp/terraform-mcp-server:1.1.0` (official HashiCorp) | stdio via Docker |
| `azure` | `@azure/mcp@latest server start` (official Microsoft) | stdio via npx |

Commands were taken from each project's own README, not inferred.

### terraform

```toml
command = ["docker", "run", "-i", "--rm", "hashicorp/terraform-mcp-server:1.1.0"]
```

Two tiers of capability in one server:

- **Registry lookup** — `search_providers`, `get_provider_details`, and
  siblings. Public Terraform registry data; no credential required.
- **Workspace operations** — `list_workspaces` and siblings against Terraform
  Enterprise / HCP Terraform. Requires `TFE_TOKEN` and `TFE_ADDRESS`.

The image tag is pinned. `latest` would let the tool surface change under the
governance contract without a commit, which the connector policy exists to
prevent.

### azure

```toml
command = ["npx", "-y", "@azure/mcp@latest", "server", "start"]
```

Authenticates through the Azure Identity SDK's `DefaultAzureCredential` — `az
login` interactively on Joe's machine, or `AZURE_TENANT_ID` /
`AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` for headless use. The server never
holds tokens itself.

## Activation control

Both carry `require_grant = true`, so `scripts/trusted_launcher.py` refuses to
start them without a Joe-signed, single-use, short-lived, mount-specific grant.
Verified fail-closed:

```
$ python scripts/trusted_launcher.py launch --mount terraform --dry-run
{"authorized": false, "error": "launch of 'terraform' denied: write-capable mount requires a signed one-time grant"}

$ python scripts/trusted_launcher.py launch --mount azure --dry-run
{"authorized": false, "error": "launch of 'azure' denied: write-capable mount requires a signed one-time grant"}
```

To activate, on the machine that will run the mount:

```bash
python scripts/trusted_launcher.py grant --mount terraform --minutes 30
python scripts/trusted_launcher.py launch --mount terraform --grant <grant-file>
```

Every authorization and denial appends to the hash-chained ledger at
`audit/launcher.jsonl`. That ledger is machine-local and gitignored — it is
runtime evidence, not source, and publishing it from a public repository would
leak operational activity.

## Brain locking

Both mounts are APEX-only:

```toml
agents = ["apex_systems_blacksmith", "apex_delivery_commander", "apex_chief_of_staff"]
```

- `apex_systems_blacksmith` — Systems / automation. The IaC owner.
- `apex_delivery_commander` — Execution / capacity. Deployment execution.
- `apex_chief_of_staff` — Agent 007, sole write-capable native agent and integrator.

This mirrors the existing `civil3d` assignment, the closest analogue already in
the registry (infrastructure tooling, workstation-activated).

No JEOS specialist gets either mount. Cloud infrastructure is professional
context, which APEX owns; granting it to the personal brain would breach the
brain lock. `tests/test_orchestration.py::McpMountRegistryTests::test_infrastructure_mounts_are_apex_locked_and_grant_gated`
enforces both properties — grant-gated, and no `jeos_*` agent — so a later edit
cannot quietly widen the surface.

## Verification

```
$ python scripts/verify_mcp_mounts.py
  terraform -> status "registered", activation recorded
  azure     -> status "registered", activation recorded
  valid: true
```

`verify_offline = false` for both: neither can be probed in-container (no Docker
daemon, no credentials), so the audit reports them as *registered with an
activation requirement* and never as working. That is the honest state.

Full suite green: 243 tests.

## Known gap

`task-planner` also declares a `Microsoft Docs` tool. That is the Microsoft
Learn MCP server, which is remote-HTTP-only; `scripts/verify_mcp_mounts.py` and
`scripts/trusted_launcher.py` both speak stdio exclusively. Registering it would
mean adding an HTTP transport path to the launcher and the audit, which is a
larger change than this build-out and has not been made. The agent degrades
without it — it loses documentation lookup, not planning.

## Rollback

Remove the `terraform` and `azure` blocks from `config/mcp_mounts.toml`, drop
the two `assertIn` lines and the `test_infrastructure_mounts_are_apex_locked_and_grant_gated`
test from `tests/test_orchestration.py`, delete
`.github/agents/task-planner.agent.md`, revert the `audit/*.jsonl` rule in
`.gitignore`, and delete this document.
