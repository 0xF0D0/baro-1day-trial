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


if __name__ == "__main__":
    unittest.main()
