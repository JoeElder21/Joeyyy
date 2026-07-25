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

Requires **Node >= 22.19.0**. `agent-relay@11.2.0` itself declares `>=22.0.0`,
and five non-optional packages in its locked tree
(`@earendil-works/pi-coding-agent` and its bundled dependencies) require
`>=22.19.0`. The manifest declares the higher floor deliberately: npm reports
engine mismatches as warnings rather than refusing to install, so a lower
declared floor would let the CLI install on Node 20 and fail at runtime.

```bash
npm --prefix connectors/relay install
```

## Promotion condition

Before anything in this repository may route work through relay: a configured
transport boundary, an isolation test against a local relay instance, and a
recorded writer-lease policy for any resource a relayed agent could mutate.
Until then this stays a declaration, consistent with the disposition column in
`docs/EXTERNAL_RUNTIME_REGISTER_2026-07-24.md`.
