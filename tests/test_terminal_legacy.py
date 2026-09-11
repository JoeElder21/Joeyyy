"""Migration of a legacy page (capsule schema v43) into store documents."""

import unittest
from datetime import UTC, datetime

from terminal import legacy, pipeline, schema

PAGE = """<html><body>
<div class="tickerbar"><span class="tk">6:41 AM RUN - hello</span><span class="tk">6:41 AM RUN - hello</span></div>
<section id="action"><h2>ACTION</h2><div class="sub">Stamp: <span data-stamp="action">Fri Sep 11, 6:41 AM</span>.</div>
<div class="todo"><div class="tt">1 &middot; Do X</div><div class="tw">Because <b>Y</b></div></div></section>
<section id="accounts"><h2>ACCOUNT LEDGER</h2><div class="cards">
<div class="card"><div class="name">SCHWAB ROTH</div><div class="val">$1,000.00</div><div class="d">unrl +$10.00 &middot; cash $100.00 = 10.00%</div></div>
<div class="card"><div class="name">SCHWAB ROLLOVER</div><div class="val">$500.00</div><div class="d">cash <b>$0.01</b> — fully invested</div></div>
<div class="card"><div class="name">COINBASE</div><div class="val">$300.00</div><div class="d">stocks + cash $200.00 at the Sep 1 mark</div></div>
</div></section>
<section id="optimizer"><h2>BOARD 21</h2><h3>01 &middot; CHARLES SCHWAB &mdash; TWO IRAs, ONE BOOK &middot; $1,500.00</h3>
<table><tr><th>#</th><th>POSITION</th><th>NOW</th><th>TARGET</th><th>MOVE</th><th>SCORE</th><th>ACTION</th><th>THE CASE</th></tr>
<tr><td>1</td><td>AAA</td><td>$900.00 60.00%</td><td>$750.00 50.00%</td><td>−$150.00</td><td>80.0</td><td>TRIM</td><td>case</td></tr></table></section>
<section id="stocks"><h2>BOARD 01 &mdash; STOCKS</h2><div class="sub">stamp: <span data-stamp="stocks">Fri Sep 11, 6:41 AM — 6AM run: 2 of 2 re-quoted</span></div>
<table><tr><th>#</th><th>TKR</th><th>PRICE</th><th>DAY</th><th>WEEK</th><th>30D</th><th>ZONE</th><th>THE CASE</th></tr>
<tr data-b="10.00"><td class="rk">1</td><td class="tk2"><span class="cy">●</span> AAA</td><td>$10.00</td><td>+1.0%</td><td>−2.0%</td><td>+3.0%</td><td><span class="zone zHOLD">HOLD</span></td><td class="note">The <b>case</b> text</td></tr>
<tr><td>2</td><td>BBB</td><td>$5.00</td><td>−1.0%</td><td>+2.0%</td><td>−3.0%</td><td>WAIT</td><td>Another</td></tr>
<tr><td colspan="8">a note row that is not a ranked row</td></tr></table></section>
<section id="pumpfun"><h2>BOARD 06</h2><div class="sub"><span data-stamp="pumpfun">6AM audit, 3 of 4 priced</span></div>
<table><tr><th>#</th><th>ASSET</th><th>PRICE</th><th>ZONE</th><th>THE CASE</th></tr><tr><td>1</td><td>CCC</td><td>$0.01</td><td>BUY</td><td>x</td></tr></table></section>
<section id="allcall"><h2>BOARD 17</h2><table><tr><th>DATE</th><th>THE CALL</th><th>BASIS</th><th>EXPECTED</th><th>CHECK</th><th>RESULT</th></tr>
<tr><td>Sep 3</td><td>TOP 5 (equal weight)</td><td>basis</td><td>expected</td><td>Oct 3</td><td>PENDING</td></tr></table></section>
<section id="ledger"><h2>BOARD 07</h2><table><tr><th>CALL</th><th>WHAT WAS SAID</th><th>WHAT HAPPENED</th><th>SCORE</th></tr>
<tr><td>A</td><td>b</td><td>c</td><td>HIT</td></tr></table></section>
<!--R:runlog:ANY:APPEND:1-->
<!--ACX_RUNLOG
RUN|chat-1|CHAT|2026-09-04T03:45:02Z|chat:one|2026-09-04T03:45:02Z|aaaa|bbbb|1|PUBLISHED
RUN|daily-2|DAILY|2026-09-05T10:00:00Z|daily:2026-09-05|2026-09-05T10:20:00Z|bbbb|cccc|2|PUBLISHED
-->
<!--ACX_CANONICAL_STATE v43
{"meta":{"schemaVersion":"v43","artifactVersion":"V99","generatedAtUTC":"2026-09-11T10:29:12Z"},
 "models":{"ordering":{"id":"ENTRY_QUALITY_V44_2"}},"lastRefresh":{"boardsReordered":["stocks"]},
 "lastAction":{"scorecard":{"stocks":{"BUY":[-0.03,21],"WAIT":[0.002,13]},"crypto":{"BUY":[-0.01,5]}},"scorecardRecord":{"stocks":[5,5,1]}}}
-->
</body></html>"""
NOW = datetime(2026, 9, 11, 10, 45, tzinfo=UTC)


class LegacyParseTests(unittest.TestCase):
    def test_capsule_and_run_lines(self):
        capsule = legacy.extract_capsule(PAGE)
        self.assertEqual(capsule["meta"]["artifactVersion"], "V99")
        self.assertEqual(len(legacy.extract_run_lines(PAGE)), 2)
        with self.assertRaises(ValueError):
            legacy.extract_capsule("<html></html>")

    def test_sections_tables_cards_and_todos(self):
        sections, ticker = legacy.parse_page(PAGE)
        stocks = sections["stocks"]
        self.assertEqual(stocks.stamp, "Fri Sep 11, 6:41 AM — 6AM run: 2 of 2 re-quoted")
        self.assertEqual(stocks.tables[0].header[:3], ["#", "TKR", "PRICE"])
        self.assertEqual(stocks.tables[0].rows[0][1], "● AAA")
        self.assertEqual(stocks.tables[0].rows[0][-1], "The case text")
        self.assertEqual(sections["accounts"].cards[0]["val"], "$1,000.00")
        self.assertEqual(sections["action"].todos[0], {"title": "1 · Do X", "body": "Because Y"})
        self.assertEqual(ticker, ["6:41 AM RUN - hello", "6:41 AM RUN - hello"])
        self.assertEqual(
            sections["optimizer"].h3[0], "01 · CHARLES SCHWAB — TWO IRAs, ONE BOOK · $1,500.00"
        )


class MigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = legacy.migrate(PAGE, NOW)

    def test_boards_carry_legacy_zones_unscored(self):
        board = self.docs["boards/stocks"]
        self.assertEqual(board["status"], "LIVE")
        self.assertEqual(len(board["rows"]), 2)
        first = board["rows"][0]
        self.assertEqual(
            (first["symbol"], first["owned"], first["legacy_zone"], first["status"]),
            ("AAA", True, "HOLD", "LEGACY_UNSCORED"),
        )
        self.assertIsNone(first["scorecard"])
        self.assertEqual(first["cells"]["PRICE"], "$10.00")
        self.assertEqual(first["case"], "The case text")
        self.assertEqual(self.docs["boards/pumpfun"]["status"], "STALE")

    def test_two_schwab_accounts_stay_distinct(self):
        roth = self.docs["portfolios/schwab-roth"]
        rollover = self.docs["portfolios/schwab-rollover"]
        self.assertEqual(
            (roth["total_value"], roth["cash_value"], roth["cash_weight"]), (1000.0, 100.0, 0.1)
        )
        self.assertEqual((rollover["total_value"], rollover["cash_value"]), (500.0, 0.01))
        self.assertEqual(roth["distinct_from"], ["schwab-rollover"])
        self.assertEqual(roth["positions"], [])
        pooled = self.docs["portfolios/schwab-combined"]
        self.assertEqual(pooled["total_value"], 1500.0)
        self.assertEqual(pooled["positions"][0]["symbol"], "AAA")
        self.assertEqual(pooled["positions"][0]["weight"], 0.6)
        self.assertIsNone(self.docs["portfolios/coinbase"]["cash_value"])
        self.assertTrue(self.docs["portfolios/coinbase"]["excluded_from_book"])

    def test_calls_outcomes_learning_and_chain(self):
        rec = self.docs["recommendations/rec-legacy-001"]
        self.assertEqual(
            (rec["lens"], rec["stance"], rec["horizon_days"], rec["issued_at"]),
            ("legacy", "WATCH", 30, "2026-09-03T00:00:00Z"),
        )
        self.assertEqual(self.docs["outcomes/legacy-001"]["status"], "LEGACY")
        windows = {w["board"]: w["verdict"] for w in self.docs["learning/current"]["windows"]}
        self.assertTrue(windows["stocks"].startswith("INVERTED"))
        self.assertTrue(windows["crypto"].startswith("NOT COMPARABLE"))
        self.assertTrue(self.docs["runs/legacy-chain"]["chain_ok"])
        self.assertEqual(self.docs["legacy/ticker"]["items"], ["6:41 AM RUN - hello"])

    def test_migrated_documents_validate(self):
        for path, doc in self.docs.items():
            name = pipeline.SCHEMA_BY_COLLECTION.get(path.split("/")[0])
            if name is None or path in pipeline.UNSCHEMAED_DOCS:
                continue
            with self.subTest(path=path):
                self.assertEqual(schema.validate(doc, schema.load_schema(name)), [])


if __name__ == "__main__":
    unittest.main()
