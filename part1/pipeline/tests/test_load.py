import json
import types
from decimal import Decimal

import support
from support import DbTestCase, rec, ts

from load import load_all
from model import MappedRun

T1 = "20261110T100000Z"
T2 = "20261110T110000Z"
M = {"fake": support.FAKE}


class LoadTest(DbTestCase):
    def load(self):
        return load_all(self.conn, self.dir, M)

    def test_first_run_inserts(self):
        self.write_run("fake", "b", T1, records=[rec("a"), rec("b")])
        out = self.load()
        self.assertEqual([(o.result, o.inserted, o.updated, o.ended) for o in out], [("applied", 2, 0, 0)])
        rows = self.table("products")
        self.assertEqual([r["key"] for r in rows], ["a", "b"])
        for r in rows:
            self.assertEqual((r["first_seen_at"], r["last_seen_at"], r["ended_at"]), (ts(T1), ts(T1), None))
            self.assertEqual((r["source"], r["brand"], r["kind"], r["scope"], r["last_run_id"]),
                             ("fake", "b", "product", "all", T1))
            self.assertEqual(r["url"], "https://example.test/" + r["key"])
            self.assertEqual(r["raw"], {"table": "products", "scope": "all"})
        self.assertEqual([(r["result"], r["status"], r["records"]) for r in self.table("runs")],
                         [("applied", "ok", 2)])
        self.assertEqual([(r["scope"], r["status"], r["reason"]) for r in self.table("run_scopes")],
                         [("all", "ok", "")])

    def test_same_run_twice_changes_nothing(self):
        self.write_run("fake", "b", T1, records=[rec("a")])
        self.load()
        before = (self.table("products"), self.table("runs"), self.table("run_scopes"))
        self.assertEqual([o.result for o in self.load()], ["already_loaded"])
        self.assertEqual((self.table("products"), self.table("runs"), self.table("run_scopes")), before)

    def test_could_not_look_run_is_recorded(self):
        self.write_run("fake", "b", T1, status="could_not_look", reason="blocked")
        self.assertEqual([o.result for o in self.load()], ["applied"])
        self.assertEqual(self.table("products"), [])
        self.assertEqual([(r["scope"], r["status"], r["reason"]) for r in self.table("run_scopes")],
                         [("all", "could_not_look", "blocked")])

    def test_older_run_after_newer_is_superseded(self):
        self.write_run("fake", "b", T2, records=[rec("a")])
        self.load()
        self.write_run("fake", "b", T1, records=[rec("a"), rec("b")])
        self.assertEqual([o.result for o in self.load()], ["superseded", "already_loaded"])
        self.assertEqual([r["key"] for r in self.table("products")], ["a"])
        self.assertEqual([(r["run_id"], r["result"]) for r in self.table("runs")],
                         [(T1, "superseded"), (T2, "applied")])
        self.assertEqual([r["run_id"] for r in self.table("run_scopes")], [T2])

    def test_rejected_record_fails_only_its_run(self):
        self.write_run("fake", "b1", T1, records=[rec("x", bad=True), rec("y")])
        self.write_run("fake", "b2", T1, records=[rec("z")])
        out = self.load()
        self.assertEqual([o.result for o in out], ["failed", "applied"])
        self.assertIn("x", out[0].error)
        self.assertEqual((out[0].source, out[0].brand, out[0].run_id), ("fake", "b1", T1))
        self.assertEqual([(r["brand"], r["key"]) for r in self.table("products")], [("b2", "z")])
        self.assertEqual([r["brand"] for r in self.table("runs")], ["b2"])

    def test_not_fetched_record_gives_no_row(self):
        self.write_run("fake", "b", T1, records=[rec("a"), rec("b", state="not_fetched")])
        out = self.load()
        self.assertEqual((out[0].result, out[0].inserted, out[0].not_fetched), ("applied", 1, 1))
        self.assertEqual([r["key"] for r in self.table("products")], ["a"])

    def test_left_out_column_keeps_value(self):
        self.write_run("fake", "b", T1,
                       records=[rec("a", columns={"retailer": "shop", "title": "T", "price": "9.99"})])
        self.load()
        self.write_run("fake", "b", T2, records=[rec("a", columns={"retailer": "shop", "title": None})])
        self.load()
        row = self.table("products")[0]
        self.assertEqual((row["title"], row["price"], row["last_run_id"]), (None, Decimal("9.99"), T2))

    def test_empty_run_without_mapper_is_recorded(self):
        self.write_run("nomap", "b", T1, status="could_not_look", reason="blocked")
        self.write_run("nomap", "b", T2, records=[rec("a")])
        self.assertEqual([o.result for o in self.load()], ["empty_no_mapper", "no_mapper"])
        self.assertEqual([(r["run_id"], r["result"]) for r in self.table("runs")], [(T1, "empty_no_mapper")])
        self.assertEqual([(r["scope"], r["status"]) for r in self.table("run_scopes")],
                         [("all", "could_not_look")])

    def test_same_key_twice_later_wins(self):
        cols = lambda t: {"retailer": "shop", "title": t}
        self.write_run("fake", "b", T1,
                       records=[rec("a", columns=cols("first")), rec("a", columns=cols("second"))])
        out = self.load()
        self.assertEqual((out[0].result, out[0].inserted), ("applied", 1))
        self.assertEqual([r["title"] for r in self.table("products")], ["second"])

    def test_unicode_line_separators_inside_a_record_do_not_split_it(self):
        odd = "a b c\u0085d"
        p = self.write_run("fake", "b", T1, records=[rec("a", note=odd)])
        p.with_name(T1 + ".jsonl").write_text(
            json.dumps(rec("a", note=odd), ensure_ascii=False) + "\n", encoding="utf-8")
        out = self.load()
        self.assertEqual([(o.result, o.inserted) for o in out], [("applied", 1)])
        self.assertEqual(self.table("products")[0]["raw"]["note"], odd)

    def test_broken_records_file_fails_run(self):
        p = self.write_run("fake", "b1", T1, records=[rec("a")])
        with open(p.with_name(T1 + ".jsonl"), "a") as f:
            f.write("not json\n")
        q = self.write_run("fake", "b2", T1, records=[rec("a")])
        q.with_name(T1 + ".jsonl").unlink()
        out = self.load()
        self.assertEqual([o.result for o in out], ["failed", "failed"])
        self.assertIn(T1 + ".jsonl:2: not JSON", out[0].error)
        self.assertIn("records file missing", out[1].error)
        self.assertEqual(self.table("runs"), [])

    def test_database_error_fails_whole_run(self):
        self.write_run("fake", "b1", T1, records=[rec("a"), rec("x", columns={"retailer": "shop", "price": "abc"})])
        self.write_run("fake", "b2", T1, records=[rec("z")])
        out = self.load()
        self.assertEqual([(o.source, o.brand, o.run_id, o.status, o.result) for o in out],
                         [("fake", "b1", T1, "ok", "failed"), ("fake", "b2", T1, "ok", "applied")])
        self.assertTrue(out[0].error)
        self.assertNotIn("\n", out[0].error)
        self.assertEqual([(r["brand"], r["key"]) for r in self.table("products")], [("b2", "z")])
        self.assertEqual([r["brand"] for r in self.table("runs")], ["b2"])
        self.assertEqual([r["brand"] for r in self.table("run_scopes")], ["b2"])

    def test_row_scope_must_be_a_returned_scope(self):
        self.write_run("fake", "b", T1, records=[rec("a", scope="s9")], extra={"scopes": [["s1", "ok", ""]]})
        out = self.load()
        self.assertEqual(out[0].result, "failed")
        self.assertTrue(out[0].error.startswith("a")); self.assertIn("s9", out[0].error)
        self.assertEqual(self.table("runs"), [])

    def test_bad_scope_status_fails_run(self):
        self.write_run("fake", "b", T1, records=[rec("a", scope="s1")], extra={"scopes": [["s1", "OK", ""]]})
        out = self.load()
        self.assertEqual(out[0].result, "failed"); self.assertIn("OK", out[0].error)

    def test_bad_ending_policy_fails_run(self):
        bad = types.SimpleNamespace(SOURCE="fake", ENDING={**support.FAKE.ENDING, ("products", "product"): "absnet"}, map_run=support.FAKE.map_run)
        self.write_run("fake", "b", T1, records=[rec("a")])
        out = load_all(self.conn, self.dir, {"fake": bad})
        self.assertEqual(out[0].result, "failed"); self.assertIn("absnet", out[0].error)

    def test_mapper_without_scopes_fails_run(self):
        empty = types.SimpleNamespace(SOURCE="fake", ENDING=support.FAKE.ENDING, map_run=lambda run, records: MappedRun(rows=[], scopes=[]))
        self.write_run("fake", "b", T1)
        out = load_all(self.conn, self.dir, {"fake": empty})
        self.assertEqual((out[0].result, out[0].error), ("failed", "mapper returned no scopes"))

    def test_unknown_column_fails_run(self):
        self.write_run("fake", "b", T1, records=[rec("a", columns={"retailer": "shop", "nope": 1})])
        self.assertEqual([o.result for o in self.load()], ["failed"])


if __name__ == "__main__":
    import unittest
    unittest.main()
