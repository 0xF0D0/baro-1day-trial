import io, json, sys, threading, time, unittest
from unittest import mock
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


class ReviewPoolTests(unittest.TestCase):
    def _run(self, n, fake):
        rows = [{"tcin": str(i), "url": f"https://t/p{i}", "reviewCount": 5} for i in range(1, n + 1)]
        ctx = {"fh": io.StringIO(), "kinds": {}, "token": "t", "requests": 0, "runs": {}, "pending": []}
        cell = {"retailer": "target", "search_term": "x", "brand_name": "b"}
        with mock.patch.object(sc, "list_rows", return_value=rows), mock.patch.object(sc, "select", return_value=rows), \
                mock.patch.object(sc, "apify_reviews", side_effect=fake):
            t0 = time.monotonic()
            out = sc.run_cell(ctx, cell)
            took = time.monotonic() - t0
        recs = [json.loads(l) for l in ctx["fh"].getvalue().splitlines()]
        return ctx, out, took, recs

    @staticmethod
    def _item(p):
        return {"reviewBody": "b" + p["key"], "datePublished": "2026-01-01", "inputUrl": p["url"]}

    def test_review_runs_side_by_side(self):
        lock, state = threading.Lock(), {"now": 0, "max": 0}

        def fake(ctx, r, p):
            with lock:
                state["now"] += 1
                state["max"] = max(state["max"], state["now"])
            time.sleep(0.3)
            with lock:
                state["now"] -= 1
                state["threads"].add(threading.current_thread())
            return None, [self._item(p)], None
        writers, real_write = set(), sc.write

        def spy_write(*a, **k):
            writers.add(threading.current_thread())
            return real_write(*a, **k)
        state["threads"] = set()
        with mock.patch.object(sc, "write", side_effect=spy_write):
            ctx, out, took, recs = self._run(10, fake)
        me = threading.current_thread()
        self.assertEqual(writers, {me})
        self.assertNotIn(me, state["threads"])
        self.assertLess(took, 2.5)
        self.assertGreater(state["max"], 1)
        self.assertLessEqual(state["max"], sc.REVIEW_WORKERS)
        reviews = [r for r in recs if r["kind"] == "review"]
        self.assertEqual([r["raw"]["product_key"] for r in reviews], [f"target:{i}" for i in range(1, 11)])
        products = [r for r in recs if r["kind"] == "product"]
        self.assertEqual([r["raw"]["reviews_state"] for r in products], ["fetched"] * 10)

    def test_failure_rule_in_product_order(self):
        def fake(ctx, r, p):
            i = int(p["key"].split(":")[1])
            if i == 1:
                time.sleep(0.4)
            if i in (2, 3, 4):
                return "apify_failed", None, None
            return None, [self._item(p)], None
        ctx, out, took, recs = self._run(8, fake)
        states = {r["key"]: r["raw"]["reviews_state"] for r in recs if r["kind"] == "product"}
        self.assertEqual([states[f"target:{i}"] for i in range(1, 9)],
                         ["fetched"] + ["failed"] * 3 + ["not_attempted"] * 4)
        written = {r["raw"]["product_key"] for r in recs if r["kind"] == "review"}
        self.assertEqual(written, {"target:1"})

    def test_apify_counters_are_guarded(self):
        held = threading.local()

        class RecLock:
            def __init__(self):
                self._l = threading.Lock()

            def __enter__(self):
                self._l.acquire()
                held.v = True

            def __exit__(self, *a):
                held.v = False
                self._l.release()

        writes = []

        class RecDict(dict):
            def __init__(self, name):
                super().__init__()
                self.name = name

            def __setitem__(self, k, v):
                writes.append((self.name, bool(getattr(held, "v", False))))
                super().__setitem__(k, v)

        class Ctx(dict):
            def __setitem__(self, k, v):
                writes.append((k, bool(getattr(held, "v", False))))
                super().__setitem__(k, v)

        def fake_http(method, url, token, body=None):
            if method == "POST":
                return 201, {"data": {"id": "run" + str(threading.get_ident()) + str(time.monotonic_ns()), "status": "SUCCEEDED", "defaultDatasetId": "d"}}
            return 200, []
        ctx = Ctx(token="t", requests=0)
        dict.__setitem__(ctx, "runs", RecDict("runs"))
        with mock.patch.object(sc, "http", side_effect=fake_http), mock.patch.object(sc.time, "sleep"), \
                mock.patch.object(sc, "COUNT_LOCK", RecLock()), mock.patch("sys.stdout", new=io.StringIO()):
            sys.setswitchinterval(1e-6)
            try:
                threads = [threading.Thread(target=sc.apify, args=(ctx, "a", {}, 1)) for _ in range(20)]
                [t.start() for t in threads]
                [t.join() for t in threads]
            finally:
                sys.setswitchinterval(0.005)
        self.assertEqual(ctx["requests"], 20)
        self.assertEqual(len(ctx["runs"]), 20)
        self.assertGreaterEqual(len(writes), 40)
        self.assertTrue(all(h for _, h in writes), writes)

    def test_runs_not_started_are_cancelled_after_a_stop(self):
        calls = []

        def fake(ctx, r, p):
            calls.append(p["key"])
            if p["key"] == "target:1":
                time.sleep(0.2)
                return "blocked", None, None
            time.sleep(0.2)
            return None, [self._item(p)], None
        ctx, out, took, recs = self._run(10, fake)
        self.assertLess(len(calls), 10)
        states = {r["key"]: r["raw"]["reviews_state"] for r in recs if r["kind"] == "product"}
        self.assertEqual(states["target:1"], "failed")
        self.assertEqual([states[f"target:{i}"] for i in range(2, 11)], ["not_attempted"] * 9)


if __name__ == "__main__":
    unittest.main()
