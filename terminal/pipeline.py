"""The daily research workflow as ordered, testable stages.

Each stage is a pure function of the inputs and the store. In production the
analyst stages are filled by the agent roles under ``terminal/agents``; in the
dry run they are filled by fixture inputs, so every calculation downstream of
the research can be exercised without a model, a broker, or the network.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from terminal import (
    clock,
    critic,
    freshness,
    gates,
    identity,
    outcomes,
    runs,
    scenarios,
    schema,
    scorecard,
    universe,
)
from terminal import store as store_mod

INJECTIONS = (
    "stale-prices",
    "missing-evidence",
    "lock-held",
    "duplicate-run",
    "chain-break",
    "critic-block",
)
MIN_INDEPENDENT_SOURCES = 2
POLICY_EVIDENCE_ID = "ev-policy-min-sources"
SCHEMA_BY_COLLECTION = {
    "policy": "policy",
    "portfolios": "portfolio_state",
    "evidence": "evidence",
    "runs": "research_run",
    "recommendations": "recommendation",
    "outcomes": "outcome",
    "security": "security_research",
    "learning": "learning",
    "health": "health",
    "snapshots": "snapshot",
    "boards": "board",
}
UNSCHEMAED_DOCS = frozenset({"runs/legacy-chain"})


def parse_time(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def iso(moment: datetime) -> str:
    return clock.to_utc(moment).isoformat(timespec="seconds").replace("+00:00", "Z")


def default_policy(adopted_at: str) -> dict[str, Any]:
    """The public-safe policy document: mandate defaults, rubric, freshness, schedule."""
    return {
        "version": "1.0.0-draft",
        "adopted_at": adopted_at,
        "mandate": {
            "horizons": [
                {"name": "tactical", "min_months": 3, "max_months": 6},
                {"name": "secondary", "min_months": 12, "max_months": 36},
            ],
            "upside_hurdle": scorecard.UPSIDE_HURDLE,
            "return_goal": 0.10,
            "target_stock_count": 10,
            "target_cash_weight": 0.13,
            "min_cash_weight": 0.10,
            "max_cash_weight": 0.25,
            "max_single_position": 0.13,
            "max_initial_position": 0.10,
            "max_sector_weight": 0.26,
            "cooling_hours": 24,
            "benchmark": "SPY total return",
            "exclusions": [
                "options",
                "margin",
                "leverage",
                "short selling",
                "futures",
                "swaps",
                "inverse or leveraged funds",
                "penny stocks",
                "blank-check companies",
                "illiquid or unlisted securities",
                "rumor-dependent theses",
                "paid promotion",
            ],
        },
        "rubric": {
            "equity": {
                "id": scorecard.RUBRIC_VERSION,
                "status": "ADOPTED",
                "weights": dict(scorecard.EQUITY_WEIGHTS),
                "core": sorted(scorecard.EQUITY_CORE),
                "min_coverage": scorecard.MIN_COVERAGE,
            },
            "crypto": {
                "id": scorecard.CRYPTO_RUBRIC_VERSION,
                "status": "PROPOSED",
                "weights": dict(scorecard.CRYPTO_WEIGHTS_PROPOSED),
                "core": sorted(scorecard.CRYPTO_CORE),
            },
        },
        "freshness": {
            "equity_price": "at or after the last regular close",
            **{k: f"{int(v.total_seconds() // 3600)}h" for k, v in freshness.LIMITS.items()},
        },
        "schedule": {
            "timezone": "America/New_York",
            "runs": [
                {
                    "name": "daily",
                    "target_et": "06:00",
                    "cron_utc": "0 10 * * *",
                    "idempotency": "daily:YYYY-MM-DD",
                    "dst_note": "a fixed 10:00 UTC cron fires at 5:00 AM ET during standard time",
                },
                {
                    "name": "sentinel",
                    "target_et": "hourly at :26",
                    "cron_utc": "26 * * * *",
                    "idempotency": "sentinel:YYYY-MM-DDTHH",
                    "dst_note": "hourly; wall-clock minute is unaffected by DST",
                },
            ],
        },
        "governance": {
            "read_only": True,
            "no_trade_execution": True,
            "screenshot_only_balances": True,
            "contract_first_crypto_identity": True,
            "no_invented_numbers": True,
            "recommendations_immutable": True,
            "human_approval_for_model_promotion": True,
            "critic_rounds_max": "2",
        },
        "provenance": {
            "horizons": {
                "label": "source-backed",
                "source": "repository mandate (3-6 months) and the 2026-09-11 implementation prompt (12-36 months secondary lens)",
            },
            "upside_hurdle": {
                "label": "conflict",
                "source": "implementation prompt names a 15% upside screening hurdle; the repository mandate states a 10% total-return goal; 15% retained for screening pending Joe's confirmation",
            },
            "target_stock_count": {
                "label": "source-backed",
                "source": "handoffs/perplexity_portfolio/01_Joe_Investment_Mandate.md",
            },
            "target_cash_weight": {
                "label": "source-backed",
                "source": "handoffs/perplexity_portfolio/04_Portfolio_Risk_Limits.md",
            },
            "cooling_hours": {
                "label": "source-backed",
                "source": "handoffs/perplexity_portfolio/01_Joe_Investment_Mandate.md (24-hour cooling rule)",
            },
            "max_single_position": {
                "label": "source-backed",
                "source": "handoffs/perplexity_portfolio/04_Portfolio_Risk_Limits.md (13% hard ceiling)",
            },
            "rubric.equity": {
                "label": "judgment",
                "source": "implementation prompt weights; adopted for the dry run, subject to Joe's approval",
            },
            "rubric.crypto": {
                "label": "assumption",
                "source": "docs/TERMINAL_CRYPTO_RUBRIC_PROPOSAL.md; PROPOSED, not adopted",
            },
            "schedule": {
                "label": "confirmed",
                "source": "Routine cron expressions read from the account's trigger list on 2026-09-11",
            },
        },
    }


@dataclass
class RunResult:
    manifest: runs.RunManifest
    docs: dict[str, dict] = field(default_factory=dict)
    stages: list[dict] = field(default_factory=list)
    gate_checks: list[gates.GateCheck] = field(default_factory=list)
    debate: dict | None = None
    boards: dict[str, str] = field(default_factory=dict)
    risk: list[dict] = field(default_factory=list)

    @property
    def status(self) -> str:
        return self.manifest.status

    def as_dict(self) -> dict:
        return {
            "manifest": self.manifest.as_dict(),
            "stages": list(self.stages),
            "gates": [g.as_dict() for g in self.gate_checks],
            "debate": self.debate,
            "boards": dict(self.boards),
            "risk": list(self.risk),
            "documents": sorted(self.docs),
        }


def _stage(name: str, status: str, detail: str) -> dict:
    return {"name": name, "status": status, "detail": detail}


def _observed(security: dict, inject: str | None) -> datetime | None:
    price = security.get("price") or {}
    if not price.get("observed_at"):
        return None
    observed = parse_time(price["observed_at"])
    if inject == "stale-prices":
        observed -= timedelta(days=5)
    return observed


def _weights(portfolio: dict) -> dict[str, float]:
    total = portfolio.get("total_value") or 0.0
    weights: dict[str, float] = {}
    for position in portfolio.get("positions", []):
        weight = position.get("weight")
        if weight is None and total and position.get("market_value") is not None:
            weight = position["market_value"] / total
        if weight is not None:
            key = position.get("asset_id") or position["symbol"]
            weights[key] = max(weights.get(key, 0.0), float(weight))
    return weights


def portfolio_risk(portfolio: dict, policy: dict) -> dict:
    """Limits from the policy, applied to one portfolio on its own."""
    mandate = policy["mandate"]
    weights = _weights(portfolio)
    breaches: list[str] = []
    largest = max(weights.items(), key=lambda kv: kv[1]) if weights else (None, 0.0)
    if largest[1] > mandate["max_single_position"]:
        breaches.append(
            f"{largest[0]} at {largest[1]:.1%} exceeds the {mandate['max_single_position']:.0%} single-name ceiling"
        )
    cash = portfolio.get("cash_weight")
    if cash is not None:
        if cash < mandate["min_cash_weight"]:
            breaches.append(f"cash {cash:.1%} is below the {mandate['min_cash_weight']:.0%} floor")
        elif cash > mandate["max_cash_weight"]:
            breaches.append(
                f"cash {cash:.1%} is above the {mandate['max_cash_weight']:.0%} ceiling (defensive rationale required)"
            )
    count = len(weights)
    if (
        count > mandate["target_stock_count"]
        and portfolio.get("account_kind", "").lower().find("ira") >= 0
    ):
        breaches.append(f"{count} positions against a {mandate['target_stock_count']}-name target")
    return {
        "portfolio_id": portfolio["portfolio_id"],
        "label": portfolio.get("label", portfolio["portfolio_id"]),
        "positions": count,
        "largest": {"asset": largest[0], "weight": round(largest[1], 4)},
        "cash_weight": cash,
        "breaches": breaches,
        "status": "REVIEW" if breaches else "OK",
        "as_of": portfolio.get("as_of"),
        "verification": portfolio.get("verification"),
    }


def _stance(score: float | None, hurdle: bool | None, owned_weight: float, policy: dict) -> str:
    target = policy["mandate"]["max_initial_position"] or policy["mandate"]["max_single_position"]
    if score is None:
        return "PASS"
    if score >= 70 and hurdle:
        return "ADD" if 0 < owned_weight < target else ("HOLD" if owned_weight else "BUY")
    if score >= 50:
        return "HOLD" if owned_weight else "WATCH"
    if score < 35:
        return "TRIM" if owned_weight else "PASS"
    return "HOLD" if owned_weight else "WATCH"


def _critic_stand_in(inject: str | None):
    def critic_fn(proposal: dict, round_number: int) -> list[critic.Challenge]:
        challenges: list[critic.Challenge] = []
        for rec in proposal["recommendations"]:
            if inject == "critic-block":
                challenges.append(
                    critic.Challenge(
                        rec["recommendation_id"],
                        "injected blocking objection",
                        "blocking",
                        ("ev-inject",),
                    )
                )
                continue
            if len(rec["evidence_ids"]) < MIN_INDEPENDENT_SOURCES and rec["stance"] in (
                "BUY",
                "ADD",
            ):
                challenges.append(
                    critic.Challenge(
                        rec["recommendation_id"],
                        f"fewer than {MIN_INDEPENDENT_SOURCES} independent sources behind a {rec['stance']}",
                        "blocking",
                        (POLICY_EVIDENCE_ID,),
                    )
                )
            elif round_number == 1 and rec.get("scorecard") and rec["scorecard"]["coverage"] < 0.85:
                challenges.append(
                    critic.Challenge(
                        rec["recommendation_id"],
                        f"rubric coverage {rec['scorecard']['coverage']:.0%}: the rationale must say what is unscored",
                        "material",
                        tuple(rec["evidence_ids"][:1]),
                    )
                )
        return challenges

    def responder_fn(
        proposal: dict, challenges: list[critic.Challenge], round_number: int
    ) -> tuple[dict, list[critic.Response]]:
        revised = copy.deepcopy(proposal)
        responses: list[critic.Response] = []
        by_id = {rec["recommendation_id"]: rec for rec in revised["recommendations"]}
        for challenge in challenges:
            rec = by_id.get(challenge.target)
            if rec is None:
                continue
            if inject == "critic-block":
                responses.append(
                    critic.Response(challenge.target, "rebut", "no evidence offered", ())
                )
            elif challenge.severity == "blocking":
                revised["recommendations"] = [
                    r
                    for r in revised["recommendations"]
                    if r["recommendation_id"] != challenge.target
                ]
                responses.append(
                    critic.Response(
                        challenge.target,
                        "revise",
                        "withdrawn: the source floor is not met",
                        (POLICY_EVIDENCE_ID,),
                    )
                )
            else:
                unscored = ", ".join(rec["scorecard"]["unscored"]) or "none"
                rec["rationale"] += f" Unscored factors: {unscored}."
                responses.append(
                    critic.Response(
                        challenge.target,
                        "revise",
                        "rationale now names the unscored factors",
                        tuple(rec["evidence_ids"][:1]),
                    )
                )
        return revised, responses

    return critic_fn, responder_fn


def run(
    inputs: dict,
    store: store_mod.Store,
    *,
    lock: runs.RunLock | None = None,
    ledger: runs.RunLedger | None = None,
) -> RunResult:
    """Execute one research run against ``store`` and return what happened."""
    inject = inputs.get("inject")
    if inject is not None and inject not in INJECTIONS:
        raise ValueError(f"unknown failure injection {inject!r}")
    now = parse_time(inputs["now"])
    scheduled = parse_time(inputs.get("scheduled_at") or inputs["now"])
    kind = inputs.get("kind", "daily")
    writer = inputs.get("writer", "DAILY")
    key = runs.idempotency_key(kind, scheduled, inputs.get("label"))
    rid = runs.run_id(kind, key, inputs.get("salt", ""))
    manifest = runs.RunManifest(rid, kind, key, writer, iso(scheduled), iso(now))
    result = RunResult(manifest)
    stages = result.stages

    # Stage 0: idempotency and the writer lock.
    if ledger is None:
        ledger = runs.RunLedger([doc for _, doc in store.list("runs") if "idempotency_key" in doc])
    if inject == "duplicate-run":
        ledger.records.append(
            {
                "idempotency_key": key,
                "status": "PUBLISHED",
                "run_id": "prior-run",
                "result_sha": ledger.last_published_sha() or "0" * 64,
                "base_sha": None,
            }
        )
    if ledger.already_published(key):
        manifest.status = "SKIPPED"
        manifest.notes.append(f"idempotency key {key} already published; nothing re-run")
        stages.append(_stage("idempotency", "SKIPPED", manifest.notes[-1]))
        return result
    stages.append(_stage("idempotency", "OK", f"key {key} not yet published"))
    lock = lock or runs.RunLock()
    if inject == "lock-held":
        lock.acquire("another-writer", now)
    if not lock.acquire(rid, now):
        manifest.status = "BLOCKED"
        holder = lock.holder(now)
        stages.append(_stage("lock", "FAILED", f"writer lock held by {holder}; not run"))
        return result
    stages.append(_stage("lock", "OK", f"lease held by {rid}"))

    # Stage 1: data steward.
    policy = inputs.get("policy") or store.get("policy/current") or default_policy(iso(now))
    steward_errors = schema.validate(policy, schema.load_schema("policy"))
    portfolios = [copy.deepcopy(p) for p in inputs.get("portfolios", [])]
    for portfolio in portfolios:
        steward_errors += [
            f"portfolio {portfolio.get('portfolio_id')}: {e}"
            for e in schema.validate(portfolio, schema.load_schema("portfolio_state"))
        ]
    evidence_docs = {e["evidence_id"]: e for e in inputs.get("evidence", [])}
    for doc in evidence_docs.values():
        steward_errors += schema.validate(doc, schema.load_schema("evidence"))
    if steward_errors:
        manifest.status = "BLOCKED"
        stages.append(_stage("steward", "FAILED", "; ".join(steward_errors[:5])))
        lock.release(rid)
        return result
    securities = [copy.deepcopy(s) for s in inputs.get("securities", [])]
    identity_problems: dict[str, list[str]] = {}
    parsed: list[identity.AssetId] = []
    for security in securities:
        asset = identity.parse(security["asset_id"], security.get("symbol"))
        problems = identity.validate(asset)
        if problems:
            identity_problems[security["asset_id"]] = problems
        parsed.append(asset)
    collisions = identity.collisions(parsed)
    equity_fresh: list[freshness.Freshness] = []
    crypto_fresh: list[freshness.Freshness] = []
    for security in securities:
        field_name = "equity_price" if security["asset_class"] == "equity" else "crypto_price"
        item = freshness.assess(field_name, _observed(security, inject), now)
        security["_freshness"] = item
        (equity_fresh if field_name == "equity_price" else crypto_fresh).append(item)
    boards = {
        "rankings-equity": freshness.board_status(equity_fresh),
        "rankings-crypto": freshness.board_status(crypto_fresh),
    }
    for board_id, doc in store.list("boards"):
        boards.setdefault(board_id, doc.get("status", "STALE"))
    result.boards = boards
    steward_status = "OK"
    detail = f"{len(securities)} securities, {len(evidence_docs)} evidence records"
    if identity_problems or collisions:
        steward_status = "DEGRADED"
        detail += f"; identity problems on {len(identity_problems)} asset(s); symbol collisions {sorted(collisions)}"
    if any(
        status != freshness.LIVE
        for status in (boards["rankings-equity"], boards["rankings-crypto"])
    ):
        steward_status = "DEGRADED"
        detail += f"; boards {boards['rankings-equity']}/{boards['rankings-crypto']}"
    stages.append(_stage("steward", steward_status, detail))

    # Stage 2: universe tiers and the research budget.
    owned = {
        p.get("asset_id") or p["symbol"]
        for portfolio in portfolios
        for p in portfolio.get("positions", [])
    }
    universe_in = inputs.get("universe", {})
    assignment = universe.assign(
        owned,
        set(universe_in.get("mandate", [])),
        set(universe_in.get("screened", [])),
        set(universe_in.get("mentions", [])),
    )
    budget = universe.research_budget(assignment)
    stages.append(
        _stage(
            "universe",
            "OK",
            ", ".join(
                f"{tier} {assignment.counts[tier]} assets / {budget[tier]['slots']} slots"
                for tier in universe.TIERS
            ),
        )
    )

    # Stage 3: analysts and quant: gates, scorecards, scenarios, hurdle.
    security_docs: dict[str, dict] = {}
    rows_by_kind: dict[str, list[dict]] = {"equity": [], "crypto": []}
    owned_weight: dict[str, float] = {}
    for portfolio in portfolios:
        for key_, weight in _weights(portfolio).items():
            owned_weight[key_] = max(owned_weight.get(key_, 0.0), weight)
    for security in securities:
        asset_id = security["asset_id"]
        gate = gates.asset_gate(security.get("fatal_flags", {}))
        evidence_map = {} if inject == "missing-evidence" else dict(security.get("evidence", {}))
        factors = security.get("factors", {})
        result_card = None
        weighted = None
        hurdle: bool | None = None
        if gate.passed and asset_id not in identity_problems:
            scorer = (
                scorecard.score_equity
                if security["asset_class"] == "equity"
                else scorecard.score_crypto
            )
            result_card = scorer(factors, evidence_map)
            scen = security.get("scenarios")
            if scen:
                cases = [
                    scenarios.Scenario(
                        c["name"], c["probability"], c["end_value"], c.get("distributions", 0.0)
                    )
                    for c in scen["cases"]
                ]
                weighted = scenarios.probability_weighted(
                    scen["entry"], cases, scen.get("costs", 0.0)
                )
                hurdle = scorecard.clears_hurdle(
                    weighted.expected, policy["mandate"]["upside_hurdle"]
                )
        fresh = security.pop("_freshness")
        doc = {
            "asset_id": asset_id,
            "symbol": security["symbol"],
            "asset_class": security["asset_class"],
            "as_of": iso(now),
            "identity": security.get("identity", {"canonical": asset_id}),
            "fatal_flags": security.get("fatal_flags", {}),
            "gate": gate.as_dict(),
            "facts": security.get("facts", []),
            "catalysts": security.get("catalysts", []),
            "scorecard": result_card.as_dict() if result_card else None,
            "notes": list(security.get("notes", []))
            + [f"price freshness {fresh.state} ({fresh.limit})"]
            + [f"identity: {p}" for p in identity_problems.get(asset_id, [])],
        }
        if weighted is not None:
            doc["scenarios"] = weighted.as_dict() | {
                "entry": security["scenarios"]["entry"],
                "hurdle": policy["mandate"]["upside_hurdle"],
                "hurdle_cleared": hurdle,
            }
        security_docs[asset_id] = doc
        status = (
            "EXCLUDED"
            if not gate.passed or asset_id in identity_problems
            else (result_card.status if result_card else "INSUFFICIENT")
        )
        rows_by_kind["equity" if security["asset_class"] == "equity" else "crypto"].append(
            {
                "rank": 0,
                "asset_id": asset_id,
                "symbol": security["symbol"],
                "owned": (owned_weight.get(asset_id) or owned_weight.get(security["symbol"]) or 0.0)
                > 0,
                "cells": {
                    "PRICE": (security.get("price") or {}).get("price"),
                    "SCORE": result_card.score if result_card else None,
                    "COVERAGE": f"{result_card.coverage:.0%}" if result_card else None,
                    "EXPECTED": f"{weighted.expected:+.1%}" if weighted else None,
                    "HURDLE": ("YES" if hurdle else "NO") if hurdle is not None else "n/a",
                    "FRESHNESS": fresh.state,
                    "GATE": "PASS" if gate.passed else "FAIL: " + ", ".join(gate.failed),
                },
                "legacy_zone": None,
                "scorecard": result_card.as_dict() if result_card else None,
                "status": status,
                "case": "; ".join(result_card.notes) if result_card and result_card.notes else None,
                "_hurdle": hurdle,
                "_weight": owned_weight.get(asset_id)
                or owned_weight.get(security["symbol"])
                or 0.0,
                "_evidence": sorted({eid for ids in evidence_map.values() for eid in ids}),
                "_catalysts": security.get("catalysts", []),
                "_risks": security.get("risks", []),
                "_invalidation": security.get("invalidation", []),
            }
        )
    board_docs: dict[str, dict] = {}
    for kind_name, rows in rows_by_kind.items():
        ranked = [r for r in rows if r["status"] in ("SCORED", "PARTIAL")]
        ranked.sort(
            key=lambda r: (
                -(r["scorecard"]["score"] or 0.0),
                -r["scorecard"]["coverage"],
                r["symbol"],
            )
        )
        for index, row in enumerate(ranked, start=1):
            row["rank"] = index
        unranked = [r for r in rows if r["status"] not in ("SCORED", "PARTIAL")]
        board_id = f"rankings-{kind_name}"
        rubric = (
            scorecard.RUBRIC_VERSION if kind_name == "equity" else scorecard.CRYPTO_RUBRIC_VERSION
        )
        board_docs[board_id] = {
            "board_id": board_id,
            "title": "Stock rankings (100-point scorecard)"
            if kind_name == "equity"
            else "Crypto rankings (PROPOSED rubric)",
            "kind": kind_name,
            "as_of": iso(now),
            "status": boards[board_id],
            "stamp": clock.stamp(now),
            "columns": ["PRICE", "SCORE", "COVERAGE", "EXPECTED", "HURDLE", "FRESHNESS", "GATE"],
            "rows": [
                {k: v for k, v in r.items() if not k.startswith("_")} for r in ranked + unranked
            ],
            "notes": [
                f"{len(ranked)} ranked, {len(unranked)} listed not ranked (excluded or insufficient)"
            ],
            "rubric": rubric,
            "legacy_ordering": None,
        }
    stages.append(
        _stage(
            "quant",
            "OK",
            f"{sum(1 for r in rows_by_kind['equity'] + rows_by_kind['crypto'] if r['rank'])} ranked of {len(securities)}",
        )
    )

    # Stage 4: portfolio risk, each portfolio on its own.
    result.risk = [portfolio_risk(p, policy) for p in portfolios]
    schwab = [
        p
        for p in portfolios
        if p["portfolio_id"].startswith("schwab-") and p["portfolio_id"] != "schwab-combined"
    ]
    invariant_failures: list[str] = []
    if len(schwab) == 2 and not all(set(p.get("distinct_from", [])) for p in schwab):
        invariant_failures.append("the two Schwab portfolios must declare distinct_from each other")
    stages.append(
        _stage(
            "risk",
            "OK" if not any(r["breaches"] for r in result.risk) else "DEGRADED",
            "; ".join(f"{r['portfolio_id']} {r['status']}" for r in result.risk)
            or "no portfolios supplied",
        )
    )

    # Stage 5: recommendations, then the critic.
    recs: list[dict] = []
    cooling = timedelta(hours=policy["mandate"]["cooling_hours"])
    for kind_name in ("equity", "crypto"):
        for row in rows_by_kind[kind_name]:
            if not row["rank"]:
                continue
            stance = _stance(row["scorecard"]["score"], row["_hurdle"], row["_weight"], policy)
            body = {
                "recommendation_id": f"rec-{rid}-{row['symbol'].lower()}",
                "run_id": rid,
                "issued_at": iso(now),
                "asset_id": row["asset_id"],
                "symbol": row["symbol"],
                "portfolio_id": None,
                "stance": stance,
                "horizon_days": 120,
                "lens": "tactical",
                "reference_price": None,
                "reference_convention": "first regular-session open after publication (quote if published during the session)",
                "scorecard": row["scorecard"],
                "scenarios": security_docs[row["asset_id"]].get("scenarios"),
                "hurdle_cleared": row["_hurdle"],
                "rationale": f"{row['symbol']} scores {row['scorecard']['score']} on {row['scorecard']['rubric']} with {row['scorecard']['coverage']:.0%} coverage; stance {stance} by the policy ladder.",
                "evidence_ids": row["_evidence"],
                "risks": row["_risks"],
                "invalidation": row["_invalidation"],
                "critic": None,
                "cooling_period_ends": iso(now + cooling) if stance in ("BUY", "ADD") else None,
            }
            recs.append(body)
    critic_fn, responder_fn = _critic_stand_in(inject)
    revised, record = critic.run_debate({"recommendations": recs}, critic_fn, responder_fn)
    result.debate = record.as_dict()
    final_recs = revised["recommendations"] if record.verdict != critic.BLOCKED else []
    rec_docs: dict[str, dict] = {}
    for body in final_recs:
        body["critic"] = {"verdict": record.verdict, "rounds": record.rounds}
        body["content_sha"] = runs.sha256_of({k: v for k, v in body.items() if k != "content_sha"})
        rec_docs[body["recommendation_id"]] = body
    stages.append(
        _stage(
            "critic",
            "OK" if record.verdict != critic.BLOCKED else "FAILED",
            f"verdict {record.verdict} after {record.rounds} round(s); {len(final_recs)} recommendation(s) stand",
        )
    )

    # Stage 6: outcomes and learning.
    outcome_docs: dict[str, dict] = {}
    observations = inputs.get("observations", {})
    bench = [
        outcomes.Observation(parse_time(o["at"]), o["price"], o["kind"])
        for o in observations.get("benchmark", [])
    ]
    graded: list[outcomes.Outcome] = []
    for prior in inputs.get("prior_recommendations", []):
        series = [
            outcomes.Observation(parse_time(o["at"]), o["price"], o["kind"])
            for o in observations.get(prior["asset_id"], [])
        ]
        outcome = outcomes.evaluate(
            prior["stance"],
            parse_time(prior["issued_at"]),
            prior["horizon_days"],
            series,
            bench,
            now,
        )
        graded.append(outcome)
        outcome_docs[prior["recommendation_id"]] = {
            "outcome_id": prior["recommendation_id"],
            "recommendation_id": prior["recommendation_id"],
            "graded_at": iso(now),
            "benchmark": policy["mandate"]["benchmark"],
            **outcome.as_dict(),
        }
    learning = store.get("learning/current") or {
        "as_of": iso(now),
        "windows": [],
        "hit_rates": {},
        "brier": None,
        "lessons": [],
        "model_changes": [],
    }
    learning = copy.deepcopy(learning)
    learning["as_of"] = iso(now)
    learning["hit_rates"][rid] = outcomes.hit_rate(graded)
    stages.append(
        _stage(
            "learning",
            "OK",
            f"{len(graded)} prior recommendation(s) graded: {outcomes.hit_rate(graded)}",
        )
    )

    # Stage 7: health, snapshot and the release gates.
    docs: dict[str, dict] = {"policy/current": policy}
    for portfolio in portfolios:
        docs[f"portfolios/{portfolio['portfolio_id']}"] = portfolio
    for eid, doc in evidence_docs.items():
        docs[f"evidence/{eid}"] = doc
    for asset_id, doc in security_docs.items():
        docs[f"security/{asset_id}"] = doc
    for board_id, doc in board_docs.items():
        docs[f"boards/{board_id}"] = doc
    for rec_id, doc in rec_docs.items():
        docs[f"recommendations/{rec_id}"] = doc
    for oid, doc in outcome_docs.items():
        docs[f"outcomes/{oid}"] = doc
    docs["learning/current"] = learning
    schedule = []
    for entry in policy["schedule"]["runs"]:
        parts = entry["cron_utc"].split()
        drift: list[dict] = []
        if (
            len(parts) == 5
            and parts[0].isdigit()
            and parts[1].isdigit()
            and ":" in entry["target_et"]
        ):
            hour, minute = (int(x) for x in entry["target_et"].split(":"))
            drift = [
                w.__dict__ | {"starts": w.starts.isoformat(), "ends": w.ends.isoformat()}
                for w in clock.dst_drift(
                    int(parts[1]),
                    int(parts[0]),
                    datetime.min.time().replace(hour=hour, minute=minute),
                    now.year,
                )
            ]
        schedule.append(
            {
                "name": entry["name"],
                "cron_utc": entry["cron_utc"],
                "target_et": entry["target_et"],
                "dst_drift": drift,
                "last_starts_vs_ready": clock.starts_vs_ready(scheduled, now).label,
            }
        )
    base_sha = "deadbeef" * 8 if inject == "chain-break" else ledger.last_published_sha()
    manifest.base_sha = base_sha
    manifest.inputs_sha = runs.sha256_of({k: v for k, v in inputs.items() if k != "inject"})
    manifest.result_sha = runs.sha256_of(docs)
    manifest.rows = sum(len(d["rows"]) for d in board_docs.values())
    candidate = manifest.as_dict() | {"status": "PUBLISHED"}
    chain = runs.verify_chain([*ledger.records, candidate])
    chain_ok = chain.ok and base_sha == ledger.last_published_sha()
    health = {
        "as_of": iso(now),
        "run_id": rid,
        "boards": {
            board_id: {
                "status": status,
                "stamp": clock.stamp(now)
                if board_id.startswith("rankings-")
                else (store.get(f"boards/{board_id}") or {}).get("stamp", "legacy"),
                "source": "pipeline" if board_id.startswith("rankings-") else "legacy migration",
            }
            for board_id, status in boards.items()
        },
        "schedule": schedule,
        "calendar_covered_through": clock.calendar_covered_through(),
        "store": {
            "mode": "json-dir" if isinstance(store, store_mod.JsonDirStore) else "memory",
            "documents": len(store_mod.MemoryStore.paths(store))
            if isinstance(store, store_mod.MemoryStore)
            else 0,
        },
        "page_bytes": sum(store_mod.doc_bytes(d) for d in docs.values()),
        "chain": {
            "ok": chain_ok,
            "length": chain.length,
            "breaks": chain.breaks
            or (
                [] if chain_ok else [f"base {str(base_sha)[:12]} is not the last published result"]
            ),
        },
        "notes": [
            f"starts vs ready: {clock.starts_vs_ready(scheduled, now).label}",
            f"failure injection: {inject or 'none'}",
        ],
    }
    docs["health/current"] = health
    schema_errors: list[str] = []
    for path, doc in docs.items():
        collection = path.split("/")[0]
        if path in UNSCHEMAED_DOCS or collection not in SCHEMA_BY_COLLECTION:
            continue
        schema_errors += [
            f"{path}: {e}"
            for e in schema.validate(doc, schema.load_schema(SCHEMA_BY_COLLECTION[collection]))
        ]
    before = {f"recommendations/{rec_id}": doc for rec_id, doc in store.list("recommendations")}
    violations = store_mod.immutable_violations(before, docs)
    checks = gates.release_gates(
        schema_errors=schema_errors,
        chain_ok=chain_ok,
        page_bytes=health["page_bytes"],
        boards_with_status=boards,
        immutable_violations=violations,
        invariant_failures=invariant_failures,
        critic_verdict=record.verdict,
    )
    result.gate_checks = checks
    passed = gates.all_passed(checks)
    manifest.status = "PUBLISHED" if passed else "BLOCKED"
    manifest.ready_at = iso(now)
    manifest.notes.append(f"starts vs ready: {clock.starts_vs_ready(scheduled, now).label}")
    run_doc = manifest.as_dict() | {
        "stages": stages,
        "gates": [c.as_dict() for c in checks],
        "boards": boards,
        "starts_vs_ready": clock.starts_vs_ready(scheduled, now).label,
        "failure_injected": inject,
        "risk": result.risk,
        "debate": result.debate,
    }
    stages.append(
        _stage(
            "release",
            "OK" if passed else "FAILED",
            "; ".join(f"{c.name}:{'pass' if c.passed else 'FAIL'}" for c in checks),
        )
    )
    run_doc["stages"] = stages
    if passed:
        for path, doc in docs.items():
            store.set(path, doc)
        store.set(f"runs/{rid}", run_doc)
        parts = {
            f"{collection}/{doc_id}": doc
            for collection in store_mod.COLLECTIONS
            for doc_id, doc in store.list(collection)
            if collection != "snapshots"
        }
        snapshot = runs.build_snapshot(
            parts, now, inputs.get("version_label") or f"run-{rid}", base_sha
        ) | {"run_id": rid, "starts_vs_ready": run_doc["starts_vs_ready"]}
        store.set("snapshots/current", snapshot)
        ledger.append(manifest)
        docs["snapshots/current"] = snapshot
    else:
        store.set(f"runs/{rid}", run_doc)
    docs[f"runs/{rid}"] = run_doc
    result.docs = docs
    lock.release(rid)
    return result
