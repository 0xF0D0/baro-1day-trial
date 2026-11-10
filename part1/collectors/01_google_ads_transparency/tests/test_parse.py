import copy
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import source_collector as sc

SAMPLES = Path(__file__).resolve().parents[3] / "collectors/01_google_ads_transparency/samples"


def load(name):
    return json.loads((SAMPLES / name).read_text())["response"]


class ParseTests(unittest.TestCase):
    def test_deathwish_list(self):
        items, tok, lo, hi = sc.parse_list(load("list_deathwishcoffee.json"))
        self.assertEqual((len(items), tok, lo, hi), (30, None, 30, 30))

    def test_batiste_page1(self):
        items, tok, lo, hi = sc.parse_list(load("list_batiste_page1.json"))
        self.assertEqual((len(items), lo, hi), (40, 67, 67))
        self.assertTrue(tok.startswith("CgoAP7zmiMGEloKvEhBXJNEL"))

    def test_batiste_pages_dedup(self):
        ads = {}
        for name in ("list_batiste_page1.json", "list_batiste_page2.json"):
            for it in sc.parse_list(load(name))[0]:
                ads.setdefault(it["2"], it)
        self.assertEqual(len(ads), 67)
        first = next(iter(ads.values()))
        self.assertEqual("%s/%s" % (first["1"], first["2"]), "AR09009539290362806273/CR18313658679477403649")

    def test_livingproof_totals(self):
        _, _, lo, hi = sc.parse_list(load("list_livingproof_page1.json"))
        self.assertEqual((lo, hi), (200, 300))

    def test_zero(self):
        self.assertEqual(sc.parse_list(load("list_zero.json")), ([], None, None, None))

    def test_bad_shape(self):
        resp = copy.deepcopy(load("list_deathwishcoffee.json"))
        del resp["1"][0]["2"]
        with self.assertRaises(ValueError):
            sc.parse_list(resp)

    def test_in_scope(self):
        items = sc.parse_list(load("list_deathwishcoffee.json"))[0]
        start = int(datetime(2026, 11, 10, 8, 0, 0, tzinfo=timezone.utc).timestamp())
        flags = [sc.in_scope(i, start) for i in items]
        self.assertEqual((sum(flags), len(flags) - sum(flags)), (25, 5))

    def test_script_urls_text(self):
        self.assertEqual(sc.script_urls(load("detail_text_3_variations.json")["1"]), {})

    def test_script_urls_video(self):
        urls = sc.script_urls(load("detail_script_video.json")["1"])
        self.assertEqual(list(urls), [0])
        self.assertTrue(urls[0].startswith("https://displayads-formats.googleusercontent.com/ads/preview/content.js"))


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
                return {n: getattr(sc, n) for n in ['DETAIL_SPACING_S']}
        finally:
            importlib.reload(sc)

    def test_pace(self):
        self.assertEqual(self._pace(None)["DETAIL_SPACING_S"], 2)
        self.assertEqual(self._pace("")["DETAIL_SPACING_S"], 2)
        self.assertEqual(self._pace("1")["DETAIL_SPACING_S"], 10)


if __name__ == "__main__":
    unittest.main()
