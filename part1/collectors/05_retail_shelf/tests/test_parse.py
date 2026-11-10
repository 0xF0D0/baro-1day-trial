import json, sys, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import source_collector as sc

SAMPLES = HERE.parents[2] / "collectors" / "05_retail_shelf" / "samples"
INPUTS = json.load(open(HERE.parent / "brand_inputs.json"))


class ParseTests(unittest.TestCase):
    def test_ulta_batiste(self):
        module = json.load(open(SAMPLES / "ulta" / "listing_module_batiste.json"))["module"]
        root = {"a": [module], "b": {"parentModule": {"moduleName": "ProductListingResults"}}}
        self.assertIs(sc.find_listing_module(root), module)
        rows = sc.select("ulta", module["items"], INPUTS["batiste"][0])
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[0]["productId"], "pimprod2045775")
        self.assertEqual(rows[-1]["productId"], "xlsImpprod15622775")

    def test_target_jinx(self):
        items = json.load(open(SAMPLES / "apify" / "target_al_store2581_4brands.json"))["items"]
        rows = sorted((i for i in items if i["searchQuery"] == "jinx dog food"), key=lambda i: i["position"])
        picked = sc.select("target", rows, INPUTS["jinx"][0])
        tcins = [r["tcin"] for r in picked]
        self.assertEqual(len(picked), 10)
        self.assertEqual((tcins[0], tcins[-1]), ("88766771", "94961044"))
        self.assertFalse(any(r["isMarketplace"] for r in picked))
        self.assertNotIn("86020323", tcins)
        self.assertNotIn("89559952", tcins)

    def test_target_review_key(self):
        item = json.load(open(SAMPLES / "apify" / "target_reviews_A-88498115.json"))["items"][0]
        self.assertEqual(sc.review_key("target:88498115", "target", item), "target:88498115:h27cef09620e38f8f")

    def test_product_page_offer(self):
        html = (SAMPLES / "ulta" / "product_page_ld_pimprod2037265.html").read_text()
        self.assertEqual(sc.product_page_offer(html, "2604512"),
                         {"sku": "2604512", "price": 33, "currency": "USD", "availability": "InStock"})
        with self.assertRaisesRegex(ValueError, "product_ld_not_found"):
            sc.product_page_offer(html, "2604513")
        with self.assertRaisesRegex(ValueError, "product_ld_not_found"):
            sc.product_page_offer("<html><body>none</body></html>", "2604512")

        def page(price, avail):
            o = {"@type": "Product", "sku": "1", "offers": {"@type": "Offer", "price": price, "availability": avail, "priceCurrency": "USD"}}
            return '<script type="application/ld+json">' + json.dumps(o) + "</script>"
        self.assertEqual(sc.product_page_offer(page("33", "InStock"), "1")["price"], "33")
        for bad in ("$33", "", None, True):
            with self.assertRaisesRegex(ValueError, "price_not_number"):
                sc.product_page_offer(page(bad, "InStock"), "1")
        for bad in (0, -1, "0", "0.00", float("nan"), float("inf")):
            with self.assertRaisesRegex(ValueError, "price_not_number"):
                sc.product_page_offer(page(bad, "InStock"), "1")
        for ok in (0.5, "0.50"):
            self.assertEqual(sc.product_page_offer(page(ok, "InStock"), "1")["price"], ok)
        html2 = (SAMPLES / "ulta" / "product_page_ld_xlsImpprod2040049.html").read_text()
        self.assertEqual(sc.product_page_offer(html2, "2515942"),
                         {"sku": "2515942", "price": "20.99", "currency": "USD", "availability": "InStock"})
        self.assertEqual(sc.product_page_offer(page(5.99, "https://schema.org/OutOfStock"), "1")["availability"], "OutOfStock")


class CarefulPaceTests(unittest.TestCase):
    def _pace(self, value):
        import importlib, os
        from unittest import mock
        env = dict(os.environ)
        env.pop("RADAR_CAREFUL", None)
        if value is not None:
            env["RADAR_CAREFUL"] = value
        try:
            with mock.patch.dict(os.environ, env, clear=True):
                importlib.reload(sc)
                return {n: getattr(sc, n) for n in ['ULTA_SPACING_S', 'APIFY_POLL_S']}
        finally:
            importlib.reload(sc)

    def test_pace(self):
        self.assertEqual(self._pace(None)["ULTA_SPACING_S"], 2)
        self.assertEqual(self._pace("")["ULTA_SPACING_S"], 2)
        self.assertEqual(self._pace("1")["ULTA_SPACING_S"], 3)
        self.assertEqual(self._pace(None)["APIFY_POLL_S"], 3)
        self.assertEqual(self._pace("")["APIFY_POLL_S"], 3)
        self.assertEqual(self._pace("1")["APIFY_POLL_S"], 3)


if __name__ == "__main__":
    unittest.main()
