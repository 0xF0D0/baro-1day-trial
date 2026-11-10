# Market Radar

Give it brands; it looks at ten sources (ads, shelf, search, social) and keeps what it finds in a local Postgres:
what each competitor is doing, since when, whether it stopped, and what the agents read on top of that.

| Part | What it does | Details |
|---|---|---|
| `collectors/` | ten collectors, one per source; each writes what the source shows right now to files | `collectors/README.md` |
| `pipeline/` | loads those files into tables, marks what ended, records what changed, applies the ad angles, defines the views | `pipeline/README.md` |
| `run.py` | one command that does a whole pass | this page |

Every command on this page is run from the repository root.

## Prerequisites

What a machine needs before the first pass. Nothing here is started or installed by `run.py`.

| Needed | Used by | Without it |
|---|---|---|
| macOS or Linux | `run.py` uses POSIX process groups and file locks. Developed on macOS; not tried on Linux, and it will not run on Windows | nothing runs |
| Python 3.10 or newer (developed on 3.14) | everything | nothing runs |
| A running PostgreSQL server with a database in it (developed on 16): one already installed, or Docker for the compose file in this folder | the loader and the tables | the collectors still write their files; nothing is loaded |
| Google Chrome, installed | sources 1, 3, 5, 7 and 10, through Playwright with `channel="chrome"`. No Playwright browser download is needed | those sources fail |
| A desktop session | source 7 opens a visible Chrome window | source 7 fails |
| An Apify account with usage available, and its API token | sources 2, 3, 4, 6, 8, 9 and parts of 5 and 10 | each of those records "could not look" (`missing_token`); the rest runs |
| An Anthropic API key (optional) | labeling the angles of ad texts not seen before | new texts stay `not_labeled`; the labels already in the repository still apply |
| A mailbox signed up to the brands, and an app password for it (optional) | source 10's welcome emails, read over IMAP on every pass | the three exported messages in the repository are read instead |
| A US IP address | see "Network" | see "Network" |

No collector logs in to a site, and a rerun needs no email account: see "Accounts and the inbox".

### `.env`

In `.env` at the repository root (`.env.example` is the template; `.env` is ignored by git):

| Key | Needed | Notes |
|---|---|---|
| `APIFY_TOKEN` | for the Apify sources | Must be in the file: most collectors read the file, not the environment |
| `ANTHROPIC_API_KEY` | no | Environment variable or the file |
| `DATABASE_URL` | no | Default `postgresql://localhost:5432/market_radar`. Set it for another host, port, user or database. An environment variable of the same name wins over the file |
| `INBOX_ADDRESS`, `INBOX_APP_PASSWORD` | no | The welcome-email mailbox and an app password for it. With both set, source 10 reads the mailbox over IMAP; without them it reads the exported files. Environment variable or the file. How to get them: `collectors/10_brand_site_and_emails/inbox_setup.md` |
| `INBOX_IMAP_HOST` | no | Default `imap.gmail.com`. Only Gmail was tried |

### Postgres

The code connects to `DATABASE_URL` and expects the server to be up and the database to exist. The loader creates
the tables and views on its first run. Two ways to have a server:

- **One that is already installed.** `createdb market_radar`; the default `DATABASE_URL` then works as it is. On
  macOS, Homebrew Postgres may refuse to start without a locale:
  `LC_ALL=en_US.UTF-8 pg_ctl -D <data directory> start`.
- **Docker.** `docker compose -f part1/docker-compose.yml up -d` starts Postgres 16 with the database already
  created, on `127.0.0.1:5433` so that it does not collide with a server on 5432. Put
  `DATABASE_URL=postgresql://postgres@localhost:5433/market_radar` in `.env`. The data stays in a Docker volume
  until `docker compose -f part1/docker-compose.yml down -v`.

### Apify

- The collectors call thirteen actors. All are billed per event: none needs a monthly rental, so a token whose
  account has usage available is enough.

  | Source | Actors |
  |---|---|
  | 2 TikTok ads | `fetch_cat/tiktok-ads-library-scraper` |
  | 3 Meta Ad Library | `apify/facebook-ads-scraper` |
  | 4 Amazon | `apt_marble/amazon-search-results-scraper`, `junglee/Amazon-crawler`, `delicious_zebu/amazon-reviews-scraper-with-advanced-filters` |
  | 5 retail shelf | `automation-lab/target-scraper`, `igview-owner/sephora-search-scraper`, `parseforge/chewy-com-scraper`, `apify/e-commerce-scraping-tool`, `automation-lab/chewy-product-reviews-scraper` |
  | 6 Google results | `apify/google-search-scraper` |
  | 8 TikTok posts | `clockworks/tiktok-scraper` |
  | 9 TikTok Shop | `lurkapi/tiktok-shop-scraper` |
  | 10 brand site (Black Rifle only) | `apify/e-commerce-scraping-tool` |

- **Cost.** One pass of all ten sources and five brands cost 7.05 USD (the latest run of each on 2026-11-11):
  Amazon 3.13, Meta 2.41, retail shelf 0.79, Google results 0.24, TikTok Shop 0.17, TikTok posts 0.13, brand site
  0.11, TikTok ads 0.07. The account's plan credit or monthly limit has to leave room for that; a run the account
  refuses to start is recorded as a failure of that step, not retried.
- **Runs at once.** At `--jobs` 16 a pass can have 31 actor runs going at the same time. The account used here
  allows 32. With a lower limit, lower `--jobs`.

### Network

Run it from a US IP address. Everything here was developed and run from one (a datacenter VPN). What is known
about other addresses:

- Source 10 checks which market each brand's site serves and records `not_us` instead of prices when it is not the
  US in USD.
- Sources 1, 3 and 7 put the US in the URL (`region=US`, `country=US`, `geo=US`). Source 1 behaved the same from a
  non-US address during research; the others were not tried from one.
- The Apify actors fetch from their own addresses.

### Accounts and the inbox

- **No site logins.** No collector signs in to a site; every page it opens is public.
- **Welcome emails (source 10) have two routes.** With `INBOX_ADDRESS` and `INBOX_APP_PASSWORD` set, the collector
  logs in to that mailbox over IMAP on every pass, read-only, takes the mail from the brands' sender addresses
  since each signup, removes what identifies the mailbox, and records it. Without them it reads the redacted
  `.eml` files in `collectors/10_brand_site_and_emails/inbox_export/`: the export of 2026-11-10, one email each
  for Living Proof, Death Wish Coffee and Black Rifle Coffee. A rerun without a mailbox therefore gives those
  three, and `could not look` for Batiste and Jinx.
- **The mailbox itself is set up by hand.** A dedicated inbox, a signup on each brand's site and a record of each
  signup: the procedure, with the form to use on each brand's site, is in
  `collectors/10_brand_site_and_emails/inbox_setup.md`. Nothing in the code signs up anywhere.
- **Only for checking records by hand:** an Amazon review link opens only when signed in to Amazon, and a TikTok ad
  detail link only with a TikTok Creative Center login. Neither is needed to run.

## Setup

From the repository root:

    python3 -m venv .venv
    .venv/bin/pip install -r part1/requirements.txt
    createdb market_radar       # or: docker compose -f part1/docker-compose.yml up -d  (see "Postgres")
    cp .env.example .env        # then fill in what you have

## One pass

    .venv/bin/python part1/run.py

It runs the collectors side by side, loads their files, asks a model for the angles of ad texts it has not seen, and
applies them. Running it again adds no duplicates.

**How long.** A pass of all ten sources and five brands took 7 minutes 8 seconds on 2026-11-11: 42 collector
processes, none failed. The slowest of each source: TikTok Shop 273 s, Amazon 253 s, the brand site 200 s, search
interest 171 s, Google ads 147 s, the retail shelf 125 s, Meta 109 s, Google results 79 s, TikTok posts 40 s. The
first pass of a day is longer: source 1 then loads every ad's detail page, about 12 seconds each (about 170 of
them on that day).

| Option | Meaning | Default |
|---|---|---|
| `--brand <slug>` | only this brand | all five |
| `--sources <list>` | only these collectors, by number or folder name: `1,5,10` | all ten |
| `--jobs <n>` | how many collector processes at once | 16 |
| `--timeout <minutes>` | stop a collector that runs longer | 60 |
| `--no-label` | skip the label step | |
| `--careful` | the slower pace: longer waits, and brands one after another on the sites we visit ourselves | |
| `--collectors-dir <path>` | where the collectors are | `part1/collectors` |

A cheap check: one brand, and two sources that cost nothing for it:

    .venv/bin/python part1/run.py --brand batiste --sources 1,10

### What runs side by side

Different collectors always do: they talk to different sites. Every collector also runs one process per brand,
except sources 1 and 7, whose sites limit requests per client and so take the brands one after another. A site can
therefore see several sessions at once (five on Meta's Ad Library, two on Ulta).

When a site objects, the collector stops there and records "could not look". Run that source again at the slower
pace: `--careful --sources 3` waits longer between requests and takes the brands one after another.

### What it prints

    collect <collector> <brand or all> exit=<code> <seconds>s        one line per collector process, as it ends
    collect: jobs=<n> failed=<n> runs=<n> ok=<n> partial=<n> could_not_look=<n> cost_usd=<sum>
    ...the loader's lines (see pipeline/README.md), ending in its `angles:` and `runs:` lines
    ...the label command's line

`exit=timeout` means the collector was stopped; `exit=1` that one of its brands hit an unexpected error (its run
result was still written); `exit=not_started` that the process could not be started; `exit=error` that `run.py`
itself failed while handling it. `cost_usd` is what the pass's Apify runs cost. Each collector's own output is in
`part1/logs/<start time>/<collector>.<brand or all>.log`.

The exit code is 0 when no collector process failed and the loader returned 0, 1 otherwise, 2 for a wrong option
value, 3 when another pass is still running, and 130 when the pass was interrupted (Ctrl-C, or the terminal or the
scheduler stopping it): it then stops what it started and loads nothing more. A collector that fails does not stop the pass: the others'
files are still loaded, and nothing is marked ended for a source that was not read completely.

### Did it work

Exit code 0 with `failed=0` on the `collect:` line and on the loader's `runs:` line means every collector process
ended and every file was loaded. It does not mean every source was read: each source and brand has its own status.
The latest one for each:

    psql market_radar -c "SELECT DISTINCT ON (source, brand) source, brand, status, reason, records, finished_at FROM runs WHERE result = 'applied' ORDER BY source, brand, run_id DESC"

That is fifty rows after a full pass.

| Status | Meaning |
|---|---|
| `ok` | Everything in scope was read. `ok` with no records means the source showed nothing, for example no TikTok ads for that brand |
| `partial` | Some of it was read; `reason` names what was not. Rows that were not looked at are not marked ended |
| `could_not_look` | Nothing could be read. The tables do not change for that source and brand |

| Reason, or what the pass printed | What to do |
|---|---|
| `missing_token` | Put `APIFY_TOKEN` in `.env` |
| `not_us(...)`, `market_unconfirmed` | The brand's site served another market, or its home page did not load. Run from a US IP address; run that source again |
| `blocked`, an HTTP 403 or 429 | The site refused. Run that source later at the slower pace, `--careful --sources <n>`. Nothing here works around a block |
| `emails: first_day_not_over`, `spam_not_checked`, `domain_not_searched(...)` | About the welcome emails read from the exported files; expected without a mailbox. See `collectors/10_brand_site_and_emails/inbox_setup.md` |
| `emails: imap_login_failed`, `imap_error: ...`, `imap_no_all_folder` | The mailbox could not be read with the credentials in `.env`. The exported files are not used in its place |
| `emails: eml_invalid=<n>` | That many messages could not be redacted safely or read, and were not stored. The others were |
| `exit=timeout` on a `collect` line | The process was stopped and wrote nothing. The next pass reads that source again; raise `--timeout` if it keeps happening |
| anything else | Each collector's `spec.md` lists its reasons, and its output is in `part1/logs/` |

For comparison, the state after the full pass of 2026-11-11, with a mailbox configured: 41 `ok`, 8 `partial`, 1
`could_not_look`. Not `ok` were TikTok Shop for all five brands (11 to 18 of 20 search results fetched, also on a
second try), and for Batiste the brand site (6 of 63 barcodes refused by the where-to-buy API), Google ads (one
script file not fetched), the retail shelf (one product's reviews) and TikTok ads (`could_not_look`). The tables
held 1,168 ads, 819 products, 1,427 reviews, 272 posts, 1,342 search rankings, 530 search-interest rows and 1,817
changes; most of the changes are between that pass and the one five hours before it.

## Every hour

`run.py` is what a scheduler calls; a second pass that starts while one is running exits at once.

    0 * * * * cd <repository> && mkdir -p part1/logs && .venv/bin/python part1/run.py >> part1/logs/cron.log 2>&1

- The schedule has to run inside a desktop session, because source 7 opens a browser window.
- Every pass costs what its Apify collectors cost; the `collect:` line prints the sum. A pass of everything cost
  7.05 USD on 2026-11-11, 3.13 USD of it source 4 (see "Apify"). Sources 1 and 7 cost nothing. Which sources run
  every hour and which once a day is a choice made with `--sources`, for example:

      0 * * * * cd <repository> && mkdir -p part1/logs && .venv/bin/python part1/run.py --sources 1,7 >> part1/logs/cron.log 2>&1
      30 6 * * * cd <repository> && mkdir -p part1/logs && .venv/bin/python part1/run.py --sources 2,3,4,5,6,8,9,10 >> part1/logs/cron.log 2>&1

## Brands

The five brands are in `collectors/brands.json` (name and slug). Each collector also has a `brand_inputs.json` of
its own with what it needs for each brand: page IDs, search terms, product listing addresses, sender domains.
Adding a brand means adding it to `brands.json` and to all ten `brand_inputs.json` files; each collector's `spec.md`
describes its fields and how the values were found.

## The filled tables

`part1/data/market_radar.sql.gz` is a dump of the tables after the full pass of 2026-11-11: the ten tables with
their rows and the three views. To look at it without running a collector:

    createdb market_radar
    gunzip -c part1/data/market_radar.sql.gz | psql -q -d market_radar

(With the compose file: `gunzip -c part1/data/market_radar.sql.gz | psql -q -d postgresql://postgres@localhost:5433/market_radar`.)
A pass run afterwards continues from it: rows are updated, and what is gone is marked ended.

The dump was made with

    pg_dump --no-owner --no-privileges -d postgresql://localhost:5432/market_radar | gzip -9 > part1/data/market_radar.sql.gz

and checked before it was committed: it restores into an empty database, and it holds no token, key, mailbox
address or local path, no reviewer names and no profile data of persons. The collectors' files (`collectors/*/raw/`, ignored by git) are the
other way: the loader rebuilds every table from them.

## Tests

No test contacts a live site or costs anything.

    .venv/bin/python -m unittest discover -s part1/tests                                    # run.py
    for d in part1/collectors/*/tests; do .venv/bin/python -m unittest discover -s "$d"; done   # the ten collectors
    createdb market_radar_test
    .venv/bin/python -m unittest discover -s part1/pipeline/tests                           # the loader; needs that database

The loader tests read `TEST_DATABASE_URL` (default `postgresql://localhost:5432/market_radar_test`).

## Where to look

- The tables and views, with example queries: `pipeline/README.md`.
- The filled tables: `data/market_radar.sql.gz` (see "The filled tables").
- The designs: `docs/superpowers/specs/` at the repository root.
