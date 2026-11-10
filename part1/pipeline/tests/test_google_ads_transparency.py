import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

import support  # noqa: F401  (puts part1/pipeline on sys.path)
import mappers.google_ads_transparency as gat
from model import MapError, Scope

SAMPLES = Path(__file__).resolve().parents[2] / "collectors" / "01_google_ads_transparency" / "samples"
UTC = timezone.utc

RUN_OK = {"status": "ok", "reason": "", "extra": {"list_complete": True}}
RUN_PARTIAL = {"status": "partial", "reason": "details_failed=1", "extra": {"list_complete": True}}


def sample(name):
    return json.loads((SAMPLES / name).read_text())["response"]


DEATH_ITEMS = sample("list_deathwishcoffee.json")["1"]
TEXT_ITEM = next(i for i in DEATH_ITEMS if i["2"] == "CR15233930458367524865")   # format 1
VIDEO_ITEM = DEATH_ITEMS[0]                                                     # format 3
TEXT_DETAIL = sample("detail_text_3_variations.json")["1"]
VIDEO_DETAIL = sample("detail_script_video.json")["1"]


def record(item, detail=None, state="skipped_old", error=None):
    key = f"{item['1']}/{item['2']}"
    return {"key": key, "kind": "ad",
            "url": f"https://adstransparency.google.com/advertiser/{item['1']}/creative/{item['2']}?region=US",
            "fetched_at": "2026-11-10T08:01:00Z",
            "raw": {"list_item": item, "detail": detail, "detail_state": state, "detail_error": error,
                    "script_files": {}}}


class GoogleAdsTransparencyTest(unittest.TestCase):
    def test_fetched_detail_row(self):
        rec = record(TEXT_ITEM, TEXT_DETAIL, "fetched")
        m = gat.map_run(RUN_OK, [rec])
        row = m.rows[0]
        self.assertEqual((row.table, row.kind, row.key, row.scope, row.url, row.fetched_at),
                         ("ads", "ad", rec["key"], "all", rec["url"], rec["fetched_at"]))
        self.assertIs(row.raw, rec["raw"])
        self.assertEqual(row.columns, {
            "channel": "google", "advertiser_id": "AR06827167829175828481",
            "advertiser_name": "Death Wish Coffee LLC", "format": "text", "headline": None, "body": None,
            "cta": None, "landing_url": None, "landing_domain": "deathwishcoffee.com",
            "started_at": datetime(2026, 9, 2, 12, 56, 25, tzinfo=UTC),
            "last_shown_at": datetime(2026, 11, 10, 0, 57, 10, tzinfo=UTC),
            "variation_count": 3, "placements": None, "offer_code": None})
        self.assertEqual((m.not_fetched, m.scopes), (0, [Scope("all", "ok", "")]))

    def test_formats(self):
        for fmt, name in ((1, "text"), (2, "image"), (3, "video")):
            rec = record({**TEXT_ITEM, "4": fmt})
            self.assertEqual(gat.map_run(RUN_OK, [rec]).rows[0].columns["format"], name)

    def test_video_detail_counts_variations(self):
        row = gat.map_run(RUN_OK, [record(VIDEO_ITEM, VIDEO_DETAIL, "fetched")]).rows[0]
        self.assertEqual((row.columns["format"], row.columns["variation_count"]), ("video", 1))

    def test_variation_count_left_out_unless_fetched(self):
        for state, err in (("skipped_old", None), ("not_attempted", None), ("failed", "timeout")):
            row = gat.map_run(RUN_PARTIAL, [record(TEXT_ITEM, None, state, err)]).rows[0]
            self.assertNotIn("variation_count", row.columns)
            self.assertEqual(row.columns["landing_domain"], "deathwishcoffee.com")
            self.assertEqual(row.columns["last_shown_at"], datetime(2026, 11, 10, 0, 57, 10, tzinfo=UTC))

    def test_null_advertiser_name_stays_null(self):
        row = gat.map_run(RUN_OK, [record({**TEXT_ITEM, "12": None})]).rows[0]
        self.assertIsNone(row.columns["advertiser_name"])

    def test_scopes_follow_run(self):
        self.assertEqual(gat.map_run(RUN_PARTIAL, []).scopes, [Scope("all", "partial", "details_failed=1")])
        run = {"status": "could_not_look", "reason": "blocked", "extra": {}}
        m = gat.map_run(run, [])
        self.assertEqual((m.rows, m.scopes, m.not_fetched), ([], [Scope("all", "could_not_look", "blocked")], 0))

    def test_ending(self):
        self.assertEqual(gat.SOURCE, "google_ads_transparency")
        self.assertEqual(gat.ENDING, {("ads", "ad"): "source_date"})

    def test_bad_inputs_are_keyed_errors(self):
        no_seven = {k: v for k, v in TEXT_ITEM.items() if k != "7"}
        for bad in (record({**TEXT_ITEM, "4": 9}),
                    record(no_seven),
                    record({**TEXT_ITEM, "7": {"1": "soon"}}),
                    record(TEXT_ITEM, {"1": "x"}, "fetched"),
                    {**record(TEXT_ITEM), "kind": "creative"}):
            with self.assertRaises(MapError) as e:
                gat.map_run(RUN_OK, [bad])
            self.assertTrue(str(e.exception).startswith(bad["key"]))


if __name__ == "__main__":
    unittest.main()
