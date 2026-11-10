import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import source_collector as sc  # noqa: E402

S = Path(__file__).resolve().parents[3] / "collectors/04_amazon/samples/apify"


def load(name):
    return json.loads((S / name).read_text())


def asins(cands):
    return [c["asin"] for c in cands]


class Candidates(unittest.TestCase):
    def test_death_wish(self):
        rows = load("dataset_apt_marble_dw60.json")
        c, m = sc.select_candidates(rows, ["death wish coffee"])
        a = asins(c)
        self.assertEqual(len(c), 27)
        self.assertEqual(a[:4], ["B0182HSTIM", "B006CQ1ZHI", "B08VFVSBXM", "B00FM03XCU"])
        self.assertEqual(m["B0182HSTIM"], ["B0CGRPR2PW", "B00FJYTGBG"])
        self.assertEqual(m["B006CQ1ZHI"], ["B00TXTNL2S"])
        self.assertEqual(m["B00FM03XCU"], ["B006CNTR6W", "B00U1NFVZ0"])
        self.assertEqual(m["B081TMDLXF"], ["B0FL1VS9SH"])
        self.assertIn("B0F5HZR1KB", a)
        self.assertIn("B0CJ97Z6TB", a)
        self.assertNotIn("B081LLCJTC", a)

    def test_bad_shape(self):
        rows = copy.deepcopy(load("dataset_apt_marble_dw60.json"))
        del rows[5]["position"]
        with self.assertRaises(ValueError):
            sc.select_candidates(rows, ["death wish coffee"])

    def test_black_rifle_and_jinx(self):
        rows = load("dataset_apt_marble_3x10.json")
        c, m = sc.select_candidates([r for r in rows if r["keyword"] == "black rifle coffee"], ["black rifle coffee"])
        self.assertEqual(len(c), 9)
        self.assertEqual(m["B01M8OD0LQ"], ["B01MQ62LR0"])
        c, _ = sc.select_candidates([r for r in rows if r["keyword"] == "jinx dog food"], ["jinx"])
        self.assertEqual(asins(c), ["B0F5LZXCDH", "B0F5LRDP8G", "B0GGL6L1HX"])

    def test_living_proof(self):
        c, m = sc.select_candidates(load("dataset_apt_marble_living_proof_20.json"), ["living proof"])
        self.assertEqual(len(c), 17)
        self.assertEqual(m["B0BQ3YFRC5"], ["B0170GOCVO"])


class Top(unittest.TestCase):
    def setUp(self):
        self.items = {i["asin"]: i for i in load("dataset_junglee_3asins.json")}

    def test_distinct(self):
        d = {a: self.items[a] for a in ("B006CQ1ZHI", "B08VFVSBXM")}
        sel, m = sc.select_top(list(d), d, 10)
        self.assertEqual(sel, ["B006CQ1ZHI", "B08VFVSBXM"])

    def test_merge(self):
        twin = {**self.items["B006CQ1ZHI"], "asin": "B00TXTNL2S"}
        d = {"B006CQ1ZHI": self.items["B006CQ1ZHI"], "B08VFVSBXM": self.items["B08VFVSBXM"], "B00TXTNL2S": twin}
        sel, m = sc.select_top(list(d), d, 10)
        self.assertEqual(sel, ["B006CQ1ZHI", "B08VFVSBXM"])
        self.assertEqual(m["B006CQ1ZHI"], ["B00TXTNL2S"])

    def test_failed_detail(self):
        sel, _ = sc.select_top(["B00OQKOO02"], {"B00OQKOO02": None}, 10)
        self.assertEqual(sel, ["B00OQKOO02"])


class Reviews(unittest.TestCase):
    def test_two_asins(self):
        g = sc.group_reviews(load("dataset_2asins_5each.json"), ["B006CQ1ZHI", "B00OQKOO02"], 5)
        self.assertTrue(all(len(v) == 5 for v in g.values()))
        self.assertEqual(g["B006CQ1ZHI"][0][0]["ReviewId"], "R33VC4QUNQ77MM")
        for v in g.values():
            for row, _ in v:
                self.assertIsNone(row["Reviewer"])
                self.assertIsNone(row["Images"])

    def test_too_many(self):
        with self.assertRaises(ValueError):
            sc.group_reviews(load("dataset_B00OQKOO02_20.json"), ["B00OQKOO02"], 10)

    def test_image_count(self):
        rows = load("dataset_B00OQKOO02_20.json")
        g = sc.group_reviews(rows, ["B00OQKOO02"], 20)["B00OQKOO02"]
        self.assertEqual(len(g), 20)
        for row, n in g:
            self.assertEqual(n, 1 if row["ReviewId"] == "R2LUGCESGD69T4" else 0)


if __name__ == "__main__":
    unittest.main()
