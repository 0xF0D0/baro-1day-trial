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
3. A virtual environment with its two dependencies: `python3 -m venv .venv && .venv/bin/pip install -r part1/pipeline/requirements.txt`
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

## The tables

Items come in four kinds. Each kind has its own table, or a pair of tables, and every one of them starts with the
same columns. Two more tables describe the runs themselves.

| Kind | Tables | Filled by |
|---|---|---|
| 1. Ads | `ads` | 1 Google Ads Transparency, 2 TikTok ads, 3 Meta Ad Library, 10 brand site and emails |
| 2. Product pages | `products`, `reviews` | 4 Amazon, 5 retail shelf, 9 TikTok Shop, 10 brand site |
| 3. Search | `search_rankings`, `search_interest` | 6 Google results, 7 search interest |
| 4. Social posts | `posts` | 8 TikTok posts |

### Columns every item table has

```sql
source        text        NOT NULL,  -- which source saw the item
brand         text        NOT NULL,  -- brand slug
kind          text        NOT NULL,  -- what the row is within its source: ad, product, review, ...
key           text        NOT NULL,  -- the item's identity in its source
scope         text        NOT NULL,  -- the part of the source it belongs to (see run_scopes)
url           text,                  -- where a person can check the item
fetched_at    timestamptz NOT NULL,  -- when the stored values were collected
first_seen_at timestamptz NOT NULL,  -- start of the first run that saw the item
last_seen_at  timestamptz NOT NULL,  -- start of the latest run that saw it
ended_at      timestamptz,           -- when it was found gone; NULL while it is there
last_run_id   text        NOT NULL,  -- the run that last wrote the row
raw           jsonb       NOT NULL,  -- the source's own record, as collected
PRIMARY KEY (source, brand, kind, key)   -- a second run updates the row; rows are never deleted
```

### 1. Ads

`ads`: one ad creative, or one message on a channel the brand owns. Kinds: `ad` (sources 1, 2, 3); `offer_slot`,
`klaviyo_form`, `email` (source 10).

```sql
-- the shared columns, then
channel         text NOT NULL,  -- paid: google, meta, tiktok. owned: site, signup_form, email
advertiser_id   text,           -- the advertiser's ID in the source
advertiser_name text,
format          text,           -- text, image, video, dco, dpa
headline        text,
body            text,
cta             text,           -- the call-to-action label
landing_url     text,           -- where the ad sends people
landing_domain  text,
started_at      timestamptz,    -- the start date the source states; NULL when it states none
last_shown_at   timestamptz,    -- the last-shown date the source states
variation_count integer,        -- how many variations the creative has (Google)
placements      text[],         -- FACEBOOK, INSTAGRAM, MESSENGER, ... (Meta)
offer_code      text            -- a discount code stated with the offer
```

How long an ad has been seen is in the shared `first_seen_at`, `last_seen_at` and `ended_at`; they are never copied
into `started_at`.

### 2. Product pages

`products`: one product at one seller. Kinds: `product` (sources 4, 5, 9, 10); `search_result` (source 9);
`retailer_availability` (source 10, Batiste's where-to-buy data).

```sql
-- the shared columns, then
retailer     text NOT NULL,   -- amazon, ulta, target, sephora, chewy, tiktok_shop, own_site;
                              -- for where-to-buy rows the retailer the widget names (walmart, cvs, ...)
product_id   text,            -- the seller's product ID (ASIN, TCIN, SKU)
title        text,
price        numeric(12,2),   -- the price a person sees at the row's url
price_max    numeric(12,2),   -- the upper end when the seller shows a range
list_price   numeric(12,2),   -- the price before a discount, when shown
currency     text,
rating       numeric(3,2),    -- NULL, not 0, when there are no reviews
review_count integer,
rank         integer,         -- position in the seller's listing or search
sponsored    boolean,
availability text,            -- IN_STOCK, OUT_OF_STOCK or NULL
seller_name  text,            -- the seller on a marketplace
sold_count   bigint           -- units sold, where the source publishes it
```

`reviews`: one review of a product, a child row of `products`. Sources 4 and 5. Reviewer names are not stored.

```sql
-- the shared columns, then
product_key   text NOT NULL,  -- the key of its products row (same source and brand)
rating        numeric(3,2),
title         text,
body          text,
review_date   date,
verified      boolean,        -- a verified purchase
helpful_votes integer
```

### 3. Search

`search_rankings`: one result for one search term. Source 6.

```sql
-- the shared columns, then
keyword      text NOT NULL,   -- the search term
keyword_rank integer,         -- the term's place among the brand's terms
position     integer,         -- the result's place on the page
result_url   text,
domain       text,
title        text,
description  text,
result_type  text             -- organic
```

`search_interest`: one week of one search term. Source 7.

```sql
-- the shared columns, then
keyword    text NOT NULL,
series     text NOT NULL,     -- solo: the term by itself. compared: next to the brand's other terms
week_start date NOT NULL,
value      integer,           -- Google Trends' 0 to 100, relative within the series
has_data   boolean,
is_partial boolean,           -- the current, unfinished week
geo        text               -- US
```

### 4. Social posts

`posts`: one TikTok post. Source 8.

```sql
-- the shared columns, then
post_id           text,
posted_at         timestamptz,
creator_handle    text,       -- the account name; display names are not stored
creator_is_brand  boolean,    -- posted by the brand's own account
creator_followers bigint,
views             bigint,
likes             bigint,
comments          bigint,
shares            bigint,
saves             bigint,
caption           text,
hashtags          text[],
surfaced_by       text[]      -- how the post was found: profile_popular, hashtag
```

### The runs

`runs`: one row per run, that is one look at one source for one brand. This is where "could not look" lives.

```sql
source         text,
brand          text,
run_id         text,                  -- the look's start time in UTC, YYYYMMDDTHHMMSSZ
started_at     timestamptz NOT NULL,
finished_at    timestamptz,
status         text NOT NULL,         -- ok: everything in scope was read. partial: some of it.
                                      -- could_not_look: nothing could be read
reason         text NOT NULL,         -- empty for ok; otherwise what was not read and why
records        integer,               -- records the collector wrote
expected_total integer,               -- the total the source itself reported, when it reports one
requests       integer,               -- requests the collector sent
cost_usd       numeric(10,4),         -- what its paid runs cost
extra          jsonb,                 -- the collector's own details, part by part
result         text NOT NULL,         -- what the loader did: applied, superseded, empty_no_mapper
loaded_at      timestamptz NOT NULL,
PRIMARY KEY (source, brand, run_id)
```

`run_scopes`: one row per scope of a run. A scope is a part of a source that can be complete or not by itself:
one retailer of the shelf (`ulta`, `target`), the `prices`, `offers_home` or `emails` of a brand's site, one Facebook
page of a brand. An item is marked ended only by a run whose scope for that item was `ok`, so a partial look never
ends what it did not see.

```sql
source text,
brand  text,
run_id text,
scope  text,
status text NOT NULL,                 -- ok, partial, could_not_look
reason text NOT NULL,
PRIMARY KEY (source, brand, run_id, scope)
```

The latest state of every source and brand:

```sql
SELECT DISTINCT ON (source, brand) source, brand, status, reason, records, finished_at
FROM runs WHERE result = 'applied' ORDER BY source, brand, run_id DESC;
```

`changes` and `ad_angles` are described under "What the agents read".

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
