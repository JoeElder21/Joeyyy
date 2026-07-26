# skill-up integration

## Placement in the command center

`skill-up` is a bounded Agent 007 governance workflow for evaluating Agent
Skills and proposing evidence-led improvements. It is not a new agent, a
background self-modifier, or a direct bridge between APEX and JEOS. Agent 007
owns suite selection and terminal integration; APEX and JEOS evaluations run
as separate suites with separate private evidence stores. A passing suite does
not activate or promote a Skill.

## Provenance and installation

The integration pins Alibaba `skill-up` release `v0.7.0`, source commit
`5ac7ce0467a164d07aacbbf7052bcffda68a446b`, under Apache-2.0. The Linux AMD64
release archive is verified against upstream SHA-256
`8b5f24e2d585e1f4513720f1f1542a462526c033f218d0c4998c445fe47b55e3`;
the installer also pins the published Linux ARM64 and macOS checksums.

```bash
scripts/install_skill_up.sh
scripts/skill_up.sh validate
scripts/skill_up.sh list
scripts/skill_up.sh run
```

The upstream `skill-upper` prompt was reviewed but not copied wholesale. The
repository adapter removes moving-version auto-installation, credential
prompts, self-directed mutation, and any suggestion that evaluation proves
promotion. Reports default to `.state/skill-up`, which Git ignores because
reports can contain prompts, transcripts, file paths, generated workspaces,
and model output.

## Evaluation and evolution contract

Evaluation uses declarative YAML cases, one explicit engine, and deterministic
rule or script judges wherever possible. Built-in Claude Code and Codex engines
may be selected only in an approved environment. Custom `local` and `http`
engines remain untrusted boundaries: input files/uploads must be explicit,
secrets must use approved environment resolution, results and artifact paths
must be bounded, and private reports remain outside public Git.

Evolution is a reviewed loop:

`MEASURE → DIAGNOSE → PROPOSE SMALLEST REPAIR → ADD REGRESSION → RERUN → INDEPENDENT REVIEW`

It may improve a Skill implementation or eval suite within the mission's
authority. It may not change identity, brain, permissions, lifecycle,
thresholds, governing tests, or production behavior without their separate
gates. Agent judges are supporting evidence, never sole approval.

The committed three-case suite is a controlled, credential-free synthetic
mission. It verifies that the installed `v0.7.0` binary can validate, execute a
custom local `SessionInput`/`SessionResult` engine, apply rule judges, and write
structured reports while preserving the declared APEX, JEOS, and evolution
constraints. It does not qualify Claude, Codex, live-model judging, private
brain data, HTTP transport, longitudinal value, or a production lifecycle.

## Google Drive

The supplied Drive folder URL identifies a desired destination but does not
provide a callable Drive connector, authenticated account, canonical subfolder,
privacy classification, retention rule, or readback interface in this session.
No Drive mutation is therefore performed or claimed. When those controls are
verified, the permitted direction is repository public-safe runbook → a
sanitized Drive reference record, plus brain-specific private reports → their
separate authorized private folders. Never upload credentials, mixed-brain
reports, raw transcripts, or a second editable copy of governance.

## Rollback

Uninstall the machine binary with `rm "$(command -v skill-up)"` after verifying
the path, revert the integration commit, remove machine-local `.state/skill-up`
reports subject to evidence retention, and rerun the full repository validation
surface. No remote service or schedule needs demotion because none is created.
