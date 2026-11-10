import copy
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

import support  # noqa: F401  (puts part1/pipeline on sys.path)
from mappers.tiktok_posts import ENDING, SOURCE, map_run
from model import MapError, Scope

SAMPLES = Path(__file__).resolve().parents[2] / "collectors" / "08_tiktok_posts" / "samples" / "apify"
PROFILE = json.loads((SAMPLES / "profile_deathwishcoffee_popular_10.json").read_text())["items"]
HASHTAG = json.loads((SAMPLES / "hashtag_deathwishcoffee_10.json").read_text())["items"]

OK_PATH = {"query": "deathwishcoffee", "state": "complete", "error": None}
RUN = {"brand": "death-wish-coffee", "status": "ok", "reason": "",
       "extra": {"profile_popular": {**OK_PATH, "records": 10}, "hashtag": {**OK_PATH, "records": 10}}}


def post(path, position, item, fetched_at="2026-11-10T00:00:00Z"):
    return {"key": f"{path}/{item['id']}", "kind": "post", "url": item["webVideoUrl"], "fetched_at": fetched_at,
            "raw": {"path": path, "query": "deathwishcoffee", "position": position, "item": item}}


class TiktokPostsTest(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(SOURCE, "tiktok_posts")
        self.assertEqual(ENDING, {("posts", "post"): "never"})

    def test_profile_post_of_the_brand(self):
        rec = post("profile_popular", 1, PROFILE[0])
        row = map_run(RUN, [rec]).rows[0]
        self.assertEqual((row.table, row.kind, row.key, row.scope), ("posts", "post", "7106601227126885674", "profile_popular"))
        self.assertEqual((row.url, row.fetched_at), (rec["url"], "2026-11-10T00:00:00Z"))
        self.assertIs(row.raw, rec["raw"])
        self.assertEqual(row.columns, {
            "post_id": "7106601227126885674", "posted_at": datetime(2022, 6, 7, 20, 42, 19, tzinfo=timezone.utc),
            "creator_handle": "deathwishcoffee", "creator_is_brand": True, "creator_followers": 371900,
            "views": 1800000, "likes": 420500, "comments": 1093, "shares": 2819, "saves": 19785,
            "caption": PROFILE[0]["text"],
            "hashtags": ["duet", "worldsstrongestcoffee", "coffee", "coffeeconctions", "cocktailrecipes"],
            "surfaced_by": ["profile_popular"]})

    def test_hashtag_post_of_a_creator(self):
        c = map_run(RUN, [post("hashtag", 9, HASHTAG[8])]).rows[0].columns
        self.assertEqual((c["creator_handle"], c["creator_is_brand"], c["creator_followers"], c["views"], c["surfaced_by"]),
                         ("amiyatok", False, 483, 2266, ["hashtag"]))
        self.assertEqual(c["posted_at"], datetime(2026, 3, 31, 17, 22, 52, tzinfo=timezone.utc))
        self.assertEqual(c["hashtags"], ["coffee", "justagirl", "deathwishcoffee", "fyp", "xyzabc"])

    def test_hashtags_come_from_text_when_the_list_is_empty(self):
        item = next(i for i in PROFILE + HASHTAG if i["text"].startswith("It’s here. It’s limited"))
        self.assertEqual(item["hashtags"], [])
        c = map_run(RUN, [post("hashtag", 1, item)]).rows[0].columns
        self.assertEqual(c["hashtags"], ["peppermintmocha", "peppermintcoffee", "holidaycoffee", "deathwishcoffee"])
        plain = next(i for i in HASHTAG if "#" not in i["text"] and not i["hashtags"])
        self.assertEqual(map_run(RUN, [post("hashtag", 1, plain)]).rows[0].columns["hashtags"], [])

    def test_hashtags_are_not_repeated(self):
        item = {**copy.deepcopy(PROFILE[0]), "text": "#Duet #coffee #new", "hashtags": [{"name": "duet"}, {"name": "coffee"}]}
        self.assertEqual(map_run(RUN, [post("profile_popular", 1, item)]).rows[0].columns["hashtags"], ["duet", "coffee", "new"])

    def test_caption_only_hashtag_is_lower_cased(self):
        item = {**copy.deepcopy(PROFILE[0]), "text": "Hi #MixedCase #coffee", "hashtags": [{"name": "Coffee"}]}
        self.assertEqual(map_run(RUN, [post("profile_popular", 1, item)]).rows[0].columns["hashtags"], ["coffee", "mixedcase"])

    def test_unknown_path_state_is_keyed_error(self):
        run = {**RUN, "extra": {"profile_popular": {**OK_PATH, "state": "weird"}}}
        with self.assertRaises(MapError) as e:
            map_run(run, [])
        self.assertTrue(str(e.exception).startswith("profile_popular"), str(e.exception))

    def test_post_found_by_both_paths_is_one_row(self):
        hashtag = copy.deepcopy(PROFILE[0])
        hashtag["playCount"] = 1
        a, b = post("profile_popular", 1, PROFILE[0], "2026-11-10T00:00:00Z"), post("hashtag", 4, hashtag, "2026-11-10T00:05:00Z")
        for records in ([a, b], [b, a]):
            m = map_run(RUN, records)
            self.assertEqual(len(m.rows), 1)
            row = m.rows[0]
            self.assertEqual((row.key, row.scope, row.fetched_at, row.url), ("7106601227126885674", "profile_popular", "2026-11-10T00:00:00Z", a["url"]))
            self.assertIs(row.raw, a["raw"])
            self.assertEqual((row.columns["surfaced_by"], row.columns["views"]), (["profile_popular", "hashtag"], 1800000))

    def test_post_found_only_by_hashtag_when_other_posts_come_from_profile(self):
        m = map_run(RUN, [post("profile_popular", 1, PROFILE[0]), post("hashtag", 1, HASHTAG[0])])
        self.assertEqual([(r.key, r.scope) for r in m.rows], [("7106601227126885674", "profile_popular"), ("7699600078079593750", "hashtag")])

    def test_scopes_of_a_complete_run(self):
        self.assertEqual(map_run(RUN, []).scopes, [Scope("profile_popular", "ok", ""), Scope("hashtag", "ok", "")])

    def test_scopes_of_an_incomplete_run(self):
        run = {**RUN, "status": "partial", "reason": "profile_popular: short(9/10); hashtag: run_FAILED",
               "extra": {"profile_popular": {**OK_PATH, "state": "incomplete", "error": "short(9/10)"},
                         "hashtag": {**OK_PATH, "state": "failed", "error": "run_FAILED"}}}
        self.assertEqual(map_run(run, []).scopes, [Scope("profile_popular", "partial", "short(9/10)"),
                                                   Scope("hashtag", "could_not_look", "run_FAILED")])

    def test_run_without_path_results_gets_all_scope(self):
        run = {**RUN, "status": "could_not_look", "reason": "missing_token", "extra": {}}
        m = map_run(run, [])
        self.assertEqual((m.rows, m.not_fetched, m.scopes), ([], 0, [Scope("all", "could_not_look", "missing_token")]))

    def test_unknown_brand_is_an_error(self):
        with self.assertRaises(MapError) as e:
            map_run({**RUN, "brand": "nobody"}, [post("profile_popular", 1, PROFILE[0])])
        self.assertTrue(str(e.exception).startswith("nobody"))

    def test_other_brand_uses_its_own_profile(self):
        c = map_run({**RUN, "brand": "batiste"}, [post("profile_popular", 1, PROFILE[0])]).rows[0].columns
        self.assertFalse(c["creator_is_brand"])

    def test_unknown_inputs_are_errors(self):
        good = post("profile_popular", 1, PROFILE[0])
        bad_count = copy.deepcopy(good)
        bad_count["raw"]["item"]["playCount"] = "1.8M"
        bad_time = copy.deepcopy(good)
        bad_time["raw"]["item"]["createTime"] = "yesterday"
        no_author = copy.deepcopy(good)
        del no_author["raw"]["item"]["authorMeta"]
        for bad in ({**good, "kind": "video"}, post("search", 1, PROFILE[0]), bad_count, bad_time, no_author):
            with self.assertRaises(MapError) as e:
                map_run(RUN, [bad])
            self.assertTrue(str(e.exception).startswith(bad["key"]), str(e.exception))


if __name__ == "__main__":
    unittest.main()
