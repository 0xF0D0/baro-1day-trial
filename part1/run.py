#!/usr/bin/env python3
"""Market Radar: one command that collects, loads and labels.

Plans one process per collector job, runs them with a bounded pool and a timeout, prints the run results'
summary, then starts the loader and the label command as processes. See
docs/superpowers/specs/2026-11-11-run-all-design.md.
"""
import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Collectors that only call the Apify API, so their brands may run side by side.
BRAND_PARALLEL = ("02_tiktok_ad_library", "04_amazon", "06_google_results", "08_tiktok_posts", "09_tiktok_shop")
ROOT = Path(__file__).resolve().parents[1]
POLL_S = 0.05
KILL_GRACE_S = 10

_print_lock = threading.Lock()


def say(line: str) -> None:
    with _print_lock:
        print(line, flush=True)


@dataclass(frozen=True)
class Job:
    folder: str
    brand: str | None  # None means --all


def collector_folders(collectors_dir: Path) -> list[str]:
    return sorted(p.name for p in collectors_dir.iterdir() if (p / "source_collector.py").is_file())


def read_brands(collectors_dir: Path) -> list[str]:
    return [b["slug"] for b in json.loads((collectors_dir / "brands.json").read_text())]


def select_sources(folders: list[str], sources: str | None) -> list[str]:
    if sources is None:
        return list(folders)
    chosen = set()
    for entry in (e.strip() for e in sources.split(",")):
        if entry.isdigit():
            hits = [f for f in folders if f.split("_", 1)[0].isdigit() and int(f.split("_", 1)[0]) == int(entry)]
        else:
            hits = [f for f in folders if f == entry]
        if not hits:
            raise ValueError(f"unknown source: {entry}")
        chosen.update(hits)
    return [f for f in folders if f in chosen]


def plan_jobs(folders: list[str], brands: list[str], brand: str | None) -> list[Job]:
    jobs = []
    for f in folders:
        if brand is not None:
            jobs.append(Job(f, brand))
        elif f in BRAND_PARALLEL:
            jobs.extend(Job(f, b) for b in brands)
        else:
            jobs.append(Job(f, None))
    return jobs


def _stop_group(proc: subprocess.Popen) -> None:
    """SIGTERM the job's process group, SIGKILL it after the grace period."""
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):  # macOS: PermissionError for an unreaped leader
        pass
    try:
        proc.wait(KILL_GRACE_S)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)  # whatever of the group is still there
    except (ProcessLookupError, PermissionError):
        pass
    proc.wait()


def run_jobs(jobs, collectors_dir, log_dir, max_jobs, timeout_s, python=sys.executable, on_done=None):
    log_dir.mkdir(parents=True, exist_ok=True)
    results: dict[Job, str] = {j: "not_started" for j in jobs}
    stop = threading.Event()

    def one(job: Job) -> None:
        if stop.is_set():
            return
        t0 = time.monotonic()
        try:
            _one(job, t0)
        except Exception:  # a bad job is reported, never allowed to stop the pass
            results[job] = "error"
            if on_done:
                on_done(job, "error", time.monotonic() - t0)

    def _one(job: Job, t0: float) -> None:
        script = collectors_dir / job.folder / "source_collector.py"
        args = ["--all"] if job.brand is None else ["--brand", job.brand]
        log = log_dir / f"{job.folder}.{job.brand or 'all'}.log"
        try:
            with open(log, "wb") as out:
                proc = subprocess.Popen([python, str(script), *args], stdin=subprocess.DEVNULL,
                                        stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
        except OSError:
            results[job] = "not_started"
            if on_done:
                on_done(job, "not_started", 0)
            return
        deadline = t0 + timeout_s
        while True:
            try:
                code = proc.wait(POLL_S)
                text = str(code)
                try:  # best effort: a child left behind in the group (a browser after a crash)
                    os.killpg(proc.pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass
                break
            except subprocess.TimeoutExpired:
                pass
            if stop.is_set():
                _stop_group(proc)
                text = "interrupted"
                break
            if time.monotonic() >= deadline:
                _stop_group(proc)
                text = "timeout"
                break
        results[job] = text
        if on_done:
            on_done(job, text, time.monotonic() - t0)

    pool = ThreadPoolExecutor(max_workers=max_jobs)
    try:
        futures = [pool.submit(one, j) for j in jobs]
        for f in futures:
            f.result()
    except BaseException:
        stop.set()
        pool.shutdown(wait=True, cancel_futures=True)
        raise
    pool.shutdown()
    return results


def summarize(collectors_dir: Path, folders: list[str], start_stamp: str) -> dict:
    out = {"runs": 0, "ok": 0, "partial": 0, "could_not_look": 0, "cost_usd": 0.0}
    for f in folders:
        for path in sorted((collectors_dir / f / "raw").glob("*/*.run.json")):
            try:
                data = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict) or str(data.get("run_id", "")) < start_stamp:
                continue
            out["runs"] += 1
            if data.get("status") in ("ok", "partial", "could_not_look"):
                out[data["status"]] += 1
            cost = data.get("cost_usd")
            if isinstance(cost, (int, float)) and not isinstance(cost, bool):
                out["cost_usd"] += cost
    return out


def _labels_state(path: Path) -> tuple[int, int]:
    try:
        st = path.stat()
        return st.st_size, st.st_mtime_ns
    except OSError:
        return 0, 0


def _run_command(cmd: list[str]) -> int:
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL)
    except OSError as e:
        say(f"run: could not start {cmd[0]}: {e.strerror}")
        return 1
    try:
        return proc.wait()
    except BaseException:  # an interrupt: stop the command, then let it go on up
        proc.terminate()
        try:
            proc.wait(KILL_GRACE_S)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        raise


def main(argv=None, *, load_cmd=None, label_cmd=None, labels_file=None, state_dir=None) -> int:
    ap = argparse.ArgumentParser(prog="run.py", description="Collect, load and label in one pass.")
    ap.add_argument("--brand")
    ap.add_argument("--sources")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--timeout", type=float, default=60, help="minutes per job")
    ap.add_argument("--no-label", action="store_true")
    ap.add_argument("--collectors-dir", type=Path, default=ROOT / "part1/collectors")
    a = ap.parse_args(argv)
    if a.jobs < 1:
        say("--jobs must be at least 1")
        return 2
    if not a.timeout > 0:
        say("--timeout must be greater than 0")
        return 2
    load_cmd = load_cmd or [sys.executable, str(ROOT / "part1/pipeline/load.py")]
    label_cmd = label_cmd or [sys.executable, str(ROOT / "part1/pipeline/angles.py"), "--label"]
    labels_file = labels_file or ROOT / "part1/pipeline/labels/ad_angles.jsonl"
    state_dir = state_dir or ROOT / "part1"
    cdir = a.collectors_dir

    brands = read_brands(cdir)
    if a.brand is not None and a.brand not in brands:
        say(f"unknown brand: {a.brand}")
        return 2
    try:
        folders = select_sources(collector_folders(cdir), a.sources)
    except ValueError as e:
        say(str(e))
        return 2

    state_dir.mkdir(parents=True, exist_ok=True)
    with open(state_dir / ".run.lock", "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            say("run: another run is in progress")
            return 3

        start_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        jobs = plan_jobs(folders, brands, a.brand)

        def on_done(job, text, secs):
            say(f"collect {job.folder} {job.brand or 'all'} exit={text} {int(secs)}s")

        def on_term(signum, frame):
            raise KeyboardInterrupt

        previous = {}
        try:
            for sig in (signal.SIGTERM, signal.SIGHUP):
                if signal.getsignal(sig) == signal.SIG_IGN:  # e.g. started under nohup: stay ignored
                    continue
                previous[sig] = signal.signal(sig, on_term)
        except ValueError:  # not the main thread
            pass
        try:
            results = run_jobs(jobs, cdir, state_dir / "logs" / start_stamp, a.jobs, a.timeout * 60,
                               on_done=on_done)

            failed = sum(1 for t in results.values() if t != "0")
            s = summarize(cdir, folders, start_stamp)
            say(f"collect: jobs={len(jobs)} failed={failed} runs={s['runs']} ok={s['ok']} "
                f"partial={s['partial']} could_not_look={s['could_not_look']} cost_usd={s['cost_usd']:.4f}")

            load = [*load_cmd, "--collectors-dir", str(cdir)]
            load_failed = _run_command(load) != 0
            if not a.no_label:
                before = _labels_state(labels_file)
                _run_command(label_cmd)  # its exit code never changes ours
                if _labels_state(labels_file) != before:
                    load_failed |= _run_command(load) != 0
            return 1 if failed or load_failed else 0
        except KeyboardInterrupt:
            say("run: interrupted")
            return 130
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)


if __name__ == "__main__":
    sys.exit(main())
