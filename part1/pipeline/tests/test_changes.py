import support
from support import DbTestCase, rec, ts

from load import load_all

T1 = "20261110T100000Z"
T2 = "20261110T110000Z"
T3 = "20261110T120000Z"
M = {"fake": support.FAKE}


def prod(key, **columns):
    return rec(key, columns={"retailer": "shop", **columns})


class ChangesTest(DbTestCase):
    def load(self):
        return load_all(self.conn, self.dir, M)

    def changes(self):
        return self._query("SELECT * FROM changes ORDER BY id")

    def test_first_load_writes_nothing(self):
        self.write_run("fake", "b", T1, records=[prod("a", price="12.99")]); self.load()
        self.assertEqual(self.changes(), [])

    def test_new_key_after_a_complete_look_appears(self):
        self.write_run("fake", "b", T1, records=[prod("a")]); self.load()
        self.write_run("fake", "b", T2, records=[prod("a"), prod("n")]); self.load()
        self.assertEqual([(c["change"], c["key"], c["table_name"], c["kind"], c["changed_at"], c["run_id"], c["field"])
                          for c in self.changes()], [("appeared", "n", "products", "product", ts(T2), T2, None)])

    def test_new_key_after_a_partial_look_does_not_appear(self):
        self.write_run("fake", "b", T1, status="partial", reason="x", records=[prod("a")]); self.load()
        self.write_run("fake", "b", T2, records=[prod("a"), prod("n")]); self.load()
        self.assertEqual(self.changes(), [])

    def test_changed_values_one_row_per_column(self):
        self.write_run("fake", "b", T1, records=[prod("a", price="12.99", rank=3, sponsored=False, availability="IN_STOCK")]); self.load()
        self.write_run("fake", "b", T2, records=[prod("a", price="10.50", rank=3, sponsored=True, availability=None)]); self.load()
        self.assertEqual(sorted((c["field"], c["old_value"], c["new_value"]) for c in self.changes()),
                         [("availability", "IN_STOCK", None), ("price", "12.99", "10.5"), ("sponsored", "false", "true")])
        self.assertEqual({c["change"] for c in self.changes()}, {"changed"})

    def test_equal_numbers_written_differently_are_not_a_change(self):
        self.write_run("fake", "b", T1, records=[prod("a", price="12.99", rating="4.50", review_count=30000000)]); self.load()
        self.write_run("fake", "b", T2, records=[prod("a", price="12.990", rating="4.5", review_count=30000000)]); self.load()
        self.assertEqual(self.changes(), [])

    def test_large_numbers_are_plain_decimal_text(self):
        self.write_run("fake", "b", T1, records=[prod("a", review_count=30000000, price="100")]); self.load()
        self.write_run("fake", "b", T2, records=[prod("a", review_count=40000000, price="200")]); self.load()
        self.assertEqual(sorted((c["field"], c["old_value"], c["new_value"]) for c in self.changes()),
                         [("price", "100", "200"), ("review_count", "30000000", "40000000")])

    def test_untracked_and_left_out_columns_are_not_compared(self):
        self.write_run("fake", "b", T1, records=[prod("a", price="5", title="old")]); self.load()
        self.write_run("fake", "b", T2, records=[prod("a", title="new")]); self.load()   # price left out, title not tracked
        self.assertEqual(self.changes(), [])

    def test_ended_by_absence_then_reappeared(self):
        self.write_run("fake", "b", T1, records=[prod("a"), prod("b")]); self.load()
        self.write_run("fake", "b", T2, records=[prod("a")]); self.load()
        self.write_run("fake", "b", T3, records=[prod("a"), prod("b")]); self.load()
        self.assertEqual([(c["change"], c["key"], c["changed_at"]) for c in self.changes()],
                         [("ended", "b", ts(T2)), ("reappeared", "b", ts(T3))])

    def test_source_date_policy(self):
        ad = lambda key, shown: rec(key, kind="ad", table="ads", columns={"channel": "google", "last_shown_at": shown})
        self.write_run("fake", "b", T1, records=[ad("live", "2026-11-09T00:00:00Z"), ad("old", "2026-10-01T00:00:00Z")]); self.load()
        self.assertEqual(self.changes(), [])                       # "old" was inserted already ended
        later = "20261120T100000Z"
        self.write_run("fake", "b", later, records=[ad("live", "2026-11-09T00:00:00Z"), ad("old", "2026-10-02T00:00:00Z")]); self.load()
        self.assertEqual([(c["change"], c["key"], c["changed_at"]) for c in self.changes()], [("ended", "live", ts(later))])
        again = "20261121T100000Z"
        self.write_run("fake", "b", again, records=[ad("live", "2026-11-21T00:00:00Z")]); self.load()
        self.assertEqual([(c["change"], c["key"]) for c in self.changes()][1:], [("reappeared", "live")])

    def test_second_load_superseded_and_failed_runs_write_nothing(self):
        self.write_run("fake", "b", T1, records=[prod("a")]); self.load()
        self.write_run("fake", "b", T3, records=[prod("a"), prod("n")]); self.load()
        before = self.changes()
        self.assertEqual(len(before), 1)
        self.load()                                                                    # same files again
        self.write_run("fake", "b", T2, records=[prod("a"), prod("x")]); self.load()   # older than T3: superseded
        bad = "20261110T130000Z"
        self.write_run("fake", "b", bad, records=[prod("a", price="1"), rec("z", bad=True)]); self.load()   # fails to map
        self.assertEqual(self.changes(), before)

    def test_appearance_follows_the_rows_own_scope(self):
        self.write_run("fake", "b", T1, records=[rec("a", scope="s1", columns={"retailer": "shop"}),
                                                rec("b", scope="s2", columns={"retailer": "shop"})],
                       extra={"scopes": [["s1", "ok", ""], ["s2", "partial", "x"]]}); self.load()
        self.write_run("fake", "b", T2, records=[rec("a", scope="s1", columns={"retailer": "shop"}),
                                                rec("n1", scope="s1", columns={"retailer": "shop"}),
                                                rec("b", scope="s2", columns={"retailer": "shop"}),
                                                rec("n2", scope="s2", columns={"retailer": "shop"})],
                       extra={"scopes": [["s1", "ok", ""], ["s2", "ok", ""]]}); self.load()
        self.assertEqual([(c["change"], c["key"]) for c in self.changes()], [("appeared", "n1")])


if __name__ == "__main__":
    import unittest
    unittest.main()
