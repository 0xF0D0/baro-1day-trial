import copy
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

import support  # noqa: F401  (puts part1/pipeline on sys.path)
from mappers.meta_ad_library import ENDING, SOURCE, map_run
from model import MapError, Scope

SAMPLE = (Path(__file__).resolve().parents[2] / "collectors" / "03_meta_ad_library" / "samples" / "apify"
          / "items_livingproof_98.json")
ITEMS = {i["adArchiveID"]: i for i in json.loads(SAMPLE.read_text())}

BODY_COUNT = 98

RUN = {"status": "ok", "reason": "", "extra": {"counts": {"40730897173": 98}, "runs": {}, "media_files": 0,
                                               "media_failed": 0}}


def record(ad_id, item=None):
    item = copy.deepcopy(item or ITEMS[ad_id])
    return {"key": ad_id, "kind": "ad", "url": f"https://www.facebook.com/ads/library/?id={ad_id}",
            "fetched_at": "2026-11-10T08:55:17Z", "raw": {"page_id": "40730897173", "item": item, "media": {}}}


class MetaAdLibraryTest(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(SOURCE, "meta_ad_library")
        self.assertEqual(ENDING, {("ads", "ad"): "absent"})

    def test_video_ad(self):
        rec = record("1107817355342261")
        m = map_run(RUN, [rec])
        row = m.rows[0]
        self.assertEqual((row.table, row.kind, row.key, row.scope), ("ads", "ad", "1107817355342261", "all"))
        self.assertEqual((row.url, row.fetched_at, row.raw), (rec["url"], rec["fetched_at"], rec["raw"]))
        item = rec["raw"]["item"]
        self.assertEqual(row.columns, {
            "channel": "meta", "advertiser_id": "40730897173", "advertiser_name": "Living Proof",
            "format": "video", "headline": "Heat Styling Spray", "body": item["snapshot"]["body"]["text"],
            "cta": "Shop now",
            "landing_url": "https://www.livingproof.com/collections/hairspray/products/style-lab-flex-hairspray?variant=47057960173820",
            "landing_domain": "livingproof.com",
            "started_at": datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc),
            "last_shown_at": None, "variation_count": 1,
            "placements": item["publisherPlatform"], "offer_code": None})
        self.assertEqual(row.columns["started_at"], datetime.fromtimestamp(1793606400, timezone.utc))
        self.assertIsNotNone(row.columns["started_at"].tzinfo)

    def test_card_text_fills_null_snapshot_text(self):
        rec = record("1776927800243326")
        self.assertIsNone(rec["raw"]["item"]["snapshot"]["body"])
        c = map_run(RUN, [rec]).rows[0].columns
        card = rec["raw"]["item"]["snapshot"]["cards"][0]
        self.assertEqual(c["headline"], rec["raw"]["item"]["snapshot"]["title"])  # snapshot wins
        self.assertTrue(c["headline"].startswith("Living Proof Perfect Hair Day"))
        self.assertEqual(c["body"], card["body"])
        self.assertTrue(c["body"].startswith("A heat protectant spray that smooths"))
        self.assertEqual(c["cta"], "Shop now")  # the snapshot's own value wins over the card's "Shop Now"
        self.assertEqual(c["landing_url"], "https://www.amazon.com/Living-proof-Perfect-Styling-Spray/dp/B07XC9XZGN/")
        self.assertEqual(c["landing_domain"], "amazon.com")

    def test_first_non_empty_card_gives_text(self):
        rec = record("900663596346931")
        cards = rec["raw"]["item"]["snapshot"]["cards"]
        self.assertEqual([c["body"] == "" for c in cards[:2]], [True, False])
        c = map_run(RUN, [rec]).rows[0].columns
        self.assertEqual(c["body"], "Love a good blowout? Protect your hair from heat while smoothing "
                                    "and keeping your style looking polished.")

    def test_empty_snapshot_value_falls_back_and_nothing_gives_none(self):
        rec = record("1776927800243326")
        snap = rec["raw"]["item"]["snapshot"]
        snap["title"] = ""
        self.assertEqual(map_run(RUN, [rec]).rows[0].columns["headline"], "Heat Styling Spray")
        for card in snap["cards"]:
            card["title"] = None
        self.assertIsNone(map_run(RUN, [rec]).rows[0].columns["headline"])
        snap["cards"] = []
        snap["linkUrl"] = None
        c = map_run(RUN, [rec]).rows[0].columns
        self.assertEqual((c["body"], c["landing_url"], c["landing_domain"]), (None, None, None))

    def test_sample_coverage(self):
        cols = [map_run(RUN, [record(a)]).rows[0].columns for a in ITEMS]
        self.assertEqual(sum(c["body"] is not None for c in cols), BODY_COUNT)
        self.assertEqual(sum(c["landing_url"] is not None for c in cols), 98)

    def test_dco_ad_with_null_group_count(self):
        ad = next(a for a, i in ITEMS.items() if i["snapshot"]["body"] is None and i["collationCount"] is None)
        c = map_run(RUN, [record(ad)]).rows[0].columns
        self.assertIsNone(c["variation_count"])
        self.assertEqual(c["format"], "dco")

    def test_partner_ad_keeps_brand_page_and_no_creator(self):
        ad = next(a for a, i in ITEMS.items() if i["snapshot"]["pageId"] != i["pageId"])
        rec = record(ad)
        item = rec["raw"]["item"]
        for k in ("pageName", "pageProfileUri", "pageProfilePictureUrl", "pageId"):
            item["snapshot"][k] = None
        c = map_run(RUN, [rec]).rows[0].columns
        self.assertEqual((c["advertiser_id"], c["advertiser_name"]), ("40730897173", "Living Proof"))

    def test_landing_domain_strips_www_and_lowercases_host(self):
        for url, domain in (("http://livingproof.com/pages/dry-shampoo", "livingproof.com"),
                            ("https://WWW.Amazon.com/dp/B1", "amazon.com"), (None, None)):
            rec = record("1776927800243326")
            rec["raw"]["item"]["snapshot"]["linkUrl"] = url
            rec["raw"]["item"]["snapshot"]["cards"] = []
            c = map_run(RUN, [rec]).rows[0].columns
            self.assertEqual((c["landing_url"], c["landing_domain"]), (url, domain))

    def test_scopes_follow_run_status(self):
        self.assertEqual(map_run(RUN, []).scopes, [Scope("all", "ok", "")])
        run = {**RUN, "status": "partial", "reason": "incomplete(40730897173): got=90 count=98"}
        self.assertEqual(map_run(run, [record("1776927800243326")]).scopes,
                         [Scope("all", "partial", "incomplete(40730897173): got=90 count=98")])
        run = {**RUN, "status": "could_not_look", "reason": "missing_token"}
        self.assertEqual(map_run(run, []).scopes, [Scope("all", "could_not_look", "missing_token")])
        self.assertEqual(map_run(RUN, [record("1776927800243326")]).not_fetched, 0)

    def test_scopes_per_page(self):
        pages = {"40730897173": {"ads_complete": True, "reasons": []},
                 "999": {"ads_complete": False, "reasons": ["blocked(999)", "count_timeout(999)"]}}
        run = {"status": "partial", "reason": "blocked(999)", "extra": {"pages": pages}}
        m = map_run(run, [record("1776927800243326")])
        self.assertEqual(m.scopes, [Scope("40730897173", "ok", ""),
                                    Scope("999", "could_not_look", "blocked(999); count_timeout(999)")])
        self.assertEqual([r.scope for r in m.rows], ["40730897173"])
        other = record("1107817355342261")
        other["raw"]["page_id"] = "999"
        m = map_run(run, [record("1776927800243326"), other])
        self.assertEqual(m.scopes[1], Scope("999", "partial", "blocked(999); count_timeout(999)"))
        self.assertEqual([r.scope for r in m.rows], ["40730897173", "999"])

    def test_complete_page_without_records_is_ok(self):
        pages = {"40730897173": {"ads_complete": True, "reasons": []}}
        run = {"status": "ok", "reason": "", "extra": {"pages": pages}}
        self.assertEqual(map_run(run, []).scopes, [Scope("40730897173", "ok", "")])

    def test_empty_reasons_fall_back_to_run_reason(self):
        pages = {"999": {"ads_complete": False, "reasons": []}}
        run = {"status": "could_not_look", "reason": "missing_token", "extra": {"pages": pages}}
        self.assertEqual(map_run(run, []).scopes, [Scope("999", "could_not_look", "missing_token")])

    def test_missing_or_empty_pages_keep_single_scope(self):
        for extra in ({}, {"pages": {}}):
            run = {"status": "ok", "reason": "", "extra": extra}
            m = map_run(run, [record("1776927800243326")])
            self.assertEqual(m.scopes, [Scope("all", "ok", "")])
            self.assertEqual([r.scope for r in m.rows], ["all"])

    def test_record_page_not_in_pages_gets_partial_scope(self):
        pages = {"40730897173": {"ads_complete": True, "reasons": []}}
        run = {"status": "ok", "reason": "", "extra": {"pages": pages}}
        rec = record("1776927800243326")
        rec["raw"]["page_id"] = "555"
        m = map_run(run, [rec])
        self.assertEqual(m.scopes, [Scope("40730897173", "ok", ""), Scope("555", "partial", "")])
        self.assertEqual(m.rows[0].scope, "555")

    def test_unknown_kind_raises_keyed_error(self):
        rec = {**record("1776927800243326"), "kind": "page"}
        with self.assertRaisesRegex(MapError, r"^1776927800243326"):
            map_run(RUN, [rec])

    def test_unconvertible_values_raise_keyed_error(self):
        for path, value in ((("startDate",), "yesterday"), (("startDate",), None),
                            (("snapshot",), None), (("publisherPlatform",), 5),
                            (("collationCount",), "2"), (("collationCount",), 1.5)):
            rec = record("1776927800243326")
            node = rec["raw"]["item"]
            for p in path[:-1]:
                node = node[p]
            node[path[-1]] = value
            with self.assertRaisesRegex(MapError, r"^1776927800243326", msg=str(path)):
                map_run(RUN, [rec])
        rec = record("1776927800243326")
        del rec["raw"]["item"]
        with self.assertRaisesRegex(MapError, r"^1776927800243326"):
            map_run(RUN, [rec])


if __name__ == "__main__":
    unittest.main()
