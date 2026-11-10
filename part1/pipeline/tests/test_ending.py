from datetime import datetime, timezone

import support
from support import DbTestCase, rec, ts

from load import load_all

T1 = "20261110T100000Z"
T2 = "20261110T110000Z"
T3 = "20261110T120000Z"
M = {"fake": support.FAKE}


def by_key(rows):
    return {r["key"]: r for r in rows}


class EndingTest(DbTestCase):
    def load(self):
        return load_all(self.conn, self.dir, M)

    def test_ok_run_ends_missing_and_inserts_new(self):
        self.write_run("fake", "b", T1, records=[rec("a"), rec("b"), rec("c")]); self.load()
        self.write_run("fake", "b", T2, records=[rec("a"), rec("c"), rec("d")])
        out = [o for o in self.load() if o.run_id == T2][0]
        self.assertEqual((out.inserted, out.updated, out.ended), (1, 2, 1))
        p = by_key(self.table("products"))
        self.assertEqual((p["b"]["ended_at"], p["b"]["last_seen_at"]), (ts(T2), ts(T1)))
        self.assertEqual((p["a"]["first_seen_at"], p["a"]["last_seen_at"], p["a"]["ended_at"]), (ts(T1), ts(T2), None))
        self.assertEqual((p["d"]["first_seen_at"], p["d"]["ended_at"]), (ts(T2), None))

    def test_partial_run_ends_nothing(self):
        self.write_run("fake", "b", T1, records=[rec("a"), rec("b"), rec("c")]); self.load()
        self.write_run("fake", "b", T2, status="partial", reason="x", records=[rec("a")]); self.load()
        self.assertEqual([r["ended_at"] for r in self.table("products")], [None, None, None])

    def test_item_returns(self):
        self.write_run("fake", "b", T1, records=[rec("a"), rec("b")]); self.load()
        self.write_run("fake", "b", T2, records=[rec("a")]); self.load()
        self.assertEqual(by_key(self.table("products"))["b"]["ended_at"], ts(T2))
        self.write_run("fake", "b", T3, records=[rec("a"), rec("b")]); self.load()
        b = by_key(self.table("products"))["b"]
        self.assertEqual((b["first_seen_at"], b["last_seen_at"], b["ended_at"]), (ts(T1), ts(T3), None))

    def test_never_kind_is_not_ended(self):
        self.write_run("fake", "b", T1, records=[rec("p"), rec("r1", kind="review", table="reviews")]); self.load()
        self.write_run("fake", "b", T2, records=[rec("p")]); self.load()
        self.assertEqual(self.table("reviews")[0]["ended_at"], None)

    def test_only_ok_scope_ends(self):
        scopes = lambda s2: {"scopes": [["s1", "ok", ""], ["s2", s2, "" if s2 == "ok" else "blocked"]]}
        self.write_run("fake", "b", T1, records=[rec("a", scope="s1"), rec("b", scope="s2")], extra=scopes("ok")); self.load()
        self.write_run("fake", "b", T2, status="partial", reason="s2: blocked", extra=scopes("could_not_look")); self.load()
        p = by_key(self.table("products"))
        self.assertEqual((p["a"]["ended_at"], p["b"]["ended_at"]), (ts(T2), None))

    def test_source_date(self):
        ad = lambda key, shown: rec(key, kind="ad", table="ads", columns={"channel": "google", "last_shown_at": shown})
        self.write_run("fake", "b", T1, status="partial", reason="x",
                       records=[ad("old", "2026-11-06T00:00:00Z"), ad("new", "2026-11-09T00:00:00Z")]); self.load()
        a = by_key(self.table("ads"))
        self.assertEqual((a["old"]["ended_at"], a["new"]["ended_at"]), (datetime(2026, 11, 6, tzinfo=timezone.utc), None))
        self.write_run("fake", "b", T2, records=[ad("old", "2026-11-10T00:00:00Z")]); self.load()
        a = by_key(self.table("ads"))
        self.assertEqual((a["old"]["ended_at"], a["new"]["ended_at"]), (None, None))   # reopened; absence does not end a source_date kind

    def test_not_fetched_keeps_stored_row(self):
        self.write_run("fake", "b", T1, records=[rec("a", scope="s1")], extra={"scopes": [["s1", "ok", ""]]}); self.load()
        self.write_run("fake", "b", T2, status="partial", reason="x",
                       records=[rec("a", scope="s1", state="not_fetched")], extra={"scopes": [["s1", "partial", "x"]]}); self.load()
        a = self.table("products")[0]
        self.assertEqual((a["last_seen_at"], a["ended_at"], a["last_run_id"]), (ts(T1), None, T1))


if __name__ == "__main__":
    import unittest
    unittest.main()
