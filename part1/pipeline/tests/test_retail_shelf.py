import json
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

import support  # noqa: F401  (puts part1/pipeline on sys.path)
import mappers
from mappers.retail_shelf import map_run, parse_price
from model import MapError, Scope

SAMPLES = Path(__file__).resolve().parents[2] / "collectors" / "05_retail_shelf" / "samples"

RUN = {"extra": {"cells": [{"retailer": "ulta", "status": "ok", "reason": "", "selected": 10},
                           {"retailer": "target", "status": "could_not_look", "reason": "missing_token", "selected": 0}]}}

ULTA_LI = {"productId": "pimprod2045775", "productName": "Light Dry Shampoo - Mellow Melon", "brandName": "Batiste",
           "listPrice": "$12.99", "salePrice": None, "rating": 4.5, "reviewCount": 28849, "sponsored": False}
ULTA_R = {"ugc_id": 589138362, "details": {"headline": "I Stick With Batiste", "comments": "I love this specific Batiste dry shampoo",
          "created_date": 1793021408804}, "badges": {"is_verified_buyer": False}, "metrics": {"rating": 5, "helpful_votes": 0}}


def items(name):
    return json.loads((SAMPLES / name).read_text())["items"]


def product(retailer, li, rank=1, key="x:1"):
    return {"key": key, "kind": "product", "url": "https://example.test/" + key, "fetched_at": "2026-11-10T00:00:00Z",
            "raw": {"retailer": retailer, "rank": rank, "listing_item": li, "reviews_state": "fetched",
                    "reviews_error": None, "reviews_meta": None}}


def review(retailer, product_key, r, key="x:1:r"):
    return {"key": key, "kind": "review", "url": "https://example.test/" + key, "fetched_at": "2026-11-10T00:00:00Z",
            "raw": {"retailer": retailer, "product_key": product_key, "review": r}}


class RetailShelfTest(unittest.TestCase):
    def test_parse_price(self):
        self.assertEqual(parse_price("$12.99"), (Decimal("12.99"), None))
        self.assertEqual(parse_price("$18.00 - $46.00"), (Decimal("18.00"), Decimal("46.00")))
        self.assertEqual(parse_price("$1,299.00"), (Decimal("1299.00"), None))
        for bad in ("", "12.99", "from $5", "$5 - "):
            with self.assertRaises(ValueError):
                parse_price(bad)

    def test_ulta_product(self):
        row = map_run(RUN, [product("ulta", ULTA_LI, key="ulta:pimprod2045775")]).rows[0]
        self.assertEqual((row.table, row.kind, row.key, row.scope), ("products", "product", "ulta:pimprod2045775", "ulta"))
        self.assertEqual(row.columns, {"retailer": "ulta", "product_id": "pimprod2045775", "title": "Light Dry Shampoo - Mellow Melon",
            "price": Decimal("12.99"), "price_max": None, "list_price": None, "currency": "USD", "rating": Decimal("4.50"),
            "review_count": 28849, "rank": 1, "sponsored": False, "availability": None, "seller_name": None, "sold_count": None})

    def test_ulta_range_and_sale(self):
        cols = lambda **kw: map_run(RUN, [product("ulta", {**ULTA_LI, **kw}, key="ulta:x")]).rows[0].columns
        c = cols(listPrice="$12.99 - $20.99")
        self.assertEqual((c["price"], c["price_max"], c["list_price"]), (Decimal("12.99"), Decimal("20.99"), None))
        c = cols(listPrice="$12.99", salePrice="$9.74")
        self.assertEqual((c["price"], c["price_max"], c["list_price"]), (Decimal("9.74"), None, Decimal("12.99")))

    def test_target_product(self):
        li = items("apify/target_al_store2581_4brands.json")[0]        # tcin 75561114
        c = map_run(RUN, [product("target", li, key="target:75561114")]).rows[0].columns
        self.assertEqual((c["title"], c["price"], c["price_max"], c["list_price"], c["rating"], c["review_count"], c["sponsored"], c["availability"]),
            ("Batiste Brunette Dry Shampoo - 3.81oz", Decimal("8.99"), None, None, Decimal("4.27"), 567, True, "IN_STOCK"))
        sale = next(i for i in items("apify/target_al_store2581_4brands.json") if i["tcin"] == "17079185")
        c = map_run(RUN, [product("target", sale, key="target:17079185")]).rows[0].columns
        self.assertEqual((c["price"], c["list_price"]), (Decimal("9.99"), Decimal("11.59")))

    def test_sephora_product(self):
        its = items("apify/sephora_search_igview_bestselling_3.json")
        c = map_run(RUN, [product("sephora", its[0], key="sephora:P525776")]).rows[0].columns
        self.assertEqual((c["title"], c["price"], c["price_max"], c["rating"], c["review_count"], c["sponsored"]),
            ("Sheer Clean Non-Aerosol Dry Shampoo Mist", Decimal("33.00"), None, Decimal("4.57"), 341, False))
        c = map_run(RUN, [product("sephora", its[2], key="sephora:P399330")]).rows[0].columns
        self.assertEqual((c["price"], c["price_max"], c["review_count"]), (Decimal("18.00"), Decimal("46.00"), 4379))

    def test_chewy_product(self):
        li = items("apify/chewy_search_jinx_parseforge.json")[0]       # partNumber 845310
        c = map_run(RUN, [product("chewy", li, key="chewy:845310")]).rows[0].columns
        self.assertEqual((c["price"], c["list_price"], c["rating"], c["review_count"], c["sponsored"], c["availability"]),
            (Decimal("47.34"), Decimal("52.99"), Decimal("4.58"), 1260, None, "IN_STOCK"))
        self.assertTrue(c["title"].startswith("Jinx Beef, Brown Rice & Sweet Potato"))

    def test_reviews(self):
        row = map_run(RUN, [review("ulta", "ulta:pimprod2045775", ULTA_R, key="ulta:pimprod2045775:589138362")]).rows[0]
        self.assertEqual((row.table, row.kind, row.scope), ("reviews", "review", "ulta"))
        self.assertEqual(row.columns, {"product_key": "ulta:pimprod2045775", "rating": 5, "title": "I Stick With Batiste",
            "body": "I love this specific Batiste dry shampoo", "review_date": date(2026, 10, 26), "verified": False, "helpful_votes": 0})
        t = map_run(RUN, [review("target", "target:88498115", items("apify/target_reviews_A-88498115.json")[0], key="target:88498115:h0")]).rows[0].columns
        self.assertEqual((t["rating"], t["title"], t["review_date"], t["verified"], t["helpful_votes"]), (5, "Go to coffee", date(2026, 10, 25), None, None))
        c = map_run(RUN, [review("chewy", "chewy:845310", items("apify/chewy_reviews_alc_845310.json")[0], key="chewy:845310:r0")]).rows[0].columns
        self.assertEqual((c["rating"], c["title"], c["review_date"], c["verified"], c["helpful_votes"]), (1, "Disappointed", date(2026, 11, 7), None, 0))

    def test_scopes_and_empty_run(self):
        m = map_run(RUN, [])
        self.assertEqual((m.rows, m.not_fetched), ([], 0))
        self.assertEqual(m.scopes, [Scope("ulta", "ok", ""), Scope("target", "could_not_look", "missing_token")])

    def test_unknown_inputs_are_errors(self):
        for bad in (product("walmart", ULTA_LI, key="walmart:1"),
                    {**product("ulta", ULTA_LI, key="ulta:2"), "kind": "listing"},
                    product("ulta", {**ULTA_LI, "listPrice": "call for price"}, key="ulta:3")):
            with self.assertRaises(MapError) as e:
                map_run(RUN, [bad])
            self.assertTrue(str(e.exception).startswith(bad["key"]))

    def test_registry(self):
        self.assertIs(mappers.MAPPERS["retail_shelf"], mappers.retail_shelf)


if __name__ == "__main__":
    unittest.main()
