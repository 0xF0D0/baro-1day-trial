import io
import json
import re
import sys
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
COLLECTOR = HERE.parent
sys.path.insert(0, str(COLLECTOR))
import source_collector as sc  # noqa: E402

INPUTS = json.loads((COLLECTOR / "brand_inputs.json").read_text())
BR = INPUTS["black-rifle-coffee"]
ANN, CARDS = "announcement-bar .swiper-slide", "product-carousel product-card"


def el(text):
    return {"outer_html": f"<div>{text}</div>", "text": text}


def item(**kw):
    base = {"requested": BR["home"]["url"], "url": BR["home"]["url"], "title": "Black Rifle Coffee Company", "status": 200,
            "market": ["US", "USD"],
            "slots": {"announcement_bar": [el("a"), el("b")], "bundle_cards": [el("x"), el("y"), el("z")]}}
    base.update(kw)
    return base


class PageFunctionTests(unittest.TestCase):
    def test_selectors_are_json_inside_the_source(self):
        slots = {"a": ANN, "b": 'a[href*="walmart.com"]'}
        src = sc.home_page_function(slots, 8)
        m = re.search(r"const slots = (.*);\n", src)
        self.assertEqual(json.loads(m.group(1)), slots)
        self.assertNotIn('a[href*="walmart.com"]', src)  # only the escaped form is there
        self.assertIn(r'a[href*=\"walmart.com\"]', src)
        self.assertIn("waitForTimeout(8000)", src)
        self.assertIn("typeof response.status === 'function'", src)
        self.assertIn("page.$$eval", src)

    def test_input(self):
        got = sc.home_apify_input(BR)
        src = sc.home_page_function(BR["home"]["slots"], sc.HOME_SETTLE_S)
        self.assertEqual(got, {
            "startUrls": [{"url": "https://www.blackriflecoffee.com/"}], "linkSelector": "", "pageFunction": src,
            "launcher": "chromium",
            "proxyConfiguration": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"], "apifyProxyCountry": "US"},
            "maxPagesPerCrawl": 1, "maxRequestRetries": 0, "pageLoadTimeoutSecs": 60, "waitUntil": "domcontentloaded"})

    def test_black_rifle_uses_the_route(self):
        self.assertEqual(BR["home"]["route"], "apify_playwright")
        self.assertTrue(all("route" not in v["home"] for k, v in INPUTS.items() if k != "black-rifle-coffee"))


class PartTests(unittest.TestCase):
    def test_good_item(self):
        part, raws = sc.home_apify_part("SUCCEEDED", [item()], BR)
        self.assertEqual((part["state"], part["reason"], part["route"], part["slots_not_found"]),
                         ("ok", "", "home_apify", []))
        self.assertIsNone(part["market"])  # no market check for Black Rifle
        self.assertEqual([r["slot"] for r in raws], ["announcement_bar", "bundle_cards"])
        self.assertEqual([len(r["elements"]) for r in raws], [2, 3])
        self.assertEqual(raws[0], {"route": "home_apify", "slot": "announcement_bar", "selector": ANN,
                                   "state": "found", "elements": [el("a"), el("b")]})
        self.assertEqual(raws[1]["selector"], CARDS)

    def test_market_only_with_the_check(self):
        cfg = json.loads(json.dumps(BR))
        cfg["home"]["shopify_market_check"] = True
        part, _ = sc.home_apify_part("SUCCEEDED", [item()], cfg)
        self.assertEqual(part["market"], {"country": "US", "currency": "USD"})
        part, _ = sc.home_apify_part("SUCCEEDED", [item(market=None)], cfg)
        self.assertIsNone(part["market"])

    def test_empty_slot_is_partial(self):
        it = item()
        it["slots"]["bundle_cards"] = []
        part, raws = sc.home_apify_part("SUCCEEDED", [it], BR)
        self.assertEqual((part["state"], part["reason"], part["slots_not_found"]),
                         ("partial", "slots_not_found(bundle_cards)", ["bundle_cards"]))
        self.assertEqual((raws[1]["state"], raws[1]["elements"]), ("not_found", []))

    def test_missing_or_bad_slot_counts_as_not_found(self):
        it = item()
        it["slots"] = {"announcement_bar": "oops"}
        part, raws = sc.home_apify_part("SUCCEEDED", [it], BR)
        self.assertEqual(part["reason"], "slots_not_found(announcement_bar,bundle_cards)")
        self.assertEqual([r["state"] for r in raws], ["not_found", "not_found"])
        self.assertEqual([r["elements"] for r in raws], [[], []])

    def test_could_not_look_cases(self):
        cases = [
            (("FAILED", [item()]), "apify_run_FAILED"),
            (("TIMED-OUT", None), "apify_run_TIMED-OUT"),
            (("SUCCEEDED", []), "home_not_returned"),
            (("SUCCEEDED", None), "home_not_returned"),
            (("SUCCEEDED", [item(status=403)]), "blocked: http_403"),
            (("SUCCEEDED", [item(status=429)]), "blocked: http_429"),
            (("SUCCEEDED", [item(url="https://www.google.com/")]), "blocked: host=www.google.com"),
            (("SUCCEEDED", [item(title="Attention Required! | Cloudflare")]), "blocked: title=attention required"),
            (("SUCCEEDED", [item(title="Just a moment...")]), "blocked: title=just a moment"),
            (("SUCCEEDED", [item(status=500)]), "http_500"),
        ]
        for args, reason in cases:
            part, raws = sc.home_apify_part(*args, BR)
            self.assertEqual((part["state"], part["reason"], raws), ("could_not_look", reason, []), reason)
            self.assertEqual(part["route"], "home_apify")


class RunTests(unittest.TestCase):
    def setUp(self):
        self.buf = io.StringIO()
        sc.R.clear()
        sc.R.update(fh=self.buf, kinds=Counter(), requests=0)

    def test_without_token_sends_nothing(self):
        with mock.patch.object(sc, "read_token", return_value=None), \
                mock.patch.object(sc, "http", side_effect=AssertionError("no request")):
            part, cost = sc.home_apify(BR)
        self.assertEqual((part["state"], part["reason"], part["route"], cost), ("could_not_look", "missing_token", "home_apify", 0))
        self.assertEqual(self.buf.getvalue(), "")

    def test_flow(self):
        calls = []
        run = {"data": {"id": "R1", "status": "SUCCEEDED", "usageTotalUsd": 0.003, "defaultDatasetId": "D1"}}

        def fake_http(url, method="GET", headers=None, data=None, timeout=None, spaced=True):
            calls.append((method, url, spaced))
            if method == "POST":
                return 201, {}, json.dumps({"data": {"id": "R1"}}).encode()
            if "/actor-runs/" in url:
                return 200, {}, json.dumps(run).encode()
            return 200, {}, json.dumps([item()]).encode()

        with mock.patch.object(sc, "read_token", return_value="tok"), mock.patch.object(sc, "http", fake_http):
            part, cost = sc.home_apify(BR)
        self.assertEqual(calls[0][:2], ("POST", "https://api.apify.com/v2/acts/apify~playwright-scraper/runs?timeout=180&memory=2048"))
        self.assertEqual(sum(1 for c in calls if c[0] == "POST"), 1)
        self.assertTrue(all(c[2] is False for c in calls))
        self.assertEqual((part["state"], part["run_id"], part["run_status"], cost), ("ok", "R1", "SUCCEEDED", 0.003))
        recs = [json.loads(line) for line in self.buf.getvalue().splitlines()]
        self.assertEqual([r["key"] for r in recs], ["offer_slot/www.blackriflecoffee.com/announcement_bar",
                                                    "offer_slot/www.blackriflecoffee.com/bundle_cards"])
        self.assertTrue(all(r["kind"] == "offer_slot" and r["url"] == "https://www.blackriflecoffee.com/" for r in recs))
        self.assertEqual(recs[0]["raw"]["route"], "home_apify")

    def test_start_refused(self):
        with mock.patch.object(sc, "read_token", return_value="tok"), \
                mock.patch.object(sc, "http", return_value=(402, {}, b"{}")):
            part, cost = sc.home_apify(BR)
        self.assertEqual((part["state"], part["reason"], cost), ("could_not_look", "apify_start_failed: http_402", 0))

    def test_empty_dataset(self):
        run = {"data": {"id": "R1", "status": "SUCCEEDED", "usageTotalUsd": 0.002, "defaultDatasetId": "D1"}}

        def fake_http(url, method="GET", headers=None, data=None, **kw):
            if method == "POST":
                return 201, {}, json.dumps({"data": {"id": "R1"}}).encode()
            return (200, {}, json.dumps(run).encode()) if "/actor-runs/" in url else (200, {}, b"[]")

        with mock.patch.object(sc, "read_token", return_value="tok"), mock.patch.object(sc, "http", fake_http):
            part, cost = sc.home_apify(BR)
        self.assertEqual((part["state"], part["reason"], cost), ("could_not_look", "home_not_returned", 0.002))
        self.assertEqual(self.buf.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
