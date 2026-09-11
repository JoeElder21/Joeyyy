"""Store adapters, path grammar, immutability and write plans."""

import tempfile
import unittest
from pathlib import Path

from terminal import store


class StoreTests(unittest.TestCase):
    def test_path_grammar(self):
        self.assertEqual(store.split_path("boards/b1"), ("boards", "b1"))
        self.assertEqual(store.split_path("data/users/u1/profile"), ("data/users/u1", "profile"))
        for bad in ("boards", "boards/b1/rows", "boards/..", "boards/a b", ""):
            with self.subTest(path=bad), self.assertRaises(ValueError):
                store.split_path(bad)

    def test_memory_store_round_trip_and_isolation(self):
        s = store.MemoryStore()
        s.set("boards/b1", {"rows": [1]})
        doc = s.get("boards/b1")
        doc["rows"].append(2)
        self.assertEqual(s.get("boards/b1"), {"rows": [1]})
        self.assertEqual(s.list("boards"), [("b1", {"rows": [1]})])
        self.assertIsNone(s.get("boards/missing"))
        s.delete("boards/b1")
        self.assertEqual(s.paths(), [])

    def test_recommendations_are_immutable(self):
        s = store.MemoryStore()
        s.set("recommendations/r1", {"stance": "BUY"})
        s.set("recommendations/r1", {"stance": "BUY"})
        with self.assertRaises(store.ImmutableDocumentError):
            s.set("recommendations/r1", {"stance": "SELL"})
        with self.assertRaises(store.ImmutableDocumentError):
            s.delete("recommendations/r1")
        self.assertEqual(
            store.immutable_violations(
                {"recommendations/r1": {"a": 1}}, {"recommendations/r1": {"a": 2}}
            ),
            ["recommendations/r1"],
        )

    def test_document_checks(self):
        self.assertTrue(store.check_document("nope/x", {}))
        self.assertTrue(store.check_document("boards/x", []))
        self.assertTrue(store.check_document("boards/x", {"big": "x" * (store.MAX_DOC_BYTES + 1)}))
        self.assertEqual(store.check_document("boards/x", {"ok": True}), [])

    def test_json_dir_store_persists_and_ignores_non_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = store.JsonDirStore(root)
            first.set("boards/b1", {"rows": [1]})
            (root / "run_report.json").write_text("{}", encoding="utf-8")
            second = store.JsonDirStore(root)
            self.assertEqual(second.paths(), ["boards/b1"])
            self.assertEqual(second.get("boards/b1"), {"rows": [1]})
            second.delete("boards/b1")
            self.assertFalse((root / "boards" / "b1.json").exists())

    def test_write_plan_batches(self):
        docs = {f"boards/b{i}": {"i": i} for i in range(120)}
        plan = store.write_plan(docs)
        self.assertEqual([len(b) for b in plan], [50, 50, 20])
        self.assertEqual(
            plan[0][0], {"op": "set", "collection": "boards", "doc_id": "b0", "data": {"i": 0}}
        )
        with self.assertRaises(ValueError):
            store.write_plan({"nope/x": {}})


if __name__ == "__main__":
    unittest.main()
