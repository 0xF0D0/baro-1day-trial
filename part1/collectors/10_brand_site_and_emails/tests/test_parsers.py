import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLLECTOR = HERE.parent
ROOT = HERE.parents[3]
SAMPLES = ROOT / "part1/collectors/10_brand_site_and_emails/samples"
sys.path.insert(0, str(COLLECTOR))
import source_collector as sc  # noqa: E402

WTBID = "679a839e96a96e0f672b1fcc"


def jload(p):
    return json.loads(Path(p).read_text())


class ParserTests(unittest.TestCase):
    def test_shopify_products_page(self):
        resp = jload(SAMPLES / "products_jinx_page1_full.json")
        products = sc.parse_products_page(resp)
        self.assertEqual(len(products), 73)
        self.assertEqual(sc.product_key("www.thinkjinx.com", products[0]["handle"]),
                         "product/www.thinkjinx.com/peanut-butter-bone-broth-biscuits")
        del resp["products"][0]["handle"]
        with self.assertRaises(sc.ShapeError):
            sc.parse_products_page(resp)

    def test_batiste_widget_and_wtb(self):
        html = (SAMPLES / "batiste/product_page_fragrance-bare.html").read_text()
        self.assertEqual(sc.classify_batiste_page(200, None, html, WTBID),
                         ("widget", ["5010724526705", "5010724527146", "5010724538333", "5010724532133"]))
        self.assertEqual(sc.classify_batiste_page(301, "https://www.batistehair.com/batiste-products", "", WTBID),
                         ("redirected", []))
        resp = jload(SAMPLES / "batiste/wtb_availabilities_5010724526705_full.json")
        self.assertEqual(sc.validate_wtb(resp, "5010724526705"), ("US", "USD"))
        self.assertEqual(len(resp["d"]), 7)
        with self.assertRaises(sc.ShapeError):
            sc.validate_wtb(resp, "5010724527146")

    def test_emails_part_living_proof(self):
        manifest = jload(COLLECTOR / "inbox_export/export.json")
        emls = [sc.read_eml(COLLECTOR / "inbox_export" / m["file"], m["gmail_id"]) for m in manifest["messages"]]
        self.assertTrue(all(emls))
        signups = {s["brand"]: s for s in jload(ROOT / "part1/data/email_signups.json")["signups"]}
        state, reason, msgs = sc.emails_part(signups["Living Proof"], ["livingproof.com"], manifest, emls)
        self.assertEqual((state, reason), ("partial", "first_day_not_over(covered=2.65h); spam_not_checked"))
        self.assertEqual(len(msgs), 1)
        self.assertEqual(sc.emails_part(signups["Jinx"], [], manifest, emls),
                         ("could_not_look", "not_signed_up(status=not_signed_up)", []))

    def test_apify_items_and_log(self):
        items = jload(SAMPLES / "apify/blackrifle_run2_items.json")
        keys = [sc.apify_item_key(i) for i in items]
        self.assertEqual(len(keys), 55)
        self.assertEqual(keys[0], "product/www.blackriflecoffee.com/fall-coffee-lineup")
        url = "https://www.blackriflecoffee.com/collections/coffee"
        self.assertEqual(sc.apify_listed((SAMPLES / "apify/blackrifle_run2_log.txt").read_text(), url), 55)

    def test_apify_prices_state(self):
        c = dict(items_without_product_url=0, duplicate_items=0, items_without_price=0, currency_not_reported=55)
        self.assertEqual(sc.apify_prices_state("SUCCEEDED", 55, 55, False, 0, True, c),
                         ("partial", "currency_not_reported(n=55)"))
        c["currency_not_reported"] = 0
        self.assertEqual(sc.apify_prices_state("SUCCEEDED", 55, 55, False, 0, True, c), ("ok", ""))
        self.assertEqual(sc.apify_prices_state("SUCCEEDED", 5, 10, True, 0, True, c),
                         ("partial", "apify_max_results_reached; apify_count_mismatch(got=5,listed=10)"))
        self.assertEqual(sc.apify_prices_state("FAILED", 0, None, False, None, False, c),
                         ("could_not_look", "apify_run_FAILED"))

    def test_wtb_failure(self):
        body = (b'{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.4","title":"Forbidden",'
                b'"status":403,"detail":"Unauthorized ProductUIDs 5010724008355"}')
        self.assertEqual(sc.wtb_failure(403, body), ("unauthorized_product", False))
        self.assertEqual(sc.wtb_failure(403, b"<html>Access denied</html>"), ("blocked: http_403", True))
        self.assertEqual(sc.wtb_failure(403, b'{"detail":"Forbidden"}'), ("blocked: http_403", True))
        self.assertEqual(sc.wtb_failure(429, b""), ("blocked: http_429", True))
        self.assertEqual(sc.wtb_failure(500, b"oops"), ("http_500", True))


if __name__ == "__main__":
    unittest.main()
