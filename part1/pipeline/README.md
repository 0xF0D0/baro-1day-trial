# Loader

The loader reads the raw files that the collectors write (`<source>/raw/<brand>/<run_id>.run.json` and `.jsonl`)
and fills Postgres tables. A source with a mapper is turned into rows; a source without one is only reported.
Running it twice adds no duplicates: items that disappear are marked ended, never deleted.

On top of the item tables it keeps what the agents read: a log of what changed between runs, the angles of each
ad, and three views (see "What the agents read").

## Setup

1. A running local Postgres. On macOS, Homebrew Postgres may refuse to start without a locale:
   `LC_ALL=en_US.UTF-8 pg_ctl -D <data directory> start`.
2. `createdb market_radar`
3. A virtual environment with the one dependency: `python3 -m venv .venv && .venv/bin/pip install -r part1/pipeline/requirements.txt`
   (or `-r part1/requirements.txt`, which also installs what the collectors need)
4. Optional: `DATABASE_URL` (environment, or a line in `.env` at the repository root).
   Default: `postgresql://localhost:5432/market_radar`.
5. Only for `angles.py --label`: `ANTHROPIC_API_KEY` (environment, or a line in `.env` at the repository root).
   Everything else runs without it.

## Run

    .venv/bin/python part1/pipeline/load.py [--collectors-dir <path>] [--labels <file>]

`--collectors-dir` defaults to `part1/collectors` of this repository, `--labels` to
`part1/pipeline/labels/ad_angles.jsonl`. The schema is created if missing.

The ten tables are created only when they do not exist. After a change to a table in `schema.sql`, drop the
database (`dropdb market_radar && createdb market_radar`; the views depend on the tables, so a plain
`DROP TABLE` is refused) and run the loader again; it reloads every run from the files, `changes` included.
The three views are dropped and created on every run, so a changed view definition takes effect at once.

## What the agents read

| Name | One row is | Answers |
|---|---|---|
| `radar_angles` (view) | one angle of one thing a brand sells | which angles does a brand use for a product, and do they last |
| `radar_running` (view) | one ad or owned-channel message | how long has it run, what does it sell, where does it send people, with which angles |
| `radar_response` (view) | one published number of a post, product or search result | what is getting a response |
| `changes` (table) | one change to one item, seen at one run | what changed, and when |
| `ad_angles` (table) | the three angles of one ad, with the words they were read from | how does this ad sell |

An ad is `working` when it has run 30 days or more, `not_working` when it ended within 7 days of a known start,
and `undecided` otherwise. The rules, the columns and the limits are in
`docs/superpowers/specs/2026-11-11-agent-radar-design.md`.

    -- which angles a brand uses per product, longest-lived first
    SELECT subject, angle_kind, angle, ads, live, started_last_7d, oldest_days_live
    FROM radar_angles WHERE brand = 'living-proof' ORDER BY oldest_days_live DESC, ads DESC;

    -- the ads behind one line
    SELECT key, started, days_live, verdict, headline, url
    FROM radar_running WHERE brand = 'living-proof' AND subject = 'collections/holiday-kits';

    -- what changed since a time
    SELECT changed_at, brand, table_name, key, change, field, old_value, new_value
    FROM changes WHERE changed_at >= '2026-11-10' ORDER BY changed_at;

    -- posts that reached past the creator's own followers
    SELECT brand, label, value AS views, ratio, url
    FROM radar_response WHERE metric = 'views' AND verdict = 'working' ORDER BY value DESC;

## Angles

An angle is a reading of an ad's words, so it is kept in a file of its own, `part1/pipeline/labels/ad_angles.jsonl`:
one line per distinct ad text, keyed by the SHA-256 of the text, with one value for each of three kinds (offer,
message, voice) and the phrase of the ad each was read from. The loader copies the lines onto the ads after its
runs. It refuses a file with a value outside the lists, or with a phrase that is not in the ad's words.

    .venv/bin/python part1/pipeline/angles.py --pending    # the ad texts that have no line yet, as JSON lines
    .venv/bin/python part1/pipeline/angles.py --label      # ask a model for them and append the lines

`--label` sends each pending text once, up to 8 requests at a time, to the model named by `ANGLE_MODEL` (default
`claude-opus-5-5`), checks the answer like any other line, and never asks again for a text that has a line. Without a key it prints
`label: could not look: missing_key`; when the API rejects the request it stops and prints the API's reason. A text
without a line is shown as `not_labeled`, never as an ad without an angle. Lines can also be written or corrected
by hand.

## Writing a mapper

A column that a mapper leaves out of a row keeps its stored value on update and is NULL on first insert, so a
mapper must return every column it wants filled the first time a row is seen. Every row's scope must be one of
the scopes the mapper returns; the loader fails the run otherwise.

## Output

One line per run, except runs already loaded:

    <source> <brand> <run_id> <status> <result> inserted=<n> updated=<n> ended=<n> not_fetched=<n> [error=<text>]

`<result>` is `applied`, `superseded`, `empty_no_mapper`, `no_mapper` or `failed`. Two last lines summarise:

    angles: labeled=<ads> not_labeled=<ads> no_text=<ads>
    runs: applied=<n> superseded=<n> empty_no_mapper=<n> failed=<n> already_loaded=<n> no_mapper=<sources>

`no_mapper` lists the sources that have records but no mapper yet (`-` if none). When the labels file is not
valid the first of the two lines is `angles: failed: line <n>: <reason>`; the runs stay loaded. The exit code is 1
when a run failed, the labels file is not valid or the database cannot be reached, otherwise 0.

## Tests

The tests use a real Postgres and create a temporary schema in `market_radar_test`:

    createdb market_radar_test
    TEST_DATABASE_URL=postgresql://localhost:5432/market_radar_test .venv/bin/python -m unittest discover -s part1/pipeline/tests -v
