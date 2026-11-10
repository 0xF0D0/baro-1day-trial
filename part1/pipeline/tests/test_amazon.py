import json
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

import support  # noqa: F401  (puts part1/pipeline on sys.path)
from mappers.amazon import ENDING, SOURCE, map_run
from model import MapError, Scope

SAMPLES = Path(__file__).resolve().parents[2] / "collectors" / "04_amazon" / "samples" / "apify"

OK = {"source": "amazon", "status": "ok", "reason": "", "extra": {"search_rows": 60, "candidates": 27, "selected": 10}}
PARTIAL = {**OK, "status": "partial", "reason": "details_failed=1"}


def sample(name):
    return json.loads((SAMPLES / name).read_text())


DETAIL = next(i for i in sample("dataset_junglee_3asins.json") if i["asin"] == "B08VFVSBXM")
SEARCH = next(i for i in sample("dataset_apt_marble_dw60.json") if i["asin"] == "B08VFVSBXM")
REVIEW = sample("dataset_2asins_5each.json")[0]


def product(detail=DETAIL, detail_error=None, rank=2, key="B08VFVSBXM", search=SEARCH):
    return {"key": key, "kind": "product", "url": "https://www.amazon.com/dp/" + key,
            "fetched_at": "2026-11-10T10:50:00Z",
            "raw": {"rank": rank, "search_item": search, "merged_asins": [], "detail": detail,
                    "detail_error": detail_error, "reviews": "complete"}}


def review(item=REVIEW, key=None, asin="B00OQKOO02"):
    key = key or item["ReviewId"]
    return {"key": key, "kind": "review", "url": "https://www.amazon.com/portal/customer-reviews/srp/-/" + key,
            "fetched_at": "2026-11-10T10:55:00Z",
            "raw": {"product_asin": asin, "rank_in_product": 1, "image_count": 0, "item": {**item, "Reviewer": None,
                    "ReviewerProfileUrl": None, "ReviewerId": None, "Images": None, "Videos": None}}}


class AmazonTest(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(SOURCE, "amazon")
        self.assertEqual(ENDING, {("products", "product"): "absent", ("reviews", "review"): "never"})

    def test_product_with_detail(self):
        rec = product()
        m = map_run(OK, [rec])
        row = m.rows[0]
        self.assertEqual((row.table, row.kind, row.key, row.scope, row.url, row.fetched_at, row.raw),
                         ("products", "product", "B08VFVSBXM", "all", rec["url"], rec["fetched_at"], rec["raw"]))
        self.assertEqual(row.columns, {
            "retailer": "amazon", "product_id": "B08VFVSBXM", "title": DETAIL["title"], "price": Decimal("17.48"),
            "price_max": None, "list_price": None, "currency": "USD", "rating": Decimal("4.60"),
            "review_count": 3357, "rank": 2, "sponsored": None, "availability": "In Stock  In Stock",
            "seller_name": "Death Wish Coffee Co.", "sold_count": None})
        self.assertEqual(m.not_fetched, 0)

    def test_list_price(self):
        c = map_run(OK, [product({**DETAIL, "listPrice": {"value": 21.5, "currency": "$"}})]).rows[0].columns
        self.assertEqual(c["list_price"], Decimal("21.50"))

    def test_list_price_as_plain_number(self):
        c = map_run(OK, [product({**DETAIL, "listPrice": 11.99})]).rows[0].columns
        self.assertEqual(c["list_price"], Decimal("11.99"))

    def test_list_price_as_text_is_keyed_error(self):
        with self.assertRaises(MapError) as e:
            map_run(OK, [product({**DETAIL, "listPrice": "$11.99"}, key="B4")])
        self.assertTrue(str(e.exception).startswith("B4"), str(e.exception))

    def test_product_without_detail_leaves_detail_columns_out(self):
        m = map_run(PARTIAL, [product(detail=None, detail_error="no_item")])
        self.assertEqual(m.rows[0].columns, {"retailer": "amazon", "product_id": "B08VFVSBXM", "price_max": None,
                                             "currency": "USD", "rank": 2, "sponsored": None, "sold_count": None})

    def test_review(self):
        row = map_run(OK, [review()]).rows[0]
        self.assertEqual((row.table, row.kind, row.key, row.scope), ("reviews", "review", "R2PAMD6PD20P7R", "all"))
        self.assertEqual(row.columns, {
            "product_key": "B00OQKOO02", "rating": Decimal("5.00"), "title": REVIEW["ReviewTitle"],
            "body": REVIEW["ReviewContent"], "review_date": date(2023, 11, 24), "verified": True, "helpful_votes": 3})
        self.assertNotIn("Reviewer", row.columns)

    def test_unverified_review(self):
        c = map_run(OK, [review({**REVIEW, "Verified": "False"})]).rows[0].columns
        self.assertIs(c["verified"], False)

    def test_scopes(self):
        self.assertEqual(map_run(OK, []).scopes, [Scope("all", "ok", "")])
        self.assertEqual(map_run(PARTIAL, [product()]).scopes, [Scope("all", "partial", "details_failed=1")])
        self.assertEqual(map_run({**OK, "status": "could_not_look", "reason": "missing_token"}, []).scopes,
                         [Scope("all", "could_not_look", "missing_token")])

    def test_bad_input_is_keyed_error(self):
        bad_price = product({**DETAIL, "price": {"value": "free"}}, key="B1")
        bad_date = review({**REVIEW, "ReviewDate": "yesterday"}, key="R1")
        bad_verified = review({**REVIEW, "Verified": "maybe"}, key="R2")
        bad_list = product({**DETAIL, "listPrice": "n/a"}, key="B2")
        for bad in (bad_price, bad_date, bad_verified, bad_list, {**product(key="B3"), "kind": "offer"}):
            with self.assertRaises(MapError) as e:
                map_run(OK, [bad])
            self.assertTrue(str(e.exception).startswith(bad["key"]), str(e.exception))


if __name__ == "__main__":
    unittest.main()
