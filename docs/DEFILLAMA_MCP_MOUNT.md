# DefiLlama MCP Mount — 2026-09-14

Registration record for the `defillama` mount in `config/mcp_mounts.toml`: what
it is, why it is shaped the way it is, who may hold it, what is verified, and
how to take it back out.

---

## What this mount is

DefiLlama's hosted MCP server (`https://mcp.defillama.com/mcp`), exposing DeFi
analytics — TVL, yields, token prices, protocol fees and revenue, stablecoin
supply, bridge and ETF flows, hacks, fundraises, treasuries, institutional
holdings. Every tool is a read.

Source of the setup instructions: `DefiLlama/defillama-skills`,
`defillama-setup/SKILL.md`, read on 2026-09-14.

## Why it mounts through a bridge

`scripts/verify_mcp_mounts.py` probes a mount with
`StdioServerParameters(command=mount["command"])`. The registry has **no
transport or URL field** — it is stdio-only. A remote HTTP server therefore
cannot be registered directly, and the honest options were to extend the
registry schema or to bridge.

Bridging was chosen because DefiLlama documents `mcp-remote` as the supported
path for stdio-only clients, and because extending the schema to carry an HTTP
transport would change how *every* mount is launched and verified — a larger
blast radius than this one connector justifies. If a second remote HTTP server
is ever registered, revisit that trade.

The consequence is recorded rather than hidden: the mount's `command` carries a
URL, which is the only thing in the registry that looks like an HTTP endpoint.

## Pinning

`mcp-remote@0.14.2`, pinned for the reason already recorded on the `filesystem`
mount: `npx -y <pkg>` with no version runs whatever the npm registry serves at
launch, so an unchanged commit could execute different code on every CI run and
on the workstation. That is the FakeGit-class exposure from
`docs/FRONTIER_REPO_SCAN_2026-07-24.md`, applied to a package this repository
launches deliberately. Bumping the pin is a reviewed change.

## Who may hold it

`agents = ["apex_chief_of_staff"]`.

`[lifecycle] connector_stages = ["active", "value-proven"]`, and all ten
specialists are `shadow` as of this writing (`MissionRunner.promotion_status()`
reports 0 of 39 modes covered). `market-operator` is the natural consumer of
this data and **cannot hold this mount** until it is promoted. Agent 007 holds
it and passes evidence to specialists inside validated packets, which is the
same posture the `terraform` and `azure` mounts already take and is what
`connector_policy = "packet_only_no_direct_connectors"` requires regardless.

## Grant scope, stated honestly

Every tool is a read, so the mount cannot mutate a protocol, a position, or
anything else. That is not a reason to skip the grant. What a signed grant
actually hands over:

- the whole tool surface, not a chosen subset — the launcher does not narrow a
  grant to the operation Joe had in mind when signing;
- the subscription's API credits and the ability to spend them;
- whatever the authenticated DefiLlama account can reach, since `mcp-remote`
  holds a bearer token for it.

## Verification status

`verify_offline = false`. The server requires OAuth, so it cannot be launched
and listed without credentials, and `scripts/verify_mcp_mounts.py` reports it as
**registered, not verified** — with its activation requirement — which is the
correct and intended outcome. It must never be reported as working on the
strength of registration alone.

What *was* verified on 2026-09-14, in the session that added this mount:

| Check | Result |
| --- | --- |
| Endpoint reachable | `POST https://mcp.defillama.com/mcp` (`initialize`) → **HTTP 401** — alive, refusing unauthenticated calls |
| `mcp-remote@0.14.2` exists on the npm registry | confirmed via `registry.npmjs.org/mcp-remote/latest` |
| Registry still parses and passes its gate | `python scripts/verify_mcp_mounts.py` → `"defillama": "registered"`, `valid: true` |

The tool contract in `expected_tools` is **declared, not yet observed**. It
becomes enforceable the first time the mount is probed with a live credential.

## Activation

1. An active DefiLlama API subscription — https://defillama.com/subscribe.
2. On Joe's machine: `claude mcp add defillama --transport http https://mcp.defillama.com/mcp`
3. `/mcp` → DefiLlama → Authenticate → log in.

No API key, no environment variable: the token lives in `mcp-remote`'s own
store and refreshes every 24 hours. That is why this mount declares no `env`,
and it is also why the credential never lands in this public repository.

A lapsed subscription surfaces at the next token refresh, not at mount time.

## Rollback

Delete the `[[mounts]]` block named `defillama` from
`config/mcp_mounts.toml` and delete this file. Nothing else reads either. The
mount has no credential in the repository and no stored state, so removal is
complete — `PolicyEnforcementPoint._registered_mounts()` re-reads the registry
per call and stops admitting the connector on the next call, which is the
emergency-revocation path `tests/test_policy_enforcement.py` already exercises.

## Open items

- **Not verified against a live credential.** Until it is, `expected_tools` is
  a declaration. The first authenticated probe is what turns it into a gate.
- **`market-operator` cannot use it yet.** Promotion out of `shadow` is the
  blocker, per `docs/PROMOTION_CHECKLISTS.md`.
- **Nothing here is investment advice.** DefiLlama data is analysis input for
  Joe's review. The Market Operator recommends and never trades; this mount
  does not change that and adds no execution path.
