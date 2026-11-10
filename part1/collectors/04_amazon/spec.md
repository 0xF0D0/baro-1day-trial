# Spec: source 4, Amazon raw collector

- Shared contract: `part1/collectors/README.md`. Read it first; this document adds only what is specific to this source.
- Research notes: `part1/collectors/04_amazon/source_info.md`. Where they differ from this spec, this spec is newer.
- Every fact below was observed in real Apify runs or on the live site on 2026-11-10. If an actor or the Apify API behaves differently, or a step needs something this spec does not give, stop and report. Do not guess, and never switch to another actor or to fetching amazon.com directly.

## 1. What to build
One file, `source_collector.py`. Given a brand, it picks the brand's top 10 distinct products on Amazon.com and writes one record per product and one per review (up to 10 Top reviews per product). It calls three paid Apify actors over the Apify REST API, one after another, with the standard library. No retries.

| Stage | Actor | Gives |
|---|---|---|
| A. Search | `apt_marble~amazon-search-results-scraper` | the brand-name search results in Amazon's order |
| C. Detail | `junglee~Amazon-crawler` | Best Sellers Rank, exact rating count, variant family, seller, stock |
| E. Reviews | `delicious_zebu~amazon-reviews-scraper-with-advanced-filters` | the Top reviews of each product |

The collector decides which products and reviews to fetch (stages B and D). It does not extract or interpret any other value, and it does not store ads.

## 2. Facts about the source
| # | Fact |
|---|---|
| F1 | The search actor takes search terms only (`keywords`), so Amazon's brand filter cannot be used. It returns one row per result in Amazon's order. `position` counts across pages (page 1 gave 1 to 48, page 2 gave 50 to 61); 60 results took 2 pages and 13 seconds |
| F2 | Every search row had `keyword`, `position`, `isSponsored`, `asin`, `brand`, `scrapedAt`. `price`, `rating` and `ratingsCount` are left out when Amazon shows none (2 of 60 rows had no price) |
| F3 | `isSponsored` was `false` in all 110 rows of 5 search terms, although a browser saw ads in the same search. The actor's sessions get results without ads |
| F4 | `brand` is the card's brand line when there is one (`Batiste`, `Jinx`, `Death Wish Coffee`, `LIVING PROOF`, `Black Rifle Coffee Company`). Otherwise it holds title-like text: 9 of 10 Black Rifle rows, for example `Black Rifle Coffee Medium Roast Ground Coffee Just Black 18 oz`, and competitors such as `Hardcore Ground Coffee, Strong Roast, High Caffeine, 16 Oz` |
| F5 | `ratingsCount` is the exact integer. Size and pack variants of one product share `rating` and `ratingsCount` (Death Wish 16 oz and 2-pack: 4.6 / 48,586), and so do Jinx flavors (4.6 / 2,323). Small counts coincide between unrelated products (two Death Wish products both 5.0 / 1) |
| F6 | Price, rating and "bought in past month" matched a browser 20 of 20. Search order differs between sessions: 18 of 20 rows were within the browser's first 22 results, 2 were far off |
| F7 | The detail actor takes product URLs. Each item has `input` equal to the URL sent; items do not come back in input order. Items have `asin`, `price.value`, `stars`, `reviewsCount`, `starsBreakdown`, `bestsellerRanks` (main category first), `variantAsins`, `variantAttributes`, `seller.name`, `inStockText`, `monthlyPurchaseVolume`, `aiReviewsSummary`, `locationText`. Price, `reviewsCount` and both ranks matched the product pages 3 of 3. There is no parent ASIN field |
| F8 | `variantAsins` lists the whole family, other flavors included: Death Wish Dark Roast and Medium Roast list the same 41 ASINs but have different `reviewsCount` (48,586 and 3,357). A product without variants has `[]`. When an input cannot be read the actor writes an item with an `error` key |
| F9 | The review actor returns exactly `max_reviews` rows per ASIN, each with the requested `ASIN` and a `ReviewId`. Row order is Amazon's Top reviews order: it matched a signed-in browser for 8 Batiste and 5 Death Wish reviews. With `include_personal_data: false`, `Reviewer`, `ReviewerProfileUrl` and `ReviewerId` are empty strings. `Images` and `Videos` are lists of customer media URLs |
| F10 | `https://www.amazon.com/portal/customer-reviews/srp/-/<ReviewId>` shows the review to a signed-in browser; signed out it redirects to sign-in |
| F11 | An Apify run can end `SUCCEEDED` with 0 items while the actor was blocked (seen with two other Amazon actors). The status alone never proves data was collected |
| F12 | Right after a run ends, `usageTotalUsd` can still be incomplete (0 instead of 0.06; 0.03 instead of 0.15). Read 19 to 31 seconds after `finishedAt` it was final in every run |
| F13 | Prices on the free plan: search $0.001 per row; detail $0.005 per product; reviews $0.006 per review plus $0.03 per run at 256 MB. Caps from $0.05 to $0.20 were accepted by all three actors |

Samples for all of these are in `part1/collectors/04_amazon/samples/apify/`.

## 3. Input
`brand_inputs.json`:
```json
{
  "batiste": {"keyword": "batiste", "brand_names": ["batiste"]},
  "living-proof": {"keyword": "living proof", "brand_names": ["living proof"]},
  "death-wish-coffee": {"keyword": "death wish coffee", "brand_names": ["death wish coffee"]},
  "black-rifle-coffee": {"keyword": "black rifle coffee", "brand_names": ["black rifle coffee"]},
  "jinx": {"keyword": "jinx dog food", "brand_names": ["jinx"]}
}
```
Jinx uses `jinx dog food` because the bare word matches unrelated products; Jinx cat food and treats can be missed. `APIFY_TOKEN` comes from `.env`.

| Constant | Value |
|---|---|
| `SEARCH_RESULTS` | 60 |
| `TOP_N` | 10 |
| `MIN_RATINGS_TO_MERGE` | 100 |
| `DETAIL_CANDIDATES` | 15 |
| `REVIEWS_PER_PRODUCT` | 10 |
| `RUN_TIMEOUT_S` | 600 |
| `RUN_MEMORY_MB` | search 512, detail 4096, reviews 256 |
| `MAX_CHARGE_USD` | search 0.10, detail 0.10, reviews 0.70 |
| `POLL_S` | 3 |
| `WAIT_MARGIN_S` | 120 |
| `CHARGE_READ_DELAY_S` | 30 |
| `HTTP_TIMEOUT_S` | 60 |

The caps are above the largest charge of each run (search $0.06, detail $0.075, reviews $0.63), so a brand costs at most $0.90 and about $0.77 when every product has 10 reviews.

## 4. Procedure
If `APIFY_TOKEN` is missing or empty, stop with `missing_token` and send nothing.

**Running an actor.** Every request below is sent once, with `Authorization: Bearer <token>` and `HTTP_TIMEOUT_S`.
1. `POST https://api.apify.com/v2/acts/<actor>/runs?timeout=<RUN_TIMEOUT_S>&memory=<RUN_MEMORY_MB>&maxTotalChargeUsd=<MAX_CHARGE_USD>` with the input as a JSON body. Keep `data.id`.
2. Every `POLL_S` seconds, `GET https://api.apify.com/v2/actor-runs/<id>` until `data.status` is `SUCCEEDED`, `FAILED`, `ABORTED` or `TIMED-OUT`. Give up after `RUN_TIMEOUT_S + WAIT_MARGIN_S` seconds.
3. If `SUCCEEDED`: `GET https://api.apify.com/v2/datasets/<defaultDatasetId>/items?format=json&clean=true`.
4. Cost is read once per brand, after the brand's last run (whatever its outcome, including an early stop): wait until `CHARGE_READ_DELAY_S` seconds after the latest `finishedAt` among the runs that ended, then `GET` each of those runs once and use its `usageTotalUsd` (F12). If a read fails, or the run never ended (step 2 gave up), use the last value seen in step 2. `cost_usd` is the sum over the brand's runs. With no ended run there is no wait and no read.

The stage error is `http_<status>` or `request_error` for a failed request, `wait_exceeded` for step 2, and `failed`, `aborted` or `timed_out` for the other end states.

**A. Search.** Run the search actor with `{"keywords": ["<keyword>"], "maxResultsPerKeyword": 60, "sortBy": "relevance", "excludeSponsored": false, "primeOnly": false, "marketplace": "us", "maxConcurrency": 1}`.

**B. Candidates.** Go through the rows in ascending `position`. A row is dropped when `isSponsored` is `true`, when an earlier kept row has the same `asin`, when `price` is not a number, or when the brand test fails. Brand test: take `brand`, collapse whitespace to single spaces, strip, and `casefold()`; it passes when it equals a name in `brand_names` or starts with that name followed by a space (F4). A kept row whose `rating` and `ratingsCount` (at least `MIN_RATINGS_TO_MERGE`) are both equal to an earlier candidate's is merged into that candidate (F5). Every other kept row is a candidate.

**C. Details.** Run the detail actor for the first `DETAIL_CANDIDATES` candidates, with `{"categoryOrProductUrls": [{"url": "https://www.amazon.com/dp/<asin>"}, ...], "maxItemsPerStartUrl": 1, "scrapeProductDetails": true, "useCaptchaSolver": false, "maxOffers": 0, "scrapeSellers": false, "scrapeProductVariantPrices": false, "maxProductVariantsAsSeparateResults": 0, "proxyCountry": "AUTO_SELECT_PROXY_COUNTRY"}`. Match each candidate to the one item whose `input` is its URL. The detail fails (`detail_error`) with `no_item` when there is none, `<error>` when the item has an `error` key, `asin_mismatch` when its `asin` differs, and `shape_changed` when it lacks `reviewsCount` or a list `variantAsins`. When the run itself fails, every candidate's `detail_error` is the stage error.

**D. Top products.** Go through the checked candidates in order. A candidate is merged into an already selected product when both details were read, their `reviewsCount` are equal integers, and one's ASIN is in the other's `variantAsins` (F8: flavors stay separate). Otherwise it is selected with the next `rank`; a candidate whose detail failed is selected too. Stop at `TOP_N`.

**E. Reviews.** Run the review actor once for the selected ASINs in rank order, with `{"ASIN_or_URL": [...], "country": "United States", "max_reviews": 10, "sort_reviews_by": ["helpful"], "filter_by_verified_purchase_only": ["all_reviews"], "filter_by_ratings": ["all_stars"], "filter_by_mediaType": ["all_contents"], "variant_scope": "all_variants", "unique_only": true, "get_customers_say": true, "include_personal_data": false, "filter_by_keywords": []}`. Group the rows by `ASIN`, keeping their order. If a row has no `ReviewId`, an `ASIN` that was not requested, or an ASIN has more than `REVIEWS_PER_PRODUCT` rows, treat the reviews as failed (`shape_changed`). In every row set `Reviewer`, `ReviewerProfileUrl`, `ReviewerId`, `Images` and `Videos` to `null` (customer media can show private individuals).

A product's reviews are `complete` when it got `REVIEWS_PER_PRODUCT` rows, or as many rows as its `RatingTypeTotalReviewsCount`, or no rows while its detail `reviewsCount` is 0. They are `failed` when the run failed, and `short` otherwise.

**Write** each selected product in rank order, followed by its reviews. A `ReviewId` already written in this run is skipped.

## 5. Output
Product record:
| Field | Value |
|---|---|
| `key` | the ASIN, for example `B006CQ1ZHI` |
| `kind` | `product` |
| `url` | `https://www.amazon.com/dp/<asin>` |
| `fetched_at` | `finishedAt` of the detail run when the detail was read, otherwise the row's `scrapedAt` |
| `raw.rank` | 1 to `TOP_N` |
| `raw.search_item` | the search row |
| `raw.merged_asins` | ASINs merged into this product in stages B and D |
| `raw.detail` | the detail item, or `null` |
| `raw.detail_error` | `null` or the error from stage C |
| `raw.reviews` | `complete`, `short` or `failed` |

Review record:
| Field | Value |
|---|---|
| `key` | `ReviewId` |
| `kind` | `review` |
| `url` | `https://www.amazon.com/portal/customer-reviews/srp/-/<ReviewId>` (needs sign-in, F10) |
| `fetched_at` | `finishedAt` of the review run |
| `raw.product_asin` | the product's ASIN (also `raw.item.ASIN`) |
| `raw.rank_in_product` | 1 to 10, the row's place among that product's rows |
| `raw.image_count` | the length of `Images` before it was removed |
| `raw.item` | the review row, with the fields above set to `null` |

Run result: `source` is `amazon`, `expected_total` is `null`, `requests` counts the HTTP requests sent to `api.apify.com`, `cost_usd` is the sum from step 4. `extra` is `{"search_rows": 60, "candidates": 27, "selected": 10}`.

| Condition, checked in this order | `status` | `reason` |
|---|---|---|
| No token | `could_not_look` | `missing_token` |
| The search run failed | `could_not_look` | `search_<stage error>` |
| The search returned 0 rows | `could_not_look` | `search_empty` (F11) |
| A search row lacks `asin`, `position` or `isSponsored` | `could_not_look` | `search_shape_changed` |
| No candidate | `could_not_look` | `no_matching_products` |
| `TOP_N` selected, or every candidate checked and 60 search rows; every detail read; every product's reviews `complete` | `ok` | empty |
| Anything else | `partial` | what applies, joined with `; `: `search_short(rows=<n>)`, `candidates_unchecked=<n>`, `details_failed=<n>`, `reviews_failed(<error>)`, `reviews_short=<n>` |

A brand with fewer than `TOP_N` distinct products among 60 rows is `ok`; Jinx can be one (its first 10 rows hold 3 distinct products).

## 6. Tests
Three pure functions, tested against the files in `part1/collectors/04_amazon/samples/apify/`. No network.

```python
def select_candidates(rows: list[dict], brand_names: list[str]) -> tuple[list[dict], dict[str, list[str]]]: ...  # candidates in position order, merged ASINs per candidate; ValueError on a bad shape
def select_top(candidates: list[str], details: dict[str, dict | None], top_n: int) -> tuple[list[str], dict[str, list[str]]]: ...  # selected ASINs, merged ASINs per selected; None = detail failed
def group_reviews(rows: list[dict], asins: list[str], per_product: int) -> dict[str, list[tuple[dict, int]]]: ...  # (row with personal fields removed, image count); ValueError on a bad shape
```

| Input | Expected |
|---|---|
| `dataset_apt_marble_dw60.json`, `["death wish coffee"]` | 27 candidates, starting `B0182HSTIM`, `B006CQ1ZHI`, `B08VFVSBXM`, `B00FM03XCU`; merged: `B0CGRPR2PW` and `B00FJYTGBG` into `B0182HSTIM`, `B00TXTNL2S` into `B006CQ1ZHI`, `B006CNTR6W` and `B00U1NFVZ0` into `B00FM03XCU`, `B0FL1VS9SH` into `B081TMDLXF`; `B0F5HZR1KB` and `B0CJ97Z6TB` (both 5.0 / 1) are separate candidates; `B081LLCJTC` (Hardcore) is not a candidate |
| same, `position` removed from one row | `ValueError` |
| rows of `dataset_apt_marble_3x10.json` with keyword `black rifle coffee`, `["black rifle coffee"]` | 9 candidates; `B01MQ62LR0` merged into `B01M8OD0LQ` |
| rows with keyword `jinx dog food`, `["jinx"]` | 3 candidates: `B0F5LZXCDH`, `B0F5LRDP8G`, `B0GGL6L1HX` |
| `dataset_apt_marble_living_proof_20.json`, `["living proof"]` | 17 candidates; `B0170GOCVO` into `B0BQ3YFRC5` |
| `select_top`: `B006CQ1ZHI`, `B08VFVSBXM` with their items from `dataset_junglee_3asins.json` | both selected |
| the same plus `B00TXTNL2S` whose detail is the `B006CQ1ZHI` item with `asin` changed | `B00TXTNL2S` merged into `B006CQ1ZHI` |
| `B00OQKOO02` with detail `None` | selected |
| `dataset_2asins_5each.json`, both ASINs, 5 | 5 rows each; `B006CQ1ZHI` starts with `R33VC4QUNQ77MM`; `Reviewer` and `Images` are `None` in every row |
| `dataset_B00OQKOO02_20.json`, `["B00OQKOO02"]`, 10 | `ValueError` (20 rows) |
| same, 20 | 20 rows; image count 1 for `R2LUGCESGD69T4`, 0 for the others |

## 7. Done when
1. The tests pass.
2. `--brand death-wish-coffee` ends `ok` with 10 product records and `cost_usd` of at most 0.90.
3. `--brand jinx` ends `ok`.
4. A second run adds new files and leaves the first run's files unchanged.
5. For three products, the live page shows the same price as `raw.detail.price.value` and the same rating count as `raw.detail.reviewsCount`. For three reviews, the review URL opened with the checker's own Amazon account shows the same title and stars.
6. No review record has a non-null `Reviewer`, `ReviewerProfileUrl`, `ReviewerId`, `Images` or `Videos`.

## 8. Where the pipeline finds each value
| Attribute | Location |
|---|---|
| product_id, rank | `key`, `raw.rank` |
| variant_family, variant | `raw.detail.variantAsins`, `raw.detail.variantAttributes` |
| search_keyword, search_position | `raw.search_item.keyword`, `raw.search_item.position` |
| bsr_main, bsr_sub (and categories) | `raw.detail.bestsellerRanks[0]`, `[1]` (`rank`, `category`) |
| title, price, list_price, unit_price | `raw.detail.title`, `raw.detail.price.value`, `raw.detail.listPrice`, `raw.search_item.unitPrice` |
| rating_avg, review_count, rating_histogram | `raw.detail.stars`, `raw.detail.reviewsCount`, `raw.detail.starsBreakdown` |
| written_review_count | `RatingTypeTotalReviewsCount` in the product's review records |
| ai_review_summary, aspect_tags | `raw.detail.aiReviewsSummary.text`, `.keywords[]`; also `CustomersSay`, `ReviewAspects` in review records |
| sales_signal, promo_badges | `raw.detail.monthlyPurchaseVolume`; `raw.search_item.isAmazonsChoice`, `isBestSeller`, `badge`, `couponText` |
| availability, seller, context | `raw.detail.inStockText`, `raw.detail.seller.name`, `raw.detail.locationText` |
| review: rating, title, body, date, country | `raw.item.ReviewScore`, `ReviewTitle`, `ReviewContent`, `ReviewDate`, `ReviewCountry` |
| review: verified, helpful_votes, reviewed_variant | `raw.item.Verified`, `HelpfulVotes`, `Variant`, `VariantASIN` |
| review: rank, image_count, source_page_url | `raw.rank_in_product`, `raw.image_count`, `raw.item.PageUrl` |
