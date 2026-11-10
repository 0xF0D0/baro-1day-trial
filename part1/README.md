# Market Radar

Give it brands; it looks at ten sources (ads, shelf, search, social) and keeps what it finds in a local Postgres:
what each competitor is doing, since when, whether it stopped, and what the agents read on top of that.

| Part | What it does | Details |
|---|---|---|
| `collectors/` | ten collectors, one per source; each writes what the source shows right now to files | `collectors/README.md` |
| `pipeline/` | loads those files into tables, marks what ended, records what changed, applies the ad angles, defines the views | `pipeline/README.md` |
| `run.py` | one command that does a whole pass | this page |

## Setup

From the repository root:

    python3 -m venv .venv
    .venv/bin/pip install -r part1/requirements.txt
    createdb market_radar
    cp .env.example .env        # then fill in what you have

- Google Chrome must be installed: sources 1, 3, 5, 7 and 10 drive it. Source 7 opens a visible window.
- A running local Postgres. On macOS, Homebrew Postgres may refuse to start without a locale:
  `LC_ALL=en_US.UTF-8 pg_ctl -D <data directory> start`.
- `.env` holds `APIFY_TOKEN` (sources 2, 3, 4, 6, 8, 9 and parts of 5 and 10) and, optionally, `ANTHROPIC_API_KEY`
  (labeling new ad texts). Without a token or key the step that needs it records "could not look" and the rest runs.

## One pass

    .venv/bin/python part1/run.py

It runs the collectors side by side, loads their files, asks a model for the angles of ad texts it has not seen, and
applies them. Running it again adds no duplicates.

| Option | Meaning | Default |
|---|---|---|
| `--brand <slug>` | only this brand | all five |
| `--sources <list>` | only these collectors, by number or folder name: `1,5,10` | all ten |
| `--jobs <n>` | how many collector processes at once | 8 |
| `--timeout <minutes>` | stop a collector that runs longer | 60 |
| `--no-label` | skip the label step | |
| `--collectors-dir <path>` | where the collectors are | `part1/collectors` |

A cheap check: one brand, and two sources that cost nothing for it:

    .venv/bin/python part1/run.py --brand batiste --sources 1,10

### What runs side by side

Different collectors always do: they talk to different sites. Inside one collector, brands run one after another
when the collector itself sends requests to the source's site (sources 1, 3, 5, 7, 10), because the rule is one
request at a time per site. Collectors that only call the Apify API (sources 2, 4, 6, 8, 9) run one process per brand.

### What it prints

    collect <collector> <brand or all> exit=<code> <seconds>s        one line per collector process, as it ends
    collect: jobs=<n> failed=<n> runs=<n> ok=<n> partial=<n> could_not_look=<n> cost_usd=<sum>
    ...the loader's lines (see pipeline/README.md), ending in its `angles:` and `runs:` lines
    ...the label command's line

`exit=timeout` means the collector was stopped; `exit=1` that one of its brands hit an unexpected error (its run
result was still written). `cost_usd` is what the pass's Apify runs cost. Each collector's own output is in
`part1/logs/<start time>/<collector>.<brand or all>.log`.

The exit code is 0 when no collector process failed and the loader returned 0, 1 otherwise, 2 for a wrong `--brand`
or `--sources`, and 3 when another pass is still running. A collector that fails does not stop the pass: the others'
files are still loaded, and nothing is marked ended for a source that was not read completely.

## Every hour

`run.py` is what a scheduler calls; a second pass that starts while one is running exits at once.

    0 * * * * cd <repository> && .venv/bin/python part1/run.py >> part1/logs/cron.log 2>&1

- The schedule has to run inside a desktop session, because source 7 opens a browser window.
- Every pass costs what its Apify collectors cost; the `collect:` line prints the sum. The runs of 2026-11-11 cost
  5.28 USD (without source 3 for three brands and source 5 for one), 3.12 USD of it source 4. Sources 1 and 7 cost
  nothing. Which sources run every hour and which once a day is a choice made with `--sources`, for example:

      0 * * * * cd <repository> && .venv/bin/python part1/run.py --sources 1,7 >> part1/logs/cron.log 2>&1
      30 6 * * * cd <repository> && .venv/bin/python part1/run.py --sources 2,3,4,5,6,8,9,10 >> part1/logs/cron.log 2>&1

## Where to look

- The tables and views, with example queries: `pipeline/README.md`.
- The designs: `docs/superpowers/specs/` at the repository root.
