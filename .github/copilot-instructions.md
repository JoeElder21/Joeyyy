# GitHub Copilot runtime adapter

This file is a thin runtime adapter. The canonical cross-runtime repository policy is the **JOEYYY Global Agent Engineering Constitution** in the repository-root [`AGENTS.md`](../AGENTS.md). Read it first and follow it; nothing in this file may amend, restate, or supersede it.

Copilot specific guidance:

- Repository validation requires Python 3.11 or 3.12. Before committing, validate all TOML files and run the validation surface listed in the `AGENTS.md` Repository Operating Annex (`scripts/privacy_guard.py`, `scripts/validate_specialist_corps.py`, `python -m unittest discover -s tests -v`).
- Develop on a task branch and open a pull request; never write directly to the default branch.
- This repository is public. Never commit credentials, connector identifiers, private facts, or employer/client source records.
- Propose policy changes as isolated edits to `AGENTS.md`, separate from behavior changes. Do not copy policy text into this file.
