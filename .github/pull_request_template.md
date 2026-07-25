## What changed

<!-- One paragraph. What this does and why. -->

## Evidence

<!--
Required by the change standards in AGENTS.md: every persistent improvement must be
evidence-led. Paste command output, test names, or the record document this change
is based on. "Looks right" is not evidence.
-->

## Rollback point

<!-- How this is reverted and what state that restores. Required. -->

## Validation

- [ ] `python scripts/privacy_guard.py`
- [ ] `python scripts/validate_specialist_corps.py`
- [ ] `python scripts/verify_runtime_stack.py`
- [ ] `ruff check .`
- [ ] `python -m unittest discover -s tests -v`

## Boundaries

- [ ] No credentials, connector identifiers, private facts, or employer/client source
      records are added to this public repository.
- [ ] No claim of an available agent, connector, skill, or memory that is not verified.
- [ ] No claim of continuous background agent operation.
- [ ] APEX/JEOS brain separation preserved; cross-brain changes read back into both
      memories with matching evidence.
- [ ] One designated writer per shared resource; writer leases respected.

## Contract changes

<!--
If this touches the agent contract, confirm documentation, templates, registry, and
tests were updated together. Write "n/a" if it does not.
-->
