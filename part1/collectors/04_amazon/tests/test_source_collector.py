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


class Settling(unittest.TestCase):
    NOW = 1_800_000_000.0

    def fin(self, ago):
        t = self.NOW - ago
        return __import__("datetime").datetime.fromtimestamp(t, __import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    def setUp(self):
        from unittest import mock
        self.sleeps, self.gets = [], {}
        self.last = {"r1": 0.01, "r2": 0.02, "r3": 0.03}
        self.settled = {"r1": 0.06, "r2": 0.075, "r3": 0.63}
        self.ago = {"r1": 50, "r2": 30, "r3": 10}
        self.status = {"r1": "SUCCEEDED", "r2": "SUCCEEDED", "r3": "SUCCEEDED"}
        self.fail_settle = set()
        self.posts = []
        for p in (mock.patch.object(sc.time, "sleep", self.sleeps.append),
                  mock.patch.object(sc.time, "time", lambda: self.NOW),
                  mock.patch.object(sc, "call", self.fake_call)):
            p.start()
            self.addCleanup(p.stop)

    def fake_call(self, st, method, url, token, body=None):
        st["requests"] += 1
        if method == "POST":
            self.posts.append(url)
            rid = "r%d" % len(self.posts)
            return {"data": {"id": rid}}
        if "/datasets/" in url:
            return []
        rid = url.rsplit("/", 1)[1]
        n = self.gets[rid] = self.gets.get(rid, 0) + 1
        if n == 1:
            return {"data": {"id": rid, "status": self.status[rid], "usageTotalUsd": self.last[rid],
                             "finishedAt": self.fin(self.ago[rid]), "defaultDatasetId": "d"}}
        if rid in self.fail_settle:
            raise sc.Fail("http_500")
        return {"data": {"usageTotalUsd": self.settled[rid]}}

    def st(self):
        return {"requests": 0, "cost": 0.0, "runs": [], "extra": {}}

    def run_three(self, st):
        return [sc.run_actor(st, "t", sc.SEARCH, {}) for _ in range(3)]

    def test_poll_interval(self):
        self.assertEqual(sc.POLL_S, 3)

    def test_settled_once_after_last_run(self):
        st = self.st()
        self.run_three(st)
        self.assertEqual(self.gets, {"r1": 1, "r2": 1, "r3": 1})
        self.assertEqual([s for s in self.sleeps if s > sc.POLL_S], [])
        sc.settle(st, "t")
        self.assertEqual(self.gets, {"r1": 2, "r2": 2, "r3": 2})
        self.assertAlmostEqual(st["cost"], 0.765)
        self.assertEqual([s for s in self.sleeps if s > sc.POLL_S], [sc.CHARGE_READ_DELAY_S - 10])

    def test_failed_second_run_still_settled_via_run_brand(self):
        from unittest import mock
        import tempfile
        self.status["r2"] = "FAILED"

        def fake_collect(st, cfg, token, emit):
            for _ in range(3):
                err, _, _ = sc.run_actor(st, token, sc.SEARCH, {})
                if err:
                    return "could_not_look", "search_" + err
            return "ok", ""
        with tempfile.TemporaryDirectory() as d, mock.patch.object(sc, "HERE", Path(d)), \
                mock.patch.object(sc, "collect", fake_collect):
            sc.run_brand("x", {}, "t")
            res = json.loads(next(Path(d).glob("raw/x/*.run.json")).read_text())
        self.assertEqual(self.gets, {"r1": 2, "r2": 2})
        self.assertAlmostEqual(res["cost_usd"], 0.135)

    def test_exception_in_collect_still_settles(self):
        from unittest import mock
        import tempfile

        def boom(st, cfg, token, emit):
            sc.run_actor(st, token, sc.SEARCH, {})
            raise RuntimeError("x")
        with tempfile.TemporaryDirectory() as d, mock.patch.object(sc, "HERE", Path(d)), \
                mock.patch.object(sc, "collect", boom):
            sc.run_brand("x", {}, "t")
            res = json.loads(next(Path(d).glob("raw/x/*.run.json")).read_text())
        self.assertAlmostEqual(res["cost_usd"], 0.06)

    def test_failed_settle_read_keeps_last_seen(self):
        self.fail_settle = {"r2"}
        st = self.st()
        self.run_three(st)
        sc.settle(st, "t")
        self.assertAlmostEqual(st["cost"], 0.06 + 0.02 + 0.63)

    def test_unended_run_not_read_and_no_wait(self):
        self.status["r1"] = "RUNNING"
        st = self.st()
        with __import__("unittest").mock.patch.object(sc, "RUN_TIMEOUT_S", -sc.WAIT_MARGIN_S - 1):
            sc.run_actor(st, "t", sc.SEARCH, {})
        n = len(self.sleeps)
        sc.settle(st, "t")
        self.assertEqual(self.gets, {"r1": 1})
        self.assertEqual(len(self.sleeps), n)
        self.assertAlmostEqual(st["cost"], 0.01)

    def test_null_settled_cost_is_skipped(self):
        self.settled["r2"] = None
        st = self.st()
        runs = self.run_three(st)
        before = st["cost"]
        sc.settle(st, "t")
        self.assertAlmostEqual(st["cost"], before - 0.01 - 0.03 + 0.06 + 0.63)
        self.assertEqual([r["cost"] for r in st["runs"]], [0.06, 0.02, 0.63])


if __name__ == "__main__":
    unittest.main()
