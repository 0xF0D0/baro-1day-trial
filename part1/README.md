# Market Radar

Give it brands; it looks at ten sources (ads, shelf, search, social) and keeps what it finds in a local Postgres:
what each competitor is doing, since when, whether it stopped, and what the agents read on top of that.

| Part | What it does | Details |
|---|---|---|
| `collectors/` | ten collectors, one per source; each writes what the source shows right now to files | `collectors/README.md` |
| `pipeline/` | loads those files into tables, marks what ended, records what changed, applies the ad angles, defines the views | `pipeline/README.md` |
| `run.py` | one command that does a whole pass | this page |

## Prerequisites

What a machine needs before the first pass. Nothing here is started or installed by `run.py`.

| Needed | Used by | Without it |
|---|---|---|
| Python 3.10 or newer (developed on 3.14) | everything | nothing runs |
| A PostgreSQL server that is already running (developed on 16, local) and a database in it | the loader and the tables | the collectors still write their files; nothing is loaded |
| Google Chrome, installed | sources 1, 3, 5, 7 and 10, through Playwright with `channel="chrome"`. No Playwright browser download is needed | those sources fail |
| A desktop session | source 7 opens a visible Chrome window | source 7 fails |
| An Apify account with usage available, and its API token | sources 2, 3, 4, 6, 8, 9 and parts of 5 and 10 | each of those records "could not look" (`missing_token`); the rest runs |
| An Anthropic API key (optional) | labeling the angles of ad texts not seen before | new texts stay `not_labeled`; the labels already in the repository still apply |
| A US IP address | see "Network" | see "Network" |

No collector logs in anywhere, and none needs an email account: see "Accounts and the inbox".

### `.env`

Three lines, in `.env` at the repository root (`.env.example` is the template; `.env` is ignored by git):

| Key | Needed | Notes |
|---|---|---|
| `APIFY_TOKEN` | for the Apify sources | Must be in the file: most collectors read the file, not the environment |
| `ANTHROPIC_API_KEY` | no | Environment variable or the file |
| `DATABASE_URL` | no | Default `postgresql://localhost:5432/market_radar`. Set it for another host, port, user or database. An environment variable of the same name wins over the file |

### Postgres

The code connects to `DATABASE_URL` and expects the server to be up and the database to exist (`createdb
market_radar`). The loader creates the tables and views on its first run. On macOS, Homebrew Postgres may refuse to
start without a locale: `LC_ALL=en_US.UTF-8 pg_ctl -D <data directory> start`.

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

- **Cost.** One pass of all ten sources and five brands cost 7.33 USD (the latest run of each on 2026-11-11):
  Amazon 3.12, Meta 2.41, retail shelf 0.78, TikTok posts 0.34, Google results 0.25, TikTok Shop 0.24, brand site
  0.12, TikTok ads 0.07. The account's plan credit or monthly limit has to leave room for that; a run the account
  refuses to start is recorded as a failure of that step, not retried.
- **Runs at once.** At `--jobs` 16 a pass can have 31 actor runs going at the same time. The account used here
  allows 32. With a lower limit, lower `--jobs`.

### Network

Everything here was developed and run from a US IP address (a datacenter VPN). What is known about other addresses:

- Source 10 checks which market each brand's site serves and records `not_us` instead of prices when it is not the
  US in USD.
- Sources 1, 3 and 7 put the US in the URL (`region=US`, `country=US`, `geo=US`). Source 1 behaved the same from a
  non-US address during research; the others were not tried from one.
- The Apify actors fetch from their own addresses.

### Accounts and the inbox

- **No logins.** No collector signs in anywhere; every page it opens is public.
- **Welcome emails (source 10) come from files, not from an inbox.** The collector reads the redacted `.eml` files
  in `collectors/10_brand_site_and_emails/inbox_export/` and never connects to a mailbox. The repository holds the
  export of 2026-11-10: one email each for Living Proof, Death Wish Coffee and Black Rifle Coffee. A rerun reads
  these same files, so it needs no email account.
- **Adding newer mail is a manual step outside the pass.** It needs an inbox that is signed up to the brands' lists
  (the signups are recorded in `data/email_signups.json`) and the export procedure in section 12 of that
  collector's `source_info.md`: the mailbox is read by hand, each message is redacted with `tools/redact_eml.py`
  and the result is checked with `tools/verify_eml.py`. Batiste and Jinx have no exported mail: their emails are
  recorded as `not_signed_up`.
- **Only for checking records by hand:** an Amazon review link opens only when signed in to Amazon, and a TikTok ad
  detail link only with a TikTok Creative Center login. Neither is needed to run.

## Setup

From the repository root:

    python3 -m venv .venv
    .venv/bin/pip install -r part1/requirements.txt
    createdb market_radar
    cp .env.example .env        # then fill in what you have

## One pass

    .venv/bin/python part1/run.py

It runs the collectors side by side, loads their files, asks a model for the angles of ad texts it has not seen, and
applies them. Running it again adds no duplicates.

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

## Every hour

`run.py` is what a scheduler calls; a second pass that starts while one is running exits at once.

    0 * * * * cd <repository> && mkdir -p part1/logs && .venv/bin/python part1/run.py >> part1/logs/cron.log 2>&1

- The schedule has to run inside a desktop session, because source 7 opens a browser window.
- Every pass costs what its Apify collectors cost; the `collect:` line prints the sum. The runs of 2026-11-11 cost
  5.28 USD (without source 3 for three brands and source 5 for one), 3.12 USD of it source 4. Sources 1 and 7 cost
  nothing. Which sources run every hour and which once a day is a choice made with `--sources`, for example:

      0 * * * * cd <repository> && mkdir -p part1/logs && .venv/bin/python part1/run.py --sources 1,7 >> part1/logs/cron.log 2>&1
      30 6 * * * cd <repository> && mkdir -p part1/logs && .venv/bin/python part1/run.py --sources 2,3,4,5,6,8,9,10 >> part1/logs/cron.log 2>&1

## Where to look

- The tables and views, with example queries: `pipeline/README.md`.
- The designs: `docs/superpowers/specs/` at the repository root.
