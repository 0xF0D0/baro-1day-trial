import json, sys, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import source_collector as sc

SAMPLES = HERE.parents[2] / "collectors" / "06_google_results" / "samples" / "apify"
TERMS = ["batiste dry shampoo", "death wish coffee", "jinx dog food"]
ITEMS = json.loads((SAMPLES / "trial_run_dataset.json").read_text())


class CollectorTest(unittest.TestCase):
    def test_actor_input(self):
        want = json.loads((SAMPLES / "trial_input.json").read_text())
        want.update(focusOnPaidAds=False, saveHtmlToKeyValueStore=False)
        self.assertEqual(sc.actor_input(TERMS), want)

    def test_match(self):
        res = sc.match(TERMS, ITEMS)
        self.assertEqual([e for _, e in res], [None] * 3)
        self.assertEqual([len(i["organicResults"]) for i, _ in res], [7, 6, 9])
        kw = json.loads((HERE.parent / "brand_inputs.json").read_text())["batiste"]["keywords"]
        res = sc.match(kw, ITEMS)
        self.assertIsNone(res[0][1])
        self.assertEqual(res[1:], [(None, "missing")] * 19)

    def test_remove_names(self):
        item = next(i for i in ITEMS if i["searchQuery"]["term"] == "death wish coffee")
        before = json.dumps(item)
        out = sc.remove_names(item)
        self.assertEqual([r["websiteTitle"] for r in out["organicResults"]],
                         ["Death Wish Coffee", "Amazon.com", None, None, "Walmart", "Wikipedia"])
        self.assertEqual(json.dumps(item), before)

    def test_drop_personal_info(self):
        item = {"a": 1, "organicResults": [{"url": "u1", "personalInfo": {"rawText": "x"}, "title": "t"}, "odd", {"url": "u2"}],
                "paidResults": [{"url": "p", "personalInfo": {}}], "suggestedResults": [{"personalInfo": 1, "q": 2}],
                "paidProducts": [{"personalInfo": 1}], "z": 2}
        before = json.dumps(item)
        out = sc.drop_personal_info(item)
        self.assertEqual(out["organicResults"], [{"url": "u1", "title": "t"}, "odd", {"url": "u2"}])
        self.assertEqual(list(out["organicResults"][0]), ["url", "title"])
        self.assertEqual(out["paidResults"], [{"url": "p"}])
        self.assertEqual(out["suggestedResults"], [{"q": 2}])
        self.assertEqual(out["paidProducts"], [{}])
        self.assertEqual(list(out), list(item))
        self.assertEqual(json.dumps(item), before)
        for odd in ({"a": 1}, {"organicResults": None}, {"organicResults": "x"}):
            self.assertEqual(sc.drop_personal_info(odd), odd)

    def test_collect_writes_no_personal_info(self):
        import io
        from unittest import mock
        item = json.loads(json.dumps(next(i for i in ITEMS if i["searchQuery"]["term"] == "death wish coffee")))
        item["organicResults"][0]["personalInfo"] = {"rawText": "invented", "location": "Nowhere", "companyName": "Acme"}
        run = {"status": "SUCCEEDED", "finishedAt": "2026-11-11T00:00:00.000Z", "chargedEventCounts": {"search-page-scraped": 1}}
        st = {"token": "t", "requests": 0, "records": 0, "status": None, "cost": 0, "run_id": None}
        out = io.StringIO()
        with mock.patch.object(sc, "call", return_value={"data": {"id": "r", "defaultDatasetId": "d"}}) as call, \
                mock.patch.object(sc, "read_run", return_value=run):
            call.side_effect = [{"data": {"id": "r", "defaultDatasetId": "d"}}, [item]]
            sc.collect(st, ["death wish coffee"], out)
        rec = json.loads(out.getvalue().splitlines()[0])
        self.assertIsNotNone(rec["raw"]["serp"])
        self.assertNotIn("personalInfo", json.dumps(rec["raw"]))

    def test_redact_emails(self):
        serp = {"organicResults": [{"url": "https://a.com/x@y.com", "link": "mailto:jane@corp.example", "title": "Mail jane.q+x@corp.example now",
                                    "description": "sales@shop.example or Jane.Doe@mail.example.org",
                                    "siteLinks": [{"title": "t", "description": "write to bob_1@careers.example"}],
                                    "emphasizedKeywords": ["a@b.example", "plain"], "position": 1}, "odd"],
                "paidResults": [{"description": "x@y.example"}], "other": [{"title": "also@z.example"}], "n": 1,
                "aiOverview": {"content": "write support@brand.example", "url": "https://x.example/a@b.example"}}
        before = json.dumps(serp)
        out = sc.redact_emails(serp)
        r = out["organicResults"][0]
        self.assertEqual((r["url"], r["link"]), ("https://a.com/x@y.com", "mailto:jane@corp.example"))
        self.assertEqual(r["title"], "Mail REDACTED@corp.example now")
        self.assertEqual(r["description"], "REDACTED@shop.example or REDACTED@mail.example.org")
        self.assertEqual(r["siteLinks"][0]["description"], "write to REDACTED@careers.example")
        self.assertEqual(r["emphasizedKeywords"], ["REDACTED@b.example", "plain"])
        self.assertEqual((r["position"], out["organicResults"][1]), (1, "odd"))
        self.assertEqual(out["paidResults"][0]["description"], "REDACTED@y.example")
        self.assertEqual(out["other"], [{"title": "REDACTED@z.example"}])
        self.assertEqual(out["aiOverview"], {"content": "write REDACTED@brand.example", "url": "https://x.example/a@b.example"})
        self.assertEqual(json.dumps(serp), before)
        for odd in ({"a": 1}, {"organicResults": None}):
            self.assertEqual(sc.redact_emails(odd), odd)

    def test_is_personal_profile_url(self):
        for u in ("https://www.facebook.com/jane.doe.12345", "https://m.facebook.com/jane.doe.12345/posts/9", "https://www.facebook.com/people/Jane-Doe/1000123/",
                  "https://facebook.com/profile.php?id=1000123"):
            self.assertTrue(sc.is_personal_profile_url(u), u)
        for u in ("https://www.facebook.com/BrandPage/", "https://www.facebook.com/brand.page/posts/1", "https://www.facebook.com/groups/123/",
                  "https://www.instagram.com/jane.doe.12345/", "https://notfacebook.com/jane.doe.12345", None, 5):
            self.assertFalse(sc.is_personal_profile_url(u), u)

    def test_redact_personal_pages(self):
        keep = {"url": "https://www.facebook.com/BrandPage/", "title": "Brand", "description": "d"}
        serp = {"organicResults": [
            {"url": "https://www.facebook.com/jane.doe.12345/posts/77", "link": "https://www.facebook.com/jane.doe.12345/posts/77",
             "displayedUrl": "https://www.facebook.com › jane.doe.12345 › posts", "title": "Jane Doe", "description": "post text", "position": 1},
            {"url": "https://www.facebook.com/people/Jane-Doe/1000123/", "title": "t", "description": "d"},
            {"url": "https://www.facebook.com/profile.php?id=1000123", "title": "t", "description": "d"}, keep, "odd"],
            "paidResults": [{"url": "https://www.facebook.com/jane.doe.12345", "title": "t"}], "n": 1}
        before = json.dumps(serp)
        out = sc.redact_personal_pages(serp)
        a, b, c = out["organicResults"][:3]
        self.assertEqual(a["url"], "https://www.facebook.com/REDACTED/posts/77")
        self.assertEqual(a["link"], a["url"])
        self.assertEqual(a["displayedUrl"], "https://www.facebook.com › REDACTED › posts")
        self.assertEqual((a["title"], a["description"], a["position"]), (None, None, 1))
        self.assertEqual(b["url"], "https://www.facebook.com/people/REDACTED/REDACTED/")
        self.assertEqual(c["url"], "https://www.facebook.com/profile.php?REDACTED")
        self.assertEqual((b["title"], c["description"]), (None, None))
        self.assertEqual(out["organicResults"][3:], [keep, "odd"])
        self.assertEqual(out["paidResults"], [{"url": "https://www.facebook.com/REDACTED", "title": None, "description": None}])
        self.assertEqual(sc.redact_personal_pages(serp), out)
        self.assertEqual(json.dumps(serp), before)

    def test_collect_writes_no_name_or_address(self):
        import io
        from unittest import mock
        item = json.loads(json.dumps(next(i for i in ITEMS if i["searchQuery"]["term"] == "death wish coffee")))
        item["organicResults"][0].update(url="https://www.facebook.com/jane.invented.12345/posts/1", title="Jane Invented", description="mail jane@corp.example")
        item["organicResults"][1]["description"] = "write to bob.invented@corp.example"
        run = {"status": "SUCCEEDED", "finishedAt": "2026-11-11T00:00:00.000Z", "chargedEventCounts": {"search-page-scraped": 1}}
        st = {"token": "t", "requests": 0, "records": 0, "status": None, "cost": 0, "run_id": None}
        out = io.StringIO()
        with mock.patch.object(sc, "call") as call, mock.patch.object(sc, "read_run", return_value=run):
            call.side_effect = [{"data": {"id": "r", "defaultDatasetId": "d"}}, [item]]
            sc.collect(st, ["death wish coffee"], out)
        text = out.getvalue()
        for s in ("invented", "Invented", "jane@", "bob.invented@"):
            self.assertNotIn(s, text)
        self.assertIn("REDACTED@corp.example", text)
        self.assertIn("https://www.facebook.com/REDACTED/posts/1", text)


if __name__ == "__main__":
    unittest.main()
