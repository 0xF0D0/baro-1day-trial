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
                         ("could_not_look", "sender_domains_unknown", []))

    def test_apify_items_and_log(self):
        items = jload(SAMPLES / "apify/blackrifle_run2_items.json")
        keys = [sc.apify_item_key(i) for i in items]
        self.assertEqual(len(keys), 55)
        self.assertEqual(keys[0], "product/www.blackriflecoffee.com/fall-coffee-lineup")
        base = "https://www.blackriflecoffee.com/products/dark-roast-bundle"
        self.assertEqual(sc.apify_item_key({"url": base + "?variant=42986248175712"}),
                         "product/www.blackriflecoffee.com/dark-roast-bundle")
        self.assertIsNone(sc.apify_item_key({"url": base + "?ref=home"}))
        url = "https://www.blackriflecoffee.com/collections/coffee"
        log = lambda n: (SAMPLES / f"apify/blackrifle_run{n}_log.txt").read_text()
        self.assertEqual(sc.apify_listed(log(4), url), 55)
        self.assertEqual(sc.apify_found_per_page(log(4), url), [10, 22, 22, 30, 20, 5])
        self.assertEqual(sc.apify_listed(log(2), url), 55)
        self.assertEqual(sc.apify_found_per_page(log(2), url), [55])
        self.assertEqual(sc.apify_listed(log(1), url), 5)
        self.assertEqual(sc.apify_found_per_page(log(1), url), [10])
        self.assertIsNone(sc.apify_listed("INFO  nothing here\n", url))
        self.assertEqual(sc.apify_found_per_page("INFO  nothing here\n", url), [])

    def test_apify_prices_state(self):
        c = dict(items_without_product_url=0, duplicate_items=0, items_without_price=0, currency_not_reported=55)
        self.assertEqual(sc.apify_prices_state("SUCCEEDED", 55, 55, False, 0, True, c),
                         ("partial", "currency_not_reported(n=55)"))
        c["currency_not_reported"] = 0
        self.assertEqual(sc.apify_prices_state("SUCCEEDED", 55, 55, False, 0, True, c), ("ok", ""))
        # run 4: pages 10, 22, 22, 30, 20, 5 for 55 handled products
        self.assertEqual(sc.apify_prices_state("SUCCEEDED", 55, sc.apify_listed(
            (SAMPLES / "apify/blackrifle_run4_log.txt").read_text(), "https://www.blackriflecoffee.com/collections/coffee"),
            False, 0, True, c), ("ok", ""))
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


class BatisteOverlapTests(unittest.TestCase):
    """batiste_prices with a fake http: no network, no real waiting beyond a few tenths of a second."""

    LISTING = "https://www.batistehair.com/batiste-products"
    API_HOST = "wtb-api-hub.swaven.com"

    def _run(self, page_eans, api_answer=None, api_delay=0.05, raise_on_page=None, calls=None, utc=None, on_emit=None):
        """page_eans: {path: [ean, ...]}. -> (part, calls, records)."""
        import tempfile, threading, time
        from unittest import mock
        calls = [] if calls is None else calls
        lock, n_pages = threading.Lock(), [0]
        sample = jload(SAMPLES / "batiste/wtb_availabilities_5010724526705_full.json")
        paths = list(page_eans)

        def fake_http(url, method="GET", headers=None, data=None, timeout=None, spaced=True):
            host = url.split("/")[2]
            t0 = time.monotonic()
            is_api = host == self.API_HOST
            time.sleep(api_delay if is_api else 0.15)
            if not is_api and url != self.LISTING:
                n_pages[0] += 1
                if raise_on_page == n_pages[0]:
                    raise KeyboardInterrupt
            if url == self.LISTING:
                out = (200, {}, b"listing")
            elif is_api:
                ean = url.split("/availabilities/")[1].split("?")[0]
                ans = api_answer(ean) if api_answer else None
                if ans:
                    out = (ans[0], {}, ans[1])
                else:
                    body = dict(sample, prd=dict(sample["prd"], ean=ean))
                    out = (200, {}, json.dumps(body).encode())
            else:
                out = (200, {}, url[len("https://www.batistehair.com"):].encode())
            with lock:
                calls.append((threading.current_thread().name, host, t0, time.monotonic(), url))
            return out

        def fake_classify(status, location, html, wtbid):
            return "widget", list(page_eans[html])

        records = []
        cfg = {"prices": {"listing_url": self.LISTING, "wtbid": WTBID}}
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(sc, "http", fake_http), \
                mock.patch.object(sc, "parse_batiste_listing", lambda html: paths), \
                mock.patch.object(sc, "classify_batiste_page", fake_classify), \
                mock.patch.object(sc, "emit", lambda kind, key, url, at, raw: (records.append((kind, key, raw)),
                                                                              on_emit and on_emit(kind, key, at, raw))), \
                mock.patch.object(sc, "utc_now", utc or sc.utc_now):
            part = sc.batiste_prices(cfg, Path(d))
        return part, calls, records

    def _no_overlap(self, calls):
        calls = sorted(calls, key=lambda c: c[2])
        for a, b in zip(calls, calls[1:]):
            self.assertLessEqual(a[3], b[2] + 1e-6)

    def test_widget_requests_overlap_the_product_pages(self):
        pages = {f"/products/p{i}": [f"501072452{i}0{j}" for j in range(2)] for i in range(6)}
        part, calls, records = self._run(pages)
        page_calls = [c for c in calls if c[1] == "www.batistehair.com" and c[4] != self.LISTING]
        api_calls = [c for c in calls if c[1] == self.API_HOST]
        self.assertEqual(len(page_calls), 6)
        self.assertEqual(len(api_calls), 12)
        self.assertLess(min(c[2] for c in api_calls), max(c[3] for c in page_calls))
        self._no_overlap(page_calls)
        self._no_overlap(api_calls)
        expected = [e for eans in pages.values() for e in eans]
        got = [c[4].split("/availabilities/")[1].split("?")[0] for c in sorted(api_calls, key=lambda c: c[2])]
        self.assertEqual(got, expected)
        self.assertEqual((part["eans"], part["fetched"], part["state"]), (12, 12, "ok"))
        self.assertEqual([r[1] for r in records], [f"wtb/{e}" for e in expected])
        self.assertTrue(all(r[0] == "retailer_availability" for r in records))
        for path, eans in pages.items():
            for e in eans:
                self.assertEqual(records[expected.index(e)][2]["product_pages"], [path])

    def test_an_ean_on_two_pages_is_requested_once_and_lists_both_pages(self):
        part, calls, records = self._run({"/products/a": ["111", "222"], "/products/b": ["222", "333"]})
        api = [c[4].split("/availabilities/")[1].split("?")[0] for c in calls if c[1] == self.API_HOST]
        self.assertEqual(sorted(api), ["111", "222", "333"])
        self.assertEqual(part["eans"], 3)
        by_key = {r[1]: r[2] for r in records}
        self.assertEqual(by_key["wtb/222"]["product_pages"], ["/products/a", "/products/b"])
        self.assertEqual(by_key["wtb/333"]["product_pages"], ["/products/b"])

    def test_stop_rule_keeps_the_rest_not_attempted(self):
        pages = {f"/products/p{i}": [f"90{i}0", f"90{i}1"] for i in range(4)}
        eans = [e for v in pages.values() for e in v]
        part, calls, records = self._run(pages, lambda e: (429, b"slow down") if e == eans[2] else None)
        api = [c[4].split("/availabilities/")[1].split("?")[0] for c in calls if c[1] == self.API_HOST]
        self.assertEqual(api, eans[:3])
        page_calls = [c for c in calls if c[1] == "www.batistehair.com" and c[4] != self.LISTING]
        self.assertEqual(len(page_calls), 4)
        self.assertEqual(len(records), len(eans))
        states = [r[2]["state"] for r in records]
        self.assertEqual(states, ["fetched", "fetched", "failed"] + ["not_attempted"] * (len(eans) - 3))
        self.assertEqual(part["not_attempted"], len(eans) - 3)
        self.assertEqual(part["state"], "partial")

    def test_no_eans(self):
        part, calls, records = self._run({"/products/a": [], "/products/b": []})
        self.assertEqual(part["reason"], "no_eans")
        self.assertEqual(part["state"], "could_not_look")
        self.assertFalse([c for c in calls if c[1] == self.API_HOST])
        self.assertEqual(records, [])

    def test_spacing_is_between_request_starts(self):
        import time
        from unittest import mock

        class Resp:
            status = 200
            headers = {}

            def read(self):
                return b"x"

            def __enter__(self):
                time.sleep(0.3)
                return self

            def __exit__(self, *a):
                return False

        starts = []

        def fake_open(req, timeout=None):
            starts.append(time.monotonic())
            return Resp()

        with mock.patch.object(sc, "SPACING_S", 0.4), \
                mock.patch.dict(sc.R, {"requests": 0}), \
                mock.patch.dict(sc._last, {}, clear=True), \
                mock.patch.object(sc._opener, "open", fake_open):
            sc.http("https://spacing.example/a")
            sc.http("https://spacing.example/b")
        self.assertEqual(len(starts), 2)
        self.assertGreater(starts[1] - starts[0], 0.38)
        self.assertLess(starts[1] - starts[0], 0.6)

    def _ean(self, url):
        return url.split("/availabilities/")[1].split("?")[0]

    def test_page_loop_raising_stops_the_worker(self):
        import threading
        pages = {f"/products/p{i}": [f"80{i}0", f"80{i}1"] for i in range(6)}
        calls = []
        with self.assertRaises(KeyboardInterrupt):
            self._run(pages, api_delay=0.2, raise_on_page=3, calls=calls)
        self.assertFalse([t for t in threading.enumerate() if t.name == "batiste-widget"])
        api = [c for c in calls if c[1] == self.API_HOST]
        self.assertLess(len(api), 4)

    def test_not_us_drops_every_response(self):
        sample = jload(SAMPLES / "batiste/wtb_availabilities_5010724526705_full.json")
        pages = {f"/products/p{i}": [f"70{i}0", f"70{i}1"] for i in range(3)}
        eans = [e for v in pages.values() for e in v]

        def answer(e):
            if e != eans[1]:
                return None
            body = dict(sample, prd=dict(sample["prd"], ean=e), loc=dict(sample["loc"], Country="FR", ISOCurrencySymbol="EUR"))
            return 200, json.dumps(body).encode()

        part, calls, records = self._run(pages, answer)
        api = [self._ean(c[4]) for c in calls if c[1] == self.API_HOST]
        self.assertEqual(api, eans[:2])
        self.assertEqual(len(records), len(eans))
        for _, _, raw in records:
            self.assertEqual(raw["state"], "not_us")
            self.assertIsNone(raw["response"])
        self.assertEqual(part["state"], "could_not_look")
        self.assertEqual(part["reason"], "not_us(country=FR,currency=EUR)")

    def test_unauthorized_product_continues(self):
        pages = {f"/products/p{i}": [f"60{i}0", f"60{i}1"] for i in range(2)}
        eans = [e for v in pages.values() for e in v]
        body = json.dumps({"detail": "Unauthorized ProductUIDs: x"}).encode()
        part, calls, records = self._run(pages, lambda e: (403, body) if e == eans[1] else None)
        api = [self._ean(c[4]) for c in calls if c[1] == self.API_HOST]
        self.assertEqual(api, eans)
        by = {r[1]: r[2] for r in records}
        self.assertEqual(by[f"wtb/{eans[1]}"]["state"], "failed")
        self.assertEqual(by[f"wtb/{eans[1]}"]["error"], "unauthorized_product")
        for e in eans:
            if e != eans[1]:
                self.assertEqual(by[f"wtb/{e}"]["state"], "fetched")

    def test_stop_time_is_taken_by_the_worker(self):
        import threading
        labels, lock = {}, threading.Lock()

        def fake_utc():
            with lock:
                label = f"t{len(labels)}"
                labels[label] = threading.current_thread().name
            return label

        pages = {f"/products/p{i}": [f"50{i}0", f"50{i}1"] for i in range(4)}
        eans = [e for v in pages.values() for e in v]
        emitted = []
        self._run(pages, lambda e: (429, b"slow") if e == eans[2] else None, utc=fake_utc,
                  on_emit=lambda kind, key, at, raw: emitted.append((raw["state"], at)))
        stamps = [at for st, at in emitted if st == "not_attempted"]
        self.assertEqual(len(stamps), len(eans) - 3)
        for at in stamps:
            self.assertEqual(labels[at], "batiste-widget")


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
                return {n: getattr(sc, n) for n in ['SPACING_S']}
        finally:
            importlib.reload(sc)

    def test_pace(self):
        self.assertEqual(self._pace(None)["SPACING_S"], 2)
        self.assertEqual(self._pace("")["SPACING_S"], 2)
        self.assertEqual(self._pace("1")["SPACING_S"], 4)


if __name__ == "__main__":
    unittest.main()
