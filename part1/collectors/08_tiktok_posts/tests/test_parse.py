import json, sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import source_collector as sc

SAMPLES = Path(__file__).resolve().parents[3] / "collectors" / "08_tiktok_posts" / "samples" / "apify"


def load(name): return json.loads((SAMPLES / name).read_text())


class ParseTests(unittest.TestCase):
    def test_profile_sample(self):
        recs, bad = sc.path_records(load("profile_deathwishcoffee_popular_10.json")["items"], "profile_popular", "deathwishcoffee")
        self.assertEqual((len(recs), bad), (10, 0))
        self.assertEqual((recs[0]["position"], recs[0]["item"]["id"]), (1, "7106601227126885674"))
        self.assertEqual((recs[9]["position"], recs[9]["item"]["id"]), (10, "7077553857361956142"))

    def test_bad_items(self):
        items = load("profile_deathwishcoffee_popular_10.json")["items"]
        del items[2]["id"]
        items.append({"error": "x"})
        recs, bad = sc.path_records(items, "profile_popular", "deathwishcoffee")
        self.assertEqual((len(recs), bad), (9, 2))
        self.assertEqual([r["position"] for r in recs if r["item"]["id"] == "7082765480859094318"], [4])
        with self.assertRaises(ValueError):
            sc.path_records({"items": []}, "hashtag", "x")

    def test_remove_personal(self):
        item = load("hashtag_deathwishcoffee_10.json")["items"][8]
        self.assertEqual(item["id"], "7623471337998191903")
        for k in ("nickName", "signature", "bioLink", "avatar", "originalAvatarUrl", "profileUrl"): item["authorMeta"][k] = "x"
        for k in ("musicAuthor", "coverMediumUrl", "originalCoverMediumUrl"): item["musicMeta"][k] = "x"
        item["mentions"] = "x"; item["locationMeta"] = "x"
        for m in item["detailedMentions"]: m["nickName"] = m["profileUrl"] = "x"
        out = sc.remove_personal(item)
        for k in ("nickName", "signature", "bioLink", "avatar", "originalAvatarUrl", "profileUrl"): self.assertIsNone(out["authorMeta"][k])
        for k in ("musicAuthor", "coverMediumUrl", "originalCoverMediumUrl"): self.assertIsNone(out["musicMeta"][k])
        self.assertIsNone(out["mentions"]); self.assertIsNone(out["locationMeta"])
        self.assertIsNone(out["detailedMentions"][0]["nickName"]); self.assertIsNone(out["detailedMentions"][0]["profileUrl"])
        self.assertEqual((out["authorMeta"]["name"], out["playCount"], out["detailedMentions"][0]["name"]), ("amiyatok", 2266, "deathwishcoffee"))
        self.assertEqual(item["authorMeta"]["nickName"], "x")
        first = load("hashtag_deathwishcoffee_10.json")["items"][0]
        self.assertNotIn("locationMeta", sc.remove_personal(first))

    def test_cut_sound_title(self):
        def item(name, original, **extra): return {"id": "1", "musicMeta": {"musicName": name, "musicOriginal": original, **extra}}
        for name, want in (("original sound - Holly Invented", "original sound"), ("sonido original - Holly Invented", "sonido original"),
                           ("original sound - A - B", "original sound"), ("original sound", "original sound")):
            it = item(name, True)
            before = json.dumps(it)
            self.assertEqual(sc.cut_sound_title(it)["musicMeta"]["musicName"], want)
            self.assertEqual(json.dumps(it), before)
        for it in (item("Espresso - Sabrina Carpenter", False), {"musicMeta": {"musicName": "Espresso - Sabrina Carpenter"}}):
            self.assertEqual(sc.cut_sound_title(it), it)
        for it in ({"id": "1"}, {"musicMeta": None}, {"musicMeta": "x"}, {"musicMeta": ["original sound - Q"]}, {"musicMeta": {"musicOriginal": True}},
                   {"musicMeta": {"musicOriginal": True, "musicName": None}}):
            self.assertEqual(sc.cut_sound_title(it), it)

    def test_record_has_no_sound_display_name(self):
        raw = {"id": "123", "webVideoUrl": "https://www.tiktok.com/@h/video/123", "musicMeta": {"musicName": "original sound - Holly Invented", "musicOriginal": True}}
        recs, bad = sc.path_records([raw], "hashtag", "x")
        self.assertEqual(bad, 0)
        self.assertNotIn("Holly Invented", json.dumps(recs[0]))
        self.assertEqual(recs[0]["item"]["musicMeta"]["musicName"], "original sound")

    def test_run_input_and_status(self):
        self.assertEqual(sc.run_input("profile_popular", "deathwishcoffee"), load("profile_run.json")["input"])
        self.assertEqual(sc.run_input("hashtag", "deathwishcoffee"), {**load("hashtag_run.json")["input"], "resultsPerPage": 30})
        c, f = {"state": "complete", "error": None}, {"state": "failed", "error": "no_items"}
        self.assertEqual(sc.decide_status({"profile_popular": c, "hashtag": c}), ("ok", ""))
        self.assertEqual(sc.decide_status({"profile_popular": f, "hashtag": f}), ("could_not_look", "profile_popular: no_items; hashtag: no_items"))
        self.assertEqual(sc.decide_status({"profile_popular": c, "hashtag": f}), ("partial", "hashtag: no_items"))


if __name__ == "__main__":
    unittest.main()
