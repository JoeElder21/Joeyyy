"""Tests for scripts/daily_balance_report.py using synthetic fixtures only.

No network: every fetcher is replaced with a fake. Symbols, quantities and
prices below are invented round numbers, not anyone's holdings.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "daily_balance_report", ROOT / "scripts" / "daily_balance_report.py"
)
dbr = importlib.util.module_from_spec(SPEC)
sys.modules["daily_balance_report"] = dbr
SPEC.loader.exec_module(dbr)

NOW = dt.datetime(2026, 1, 15, 14, 35, tzinfo=dt.UTC)


def quote(price, source="FAKE", note=""):
    return dbr.Quote(
        price, "2026-01-15T14:35:00+00:00", source, "https://example.invalid/q", note=note
    )


def fake_fetchers(prices: dict, failing: set | None = None, thin: set | None = None):
    """Build a fetcher table keyed by spec['type']; price looked up by spec['key']."""
    failing = failing or set()
    thin = thin or set()

    def make(kind):
        def fn(spec, now=None):
            key = spec["key"]
            if key in failing:
                raise RuntimeError(f"{kind} unavailable for {key}")
            return quote(prices[key], source=kind.upper(), note="THIN" if key in thin else "")

        return fn

    return {k: make(k) for k in ("p", "s", "m")} | {
        "static": dbr.fetch_static,
        "manual": dbr.fetch_manual,
    }


def ledger(**overrides):
    base = {
        "schema": dbr.SCHEMA,
        "owner_label": "Test Household",
        "baseline": {"date": "2026-01-01", "time_et": "18:00"},
        "tolerance_pct": {"equity": 1.0, "dex_token": 5.0, "default": 2.0},
        "notes": ["synthetic fixture"],
        "accounts": [
            {
                "id": "brokerage",
                "name": "Test Brokerage",
                "venue": "Broker A",
                "cash": [{"label": "Cash", "amount": 100.0}],
                "positions": [
                    {
                        "symbol": "AAA",
                        "name": "Alpha Fund",
                        "asset_class": "equity",
                        "qty": 10,
                        "baseline_value": 1000.0,
                        "baseline_price": 100.0,
                        "cost_basis_total": 900.0,
                        "price": {
                            "primary": {"type": "p", "key": "AAA"},
                            "secondary": {"type": "s", "key": "AAA-s"},
                        },
                    },
                    {
                        "symbol": "BBB",
                        "name": "Beta Token",
                        "asset_class": "dex_token",
                        "qty": 1000,
                        "qty_status": "derived",
                        "baseline_value": 50.0,
                        "baseline_price": 0.05,
                        "price": {
                            "primary": {"type": "p", "key": "BBB"},
                            "secondary": {"type": "s", "key": "BBB-s"},
                        },
                    },
                ],
                "perps": [
                    {
                        "symbol": "AAA PERP",
                        "side": "long",
                        "contracts": 2,
                        "contract_size": 0.5,
                        "entry_price": 100.0,
                        "baseline_pnl": 5.0,
                        "mark": {"primary": {"type": "m", "key": "AAA-mark"}},
                    },
                ],
            },
            {
                "id": "wallet",
                "name": "Test Wallet",
                "venue": "Chain Z",
                "positions": [
                    {
                        "symbol": "CCC",
                        "name": "Gamma Coin",
                        "asset_class": "dex_token",
                        "qty": 5,
                        "baseline_value": 250.0,
                        "baseline_price": 50.0,
                        "price": {"primary": {"type": "p", "key": "CCC"}},
                    },
                ],
            },
        ],
    }
    base.update(overrides)
    return base


class ResolveTests(unittest.TestCase):
    def test_agreement_uses_primary_without_flags(self):
        f = fake_fetchers({"AAA": 101.0, "AAA-s": 101.5})
        r = dbr.resolve_price(
            {"primary": {"type": "p", "key": "AAA"}, "secondary": {"type": "s", "key": "AAA-s"}},
            1.0,
            f,
            NOW,
        )
        self.assertEqual(r.price, 101.0)
        self.assertEqual(r.flags, [])
        self.assertAlmostEqual(r.gap_pct, abs(101.0 - 101.5) / 101.5 * 100)

    def test_disagreement_is_flagged_and_primary_kept(self):
        f = fake_fetchers({"AAA": 100.0, "AAA-s": 110.0})
        r = dbr.resolve_price(
            {"primary": {"type": "p", "key": "AAA"}, "secondary": {"type": "s", "key": "AAA-s"}},
            1.0,
            f,
            NOW,
        )
        self.assertEqual(r.price, 100.0)
        self.assertIn("DISAGREE", r.flags)

    def test_secondary_fallback(self):
        f = fake_fetchers({"AAA": 100.0, "AAA-s": 99.0}, failing={"AAA"})
        r = dbr.resolve_price(
            {"primary": {"type": "p", "key": "AAA"}, "secondary": {"type": "s", "key": "AAA-s"}},
            1.0,
            f,
            NOW,
        )
        self.assertEqual(r.price, 99.0)
        self.assertIn("SECONDARY", r.flags)
        self.assertTrue(any("unavailable" in e for e in r.errors))

    def test_both_fail_gives_no_price(self):
        f = fake_fetchers({"AAA": 1, "AAA-s": 1}, failing={"AAA", "AAA-s"})
        r = dbr.resolve_price(
            {"primary": {"type": "p", "key": "AAA"}, "secondary": {"type": "s", "key": "AAA-s"}},
            1.0,
            f,
            NOW,
        )
        self.assertIsNone(r.price)
        self.assertEqual(r.flags, ["NO PRICE"])

    def test_thin_liquidity_flag(self):
        f = fake_fetchers({"BBB": 0.05, "BBB-s": 0.05}, thin={"BBB"})
        r = dbr.resolve_price(
            {"primary": {"type": "p", "key": "BBB"}, "secondary": {"type": "s", "key": "BBB-s"}},
            5.0,
            f,
            NOW,
        )
        self.assertIn("THIN", r.flags)

    def test_unknown_fetcher_type_is_an_error_not_a_crash(self):
        r = dbr.resolve_price({"primary": {"type": "nope", "key": "x"}}, 1.0, {}, NOW)
        self.assertIsNone(r.price)
        self.assertTrue(r.errors and "unknown fetcher" in r.errors[0])


class ComputeTests(unittest.TestCase):
    def test_values_totals_and_gains(self):
        f = fake_fetchers(
            {
                "AAA": 110.0,
                "AAA-s": 110.5,
                "BBB": 0.04,
                "BBB-s": 0.041,
                "CCC": 60.0,
                "AAA-mark": 103.0,
            }
        )
        m = dbr.compute(ledger(), [], NOW, f)
        brok = m["accounts"][0]
        aaa = brok["positions"][0]
        self.assertAlmostEqual(aaa["value"], 1100.0)
        self.assertAlmostEqual(aaa["delta_vs_baseline"], 100.0)
        self.assertAlmostEqual(aaa["pct_vs_baseline"], 10.0)
        self.assertAlmostEqual(aaa["pct_vs_cost"], 1100.0 / 900.0 * 100 - 100)
        bbb = brok["positions"][1]
        self.assertAlmostEqual(bbb["value"], 40.0)
        self.assertIsNone(bbb["pct_vs_cost"])
        perp = brok["perps"][0]
        self.assertAlmostEqual(perp["pnl"], (103.0 - 100.0) * 2 * 0.5)
        self.assertAlmostEqual(brok["total"], 1100.0 + 40.0 + 100.0 + 3.0)
        self.assertAlmostEqual(brok["baseline_total"], 1000.0 + 50.0 + 100.0 + 5.0)
        self.assertAlmostEqual(m["household_total"], brok["total"] + 300.0)
        self.assertEqual(m["stale_rows"], 0)
        self.assertEqual(m["date_et"], "2026-01-15")

    def test_no_price_carries_baseline_forward_and_counts_stale(self):
        f = fake_fetchers(
            {"AAA": 110.0, "AAA-s": 110.0, "BBB": 1, "BBB-s": 1, "CCC": 60.0, "AAA-mark": 100.0},
            failing={"BBB", "BBB-s"},
        )
        m = dbr.compute(ledger(), [], NOW, f)
        bbb = m["accounts"][0]["positions"][1]
        self.assertTrue(bbb["stale"])
        self.assertEqual(bbb["value"], 50.0)
        self.assertEqual(bbb["stale_from"], "2026-01-01")
        self.assertIsNone(bbb["price"])
        self.assertEqual(m["stale_rows"], 1)

    def test_no_price_prefers_last_known_history_value(self):
        f = fake_fetchers(
            {"AAA": 110.0, "AAA-s": 110.0, "BBB": 1, "BBB-s": 1, "CCC": 60.0, "AAA-mark": 100.0},
            failing={"BBB", "BBB-s"},
        )
        history = [
            {
                "date_et": "2026-01-14",
                "household_total": 1,
                "positions": {"brokerage:BBB": {"value": 44.0, "price": 0.044, "stale": False}},
            }
        ]
        m = dbr.compute(ledger(), history, NOW, f)
        bbb = m["accounts"][0]["positions"][1]
        self.assertEqual(bbb["value"], 44.0)
        self.assertEqual(bbb["stale_from"], "2026-01-14")

    def test_perp_without_entry_carries_baseline_pnl(self):
        led = ledger()
        led["accounts"][0]["perps"][0].pop("entry_price")
        f = fake_fetchers(
            {
                "AAA": 110.0,
                "AAA-s": 110.0,
                "BBB": 0.05,
                "BBB-s": 0.05,
                "CCC": 60.0,
                "AAA-mark": 103.0,
            }
        )
        m = dbr.compute(led, [], NOW, f)
        perp = m["accounts"][0]["perps"][0]
        self.assertEqual(perp["pnl"], 5.0)
        self.assertIn("ENTRY n/a", perp["flags"])
        self.assertTrue(perp["entry_missing"])
        self.assertFalse(perp["stale"])
        self.assertEqual(m["entry_missing"], 1)
        self.assertEqual(m["stale_rows"], 0)
        self.assertAlmostEqual(perp["notional"], 103.0 * 2 * 0.5)
        page = dbr.render_html(m)
        self.assertIn("entry price is not on file", page)

    def test_prior_report_delta(self):
        f = fake_fetchers(
            {
                "AAA": 110.0,
                "AAA-s": 110.0,
                "BBB": 0.05,
                "BBB-s": 0.05,
                "CCC": 60.0,
                "AAA-mark": 100.0,
            }
        )
        history = [{"date_et": "2026-01-14", "household_total": 1500.0, "positions": {}}]
        m = dbr.compute(ledger(), history, NOW, f)
        self.assertEqual(m["prior_date_et"], "2026-01-14")
        self.assertAlmostEqual(m["delta_vs_prior"], m["household_total"] - 1500.0)


class HistoryTests(unittest.TestCase):
    def test_same_day_entry_is_replaced(self):
        h = [
            {"date_et": "2026-01-14", "generated_utc": "a", "household_total": 1},
            {"date_et": "2026-01-15", "generated_utc": "b", "household_total": 2},
        ]
        out = dbr.append_history(
            h, {"date_et": "2026-01-15", "generated_utc": "c", "household_total": 3}
        )
        self.assertEqual([e["household_total"] for e in out], [1, 3])

    def test_entry_shape(self):
        f = fake_fetchers(
            {
                "AAA": 110.0,
                "AAA-s": 110.0,
                "BBB": 0.05,
                "BBB-s": 0.05,
                "CCC": 60.0,
                "AAA-mark": 100.0,
            }
        )
        m = dbr.compute(ledger(), [], NOW, f)
        entry = dbr.history_entry(m)
        self.assertIn("brokerage:AAA", entry["positions"])
        self.assertIn("brokerage:AAA PERP", entry["positions"])
        self.assertEqual(entry["accounts"]["wallet"]["total"], 300.0)


class FormatTests(unittest.TestCase):
    def test_minus_sign_is_unicode(self):
        self.assertEqual(dbr.fmt_money(-12.5), "−$12.50")
        self.assertEqual(dbr.fmt_signed_money(12.5), "+$12.50")
        self.assertEqual(dbr.fmt_pct(-3.456), "−3.46%")
        self.assertEqual(dbr.fmt_pct(None), "n/a")

    def test_quantities_and_prices(self):
        self.assertEqual(dbr.fmt_qty(22922281.19), "22.922M")
        self.assertEqual(dbr.fmt_qty(192200), "192.20K")
        self.assertEqual(dbr.fmt_qty(15.754), "15.754")
        self.assertEqual(dbr.fmt_price(0.00001187), "$0.00001187")
        self.assertEqual(dbr.fmt_price(1234.5), "$1,234.50")

    def test_walk_path(self):
        data = {"chart": {"result": [{"meta": {"p": 1.5}}]}, "data": {"amount": "2"}}
        self.assertEqual(dbr._walk(data, "chart.result[0].meta.p"), 1.5)
        self.assertEqual(dbr._walk(data, "data.amount"), "2")


class RenderAndCliTests(unittest.TestCase):
    def test_render_mentions_everything_and_never_prints_none(self):
        f = fake_fetchers(
            {"AAA": 110.0, "AAA-s": 110.0, "BBB": 1, "BBB-s": 1, "CCC": 60.0, "AAA-mark": 103.0},
            failing={"BBB", "BBB-s"},
        )
        m = dbr.compute(ledger(), [], NOW, f)
        page = dbr.render_html(m)
        for needle in (
            "Test Brokerage",
            "Test Wallet",
            "AAA",
            "Beta Token",
            "CCC",
            "Account total",
            "carried forward",
            "synthetic fixture",
            "<title>Test Household Daily Balance</title>",
        ):
            self.assertIn(needle, page)
        self.assertNotIn(">None<", page)
        self.assertIn("n/a", page)
        self.assertIn("@page", page)

    def test_render_survives_secondary_only_and_no_quote_rows(self):
        f = fake_fetchers(
            {"AAA": 110.0, "AAA-s": 109.0, "BBB": 1, "BBB-s": 1, "CCC": 60.0, "AAA-mark": 103.0},
            failing={"AAA", "BBB", "BBB-s"},
        )
        m = dbr.compute(ledger(), [], NOW, f)
        page = dbr.render_html(m)
        self.assertIn("<b>S</b>", page)  # secondary source code appears in the legend
        self.assertIn("§", page)  # secondary-used glyph on the row

    def test_cli_writes_outputs(self):
        f = fake_fetchers(
            {
                "AAA": 110.0,
                "AAA-s": 110.0,
                "BBB": 0.05,
                "BBB-s": 0.05,
                "CCC": 60.0,
                "AAA-mark": 100.0,
            }
        )
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "ledger.json").write_text(json.dumps(ledger()), encoding="utf-8")
            with mock.patch.dict(dbr.FETCHERS, f, clear=True):
                rc = dbr.main(
                    [
                        "--ledger",
                        str(d / "ledger.json"),
                        "--history",
                        str(d / "history.json"),
                        "--out-dir",
                        str(d / "out"),
                        "--now",
                        NOW.isoformat(),
                    ]
                )
            self.assertEqual(rc, 0)
            self.assertTrue((d / "out" / "report.html").exists())
            model = json.loads((d / "out" / "report.json").read_text())
            self.assertEqual(model["schema"], dbr.SCHEMA)
            history = json.loads((d / "history.json").read_text())
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["date_et"], "2026-01-15")
            prices = json.loads((d / "out" / "prices.json").read_text())
            self.assertEqual(len(prices), 4)

    def test_cli_rejects_wrong_schema(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "ledger.json").write_text(
                json.dumps({"schema": "other", "accounts": []}), encoding="utf-8"
            )
            rc = dbr.main(
                [
                    "--ledger",
                    str(d / "ledger.json"),
                    "--history",
                    str(d / "h.json"),
                    "--out-dir",
                    str(d / "out"),
                ]
            )
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
