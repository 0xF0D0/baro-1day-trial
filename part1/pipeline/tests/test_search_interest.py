import importlib.util
import unittest
from datetime import date
from pathlib import Path

import support  # noqa: F401  (puts part1/pipeline on sys.path)
from mappers.search_interest import ENDING, map_run
from model import MapError, Scope

COLLECTOR = Path(__file__).resolve().parents[2] / "collectors" / "07_search_interest"
_spec = importlib.util.spec_from_file_location("collector_07_search_interest", COLLECTOR / "source_collector.py")
collector = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(collector)
explore_url, parse_multiline = collector.explore_url, collector.parse_multiline

SAMPLES = COLLECTOR / "samples"
W = "2025-11-10 2026-11-10"
SET = ["Batiste dry shampoo", "Living Proof shampoo", "Death Wish Coffee", "Black Rifle Coffee", "Jinx dog food"]
OK = {"status": "ok", "reason": "", "extra": {"window": W}}
FETCHED = "2026-11-10T12:00:00Z"


def series(name, terms):
    lines = (SAMPLES / name).read_text(encoding="utf-8").split("\n")
    return parse_multiline(lines[0], "\n".join(lines[2:]), terms, W)


def solo_record(term, name, i):
    req, points = series(name, [term])
    p = points[i]
    return {"key": f"{term}|US|{p['time']}", "kind": "interest_point", "url": explore_url([term], W),
            "fetched_at": FETCHED, "raw": {"point": p, "series_index": 0, "request": req}}


def compared_record(term, i):
    req, points = series("multiline_compare5_qualified_fixed.txt", SET)
    p = points[i]
    return {"key": f"{term}|US|{p['time']}|vs:{','.join(SET)}", "kind": "interest_point_compared",
            "url": explore_url(SET, W), "fetched_at": FETCHED,
            "raw": {"point": p, "series_index": SET.index(term), "request": req}}


class SearchInterestTest(unittest.TestCase):
    def test_solo_point(self):
        rec = solo_record("Batiste dry shampoo", "multiline_batiste_dry_shampoo_fixed.txt", 0)
        m = map_run(OK, [rec])
        row = m.rows[0]
        self.assertEqual((row.table, row.kind, row.key, row.scope, row.url, row.fetched_at),
                         ("search_interest", "interest_point", rec["key"], "all", rec["url"], FETCHED))
        self.assertIs(row.raw, rec["raw"])
        self.assertEqual(row.columns, {"keyword": "Batiste dry shampoo", "series": "solo", "week_start": date(2025, 11, 9),
                                       "value": 21, "has_data": True, "is_partial": False, "geo": "US"})
        self.assertEqual((m.scopes, m.not_fetched), ([Scope("all", "ok", "")], 0))

    def test_partial_week(self):
        c = map_run(OK, [solo_record("Batiste dry shampoo", "multiline_batiste_dry_shampoo_fixed.txt", 52)]).rows[0].columns
        self.assertEqual((c["week_start"], c["value"], c["is_partial"]), (date(2026, 11, 8), 22, True))

    def test_compared_point(self):
        rec = compared_record("Black Rifle Coffee", 0)
        row = map_run(OK, [rec]).rows[0]
        self.assertEqual((row.table, row.kind), ("search_interest", "interest_point_compared"))
        self.assertEqual(row.columns, {"keyword": "Black Rifle Coffee", "series": "compared", "week_start": date(2025, 11, 9),
                                       "value": 100, "has_data": True, "is_partial": False, "geo": "US"})
        c = map_run(OK, [compared_record("Jinx dog food", 52)]).rows[0].columns
        self.assertEqual((c["keyword"], c["value"], c["is_partial"]), ("Jinx dog food", 7, True))

    def test_no_data_point(self):
        rec = solo_record("Batiste dry shampoo", "multiline_batiste_dry_shampoo_fixed.txt", 0)
        rec["raw"]["point"] = {**rec["raw"]["point"], "value": [0], "hasData": [False]}
        c = map_run(OK, [rec]).rows[0].columns
        self.assertEqual((c["value"], c["has_data"]), (0, False))

    def test_scopes_follow_run(self):
        run = {"status": "partial", "reason": "compared: blocked", "extra": {"window": W}}
        self.assertEqual(map_run(run, []).scopes, [Scope("all", "partial", "compared: blocked")])
        run = {"status": "could_not_look", "reason": "solo: blocked; compared: blocked", "extra": {"window": W}}
        m = map_run(run, [])
        self.assertEqual((m.rows, m.not_fetched, m.scopes),
                         ([], 0, [Scope("all", "could_not_look", "solo: blocked; compared: blocked")]))

    def test_ending(self):
        self.assertEqual(ENDING, {("search_interest", "interest_point"): "never",
                                  ("search_interest", "interest_point_compared"): "never"})

    def test_unknown_inputs_are_errors(self):
        good = solo_record("Batiste dry shampoo", "multiline_batiste_dry_shampoo_fixed.txt", 3)
        bad_time = {**good, "key": "k1", "raw": {**good["raw"], "point": {**good["raw"]["point"], "time": "soon"}}}
        bad_index = {**good, "key": "k2", "raw": {**good["raw"], "series_index": 4}}
        bad_value = {**good, "key": "k3", "raw": {**good["raw"], "point": {**good["raw"]["point"], "value": ["x"]}}}
        for bad in ({**good, "key": "k0", "kind": "other"}, bad_time, bad_index, bad_value):
            with self.assertRaises(MapError) as e:
                map_run(OK, [bad])
            self.assertTrue(str(e.exception).startswith(bad["key"]))


if __name__ == "__main__":
    unittest.main()
