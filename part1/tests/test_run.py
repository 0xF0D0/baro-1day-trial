import contextlib
import fcntl
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run  # noqa: E402
from run import Job  # noqa: E402

STUB = r'''
import json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path
here = Path(__file__).resolve().parent
cfg = json.loads((here / "stub.json").read_text())
args = sys.argv[1:]
brands = [b["slug"] for b in json.loads((here.parent / "brands.json").read_text())]
todo = brands if args == ["--all"] else [args[1]]
(here / "calls.log").open("a").write(" ".join(args) + "\n")
(here / "env.log").open("a").write(os.environ.get("RADAR_CAREFUL", "") + "\n")
if cfg.get("spawn_child"):
    import subprocess
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    (here / "child.pid").write_text(str(child.pid))
(here / ("started." + "-".join(args))).write_text(str(time.time()))
time.sleep(cfg.get("sleep", 0))
for b in todo:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    d = here / "raw" / b; d.mkdir(parents=True, exist_ok=True)
    (d / (run_id + ".run.json")).write_text(json.dumps({"run_id": run_id, "status": cfg.get("status", "ok"), "cost_usd": cfg.get("cost", 0)}))
print("stub done", flush=True)
(here / ("ended." + "-".join(args))).write_text(str(time.time()))
sys.exit(cfg.get("exit", 0))
'''

LOAD_STUB = r'''
import json, os, sys
from pathlib import Path
here = Path(__file__).resolve().parent
cfg = json.loads((here / "cmds.json").read_text())
(here / "env.log").open("a").write(os.environ.get("RADAR_CAREFUL", "") + "\n")
(here / "load.calls").open("a").write(json.dumps(sys.argv[1:]) + "\n")
sys.exit(cfg["load_exit"])
'''

LABEL_STUB = r'''
import json, os, sys
from pathlib import Path
here = Path(__file__).resolve().parent
cfg = json.loads((here / "cmds.json").read_text())
(here / "env.log").open("a").write(os.environ.get("RADAR_CAREFUL", "") + "\n")
(here / "label.calls").open("a").write("called\n")
if cfg["label_appends"]:
    Path(cfg["labels_file"]).open("a").write("{}\n")
sys.exit(cfg["label_exit"])
'''

SLOW_LOAD_STUB = r'''
import os, sys, time
from pathlib import Path
here = Path(__file__).resolve().parent
(here / "load.pid").write_text(str(os.getpid()))
(here / "load.started").write_text("1")
time.sleep(60)
'''

DRIVER = r'''
import sys
from pathlib import Path
tmp = Path(sys.argv[1])
sys.path.insert(0, sys.argv[2])
import run
sys.exit(run.main(["--collectors-dir", str(tmp / "collectors")],
                  load_cmd=[sys.executable, str(tmp / "load_stub.py")],
                  label_cmd=[sys.executable, str(tmp / "label_stub.py")],
                  labels_file=tmp / "ad_angles.jsonl", state_dir=tmp / "state"))
'''


class RunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="run-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cdir = self.tmp / "collectors"
        self.state = self.tmp / "state"
        self.labels = self.tmp / "ad_angles.jsonl"
        (self.tmp / "load_stub.py").write_text(LOAD_STUB)
        (self.tmp / "label_stub.py").write_text(LABEL_STUB)
        self.cmds = {"load_exit": 0, "label_exit": 0, "label_appends": False,
                     "labels_file": str(self.labels)}

    def make(self, folders, brands=("x", "y")):
        self.cdir.mkdir(exist_ok=True)
        (self.cdir / "brands.json").write_text(json.dumps([{"slug": b, "name": b} for b in brands]))
        for name, cfg in folders.items():
            d = self.cdir / name
            d.mkdir(exist_ok=True)
            (d / "source_collector.py").write_text(STUB)
            (d / "stub.json").write_text(json.dumps(cfg))
        return self.cdir

    def run_pass(self, *argv):
        (self.tmp / "cmds.json").write_text(json.dumps(self.cmds))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = run.main(
                [*argv, "--collectors-dir", str(self.cdir)],
                load_cmd=[sys.executable, str(self.tmp / "load_stub.py")],
                label_cmd=[sys.executable, str(self.tmp / "label_stub.py")],
                labels_file=self.labels, state_dir=self.state)
        return code, buf.getvalue().splitlines()

    def calls(self, folder):
        p = self.cdir / folder / "calls.log"
        return p.read_text().splitlines() if p.exists() else None

    def load_calls(self):
        p = self.tmp / "load.calls"
        return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []

    def three(self, **over):
        cfgs = {"01_a": {}, "04_amazon": {}, "05_b": {}}
        for k, v in over.items():
            cfgs[k].update(v)
        return self.make(cfgs)

    def test_plan_jobs(self):
        self.assertEqual(run.BRAND_SEQUENTIAL, ("01_google_ads_transparency", "07_search_interest"))
        self.assertEqual(run.plan_jobs(["01_google_ads_transparency", "03_x"], ["a", "b"], None),
                         [Job("01_google_ads_transparency", None), Job("03_x", "a"), Job("03_x", "b")])
        folders = ["01_a", "04_amazon", "07_search_interest"]
        self.assertEqual(run.plan_jobs(folders, ["x", "y"], None),
                         [Job("01_a", "x"), Job("01_a", "y"), Job("04_amazon", "x"), Job("04_amazon", "y"),
                          Job("07_search_interest", None)])
        self.assertEqual(run.plan_jobs(folders, ["x", "y"], None, careful=True),
                         [Job("01_a", None), Job("04_amazon", "x"), Job("04_amazon", "y"),
                          Job("07_search_interest", None)])
        for careful in (False, True):
            self.assertEqual(run.plan_jobs(folders, ["x", "y"], "y", careful=careful),
                             [Job("01_a", "y"), Job("04_amazon", "y"), Job("07_search_interest", "y")])

    def env_log(self, folder):
        return (self.cdir / folder / "env.log").read_text().splitlines()

    def test_careful_pass(self):
        self.make({"01_a": {}, "04_amazon": {}})
        with unittest.mock.patch.dict(os.environ):
            os.environ.pop("RADAR_CAREFUL", None)
            code, _ = self.run_pass("--careful")
            self.assertEqual(code, 0)
            self.assertEqual(self.calls("01_a"), ["--all"])
            self.assertEqual(sorted(self.calls("04_amazon")), ["--brand x", "--brand y"])
            self.assertEqual(self.env_log("01_a"), ["1"])
            self.assertEqual(self.env_log("04_amazon"), ["1", "1"])
            # load runs once, label once (labels file unchanged): neither got the variable
            self.assertEqual((self.tmp / "env.log").read_text().splitlines(), ["", ""])
            for f in (self.cdir / "01_a" / "calls.log", self.cdir / "01_a" / "env.log",
                      self.cdir / "04_amazon" / "calls.log", self.cdir / "04_amazon" / "env.log",
                      self.tmp / "env.log"):
                f.unlink()
            shutil.rmtree(self.cdir / "01_a" / "raw")
            shutil.rmtree(self.cdir / "04_amazon" / "raw")
            code, _ = self.run_pass()
            self.assertEqual(code, 0)
            self.assertEqual(sorted(self.calls("01_a")), ["--brand x", "--brand y"])
            self.assertEqual(self.env_log("01_a"), ["", ""])
            self.assertEqual(self.env_log("04_amazon"), ["", ""])

    def test_default_jobs_is_16(self):
        self.three()
        seen = []

        def fake(jobs, cdir, log_dir, max_jobs, *a, **kw):
            seen.append(max_jobs)
            return {}
        with unittest.mock.patch.object(run, "run_jobs", fake):
            self.run_pass()
            self.run_pass("--jobs", "3")
        self.assertEqual(seen, [16, 3])

    def test_select_sources(self):
        folders = ["01_a", "04_amazon", "10_b"]
        self.assertEqual(run.select_sources(folders, None), folders)
        self.assertEqual(run.select_sources(folders, "10, 1"), ["01_a", "10_b"])
        self.assertEqual(run.select_sources(folders, "04_amazon,4"), ["04_amazon"])
        with self.assertRaises(ValueError) as e:
            run.select_sources(folders, "1,7")
        self.assertEqual(str(e.exception), "unknown source: 7")

    def test_folders_and_brands(self):
        self.make({"05_b": {}, "01_a": {}})
        (self.cdir / "99_nocode").mkdir()
        self.assertEqual(run.collector_folders(self.cdir), ["01_a", "05_b"])
        self.assertEqual(run.read_brands(self.cdir), ["x", "y"])

    def test_whole_pass(self):
        self.three(**{"01_a": {"cost": 0}, "04_amazon": {"status": "partial", "cost": 0.05},
                      "05_b": {"status": "could_not_look", "exit": 1}})
        old = self.cdir / "01_a" / "raw" / "x"
        old.mkdir(parents=True)
        (old / "20200101T000000Z.run.json").write_text(
            json.dumps({"run_id": "20200101T000000Z", "status": "ok", "cost_usd": 9}))
        code, lines = self.run_pass()
        self.assertEqual(code, 1)
        self.assertEqual(sorted(l.rsplit(" ", 1)[0] for l in lines if l.startswith("collect ") and "exit=" in l),
                         ["collect 01_a x exit=0", "collect 01_a y exit=0", "collect 04_amazon x exit=0",
                          "collect 04_amazon y exit=0", "collect 05_b x exit=1", "collect 05_b y exit=1"])
        for l in lines:
            if "exit=" in l:
                self.assertRegex(l, r" \d+s$")
        # 3 folders x 2 brands = 6 jobs; 05_b fails for both brands so failed=2; each job writes one run
        # file (the 2020 file is older than the start) so runs=6: 01_a ok x2, 04_amazon partial x2,
        # 05_b could_not_look x2; cost = 2 x 0.05 from 04_amazon
        self.assertIn("collect: jobs=6 failed=2 runs=6 ok=2 partial=2 could_not_look=2 cost_usd=0.1000", lines)
        self.assertEqual(self.load_calls(), [["--collectors-dir", str(self.cdir)]])
        self.assertEqual((self.tmp / "label.calls").read_text().splitlines(), ["called"])
        self.assertEqual(sorted(self.calls("01_a")), ["--brand x", "--brand y"])
        self.assertEqual(sorted(self.calls("04_amazon")), ["--brand x", "--brand y"])
        stamps = list((self.state / "logs").iterdir())
        self.assertEqual(len(stamps), 1)
        self.assertRegex(stamps[0].name, r"^\d{8}T\d{6}Z$")
        for name in ("01_a.x.log", "01_a.y.log", "04_amazon.x.log", "04_amazon.y.log", "05_b.x.log", "05_b.y.log"):
            self.assertIn("stub done", (stamps[0] / name).read_text())

    def test_labels_change_triggers_a_second_load(self):
        self.three()
        self.cmds["label_appends"] = True
        code, _ = self.run_pass()
        self.assertEqual(code, 0)
        self.assertEqual(len(self.load_calls()), 2)
        self.assertEqual((self.tmp / "label.calls").read_text().splitlines(), ["called"])

    def test_no_label(self):
        self.three()
        code, _ = self.run_pass("--no-label")
        self.assertEqual(code, 0)
        self.assertFalse((self.tmp / "label.calls").exists())
        self.assertEqual(len(self.load_calls()), 1)

    def test_exit_codes(self):
        self.three()
        self.cmds["label_exit"] = 1
        self.assertEqual(self.run_pass()[0], 0)
        self.cmds.update(label_exit=0, load_exit=1)
        self.assertEqual(self.run_pass()[0], 1)
        self.cmds["load_exit"] = 0
        self.three(**{"05_b": {"exit": 1}})
        self.assertEqual(self.run_pass()[0], 1)

    def test_brand_and_sources(self):
        self.three()
        code, lines = self.run_pass("--brand", "y", "--sources", "1,4")
        self.assertEqual(code, 0)
        self.assertEqual(self.calls("01_a"), ["--brand y"])
        self.assertEqual(self.calls("04_amazon"), ["--brand y"])
        self.assertIsNone(self.calls("05_b"))
        self.assertIn("collect: jobs=2 failed=0 runs=2 ok=2 partial=0 could_not_look=0 cost_usd=0.0000", lines)

    def test_wrong_arguments_stop_before_anything_runs(self):
        self.three()
        code, lines = self.run_pass("--brand", "zzz")
        self.assertEqual(code, 2)
        self.assertIn("unknown brand: zzz", lines)
        code, lines = self.run_pass("--sources", "7")
        self.assertEqual(code, 2)
        self.assertIn("unknown source: 7", lines)
        for f in ("01_a", "04_amazon", "05_b"):
            self.assertIsNone(self.calls(f))
        self.assertEqual(self.load_calls(), [])
        self.assertFalse((self.state / "logs").exists())

    def test_timeout_stops_the_job_and_its_children(self):
        self.make({"01_a": {"sleep": 60, "spawn_child": True}, "05_b": {}})
        t0 = time.time()
        code, lines = self.run_pass("--timeout", "0.05", "--careful")
        self.assertLess(time.time() - t0, 20)
        self.assertEqual(code, 1)
        self.assertTrue(any(l.startswith("collect 01_a all exit=timeout ") for l in lines), lines)
        self.assertTrue(any(l.startswith("collect 05_b all exit=0 ") for l in lines), lines)
        pidfile = self.cdir / "01_a" / "child.pid"
        self.assertTrue(pidfile.exists())
        pid = int(pidfile.read_text())
        self.addCleanup(lambda: self._kill(pid))
        deadline = time.time() + 15
        gone = False
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                gone = True
                break
            time.sleep(0.1)
        self.assertTrue(gone, "child of the timed-out job is still alive")
        self.assertEqual(len(self.load_calls()), 1)

    @staticmethod
    def _kill(pid):
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass

    def test_jobs_limit(self):
        names = ["01_a", "02_b", "03_c", "05_d"]
        self.make({n: {"sleep": 0.8} for n in names})
        jobs = [Job(n, None) for n in names]

        def timed(limit):
            for f in self.cdir.glob("*/started.*"):
                f.unlink()
            for f in self.cdir.glob("*/ended.*"):
                f.unlink()
            t0 = time.time()
            res = run.run_jobs(jobs, self.cdir, self.tmp / "logs", limit, 60)
            took = time.time() - t0
            self.assertEqual(set(res.values()), {"0"})
            ev = []
            for n in names:
                s = float(next((self.cdir / n).glob("started.*")).read_text())
                e = float(next((self.cdir / n).glob("ended.*")).read_text())
                ev += [(s, 1), (e, -1)]
            ev.sort()
            cur = peak = 0
            for _, d in ev:
                cur += d
                peak = max(peak, cur)
            return took, peak

        took, peak = timed(2)
        self.assertLessEqual(peak, 2)
        self.assertGreaterEqual(took, 1.6)
        took, peak = timed(4)
        self.assertLess(took, 2.4)
        self.assertGreater(peak, 2)

    # --- signals and leftovers -------------------------------------------------

    def start_driver(self):
        """Run a real pass in a separate interpreter; returns (process, output path)."""
        (self.tmp / "cmds.json").write_text(json.dumps(self.cmds))
        (self.tmp / "driver.py").write_text(DRIVER)
        out = self.tmp / "driver.out"
        fh = open(out, "wb")
        self.addCleanup(fh.close)
        proc = subprocess.Popen([sys.executable, str(self.tmp / "driver.py"), str(self.tmp),
                                 str(Path(run.__file__).resolve().parent)],
                                stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT,
                                start_new_session=True)

        def reap():
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, 9)
                except OSError:
                    pass
                proc.wait()
        self.addCleanup(reap)
        return proc, out

    @staticmethod
    def wait_for(path, seconds=15):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if path.exists() and path.read_text().strip():
                return True
            time.sleep(0.05)
        return False

    def assert_gone(self, pid, what):
        self.addCleanup(lambda: self._kill(pid))
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.1)
        self.fail(f"{what} is still alive")

    def test_sigterm_and_sighup_stop_the_pass(self):
        for sig in (signal.SIGTERM, signal.SIGHUP):
            with self.subTest(sig=sig.name):
                shutil.rmtree(self.cdir, True)
                shutil.rmtree(self.state, True)
                for f in self.tmp.glob("load.*"):
                    f.unlink()
                self.make({"07_search_interest": {"sleep": 60, "spawn_child": True}})
                proc, out = self.start_driver()
                self.assertTrue(self.wait_for(self.cdir / "07_search_interest" / "started.--all"), "collector did not start")
                self.assertTrue(self.wait_for(self.cdir / "07_search_interest" / "child.pid"))
                pid = int((self.cdir / "07_search_interest" / "child.pid").read_text())
                self.addCleanup(lambda p=pid: self._kill(p))
                proc.send_signal(sig)
                self.assertEqual(proc.wait(20), 130)
                self.assertIn("run: interrupted", out.read_text())
                self.assertEqual(self.load_calls(), [])
                self.assert_gone(pid, "child of the interrupted job")

    def test_interrupt_during_load_stops_the_load(self):
        self.three()
        (self.tmp / "load_stub.py").write_text(SLOW_LOAD_STUB)
        proc, out = self.start_driver()
        self.assertTrue(self.wait_for(self.tmp / "load.started"), "load did not start")
        pid = int((self.tmp / "load.pid").read_text())
        self.addCleanup(lambda: self._kill(pid))
        proc.send_signal(signal.SIGTERM)
        self.assertEqual(proc.wait(20), 130)
        self.assertIn("run: interrupted", out.read_text())
        self.assert_gone(pid, "load command")
        self.assertFalse((self.tmp / "label.calls").exists())

    def test_leftover_child_is_cleaned_up_after_a_normal_exit(self):
        self.make({"07_search_interest": {"spawn_child": True}})
        code, _ = self.run_pass()
        self.assertEqual(code, 0)
        pid = int((self.cdir / "07_search_interest" / "child.pid").read_text())
        self.addCleanup(lambda: self._kill(pid))
        self.assert_gone(pid, "leftover child")

    def test_lock(self):
        self.three()
        self.state.mkdir(parents=True)
        with open(self.state / ".run.lock", "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            code, lines = self.run_pass()
            self.assertEqual(code, 3)
            self.assertIn("run: another run is in progress", lines)
            for n in ("01_a", "04_amazon", "05_b"):
                self.assertIsNone(self.calls(n))
            self.assertEqual(self.load_calls(), [])
        code, _ = self.run_pass()
        self.assertEqual(code, 0)

    def test_not_started(self):
        self.make({"01_a": {}, "05_b": {}})
        seen = []
        jobs = [Job("01_a", None), Job("05_b", None)]
        res = run.run_jobs(jobs, self.cdir, self.tmp / "logs", 2, 60, python="/nonexistent/python",
                           on_done=lambda j, e, s: seen.append((j, e)))
        self.assertEqual(res, {j: "not_started" for j in jobs})
        self.assertEqual(sorted(seen, key=lambda t: t[0].folder), [(j, "not_started") for j in jobs])

    def test_permission_error_from_killpg_does_not_stop_the_pass(self):
        self.make({"01_a": {"sleep": 60}, "05_b": {}})
        real = os.killpg

        def killpg_then_deny(pid, sig):
            real(pid, sig)  # the signal is delivered, then macOS-style refusal
            raise PermissionError(1, "Operation not permitted")

        with unittest.mock.patch.object(run.os, "killpg", killpg_then_deny):
            code, lines = self.run_pass("--timeout", "0.05", "--careful")
        self.assertEqual(code, 1)
        self.assertTrue(any(l.startswith("collect 01_a all exit=timeout ") for l in lines), lines)
        self.assertTrue(any(l.startswith("collect 05_b all exit=0 ") for l in lines), lines)
        self.assertTrue(any(l.startswith("collect: jobs=2 failed=1 ") for l in lines), lines)
        self.assertEqual(len(self.load_calls()), 1)

    def test_unexpected_error_in_one_job_is_reported_and_the_rest_complete(self):
        self.make({"01_a": {}, "05_b": {}})
        real = run.subprocess.Popen

        def popen(cmd, *a, **kw):
            if "01_a" in str(cmd[1]):
                raise RuntimeError("boom")
            return real(cmd, *a, **kw)

        with unittest.mock.patch.object(run.subprocess, "Popen", popen):
            code, lines = self.run_pass("--careful")
        self.assertEqual(code, 1)
        self.assertTrue(any(l.startswith("collect 01_a all exit=error ") for l in lines), lines)
        self.assertTrue(any(l.startswith("collect 05_b all exit=0 ") for l in lines), lines)
        self.assertTrue(any(l.startswith("collect: jobs=2 failed=1 ") for l in lines), lines)
        self.assertEqual(len(self.load_calls()), 1)

    def test_odd_run_files_do_not_stop_the_pass(self):
        self.make({"01_a": {}, "05_b": {}})
        d = self.cdir / "05_b" / "raw" / "x"
        d.mkdir(parents=True)
        (d / "20990101T000001Z.run.json").write_text("[]")
        (d / "20990101T000002Z.run.json").write_text("null")
        (d / "20990101T000003Z.run.json").write_text(
            json.dumps({"run_id": "20990101T000003Z", "status": "ok", "cost_usd": "abc"}))
        (d / "20990101T000004Z.run.json").write_text('{"run_id": "2099')
        (d / "20990101T000005Z.run.json").write_text(
            json.dumps({"run_id": "20990101T000005Z", "status": "weird", "cost_usd": None}))
        code, lines = self.run_pass()
        self.assertEqual(code, 0)
        # 2 folders x 2 brands = 4 jobs, one run file each = 4 good stub runs, plus
        # the "abc" file (ok, cost 0) and the "weird" file (runs only): runs=6, ok=5
        self.assertIn("collect: jobs=4 failed=0 runs=6 ok=5 partial=0 could_not_look=0 cost_usd=0.0000", lines)
        self.assertEqual(len(self.load_calls()), 1)

    def test_bad_jobs_and_timeout_values_stop_before_anything_runs(self):
        self.three()
        for argv, msg in ((("--jobs", "0"), "--jobs must be at least 1"),
                          (("--jobs", "-3"), "--jobs must be at least 1"),
                          (("--timeout", "0"), "--timeout must be greater than 0"),
                          (("--timeout", "-1"), "--timeout must be greater than 0")):
            code, lines = self.run_pass(*argv)
            self.assertEqual(code, 2, argv)
            self.assertIn(msg, lines)
        for f in ("01_a", "04_amazon", "05_b"):
            self.assertIsNone(self.calls(f))
        self.assertEqual(self.load_calls(), [])
        self.assertFalse((self.state / "logs").exists())


if __name__ == "__main__":
    unittest.main()
