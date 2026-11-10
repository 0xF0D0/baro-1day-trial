# Remaining Mappers Implementation Plan

> **For agentic workers:** each source below is one independent task: one mapper module and one test module. Tasks touch no shared file, so they can be built side by side. The controller registers the mappers and commits.

**Goal:** Add the nine mappers that turn the remaining collectors' runs into table rows, so every table of the design is filled by the existing loader.

**Architecture:** One pure module per source in `part1/pipeline/mappers/`, with the same interface as `mappers/retail_shelf.py`: `SOURCE`, `ENDING`, `map_run(run, records) -> MappedRun`. No SQL, no database, no network, no change to the loader.

**Tech Stack:** Python standard library, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-10-market-radar-tables-design.md` (sections 6.2, 7.1 to 7.4 and 8). For each source, its collector spec `part1/collectors/<nn_name>/spec.md`: the Output section defines the records and the run result; the last section ("Where the pipeline finds each value") names where each value is.

## Global Constraints
- Own code, standard library only in a mapper. No retries.
- Honest gaps. A record that says its item was not fetched gives no row and is counted in `not_fetched`. It is never an error and never a row with empty values.
- No names or profiles of private individuals are added to any column.
- Do not guess. A column is filled only from the place the collector spec's last section names for that attribute, or by a rule stated in this plan or in the design. A column with no stated source is `None`. If the spec is unclear or contradicts the samples, stop and report.
- An input the spec does not describe (unknown kind, a value that cannot be converted) raises `MapError` whose message starts with the record key.
- Every row's `scope` is the name of a scope the mapper returns. A mapper always returns at least one scope. Scope statuses are `ok`, `partial` or `could_not_look`.
- Scopes: when the collector's run result reports parts with their own state, one scope per part with that part's status and reason. Otherwise one scope named `all` with the run's `status` and `reason`.
- `Row.url`, `Row.fetched_at` and `Row.raw` are the record's own values. When one record becomes several rows, each row carries that record's `raw`.
- Times are timezone-aware UTC `datetime` values or ISO 8601 strings; dates are `datetime.date`; prices and product ratings are `Decimal` with 2 places.
- A mapper returns every column it can fill on every row. It leaves a column out (so the stored value is kept) only where this plan says so.
- Code and comments in English. Nothing under `part1/collectors/` and nothing else under `part1/pipeline/` is changed.

## Per source

| Source folder | `SOURCE` | Record kind -> table, row kind | Ending | Row key | Rules |
|---|---|---|---|---|---|
| `01_google_ads_transparency` | `google_ads_transparency` | `ad` -> `ads`, `ad` | `source_date` | record key | `channel` `google`. `format`: 1 `text`, 2 `image`, 3 `video`. `started_at`, `last_shown_at` from the list item's first and last shown times. `landing_domain` from the list item. `advertiser_name` as stored (already null for advertisers that are not the brand's own). `variation_count` is the number of variations in the detail when `raw.detail_state` is `fetched`; in every other state the column is left out. `headline`, `body`, `cta`, `landing_url`, `placements`, `offer_code` are `None` |
| `02_tiktok_ad_library` | `tiktok_ads` | `ad` -> `ads`, `ad` | `absent` | record key | `channel` `tiktok`, `format` `video`, `body` the ad text, `advertiser_name` the brand name as the source gives it. `started_at`, `last_shown_at` are `None` (the source gives no dates) |
| `03_meta_ad_library` | as in its collector | `ad` -> `ads`, `ad` | `absent` | record key | `channel` `meta`. `advertiser_id`, `advertiser_name` from the page. `format` lower-cased. `headline`, `body`, `cta`, `landing_url` from the snapshot; `landing_domain` is the host of `landing_url` without `www.`. `started_at` from the start date. `variation_count` from the creative group count. `placements` from the publisher platforms |
| `04_amazon` | `amazon` | `product` -> `products`, `product`; `review` -> `reviews`, `review` | `absent`; `never` | record key | `retailer` `amazon`. `product_id` is the ASIN. `rank` is the product's rank in the run. `sold_count` is `None` (the source gives a text, which stays in `raw`). A product whose detail was not fetched still gives a row from what the record holds; its detail columns are left out |
| `06_google_results` | `google_results` | `search_results_page` -> `search_rankings`, `search_result` | `absent` | record key + `\|` + result URL without the `srsltid` parameter | One record (one search term) becomes one row per organic result; the first occurrence wins when a URL repeats. `keyword_rank` is the term's rank among the brand's terms. `result_url` is the result's own URL; `Row.url` stays the record's. One scope per search term, named by the record key, plus one scope `ads` with status `could_not_look`. A record whose page was not fetched gives no rows and a scope that is not `ok` |
| `07_search_interest` | `search_interest` | `interest_point`, `interest_point_compared` -> `search_interest`, same kinds | `never` | record key | `series` is `solo` or `compared` by kind. `week_start` is the UTC date of the point's time |
| `08_tiktok_posts` | `tiktok_posts` | `post` -> `posts`, `post` | `never` | post id (the record key after the first `/`) | A post found by both paths is one row: `surfaced_by` lists the paths in the order `profile_popular`, `hashtag`, and the row's `raw`, `url` and `fetched_at` come from the record of the first of those paths. `creator_is_brand` as the spec's last section defines it (the brand's profile is in `brand_inputs.json` of the collector folder; read it at import time) |
| `09_tiktok_shop` | `tiktok_shop` | `product`, `search_result` -> `products`, same kinds | `absent` | record key | `retailer` `tiktok_shop`. `rank` only for `search_result`. A tracked product the source reports as missing or unavailable gives no row and counts as not fetched; its scope keeps the status the run result gives it |
| `10_brand_site_and_emails` | `brand_site_and_emails` | `product` -> `products`, `product`; `retailer_availability` -> `products`, `retailer_availability`; `offer_slot`, `klaviyo_form`, `email` -> `ads`, same kinds | `absent`, except `email`: `never` | record key; for `retailer_availability`, record key + `/` + the retailer's id | `product`: `retailer` `own_site`, one row per product, `price`, `list_price` and `availability` from the first variant. `retailer_availability`: one record (one barcode) becomes one row per retailer the widget returns, `retailer` is that retailer's name, `product_id` the barcode; one scope per barcode, named by the record key, `ok` only when that record's own state says it was fetched. `offer_slot`: `channel` `site`, `body` the slot's text. `klaviyo_form`: `channel` `signup_form`, `headline` the form name. `email`: `channel` `email`, `headline` the subject, `started_at` the sent time, `advertiser_name` the sender's display name, `body` the plain-text part. `offer_code` is `None` unless the collector spec states an exact extraction rule. Other scopes follow the run result's parts |

## Each task
- [ ] Read the design sections above, `part1/pipeline/model.py`, `part1/pipeline/mappers/retail_shelf.py` and its test as the pattern, and the source's collector spec (Output section and last section) and samples.
- [ ] Write `part1/pipeline/tests/test_<SOURCE>.py` first: for every record kind, at least one record shaped exactly as the collector spec's Output section says, built from the committed sample files, with the full expected `columns` dict written out; the scopes for a complete and an incomplete run; a not-fetched record where the source has that state; an unknown kind and an unconvertible value raising `MapError` that starts with the key. Plain `unittest.TestCase`, `import support` first.
- [ ] Run it and see it fail.
- [ ] Write `part1/pipeline/mappers/<SOURCE>.py`.
- [ ] Run only this test module until it passes. Do not run `load.py`. Do not commit.
- [ ] Report every column with the place its value comes from, and every point where the spec left a choice.
