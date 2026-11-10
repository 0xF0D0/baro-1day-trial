import copy, json, sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import source_collector as sc

SAMPLES = Path(__file__).resolve().parents[3] / "collectors/03_meta_ad_library/samples"


def items():
    return json.loads((SAMPLES / "apify/items_livingproof_98.json").read_text())


class ParseTests(unittest.TestCase):
    def test_parse_site_count(self):
        read = lambda n: (SAMPLES / "site" / n).read_text()
        self.assertEqual(sc.parse_site_count(read("list_page_livingproof.html")), 98)
        self.assertEqual(sc.parse_site_count(read("list_page_zero.html")), 0)
        with self.assertRaises(ValueError):
            sc.parse_site_count(read("challenge_403.html"))

    def test_media_targets(self):
        its = items()
        pairs = [t for it in its for t in sc.media_targets(it)]
        self.assertEqual(len(pairs), 350)
        self.assertEqual(len({u.split("?")[0].rsplit("/", 1)[-1] for _, u in pairs}), 273)
        video = next(it for it in its if it["adArchiveID"] == "1107817355342261")
        self.assertEqual([f for f, _ in sc.media_targets(video)],
                         ["snapshot.videos[0].videoSdUrl", "snapshot.videos[0].videoPreviewImageUrl"])

    def test_remove_partner_fields(self):
        dump = lambda x: json.dumps(x, sort_keys=True)
        changed = 0
        for it in items():
            c = copy.deepcopy(it)
            sc.remove_partner_fields(c)
            if dump(c) != dump(it):
                changed += 1
                for k in ("pageName", "pageProfileUri", "pageProfilePictureUrl", "pageId"):
                    self.assertIsNone(c["snapshot"][k])
                self.assertEqual(c["snapshot"]["brandedContent"]["pageId"], "40730897173")
        self.assertEqual(changed, 11)
        it = copy.deepcopy(next(i for i in items() if i["adArchiveID"] == "1776927800243326"))
        it["snapshot"]["brandedContent"] = {"pageId": "111", "pageIsDeleted": False,
                                            "pageProfileUri": "https://www.facebook.com/x/", "pageName": "X"}
        sc.remove_partner_fields(it)
        bc = it["snapshot"]["brandedContent"]
        self.assertIsNone(bc["pageId"]); self.assertIsNone(bc["pageName"]); self.assertIsNone(bc["pageProfileUri"])
        self.assertIs(bc["pageIsDeleted"], False)
        self.assertEqual(it["snapshot"]["pageName"], "Living Proof")

    def test_page_states(self):
        S = {"page_ids": ["A", "B", "C", "D", "E"], "counts": {"A": 5, "C": 0, "E": 7}, "bad": {"B"},
             "done": {"A", "B", "C"}, "reasons": ["blocked(B)", "media_failed(X)"]}
        self.assertEqual(sc.page_states(S), {
            "A": {"ads_complete": True, "reasons": []},
            "B": {"ads_complete": False, "reasons": ["blocked(B)"]},
            "C": {"ads_complete": True, "reasons": []},
            "D": {"ads_complete": False, "reasons": []},
            "E": {"ads_complete": False, "reasons": []}})
        self.assertEqual(sc.page_states({"page_ids": [], "counts": {}, "bad": set(), "done": set(), "reasons": []}), {})

    def test_page_problem(self):
        self.assertEqual(sc.page_problem(90, 100, 150), "incomplete")
        self.assertEqual(sc.page_problem(150, 100, 150), "truncated")
        self.assertEqual(sc.page_problem(120, 100, 150), None)
        self.assertEqual(sc.page_problem(0, 0, 50), None)


if __name__ == "__main__":
    unittest.main()
