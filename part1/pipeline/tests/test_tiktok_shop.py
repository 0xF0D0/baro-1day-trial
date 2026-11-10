import support  # noqa: F401  (puts the pipeline folder on sys.path)
import copy
import json
import re
import unittest
from decimal import Decimal
from pathlib import Path

from model import MapError, MappedRun, Scope
from mappers import tiktok_shop

SAMPLES = Path(__file__).resolve().parents[2] / "collectors" / "09_tiktok_shop" / "samples" / "apify"
RUN_ID = "l1UEKc0b7lh5XMrat"


def sample(name):
    return json.loads((SAMPLES / name).read_text())


def strip_personal(row):
    row = copy.deepcopy(row)
    row.pop("reviews", None)
    if "shippingOrigin" in row:
        row["shippingOrigin"] = None
    return row


def envelope(row, state="fetched", error=None, part="tracked", term="death wish coffee", pid=None):
    pid = pid or row["productId"]
    tracked = part == "tracked"
    stamp = re.sub(r"\.\d+Z$", "Z", row["scrapeTimestamp"]) if row else "2026-11-10T10:57:19Z"
    return {"key": f"product/{pid}" if tracked else f"search/{term}/{pid}",
            "kind": "product" if tracked else "search_result",
            "url": f"https://www.tiktok.com/shop/pdp/_/{pid}", "fetched_at": stamp,
            "raw": {"item": row and strip_personal(row), "item_state": state, "item_error": error,
                    "input": ({"part": "tracked", "product_id": pid} if tracked
                              else {"part": "search", "search_term": term, "limit": 20}),
                    "apify_run_id": RUN_ID, "reviews_removed": 0}}


def part(error=None, **counts):
    base = {"apify_run_id": RUN_ID, "apify_status": "SUCCEEDED", "apify_status_message": None, "actor_build": "0.0.34",
            "error": error, "fetched": 0, "unavailable": 0, "failed": 0, "missing": 0, "unexpected_rows": 0,
            "duplicate_rows": 0, "message_rows": 0, "cost_usd": 0.01, "cost_final": True}
    return {**base, **counts}


def run(status="ok", reason="", tracked=None, search=None):
    extra = {"data_provider": "apify:lurkapi/tiktok-shop-scraper", "verified_against_site": False}
    if tracked is not None:
        extra["tracked"] = tracked
    if search is not None:
        extra["search"] = {**search, "ranks_complete": search.get("ranks_complete", True)}
    return {"source": "tiktok_shop", "status": status, "reason": reason, "extra": extra}


OK_RUN = run(tracked=part(fetched=2), search=part(fetched=20))
TRACKED = sample("product_ids_2.items.json")[0]
SEARCH = sample("search_death_wish_coffee_20.items.json")[0]
UNAVAILABLE = sample("product_id_not_available.items.json")[0]


class TiktokShopTest(unittest.TestCase):
    def test_module_interface(self):
        self.assertEqual(tiktok_shop.SOURCE, "tiktok_shop")
        self.assertEqual(tiktok_shop.ENDING,
                         {("products", "product"): "absent", ("products", "search_result"): "absent"})

    def test_tracked_product(self):
        rec = envelope(TRACKED)
        result = tiktok_shop.map_run(OK_RUN, [rec])
        self.assertIsInstance(result, MappedRun)
        self.assertEqual(result.not_fetched, 0)
        row, = result.rows
        self.assertEqual((row.table, row.kind, row.key, row.scope), ("products", "product", rec["key"], "tracked"))
        self.assertEqual((row.url, row.fetched_at, row.raw), (rec["url"], "2026-11-10T10:57:19Z", rec["raw"]))
        self.assertEqual(row.columns, {
            "retailer": "tiktok_shop", "product_id": "1732222721408012710",
            "title": "Death Wish Coffee, Dark Roast, Instant Coffee, 300mg Natural Caffeine, (8) Single Serve Packets Per Box",
            "price": Decimal("51.99"), "price_max": None, "list_price": None, "currency": "USD",
            "rating": Decimal("5.00"), "review_count": 5, "rank": None, "sponsored": None,
            "availability": None, "seller_name": "Death Wish Coffee", "sold_count": 28})

    def test_search_result_has_rank(self):
        rec = envelope(SEARCH, part="search")
        row, = tiktok_shop.map_run(OK_RUN, [rec]).rows
        self.assertEqual((row.table, row.kind, row.key, row.scope),
                         ("products", "search_result", "search/death wish coffee/1729466621878506208", "search"))
        self.assertEqual(row.columns, {
            "retailer": "tiktok_shop", "product_id": "1729466621878506208",
            "title": "fueled by iced coffee and anxiety retro humor coffee lover tee",
            "price": Decimal("22.00"), "price_max": None, "list_price": None, "currency": "USD",
            "rating": None, "review_count": 0, "rank": 8, "sponsored": None,
            "availability": None, "seller_name": "CustomCreationsByStephanie", "sold_count": 12})

    def test_rating_is_none_without_reviews(self):
        item = {**TRACKED, "reviewCount": 0, "rating": 0}
        c = tiktok_shop.map_run(OK_RUN, [envelope(item)]).rows[0].columns
        self.assertEqual((c["rating"], c["review_count"]), (None, 0))
        c = tiktok_shop.map_run(OK_RUN, [envelope({**TRACKED, "reviewCount": None, "rating": 0})]).rows[0].columns
        self.assertEqual((c["rating"], c["review_count"]), (None, None))
        c = tiktok_shop.map_run(OK_RUN, [envelope({**TRACKED, "reviewCount": 5, "rating": 4.5})]).rows[0].columns
        self.assertEqual((c["rating"], c["review_count"]), (Decimal("4.50"), 5))

    def test_list_price_from_original_price(self):
        item = {**TRACKED, "originalPrice": 59.5}
        row, = tiktok_shop.map_run(OK_RUN, [envelope(item)]).rows
        self.assertEqual(row.columns["list_price"], Decimal("59.50"))

    def test_not_fetched_states_give_no_row(self):
        recs = [envelope(UNAVAILABLE, "unavailable", "Not available in US"),
                envelope(None, "missing", "no_row", pid="1729700841513849624"),
                envelope({**UNAVAILABLE, "status": "Error"}, "failed", "Error"),
                envelope(TRACKED)]
        result = tiktok_shop.map_run(OK_RUN, recs)
        self.assertEqual(result.not_fetched, 3)
        self.assertEqual([r.key for r in result.rows], [recs[3]["key"]])

    def test_scopes_complete_run(self):
        result = tiktok_shop.map_run(OK_RUN, [])
        self.assertEqual(result.scopes, [Scope("tracked", "ok", ""), Scope("search", "ok", "")])

    def test_unavailable_tracked_product_keeps_part_ok(self):
        r = run(tracked=part(fetched=1, unavailable=1), search=part(fetched=20))
        self.assertEqual(tiktok_shop.map_run(r, []).scopes[0], Scope("tracked", "ok", ""))

    def test_scopes_incomplete_run(self):
        r = run("partial", "tracked: missing=1; search: fetched=19/20",
                tracked=part(fetched=9, missing=1), search=part(fetched=19, unavailable=1))
        self.assertEqual(tiktok_shop.map_run(r, []).scopes, [
            Scope("tracked", "partial", "missing=1"),
            Scope("search", "partial", "unavailable=1, fetched=19/20")])

    def test_scope_with_error_could_not_look(self):
        r = run("partial", "x", tracked=part(error="apify_start_failed: http_500 -", apify_status=None),
                search=part(fetched=20))
        self.assertEqual(tiktok_shop.map_run(r, []).scopes, [
            Scope("tracked", "could_not_look", "apify_start_failed: http_500 -"), Scope("search", "ok", "")])

    def test_failed_apify_run_is_partial(self):
        r = run("partial", "x", tracked=part(apify_status="TIMED-OUT", apify_status_message="late", fetched=2),
                search=part(fetched=20, ranks_complete=False))
        self.assertEqual(tiktok_shop.map_run(r, []).scopes[0], Scope("tracked", "partial", "apify_run_TIMED-OUT: late"))
        r = run("partial", "x", tracked=part(fetched=2), search=part(fetched=20, ranks_complete=False))
        self.assertEqual(tiktok_shop.map_run(r, []).scopes[1], Scope("search", "partial", "ranks_incomplete"))

    def test_run_without_parts_uses_run_status(self):
        r = {"status": "could_not_look", "reason": "missing_token", "extra": {"verified_against_site": False}}
        self.assertEqual(tiktok_shop.map_run(r, []).scopes, [Scope("all", "could_not_look", "missing_token")])

    def test_missing_part_is_could_not_look(self):
        r = run("partial", "exception: OSError: x", tracked=part(fetched=2))
        self.assertEqual(tiktok_shop.map_run(r, []).scopes,
                         [Scope("tracked", "ok", ""), Scope("search", "could_not_look", "exception: OSError: x")])

    def test_unknown_kind_raises_with_key(self):
        rec = {**envelope(TRACKED), "kind": "review"}
        with self.assertRaises(MapError) as cm:
            tiktok_shop.map_run(OK_RUN, [rec])
        self.assertTrue(str(cm.exception).startswith(rec["key"]))

    def test_unknown_state_raises_with_key(self):
        rec = envelope(TRACKED, "weird")
        with self.assertRaises(MapError) as cm:
            tiktok_shop.map_run(OK_RUN, [rec])
        self.assertTrue(str(cm.exception).startswith(rec["key"]))

    def test_non_integer_counts_raise_with_key(self):
        for rec in (envelope({**TRACKED, "soldCount": "12"}), envelope({**SEARCH, "rank": 1.5}, part="search")):
            with self.assertRaises(MapError) as cm:
                tiktok_shop.map_run(OK_RUN, [rec])
            self.assertTrue(str(cm.exception).startswith(rec["key"]))

    def test_missing_tracked_product_makes_part_partial(self):
        r = run("partial", "tracked: missing=1", tracked=part(fetched=1, missing=1), search=part(fetched=20))
        self.assertEqual(tiktok_shop.map_run(r, []).scopes[0], Scope("tracked", "partial", "missing=1"))

    def test_unconvertible_value_raises_with_key(self):
        rec = envelope({**TRACKED, "currentPrice": "abc"})
        with self.assertRaises(MapError) as cm:
            tiktok_shop.map_run(OK_RUN, [rec])
        self.assertTrue(str(cm.exception).startswith(rec["key"]))


if __name__ == "__main__":
    unittest.main()
