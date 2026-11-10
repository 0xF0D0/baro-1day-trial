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


def iso_at(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rec(key, state, epoch, detail=None, files=None):
    if detail is None and state == "fetched":
        detail = {"id": key}
    return json.dumps({"key": key, "fetched_at": iso_at(epoch),
                       "raw": {"detail_state": state, "detail": detail,
                               "script_files": {} if files is None else files}})


class RecentDetailsTests(unittest.TestCase):
    START = 1_800_000_000

    def test_recent_details(self):
        import tempfile
        h = 3600
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "a.jsonl").write_text("\n".join([
                rec("A/1", "fetched", self.START - 2 * h),
                rec("A/2", "fetched", self.START - 30 * h),
                rec("A/3", "failed", self.START - 1 * h),
                rec("A/4", "skipped_recent", self.START - 1 * h),
                rec("A/5", "fetched", self.START - 30 * h),
                "not json",
                json.dumps({"key": "A/6"}),
            ]) + "\n")
            (d / "b.jsonl").write_text(rec("A/5", "fetched", self.START - 3 * h) + "\n")
            (d / "x.jsonl.part").write_text(rec("A/7", "fetched", self.START - 1 * h) + "\n")
            (d / "sub").mkdir()
            (d / "sub" / "c.jsonl").write_text(rec("A/8", "fetched", self.START - 1 * h) + "\n")
            got = sc.recent_details(d, self.START)
            self.assertEqual(set(got), {"A/1", "A/5"})
            self.assertEqual(got["A/5"], {"detail": {"id": "A/5"}, "script_files": {},
                                          "fetched_at": iso_at(self.START - 3 * h)})

    def test_latest_record_wins(self):
        import tempfile
        h = 3600
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "z.jsonl").write_text(rec("A/1", "fetched", self.START - 5 * h, {"v": "old"}, {"0": "o.gz"}) + "\n")
            (d / "a.jsonl").write_text(rec("A/1", "fetched", self.START - 2 * h, {"v": "new"}, {"0": "n.gz"}) + "\n")
            self.assertEqual(sc.recent_details(d, self.START)["A/1"],
                             {"detail": {"v": "new"}, "script_files": {"0": "n.gz"},
                              "fetched_at": iso_at(self.START - 2 * h)})

    def test_unusable_records_not_returned(self):
        import tempfile
        h = 3600
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "a.jsonl").write_text("\n".join([
                rec("A/1", "fetched", self.START - h, {"v": 1}, {"0": "x.gz", "1": None}),
                json.dumps({"key": "A/2", "fetched_at": iso_at(self.START - h),
                            "raw": {"detail_state": "fetched", "detail": None, "script_files": {}}}),
                rec("A/3", "skipped_recent", self.START - h, {"v": 3}),
                rec("A/4", "fetched", self.START - h, {"v": 4}, {"0": "ok.gz"}),
            ]) + "\n")
            self.assertEqual(set(sc.recent_details(d, self.START)), {"A/4"})

    def test_missing_folder(self):
        self.assertEqual(sc.recent_details(Path("/nonexistent/brand_dir_xyz"), self.START), {})


class CollectRecentTests(unittest.TestCase):
    def test_in_scope_recent_ad_is_not_navigated(self):
        import io
        import tempfile
        from unittest import mock
        start = 1_800_000_000
        arrival = datetime.fromtimestamp(start - 60, timezone.utc)

        def item(adv, cid):
            return {"1": adv, "2": cid, "4": 1, "7": {"1": str(start - 3600)}}
        ads = [(item("A", "C1"), arrival), (item("A", "C2"), arrival)]
        fetched = []

        def fake_fetch(b, it, n):
            fetched.append(it["2"])
            return "fetched", None, {"1": it["1"], "2": it["2"], "5": [], "22": None}, arrival

        class FakeCtx:
            def close(self):
                pass

        class FakeBrowser:
            def new_context(self, **kw):
                return FakeCtx()

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "old.jsonl").write_text(rec("A/C1", "fetched", start - 3600, {"id": "old", "22": "adv", "5": []},
                                             {"0": "old.gz"}) + "\n")
            st = {"records": 0, "requests": 0, "expected_total": None, "extra": {}, "block_signal": None, "totals": (2, 2)}
            out = io.StringIO()
            with mock.patch.object(sc, "Browsing", lambda ctx, st, nav: object()), \
                    mock.patch.object(sc, "collect_list", lambda b, st, cfg: (ads, True)), \
                    mock.patch.object(sc, "fetch_detail", fake_fetch):
                status, reason = sc.collect(FakeBrowser(), "x", {"named_advertiser_ids": []}, "r", start, d, out, st, {})
        recs = [json.loads(l) for l in out.getvalue().splitlines()]
        self.assertEqual(fetched, ["C2"])
        self.assertEqual(recs[0]["raw"]["detail_state"], "skipped_recent")
        self.assertEqual(recs[0]["raw"]["detail"], {"id": "old", "22": None, "5": []})
        self.assertIsNone(recs[0]["raw"]["detail_error"])
        self.assertEqual(recs[0]["raw"]["script_files"], {"0": "old.gz"})
        self.assertEqual(recs[0]["raw"]["detail_fetched_at"], iso_at(start - 3600))
        self.assertEqual(recs[0]["fetched_at"], iso_at(start - 60))
        self.assertEqual(recs[1]["raw"]["detail_state"], "fetched")
        self.assertEqual(recs[1]["raw"]["detail_fetched_at"], recs[1]["fetched_at"])
        self.assertEqual(st["extra"]["details_skipped_recent"], 1)
        self.assertEqual(st["extra"]["details_fetched"], 1)
        self.assertEqual(st["extra"]["in_scope"], 2)
        self.assertEqual((status, reason), ("ok", ""))


if __name__ == "__main__":
    unittest.main()
