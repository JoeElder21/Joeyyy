"""The rendered page: every view present, content escaped, statuses labelled."""

import copy
import json
import unittest
from pathlib import Path

from terminal import pipeline, render, store

FIXTURE = Path(__file__).resolve().parents[1] / "terminal" / "fixtures" / "synthetic_inputs.json"


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        inputs = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.store = store.MemoryStore()
        pipeline.run(copy.deepcopy(inputs), cls.store)
        cls.docs = {p: cls.store.get(p) for p in cls.store.paths()}
        cls.page = render.render(cls.docs)

    def test_every_view_is_rendered_once(self):
        for view_id, _label in render.VIEWS:
            with self.subTest(view=view_id):
                self.assertEqual(self.page.count(f'id="view-{view_id}"'), 1)
                self.assertIn(f'data-view="{view_id}"', self.page)
        self.assertEqual(len(render.VIEWS), 13)

    def test_content_and_labels(self):
        self.assertIn("<title>Savage Terminal R2</title>", self.page)
        self.assertIn("PROPOSED, not adopted", self.page)
        self.assertIn("starts 6:00 AM, ready 6:41 AM (41 min)", self.page)
        self.assertIn('id="store-status"', self.page)
        self.assertIn("Kept distinct from", self.page)
        self.assertIn("read-only research", self.page)

    def test_negatives_use_the_minus_sign_and_html_is_escaped(self):
        self.assertEqual(render.money(-12.5), "−$12.50")
        self.assertEqual(render.pct(-0.0123), "−1.2%")
        self.assertEqual(render.pct(None), "n/a")
        docs = copy.deepcopy(self.docs)
        docs["learning/current"]["lessons"].append(
            {"date": "x", "text": "<script>alert(1)</script>"}
        )
        page = render.render(docs)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)

    def test_embedded_snapshot_cannot_close_the_script_tag(self):
        # The payload carries the snapshot pointer, so the injection goes where the payload
        # actually reads from: the snapshot's own author-controlled version string.
        docs = copy.deepcopy(self.docs)
        docs["snapshots/current"]["version"] = "</script><b>bad</b>"
        page = render.render(docs)
        payload = page.split('<script id="snapshot-data" type="application/json">', 1)[1].split(
            "</script>", 1
        )[0]
        self.assertNotIn("<", payload)
        self.assertIn("\\u003c/script>", payload)

    def test_empty_store_still_renders_all_views(self):
        page = render.render({})
        for view_id, _ in render.VIEWS:
            self.assertIn(f'id="view-{view_id}"', page)

    def test_comment_opener_cannot_swallow_the_script_block(self):
        docs = copy.deepcopy(self.docs)
        docs["snapshots/current"]["version"] = "<!--<script>"
        page = render.render(docs)
        marker = '<script id="snapshot-data" type="application/json">'
        payload = page.split(marker, 1)[1].split("</script>", 1)[0]
        self.assertNotIn("<!--", payload)
        self.assertIn("<script>", page.split(marker, 1)[1].split("</script>", 1)[1])

    def test_views_are_readable_without_javascript_and_load_no_fonts(self):
        self.assertIn("<noscript><style>section.view{display:block}</style></noscript>", self.page)
        self.assertNotIn("fonts.googleapis.com", self.page)

    def test_a_board_of_pure_data_columns_keeps_every_column(self):
        docs = {
            "boards/holdings-equity": {
                "board_id": "holdings-equity",
                "title": "Holdings",
                "kind": "portfolio",
                "as_of": "2026-09-11T17:17:00Z",
                "status": "LIVE",
                "stamp": "now",
                "columns": ["QTY", "PRICE", "VALUE", "LIMIT"],
                "rows": [
                    {
                        "rank": 1,
                        "symbol": "EXA",
                        "owned": True,
                        "status": "LEGACY_UNSCORED",
                        "cells": {
                            "QTY": "12",
                            "PRICE": "$1.00",
                            "VALUE": "$12.00",
                            "LIMIT": "inside 13%",
                        },
                        "legacy_zone": None,
                        "scorecard": None,
                        "case": None,
                    }
                ],
                "notes": [],
                "rubric": None,
                "legacy_ordering": None,
            }
        }
        table = render.board_table(docs["boards/holdings-equity"])
        for header in ("QTY", "PRICE", "VALUE", "LIMIT"):
            self.assertIn(f"<th>{header}</th>", table)
        self.assertIn(">12<", table)

    def test_symbol_and_case_columns_are_still_folded_on_a_legacy_board(self):
        doc = {
            "board_id": "stocks",
            "title": "Legacy",
            "kind": "equity",
            "as_of": "2026-09-11T17:17:00Z",
            "status": "STALE",
            "stamp": "then",
            "columns": ["#", "TKR", "PRICE", "THE CASE"],
            "rows": [
                {
                    "rank": 1,
                    "symbol": "EXA",
                    "owned": False,
                    "status": "LEGACY_UNSCORED",
                    "cells": {"TKR": "EXA", "PRICE": "$1.00", "THE CASE": "words"},
                    "legacy_zone": "HOLD",
                    "scorecard": None,
                    "case": "words",
                }
            ],
            "notes": [],
            "rubric": None,
            "legacy_ordering": None,
        }
        table = render.board_table(doc)
        self.assertNotIn("<th>TKR</th>", table)
        self.assertIn("<th>ASSET</th>", table)
        self.assertIn("<th>THE CASE</th>", table)

    def test_limit_breaches_lead_the_today_view(self):
        docs = copy.deepcopy(self.docs)
        run = next(d for p, d in docs.items() if p.startswith("runs/") and "idempotency_key" in d)
        run["risk"] = [
            {
                "portfolio_id": "x",
                "label": "X",
                "positions": 1,
                "largest": {"asset": "EXA", "weight": 0.2},
                "cash_weight": 0.1,
                "breaches": ["EXA at 20.00% exceeds the 13% single-name ceiling"],
                "status": "REVIEW",
                "as_of": "2026-09-11T17:17:00Z",
                "verification": "screenshot-verified",
            }
        ]
        page = render.view_today(docs)
        self.assertIn("Limit breaches", page)
        self.assertIn("exceeds the 13% single-name ceiling", page)
        self.assertIn("never an automatic sale", page)

    def test_the_embedded_payload_is_only_the_snapshot_pointer(self):
        marker = '<script id="snapshot-data" type="application/json">'
        payload = self.page.split(marker, 1)[1].split("</script>", 1)[0]
        import json as _json

        embedded = _json.loads(payload.replace("\\u003c", "<"))
        self.assertEqual(list(embedded), ["snapshots/current"])
        self.assertEqual(
            embedded["snapshots/current"]["sha"], self.docs["snapshots/current"]["sha"]
        )
        self.assertLess(len(payload), 200_000)

    def test_document_text_is_escaped_in_the_rendered_body(self):
        docs = copy.deepcopy(self.docs)
        docs["learning/current"]["lessons"].append({"date": "x", "text": "</script><b>bad</b>"})
        page = render.render(docs)
        body = page.split('<script id="snapshot-data" type="application/json">', 1)[0]
        self.assertNotIn("</script><b>bad</b>", body)
        self.assertIn("&lt;/script&gt;&lt;b&gt;bad&lt;/b&gt;", body)

    def test_a_portfolio_board_shows_no_unscored_status_column(self):
        doc = {
            "board_id": "holdings-equity",
            "title": "Holdings",
            "kind": "portfolio",
            "as_of": "2026-09-11T17:17:00Z",
            "status": "LIVE",
            "stamp": "now",
            "columns": ["QTY", "VALUE"],
            "rows": [
                {
                    "rank": 1,
                    "symbol": "EXA",
                    "owned": True,
                    "status": "LEGACY_UNSCORED",
                    "cells": {"QTY": "12", "VALUE": "$12.00"},
                    "legacy_zone": None,
                    "scorecard": None,
                    "case": None,
                }
            ],
            "notes": [],
            "rubric": None,
            "legacy_ordering": None,
        }
        table = render.board_table(doc)
        self.assertNotIn("STATUS", table)
        self.assertNotIn("LEGACY_UNSCORED", table)
        self.assertIn("<th>VALUE</th>", table)
        doc["kind"] = "equity"
        self.assertIn("STATUS", render.board_table(doc))

    def test_breaches_name_the_view_they_were_measured_on(self):
        docs = copy.deepcopy(self.docs)
        run = next(d for p, d in docs.items() if p.startswith("runs/") and "idempotency_key" in d)
        run["risk"] = [
            {
                "portfolio_id": "combined",
                "label": "Combined view",
                "positions": 2,
                "largest": {"asset": "EXA", "weight": 0.2},
                "cash_weight": 0.1,
                "breaches": ["EXA at 20.00% exceeds the 13% single-name ceiling"],
                "status": "REVIEW",
                "as_of": "2026-09-11T17:17:00Z",
                "verification": "screenshot-verified",
            },
            {
                "portfolio_id": "quiet",
                "label": "Quiet account",
                "positions": 1,
                "largest": {"asset": "EXB", "weight": 0.01},
                "cash_weight": 0.5,
                "breaches": [],
                "status": "OK",
                "as_of": "2026-09-11T17:17:00Z",
                "verification": "screenshot-verified",
            },
        ]
        page = render.view_today(docs)
        self.assertIn("Combined view", page)
        self.assertIn("exceeds the 13% single-name ceiling", page)
        self.assertNotIn("<h4>Quiet account</h4>", page)

    def test_a_share_is_rendered_without_a_change_sign(self):
        self.assertEqual(render.share(0.1699), "16.99%")
        self.assertEqual(render.share(0.0), "0.00%")
        self.assertEqual(render.share(None), "n/a")
        self.assertEqual(render.pct(0.1699), "+17.0%")


if __name__ == "__main__":
    unittest.main()
