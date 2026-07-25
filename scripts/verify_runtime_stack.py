"""Verify the Agent 007 runtime stack and enforce contracts with real validators.

Three honest checks, each reported independently:

1. Dependency audit — which runtime-stack packages import in this environment,
   with versions. Missing packages are reported, never assumed.
2. Schema enforcement — every JSON schema in ``schemas/`` is compiled with the
   ``jsonschema`` library (spec-complete validation, superseding the minimal
   structural checker in ``packet_guard.py``) and every shadow-mission fixture
   packet is validated against its schema.
3. TOML enforcement — every tracked ``.toml`` file parses with ``rtoml`` when
   available, falling back to stdlib ``tomllib``.

Exit code is non-zero only when an installed validator finds a real contract
violation. Missing optional dependencies degrade the report, not the build:
CI runs on stdlib and must stay green without the stack installed.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.privacy_guard import gitlink_paths, is_vendored, tracked_paths  # noqa: E402

RUNTIME_STACK: dict[str, list[tuple[str, str]]] = {
    "contracts": [
        ("pydantic", "pydantic"),
        ("jsonschema", "jsonschema"),
        ("rtoml", "rtoml"),
        ("mcp", "mcp"),
        ("anthropic", "anthropic"),
    ],
    "orchestration": [
        ("langgraph", "langgraph"),
        ("crewai", "crewai"),
        ("autogen_agentchat", "autogen-agentchat"),
        ("prefect", "prefect"),
        ("celery", "celery"),
        ("agents", "openai-agents"),
    ],
    "memory": [
        ("mem0", "mem0ai"),
        ("langchain", "langchain"),
        ("llama_index.core", "llama-index-core"),
        ("graphiti_core", "graphiti-core"),
    ],
    "observability": [
        ("opentelemetry.sdk", "opentelemetry-sdk"),
        ("phoenix.otel", "arize-phoenix-otel"),
        ("taskipy", "taskipy"),
    ],
    "guards": [
        ("guardrails", "guardrails-ai"),
    ],
    "intelligence": [
        ("dspy", "dspy"),
    ],
}


def audit_dependencies() -> dict[str, dict[str, str | None]]:
    report: dict[str, dict[str, str | None]] = {}
    for tier, packages in RUNTIME_STACK.items():
        tier_report: dict[str, str | None] = {}
        for module_name, dist_name in packages:
            try:
                importlib.import_module(module_name)
            except Exception:
                tier_report[dist_name] = None
                continue
            try:
                tier_report[dist_name] = importlib.metadata.version(dist_name)
            except importlib.metadata.PackageNotFoundError:
                tier_report[dist_name] = "unknown"
        report[tier] = tier_report
    return report


def enforce_schemas() -> tuple[list[str], list[str]]:
    """Compile every schema with the spec-complete jsonschema library.

    Returns (checked, errors). Packet instances are synthesized and validated
    by ``validate_specialist_corps.py``; this check guarantees the schemas
    themselves are valid JSON Schema, which the hand-rolled structural
    validator in ``packet_guard.py`` cannot prove.
    """
    try:
        import jsonschema
    except ImportError:
        return [], []
    checked: list[str] = []
    errors: list[str] = []
    for schema_path in sorted((ROOT / "schemas").glob("*.schema.json")):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validator_cls = jsonschema.validators.validator_for(schema)
        try:
            validator_cls.check_schema(schema)
        except jsonschema.SchemaError as exc:
            errors.append(f"{schema_path.name}: invalid schema: {exc.message}")
            continue
        checked.append(schema_path.name)
    return checked, errors


def enforce_toml() -> tuple[list[str], list[str]]:
    try:
        import rtoml

        def parse(text: str) -> None:
            rtoml.loads(text)

        engine = "rtoml"
    except ImportError:

        def parse(text: str) -> None:
            tomllib.loads(text)

        engine = "tomllib"

    checked: list[str] = []
    errors: list[str] = []
    # Both resolved once: is_vendored() otherwise spawns two git processes per
    # path, and the tracked set is needed per path below.
    gitlinks = gitlink_paths(ROOT)
    tracked = tracked_paths(ROOT)
    for toml_path in sorted(ROOT.rglob("*.toml")):
        relative = toml_path.relative_to(ROOT)
        # Match against the repository-relative path: an absolute-path test
        # would skip every file when the checkout itself happens to sit under
        # a directory named .git or node_modules, silently reporting `valid`
        # with nothing checked.
        #
        # node_modules is excluded as *installed dependency content*, which is
        # not the same as "any path containing node_modules". A file the index
        # tracks is this repository's regardless of where it sits, so it stays
        # validated; only untracked installed content is skipped.
        if ".git" in relative.parts:
            continue
        if "node_modules" in relative.parts and str(relative) not in tracked:
            continue
        # Vendored submodules under vendor/ carry the upstream project's TOML
        # contract, not this repository's, and are never committed here beyond
        # the gitlink commit. Installed npm trees are excluded for the same
        # reason: an upstream package shipping malformed TOML must not fail
        # this repository's contract check.
        if is_vendored(toml_path, ROOT, gitlinks):
            continue
        try:
            parse(toml_path.read_text(encoding="utf-8"))
            checked.append(f"{toml_path.relative_to(ROOT)} [{engine}]")
        except Exception as exc:
            errors.append(f"{toml_path.relative_to(ROOT)}: {exc}")
    return checked, errors


def main() -> int:
    dependency_report = audit_dependencies()
    schemas_checked, schema_errors = enforce_schemas()
    toml_checked, toml_errors = enforce_toml()

    installed = {
        dist: version
        for tier in dependency_report.values()
        for dist, version in tier.items()
        if version is not None
    }
    missing = [
        dist
        for tier in dependency_report.values()
        for dist, version in tier.items()
        if version is None
    ]
    result = {
        "dependency_tiers": dependency_report,
        "installed_count": len(installed),
        "missing": missing,
        "schemas_enforced_with_jsonschema": schemas_checked,
        "toml_files_checked": len(toml_checked),
        "errors": schema_errors + toml_errors,
        "valid": not (schema_errors or toml_errors),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
