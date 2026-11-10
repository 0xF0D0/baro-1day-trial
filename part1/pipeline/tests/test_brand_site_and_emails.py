import json
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import support  # noqa: F401  (puts part1/pipeline on sys.path)
from mappers.brand_site_and_emails import ENDING, SOURCE, map_run
from model import MapError, Scope

SAMPLES = Path(__file__).resolve().parents[2] / "collectors" / "10_brand_site_and_emails" / "samples"
FETCHED = "2026-11-10T11:00:00Z"

PARTS_OK = {"prices": {"state": "ok", "reason": "", "route": "shopify_products_json"},
            "offers": {"state": "partial", "reason": "klaviyo: klaviyo_http_500",
                       "home": {"state": "ok", "reason": ""}, "klaviyo": {"state": "could_not_look", "reason": "klaviyo_http_500"}},
            "emails": {"state": "partial", "reason": "first_day_not_over(covered=2.65h); spam_not_checked"}}
RUN = {"status": "partial", "reason": "emails: x", "extra": {"parts": PARTS_OK}}
BATISTE_PARTS = {**PARTS_OK, "prices": {"state": "partial", "reason": "blocked: http_403", "route": "batiste_wtb"}}


def load(*path):
    return json.loads(SAMPLES.joinpath(*path).read_text())


def record(key, kind, raw, url="https://example.test/x", fetched_at=FETCHED):
    return {"key": key, "kind": kind, "url": url, "fetched_at": fetched_at, "raw": raw}


def shopify(product, key="product/www.deathwishcoffee.com/x"):
    return record(key, "product", {"route": "shopify_products_json", "page": 1, "product": product})


def availability(ean, state="fetched", response=None, error=None):
    return record(f"wtb/{ean}", "retailer_availability",
                  {"route": "batiste_wtb", "ean": ean, "product_pages": ["/products/p"], "state": state,
                   "error": error, "response": response})


def slot(name, state, texts):
    return record(f"offer_slot/h/{name}", "offer_slot",
                  {"route": "home_dom", "slot": name, "selector": "p", "state": state,
                   "elements": [{"outer_html": f"<p>{t}</p>", "text": t} for t in texts]})


def email_record(name):
    text = (SAMPLES / "eml" / name).read_bytes().decode("ascii")
    return record("email/1a1c3c946076193d", "email",
                  {"route": "inbox_export", "file": name, "eml": text, "exported_at": "2026-11-10T07:26:17Z"})


class BrandSiteAndEmailsTest(unittest.TestCase):
    def test_source_and_ending(self):
        self.assertEqual(SOURCE, "brand_site_and_emails")
        self.assertEqual(ENDING, {("products", "product"): "absent", ("products", "retailer_availability"): "absent",
                                  ("ads", "offer_slot"): "absent", ("ads", "klaviyo_form"): "absent",
                                  ("ads", "email"): "never"})

    def test_scopes_follow_parts(self):
        m = map_run(RUN, [])
        self.assertEqual(m.scopes, [Scope("prices", "ok", ""), Scope("offers_home", "ok", ""),
                                    Scope("offers_klaviyo", "could_not_look", "klaviyo_http_500"),
                                    Scope("emails", "partial", "first_day_not_over(covered=2.65h); spam_not_checked")])
        self.assertEqual((m.rows, m.not_fetched), ([], 0))

    def test_shopify_product(self):
        p = load("products_livingproof_trimmed.json")["products"][0]
        row = map_run(RUN, [shopify(p, "product/www.livingproof.com/the-classic-clean-dry-shampoo-set")]).rows[0]
        self.assertEqual((row.table, row.kind, row.key, row.scope, row.fetched_at, row.raw["product"]["id"]),
                         ("products", "product", "product/www.livingproof.com/the-classic-clean-dry-shampoo-set",
                          "prices", FETCHED, 9436155511036))
        self.assertEqual(row.columns, {
            "retailer": "own_site", "product_id": "9436155511036", "title": "The Classic Clean Dry Shampoo Set",
            "price": Decimal("46.00"), "price_max": None, "list_price": Decimal("66.00"), "currency": "USD",
            "rating": None, "review_count": None, "rank": None, "sponsored": None, "availability": "IN_STOCK",
            "seller_name": None, "sold_count": None})

    def test_shopify_without_compare_at_and_out_of_stock(self):
        p = load("products_deathwish_trimmed.json")["products"][0]
        p = {**p, "variants": [{**v, "available": False} for v in p["variants"]]}
        c = map_run(RUN, [shopify(p)]).rows[0].columns
        self.assertEqual((c["title"], c["price"], c["list_price"], c["availability"]),
                         ("Peppermint Mocha Coffee", Decimal("13.99"), None, "OUT_OF_STOCK"))

    def test_apify_product(self):
        item = load("apify", "blackrifle_run2_items.json")[0]
        rec = record("product/www.blackriflecoffee.com/fall-coffee-lineup", "product",
                     {"route": "apify_ecommerce", "apify_run_id": "r1", "item": item}, item["url"])
        row = map_run(RUN, [rec]).rows[0]
        self.assertEqual(row.scope, "prices")
        self.assertEqual(row.columns, {
            "retailer": "own_site", "product_id": None, "title": "Fall Coffee Lineup", "price": Decimal("68.36"),
            "price_max": None, "list_price": None, "currency": "USD", "rating": None, "review_count": None,
            "rank": None, "sponsored": None, "availability": None, "seller_name": None, "sold_count": None})

    def test_retailer_availability_one_row_per_retailer(self):
        resp = load("batiste", "wtb_availabilities_5010724526705_full.json")
        run = {**RUN, "extra": {"parts": BATISTE_PARTS}}
        m = map_run(run, [availability("5010724526705", response=resp)])
        self.assertEqual([r.key for r in m.rows], [f"wtb/5010724526705/{i}" for i in (257, 245, 848, 847, 397)])
        r = m.rows[0]
        self.assertEqual((r.table, r.kind, r.scope, r.url, r.fetched_at), ("products", "retailer_availability",
                         "wtb/5010724526705", "https://example.test/x", FETCHED))
        self.assertIs(r.raw, m.rows[1].raw)
        self.assertEqual(r.columns, {
            "retailer": "target", "product_id": "5010724526705", "title": resp["prd"]["pname"],
            "price": Decimal("8.99"), "price_max": None, "list_price": None, "currency": "USD", "rating": None,
            "review_count": None, "rank": None, "sponsored": None, "availability": "IN_STOCK",
            "seller_name": None, "sold_count": None})
        self.assertEqual(m.rows[4].columns["retailer"], "ulta")
        self.assertEqual(m.scopes, [Scope("wtb/5010724526705", "ok", ""),
                                    Scope("wtb_listing", "could_not_look", "blocked: http_403", "wtb/"), Scope("offers_home", "ok", ""),
                                    Scope("offers_klaviyo", "could_not_look", "klaviyo_http_500"),
                                    Scope("emails", "partial", PARTS_OK["emails"]["reason"])])

    def test_barcode_not_fetched_gives_no_rows_and_scope_not_ok(self):
        run = {**RUN, "extra": {"parts": BATISTE_PARTS}}
        m = map_run(run, [availability("1", state="failed", error="blocked: http_403"),
                          availability("2", state="not_attempted"), availability("3", state="not_us")])
        self.assertEqual((m.rows, m.not_fetched), ([], 3))
        self.assertEqual([s for s in m.scopes if s.name.startswith("wtb/")],
                         [Scope("wtb/1", "could_not_look", "blocked: http_403"),
                          Scope("wtb/2", "could_not_look", "not_attempted"),
                          Scope("wtb/3", "could_not_look", "not_us")])

    def _listing(self, pages, parts=None):
        prices = {**BATISTE_PARTS["prices"], **(parts or {}), "product_pages": pages}
        run = {**RUN, "brand": "batiste", "extra": {"parts": {**BATISTE_PARTS, "prices": prices}}}
        return [s for s in map_run(run, []).scopes if s.name == "wtb_listing"]

    LISTING = "https://www.batistehair.com/batiste-products"

    def test_wtb_listing_ok_when_every_product_page_was_read(self):
        pages = [{"path": "/p/1", "state": "widget", "eans": ["5010724526705"]},
                 {"path": "/p/2", "state": "redirected", "eans": [], "location": self.LISTING},
                 {"path": "/p/3", "state": "not_found_page", "eans": []}]
        self.assertEqual(self._listing(pages), [Scope("wtb_listing", "ok", "", "wtb/")])

    def test_wtb_listing_partial_when_product_pages_failed(self):
        pages = [{"path": "/p/1", "state": "widget", "eans": ["5010724526705"]}, {"path": "/p/2", "state": "failed", "eans": []},
                 {"path": "/p/3", "state": "widget_missing", "eans": []}]
        self.assertEqual(self._listing(pages), [Scope("wtb_listing", "partial", "product_pages_failed=2", "wtb/")])

    def test_wtb_listing_could_not_look_when_no_barcode_was_found(self):
        pages = [{"path": f"/p/{i}", "state": "redirected", "eans": [], "location": self.LISTING} for i in range(3)]
        self.assertEqual(self._listing(pages, {"state": "could_not_look", "reason": "no_eans"}),
                         [Scope("wtb_listing", "could_not_look", "no_eans", "wtb/")])

    def test_wtb_listing_partial_when_a_page_redirects_elsewhere(self):
        pages = [{"path": "/p/1", "state": "widget", "eans": ["5010724526705"]},
                 {"path": "/p/2", "state": "redirected", "eans": [], "location": "https://www.batistehair.com/challenge"}]
        self.assertEqual(self._listing(pages), [Scope("wtb_listing", "partial", "product_pages_failed=1", "wtb/")])

    def test_wtb_listing_redirect_to_the_listing_in_other_spellings(self):
        for loc in ("/batiste-products", "/batiste-products/", "https://www.batistehair.com/batiste-products/?a=1#x"):
            pages = [{"path": "/p/1", "state": "widget", "eans": ["5010724526705"]},
                     {"path": "/p/2", "state": "redirected", "eans": [], "location": loc}]
            self.assertEqual(self._listing(pages), [Scope("wtb_listing", "ok", "", "wtb/")], loc)

    def test_wtb_listing_redirect_without_a_known_listing_is_not_read(self):
        pages = [{"path": "/p/1", "state": "widget", "eans": ["5010724526705"]},
                 {"path": "/p/2", "state": "redirected", "eans": [], "location": self.LISTING}]
        prices = {**BATISTE_PARTS["prices"], "product_pages": pages}
        run = {**RUN, "brand": "no-such-brand", "extra": {"parts": {**BATISTE_PARTS, "prices": prices}}}
        got = [s for s in map_run(run, []).scopes if s.name == "wtb_listing"]
        self.assertEqual(got, [Scope("wtb_listing", "partial", "product_pages_failed=1", "wtb/")])

    def test_wtb_listing_could_not_look_without_the_listing(self):
        self.assertEqual(self._listing(None), [Scope("wtb_listing", "could_not_look", "blocked: http_403", "wtb/")])

    def test_shopify_brand_has_no_wtb_listing(self):
        m = map_run({**RUN, "extra": {"parts": PARTS_OK}}, [])
        self.assertNotIn("wtb_listing", [s.name for s in m.scopes])

    def test_batiste_without_barcode_records_keeps_prices_scope(self):
        m = map_run({**RUN, "extra": {"parts": BATISTE_PARTS}}, [])
        self.assertEqual(m.scopes[0], Scope("prices", "partial", "blocked: http_403"))

    def test_offer_slot(self):
        m = map_run(RUN, [slot("announcement_bar", "found", ["FREE SHIPPING", "NEW"]), slot("cart_note", "not_found", [])])
        self.assertEqual(m.not_fetched, 1)
        self.assertEqual(len(m.rows), 1)
        r = m.rows[0]
        self.assertEqual((r.table, r.kind, r.key, r.scope), ("ads", "offer_slot", "offer_slot/h/announcement_bar", "offers_home"))
        self.assertEqual(r.columns, {
            "channel": "site", "advertiser_id": None, "advertiser_name": None, "format": None, "headline": None,
            "body": "FREE SHIPPING\nNEW", "cta": None, "landing_url": None, "landing_domain": None,
            "started_at": None, "last_shown_at": None, "variation_count": None, "placements": None, "offer_code": None})

    def test_klaviyo_form(self):
        form = load("klaviyo_forms_livingproof.json")["full_forms"][0]
        rec = record("klaviyo_form/H99sYH/TgsYXf", "klaviyo_form",
                     {"route": "klaviyo_full_forms", "company_id": "H99sYH", "form": form})
        r = map_run(RUN, [rec]).rows[0]
        self.assertEqual((r.table, r.scope), ("ads", "offers_klaviyo"))
        self.assertEqual(r.columns, {
            "channel": "signup_form", "advertiser_id": None, "advertiser_name": None, "format": None,
            "headline": "Email Pop-up - Desktop with 15% off promo", "body": None, "cta": None,
            "landing_url": None, "landing_domain": None, "started_at": None, "last_shown_at": None,
            "variation_count": None, "placements": None, "offer_code": None})

    def test_email(self):
        rec = email_record("deathwish_20261110T044745Z_1a1c3c89e9e9cf7d.eml")
        r = map_run(RUN, [rec]).rows[0]
        self.assertEqual((r.table, r.kind, r.scope), ("ads", "email", "emails"))
        c = r.columns
        self.assertEqual((c["channel"], c["headline"], c["advertiser_name"], c["offer_code"]),
                         ("email", "START STRONG \U0001F918", "Death Wish Coffee Co.", None))
        self.assertEqual(c["started_at"], datetime(2026, 11, 10, 4, 47, 45, tzinfo=timezone.utc))
        self.assertTrue(c["body"].startswith("[Welcome to Death Wish Coffee!]"))
        self.assertNotIn("TRIAL_INBOX", repr(c))
        self.assertNotIn("redacted.invalid", repr(c))
        self.assertEqual(set(c), set(map_run(RUN, [slot("a", "found", ["x"])]).rows[0].columns))

    def test_list_price_only_when_above_price(self):
        base = load("products_deathwish_trimmed.json")["products"][0]
        for compare, expected in [("0.00", None), (None, None), ("20.00", Decimal("20.00")),
                                  ("13.99", None), ("10.00", None)]:
            p = {**base, "variants": [{**base["variants"][0], "price": "13.99", "compare_at_price": compare}]}
            self.assertEqual(map_run(RUN, [shopify(p)]).rows[0].columns["list_price"], expected, compare)

    def test_availability_from_any_variant(self):
        base = load("products_deathwish_trimmed.json")["products"][0]
        v = base["variants"][0]
        cols = lambda flags: map_run(RUN, [shopify({**base, "variants": [{**v, "available": f} for f in flags]})]).rows[0].columns
        self.assertEqual(cols([False, True])["availability"], "IN_STOCK")
        self.assertEqual(cols([False, False])["availability"], "OUT_OF_STOCK")
        self.assertEqual((cols([False, True])["price"], cols([False, True])["price_max"]), (Decimal("13.99"), None))

    def test_apify_items_with_missing_parts_still_give_rows(self):
        item = load("apify", "blackrifle_run2_items.json")[0]
        for changed in ({"offers": None}, {"offers": {"priceText": None, "priceCurrency": None}},
                        {"offers": {"price": None, "priceCurrency": None}}, {"name": None}):
            raw = {"route": "apify_ecommerce", "apify_run_id": "r1", "item": {**{k: v for k, v in item.items() if k != "name"},
                   **({} if "name" in changed else {"name": "N"}), **changed}}
            m = map_run(RUN, [record("product/www.blackriflecoffee.com/x", "product", raw)])
            c = m.rows[0].columns
            self.assertEqual((len(m.rows), m.not_fetched, c["currency"]), (1, 0, "USD"))
            if "offers" in changed:
                self.assertIsNone(c["price"])
            else:
                self.assertIsNone(c["title"])
                self.assertEqual(c["price"], Decimal("68.36"))

    def test_online_entry_preferred_over_earlier_store_entry(self):
        resp = load("batiste", "wtb_availabilities_5010724526705_full.json")
        d = resp["d"]
        store, web = d[5], d[0]                      # Target Columbia Heights (11.39), Target _WEB (8.99)
        only_stores = {**d[5], "rid": 999, "rname": "Shop", "sid": "999_1", "pr": 5.0}
        later_store = {**d[6], "rid": 999, "sid": "999_2", "pr": 6.0}
        resp = {**resp, "d": [store, web, only_stores, later_store]}
        run = {**RUN, "extra": {"parts": BATISTE_PARTS}}
        rows = map_run(run, [availability("5010724526705", response=resp)]).rows
        self.assertEqual([(r.key[-3:], r.columns["price"]) for r in rows], [("257", Decimal("8.99")), ("999", Decimal("5.00"))])

    def test_offers_without_halves_falls_back_to_one_scope(self):
        parts = {**PARTS_OK, "offers": {"state": "ok", "reason": ""}}
        m = map_run({**RUN, "extra": {"parts": parts}}, [slot("a", "found", ["x"]),
                    record("klaviyo_form/c/f", "klaviyo_form", {"form": {"name": "n"}})])
        self.assertEqual([r.scope for r in m.rows], ["offers", "offers"])
        self.assertIn(Scope("offers", "ok", ""), m.scopes)

    def test_fetched_record_without_state_raises_with_key(self):
        run = {**RUN, "extra": {"parts": BATISTE_PARTS}}
        rec = availability("7", response={"prd": {"pname": "n"}, "d": []})
        del rec["raw"]["state"]
        with self.assertRaises(MapError) as cm:
            map_run(run, [rec])
        self.assertTrue(str(cm.exception).startswith("wtb/7"))

    def test_html_only_email_has_no_body(self):
        eml = ("From: Shop <a@shop.test>\r\nSubject: Hi\r\nDate: Tue, 10 Nov 2026 04:47:45 +0000\r\n"
               "Content-Type: text/html; charset=utf-8\r\n\r\n<p>hello</p>\r\n")
        c = map_run(RUN, [record("email/5", "email", {"eml": eml})]).rows[0].columns
        self.assertEqual((c["body"], c["headline"], c["advertiser_name"]), (None, "Hi", "Shop"))

    def test_errors_start_with_key(self):
        p = load("products_deathwish_trimmed.json")["products"][0]
        bad_price = {**p, "variants": [{**p["variants"][0], "price": "free"}]}
        for rec, key in [(record("odd/1", "mystery", {}), "odd/1"),
                         (shopify(bad_price, "product/h/bad"), "product/h/bad"),
                         (record("email/9", "email", {"eml": "Subject: x\r\n\r\nbody"}), "email/9")]:
            with self.assertRaises(MapError) as cm:
                map_run(RUN, [rec])
            self.assertTrue(str(cm.exception).startswith(key), str(cm.exception))

    def test_crashed_run_without_parts_still_maps(self):
        run = {**RUN, "status": "could_not_look", "reason": "exception: RuntimeError: no browser", "extra": {"parts": {}}}
        m = map_run(run, [])
        self.assertEqual((m.rows, m.scopes), ([], [Scope("all", "could_not_look", "exception: RuntimeError: no browser")]))

    def test_run_without_extra_gives_the_all_scope(self):
        run = {"status": "could_not_look", "reason": "exception: RuntimeError: boom"}
        m = map_run(run, [])
        self.assertEqual((m.rows, m.scopes), ([], [Scope("all", "could_not_look", "exception: RuntimeError: boom")]))
        m = map_run({**run, "extra": {}}, [])
        self.assertEqual(m.scopes, [Scope("all", "could_not_look", "exception: RuntimeError: boom")])

    def test_crashed_run_with_records_of_an_unfinished_part(self):
        # only the prices part was recorded; an offer_slot record is already in the file
        p = load("products_deathwish_trimmed.json")["products"][0]
        run = {"status": "could_not_look", "reason": "exception: RuntimeError: boom",
               "extra": {"parts": {"prices": PARTS_OK["prices"]}}}
        m = map_run(run, [shopify(p), slot("a", "found", ["x"])])
        self.assertEqual([(r.kind, r.scope) for r in m.rows], [("product", "prices"), ("offer_slot", "offers_home")])
        self.assertEqual(m.scopes, [Scope("prices", "ok", ""),
                                    Scope("offers_home", "partial", "exception: RuntimeError: boom")])


if __name__ == "__main__":
    unittest.main()
