import copy
import json
import unittest
from pathlib import Path

import support  # noqa: F401  (puts part1/pipeline on sys.path)
from mappers.google_results import ENDING, SOURCE, map_run
from model import MapError, Scope

SAMPLE = Path(__file__).resolve().parents[2] / "collectors" / "06_google_results" / "samples" / "apify" / "trial_run_dataset.json"
ITEMS = {i["searchQuery"]["term"]: i for i in json.loads(SAMPLE.read_text())}

ADS = Scope("ads", "could_not_look", "ads are not collected: no tested Actor returned the ads a person saw for the same term")
RUN_OK = {"status": "ok", "reason": ""}


def record(term, index, error=None, serp="sample"):
    if serp == "sample":
        serp = copy.deepcopy(ITEMS[term])
    return {"key": term, "kind": "search_results_page",
            "url": "https://www.google.com/search?q=" + term.replace(" ", "+") + "&gl=us&hl=en",
            "fetched_at": "2026-11-10T09:00:00Z",
            "raw": {"keyword_index": index, "serp": serp, "error": error, "ads": "could_not_look"}}


class GoogleResultsTest(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(SOURCE, "google_results")
        self.assertEqual(ENDING, {("search_rankings", "search_result"): "absent"})

    def test_first_row_of_a_page(self):
        rec = record("death wish coffee", 4)
        m = map_run(RUN_OK, [rec])
        self.assertEqual(len(m.rows), 6)
        row = m.rows[0]
        self.assertEqual((row.table, row.kind, row.scope, row.url, row.fetched_at),
                         ("search_rankings", "search_result", "death wish coffee", rec["url"], "2026-11-10T09:00:00Z"))
        self.assertEqual(row.key, "death wish coffee|https://www.deathwishcoffee.com/")
        self.assertIs(row.raw, rec["raw"])
        self.assertEqual(row.columns, {
            "keyword": "death wish coffee", "keyword_rank": 4, "position": 1,
            "result_url": "https://www.deathwishcoffee.com/?srsltid=AYCX9vLQQ71SspnNx9eznBDBzCG25g-UOeSVbNtQ4yui-JWfuM6ewdyM",
            "domain": "deathwishcoffee.com", "title": "Death Wish Coffee: #1 Organic and #1 Fair Trade Coffee",
            "description": "Bold, Smooth and Delicious since 2012. We source USDA Organic and Fair Trade Certified™ arabica and robusta coffee beans from India, Peru, and other\u00a0...",
            "result_type": "organic"})

    def test_other_parameters_are_kept_and_domain_has_no_www(self):
        rows = map_run(RUN_OK, [record("batiste dry shampoo", 1)]).rows
        self.assertEqual(rows[2].key, "batiste dry shampoo|https://www.ulta.com/p/original-dry-shampoo-xlsImpprod2040049?sku=2515942")
        self.assertEqual((rows[2].columns["domain"], rows[3].columns["domain"]), ("ulta.com", "batiste-hair.eu"))
        self.assertEqual([r.columns["position"] for r in rows], list(range(1, 8)))

    def test_repeated_url_keeps_the_first(self):
        serp = copy.deepcopy(ITEMS["jinx dog food"])
        serp["organicResults"] = serp["organicResults"][:2]
        dup = copy.deepcopy(serp["organicResults"][0])
        dup["position"], dup["title"] = 3, "again"
        dup["url"] = dup["url"].split("?")[0] + "?srsltid=OTHER"
        serp["organicResults"].append(dup)
        rows = map_run(RUN_OK, [record("jinx dog food", 1, serp=serp)]).rows
        self.assertEqual([r.columns["position"] for r in rows], [1, 2])

    def test_scopes_for_a_complete_run(self):
        m = map_run(RUN_OK, [record("death wish coffee", 1), record("jinx dog food", 2)])
        self.assertEqual(m.scopes, [Scope("death wish coffee", "ok", ""), Scope("jinx dog food", "ok", ""), ADS])
        self.assertEqual({r.scope for r in m.rows}, {"death wish coffee", "jinx dog food"})
        self.assertEqual(m.not_fetched, 0)

    def test_incomplete_run_not_fetched_records(self):
        run = {"status": "partial", "reason": "missing=1; actor_error=1; no_organic_results=1"}
        recs = [record("death wish coffee", 1), record("a", 2, "missing", None), record("b", 3, "actor_error", {"#error": True}),
                record("c", 4, "no_organic_results", {"#error": False, "organicResults": []})]
        m = map_run(run, recs)
        self.assertEqual(len(m.rows), 6)
        self.assertEqual(m.not_fetched, 3)
        self.assertEqual(m.scopes, [Scope("death wish coffee", "ok", ""), Scope("a", "could_not_look", "missing"),
                                    Scope("b", "could_not_look", "actor_error"),
                                    Scope("c", "could_not_look", "no_organic_results"), ADS])

    def test_no_records_gives_all_scope(self):
        run = {"status": "could_not_look", "reason": "missing_token"}
        m = map_run(run, [])
        self.assertEqual(m.scopes, [ADS, Scope("all", "could_not_look", "missing_token")])
        self.assertEqual((m.rows, m.not_fetched), ([], 0))

    def test_unknown_kind_and_unknown_error(self):
        bad = record("jinx dog food", 1)
        bad["kind"] = "other"
        with self.assertRaisesRegex(MapError, "^jinx dog food"):
            map_run(RUN_OK, [bad])
        with self.assertRaisesRegex(MapError, "^jinx dog food"):
            map_run(RUN_OK, [record("jinx dog food", 1, "weird")])

    def test_unconvertible_values(self):
        for change in (lambda s: s["organicResults"][0].pop("position"),
                       lambda s: s["organicResults"][0].pop("url"),
                       lambda s: s["organicResults"][0].update(url="not a url"),
                       lambda s: s.pop("organicResults")):
            serp = copy.deepcopy(ITEMS["jinx dog food"])
            change(serp)
            with self.assertRaisesRegex(MapError, "^jinx dog food"):
                map_run(RUN_OK, [record("jinx dog food", 1, serp=serp)])
        with self.assertRaisesRegex(MapError, "^jinx dog food"):
            map_run(RUN_OK, [record("jinx dog food", None)])
        with self.assertRaisesRegex(MapError, "^jinx dog food"):
            map_run(RUN_OK, [record("jinx dog food", 1, serp=None)])


if __name__ == "__main__":
    unittest.main()
