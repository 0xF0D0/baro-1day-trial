# Spec: source 9, TikTok Shop raw collector

> **Implementation note (2026-11-10).** `source_collector.py` follows this spec under the shared contract's "Keep it small" rule, with these differences: no GET retries (every request is sent once); the cost is read once, 15 s after the dataset, and reported as `cost_final` instead of `cost_settled`; no shape-change side file; `brand_inputs.json` is not validated; a credit refusal is recorded as `apify_credit_exhausted: …`; the run result's `extra` uses `data_provider` and `verified_against_site: false`. Where the code and this note differ from the sections below, the code and this note win.

- Shared contract: `part1/collectors/README.md`. This document adds what is specific to this source.
- Research notes: `part1/collectors/09_tiktok_shop/source_info.md`. Where that document and this spec differ (shop input, `sellerIsOfficial`, collection scope), this spec is newer and wins.
- Every fact in section 2 was observed on 2026-11-10, either in a response saved under `part1/collectors/09_tiktok_shop/samples/` or, for F7, in the Apify API document named in that row. Nothing in this spec is an assumption.

## 0. Rule for the implementer
**Do not guess.** If the Apify API or the actor behaves in a way this spec does not describe, or a step needs a value or a choice this spec does not give, stop and report (section 9). Do not add a fallback, a retry, a default or an alternative method that is not written here. In particular, do not switch to another actor, another build, another input type (shop IDs, shop URLs, categories, hashtags) or direct requests to TikTok.

## 1. What to build
Given a brand, the collector starts two runs of the paid Apify actor `lurkapi/tiktok-shop-scraper` and writes one record per tracked product and one per search result:
1. **Tracked products.** A fixed list of TikTok Shop product IDs per brand (section 3), fetched by ID on every run. This gives the same set of items in every run, so the pipeline can follow price and sales count over time and see when a product becomes unavailable.
2. **Search.** The top `SEARCH_LIMIT` (20) results of the TikTok Shop search for the brand's search term, as ranked by TikTok at that moment.

The brief asks this source for "listings, prices and sales counts". The collector does not extract those values. It stores the rows the actor returns so they can be extracted later.

The collector **never requests TikTok itself.** TikTok Shop shows a slider puzzle to a logged-out browser (F1), and the collector does not solve, drag, or work around puzzles, and does not log in. All TikTok data comes from the actor. How the actor gets past TikTok's puzzle is not published; its README (`samples/apify/actor_readme.md`) says it solves a captcha for category inputs, which this collector does not use.

The values were **not checked against the live TikTok Shop page**, because the puzzle blocks the page (F1, F2). Every run result says so (`extra.values_checked_against_site: false`).

Out of scope: a brand shop's full catalogue (the actor returns 0 products for shop inputs, F13), extracting or comparing values, deciding which seller is the brand, deciding which products ended, adding new IDs to the tracked list, writing to the database.

## 2. Verified facts about the source
Sample paths are relative to `part1/collectors/09_tiktok_shop/samples/`.

| # | Fact | Evidence |
|---|---|---|
| F1 | `https://www.tiktok.com/shop/s/death-wish-coffee` and `https://shop.tiktok.com/` (→ `/us`) show "Verify to continue: Drag the puzzle piece into place" to a logged-out Chrome on a US IP. The page's listing request `/api/shop/brandy_desktop/death-wish-coffee/page_data` returns `{"code":10000}` | `shop_search_puzzle.png`, `shop_root_puzzle.png`, `shop_search_text_and_api.txt` |
| F2 | A plain GET of `https://www.tiktok.com/shop/pdp/_/1732222721408012710` answers HTTP 301 to `https://shop.tiktok.com/us/pdp/_/1732222721408012710`. The target was not opened (it is on the host that shows the puzzle) | `pdp_url_redirect_headers.txt` |
| F3 | The actor is pay-per-event. On the FREE plan a returned US product costs $0.00199 (`product-scraped-us`; $0.00196 to $0.00198 on paid plans) and a run start costs $0.00005 per GB of memory. Add-ons (reviews beyond 5, creator count, hashtag products) are separate events | `apify/actor_pricing_and_stats.json` |
| F4 | Run start: `POST https://api.apify.com/v2/acts/lurkapi~tiktok-shop-scraper/runs` with query `build`, `memory`, `timeout`, `maxTotalChargeUsd`, `waitForFinish`, header `Authorization: Bearer <token>`, JSON body = actor input. Answers 201 with `{"data": <run>}`. `build=0.0.34` and `memory=1024` are applied (`options.build`, `options.memoryMbytes`) | `apify/pinned_build_1.run.json` |
| F5 | `maxTotalChargeUsd` below $0.00204 is refused: HTTP 400, `error.type` `max-total-charge-usd-below-minimum`. No run is created and nothing is charged | `apify/cap_below_minimum.response.json` |
| F6 | When charges reach `maxTotalChargeUsd` the run ends with `status` `ABORTED` and `statusMessage` "This run was aborted because it reached its maximum cost of $0.00.". The dataset then holds more `Success` rows (14) than were charged (1) | `apify/cap_reached_aborted.*` |
| F7 | `waitForFinish` is at most 60 seconds. Run statuses are `READY`, `RUNNING`, `SUCCEEDED`, `FAILED`, `TIMING-OUT`, `TIMED-OUT`, `ABORTING`, `ABORTED`. `GET /v2/datasets/<id>/items` has no item limit by default | Apify OpenAPI document `https://docs.apify.com/api/openapi.json`, fetched 2026-11-10 |
| F8 | Run times on build 0.0.34: 1 ID 17.0 s, 2 IDs 8.6 s, 10 search results 21.4 s, 20 search results 13.3 s, 4 × 10 search results 41.7 s | `apify/*.run.json` (`runTimeSecs`), `apify/run_summary.json` |
| F9 | A search run returns exactly `maxProductsPerSource` rows per term, all `status` `Success`, `source` `keyword`, `rank` 1 to N each once, `inputUrl` `https://shop.tiktok.com/us/s?q=<term, percent-encoded>`. Dataset order is not rank order | `apify/search_death_wish_coffee_20.items.json` (20), `apify/search_four_brands_10.items.json` (4 × 10) |
| F10 | A product-ID run returns one row per ID: `source` `productId`, `rank` = position of the ID in the input (1-based), `inputUrl` `null` | `apify/product_ids_2.items.json`, `apify/pinned_build_1.items.json` |
| F11 | An ID with no product returns a row with `status` `Not available in US` and only the keys `countryCode`, `error`, `inputUrl`, `lastTimeStamp`, `productId`, `productUrl`, `rank`, `scrapeTimestamp`, `source`, `status`. It is not charged. The run is still `SUCCEEDED` | `apify/product_id_not_available.*` |
| F12 | The same product fetched by ID and by search gave the same `currentPrice`, `soldCount` and `reviewCount` (2 products; the two fetches were 13 minutes and 3 hours 47 minutes apart) | `apify/product_ids_2.items.json` vs the two search files |
| F13 | Shop inputs return no products: `shopIds` `7495749272480024998` (Death Wish Coffee), `7495199044660923298` (Living Proof) and the URL `https://www.tiktok.com/shop/store/death-wish-coffee/7495749272480024998` each give one row with only `status` "Input produced 0 results — every URL/ID failed to resolve. …" and `countryCode`. The log says "Found 0 products for shop" | `apify/shop_*.items.json`, `apify/shop_zero_products.log.txt` |
| F14 | In all 72 `Success` rows: these keys are never null: `status`, `productId`, `source`, `rank`, `countryCode`, `productUrl`, `title`, `currentPrice`, `priceDisplay`, `currency`, `rating`, `reviewCount`, `ratingsBreakdown`, `soldCount`, `sellerId`, `sellerName`, `sellerUrl`, `sellerSold`, `sellerProductCount`, `sellerReviewCount`, `sellerIsOfficial`, `brand`, `categoryPath`, `mainImage`, `imageUrls`, `variants`, `gmvContribution`, `scrapeTimestamp`, `lastTimeStamp`. `originalPrice` is present and non-null in 11. `productId` and `sellerId` are 19 digits. `productUrl` is always `https://www.tiktok.com/shop/pdp/_/<productId>`. `currency` is always `USD`, `countryCode` `US`. `scrapeTimestamp` looks like `2026-11-10T10:53:42.007Z` | computed over `apify/search_four_brands_10`, `search_death_wish_coffee_20`, `product_ids_2`, `search_death_wish_coffee_items` |
| F15 | The key `reviews` is present only when the product has reviews: a list of 1 to 5 entries, returned with `includeReviews` false and not charged. Each entry carries the reviewer's name (`user`), `userId`, `userAvatar` and `country` | `apify/search_death_wish_coffee_items.json` (`keys_in_raw`), `apify/*.items.json` (redacted entries) |
| F16 | `shippingOrigin` was null in all 72 rows. The actor README's example row has a street address in it (`"745 Main St, Dunedin, Florida, …"`) | same files; `apify/actor_readme.md` |
| F17 | `soldCount` is an integer and is not rounded to thousands (1332402, 17756, 12298, 1727). `sellerSold` has values such as 594265 and 65464 | `apify/search_death_wish_coffee_20.items.json`, `apify/search_four_brands_10.items.json` |
| F18 | `brand` equals `sellerName` in all 72 rows. `sellerIsOfficial` is true for some resellers (FragranceNet, Planet Beauty) and false for the Death Wish Coffee shop. `sellerProductCount` differs between rows of the same seller (FragranceNet: 0 and 16005) | `apify/search_four_brands_10.items.json` |
| F19 | Search results change between runs. "death wish coffee" at 07:09Z and at 10:53Z share 2 products in their top 10; in the second run 18 of the top 20 are not Death Wish Coffee products. A meaningless term returns products too ("zzqxv nosuchproduct 48213": 14 rows) | `apify/search_death_wish_coffee_items.json`, `apify/search_death_wish_coffee_20.items.json`, `apify/cap_reached_aborted.items_summary.json` |
| F20 | Charges are recorded after the run ends. Right after `SUCCEEDED`, `chargedEventCounts` and `accountedChargedEventCounts` of `product-scraped-us` lag behind the number of `Success` rows (once both were 0 while 2 rows existed). In 5 `SUCCEEDED` runs they both equalled the row count 7 to 13 seconds later, and `usageTotalUsd` was then final. In the `ABORTED` run, accounted (1) never reached charged (2) within 231 seconds | `apify/billing_settlement_polls.json` |
| F21 | Brand shops seen in search: Death Wish Coffee `sellerId` `7495749272480024998` (371,948 followers; the `@deathwishcoffee` profile had 371,950), Living Proof, Inc. `7495199044660923298` (104,662; profile 104,655). No seller named after Batiste, Black Rifle Coffee or Jinx appeared in the top 10 for their terms | `apify/search_*.items.json`; `part1/collectors/08_tiktok_posts/samples/handles_four_brands.json` |

## 3. Inputs
### Command line
As in the shared contract. No extra options.

### `brand_inputs.json`
```json
{
  "batiste": {"search_term": "batiste dry shampoo",
    "tracked_product_ids": ["1729700841513849624", "1731481072630141720", "1731685127579930741", "1732457334855733553", "1732457335553560881", "1732457336723312945", "1732457336927523121", "1732457338433802545", "1732819509339853133"]},
  "living-proof": {"search_term": "living proof",
    "tracked_product_ids": ["1729408843730228130", "1729408848141849506", "1729442967734752162", "1731612409548279962", "1731612497358524570", "1732296356580004770", "1732372458975171490", "1732457347225653553", "1732558722221904177", "1732666411792044962"]},
  "death-wish-coffee": {"search_term": "death wish coffee",
    "tracked_product_ids": ["1731139671457894448", "1731139718276550704", "1731262766835208281", "1731723268453077081", "1732073712165556339", "1732222721408012710", "1732448121975640919", "1732686538274607526", "1732694229670334886", "1732804219232620966"]},
  "black-rifle-coffee": {"search_term": "black rifle coffee",
    "tracked_product_ids": ["1730952228322710146"]},
  "jinx": {"search_term": "jinx dog food",
    "tracked_product_ids": ["1731985309626372528", "1732818242450854389"]}
}
```
- `search_term`: Batiste and Jinx carry a product word because the bare names also mean other things (same rule as source 7). The others are the brand name.
- `tracked_product_ids`: every `Success` row in the three search samples (`apify/search_death_wish_coffee_items.json`, `apify/search_four_brands_10.items.json`, `apify/search_death_wish_coffee_20.items.json`) that was sold by a brand shop (F21) or whose `title` contains the brand name (case-insensitive: `batiste`, `living proof`, `death wish`, `black rifle`, `jinx`), sorted ascending. 32 IDs. The list is maintained by hand; the collector never changes it.
- The collector validates the file when it starts: every brand slug from `brands.json` is present, `search_term` is a non-empty string, `tracked_product_ids` is a non-empty list of strings of digits only, with no duplicates. Otherwise it exits with code 2 and runs nothing.

### Token
`APIFY_TOKEN` from `.env` at the repository root (the directory three levels above `source_collector.py`): the first line that starts with `APIFY_TOKEN=`; the value is the rest of the line with surrounding whitespace and one pair of surrounding quotes (`"` or `'`) removed. The token is **missing** when `.env` does not exist, has no such line, or the value is empty. The token is sent only in the `Authorization` header. It is never put in a URL, a log line or a file.

### Dependencies
`requirements.txt` contains one line: `requests>=2.31,<3`.

### Constants
| Name | Value | Used in |
|---|---|---|
| `API_BASE` | `https://api.apify.com/v2` | every request |
| `ACTOR_ID` | `lurkapi~tiktok-shop-scraper` | step 2 |
| `ACTOR_BUILD` | `0.0.34` | step 2 |
| `ACTOR_MEMORY_MB` | `1024` | step 2 |
| `ACTOR_TIMEOUT_S` | `300` | step 2 |
| `SEARCH_LIMIT` | `20` | steps 1, 6 |
| `PRODUCT_PRICE_USD` | `0.00199` | step 1 |
| `START_PRICE_USD` | `0.00005` | step 1 |
| `WAIT_FOR_FINISH_S` | `60` | steps 2, 3 |
| `MAX_WAIT_REQUESTS` | `6` | step 3 |
| `HTTP_TIMEOUT_S` | `90` | every request |
| `GET_RETRIES` | `3` | steps 3, 4, 5 |
| `GET_RETRY_SPACING_S` | `10` | steps 3, 4, 5 |
| `COST_POLL_INTERVAL_S` | `5` | step 5 |
| `COST_POLL_MAX` | `12` | step 5 |
| `PART_SPACING_S` | `5` | between the two parts and between brands with `--all` |

## 4. Procedure
HTTP: the `requests` library, one request at a time, `timeout=HTTP_TIMEOUT_S`, header `Authorization: Bearer <token>`. No request goes to any host other than `api.apify.com`.

**Before anything:** if the token is missing or empty, finish with `could_not_look`, `reason` `missing_token`, `requests` 0, `cost_usd` 0, and write no records.

The brand's run has two **parts**, done in this order: `tracked`, then `search`. Wait `PART_SPACING_S` between them. The search part runs even when the tracked part failed. Steps 1 to 6 are done for each part.

1. **Actor input and charge cap.** The input is exactly:
   - tracked: `{"country": "US", "productIds": <tracked_product_ids>, "includeReviews": false, "includeCreatorCount": false, "includeFirstSeen": false}`
   - search: `{"country": "US", "keywords": [<search_term>], "keywordSortBy": "default", "maxProductsPerSource": 20, "includeReviews": false, "includeCreatorCount": false, "includeFirstSeen": false}`

   `n` is the number of tracked IDs, or `SEARCH_LIMIT`. The charge cap is `START_PRICE_USD + PRODUCT_PRICE_USD × (n + 1)`, computed with `decimal.Decimal` and written with 5 decimals (for example `0.04184` for search). It is always at least $0.00403, above the $0.00204 minimum (F5). The extra product leaves room so that a complete run never reaches the cap; a run that does reach it is `ABORTED` (F6).
2. **Start the run.** `POST {API_BASE}/acts/{ACTOR_ID}/runs?build=0.0.34&memory=1024&timeout=300&maxTotalChargeUsd=<cap>&waitForFinish=60` with the input as the JSON body.
   - HTTP 201: keep `data.id` (run ID), `data.defaultDatasetId` and `data.status`.
   - Any other HTTP status: the part fails with `apify_start_failed: http_<status> <error.type>` (`error.type` from the JSON body, or `-` when the body is not JSON or has no `error.type`). Go to the next part.
   - Network error or timeout: the part fails with `apify_start_failed: request_error: <exception class name>`. Go to the next part.
   - The POST is never retried, because a retry could start and charge a second run.
3. **Wait.** While the status is `READY`, `RUNNING`, `TIMING-OUT` or `ABORTING`: `GET {API_BASE}/actor-runs/<run ID>?waitForFinish=60` and read `data.status`. At most `MAX_WAIT_REQUESTS` such requests (6 × 60 s is more than `ACTOR_TIMEOUT_S`, after which Apify itself ends the run).
   - If the status is still one of these four after `MAX_WAIT_REQUESTS`: the part fails with `apify_run_not_finished(<status>)`. Steps 4 and 5 are skipped. Go to the next part.
   - Terminal statuses are `SUCCEEDED`, `FAILED`, `TIMED-OUT`, `ABORTED`. Keep `data.status`, `data.statusMessage` and `data.buildNumber`.
   - Any other status value: the part fails with `apify_unknown_status(<status>)`. Steps 4 and 5 are skipped. Go to the next part.
4. **Read the dataset** for every terminal status: `GET {API_BASE}/datasets/<defaultDatasetId>/items?format=json`. The body is a JSON list of rows. Note the UTC time the response was received (`dataset_received_at`). If this fails after retries, the part fails with `apify_dataset_failed: <detail>`; step 5 still runs, using its second bullet.
5. **Read the cost.**
   - Status `SUCCEEDED` and the dataset was read: send `GET {API_BASE}/actor-runs/<run ID>` (no `waitForFinish`) at once, then every `COST_POLL_INTERVAL_S`, at most `COST_POLL_MAX` requests in all, until the run is **settled**: `data.chargedEventCounts` equals `data.accountedChargedEventCounts` for every event, and `data.chargedEventCounts["product-scraped-us"]` equals the number of dataset rows with `status` `Success` (F20). The part's `cost_usd` is `data.usageTotalUsd` of the last response; `cost_settled` is true if it settled, otherwise false.
   - Any other case (status not `SUCCEEDED`, or the dataset was not read): one `GET` after waiting `COST_POLL_INTERVAL_S`; `cost_usd` is its `data.usageTotalUsd`; `cost_settled` is false (F20).
   - **Fallback value, used only here:** when step 5 is skipped or its requests fail after retries, `cost_usd` is the `data.usageTotalUsd` of the last run object received in step 2 or 3, and `cost_settled` is false. When no run was started, `cost_usd` is 0 and `cost_settled` is true.
6. **Classify the rows** (section 7, `classify_part`) and write the records (section 5) in this order: tracked records in the order of `tracked_product_ids`, then search records in `rank` order. This step also runs when the part failed in steps 2 to 4: `classify_part` is then called with `part_error` set to the failure text and no rows, and it produces only the tracked part's `missing` records. `observed_at` is `dataset_received_at`, or the UTC time the part failed when no dataset was read.

**GET retries (steps 3, 4, 5):** on a network error, a timeout, HTTP 429 or HTTP 5xx, wait `GET_RETRY_SPACING_S` and send the same request again, at most `GET_RETRIES` times. Any other non-200 answer is not retried. When a GET in step 3 still fails, the part fails with `apify_poll_failed: <detail>` and steps 4 and 5 are skipped. `<detail>` is `http_<status>` or `request_error: <exception class name>`.

**Classifying rows (step 6).** For each row of the dataset, in dataset order:
- **Message row:** a row without the key `productId` or with `productId` null (F13). It is not written. It is counted in `message_rows`.
- **Unexpected row (tracked part only):** a row whose `productId` is not in `tracked_product_ids`. It is not written. It is counted in `unexpected_rows`.
- **Duplicate row:** a row whose `productId` already appeared in an earlier row of the same part. It is not written. It is counted in `duplicate_rows`.
- **Shape check** (`check_row_shape`) on every remaining row. If any row fails, the whole part fails with `shape_changed: row <index in dataset, 0-based> <field>`, **no record of this part is written**, and the dataset (after step 7 of section 5 removes personal data) is written to `raw/<brand>/<run_id>.apify/<part>_dataset.json` for inspection.
- Otherwise each row becomes one record with `item_state`:
  - `fetched` when `status` is `Success`,
  - `unavailable` when `status` is `Not available in US` (F11),
  - `failed` for any other `status` value; `item_error` is that value.
- **Missing (tracked part only):** for each tracked ID with no written row, a record with `item_state` `missing` and `raw.item` null. Its `item_error` is the part's `error` text when the part has one (steps 2 to 4, `no_products`), otherwise `no_row`. So every tracked ID has exactly one record in every run, except when the shape check failed (then the part writes nothing).
- If the dataset was read and has no row with a `productId`, the part fails with `no_products: <status of the first message row>`, or `no_products: empty dataset` when the list is empty.

`check_row_shape(row, expected_source)` raises `ShapeError(<field>)` for the first field below that does not hold, checked top to bottom. "Number" means `int` or `float` and not `bool`; "integer" means `int` and not `bool`. First, every row must have `status` as a non-empty string (`ShapeError("status")`). Rows with `status` `Success`:

| Field | Must be |
|---|---|
| `productId` | string of digits only |
| `status` | `Success` |
| `source` | `expected_source` (`productId` for tracked, `keyword` for search) |
| `rank` | integer ≥ 1 |
| `productUrl` | exactly `https://www.tiktok.com/shop/pdp/_/<productId>` |
| `title` | non-empty string |
| `currentPrice` | number |
| `originalPrice` | key present; number or null |
| `currency` | `USD` |
| `countryCode` | `US` |
| `soldCount` | integer ≥ 0 |
| `rating` | number |
| `reviewCount` | integer ≥ 0 |
| `sellerId` | string of digits only |
| `sellerName` | non-empty string |
| `scrapeTimestamp` | string matching `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$` |
| `reviews` | absent, or a list |

Rows with any other `status`: only `productId`, `source`, `productUrl` and `scrapeTimestamp`, in that order, with the same rules. Keys not listed are not checked.

## 5. Output
### Record
| Envelope field | Tracked part | Search part |
|---|---|---|
| `key` | `product/<productId>` | `search/<search_term>/<productId>`, for example `search/death wish coffee/1732222721408012710` |
| `kind` | `product` | `search_result` |
| `url` | `https://www.tiktok.com/shop/pdp/_/<productId>` | same |
| `fetched_at` | `scrapeTimestamp` with the milliseconds removed (`2026-11-10T10:57:19Z`). For `missing` records: `observed_at` (step 6), in the same format | same |

`raw`:
```json
{
  "item": {},
  "item_state": "fetched",
  "item_error": null,
  "input": {"part": "tracked", "product_id": "1732222721408012710"},
  "apify_run_id": "l1UEKc0b7lh5XMrat",
  "reviews_removed": 5,
  "shipping_origin_removed": false
}
```
| Field | Value |
|---|---|
| `item` | The dataset row, unchanged except for step 7. `null` for `missing` |
| `item_state` | `fetched`, `unavailable`, `failed` or `missing` |
| `item_error` | `null` for `fetched`; the row's `status` for `unavailable` and `failed`; for `missing`, the part's `error` text or `no_row` (section 4) |
| `input` | `{"part": "tracked", "product_id": "<id>"}` or `{"part": "search", "search_term": "<term>", "limit": 20}` |
| `apify_run_id` | The run that produced the row. `null` when the part failed before a run existed |
| `reviews_removed` | Number of entries in the row's `reviews` list, 0 when there was none |
| `shipping_origin_removed` | `true` when `shippingOrigin` was not null |

**Step 7, remove personal data** (`strip_personal`), applied to every row before it is written anywhere: delete the key `reviews` (it holds reviewer names, user IDs and avatars, F15) and set `shippingOrigin` to `null` (it can hold a street address, F16). Seller names are kept: they are the shop names TikTok Shop shows publicly as the seller of each product.

### Run result
`source` is `tiktok_shop`. `expected_total` is `null` (the source reports no total). `records_by_kind` is `{"product": <n>, "search_result": <m>}`. `requests` is the number of HTTP requests sent to `api.apify.com`, retries included. `cost_usd` is `round(tracked cost_usd + search cost_usd, 5)`, using 0 for a part that never started a run.

`extra`:
```json
{
  "data_provider": "apify",
  "actor": "lurkapi/tiktok-shop-scraper",
  "values_checked_against_site": false,
  "reviews_removed": 7,
  "tracked": {"apify_run_id": "...", "apify_status": "SUCCEEDED", "apify_status_message": null, "actor_build": "0.0.34",
              "error": null, "requested": 10, "fetched": 10, "unavailable": 0, "failed": 0, "missing": 0,
              "unexpected_rows": 0, "duplicate_rows": 0, "message_rows": 0, "cost_usd": 0.01995, "cost_settled": true},
  "search":  {"apify_run_id": "...", "apify_status": "SUCCEEDED", "apify_status_message": null, "actor_build": "0.0.34",
              "error": null, "search_term": "death wish coffee", "limit": 20, "fetched": 20, "unavailable": 0, "failed": 0,
              "duplicate_rows": 0, "message_rows": 0, "ranks_complete": true, "cost_usd": 0.03985, "cost_settled": true}
}
```
- `values_checked_against_site` is always `false`. It tells the pipeline that the values come from the provider and were not compared with the TikTok page.
- `error` is `null` or the part's failure text from section 4. `apify_status` and `actor_build` are `null` when there was no run.
- `ranks_complete` is true when the `rank` values of the `fetched` search records are exactly 1 to 20.

**Part problems** (`part_problems`), listed in this order and joined with `, `:
1. `error`, when it is not null. When it is set, nothing else is listed.
2. `apify_run_<apify_status>: <apify_status_message or empty>`, when `apify_status` is not `SUCCEEDED`.
3. For each counter that is not 0, in this order: `failed=<n>`, `missing=<n>` (tracked only), `unavailable=<n>` (search only), `unexpected_rows=<n>` (tracked only), `duplicate_rows=<n>`, `message_rows=<n>`.
4. Search only: `fetched=<n>/20` when `fetched` is not 20; otherwise `ranks_incomplete` when `ranks_complete` is false.

A part is **complete** when its problem list is empty. An `unavailable` tracked product does not make the tracked part incomplete: the actor looked and reported that the product is not available (F11).

Status, decided in this order:
| Condition | `status` | `reason` |
|---|---|---|
| Token missing or empty | `could_not_look` | `missing_token` |
| Both parts have `error` set | `could_not_look` | `tracked: <error>; search: <error>` |
| Both parts complete | `ok` | empty |
| Anything else | `partial` | for each part with problems, `<part>: <problems>`, parts joined with `; `. Example: `tracked: missing=1; search: fetched=19/20` |

## 6. Failures
A failure is always written down. It is never hidden behind `ok`, and it never triggers a different method.

| Situation | Record or run result | Then |
|---|---|---|
| Run start refused or request error | part `error` `apify_start_failed: …`; tracked IDs get `missing` records | next part |
| Run not finished after 6 waits, or a status value not in F7 | part `error` `apify_run_not_finished(<status>)` or `apify_unknown_status(<status>)`; `missing` records | next part |
| A wait request (step 3) fails after retries | part `error` `apify_poll_failed: …`; `missing` records | next part |
| Run ends `FAILED`, `TIMED-OUT` or `ABORTED` (for example the cap, F6) | part problem `apify_run_<status>: <message>`; the rows it returned are written | next part |
| Dataset cannot be read | part `error` `apify_dataset_failed: …`; `missing` records | next part |
| Only message rows, or no rows | part `error` `no_products: …`; `missing` records | next part |
| A row fails the shape check | part `error` `shape_changed: row <i> <field>`; no records for the part; dataset side file | next part |
| A tracked product row has a status other than `Success` | record `item_state` `unavailable` or `failed` | next row |
| A tracked ID has no row | record `item_state` `missing` | next ID |
| Cost does not settle within 60 s | part `cost_settled` false; `cost_usd` is the last value read | status is not affected |
| Unexpected exception | as in the shared contract | records written so far are kept |

## 7. Required functions and tests
These functions are pure. Their tests read the files in `part1/collectors/09_tiktok_shop/samples/apify/` and do not use the network.

```python
class ShapeError(Exception): ...

@dataclass
class PartResult:
    records: list[dict]          # envelopes, ready to write
    counts: dict                 # fetched, unavailable, failed, missing, unexpected_rows, duplicate_rows, message_rows
    error: str | None            # part_error as given, or no_products: ..., or shape_changed: ...
    ranks_complete: bool | None  # search only
    reviews_removed: int

def charge_cap_usd(n_products: int) -> str: ...
def tracked_input(product_ids: list[str]) -> dict: ...
def search_input(term: str) -> dict: ...
def check_row_shape(row: dict, expected_source: str) -> None: ...
def strip_personal(row: dict) -> tuple[dict, int, bool]: ...   # row copy, reviews_removed, shipping_origin_removed
def classify_part(rows: list, part: str, apify_run_id: str | None, tracked_ids: list[str] | None,
                  search_term: str | None, observed_at: str, part_error: str | None = None) -> PartResult: ...
def start_failure(http_status: int | None, body: str | None, exc: Exception | None) -> str: ...
def is_settled(run: dict, success_rows: int) -> bool: ...
def part_problems(part_extra: dict, part: str) -> list[str]: ...
def decide_status(token_present: bool, tracked_extra: dict, search_extra: dict) -> tuple[str, str]: ...
```

Expected values below were computed from the sample files. "dw20" is `search_death_wish_coffee_20.items.json`, "ids2" is `product_ids_2.items.json`.

| Test | Input | Expected |
|---|---|---|
| charge cap | `charge_cap_usd(20)`, `(10)`, `(1)` | `"0.04184"`, `"0.02194"`, `"0.00403"` |
| tracked input | `tracked_input(["1732222721408012710", "1732457338433802545"])` | equal to `product_ids_2.input.json` |
| search input | `search_input("death wish coffee")` | equal to `search_death_wish_coffee_20.input.json` |
| shape: real rows | every row of dw20 and `search_four_brands_10.items.json` with `keyword`; every row of ids2 and `pinned_build_1.items.json` with `productId`; the row of `product_id_not_available.items.json` with `productId` | no exception (20 + 40 + 2 + 1 + 1 rows) |
| shape: missing field | dw20 row 0 with `soldCount` deleted | `ShapeError("soldCount")` |
| shape: currency | dw20 row 0 with `currency` `"GBP"` | `ShapeError("currency")` |
| shape: source | ids2 row 0 checked with `keyword` | `ShapeError("source")` |
| strip | ids2 row 1 (`1732457338433802545`) | no `reviews` key, `reviews_removed` 2, `shipping_origin_removed` false |
| strip address | ids2 row 0 with `shippingOrigin` `"745 Main St"` | `shippingOrigin` null, `reviews_removed` 5, `shipping_origin_removed` true |
| search complete | `classify_part(dw20, "search", …, search_term="death wish coffee")` | 20 records in rank order, `fetched` 20, `ranks_complete` true, `error` null, `reviews_removed` 59; first record `key` `search/death wish coffee/1732222721408012710`, `fetched_at` `2026-11-10T10:53:42Z`, `kind` `search_result`; `part_problems` is `[]` |
| search short | dw20 without its rank-20 row | `fetched` 19; `part_problems` is `["fetched=19/20"]` |
| search duplicate | dw20 plus a copy of its row 0 | 20 records, `duplicate_rows` 1; `part_problems` is `["duplicate_rows=1"]` |
| tracked complete | ids2, tracked IDs `["1732222721408012710", "1732457338433802545"]` | 2 records; first `key` `product/1732222721408012710`, `url` `https://www.tiktok.com/shop/pdp/_/1732222721408012710`, `fetched_at` `2026-11-10T10:57:19Z`, `raw.reviews_removed` 5, no `reviews` in `raw.item`; `part_problems` is `[]` |
| tracked missing | ids2, tracked IDs as above plus `"1729999999999999999"`, `observed_at` `2026-11-10T11:00:00Z` | 3 records; third has `key` `product/1729999999999999999`, `item_state` `missing`, `item_error` `no_row`, `raw.item` null, `fetched_at` `2026-11-10T11:00:00Z`; `part_problems` is `["missing=1"]` |
| part failed earlier | `[]` as tracked, tracked IDs `["1732222721408012710", "1732457338433802545"]`, `part_error` `apify_start_failed: http_400 max-total-charge-usd-below-minimum`, `apify_run_id` null | 2 records, both `item_state` `missing` with that `item_error` and `apify_run_id` null; `error` is that text |
| tracked unavailable | `product_id_not_available.items.json`, tracked IDs `["1729999999999999999"]` | 1 record, `item_state` `unavailable`, `item_error` `Not available in US`, `fetched_at` `2026-11-10T10:43:21Z`; `part_problems` is `[]` |
| tracked unexpected | ids2, tracked IDs `["1732222721408012710"]` | 1 record, `unexpected_rows` 1; `part_problems` is `["unexpected_rows=1"]` |
| no products | `shop_id_zero_products.items.json` as tracked, tracked IDs `["1732222721408012710"]` | `error` `no_products: ` + the full `status` text of its row, `message_rows` 1; 1 record with `item_state` `missing` and `item_error` equal to that `error` |
| empty dataset | `[]` as search | `error` `no_products: empty dataset`, 0 records |
| bad shape stops part | dw20 with `soldCount` deleted from row 3 | 0 records, `error` `shape_changed: row 3 soldCount` |
| start refused | `start_failure(400, <text of cap_below_minimum.response.json>, None)` | `apify_start_failed: http_400 max-total-charge-usd-below-minimum` |
| aborted run | `part_problems(e, "search")` where `e` is a search part extra with `error` null, `apify_status` and `apify_status_message` taken from `cap_reached_aborted.run.json`, `fetched` 14, `ranks_complete` false and every other counter 0 | `["apify_run_ABORTED: This run was aborted because it reached its maximum cost of $0.00.", "fetched=14/20"]` |
| settled | `is_settled(product_ids_2.run.json, 2)` | true |
| not settled: lag | `product_ids_2.run.json` with `product-scraped-us` set to 0 in both count maps (the 2-second snapshot in `billing_settlement_polls.json`), 2 rows | false |
| not settled: aborted | `is_settled(cap_reached_aborted.run.json, 14)` | false |
| status | each row of the status table in section 5 | the `status` and `reason` of that row |

## 8. Done when
1. All tests in section 7 pass with no network access.
2. `--brand death-wish-coffee` finishes with `status` `ok`, `records_by_kind` `{"product": 10, "search_result": 20}`, both parts `cost_settled` true, and `cost_usd` at most 0.0598 (10 + 20 products and two starts).
3. `--all` writes five run results. The sum of their `cost_usd` is at most 0.26318 (32 + 100 products and ten starts).
4. Running the same command twice leaves the first run's files byte-for-byte unchanged and adds a second set.
5. With `APIFY_TOKEN` removed from `.env`, every brand finishes `could_not_look`, `missing_token`, `requests` 0, `cost_usd` 0.
6. With `"1729999999999999999"` added to Death Wish Coffee's tracked IDs, that record has `item_state` `unavailable` and the run is still `ok` (if nothing else failed).
7. No `raw.item` in any record has the key `reviews`, no file under `raw/` contains the text `userAvatar`, and every non-null `raw.item` has `shippingOrigin` null.
8. The Apify console shows each run with build `0.0.34`, memory 1024 MB and the cap from step 1.

## 9. Not covered: stop and report
Stop work and report, with the exact response, when any of these happen. Do not choose a behavior yourself.
- A real run during development fails the shape check. Do not loosen the check.
- A row has a `status` other than `Success`, `Not available in US` or the message-row form of F13.
- A search part returns fewer than 20 rows, or `ranks_complete` is false.
- Build `0.0.34` cannot be started. Do not switch to `latest` or another build.
- A `SUCCEEDED` run does not settle within `COST_POLL_MAX` polls, or `cost_usd` of a part is higher than its charge cap.
- Anything else that makes a step in section 4 impossible to carry out as written.

## 10. Where the pipeline will find each value later
For reference only.

| Attribute | Location in the raw data |
|---|---|
| product_id | `raw.item.productId` |
| title | `raw.item.title` |
| price, currency | `raw.item.currentPrice`, `raw.item.currency`; as displayed: `raw.item.priceDisplay` |
| list price before discount | `raw.item.originalPrice` (often null) |
| sales count (lifetime) | `raw.item.soldCount` (exact integer) |
| rating, review count | `raw.item.rating`, `raw.item.reviewCount` (both 0 when the product has no reviews) |
| seller | `raw.item.sellerId`, `raw.item.sellerName`, `raw.item.sellerUrl` |
| brand shop or reseller | compare `raw.item.sellerId` with the brand shops in F21. Do not use `raw.item.brand` (it is the seller name) or `raw.item.sellerIsOfficial` (false for the Death Wish Coffee shop) |
| search rank | `raw.item.rank` with `raw.input.search_term` (`search_result` records only) |
| category | `raw.item.categoryPath` |
| availability | `raw.item_state`, `raw.item.status` |
| observed at | `raw.item.scrapeTimestamp` |
| image | `raw.item.mainImage` |
| not provided by TikTok | `raw.item.gmvContribution` (price × sold) and `raw.item.commentRate` (reviews ÷ sold) are computed by the actor |
| always null so far | `description`, `discountPercent`, `freeShipping`, `specifications`, `totalStock`, `variantOptions`, `videoUrls`, `businessName`, `sellerShipsWithinDays`; `variants[]` holds only `skuId` |
