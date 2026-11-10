import json
import unittest
from pathlib import Path

import support  # noqa: F401  (puts part1/pipeline on sys.path)
from mappers.tiktok_ads import ENDING, SOURCE, map_run
from model import MapError, Scope

DATASET = Path(__file__).resolve().parents[2] / "collectors" / "02_tiktok_ad_library" / "samples" / "apify_fetchcat_dataset.json"
ROWS = {r["adId"]: r for r in json.loads(DATASET.read_text())["response"]}

RUN_OK = {"source": "tiktok_ads", "status": "ok", "reason": "", "extra": {"rows": 5}}
RUN_PARTIAL = {"source": "tiktok_ads", "status": "partial", "reason": "media_failed=1", "extra": {"rows": 5}}


def ad(ad_id, terms, **item):
    row = {**ROWS[ad_id], **item}
    return {"key": ad_id, "kind": "ad", "url": row["detailUrl"], "fetched_at": "2026-11-10T07:51:30Z",
            "raw": {"item": row, "matched_terms": terms,
                    "video": {"file": f"media/b/r/{ad_id}.mp4", "bytes": 1, "sha256": "x", "error": None},
                    "cover": {"file": None, "bytes": None, "sha256": None, "error": "http_403"}}}


LP, JINX = "7531018269878140936", "7609180755211075600"


class TiktokAdsTest(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(SOURCE, "tiktok_ads")
        self.assertEqual(ENDING, {("ads", "ad"): "absent"})

    def test_ad_with_brand_name(self):
        rec = ad(LP, ["living proof", "livingproof"])
        row = map_run(RUN_OK, [rec]).rows[0]
        self.assertEqual((row.table, row.kind, row.key, row.scope, row.url, row.fetched_at),
                         ("ads", "ad", LP, "all", rec["url"], "2026-11-10T07:51:30Z"))
        self.assertIs(row.raw, rec["raw"])
        self.assertEqual(row.columns, {
            "channel": "tiktok", "advertiser_id": None, "advertiser_name": "Living Proof", "format": "video",
            "headline": None, "body": ROWS[LP]["adText"], "cta": None, "landing_url": None, "landing_domain": None,
            "started_at": None, "last_shown_at": None, "variation_count": None, "placements": None, "offer_code": None})

    def test_ad_without_brand_name(self):
        row = map_run(RUN_OK, [ad(JINX, ["@jinx", "#jinxpartner"])]).rows[0]
        self.assertIsNone(row.columns["advertiser_name"])
        self.assertEqual(row.columns["body"], "POV: ur gf wants to have a BABY  @Jinx is now available only at Walmart #jinxpartner #WalmartPets #IYWYK")

    def test_scopes_follow_run(self):
        self.assertEqual(map_run(RUN_OK, []).scopes, [Scope("all", "ok", "")])
        self.assertEqual(map_run(RUN_PARTIAL, [ad(LP, [])]).scopes, [Scope("all", "partial", "media_failed=1")])
        self.assertEqual(map_run(RUN_OK, [ad(LP, [])]).not_fetched, 0)

    def test_unknown_kind_raises_with_key(self):
        rec = {**ad(LP, []), "kind": "video"}
        with self.assertRaises(MapError) as cm:
            map_run(RUN_OK, [rec])
        self.assertTrue(str(cm.exception).startswith(LP))

    def test_unconvertible_value_raises_with_key(self):
        for bad in ({"adText": 5}, {"brandName": ["x"]}):
            with self.assertRaises(MapError) as cm:
                map_run(RUN_OK, [ad(LP, [], **bad)])
            self.assertTrue(str(cm.exception).startswith(LP))
        rec = ad(LP, [])
        del rec["raw"]["item"]
        with self.assertRaises(MapError) as cm:
            map_run(RUN_OK, [rec])
        self.assertTrue(str(cm.exception).startswith(LP))


if __name__ == "__main__":
    unittest.main()
