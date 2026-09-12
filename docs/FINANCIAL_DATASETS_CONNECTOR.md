# Financial Datasets connector — supplying the API key

`.mcp.json` registers the hosted Financial Datasets MCP server at project
scope, so every Claude Code session in this repository discovers it. The
server authenticates with an `X-API-KEY` header whose value Claude Code
expands from the environment at connection time:

```json
"headers": { "X-API-KEY": "${FINANCIAL_DATASETS_API_KEY}" }
```

The key itself is never committed. This document is the operator-facing half
of that design: where the key goes, where it must not go, and how to tell
whether it actually took.

---

## 1. Status

The constitution asks for these as separate dimensions rather than one
"active" label:

| Dimension | Status |
|---|---|
| Configured | Yes — `.mcp.json`, project scope, HTTP transport |
| Endpoint reachable | Verified — `initialize` returns HTTP 200 and the server identifies itself |
| Credentialed | Only where the operator has set `FINANCIAL_DATASETS_API_KEY` |
| Integration verified | **No.** No valid key has been exercised from this repository |

Nothing here claims the connector returns market data. It claims the
transport works and the key is the operator's to supply.

---

## 2. The failure you will see if the key is unset

An unset variable does **not** disable the server. Claude Code loads the
config anyway and sends the *unexpanded* `${FINANCIAL_DATASETS_API_KEY}`
text as the header value, so the handshake succeeds and the connector looks
healthy — the failure only surfaces on a tool call, as ordinary tool text
rather than an error:

```
get_stock_price AAPL
→ Error fetching price data for AAPL: Please provide a valid API key
  from https://financialdatasets.ai
```

The two failing cases are distinct, and both were measured against the live
endpoint:

| `X-API-KEY` sent | `initialize` | Tool call | |
|---|---|---|---|
| header absent | HTTP 401 `{"error":"Missing API key"}` | never reached | measured |
| literal `${FINANCIAL_DATASETS_API_KEY}` | HTTP 200, server info returned | `Please provide a valid API key` | measured |
| a valid key | — | — | **not measured**; see section 1 |

The middle row is what an unset variable produces, and it reproduces the
error above byte for byte. The last row is deliberately blank: no valid key
has been exercised from this repository, so what a good one returns is not
something this document has standing to assert.

**"Connected" does not mean "working key."**

Claude Code does say so, in a place that is easy to miss:

```console
$ claude mcp list
financial-datasets: https://mcp.financialdatasets.ai/api (HTTP) - ⏸ Pending approval

MCP config diagnostics ‼
 └ [Warning] [financial-datasets] mcpServers.financial-datasets:
   Missing environment variables: FINANCIAL_DATASETS_API_KEY
```

That warning is the fastest way to tell an unset variable from a wrong key.

---

## 3. Get a key

Only the account holder can. Create an account at
[financialdatasets.ai](https://financialdatasets.ai) — the address the
server's own error message points at — and copy the API key it issues. It
is a read-only market-data key: it buys nothing,
moves nothing, and can be rotated from the same dashboard at any time. That
is a materially lower privilege class than the Schwab credentials in
[`SCHWAB_TRADING_AGENT.md`](SCHWAB_TRADING_AGENT.md), and worth keeping in
mind when weighing the trade-off in section 5.

Per `AGENTS.md` §10, never paste the key into a chat session, an issue, or a
commit message — including to an agent. A key that reaches a transcript
should be rotated, not reused.

---

## 4. Supply it to a local session

This is the supported path, and both forms keep the key out of the tree.

**Either** export it before launching Claude Code. Read it in rather than
typing it on the command line, so it never reaches your shell history:

```bash
read -rs FINANCIAL_DATASETS_API_KEY && export FINANCIAL_DATASETS_API_KEY
claude
```

To make it persist, set the same variable from your shell profile —
`~/.bashrc`, `~/.zshrc`, or your shell's equivalent. A profile holding the
literal key is a file on your machine like any other: readable by anything
running as you, and worth `chmod 600` if the machine is shared. The variable
must exist in the environment that launches `claude`; setting it inside a
running session is too late for a connection already made.

An assignment of this variable is a finding for `scripts/privacy_guard.py` as
of this change, which is why no such line is spelled out here — see section 6.

**Or** register the server at local scope with the header baked in, which
stores the key in `~/.claude.json` on your machine, outside this repository.
Read it in here too, and pass the variable rather than the value — history
records the line you typed, not what it expanded to, so the key stays out of
it:

```bash
read -rs FD_KEY
claude mcp add --transport http --scope local financial-datasets \
  https://mcp.financialdatasets.ai/api --header "X-API-KEY: $FD_KEY"
unset FD_KEY
```

Typing the key directly into that command instead would put the whole
credential in your shell history, which is a second persistent copy on top of
the one `~/.claude.json` already holds.

Local scope outranks project scope, so this entry wins over `.mcp.json`
without editing it. Use one form or the other, not both.

---

## 5. Cloud sessions: read this before setting anything

A Claude Code web or cloud session runs in a throwaway container that has
none of the above — `~/.claude.json` and your shell profile live on your
machine, and Anthropic's own documentation is explicit that MCP servers
added at local or user scope **do not** carry over to cloud sessions.

The only mechanism a cloud environment offers is its environment-variable
configuration, and Anthropic advises against using it for this:

> Anyone who uses the environment can read the values, and cloud
> environments have no dedicated secrets store, so don't add API keys or
> other credentials.
>
> — [Configure cloud environments](https://code.claude.com/docs/en/cloud-environments#set-environment-variables)

So the honest position is that **this connector is a local-session
capability.** In a cloud session it is unavailable unless the operator
accepts a documented trade-off, which is theirs to make and not an agent's:

- The value is stored and displayed in plaintext, readable by anyone who can
  use that environment and by any command the session runs. In a *personal*
  environment that set is you; in an organization-shared one it is every
  member, which is categorically worse.
- Set against that, the key is read-only, rotatable, and buys nothing.

If you accept it, add one `KEY=value` line to the environment's variables at
[claude.ai/code](https://claude.ai/code). Sessions copy those values once at
startup, so **the session you are in now will not pick it up** — start a new
one. Per `AGENTS.md` §9, a credential change is Joe's call to make.

---

## 6. Where the key must not go

| Location | Why not |
|---|---|
| `.mcp.json` | Tracked and public. `scripts/privacy_guard.py` fails the build on a literal here, and `tests/test_repo_hygiene.py` asserts every header value stays a `${VAR}` reference. A key committed once is published; deleting the line later does not unpublish it, so the only remedy is rotation |
| `.env` | **Silently useless.** Nothing loads it into Claude Code. `.env` in this repository is read by `connectors/schwab/config.py` alone, for the Schwab connector's own settings; MCP header expansion reads the process environment and never opens the file. The key would sit there looking configured while every call failed |
| `.claude/settings.local.json` | Git-ignored as of this change, but it was not before, and Claude Code only auto-ignores it when it writes the file itself. Verify it is ignored before putting anything sensitive in it |
| Any tracked file in this repository | An assignment of `FINANCIAL_DATASETS_API_KEY` is a `scripts/privacy_guard.py` finding as of this change, so the gate fails rather than the key publishing. That is new — see section 8 for what was true before, and for the limits of what the guard covers now |
| Any chat, issue, or commit message | `AGENTS.md` §10. Rotate anything that lands in one |

---

## 7. Verify it took

Two checks, in this order. They fail differently, and only the second is
proof:

| Check | Passes when | Catches |
|---|---|---|
| `claude mcp list` | no `Missing environment variables` line in the diagnostics | the variable is unset, or set in the wrong environment |
| `get_stock_price AAPL`, in a session | a price comes back | the variable expanded but the key is wrong, expired, or revoked |

A clean `claude mcp list` means the reference expanded, not that the key is
good — section 2 is the whole reason those are different questions.

---

## 8. Boundaries

- `config/mcp_mounts.toml` — the trusted-launcher plane — is deliberately
  untouched by this change. That is **not** the same as saying no governed
  agent can reach the connector, and an earlier draft of this section made
  that inference and was wrong. The two planes are separate:

  | Plane | Reads | Reaches this server? |
  |---|---|---|
  | Trusted launcher | `config/mcp_mounts.toml` | No — no entry exists |
  | Claude Code projection | `.claude/agents/*.md` frontmatter | **Agent 007 does.** `scripts/generate_claude_agents.py` grants `CHIEF_TOOLS`, which includes the `mcp__*` wildcard, so any server the session has connected — this one included — is in its surface |

  Specialists are denied that wildcard (`SPECIALIST_TOOLS` in the same
  generator), so the chief remains the only connector holder. The practical
  reading: a Claude Code session with this server configured gives Agent 007
  read-only market data it did not have before, without any mount entry
  recording that. Whether that should be registered and gated in the mount
  policy, or the wildcard narrowed, is a governance decision for Joe under
  `AGENTS.md` §9 — this document records the position rather than changing
  it. `.claude/agents/apex_chief_of_staff.md` is generated; it is not
  hand-editable and is not edited here.
- The connector is read-only market data. It places no orders and holds no
  account identity; it is unrelated to the Schwab connector, which reads
  holdings and is separately credentialed.
- **No key, and no fragment of one, belongs in this repository.** That is the
  policy. What is *mechanically enforced* is narrower than the policy, and the
  difference is worth stating rather than glossing:

  | Written into a tracked file | `privacy_guard.py` |
  |---|---|
  | `FINANCIAL_DATASETS_API_KEY` assigned a value of 8+ characters | **Blocked** — exit 1, `possible credential assignment` |
  | The same name assigned 7 characters or fewer | Passes. The value clause requires 8+, so a short fragment is invisible |
  | Any other `<PREFIX>_API_KEY`, `<PREFIX>_ACCESS_TOKEN`, `<PREFIX>_CLIENT_SECRET` | Passes. `\b` cannot match after `_`, so only the name spelled out in the alternation is covered |

  Measured at the boundary, not reasoned: a 7-character value exits 0 and an
  8-character one exits 1. So the guard is a backstop against the whole-key
  mistake, which is the one that actually leaks a usable credential — not a
  proof that no fragment can land. Treat "no fragment" as a rule you follow,
  not a rule the gate keeps for you.

  This much *is* pinned:
  `tests/test_privacy.py::test_documented_but_unmounted_credential_names_are_detectable`
  fails if the name is dropped from the alternation. None of it was enforced
  when this document was first written — the exact export line this page used
  to print sailed past the guard while the identical value assigned to a bare
  `API_KEY` was caught. Widening the anchor to cover every prefixed name is a
  change to the shared guard, not to this connector, and is left as its own.
