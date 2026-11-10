import contextlib
import io
import os
from unittest import mock

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
            return self.capture(lambda: main(["--collectors-dir", str(self.dir)], mappers={"fake": support.FAKE}))

    def test_lines_summary_and_second_run(self):
        self.write_run("fake", "b", T1, records=[rec("a"), rec("b")])
        self.write_run("nomap", "b", T1, records=[rec("a")])
        code, text = self.cli()
        self.assertEqual(code, 0)
        self.assertEqual(text.splitlines(), [
            "fake b 20261110T100000Z ok applied inserted=2 updated=0 ended=0 not_fetched=0",
            "nomap b 20261110T100000Z ok no_mapper inserted=0 updated=0 ended=0 not_fetched=0",
            "runs: applied=1 superseded=0 empty_no_mapper=0 failed=0 already_loaded=0 no_mapper=nomap"])
        code, text = self.cli()
        self.assertEqual(text.splitlines(), [
            "nomap b 20261110T100000Z ok no_mapper inserted=0 updated=0 ended=0 not_fetched=0",
            "runs: applied=0 superseded=0 empty_no_mapper=0 failed=0 already_loaded=1 no_mapper=nomap"])

    def test_failed_run_returns_1(self):
        self.write_run("fake", "b", T1, records=[rec("x", bad=True)])
        code, text = self.cli()
        self.assertEqual(code, 1)
        self.assertIn("fake b 20261110T100000Z ok failed inserted=0 updated=0 ended=0 not_fetched=0 error=x", text)

    def test_unreachable_database_returns_1(self):
        with mock.patch.dict(os.environ, {"DATABASE_URL": "postgresql://u:secret@localhost:1/nope"}):
            code, text = self.capture(lambda: main(["--collectors-dir", str(self.dir)]))
        self.assertEqual(code, 1)
        self.assertIn("cannot connect to postgresql://u@localhost:1/nope", text)
        self.assertNotIn("secret", text); self.assertNotIn("Traceback", text)
