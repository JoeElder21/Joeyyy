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
| `terraform` | `hashicorp/terraform-mcp-server` pinned by digest (official HashiCorp) | stdio via Docker |
| `azure` | `@azure/mcp@2.0.5 server start` (official Microsoft) | stdio via npx |

Commands were taken from each project's own README, not inferred.

### terraform

```toml
command = ["docker", "run", "-i", "--rm", "-e", "TFE_TOKEN", "-e", "TFE_ADDRESS",
           "hashicorp/terraform-mcp-server:1.1.0@sha256:312d63756b5474df384b1844af55b58ca48cbe0996871e1d6c4239bfcd6fcd29"]
```

The bare `-e NAME` form forwards a variable from the launcher's environment into the
container without writing any value into this file. Without it the credentials would sit
only in the host-side Docker client's environment and the workspace tools could not
authenticate -- registry lookup would work and TFE calls would fail.

Two tiers of capability in one server:

- **Registry lookup** — `search_providers`, `get_provider_details`, and
  siblings. Public Terraform registry data; no credential required.
- **Workspace operations** — `list_workspaces` and siblings against Terraform
  Enterprise / HCP Terraform. Requires `TFE_TOKEN` and `TFE_ADDRESS`.

The image is pinned **by digest**, not merely by tag. A tag is mutable -- it can
be repointed at different bytes without the version string changing -- so a tag
alone would still let the tool surface move under the governance contract with no
commit here. `test_container_images_are_pinned_by_digest` enforces the digest
form. Copy this command verbatim during a rebuild or rollback; restoring the bare
tag silently drops the guarantee and fails that test.

### azure

```toml
command = ["npx", "-y", "@azure/mcp@2.0.5", "server", "start"]
```

Pinned to an exact version. `@latest` was rejected in review: `npx` resolves package
selection as `<pkg>[@<version>]`, so a floating tag lets each activation download
different code holding cloud-management privileges. At the time of pinning `latest`
resolved to `3.0.0-beta.29` -- a prerelease -- which made the risk concrete rather than
theoretical. `2.0.5` was the current stable release.
`tests/test_orchestration.py::test_mount_commands_pin_immutable_versions` now fails on any
floating tag in this registry.

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
python scripts/trusted_launcher.py grant --mount terraform --minutes 30 \
    --agent apex_chief_of_staff
python scripts/trusted_launcher.py launch --mount terraform --grant <grant-file>
```

**The authorized identity is signed into the grant**, not passed at launch. Two review
rounds shaped this:

1. `agents` was inert — `authorize()` never read it, so narrowing this mount to Agent 007
   changed no runtime decision at all.
2. The first fix took the identity from a `--agent` flag at launch, which any holder of a
   valid grant could set to anything. It authenticated nothing.

Now `--agent` is supplied when *minting* the grant, which only Joe's machine can do, and it
becomes part of the HMAC payload. `issue_grant` refuses an identity that is not on the
mount's allowlist, so a grant for a shadow specialist cannot be created in the first place;
editing the field afterwards breaks the signature. Passing `--agent` at launch is an
optional cross-check and a mismatch is refused.

This applies to **every** agent-scoped mount, including the pre-existing `civil3d`, whose
grant command now needs `--agent`. Mounts declaring `agents = ["*"]` are unaffected, and a
test enforces that every agent-scoped mount also requires a grant — otherwise its identity
would fall back to an unauthenticated value.

Every authorization and denial appends to the hash-chained ledger at
`audit/launcher.jsonl`. That ledger is machine-local and gitignored — it is
runtime evidence, not source, and publishing it from a public repository would
leak operational activity.

## Brain locking

Both mounts are Agent 007 only:

```toml
agents = ["apex_chief_of_staff"]
```

An earlier version also listed `apex_systems_blacksmith` and `apex_delivery_commander`,
mirroring the `civil3d` assignment. Review caught the problem: every APEX specialist is
still lifecycle stage `shadow`, and the contract makes Agent 007 the sole executor of
mutations while they are. Listing a shadow specialist on a mutation-capable cloud
management server hands it authority beyond its read-only / proposed-write remit,
regardless of the `civil3d` precedent. Widen this only alongside a lifecycle promotion, or
by exposing a separately constrained read-only surface.

No JEOS specialist gets either mount. Cloud infrastructure is professional
context, which APEX owns; granting it to the personal brain would breach the
brain lock. `tests/test_orchestration.py::McpMountRegistryTests::test_infrastructure_mounts_are_apex_locked_and_grant_gated`
enforces all three properties — grant-gated, `apex_chief_of_staff` alone, and no `jeos_*`
agent — so a later edit cannot quietly widen the surface.

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

Full suite green; see the PR for the current count.

## Known gaps

**These mounts serve Agent 007, not Copilot custom agents.** This registry is consumed only
by `scripts/trusted_launcher.py` and `scripts/verify_mcp_mounts.py`, and it authorizes
native APEX agent IDs. GitHub Copilot reads a different configuration entirely. So
registering these mounts does *not* make the `terraform` or `azure_get_schema_for_Bicep`
tool names declared by `.github/agents/task-planner.agent.md` reachable in a collaborator
Copilot session — per the installed agent standard, unrecognized tool names are silently
ignored there. Closing that gap means adding repository-level Copilot MCP wiring with valid
tool identifiers; it is an open decision, not done here. Both agents are registered as
`candidate` in `docs/AGENT_REGISTRY.md` for exactly this reason.

**`Microsoft Docs` has no stdio path.** `task-planner` and `task-researcher` both declare
it. It is the Microsoft Learn MCP server, remote-HTTP-only, and both the launcher and the
mount verifier speak stdio exclusively. Registering it would mean adding an HTTP transport
to the launcher and the audit ledger — a larger change than this build-out. The agents
degrade without it: they lose documentation lookup, not planning.

## Rollback

Removing the mounts alone leaves a tree that neither builds a coherent manifest nor passes its own
tests, so do all of it:

1. `config/mcp_mounts.toml` — delete the `terraform` and `azure` blocks.
2. `tests/test_orchestration.py` — drop the two `assertIn` lines and
   `test_infrastructure_mounts_are_apex_locked_and_grant_gated`. Keep
   `test_mount_commands_pin_immutable_versions`; it is not specific to these mounts.
3. `.github/agents/` — delete `task-planner.agent.md` and `task-researcher.agent.md`.
4. `.github/instructions/task-implementation.instructions.md` — delete it; nothing else loads it.
5. `.github/AWESOME-COPILOT.md` — remove the planner rows from the agents table, the
   `task-implementation` row from the instructions table, and the `task-planner` capability-limits
   section.
6. `docs/AGENT_REGISTRY.md` — remove the `task-planner` and `task-researcher` rows and their
   lifecycle note from the vendored-agents section.
7. `scripts/build_awesome_copilot_report.py` — remove the two planner rows from the agents table
   and the `task-implementation` row from the instructions table. The inventory counts derive from
   the tree, so they correct themselves.
8. `tests/test_agent_contract.py` — remove **all three** planner-dependent tests, each of which
   opens a deleted file and errors with `FileNotFoundError` otherwise, so the mandated full gate
   could not pass: `test_vendored_agent_file_dependencies_exist`,
   `test_planner_can_actually_invoke_its_researcher`, and
   `test_planner_instructions_invoke_rather_than_load_the_researcher`. An earlier version of this
   list named only the first.
9. `tests/test_trusted_launcher.py` — the allowlist and signed-identity tests reference
   `terraform` and `azure`; repoint them at `civil3d`, which is also agent-scoped and grant-gated,
   rather than deleting the coverage.
10. Delete this document.

**Keep the `audit/*.jsonl` rule in `.gitignore`,** and keep the launcher's identity enforcement.
An earlier version of this section said to revert the ignore rule; that was wrong and was caught
in review. The pre-existing trusted launcher and the `civil3d` mount both write that ledger, so
removing Terraform and Azure does not remove the producer, and reverting the rule during an
unrelated rollback would expose machine-local authorization history. The signed-identity change is
likewise independent of these two mounts and protects `civil3d` as well.

Then run the full gate: `privacy_guard.py`, `validate_specialist_corps.py`,
`verify_runtime_stack.py`, `verify_mcp_mounts.py`, and
`python -m unittest discover -s tests`.
