# Design: Market Radar tables and loader

Date: 2026-11-10. Status: waiting for the user's approval.

## 1. Intent
Ten raw collectors (`part1/collectors/<nn_name>/`) each write what one source shows for one brand at the moment they run. Nothing yet puts those files where a person can ask questions of them. This design adds the Postgres tables and the loader that fills them.

The loader is also where time enters. A collector takes no time range and remembers nothing; it is a snapshot. Running the collectors again and again (the target is hourly) must add what is new, change nothing that is the same, and mark what has disappeared as ended instead of deleting it. That comparison is done by the loader, against the tables.

## 2. Goals, non-goals, anti-goals
**Goals**
- One table per kind of thing, so that a row always means the same thing and questions are plain SQL.
- Loading is repeatable: loading the same run twice, or running collectors twice, creates no duplicates.
- An item that disappears is kept and gets `ended_at`. An item that comes back is reopened.
- A source or part of a source that could not be looked at is visible as such in the tables.
- Every row can be checked against the live site: it carries its source, its URL and the time it was fetched.

**Non-goals** (not built here)
- History of changed values (price over time). Tables hold the current value; history stays in the per-run raw files.
- Matching the same product across retailers.
- Reading text out of Google ad images.
- The scheduler and the single command that runs collectors and then the loader. They are designed after the end-goal discussion.
- Cross-source insights and the queries for them.

**Anti-goals** (failures even if everything runs)
- Marking an item ended because a run could not see everything.
- Dropping a record silently because it did not fit.
- Storing names of private individuals. Collectors already remove them; the loader adds none.

## 3. Constraints
1. Own code. No paid service is involved in loading.
2. Re-run safe. No duplicates; disappeared items are marked ended, never deleted.
3. Honest gaps. "Could not look" is recorded as that, never as "nothing found". Partial collection is marked.
4. Clean collection. No personal data of private individuals.
5. The target is a local Postgres, and the loader is one command that another person can run on their machine.
6. Each row keeps the URL and fetch time needed to compare it with the live site.
7. Per source and run, the request count, duration and cost stay available (they come from the run result).

## 4. Decided by the user (2026-11-10)
- Collectors stay as they are. Comparison with earlier state happens at load time.
- The result does not have to be one table (confirmed with BARO). Tables are split by nature: ads, product page, search, social post.
- Google search results (source 6) belong to search, together with search interest (source 7).
- Reviews are child rows of a product.
- Source 10's home-page offers, signup forms and welcome emails go into `ads`, marked as an owned channel rather than a paid one.
- An item is marked ended for being absent only by a run that was complete for that scope.
- The table list in section 6 and the six calls in section 11, which the designer proposed and the user accepted.
- `ads` has no paid flag; `channel` already tells paid media from owned channels.
- TikTok creator handles (`posts.creator_handle`) and TikTok Shop seller names (`products.seller_name`) are stored in their columns.
- Where a source gives an ad no dates (TikTok), the ad is followed by its ID alone: first seen, last seen and ended come from the runs.

## 5. Input
The loader reads only what the collector contract (`part1/collectors/README.md`) defines:
- `part1/collectors/<nn_name>/raw/<brand>/<run_id>.run.json`: the run result.
- `part1/collectors/<nn_name>/raw/<brand>/<run_id>.jsonl`: one record per line with `key`, `kind`, `url`, `fetched_at`, `raw`.

A run without a `.run.json` (a leftover `.jsonl.part`) is ignored. `source` is the `source` field of the run result.

## 6. Tables
Eight tables. Six hold items, two describe runs.

### 6.1 Columns every item table has
```sql
source        text        NOT NULL,  -- run result's "source"
brand         text        NOT NULL,  -- brand slug
kind          text        NOT NULL,  -- record kind
key           text        NOT NULL,  -- stable item key within source, brand and kind
scope         text        NOT NULL,  -- the part of a run this row belongs to (section 7.3)
url           text,                  -- where a person can check the item
fetched_at    timestamptz NOT NULL,  -- when the stored values were fetched
first_seen_at timestamptz NOT NULL,  -- start of the first run that contained the item
last_seen_at  timestamptz NOT NULL,  -- start of the latest run that contained the item
ended_at      timestamptz,           -- NULL while the item is present
last_run_id   text        NOT NULL,
raw           jsonb       NOT NULL,  -- the collector record's "raw", unchanged
PRIMARY KEY (source, brand, kind, key)
```

### 6.2 Item tables
| Table | One row is | Sources | Own columns |
|---|---|---|---|
| `ads` | one ad creative, or one message on a brand-owned channel | 1, 2, 3, 10 | `channel text NOT NULL`, `advertiser_id text`, `advertiser_name text`, `format text`, `headline text`, `body text`, `cta text`, `landing_url text`, `landing_domain text`, `started_at timestamptz`, `last_shown_at timestamptz`, `variation_count integer`, `placements text[]`, `offer_code text` |
| `products` | one product at one seller | 4, 5, 9, 10 | `retailer text NOT NULL`, `product_id text`, `title text`, `price numeric(12,2)`, `price_max numeric(12,2)`, `list_price numeric(12,2)`, `currency text`, `rating numeric(3,2)`, `review_count integer`, `rank integer`, `sponsored boolean`, `availability text`, `seller_name text`, `sold_count bigint` |
| `reviews` | one review of a product | 4, 5 | `product_key text NOT NULL` (the `key` of its `products` row, same source and brand), `rating numeric(3,2)`, `title text`, `body text`, `review_date date`, `verified boolean`, `helpful_votes integer` |
| `search_rankings` | one result line for one search term | 6 | `keyword text NOT NULL`, `keyword_rank integer`, `position integer`, `result_url text`, `domain text`, `title text`, `description text`, `result_type text` |
| `search_interest` | one week of one search term | 7 | `keyword text NOT NULL`, `series text NOT NULL` (`solo` or `compared`), `week_start date NOT NULL`, `value integer`, `has_data boolean`, `is_partial boolean`, `geo text` |
| `posts` | one social post | 8 | `post_id text`, `posted_at timestamptz`, `creator_handle text`, `creator_is_brand boolean`, `creator_followers bigint`, `views bigint`, `likes bigint`, `comments bigint`, `shares bigint`, `saves bigint`, `caption text`, `hashtags text[]`, `surfaced_by text[]` |

- `ads.channel` is one of `google`, `meta`, `tiktok` (paid media) or `site`, `signup_form`, `email` (the brand's own channels). There is no separate paid flag; the channel says it.
- `ads.started_at` and `ads.last_shown_at` hold only dates the source itself states. TikTok's rows carry no dates, so both stay NULL there. How long an ad has been seen is in `first_seen_at`, `last_seen_at` and `ended_at`, which come from the runs and which every row has; they are never copied into `started_at`.
- `products.retailer` is one of `amazon`, `ulta`, `target`, `sephora`, `chewy`, `tiktok_shop`, `own_site`; for Batiste's where-to-buy data it is the retailer name the widget returns, lower-cased, so the same retailer has the same value in every source.
- `products.availability` is `IN_STOCK`, `OUT_OF_STOCK` or NULL in every source. A source that gives a text (Amazon) is mapped by the words in it; a source that says nothing about stock leaves NULL.
- `products.rating` is NULL, not 0, when the source reports no reviews.
- `products.price` is the price as shown. When the seller shows a range (Ulta and Sephora show `$12.99 - $20.99` for a product with sizes), `price` is the lower end and `price_max` the upper end; otherwise `price_max` is NULL. `list_price` is the price before a discount, when the seller shows one.
- A column a source does not provide stays NULL. Values not given a column stay reachable in `raw`.

### 6.3 Run tables
```sql
CREATE TABLE runs (
  source text, brand text, run_id text,
  started_at timestamptz NOT NULL, finished_at timestamptz,
  status text NOT NULL,            -- ok | partial | could_not_look
  reason text NOT NULL,
  records integer, expected_total integer, requests integer, cost_usd numeric(10,4),
  extra jsonb,
  result text NOT NULL,            -- applied | superseded | empty_no_mapper (section 7.1)
  loaded_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (source, brand, run_id)
);
CREATE TABLE run_scopes (
  source text, brand text, run_id text, scope text,
  status text NOT NULL,            -- ok | partial | could_not_look
  reason text NOT NULL,
  PRIMARY KEY (source, brand, run_id, scope)
);
```
`run_scopes` is where a gap inside a run is visible: one retailer that could not be reached, or "who buys ads" for search terms, each as its own row with `could_not_look`.

## 7. Loading rules
### 7.1 Order and repeatability
- The loader finds every run result under `part1/collectors/*/raw/`, skips the ones already in `runs`, and loads the rest in ascending `(source, brand, run_id)`.
- Each run is loaded in one transaction: either all of it is in the tables or none of it.
- A run older than a run already applied for the same source and brand is written to `runs` with `result = 'superseded'` and changes no item table. Every other run that goes through a mapper gets `result = 'applied'`.
- When two records of one run give the same row key, the later record wins.
- A source without a mapper (section 8) is named in the output and its runs stay unloaded until the mapper exists. The exception is a run with no records: it needs no mapper and is recorded in `runs` (`result = 'empty_no_mapper'`) and `run_scopes` with the default scope, so a source that could not be looked at is visible in the tables from the start. Such a run does not count as applied when later runs are compared with it.
- A record that says its own item was not fetched (a per-item state such as `failed`, `not_attempted`, `missing` or `unavailable`) produces no row and does not count as seen. This is not an error. The loader prints how many such records a run had; the gap itself is in `run_scopes`.
- A record that claims to hold an item but lacks a value its mapper requires is an error: the run's transaction is rolled back, the error is printed with source, brand, run and key, and the loader goes on with the next run and exits with a failure code at the end.

### 7.2 Insert and update
For each row of the run, keyed by `(source, brand, kind, key)`:
- New key: insert with `first_seen_at = last_seen_at =` the run's `started_at`.
- Existing key: overwrite the columns the mapper returned, and `url`, `fetched_at`, `raw`, `scope`, `last_seen_at`, `last_run_id`; leave `first_seen_at`.
- A column the mapper leaves out of a row keeps its stored value; a column it returns as NULL is set to NULL. A mapper leaves out exactly the columns that come from a fetch that did not happen in this run (source 1's detail for ads last shown more than 7 days ago, a failed detail fetch), so values fetched earlier are not lost. `raw` is always the latest record.
- In both cases `ended_at` is set by the row's policy (section 7.4): NULL under `absent` and `never`, computed under `source_date`.

### 7.3 Scopes
A scope is the part of a run whose completeness is known on its own. A mapper returns, for a run, its rows (each with a scope) and a list of `(scope, status, reason)`, which is written to `run_scopes`.
- Default: one scope named `all`, with the run's own status and reason.
- Sources whose run result reports parts use them: source 5's retailer cells (`extra.cells`), source 10's `prices`, `offers_home`, `offers_klaviyo` and `emails` (`extra.parts`; the home page and the form list are reported separately, so a blocked home page does not stop forms from ending).
- A scope may be as small as one search term or one barcode when the records tell whether that piece was fetched completely. Source 6 uses one scope per search term, plus `ads`. Batiste's where-to-buy data uses one scope per barcode instead of `prices`. Otherwise one failed piece would keep every other row of the source from ever ending.
- A scope can cover other scopes. When the pieces of a source are themselves a list that can change (Batiste's barcodes come from its product pages), the mapper also returns one scope for that list, with `covers` set to the name prefix of the pieces (`wtb/`). It is `ok` only when the list itself was read completely. It has no rows of its own; it says "these are all the pieces there are" (section 7.4).
- Source 3 uses one scope per Facebook page, from the per-page state the collector writes in the run result.
- Each source's mapping plan names its scopes.

### 7.4 Ending
Each `(table, kind)` has one policy:

| Policy | Rule | Applies to |
|---|---|---|
| `absent` | For every scope of the run whose status is `ok`: rows of that source, brand and scope whose `last_run_id` is not this run and whose `ended_at` is NULL get `ended_at =` the run's `started_at` | `ads` from sources 2, 3 and source 10's `offer_slot`, `klaviyo_form`; all `products`; `search_rankings` |
| `source_date` | For rows written by this run, whatever the status of the run or scope: `ended_at = last_shown_at` when `last_shown_at` is more than 3 days before the run's `started_at`, otherwise NULL | `ads` from source 1, whose list keeps creatives that stopped months ago |
| `never` | `ended_at` is never set | `reviews`, `search_interest`, `posts`, `ads` of kind `email` |

A covering scope extends the `absent` rule to pieces that are no longer looked at: when a scope with `covers` set is `ok`, rows of an `absent` kind with that source and brand whose `scope` starts with the `covers` prefix, whose `scope` is not the name of any scope of this run, and whose `ended_at` is NULL, get `ended_at =` the run's `started_at`. A piece that is in the run keeps following its own scope's status, so a barcode that was not attempted ends nothing.

A scope with status `partial` or `could_not_look` ends nothing by absence. A run whose `reason` starts with `exception:` (the collector stopped on an unexpected error) ends nothing by absence either: its record file may be cut short, so the loader records its `ok` scopes as `partial` with that reason. `source_date` does not depend on absence: the item is in the run, and the source itself says when it was last shown. For sources that collect a top-N list (sources 4, 5, the search part of 9), `ended_at` means "no longer in the collected list", not "no longer sold".

## 8. From records to rows
One mapper per source: a pure function from a run result and its records to rows and scopes. It decides the table, the row key, the scope and the column values. Exact raw paths are in the last section of each `part1/collectors/<nn_name>/spec.md` ("Where the pipeline finds each value"); each mapper is written from that section in its own small plan.

| Source | Record kinds | Table | Row key | Notes |
|---|---|---|---|---|
| 1 Google Ads Transparency | `ad` | `ads` | record key | `channel` google. `headline`, `body` NULL (text arrives only as images). `variation_count` only when the detail was fetched |
| 2 TikTok Ad Library | `ad` | `ads` | record key | `channel` tiktok, `format` video, `body` from the ad text |
| 3 Meta Ad Library | `ad` | `ads` | record key | `channel` meta, `advertiser_*` from the page, `variation_count` from the creative group. `headline`, `body`, `cta` and `landing_url` come from the ad itself, and when it has none, from the first of its cards that has one. One scope per Facebook page: `ok` when that page's ad list is complete, whatever happened on the brand's other pages or to media downloads |
| 4 Amazon | `product`, `review` | `products`, `reviews` | record key | `retailer` amazon |
| 5 Retail shelf | `product`, `review` | `products`, `reviews` | record key | `retailer` from the cell; scope per cell |
| 6 Google results | `search_results_page` | `search_rankings` | record key + result URL without tracking parameter | one record becomes one row per organic result; first occurrence wins when a URL repeats; one scope per search term |
| 7 Search interest | `interest_point`, `interest_point_compared` | `search_interest` | record key | `series` from the kind |
| 8 TikTok posts | `post` | `posts` | post id | The record key is `<path>/<post id>`. A post found by both paths is one row; `surfaced_by` lists the paths; `raw` is the record of the first path in the order `profile_popular`, `hashtag` |
| 9 TikTok Shop | `product`, `search_result` | `products` | record key | `retailer` tiktok_shop; the two kinds stay separate rows. A tracked product the source answers as `unavailable` gives no row and leaves the tracked scope complete, so that product's row is ended. A tracked product the actor returned no row for (`missing`), or failed on, makes the scope `partial`, so nothing is ended |
| 10 Brand site and emails | `product` | `products` | record key | `retailer` own_site; one row per product, price of the first variant. `list_price` only when the compare-at price is above the price (Shopify writes 0.00 for "none"). `availability` is `IN_STOCK` when any variant can be bought |
| | `retailer_availability` | `products` | record key + retailer id | one record (one barcode) becomes one row per retailer returned; one scope per barcode, plus the covering scope `wtb_listing` (`covers` `wtb/`), which is `ok` when the listing and every product page were read, so the rows of a barcode that left the site are ended |
| | `offer_slot`, `klaviyo_form`, `email` | `ads` | record key | `channel` site, signup_form, email |

## 9. Running it
```
python part1/pipeline/load.py
```
- Creates the tables when they do not exist (`part1/pipeline/schema.sql`), then loads every run not yet loaded, then prints one line per run: source, brand, run, status, rows inserted, updated, ended.
- Connection: `DATABASE_URL` from the environment or the repository's `.env`; default `postgresql://localhost:5432/market_radar`. `.env.example` documents it.
- Python with `psycopg` 3, listed in `part1/pipeline/requirements.txt`. Postgres 16 is installed on the development machine through Homebrew and is not running by default.
- `--collectors-dir <path>` reads run files from another place; the default is `part1/collectors` of the repository the script is in.
- Exit code 0 when every run loaded or was already loaded, 1 when any run failed.

## 10. Tests and done-when
Tests run against a real Postgres (`TEST_DATABASE_URL`), with small hand-written run files, and cover the rules rather than the sources:
1. First run: rows inserted, `first_seen_at = last_seen_at`, `ended_at` NULL.
2. Same run loaded again: no row and no timestamp changes.
3. A later `ok` run without one item and with one new item: the missing one gets `ended_at`, the new one is inserted, the rest get a new `last_seen_at`.
4. A later `partial` run without several items: nothing is ended.
5. An ended item appears again: `ended_at` is NULL again, `first_seen_at` unchanged.
6. A `could_not_look` run: rows in `runs` and `run_scopes`, no item change.
7. An older run loaded after a newer one: `result` is `superseded`, no item change.
8. A `never` kind absent from an `ok` run: not ended.
9. Two scopes in one run, one `ok` and one not: only the `ok` scope ends its missing rows.
10. `source_date`: a row last shown more than 3 days before the run is ended at its `last_shown_at`; a newer one is not; the same holds in a `partial` run.
11. A record the mapper rejects: that run leaves no rows, the next run still loads, exit code 1.
12. A record marked as not fetched: no row and no error; a stored row for that key keeps its values and is not ended while its scope is not `ok`.
13. A column the mapper leaves out keeps its stored value; a column returned as NULL becomes NULL.
14. A run with no records from a source without a mapper: recorded in `runs` with `result` `empty_no_mapper`, and in `run_scopes`.

Each mapper has its own tests against the collector's sample files.

Done when: the tests pass; loading the runs on disk gives item counts equal to the records of the applied runs (after the one-to-many cases of section 8); a second load prints no changes.

## 11. Calls made by the designer
Proposed by the designer and accepted by the user on 2026-11-10:
1. No history of changed values in the tables.
2. The record's `raw` is stored in a `raw` column.
3. A Shopify product is one row; its price is the first variant's.
4. Google ads have no text columns filled.
5. Google's ended threshold is 3 days after `last_shown_at`.
6. Products that leave a top-N list are ended.

Made by the designer while writing this document, not yet seen by the user:
7. `run_scopes` as a table of its own, so gaps inside a run can be queried.
8. `kind` and `scope` columns on every item table; `kind` is part of the primary key.
9. `first_seen_at`, `last_seen_at` and `ended_at` use run start times; `fetched_at` is the record's own time.
10. Under `source_date`, `ended_at` is the ad's `last_shown_at`, not the run time.
11. A run older than one already applied is recorded and not applied.
12. An unmappable record fails its whole run instead of being skipped.
13. Python with `psycopg` 3, plain SQL schema file, `DATABASE_URL`.

Made by the designer after a reviewer read this document as the builder, not yet seen by the user:
14. A record that says its item was not fetched gives no row and is not an error.
15. A column the mapper leaves out keeps its stored value, so a skipped or failed detail fetch does not erase earlier values.
16. `source_date` applies in every run, complete or not.
17. A run with no records is recorded even when its source has no mapper yet.
18. A scope can be one search term or one barcode.
19. A post is one row even when two paths surfaced it; `posts` has no rank column.

Made by the designer while writing the first plan, from the real records, not yet seen by the user:
20. `products.price_max`, because Ulta and Sephora show a price range for products with sizes.
21. `runs.result` (`applied`, `superseded`, `empty_no_mapper`) instead of a yes/no flag.
22. When one run has two records with the same row key, the later one wins.
23. `--collectors-dir`, so the loader can read run files from another checkout.

Made by the designer while the remaining mappers were built and reviewed, not yet seen by the user:
24. A run that stopped on an exception ends nothing by absence, whatever its parts report.
25. For TikTok Shop only `unavailable` ends a tracked product; a product the actor returned no row for does not.
26. Meta ad text falls back to the first card that has a value.
27. A Google result page with no organic results is recorded as "could not look", not as "nothing ranks".
28. A product whose detail page was not fetched (Amazon) gets a row from what the list gave, with the detail columns left empty until a run fetches them.
29. One vocabulary for `availability` and lower-cased retailer names, so a query across sources does not miss one of them.
30. No rating is stored for a product with no reviews.
31. Own-site products: a list price only when it is above the price; in stock when any variant is.
32. The barcode widget shows a retailer's online price and its store prices; the online one is stored.

Asked for by the user on 2026-11-10 ("fix both"), with the mechanism chosen by the designer:
33. Covering scopes, so the retailer rows of a Batiste barcode that left the site are ended.
34. One scope per Facebook page, with the Meta collector writing each page's state into its run result, so one unreadable page does not hold back the other page's ads.

## 13. Known limits
- An ad that disappears from Google's list without a newer last-shown date is not ended; only the date ends Google ads.
- Review dates from Ulta are UTC dates and can differ by one day from the date the site shows.
- `posts.creator_handle` and TikTok Shop's `seller_name` hold account and shop names as published, and some belong to individuals. The user decided on 2026-11-10 that they are kept: the brief asks for the creator of each top post. Display names, avatars and locations are still not stored.

## 12. Left to the builder
- Module layout inside `part1/pipeline/`, and how mappers are registered.
- Index choices beyond the primary keys.
- How tests create and clean their database objects.
- Build order: the schema and loader core first, together with the mapper for source 5 (it exercises two tables, scopes and two ending policies); then one small plan per remaining source.
