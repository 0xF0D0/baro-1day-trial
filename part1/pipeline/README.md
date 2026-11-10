# Loader

The loader reads the raw files that the collectors write (`<source>/raw/<brand>/<run_id>.run.json` and `.jsonl`)
and fills Postgres tables. A source with a mapper is turned into rows; a source without one is only reported.
Running it twice adds no duplicates: items that disappear are marked ended, never deleted.

## Setup

1. A running local Postgres. On macOS, Homebrew Postgres may refuse to start without a locale:
   `LC_ALL=en_US.UTF-8 pg_ctl -D <data directory> start`.
2. `createdb market_radar`
3. A virtual environment with the one dependency: `python3 -m venv .venv && .venv/bin/pip install -r part1/pipeline/requirements.txt`
   (or `-r part1/requirements.txt`, which also installs what the collectors need)
4. Optional: `DATABASE_URL` (environment, or a line in `.env` at the repository root).
   Default: `postgresql://localhost:5432/market_radar`.

## Run

    .venv/bin/python part1/pipeline/load.py [--collectors-dir <path>]

`--collectors-dir` defaults to `part1/collectors` of this repository. The schema is created if missing.

The tables are created only when they do not exist. After a change to `schema.sql`, drop the eight tables
(or the database) and run the loader again; it reloads every run from the files.

## Writing a mapper

A column that a mapper leaves out of a row keeps its stored value on update and is NULL on first insert, so a
mapper must return every column it wants filled the first time a row is seen. Every row's scope must be one of
the scopes the mapper returns; the loader fails the run otherwise.

## Output

One line per run, except runs already loaded:

    <source> <brand> <run_id> <status> <result> inserted=<n> updated=<n> ended=<n> not_fetched=<n> [error=<text>]

`<result>` is `applied`, `superseded`, `empty_no_mapper`, `no_mapper` or `failed`. A last line summarises:

    runs: applied=<n> superseded=<n> empty_no_mapper=<n> failed=<n> already_loaded=<n> no_mapper=<sources>

`no_mapper` lists the sources that have records but no mapper yet (`-` if none). The exit code is 1 when a run
failed or the database cannot be reached, otherwise 0.

## Tests

The tests use a real Postgres and create a temporary schema in `market_radar_test`:

    createdb market_radar_test
    TEST_DATABASE_URL=postgresql://localhost:5432/market_radar_test .venv/bin/python -m unittest discover -s part1/pipeline/tests -v
