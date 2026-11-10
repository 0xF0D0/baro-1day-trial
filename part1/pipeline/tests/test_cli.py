import contextlib
import io
import json
import os
from unittest import mock

import angles
import support
from support import DbTestCase, rec

from load import main

T1 = "20261110T100000Z"


class CliTest(DbTestCase):
    def capture(self, fn):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            code = fn()
        return code, buffer.getvalue()

    def cli(self):
        with mock.patch.dict(os.environ, {"DATABASE_URL": self.url}):
            return self.capture(lambda: main(["--collectors-dir", str(self.dir), "--labels", str(self.dir / "labels.jsonl")], mappers={"fake": support.FAKE}))

    def test_lines_summary_and_second_run(self):
        self.write_run("fake", "b", T1, records=[rec("a"), rec("b")])
        self.write_run("nomap", "b", T1, records=[rec("a")])
        code, text = self.cli()
        self.assertEqual(code, 0)
        self.assertEqual(text.splitlines(), [
            "fake b 20261110T100000Z ok applied inserted=2 updated=0 ended=0 not_fetched=0",
            "nomap b 20261110T100000Z ok no_mapper inserted=0 updated=0 ended=0 not_fetched=0",
            "angles: labeled=0 not_labeled=0 no_text=0",
            "runs: applied=1 superseded=0 empty_no_mapper=0 failed=0 already_loaded=0 no_mapper=nomap"])
        code, text = self.cli()
        self.assertEqual(text.splitlines(), [
            "nomap b 20261110T100000Z ok no_mapper inserted=0 updated=0 ended=0 not_fetched=0",
            "angles: labeled=0 not_labeled=0 no_text=0",
            "runs: applied=0 superseded=0 empty_no_mapper=0 failed=0 already_loaded=1 no_mapper=nomap"])

    def test_failed_run_returns_1(self):
        self.write_run("fake", "b", T1, records=[rec("x", bad=True)])
        code, text = self.cli()
        self.assertEqual(code, 1)
        self.assertIn("fake b 20261110T100000Z ok failed inserted=0 updated=0 ended=0 not_fetched=0 error=x", text)
        self.assertIn("angles: labeled=0 not_labeled=0 no_text=0\nruns:", text)

    def test_invalid_labels_keep_the_runs_and_return_1(self):
        self.write_run("fake", "b", T1, records=[rec("x", kind="ad", table="ads",
                                                     columns={"channel": "meta", "headline": "H", "body": "B"})])
        bad = {"text_sha256": angles.text_hash("H\nB"), "list_version": 1, "labeled_by": "t",
               "labeled_at": "2026-11-11T00:00:00Z", "angle_offer": "sale", "offer_evidence": None,
               "angle_message": "none", "message_evidence": None, "angle_voice": "brand", "voice_evidence": None}
        (self.dir / "labels.jsonl").write_text(json.dumps(bad) + "\n")
        code, text = self.cli()
        self.assertEqual(code, 1)
        lines = text.splitlines()
        self.assertEqual(lines[-2], "angles: failed: line 1: angle_offer not in list")
        self.assertTrue(lines[-1].startswith("runs: applied=1"))
        self.assertEqual(len(self._query("SELECT 1 FROM ads")), 1)

    def test_unreachable_database_returns_1(self):
        with mock.patch.dict(os.environ, {"DATABASE_URL": "postgresql://u:secret@localhost:1/nope"}):
            code, text = self.capture(lambda: main(["--collectors-dir", str(self.dir)]))
        self.assertEqual(code, 1)
        self.assertIn("cannot connect to postgresql://u@localhost:1/nope", text)
        self.assertNotIn("secret", text); self.assertNotIn("Traceback", text)
