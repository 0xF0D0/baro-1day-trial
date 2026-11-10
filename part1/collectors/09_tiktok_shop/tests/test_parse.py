import copy, json, sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import source_collector as sc

SAMPLES = Path(__file__).resolve().parents[3] / "collectors" / "09_tiktok_shop" / "samples" / "apify"
DWC = "death wish coffee"
IDS2 = ["1732222721408012710", "1732457338433802545"]


def load(name): return json.loads((SAMPLES / name).read_text())


def tracked(rows, ids): return sc.classify_part(rows, "tracked", "run1", ids, "x", "2026-11-10T11:00:00Z")


def search(rows): return sc.classify_part(rows, "search", "run1", [], DWC, "2026-11-10T11:00:00Z")


class ParseTests(unittest.TestCase):
    def test_cap(self):
        self.assertEqual([sc.charge_cap_usd(n) for n in (20, 10, 1)], ["0.04184", "0.02194", "0.00403"])

    def test_search_sample(self):
        r = search(load("search_death_wish_coffee_20.items.json"))
        self.assertEqual((len(r["records"]), r["ranks_complete"], sc.part_problems(r, "search")), (20, True, []))
        self.assertEqual(r["records"][0]["key"], "search/death wish coffee/1732222721408012710")
        self.assertEqual(r["records"][0]["fetched_at"], "2026-11-10T10:53:42Z")
        self.assertEqual(sum(x["raw"]["reviews_removed"] for x in r["records"]), 59)
        self.assertFalse(any("reviews" in x["raw"]["item"] for x in r["records"]))

    def test_search_short(self):
        rows = [x for x in load("search_death_wish_coffee_20.items.json") if x["rank"] != 20]
        self.assertEqual(sc.part_problems(search(rows), "search"), ["fetched=19/20"])

    def test_tracked(self):
        rows = load("product_ids_2.items.json")
        r = tracked(rows, IDS2)
        self.assertEqual(([x["raw"]["item_state"] for x in r["records"]], sc.part_problems(r, "tracked")), (["fetched"] * 2, []))
        r = tracked(rows, IDS2 + ["1729999999999999999"])
        self.assertEqual(r["records"][2]["raw"]["item_state"], "missing")
        self.assertEqual(sc.part_problems(r, "tracked"), ["missing=1"])

    def test_unavailable_and_no_products(self):
        r = tracked(load("product_id_not_available.items.json"), ["1729999999999999999"])
        self.assertEqual((r["records"][0]["raw"]["item_state"], r["records"][0]["raw"]["item_error"], sc.part_problems(r, "tracked")),
                         ("unavailable", "Not available in US", []))
        r = tracked(load("shop_id_zero_products.items.json"), ["1732222721408012710"])
        self.assertTrue(r["error"].startswith("no_products: Input produced 0 results"))
        self.assertEqual(len(r["records"]), 1)
        self.assertEqual(r["records"][0]["raw"]["item_state"], "missing")

    def test_shape_changed(self):
        rows = copy.deepcopy(load("search_death_wish_coffee_20.items.json"))
        del rows[3]["soldCount"]
        r = search(rows)
        self.assertEqual((r["error"], r["records"]), ("shape_changed: row 3 soldCount", []))

    def test_decide_status(self):
        ok = {"error": None, "fetched": 20, "ranks_complete": True}
        bad = {**ok, "error": "boom"}
        self.assertEqual(sc.decide_status(False, {}), ("could_not_look", "missing_token"))
        self.assertEqual(sc.decide_status(True, {"tracked": bad, "search": bad}), ("could_not_look", "tracked: boom; search: boom"))
        self.assertEqual(sc.decide_status(True, {"tracked": ok, "search": ok}), ("ok", ""))
        self.assertEqual(sc.decide_status(True, {"tracked": bad, "search": ok}), ("partial", "tracked: boom"))


if __name__ == "__main__":
    unittest.main()
