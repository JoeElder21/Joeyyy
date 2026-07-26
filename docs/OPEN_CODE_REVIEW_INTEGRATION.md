# Open Code Review integration

## Status and scope

Open Code Review (OCR) is absorbed here as a bounded **APEX code-review
workflow**, not as a new identity and not as a cross-brain connector. Agent 007
is the top-level integrator and designated writer. OCR performs deterministic
file filtering and rule resolution; either the host Claude/Codex agent reviews
the resulting surface (delegation mode), or OCR calls an explicitly configured
OpenAI- or Anthropic-compatible provider (direct mode).

This integration does not make OCR continuously running, does not install it on
other machines or ChatGPT services, does not configure Google Drive, and does
not grant it access to either brain's private canon. Code review is professional
engineering work owned by APEX. JEOS remains sealed; no review input, output,
session transcript, or raw narrative crosses into it.

## Intake and provenance

| Item | Verified intake state |
| --- | --- |
| Upstream | `alibaba/open-code-review` |
| Release | npm `@alibaba-group/open-code-review@1.7.17` |
| Source commit | `0ced7165718725e15223c3e5a506df7b7e9de51f` (`v1.7.17`) |
| npm integrity | `sha512-3n2wVzE9tRCNBFo+c3yOok+oJOQm7H/c7LbMMB3q6+0U2sJZpygMW3B5JZNdk8Qf9TM2G5WOq6FubRr92vF5yg==` |
| License | Apache-2.0 |
| Runtime requirements | Node.js >=14 and Git >=2.41 |
| Network | npm registry during installation; configured LLM endpoint only in direct review mode |
| State | `~/.opencodereview/`; session transcripts are machine-local and must not enter Git or Drive |
| Telemetry | Upstream default is off; this repository does not enable or configure an exporter |

The source and published package were inspected as untrusted external input.
The upstream skill/plugin was not copied wholesale because it can auto-install
an unpinned latest package and its default workflow may apply fixes. The local
Claude command and Codex-compatible skill instead use the pinned, fail-closed
wrapper and preserve Agent 007 authority.

## Install and verify

```bash
scripts/install_open_code_review.sh
OCR_NO_UPDATE=1 ocr version
scripts/open_code_review.sh preview
```

The installer pins `1.7.17`. `OCR_NO_UPDATE=1` disables the npm wrapper's
background replacement behavior, and every repository invocation verifies the
installed version before continuing.

## Invoke from Agent 007, Claude Code, or Codex

The safe default is delegation mode, which makes no OCR-side LLM request:

```bash
# Workspace selection
scripts/open_code_review.sh preview

# Commit or branch selection
scripts/open_code_review.sh preview --commit <sha>
scripts/open_code_review.sh preview --from <base> --to <head>

# Resolve rules for exactly the selected paths
scripts/open_code_review.sh rules path/to/file.py path/to/other.toml
```

Claude Code can invoke `/open-code-review`; Codex-compatible skill discovery can
load `.agents/skills/open-code-review/SKILL.md`. Both adapters route through the
same wrapper and policy. Availability still depends on the host actually
supporting the respective discovery convention; repository presence alone is
not proof that another console loaded it.

Direct mode supports OpenAI, Anthropic, and custom compatible endpoints through
OCR's upstream provider configuration:

```bash
scripts/open_code_review.sh review --from <base> --to <head>
```

Keep `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or custom-provider credentials only
in an approved environment/provider store. Never commit them or pass them in a
command that will be logged. Direct-mode integration is not verified until
`ocr llm test` and a controlled review execute successfully in that approved
environment.

## Rules and evidence

`.opencodereview/rule.json` adds repository-specific governance checks and
explicitly includes Python tests that OCR otherwise excludes by default. Other
files fall through to OCR's embedded language rules, including its security,
null-safety, concurrency, XSS, and SQL-injection checks where applicable.
Private/runtime evidence paths and vendored source are excluded.

Selection and resolved rules are deterministic evidence. Findings produced by
an LLM remain review judgments and require human/Agent 007 verification before
mutation or publication. No workflow posts pull-request comments or applies
fixes automatically.

## Google Drive boundary

No verified Google Drive connector, target folder, retention policy, or
readback path is available in this environment. Therefore this mission makes no
Drive mutation. If Drive publication is later authorized and connected, publish
only a sanitized installation/runbook record—not credentials, private source,
review transcripts, session JSONL, or independently editable governance—and
read it back from the authoritative Drive target.

## Rollback

1. `npm uninstall --global @alibaba-group/open-code-review`
2. Revert the integration commit to remove `.opencodereview/`, the wrapper and
   installer, both host adapters, this document, and their tests.
3. Optionally remove machine-local OCR state after confirming it contains no
   evidence that must be retained: `rm -rf ~/.opencodereview`.
4. Re-run the repository validation surface.
