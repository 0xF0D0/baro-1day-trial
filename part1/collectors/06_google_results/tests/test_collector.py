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


if __name__ == "__main__":
    unittest.main()
