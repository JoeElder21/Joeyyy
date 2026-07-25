# Agent Relay — declared dependency

Declares the published Agent Relay CLI/runtime as a dependency of this
repository. **This is a package declaration, not a configured connector.** Per
`AGENTS.md`, a package declaration never grants access: no relay server is
configured, no agent in this repository is wired to a relay transport, and
every specialist remains `packet_only_no_direct_connectors`.

## Provenance

| Field | Value |
| --- | --- |
| Repository | `AgentWorkforce/relay` |
| Vendored at | `vendor/relay`, pinned to tag `v11.2.0` (`cce0cb9`) |
| npm package | `agent-relay` |
| Declared version | `^11.2.0` |
| License | see `vendor/relay/LICENSE` |

Provenance was verified per the FakeGit intake rule in
`docs/FRONTIER_REPO_SCAN_2026-07-24.md`: the npm package `agent-relay`
declares `repository.url = git+https://github.com/AgentWorkforce/relay.git`
with `directory = packages/cli`, and its published `latest` version
(`11.2.0`) matches the `v11.2.0` tag the submodule is pinned to. Registry
linkage and source tag therefore corroborate each other rather than resting
on the repository name alone.

## Why the root monorepo is not the dependency

`vendor/relay` is a Rust + Node workspace whose root `package.json` is
`private: true` and is not installable. Only the CLI workspace is published,
as `agent-relay`. The submodule supplies auditable source at a pinned commit;
this manifest supplies the installable artifact.

## Install

Requires **Node >= 22.22.0**, the highest bound anywhere in the locked tree.
`agent-relay@11.2.0` itself declares only `>=22.0.0`; five bundled packages
under `@earendil-works/pi-coding-agent` require `>=22.19.0`; and
`posthog-node@5.46.1` requires `^20.20.0 || >=22.22.0`, whose 22.x branch is
the binding one here since `agent-relay` already rules out Node 20.

The manifest declares that ceiling deliberately. npm reports engine mismatches
as warnings rather than refusing to install, so an understated floor lets the
CLI install and then fail at runtime. Note that the constraint hid inside a
compound range — a floor derived only from simple `>=x.y.z` declarations comes
out at `22.19.0` and is wrong.

```bash
npm --prefix connectors/relay install --ignore-scripts
```

`--ignore-scripts` is not optional here. npm defaults to `ignore-scripts=false`,
and five packages in the locked tree carry `hasInstallScript` — `cpu-features`,
`ssh2`, `fsevents`, and the bundled `@google/genai` and `protobufjs`. A plain
`npm install` therefore executes upstream lifecycle code on the machine running
it, which contradicts the isolation rule in `vendor/README.md`: upstream code is
untrusted input and must not be executed outside an isolated environment.

Installing script-free is sufficient for what this connector is — a
*declaration*. The dependency resolves and the CLI entry points are present;
nothing here runs the relay. Actually executing the CLI is gated behind the
promotion condition below, and belongs in an isolated environment where those
install scripts can be reviewed and run deliberately.

## Promotion condition

Before anything in this repository may route work through relay: a configured
transport boundary, an isolation test against a local relay instance, and a
recorded writer-lease policy for any resource a relayed agent could mutate.
Until then this stays a declaration, consistent with the disposition column in
`docs/EXTERNAL_RUNTIME_REGISTER_2026-07-24.md`.
