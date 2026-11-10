# Market Radar: one command

Date: 2026-11-11. Builds on the collectors' contract (`part1/collectors/README.md`), the loader
(`part1/pipeline/README.md`) and `2026-11-11-agent-radar-design.md`. None of them changes.

## 1. Intent

Today a person runs ten collectors one by one and then the loader. The radar is meant to be fed constantly, and
someone else must be able to run all of it. This adds the one command that does the whole pass, and that a scheduler
can call every hour:

    .venv/bin/python part1/run.py

It runs the collectors, loads their files, asks for the angles of new ad texts, and applies them. It adds no logic of
its own: every step is a command that already exists.

## 2. The pass

1. **Lock.** Take an exclusive lock on `part1/.run.lock` (`fcntl.flock`, non-blocking). When another pass holds it,
   print `run: another run is in progress` and exit 3. The lock goes when the process ends, however it ends.
2. **Collect.** Plan the jobs (section 3) and run them, at most `--jobs` at a time. A job is one process:
   `<python> <collector folder>/source_collector.py --brand <slug>` or `... --all`, with `<python>` the interpreter that
   runs `run.py`. Its output goes to a log file (section 5). When a job ends, print
   `collect <folder> <brand or all> exit=<code> <seconds>s`.
   A job that runs longer than `--timeout` minutes is stopped with its whole process group (the browser it started
   included): `SIGTERM`, and `SIGKILL` ten seconds later if it is still there. Its line says `exit=timeout`.
   A job that cannot be started says `exit=not_started`. A job whose handling fails inside `run.py` says
   `exit=error`; like every other job that does not end with 0, it counts as failed and the pass goes on.
   When a job's process ends on its own, anything it left running in its process group is told to stop.
3. **Collect summary.** Read the run result files (`raw/<brand>/<run_id>.run.json`) under the selected collector
   folders whose `run_id` is at or after the pass's start time (UTC, `YYYYMMDDTHHMMSSZ`), and print
   `collect: jobs=<n> failed=<n> runs=<n> ok=<n> partial=<n> could_not_look=<n> cost_usd=<sum, 4 decimals>`.
   `failed` counts jobs whose exit is not 0.
4. **Load.** Run `<python> part1/pipeline/load.py --collectors-dir <dir>` and pass its output through.
5. **Label.** Unless `--no-label`: run `<python> part1/pipeline/angles.py --label` and pass its output through. Without
   a key or without credit that command says so itself and writes nothing.
6. **Apply.** If the labels file changed during step 5 (size or modification time), run the load command once more so
   that the new lines reach `ad_angles`. Its output is passed through.
7. **Exit code.** 0 when no job failed and every load command returned 0; 1 otherwise. The label step never changes
   the exit code: an ad without a label is visible as `not_labeled` in the loader's `angles:` line.

A failed job does not stop the pass: the other collectors' files are still loaded.

When `run.py` itself is interrupted (Ctrl-C, `SIGTERM` or `SIGHUP`), it stops every running job the same way as a
timed-out one, prints `run: interrupted` and exits 130 without loading. Interrupted during the load or the label
step, it stops that command and exits 130. Without this, closing the terminal would leave collectors running
behind a released lock. A signal that was already ignored when `run.py` started (as under `nohup`) stays ignored.

## 3. Which jobs, and what runs side by side

Collector folders are the directories of `--collectors-dir` that hold a `source_collector.py`, in name order.
Brands are the slugs of `brands.json` in that directory.

| Collector | Jobs | Why |
|---|---|---|
| `02_tiktok_ad_library`, `04_amazon`, `06_google_results`, `08_tiktok_posts`, `09_tiktok_shop` | one per brand (`--brand <slug>`) | they only call the Apify API, never the source's own site, so brands may run side by side |
| every other collector | one (`--all`) | it sends requests to the source's site itself; the collectors' rule is one request at a time per site, so its brands run one after another inside the collector |

The first list is a constant in `run.py` (`BRAND_PARALLEL`). A folder not in it gets one job.

Different collectors always run side by side: they talk to different sites.

With `--brand <slug>` every selected collector gets exactly one job, `--brand <slug>`.

`--sources` selects collectors: a comma-separated list of numbers (`1,5,10`, matched against the folder's leading
number) or folder names. An entry that matches no folder is an error: print it and exit 2 before anything runs.
An unknown `--brand` is the same, and so is `--jobs` below 1 or `--timeout` not above 0.

## 4. Command line

    part1/run.py [--brand <slug>] [--sources <list>] [--jobs <n>] [--timeout <minutes>] [--no-label]
                 [--collectors-dir <path>]

| Option | Default |
|---|---|
| `--jobs` | 8 |
| `--timeout` | 60 |
| `--collectors-dir` | `part1/collectors` of this repository |

## 5. Logs

Each job writes its standard output and error to `part1/logs/<pass start, YYYYMMDDTHHMMSSZ>/<folder>.<brand or all>.log`.
`part1/logs/` and `part1/.run.lock` are git-ignored. Nothing else is written by `run.py`; tokens and keys are never
printed or logged by it.

## 6. Scheduling

`run.py` is what a scheduler calls. The README shows one crontab line. The lock makes an overlapping pass skip itself.
Source 7 opens a visible browser window, so the scheduler has to run inside a desktop session.

Every pass costs what its Apify collectors cost; the summary prints the sum. Which sources run every hour and which
once a day is the operator's choice, made with `--sources`.

## 7. Goals, non-goals, anti-goals

Goals
- One command runs the whole pass on someone else's machine, after the setup in the README.
- A pass can be cut to one brand or to some sources, so that a check does not cost a full pass.
- A stuck or crashed collector cannot hang or stop the pass, and is reported.

Non-goals
- Retries. A collector sends each request once; the next pass is the retry.
- A daemon or a scheduler of its own. A cost cap.
- Windows.

Anti-goals
- Hiding a failure: every job's exit, every run's status and the loader's own lines are printed, and the exit code
  says whether something failed.
- Two requests at once to the same source site.

## 8. Constraints carried over

1. Hand-written code; at least one source without a paid scraping service.
2. Rerun-safe: no duplicates on a second run; a missing item is marked ended, never deleted.
3. Honest gaps: "could not look" is never recorded as "nothing found"; partial collection is marked.
4. Clean collection: no personal data of private individuals; requests are spaced.
5. Local Postgres, one command, reproducible by someone else.

## 9. Calls made by the designer

1. Brands run side by side only for collectors that call nothing but the Apify API.
2. A timed-out collector is killed with its process group. It leaves no run result, so nothing is loaded for it and
   nothing is ended: the next pass looks again.
3. The label step does not affect the exit code.
4. The load command runs a second time only when the labels file changed.
5. `run.py` starts the other scripts as processes instead of importing them: each keeps its own exit code and output,
   and a crash in one cannot take the pass down.
6. Logs go to files; the terminal shows one line per job and the loader's own lines.

## 10. Left to the builder

- How the pool is built (threads over `subprocess`, or polling).
- The exact layout of the tests; they use stub collectors in a temporary directory and stub commands for the load and
  label steps, never the network.
