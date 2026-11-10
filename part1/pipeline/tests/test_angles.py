import contextlib
import hashlib
import io
import json
import os
from unittest import mock

import support
from support import DbTestCase

import angles


class AnglesTest(DbTestCase):
    def ad(self, key, headline, body, brand="b", channel="meta"):
        self.conn.execute(
            "INSERT INTO ads (source, brand, kind, key, scope, fetched_at, first_seen_at, last_seen_at, last_run_id, raw, "
            "channel, headline, body) VALUES ('fake', %s, 'ad', %s, 'all', now(), now(), now(), 'r', '{}', %s, %s, %s)",
            (brand, key, channel, headline, body))
        self.conn.commit()

    def line(self, text, **over):
        base = {"text_sha256": angles.text_hash(text), "list_version": 1, "labeled_by": "test",
                "labeled_at": "2026-11-11T00:00:00Z", "angle_offer": "none", "offer_evidence": None,
                "angle_message": "none", "message_evidence": None, "angle_voice": "brand", "voice_evidence": None}
        return {**base, **over}

    def write_labels(self, lines):
        self.labels = self.dir / "labels.jsonl"
        self.labels.write_text("".join(json.dumps(x) + "\n" for x in lines))

    def write_raw(self, lines):
        self.labels = self.dir / "labels.jsonl"
        self.labels.write_text("\n".join(lines) + "\n")

    def test_ad_text_and_hash(self):
        self.assertEqual(angles.ad_text("  Save   20%\n", " Bundled for\tthe busy "), "Save 20%\nBundled for the busy")
        self.assertEqual(angles.ad_text(None, "x"), "\nx")
        self.assertEqual(angles.ad_text(" ", None), "")
        self.assertEqual(angles.text_hash("a"), hashlib.sha256(b"a").hexdigest())

    def test_check_label_reasons(self):
        good = self.line("Save 20%\nfor the busy", angle_offer="discount", offer_evidence="Save 20%")
        self.assertIsNone(angles.check_label(good))
        for change, reason in [({"angle_offer": "sale"}, "angle_offer not in list"),
                               ({"offer_evidence": None}, "offer_evidence missing"),
                               ({"angle_offer": "none"}, "offer_evidence not expected"),
                               ({"offer_evidence": "ask @someone"}, "offer_evidence has a handle"),
                               ({"offer_evidence": " ".join(["w"] * 13)}, "offer_evidence longer than 12 words"),
                               ({"voice_evidence": "x"}, "voice_evidence not expected"),
                               ({"list_version": 2}, "list_version is not 1"),
                               ({"text_sha256": "ABC"}, "text_sha256 is not 64 lower-case hex"),
                               ({"angle_message": "brand", "message_evidence": ""}, "message_evidence missing"),
                               ({"angle_voice": "creator"}, "voice_evidence missing"),
                               ({"angle_voice": "robot"}, "angle_voice not in list")]:
            self.assertEqual(angles.check_label({**good, **change}), reason, change)
        missing = dict(good); del missing["labeled_by"]
        self.assertEqual(angles.check_label(missing), "labeled_by missing")

    def test_check_evidence(self):
        text = "Save 20%\nfor the busy"
        self.assertIsNone(angles.check_evidence(self.line(text, angle_offer="discount", offer_evidence="Save  20%"), text))
        self.assertEqual(angles.check_evidence(self.line(text, angle_offer="discount", offer_evidence="Half price"), text),
                         "offer_evidence not in the ad text")

    def test_apply_counts_and_rows(self):
        self.ad("1", "Save 20%", "for the busy"); self.ad("2", "Save 20%", "for the busy")
        self.ad("3", "Other", "words"); self.ad("4", None, " ")
        self.write_labels([self.line("Save 20%\nfor the busy", angle_offer="discount", offer_evidence="Save 20%",
                                     angle_message="convenience", message_evidence="for the busy")])
        self.assertEqual(angles.apply_labels(self.conn, self.labels), (2, 1, 1))
        rows = self.table("ad_angles")
        self.assertEqual([(r["key"], r["angle_offer"], r["offer_evidence"], r["angle_message"], r["angle_voice"],
                           r["voice_evidence"]) for r in rows],
                         [("1", "discount", "Save 20%", "convenience", "brand", None),
                          ("2", "discount", "Save 20%", "convenience", "brand", None)])
        self.assertEqual(angles.apply_labels(self.conn, self.labels), (2, 1, 1))
        self.assertEqual(len(self.table("ad_angles")), 2)

    def test_apply_rejects_evidence_that_is_not_in_the_text(self):
        self.ad("1", "Save 20%", "for the busy")
        self.write_labels([self.line("Save 20%\nfor the busy", angle_offer="discount", offer_evidence="Half price")])
        with self.assertRaises(angles.LabelError) as e:
            angles.apply_labels(self.conn, self.labels)
        self.assertEqual(str(e.exception), "line 1: offer_evidence not in the ad text")

    def test_failed_apply_leaves_rows_as_they_were(self):
        self.ad("1", "A", "b")
        self.write_labels([self.line("A\nb")])
        angles.apply_labels(self.conn, self.labels); self.conn.commit()
        self.write_labels([self.line("A\nb", angle_offer="sale")])
        with self.assertRaises(angles.LabelError):
            angles.apply_labels(self.conn, self.labels)
        self.conn.rollback()
        self.assertEqual(len(self.table("ad_angles")), 1)

    def test_read_labels_names_the_line(self):
        good = json.dumps(self.line("one"))
        bad = json.dumps(self.line("two", angle_offer="sale"))
        for lines, n, reason in [([good, "not json"], 2, "not JSON"),
                                 ([good, good], 2, "duplicate text_sha256"),
                                 ([good, good.replace('"test"', '"x"'), bad], 2, "duplicate text_sha256"),
                                 ([good, bad], 2, "angle_offer not in list"),
                                 ([good, "[1]"], 2, "not a JSON object")]:
            self.write_raw(lines)
            with self.assertRaises(angles.LabelError) as e:
                angles.read_labels(self.labels)
            self.assertEqual(e.exception.line, n)
            self.assertEqual(str(e.exception), f"line {n}: {reason}")
        self.write_raw([good, "", bad.replace("sale", "discount")])
        with self.assertRaises(angles.LabelError) as e:
            angles.read_labels(self.labels)
        self.assertTrue(str(e.exception).startswith("line 3: "))

    def test_unknown_hash_and_missing_file_are_fine(self):
        self.ad("1", "A", "b")
        self.write_labels([self.line("no such ad\nat all")])
        self.assertEqual(angles.apply_labels(self.conn, self.labels), (0, 1, 0))
        self.assertEqual(angles.apply_labels(self.conn, self.dir / "none.jsonl"), (0, 1, 0))
        self.assertEqual(angles.read_labels(self.dir / "none.jsonl"), {})

    def test_pending(self):
        self.ad("1", "Save 20%", "x", brand="b1", channel="meta"); self.ad("2", "Save 20%", "x", brand="b2", channel="site")
        self.ad("3", "Solo", "y"); self.ad("4", None, None); self.ad("5", "Done", "z")
        self.write_labels([self.line("Done\nz")])
        self.assertEqual(angles.pending(self.conn, self.labels), [
            {"text_sha256": angles.text_hash("Save 20%\nx"), "text": "Save 20%\nx", "brands": ["b1", "b2"],
             "channels": ["meta", "site"], "kinds": ["ad"], "ads": 2},
            {"text_sha256": angles.text_hash("Solo\ny"), "text": "Solo\ny", "brands": ["b"], "channels": ["meta"],
             "kinds": ["ad"], "ads": 1}])

    def test_main_pending_prints_json_lines(self):
        self.ad("3", "Solo", "y")
        self.write_labels([])
        buffer = io.StringIO()
        with mock.patch.dict(os.environ, {"DATABASE_URL": self.url}), contextlib.redirect_stdout(buffer):
            code = angles.main(["--pending", "--labels", str(self.labels)])
        self.assertEqual(code, 0)
        out = [json.loads(x) for x in buffer.getvalue().splitlines()]
        self.assertEqual(out, [{"text_sha256": angles.text_hash("Solo\ny"), "text": "Solo\ny", "brands": ["b"],
                                "channels": ["meta"], "kinds": ["ad"], "ads": 1}])

    def test_committed_labels_file_is_valid(self):
        angles.read_labels(angles.LABELS_FILE)


if __name__ == "__main__":
    import unittest
    unittest.main()
