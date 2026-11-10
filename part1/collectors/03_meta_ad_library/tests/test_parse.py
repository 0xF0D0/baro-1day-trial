import copy, io, json, sys, unittest
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

    def test_records_have_no_media_key(self):
        its = items()[:2]
        S = {"requests": 0, "cost": 0.0, "records": 0, "counts": {}, "runs": {},
             "reasons": [], "bad": set(), "done": set(), "seen": set(), "browser_err": None,
             "missing": False, "page_ids": ["40730897173"], "fh": io.StringIO()}
        run = {"finishedAt": "2026-11-11T08:00:00.000Z"}
        sc.write_page(S, "living-proof", "40730897173", len(its), run, its)
        self.assertEqual(S["records"], 2)
        self.assertEqual(S["reasons"], [])
        recs = [json.loads(l) for l in S["fh"].getvalue().splitlines()]
        self.assertEqual(len(recs), 2)
        for rec in recs:
            self.assertEqual(set(rec["raw"]), {"page_id", "item"})
            snap = rec["raw"]["item"]["snapshot"]
            urls = [v for group in ("images", "videos", "cards") for e in snap[group]
                    for v in e.values() if isinstance(v, str) and v.startswith("https://")]
            self.assertTrue(urls)


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
                return {n: getattr(sc, n) for n in ['SITE_SPACING_S']}
        finally:
            importlib.reload(sc)

    def test_pace(self):
        self.assertEqual(self._pace(None)["SITE_SPACING_S"], 5)
        self.assertEqual(self._pace("")["SITE_SPACING_S"], 5)
        self.assertEqual(self._pace("1")["SITE_SPACING_S"], 15)


if __name__ == "__main__":
    unittest.main()
