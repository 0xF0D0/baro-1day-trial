import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import source_collector as sc

SAMPLES = Path(__file__).resolve().parents[3] / "collectors/02_tiktok_ad_library/samples"
INPUTS = json.loads((Path(__file__).resolve().parents[1] / "brand_inputs.json").read_text())
LP, JINX_A, JINX_B = "7531018269878140936", "7619486503161118737", "7609180755211075600"


def load(name):
    return json.loads((SAMPLES / name).read_text())


class ParseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = load("apify_fetchcat_dataset.json")["response"]

    def by_brand(self):
        out = {}
        for slug, cfg in INPUTS.items():
            out[slug] = [r for r in self.rows if r["keyword"] in cfg["keywords"]]
        return out

    def row(self, ad_id):
        return next(r for r in self.rows if r["adId"] == ad_id)

    def test_check_rows_passes(self):
        sc.check_rows(self.rows)

    def test_check_rows_missing_key(self):
        rows = copy.deepcopy(self.rows)
        del rows[0]["videoUrl"]
        with self.assertRaises(ValueError):
            sc.check_rows(rows)

    def test_group_by_brand(self):
        counts = {k: len(v) for k, v in self.by_brand().items()}
        self.assertEqual(counts, {"batiste": 0, "living-proof": 18, "death-wish-coffee": 224,
                                  "black-rifle-coffee": 49, "jinx": 5})

    def test_find_match_terms(self):
        for slug, rows in self.by_brand().items():
            found = {r["adId"]: sc.find_match_terms(r, INPUTS[slug]["match_terms"]) for r in rows}
            found = {k: v for k, v in found.items() if v}
            if slug == "living-proof":
                self.assertEqual(found, {LP: ["living proof", "livingproof"]})
            elif slug == "jinx":
                self.assertEqual(found, {JINX_A: ["@jinx", "#jinxpartner"], JINX_B: ["@jinx", "#jinxpartner"]})
            else:
                self.assertEqual(found, {})

    def test_remove_mentions(self):
        cfg = INPUTS["living-proof"]
        out = sc.remove_personal_data(self.row(LP), cfg["match_terms"], cfg["kept_mentions"])
        self.assertTrue(out["adText"].endswith("Inspo: @<removed>  #livingproofinc #coffeetray #summeressentials #hairtok"))
        self.assertEqual(out["brandName"], "Living Proof")

    def test_remove_person_brand_name(self):
        cfg = INPUTS["living-proof"]
        row = dict(self.row(LP), brandName="Some Person")
        self.assertEqual(sc.find_match_terms(row, cfg["match_terms"]), ["livingproof"])
        self.assertIsNone(sc.remove_personal_data(row, cfg["match_terms"], [])["brandName"])
        self.assertEqual(row["brandName"], "Some Person")

    def test_kept_mention(self):
        cfg = INPUTS["jinx"]
        row = self.row(JINX_B)
        out = sc.remove_personal_data(row, cfg["match_terms"], cfg["kept_mentions"])
        self.assertEqual(out["adText"], row["adText"])

    def test_cost_settled_run(self):
        run = load("apify_fetchcat_run_settled.json")["response"]
        self.assertEqual(sc.cost_usd(run, 296), 0.06578952)

    def test_cost_jinx_run(self):
        sample = load("apify_fetchcat_jinx_verify_run.json")
        self.assertEqual(sc.cost_usd(sample["run_final"], 5), sample["usage_reads"][-1]["usageTotalUsd"])


if __name__ == "__main__":
    unittest.main()
