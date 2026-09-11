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
        docs = copy.deepcopy(self.docs)
        docs["learning/current"]["lessons"].append({"date": "x", "text": "</script><b>bad</b>"})
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
        docs["learning/current"]["lessons"].append({"date": "x", "text": "<!--<script>"})
        page = render.render(docs)
        marker = '<script id="snapshot-data" type="application/json">'
        payload = page.split(marker, 1)[1].split("</script>", 1)[0]
        self.assertNotIn("<!--", payload)
        self.assertIn("<script>", page.split(marker, 1)[1].split("</script>", 1)[1])

    def test_views_are_readable_without_javascript_and_load_no_fonts(self):
        self.assertIn("<noscript><style>section.view{display:block}</style></noscript>", self.page)
        self.assertNotIn("fonts.googleapis.com", self.page)


if __name__ == "__main__":
    unittest.main()
