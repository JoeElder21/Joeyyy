"""Command line for the terminal package.

    python -m terminal.cli dry-run --inputs terminal/fixtures/synthetic_inputs.json --store /tmp/run
    python -m terminal.cli migrate --html legacy.html --store /tmp/store
    python -m terminal.cli render --store /tmp/store --out page.html
    python -m terminal.cli verify --store /tmp/store
    python -m terminal.cli write-plan --store /tmp/store --out plan.json

Every command is read-only with respect to brokers, wallets and the live
artifact: the only things written are files under the directories named.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from terminal import legacy, pipeline, render, runs, schema
from terminal import store as store_mod


def _all_docs(store: store_mod.MemoryStore) -> dict[str, dict]:
    return {path: store.get(path) for path in store.paths()}


def cmd_dry_run(args: argparse.Namespace) -> int:
    inputs = json.loads(Path(args.inputs).read_text(encoding="utf-8"))
    if args.inject:
        inputs["inject"] = args.inject
    if args.now:
        inputs["now"] = args.now
    store = store_mod.JsonDirStore(Path(args.store))
    result = pipeline.run(inputs, store)
    report = result.as_dict()
    Path(args.store, "run_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    if args.render:
        Path(args.render).write_text(render.render(_all_docs(store)), encoding="utf-8")
    print(
        json.dumps(
            {"status": result.status, "stages": report["stages"], "gates": report["gates"]},
            indent=1,
        )
    )
    return 0 if result.status in ("PUBLISHED", "SKIPPED") else 2


def cmd_migrate(args: argparse.Namespace) -> int:
    html = Path(args.html).read_text(encoding="utf-8")
    now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(UTC)
    docs = legacy.migrate(html, now)
    store = store_mod.JsonDirStore(Path(args.store))
    for path, doc in docs.items():
        store.set(path, doc)
    sizes = {path: store_mod.doc_bytes(doc) for path, doc in docs.items()}
    print(
        json.dumps(
            {
                "documents": len(docs),
                "bytes": sum(sizes.values()),
                "largest": sorted(sizes.items(), key=lambda kv: -kv[1])[:5],
            },
            indent=1,
        )
    )
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    store = store_mod.JsonDirStore(Path(args.store))
    page = render.render(_all_docs(store), title=args.title or render.TITLE)
    Path(args.out).write_text(page, encoding="utf-8")
    print(json.dumps({"bytes": len(page.encode("utf-8")), "documents": len(store.paths())}))
    return 0


def verify_store(store: store_mod.MemoryStore) -> dict:
    docs = _all_docs(store)
    errors: list[str] = []
    for path, doc in docs.items():
        collection = path.split("/")[0]
        name = pipeline.SCHEMA_BY_COLLECTION.get(collection)
        if name is None or path in pipeline.UNSCHEMAED_DOCS:
            continue
        errors += [f"{path}: {e}" for e in schema.validate(doc, schema.load_schema(name))]
    for path, doc in docs.items():
        if path.startswith("recommendations/"):
            body = {k: v for k, v in doc.items() if k != "content_sha"}
            if runs.sha256_of(body) != doc.get("content_sha"):
                errors.append(f"{path}: content hash does not match the document")
    records = [doc for _, doc in store.list("runs") if "idempotency_key" in doc]
    records.sort(key=lambda d: d.get("started_at", ""))
    chain = runs.verify_chain(records)
    legacy_chain = docs.get("runs/legacy-chain")
    return {
        "documents": len(docs),
        "schema_errors": errors,
        "chain": {
            "ok": chain.ok,
            "length": chain.length,
            "breaks": chain.breaks,
            "duplicates": chain.duplicates,
        },
        "legacy_chain_ok": legacy_chain.get("chain_ok") if legacy_chain else None,
        "ok": not errors and chain.ok,
    }


def cmd_verify(args: argparse.Namespace) -> int:
    report = verify_store(store_mod.JsonDirStore(Path(args.store)))
    print(json.dumps(report, indent=1))
    return 0 if report["ok"] else 1


def cmd_write_plan(args: argparse.Namespace) -> int:
    store = store_mod.JsonDirStore(Path(args.store))
    plan = store_mod.write_plan(_all_docs(store))
    Path(args.out).write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"batches": len(plan), "writes": sum(len(b) for b in plan)}))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="terminal", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("dry-run", help="run the pipeline on fixture inputs")
    p.add_argument("--inputs", required=True)
    p.add_argument("--store", required=True)
    p.add_argument("--inject", choices=pipeline.INJECTIONS)
    p.add_argument("--now")
    p.add_argument("--render")
    p.set_defaults(func=cmd_dry_run)
    p = sub.add_parser("migrate", help="read a legacy page into a store directory")
    p.add_argument("--html", required=True)
    p.add_argument("--store", required=True)
    p.add_argument("--now")
    p.set_defaults(func=cmd_migrate)
    p = sub.add_parser("render", help="render the page from a store directory")
    p.add_argument("--store", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--title")
    p.set_defaults(func=cmd_render)
    p = sub.add_parser("verify", help="validate every document and the run chain")
    p.add_argument("--store", required=True)
    p.set_defaults(func=cmd_verify)
    p = sub.add_parser("write-plan", help="batches of artifact-db writes for a store")
    p.add_argument("--store", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_write_plan)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
