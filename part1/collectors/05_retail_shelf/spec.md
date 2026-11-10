# Spec: source 5, retail shelf raw collector

- Shared contract: `part1/collectors/README.md`. Read it first; this document adds only what is specific to this source.
- Research notes: `part1/collectors/05_retail_shelf/source_info.md`. Where they differ from this spec (Sephora listing path, Target page count), this spec is newer.
- Every fact below was observed on 2026-11-10 from the collector's exit IP (Seattle, AS212238). If a site or an Apify actor behaves differently, or a step needs something this spec does not give, stop and report. Do not guess.

## 1. What to build
One file, `source_collector.py`. A **cell** is one brand at one retailer. For each cell of the brand it reads the retailer's listing once, picks up to 10 of the brand's products in listing order, writes one `product` record per pick, then fetches up to 10 newest reviews per product and writes one `review` record per review. No retries.

| Brand | Retailer | Listing | Reviews |
|---|---|---|---|
| `batiste` | `ulta` | own code, Playwright | own code, PowerReviews called from the Ulta page |
| `batiste` | `target` | Apify `automation-lab/target-scraper` | Apify `apify/e-commerce-scraping-tool` |
| `living-proof` | `ulta` | own code, Playwright | own code, PowerReviews called from the Ulta page |
| `living-proof` | `sephora` | Apify `igview-owner/sephora-search-scraper` | Apify `apify/e-commerce-scraping-tool` |
| `death-wish-coffee` | `target` | Apify `automation-lab/target-scraper` | Apify `apify/e-commerce-scraping-tool` |
| `black-rifle-coffee` | `target` | Apify `automation-lab/target-scraper` | Apify `apify/e-commerce-scraping-tool` |
| `jinx` | `target` | Apify `automation-lab/target-scraper` | Apify `apify/e-commerce-scraping-tool` |
| `jinx` | `chewy` | Apify `parseforge/chewy-com-scraper` | Apify `automation-lab/chewy-product-reviews-scraper` |

The other 12 brand and retailer combinations list none of the brand's products. It does not convert prices or dates, rank across cells, or keep review photos.

## 2. Facts about the sources
| # | Fact |
|---|---|
| F1 | `https://www.ulta.com/brand/<slug>` opens in headless Chrome with status 200. The listing is inline and readable right after `domcontentloaded` as `window.__APOLLO_STATE__.ROOT_QUERY`: exactly one object in it has `moduleName == "ProductListingResults"` and an `items` array (four more objects carry that `moduleName` and nothing else). Batiste has 29 items, Living Proof 45, all of the brand, none `sponsored`, in the page's default "Best Sellers" order |
| F2 | An Ulta item has `productId`, `skuId`, `brandName`, `productName`, `listPrice`, `salePrice`, `rating`, `reviewCount` (`null` without reviews), `sponsored`, `badge`, `action.url` (absolute product URL). Several products share one review pool: 5 of Batiste's first 10 show `reviewCount` 28849 and return the same reviews |
| F3 | An Ulta product page sends `GET https://display.powerreviews.com/m/6406/l/en_US/product/<productId>/reviews?apikey=<key>&_noconfig=true` only after it is scrolled (none within 30 s unscrolled; within 6 s after two wheel scrolls of 3500 px). From that page, an in-page `fetch` of `https://display.powerreviews.com/m/6406/l/en_US/product/<productId>/reviews?paging.from=0&paging.size=10&filters=&search=&sort=Newest&image_only=false&page_locale=en_US&native_only=true&apikey=<key>` returns 200 with the 10 newest Ulta reviews of any `productId`, not only the page's |
| F4 | That response has `paging.total_results` (Ulta's own reviews) and `results`, one object with `rollup` (`review_count` including reviews from other sites, `native_review_count`, `syndicated_review_count`, `rating_histogram`) and `reviews[]`. A review has `ugc_id`, `details.headline`, `details.comments`, `details.created_date`, `details.bottom_line`, `details.nickname`, `details.location`, `metrics.rating`, `metrics.helpful_votes`, `badges.is_verified_buyer`, `media` |
| F5 | Sephora answers 403 "Access Denied" to headless Chrome from this IP for search pages, and to every browser for brand and product pages. There is no own-code path |
| F6 | `igview-owner/sephora-search-scraper` with `sortBy` `BEST_SELLING` returned Living Proof in the order a person's Chrome showed for Bestselling (`P525776`, `P449379`, `P399330`). Items have `page`, `position`, `productId`, `skuId`, `brandName`, `displayName`, `listPrice`, `rating`, `reviews`, `sponsored`, `onSaleData`, `productUrl`; there is no sale price. Its `minRating`, `minPrice`, `maxPrice` default to 4, 25, 50; all 57 Living Proof products have a rating of at least 1 and a price from $17 to $168. Its minimum memory is 4096 MB, so the start is charged 4 × $0.02; with a cap of $0.09 it saved no items |
| F7 | `automation-lab/target-scraper` with `storeId` "2581" and `zipCode` "95054" returns rows for the store San Jose North, in ascending `position` (sponsored rows counted). Price and sponsored flag matched a person's Chrome at that store. Rows have `tcin`, `parentTcin` (often `null`), `title`, `brand`, `itemType`, `isMarketplace`, `isSponsored`, `price`, `priceString`, `regularPrice`, `onSale`, `rating`, `reviewCount` (0 and 0 without reviews), `url`, `storeId`. With several search terms in one run, a TCIN returned for an earlier term is left out of later ones |
| F8 | Target `brand` "Jinx" also covers another company's goods (`isMarketplace` true, `itemType` Wallets, Costume Accessories, Stuffed Dolls); the dog food is `itemType` Pet Food or Pet Treats. Sizes and flavors of one product share `parentTcin` and `reviewCount`. Death Wish Coffee Co has 9 products in the first 24 rows and none in the next 24 |
| F9 | `parseforge/chewy-com-scraper` returns rows with `partNumber`, `name`, `manufacturer` ("Jinx"), `url`, `price`, `displayPrice`, `strikePrice`, `pricePerUnit`, `autoshipPrice`, `rating`, `ratingCount`, `inStock`. Prices matched a person's Chrome. Its order matches neither the site's Relevance nor its Bestselling order; `arcana/chewy-com-scraper` returns the same order |
| F10 | `apify/e-commerce-scraping-tool` with one Target or Sephora product URL returns that product's newest reviews with `reviewBody`, `name` (the review title), `datePublished`, `reviewRating.ratingValue`, `inputUrl` (the URL sent), `author` (the reviewer's name). There is no review ID. Its cap must be at least $1.00. For Chewy it returned nothing in 9 minutes |
| F11 | `automation-lab/chewy-product-reviews-scraper` with one product URL returns its newest reviews with `reviewId`, `rating`, `title`, `reviewText`, `reviewDate`, `helpfulVotes`, `isIncentivized`, `contributorBadge`, `reviewerName`, `sourceUrl`, and the product's `ratingCount`, `reviewCount`, `rating1Count` to `rating5Count` |
| F12 | A run's `usageTotalUsd` becomes final about 10 s after its status first reads `SUCCEEDED` |
| F13 | From inside an open ulta.com page, `fetch(<product url>, {credentials: "include"})` returns 200 and the page HTML (about 1 MB). Among its `<script type="application/ld+json">` blocks, one is a `Product` whose `sku` equals the URL's `sku` and which has `offers` (`price`, `priceCurrency`, `availability`); the price was seen both as a number (`33`) and as a numeric string (`"20.99"`), the availability both as `InStock` and as `https://schema.org/InStock`; a `ProductGroup` block lists every size under `hasVariant` as `Product` objects with a `sku` but no `offers`. The `Product` block also holds a `review` list with reviewers' names, which is never stored. For a product sold in several sizes the listing shows a range and the URL's page shows one size's price: listing 12.99-20.99, 18-45 and 4.99-6.99 gave page prices 20.99, 33 and 5.99 (2026-11-10) |

Samples for all of these are in `part1/collectors/05_retail_shelf/samples/` (`ulta/`, `sephora/`, `apify/`, `chewy/`, `target_screen/`).

## 3. Input
`brand_inputs.json`:
```json
{
  "batiste": [
    {"retailer": "ulta", "list_url": "https://www.ulta.com/brand/batiste", "brand_name": "Batiste"},
    {"retailer": "target", "search_term": "batiste", "brand_name": "Batiste", "item_types": null}],
  "living-proof": [
    {"retailer": "ulta", "list_url": "https://www.ulta.com/brand/living-proof", "brand_name": "Living Proof"},
    {"retailer": "sephora", "search_term": "living proof", "brand_name": "Living Proof"}],
  "death-wish-coffee": [{"retailer": "target", "search_term": "death wish coffee", "brand_name": "Death Wish Coffee Co", "item_types": null}],
  "black-rifle-coffee": [{"retailer": "target", "search_term": "black rifle coffee", "brand_name": "Black Rifle Coffee Company", "item_types": null}],
  "jinx": [
    {"retailer": "target", "search_term": "jinx dog food", "brand_name": "Jinx", "item_types": ["Pet Food", "Pet Treats"]},
    {"retailer": "chewy", "search_term": "jinx dog food", "brand_name": "Jinx"}]
}
```
`APIFY_TOKEN` comes from `.env`.

| Constant | Value |
|---|---|
| `PRODUCTS_PER_CELL` | 10 |
| `NAV_TIMEOUT_S` | 45 |
| `REVIEW_KEY_WAIT_S` | 20 |
| `REVIEW_FETCH_TIMEOUT_S` | 20 |
| `ULTA_SPACING_S` | 3 |
| `MAX_FAILURES_IN_A_ROW` | 3 |
| `APIFY_TIMEOUT_S` | 300 |
| `APIFY_POLL_S` | 10 |
| `APIFY_COST_WAIT_S` | 15 |

## 4. Procedure
Cells run in the order of `brand_inputs.json`, one request at a time. A failed cell does not stop the next one.

**Apify call.** Standard library HTTP, header `Authorization: Bearer <APIFY_TOKEN>`.
1. With no token, make no request: the cell is `could_not_look`, `missing_token`.
2. `POST https://api.apify.com/v2/acts/<actor>/runs?timeout=<APIFY_TIMEOUT_S>&maxTotalChargeUsd=<cap>` with the body below (`<actor>` with `/` written as `~`). Not 201: failure `apify_start: http_<status>`.
3. `GET https://api.apify.com/v2/actor-runs/<id>` every `APIFY_POLL_S` until `data.status` is `SUCCEEDED`, `FAILED`, `ABORTED` or `TIMED-OUT`. Still running `APIFY_TIMEOUT_S + 60` s after the POST: failure `apify_wait_timeout`. A poll that fails: failure `apify_poll: <message>`.
4. Any end other than `SUCCEEDED`: failure `apify_<status in lower case>`. On `SUCCEEDED`, `GET https://api.apify.com/v2/datasets/<data.defaultDatasetId>/items?clean=true&format=json`; if it fails, failure `apify_dataset: <message>`.
5. Keep every run ID. When the brand's last cell is done, wait `APIFY_COST_WAIT_S`, GET each run once and add up `usageTotalUsd` into `cost_usd` (F12). A run whose GET fails counts with the last value read.

| Use | Actor | Body | Cap |
|---|---|---|---|
| Target listing | `automation-lab~target-scraper` | `{"searchQueries": [<search_term>], "maxProductsPerSearch": 24, "maxSearchPages": 1, "storeId": "2581", "zipCode": "95054", "sort": "relevance"}` | 0.05 |
| Sephora listing | `igview-owner~sephora-search-scraper` | `{"keyword": <search_term>, "maxPages": 1, "pageSize": 10, "sortBy": "BEST_SELLING", "minRating": 1, "minPrice": 0, "maxPrice": 10000}` | 0.35 |
| Chewy listing | `parseforge~chewy-com-scraper` | `{"searchTerm": <search_term>, "maxItems": 15}` | 0.15 |
| Target or Sephora reviews | `apify~e-commerce-scraping-tool` | `{"reviewDetailsUrls": [{"url": <product url>}], "maxReviewResults": 10, "sortReview": "Most recent", "additionalReviewProperties": true}` | 1.00 |
| Chewy reviews | `automation-lab~chewy-product-reviews-scraper` | `{"productUrls": [{"url": <product url>}], "maxReviews": 10, "maxReviewsPerProduct": 10, "sort": "newest"}` | 0.05 |

One search term per Target run (F7). The Sephora filters are set because leaving them out applies the defaults (F6). A `--all` run costs about $1.55, mostly review runs.

**Listing.**
- Ulta: Playwright, `chromium.launch(headless=True, channel="chrome")`, context `locale="en-US"`, one page for the cell. Open `list_url` (`domcontentloaded`, `NAV_TIMEOUT_S`). **Blocked** means the document status is 400 or higher, or the title or text contains `Access Denied`, `captcha` or `unusual traffic`. Read `ROOT_QUERY` and take the one `ProductListingResults` object (F1); its `items` are the rows.
- Target, Sephora, Chewy: one Apify call. Target rows in ascending `position`; Sephora rows by `page`, then `position`; Chewy rows as returned. Every Target row must have `storeId` "2581".
- A row must have the keys the selection and the record use: Ulta `productId`, `brandName`, `reviewCount`, `action.url`; Target `tcin`, `position`, `brand`, `isMarketplace`, `itemType`, `parentTcin`, `reviewCount`, `url`, `storeId`; Sephora `page`, `position`, `productId`, `brandName`, `reviews`, `productUrl`; Chewy `partNumber`, `manufacturer`, `ratingCount`, `url`.

**Selection.** Go through the rows in order and keep a row when it matches the brand: Ulta and Sephora `brandName == brand_name`; Chewy `manufacturer == brand_name`; Target `brand == brand_name`, `isMarketplace` false, and `itemType` in `item_types` when that is not `null` (F8). Target only: skip a row whose `parentTcin` is not `null` and whose `parentTcin` and `reviewCount` equal those of a kept row (F8). Stop at `PRODUCTS_PER_CELL`. Sponsored rows count like any other. Fewer than 10 is the full scope, not a failure (Death Wish at Target has 9).

**Ulta product pages.** For every selected product of an Ulta cell, before the reviews: wait `ULTA_SPACING_S`, then fetch the product's URL from the open page with `page.evaluate` and `fetch(url, {credentials: "include"})` (one attempt, counted in `requests`). On status 200, `product_page_offer(html, skuId)` reads the `Product` JSON-LD object whose `sku` equals the listing item's `skuId` (top level, list items or `@graph` only, never `hasVariant`) and returns only `{sku, price, currency, availability}` (the part after the last `/`); `ValueError` `product_ld_not_found` otherwise, or `price_not_number` unless the price is a finite number or a plain decimal string (returned as received), and greater than 0. Status 403 or 429 is `failed` with `blocked: http_<status>`, any other status `failed` with `http_<status>`, an exception `failed` with `browser: <message>`. After a 403 or 429, or `MAX_FAILURES_IN_A_ROW` failed pages in a row, the remaining products get `not_attempted`. Reviews are fetched as before, whatever happened to the page. Neither the JSON-LD block nor the HTML is stored.

**Reviews.** A product whose listed review count (Ulta and Target `reviewCount`, Sephora `reviews`, Chewy `ratingCount`) is `null` or 0 gets `reviews_state` `none` and no request. For the others:
- Ulta: open the first such product's `action.url` (same timeout and block test as the list page), wait 3 s, scroll `page.mouse.wheel(0, 3500)` twice 2.5 s apart, and wait up to `REVIEW_KEY_WAIT_S` for the PowerReviews request; take its `apikey` (F3). If the page does not load, is blocked, or no request comes, these products get `failed` with `browser: <message>`, `blocked` or `review_key_not_found`. Otherwise fetch the F3 URL once per product from that page with `page.evaluate` and `fetch(url, {signal: AbortSignal.timeout(REVIEW_FETCH_TIMEOUT_S * 1000)})`. Status 403 or 429 is `blocked`. Leave `ULTA_SPACING_S` between all Ulta navigations and fetches.
- Target and Sephora: one e-commerce call per product with the product record's `url`. Chewy: one Chewy reviews call per product.
- `fetched` when the response has the expected shape: Ulta `results[0].reviews` is a list; e-commerce items have `reviewBody`, `datePublished` and `inputUrl` equal to the URL sent; Chewy items have `reviewId`. Otherwise `failed` with `http_<status>`, `timeout`, `invalid` or the Apify failure.
- After `MAX_FAILURES_IN_A_ROW` failed products in a row, or one `blocked`, the cell's remaining products get `not_attempted`.
- Personal data: Ulta sets `details.nickname`, `details.location` and `media` to `null`; e-commerce deletes `author`; Chewy deletes `reviewerName`.

**Writing.** Review records are written as each response is handled. A cell's product records are written when its reviews are done, because they carry `reviews_state`; an unexpected exception writes them as they are before the run result.

## 5. Output
| Field | `product` | `review` |
|---|---|---|
| `key` | `<retailer>:<product id>`: Ulta `productId`, Target `tcin`, Sephora `productId`, Chewy `partNumber` | `<product key>:<review id>`: Ulta `ugc_id`, Chewy `reviewId`, Target and Sephora `"h" + sha256(datePublished + "\n" + reviewBody).hexdigest()[:16]` (no ID is given, F10) |
| `url` | Ulta `action.url`, Target `url`, Sephora `productUrl`, Chewy `url` | Ulta the product URL, Target and Sephora `inputUrl`, Chewy `sourceUrl` |
| `fetched_at` | When the listing was read | When the review response arrived |
| `raw` | `{"retailer", "rank", "listing_item", "product_page", "reviews_state", "reviews_error", "reviews_meta"}` | `{"retailer", "product_key", "review"}` |

- `listing_item` is the row as received. `rank` is 1 to n in selection order. `reviews_state` is `fetched`, `none`, `failed` or `not_attempted`; `reviews_error` is `null` or the failure text. `reviews_meta` is Ulta's `{"total_results": <paging.total_results>, "rollup": <results[0].rollup>}`, otherwise `null`.
- `product_page` is `null` except for Ulta: `{"state", "error", "sku", "price", "currency", "availability"}`, `state` `fetched`, `failed` or `not_attempted`, `error` `null` or the failure text (`sku_missing` when the listing item has no `skuId`: no request is made, and it counts as a failed page), the last four `null` unless `fetched`.
- `review` is the review as received, after the personal data is removed. The same Ulta review can appear under several products of one pool (F2); the product in the key keeps them apart.

Run result: `source` is `retail_shelf`, `expected_total` is `null`, `requests` counts page navigations, Ulta product-page fetches, in-page review fetches and Apify runs. `extra` is `{"cells": [{"retailer": "ulta", "status": "ok", "reason": "", "selected": 10}]}`.

| Cell condition, checked in this order | Cell `status` | Cell `reason` |
|---|---|---|
| Apify cell without token | `could_not_look` | `missing_token` |
| Chrome did not start or the list page did not load; the Apify listing call failed | `could_not_look` | `browser: <message>` or the Apify failure |
| The Ulta list page is blocked | `could_not_look` | `blocked` |
| No rows, or a row lacks a needed key, or the Ulta module is not found exactly once | `could_not_look` | `list_empty` or `list_shape_changed` |
| A Target row has another `storeId` | `could_not_look` | `store_mismatch` |
| Rows, but none matches the brand | `could_not_look` | `brand_matched_none` |
| Every selected product is `fetched` or `none` (Ulta: and every product page is `fetched`) | `ok` | empty |
| Anything else | `partial` | what applies, joined with `; `: `review_key_not_found`, `reviews_blocked`, `reviews_failed=<n>`, `reviews_not_attempted=<n>`, `product_pages_failed=<n>`, `product_pages_not_attempted=<n>` |

The run's `status` is `ok` when every cell is `ok`, `could_not_look` when every cell is `could_not_look`, otherwise `partial`. Its `reason` joins, with ` | `, `<retailer>: <cell reason>` for every cell that is not `ok`. Example: Batiste without a token is `partial`, `target: missing_token`.

## 6. Tests
Three pure functions, tested against the sample files. No network.

```python
def find_listing_module(root_query: dict) -> dict: ...  # raises ValueError unless exactly one match
def select(retailer: str, rows: list[dict], cell: dict) -> list[dict]: ...
def review_key(product_key: str, retailer: str, review: dict) -> str: ...
```

| Input (in `samples/`) | Expected |
|---|---|
| `{"a": [<module of ulta/listing_module_batiste.json>], "b": {"parentModule": {"moduleName": "ProductListingResults"}}}` | returns the module, 29 items |
| `{"b": {"parentModule": {"moduleName": "ProductListingResults"}}}` | `ValueError` |
| `ulta/listing_module_batiste.json` items, Batiste Ulta cell | 10 rows; `productId` first `pimprod2045775`, third `xlsImpprod2040049`, last `xlsImpprod15622775` |
| `apify/target_al_store2581_4brands.json` items with `searchQuery` `batiste` | 10 rows; `tcin` first `75561114`, last `80164128`; 5 with `isSponsored` |
| same file, `death wish coffee` | 9 rows; first `95098364`, last `94459851` |
| same file, `jinx dog food`, Jinx Target cell | 10 rows; none with `isMarketplace` true; `86020323` and `89559952` skipped; first `88766771`, last `94961044` |
| `apify/sephora_search_igview_bestselling_3.json` items | `P525776`, `P449379`, `P399330` |
| `apify/chewy_search_jinx_parseforge.json` items | 10 rows; first `845310`, last `1709326` |
| first review of `ulta/powerreviews_size10_pimprod2037265.json` (`response.results[0].reviews`), product key `ulta:pimprod2037265` | `ulta:pimprod2037265:589696061` |
| first item of `apify/target_reviews_A-88498115.json`, product key `target:88498115` | `target:88498115:h27cef09620e38f8f`; the 10 items give 10 different keys |
| first item of `apify/chewy_reviews_alc_845310.json`, product key `chewy:845310` | `chewy:845310:UmV2aWV3OjE5MDU5MDIy` |

## 7. Done when
1. The tests pass.
2. `--brand batiste`, `--brand living-proof` and `--brand jinx` each end `ok` with `selected` 10 in every cell.
3. `--brand death-wish-coffee` ends `ok`, and its `selected` equals the Death Wish Coffee Co rows in that run's listing (at most 10).
4. A second run adds new files and leaves the first run's files unchanged.
5. For three products per cell, the live product page shows the same rating, review count and price text as `listing_item` (Target with the store set to San Jose North).
6. Without `APIFY_TOKEN`, Batiste ends `partial` with its Ulta records written, and Death Wish ends `could_not_look`; no Apify request is sent.
7. No review record has `author` or `reviewerName`, and every Ulta review has `details.nickname` `null`.

## 8. Where the pipeline finds each value
`li` is `raw.listing_item`, `r` is `raw.review`.

| Attribute | Ulta | Target | Sephora | Chewy |
|---|---|---|---|---|
| rank / position in listing | `raw.rank` / list order | `raw.rank` / `li.position` | `raw.rank` / `li.position` | `raw.rank` / list order |
| sort the rank is based on | Best Sellers (page default) | relevance, store 2581 | Bestselling | actor's order, basis unknown (F9) |
| sponsored | `li.sponsored` | `li.isSponsored` | `li.sponsored` | not given |
| title | `li.productName` | `li.title` | `li.displayName` | `li.name` |
| price as shown | `raw.product_page.price` (the size in the URL; `li.listPrice` is the listing card's range, `li.salePrice` its sale price) | `li.priceString` (`li.price`, `li.regularPrice`) | `li.listPrice` (`li.onSaleData`) | `li.displayPrice` (`li.strikePrice`, `li.autoshipPrice`) |
| rating, review count | `li.rating`, `li.reviewCount` | `li.rating`, `li.reviewCount` | `li.rating`, `li.reviews` | `li.rating`, `li.ratingCount` |
| own / other-site reviews, histogram | `raw.reviews_meta.rollup` | no | no | in `r` of its reviews |
| review rating, title, body, date | `r.metrics.rating`, `r.details.headline`, `r.details.comments`, `r.details.created_date` | `r.reviewRating.ratingValue`, `r.name`, `r.reviewBody`, `r.datePublished` | same as Target | `r.rating`, `r.title`, `r.reviewText`, `r.reviewDate` |
| verified, helpful, incentivized | `r.badges.is_verified_buyer`, `r.metrics.helpful_votes`, no | no; Target bodies of promotion reviews start with `[This review was collected as part of a promotion.]` | no | no, `r.helpfulVotes`, `r.isIncentivized` |
