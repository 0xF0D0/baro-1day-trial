# Market Radar: a pass in minutes

Date: 2026-11-11. Changes `2026-11-11-run-all-design.md` (section 3 and the `--jobs` default) and the waits of five
collectors. Everything else in those documents stands.

## 1. Intent

A pass of all ten sources and five brands takes about 35 minutes, set by its slowest collector. The Apify-only
collectors take 20 seconds to 5 minutes; the aim is for every source to be in that range, so that a pass is a matter
of minutes.

Measured on 2026-11-11 from the run files, per five brands:

| Source | Now | Where the time goes |
|---|---|---|
| 1 Google Ads Transparency | about 35 min | one page per ad detail with 10 s between them; brands one after another |
| 10 brand site | about 14 min | Batiste: 98 requests 4 s apart; brands one after another |
| 5 retail shelf | about 13 min | brands one after another; waits on Apify runs |
| 3 Meta Ad Library | 15 to 25 min (estimate) | brands one after another; 15 s between page loads; waits on Apify runs |
| 4 Amazon | about 5 min | three Apify runs in a row, each followed by a 30 s wait to read its settled cost |
| labeling | 2.7 s per text | one request at a time |

Nearly all of it is waiting we chose, not work.

## 2. What changes

### 2.1 Brands side by side

`run.py` starts one process per brand for every collector except `07_search_interest`, which keeps one job for all
brands: its source limits requests hard and it opens a visible window. The constant becomes
`BRAND_SEQUENTIAL = ("07_search_interest",)`. The default of `--jobs` becomes 16.

This means several sessions on one site at once: five on Google's Ads Transparency Center, five on Meta's Ad
Library, two on Ulta. Each brand of source 10 has its own site. The user decided this on 2026-11-11, knowing that
Meta has shown a block page before.

### 2.2 Shorter waits

| Collector | Constant | Before | After |
|---|---|---|---|
| `01_google_ads_transparency` | `DETAIL_SPACING_S` | 10 | 2 |
| `03_meta_ad_library` | `SITE_SPACING_S` | 15 | 5 |
| `05_retail_shelf` | `ULTA_SPACING_S` | 3 | 2 |
| `05_retail_shelf` | `APIFY_POLL_S` | 10 | 3 |
| `10_brand_site_and_emails` | `SPACING_S` | 4 | 2 |
| `04_amazon` | `POLL_S` | 10 | 3 |

Inside one process a collector still sends its own requests one at a time, with the spacing above.

`04_amazon` reads the settled cost of its runs once, at the end of the brand: it waits until `CHARGE_READ_DELAY_S`
after the last run's `finishedAt` and then reads each run once, instead of waiting after every run. The cost it
reports is the same.

### 2.3 Careful mode

The old pace stays available, as the way back when a site objects.

- A collector started with the environment variable `RADAR_CAREFUL` set to a non-empty value uses the "Before" values
  of the four site-facing constants (`DETAIL_SPACING_S`, `SITE_SPACING_S`, `ULTA_SPACING_S`, `SPACING_S`). The two
  Apify poll intervals are not affected: they do not touch a source site.
- `run.py --careful` sets `RADAR_CAREFUL=1` for the collectors it starts and plans the jobs the old way: one job per
  brand only for `02_tiktok_ad_library`, `04_amazon`, `06_google_results`, `08_tiktok_posts`, `09_tiktok_shop`, and one
  `--all` job for every other collector.

`--careful` can be combined with `--sources`, so only the source that was blocked needs to slow down.

### 2.4 Labels eight at a time

`angles.py --label` sends the requests for pending texts up to `LABEL_WORKERS` (8) at a time. Lines are appended in
the order of the pending list, one at a time, by the calling thread. A request the API rejects (HTTP 400) or an
authentication error still stops the run: requests already answered before it in the list are written, nothing after.

The default model stays `claude-opus-5-5`. On 12 texts the cheaper model took the same time per request and agreed
less with the reviewed labels on the message kind (31 of 36 values against 34 of 36).

## 3. When a site blocks

What exists, and stays: a collector that meets a block page, a CAPTCHA or a login wall stops there and records
"could not look" with the reason; nothing is marked ended for that source; the pass goes on.

What this adds: the way back, `--careful`, by hand.

What is not built here, in the order it should be:
1. Asking for less. Most of source 1's requests re-read ad details it already has; reading only ads not seen before
   would cut its requests by an order of magnitude and matters more than any spacing.
2. Backing off by itself: after a block, run that source carefully on the next passes and leave it out for some hours
   if it is blocked again.
3. A second route for a source whose site keeps refusing: an Apify actor, as five sources already use.

What is not done at all: hiding from the site's detection (rotating addresses or proxies, altering the browser's
fingerprint, solving CAPTCHAs). Being refused is recorded, not worked around.

## 4. Goals, non-goals

Goals
- A full pass in about 5 minutes, bounded by the Apify runs of source 4.
- The old pace is one option away.
- Nothing about what is collected or how it is recorded changes.

Non-goals
- The three items of section 3 that are "not built here".
- Speeding up `07_search_interest`, `02`, `06`, `08`, `09`: they already take under 3 minutes.

## 5. Constraints carried over

1. Hand-written code; at least one source without a paid scraping service.
2. Rerun-safe: no duplicates on a second run; a missing item is marked ended, never deleted.
3. Honest gaps: "could not look" is never recorded as "nothing found"; partial collection is marked.
4. Clean collection: no personal data of private individuals; requests are spaced; a block is not worked around.
5. Local Postgres, one command, reproducible by someone else.

## 6. Calls made by the designer

1. One environment variable for the careful pace instead of an option on every collector: the collectors' command
   line stays as it is.
2. `07_search_interest` is never run per brand.
3. Careful mode restores the spacing and the one-session-per-site rule together.
4. The default label model is not changed.
5. Label lines keep the order of the pending list, so a rerun writes the same file.

## 7. What is measured afterwards

One real pass of the four site-facing collectors for all five brands (`--sources 1,3,5,10`): the seconds per job, any
block, and the statuses, against the table in section 1. It also fills what is missing in the tables today (Meta for
three brands, the shelf for Jinx).
