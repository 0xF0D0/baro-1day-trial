# Spec: source 10, brand site and emails raw collector

- Shared contract: `part1/collectors/README.md`. Read it first; this document adds only what is specific to this source.
- Research notes: `part1/collectors/10_brand_site_and_emails/source_info.md`. Where they differ from this spec, this spec is newer.
- Every fact below was observed on 2026-11-10 from a US IP. If a site behaves differently, or a step needs something this spec does not give, stop and report (section 9). Do not guess.

## 1. What to build
One file, `source_collector.py`. Given a brand, it collects three **parts** and writes one record per item:

| Part | What | Record kinds |
|---|---|---|
| `prices` | The products and prices on the brand's own site. Batiste shows no prices on its site, so for Batiste it is what the site's where-to-buy widget returns for each product barcode (EAN) | `product`, `retailer_availability` |
| `offers` | Fixed elements of the home page, and the brand's public Klaviyo form list | `offer_slot`, `klaviyo_form` |
| `emails` | The emails received in the first 24 hours after the brand's signup, read from redacted `.eml` files in this folder. The collector never connects to an inbox | `email` |

Route per brand (exact values in section 3):

| Brand | `prices` | `offers` | `emails` |
|---|---|---|---|
| `batiste` | where-to-buy API (`wtb-api-hub.swaven.com`), plain HTTP | home page | not signed up |
| `living-proof` | Shopify `products.json`, in Chrome | home page + Klaviyo | `.eml` files |
| `death-wish-coffee` | Shopify `products.json`, in Chrome | home page + Klaviyo | `.eml` files |
| `black-rifle-coffee` | Apify actor `apify/e-commerce-scraping-tool` (paid) | home page + Klaviyo | `.eml` files |
| `jinx` | Shopify `products.json`, in Chrome | home page + Klaviyo | not signed up |

It does not extract prices, offer texts or email contents, does not decide what is current, and does not read the Black Rifle manual snapshot (section 3). It never stores a full home page (F9).

## 2. Facts about the source
| # | Fact | Evidence |
|---|---|---|
| F1 | The Living Proof, Death Wish Coffee and Jinx home pages open in headless Chrome (`channel="chrome"`) with status 200. The load event comes within 10 s. On each, `window.Shopify.country` is `US` and `window.Shopify.currency.active` is `USD`. The Batiste home opens with status 200 and has no `window.Shopify` | probe 10:43 UTC |
| F2 | In the same browser, `https://<host>/products.json?limit=250&page=1` returns 200 `application/json; charset=utf-8` with 66 (Living Proof), 165 (Death Wish Coffee) and 73 (Jinx) products, within 6 s. `page=2` returns `{"products":[]}` | probe; `products_jinx_page1_full.json`, `products_page2_empty.json` |
| F3 | The response is `{"products": [...]}`. Every product has an integer `id`, a string `handle` and a list `variants`; every variant has `id` and `price` (a string such as `"30.00"`). There is no currency field. The product page is `https://<host>/products/<handle>` | `products_*.json` |
| F4 | Black Rifle blocks the collector's own access: curl gets 403 "Attention Required! \| Cloudflare", and in Playwright Chrome the home page sends itself to `blackriflecoffee.com/url?q=https://www.google.com/` about 3 s after loading (2 of 2 tries). By the owner's rule this path was not tried again; Black Rifle prices come from Apify instead | `source_info.md` section 2 |
| F5 | Seen once on the Black Rifle home in a normal (not automated) browser: announcement bar `announcement-bar .swiper-slide`, bundle cards `product-carousel product-card`. Never checked in headless Chrome (F4) | `offers_blackrifle.json` |
| F6 | Home slots, counted 8 s after the load event (the selectors are in section 3): Living Proof `announcement_bar` 3, `banner_heading` 2, `free_shipping_message` 3, `footer_newsletter` 1, `gift_with_purchase` 1; Death Wish Coffee `announcement_bar` 1, `banner_heading` 9, `footer_newsletter` 1; Jinx `announcement_bar` 2, `hero_retailer_button` 1, `free_shipping_message` 1, `column_heading` 6, `cart_note` 1; Batiste `community_signup` 1 | probe 10:43 UTC; `home_slots/*.html` |
| F7 | Living Proof's free-shipping threshold is the attribute `data-limit="50"` on `p.cart__message`; Jinx's is `data-free-shipping-limit="65"` on `div.drawer__message` | `home_slots/living-proof.html`, `home_slots/jinx.html` |
| F8 | The Klaviyo popup forms do not appear in the headless home DOM within 8 s. `GET https://static-forms.klaviyo.com/forms/api/v7/<company id>/full-forms` returns 200 `application/json` without login. Its top-level keys are `company_sender_settings`, `dynamic_info_config`, `form_settings`, `full_forms`. Every element of `full_forms` has a string `form_id`. Forms: Living Proof 5 at 05:19 UTC and 2 at 10:47 UTC, so the list changes during the day; Death Wish Coffee 16, Black Rifle 16, Jinx 0. Batiste has no Klaviyo account. The list does not say whether a form is currently shown | probe 10:47 UTC; `klaviyo_forms_*.json` (05:19 UTC) |
| F9 | Full home pages contain private persons' names: the Death Wish Coffee banner slides include customer quotes signed "- CORY" and "- VALHALLA JUNKIE", and the Living Proof page carries a Yotpo review widget. The slots in section 3 hold none of this | probe 10:43 UTC (the full pages were not kept, for this reason) |
| F10 | `https://www.batistehair.com/batiste-products` returns 200 HTML with 33 distinct links `href="/products/..."`. The Batiste category pages list only products that are also on it. `/sitemap.xml` and missing pages return status 200 with the title `404 \| Batiste` | `batiste/listing_batiste-products.html`, `batiste/page_404_sitemap.html`; probe of 4 more pages |
| F11 | Of the 33 product pages (plain GET, 4 s apart), 28 return 200 with exactly one `<a>` tag carrying `data-mm-wtbid="679a839e96a96e0f672b1fcc"` and `data-mm-ids="<EAN>,<EAN>,..."`. They have 1 to 7 EANs each, 63 EANs in all, and no EAN is on two pages. The other 5 (`fragrance-wildflower` and the four `leave-in-hair-mask` pages) end on the listing page. Fetched without following redirects, `repair-hair-mask` returns `301` with `Location: https://www.batistehair.com/batiste-products` | `batiste/product_pages_probe.json`, `batiste/product_page_fragrance-bare.html` |
| F12 | A plain GET of `https://wtb-api-hub.swaven.com/wtb/v2/api/search/availabilities/<EAN>?wtbid=679a839e96a96e0f672b1fcc&lang=en&country=US&nextEndpointV2=true&applyTiedHouseLaw=true`, with no `Origin` or `Referer`, returns 200 JSON identical to what the widget receives. Keys include `d` (retailer and store rows with `rname`, `sid`, `sname`, `pr`, `currency`, `av`, `shd`, `carturl`, store address and phone), `prd` (`ean` equals the requested EAN), `loc` (Washington D.C., `Country` `US`, `ISOCurrencySymbol` `USD`, `IsDefaultLocation` `true`) and `cfg` (`displayprices` `false`). `next` and `next2` are `null` | `batiste/wtb_availabilities_5010724526705_full.json`, `batiste_wtb_availabilities_trimmed.json` |
| F13 | The API refuses single products. EAN `5010724008355` (third in order) answered **403** with the body `{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.4","title":"Forbidden","status":403,"detail":"Unauthorized ProductUIDs 5010724008355"}` in two full runs four hours apart (2026-11-10, 2026-11-11) and in direct requests, while the EANs before and after it answered 200 immediately afterwards. So this 403 is a refusal of that product, not a block of the client. (An earlier probe saw a 403 for `5010724538913` after two successes; it was not investigated.) | runs of 2026-11-10 and 2026-11-11; direct requests |
| F14 | Apify actor `apify/e-commerce-scraping-tool` (ID `2APbAvDfNDOWXbkWf`) charges per event and refuses a run cap below $1 (`minimalMaxTotalChargeUsd` 1). Prices: start $0.0001, listing page $0.0005, product $0.006, plus $0.003 residential proxy, $0.0006 browser rendering and $0.0015 unblocker per product when used | `apify/actor_pricing_current.json` |
| F15 | Run 2 used exactly the input in section 4.4 and was `SUCCEEDED` after 107 s, with 55 items, an empty error dataset and `usageTotalUsd` 0.4271 (55 products, 32 residential proxy, 2 listing pages, 1 start). Its log has the line `Found 55 products in the listing page: https://www.blackriflecoffee.com/collections/coffee. Page: 1` (printed twice). Every item has exactly the keys `url`, `name`, `offers`, `gtin`, `brand`, `image`, `description`, `reviewCount`, `rating`, `inputUrl`, `marketplace`, `scrapedAt`. `offers` is `{price (number), priceText, priceCurrency: null, availability: null}`. There is no `additionalProperties`, although it was requested | `apify/blackrifle_run2_*` |
| F16 | Run 1, with a different input (`maxProductResults` 5), returned another shape: the items from the listing carried `additionalProperties` (per-size `variants`, `sku`), `offers.priceCurrency` `USD` and `offers.price` as a string. Its log has `Found 10 products in the listing page: ... Page: 1` and `The maximum number of results per run has been reached.` | `apify/blackrifle_run1_*` |
| F17 | Apify API: `POST https://api.apify.com/v2/acts/apify~e-commerce-scraping-tool/runs?maxTotalChargeUsd=1&timeout=3600` returns 201 with `data.id`. `GET /v2/actor-runs/<id>?waitForFinish=60` returns the run object with `data.status`, `data.usageTotalUsd`, `data.defaultDatasetId`, `data.storageIds.datasets.errors`, `data.userId` and signed URLs in `data.output`. Items come from `GET /v2/datasets/<id>/items?clean=true&format=json`, the log from `GET /v2/logs/<id>` | run 2 calls; `apify/blackrifle_run2_run.json` |
| F18 | The three redacted `.eml` files are ASCII with CRLF line ends. They have `From`, `Subject`, `Date`, `X-Trial-Gmail-Id`, `X-Trial-Received-At` (Gmail receive time, UTC, whole seconds), `X-Trial-Gmail-Labels`, `X-Trial-Redaction`, and `To: TRIAL_INBOX <trial_inbox@redacted.invalid>` | `eml/*.eml` |
| F19 | The inbox was searched once, at 2026-11-10T07:26:17Z, for the three sender domains. The spam folder was not searched. One email per brand was found. The Death Wish Coffee email arrived 3 s **before** the recorded `signup_at`, because `signup_at` was recorded after the submit click finished | export session log; `eml/`; `part1/data/email_signups.json` (`note`) |
| F20 | `part1/data/email_signups.json` lists Batiste and Jinx as `not_signed_up` with `signup_at` `null`. Black Rifle is `submitted_unconfirmed`, although its email arrived 94 s after `signup_at` | `part1/data/email_signups.json`, `eml/` |

Samples are in `part1/collectors/10_brand_site_and_emails/samples/`:
- `products_*`;
- `home_slots/<brand>.html`: only the slot elements, cut from the pages of F6;
- `klaviyo_forms_*.json`;
- `batiste/`;
- `batiste_wtb_availabilities_trimmed.json`;
- `apify/blackrifle_run1_*` and `apify/blackrifle_run2_*`;
- `eml/`.

## 3. Input
`brand_inputs.json`:
```json
{
  "batiste": {
    "home": {"url": "https://www.batistehair.com/", "host": "www.batistehair.com", "shopify_market_check": false,
             "slots": {"community_signup": "div#footer-signup"}},
    "klaviyo_company_id": null,
    "prices": {"route": "batiste_wtb", "listing_url": "https://www.batistehair.com/batiste-products", "wtbid": "679a839e96a96e0f672b1fcc"},
    "email_sender_domains": []
  },
  "living-proof": {
    "home": {"url": "https://www.livingproof.com/", "host": "www.livingproof.com", "shopify_market_check": true,
             "slots": {"announcement_bar": "div.announcement__text:not(.ticker__comparitor) > p",
                       "banner_heading": "div.banner-image__heading",
                       "free_shipping_message": "p.cart__message[data-limit]",
                       "footer_newsletter": "form[id^=\"NewsletterForm--newsletter\"]",
                       "gift_with_purchase": "div.gwp-block.gwp-popup"}},
    "klaviyo_company_id": "H99sYH",
    "prices": {"route": "shopify_products_json", "host": "www.livingproof.com"},
    "email_sender_domains": ["livingproof.com"]
  },
  "death-wish-coffee": {
    "home": {"url": "https://www.deathwishcoffee.com/", "host": "www.deathwishcoffee.com", "shopify_market_check": true,
             "slots": {"announcement_bar": "p.announcement-bar__message",
                       "banner_heading": "h2.banner__heading",
                       "footer_newsletter": "div.newsletter__wrapper"}},
    "klaviyo_company_id": "Q6RhjR",
    "prices": {"route": "shopify_products_json", "host": "www.deathwishcoffee.com"},
    "email_sender_domains": ["deathwishcoffee.com"]
  },
  "black-rifle-coffee": {
    "home": {"url": "https://www.blackriflecoffee.com/", "host": "www.blackriflecoffee.com", "shopify_market_check": false,
             "slots": {"announcement_bar": "announcement-bar .swiper-slide",
                       "bundle_cards": "product-carousel product-card"}},
    "klaviyo_company_id": "XU3JTE",
    "prices": {"route": "apify_ecommerce", "listing_url": "https://www.blackriflecoffee.com/collections/coffee"},
    "email_sender_domains": ["blackriflecoffee.com"]
  },
  "jinx": {
    "home": {"url": "https://www.thinkjinx.com/", "host": "www.thinkjinx.com", "shopify_market_check": true,
             "slots": {"announcement_bar": "announcement-bar",
                       "hero_retailer_button": "a.btn--primary[href*=\"walmart.com\"]",
                       "free_shipping_message": "div.drawer__message[data-free-shipping-limit]",
                       "column_heading": "h2.column__heading",
                       "cart_note": "em.cart__note"}},
    "klaviyo_company_id": "V2u2jn",
    "prices": {"route": "shopify_products_json", "host": "www.thinkjinx.com"},
    "email_sender_domains": []
  }
}
```
- Death Wish Coffee uses `h2.banner__heading`, not the whole banner box, because the banner boxes of customer-quote slides end with the customer's name (F9).
- Black Rifle's home is still opened once per run, so the block is recorded each time (F4). Its slots come from F5.
- `shopify_market_check` is `false` for Black Rifle because its prices do not come from its site; their currency is checked on the Apify items (4.4).
- `email_sender_domains` is empty for the two brands that have not signed up. It gets filled from their first real email (section 9).

Other files the collector reads:

| File | Use |
|---|---|
| `part1/collectors/brands.json` | Brand `name` for each slug |
| `part1/data/email_signups.json` | Signup time and page per brand (F20). Read only; the main thread owns it |
| `part1/collectors/10_brand_site_and_emails/inbox_export/export.json` and the `.eml` files next to it | The inbox export (below) |
| `.env` at the repository root | `APIFY_TOKEN` |

**Inbox export.** The inbox is read outside the collector, by the procedure in section 12 of `source_info.md`. That procedure:
- searches the sender domains;
- writes one redacted `.eml` per message into `inbox_export/` with `part1/collectors/10_brand_site_and_emails/tools/redact_eml.py`;
- checks the files with `verify_eml.py`;
- rewrites `export.json` to describe that search.

The folder now holds the export of F19:
```json
{
  "exported_at": "2026-11-10T07:26:17Z",
  "query": "{from:livingproof.com from:deathwishcoffee.com from:blackriflecoffee.com}",
  "searched_domains": ["livingproof.com", "deathwishcoffee.com", "blackriflecoffee.com"],
  "spam_checked": false,
  "messages": [
    {"gmail_id": "1a1c3c89e9e9cf7d", "file": "deathwish_20261110T044745Z_1a1c3c89e9e9cf7d.eml"},
    {"gmail_id": "1a1c3c946076193d", "file": "livingproof_20261110T044829Z_1a1c3c946076193d.eml"},
    {"gmail_id": "1a1c3d099d8be175", "file": "blackrifle_20261110T045627Z_1a1c3d099d8be175.eml"}
  ]
}
```

| Field | Meaning |
|---|---|
| `exported_at` | When the search ran |
| `searched_domains` | Every sender domain in the query |
| `spam_checked` | `true` only if the spam folder was searched too |
| `messages` | Every message the search returned, each with its file name |

**Manual snapshot.** A `products.json` that the owner saves by hand from a normal browser goes to `part1/collectors/10_brand_site_and_emails/manual/black-rifle-coffee/products_<UTC time as YYYYMMDDTHHMMSSZ>.json`. The collector does not read this folder. The pipeline loads it separately as a manual snapshot.

| Constant | Value | Used in |
|---|---|---|
| `NAV_TIMEOUT_S` | 45 | every Chrome navigation (F1, F2: within 10 s) |
| `HOME_SETTLE_S` | 8 | wait after the home load event (F6 was counted this way) |
| `HTTP_TIMEOUT_S` | 30 | every plain HTTP request, except the Apify poll |
| `SPACING_S` | 4 | minimum gap between two requests the collector sends to the same host (F11 used 4 s). Requests to different hosts need no gap. Does not apply to `api.apify.com` |
| `PRODUCTS_PAGE_SIZE` | 250 | 4.3 |
| `MAX_PRODUCT_PAGES` | 10 | 4.3 |
| `APIFY_MAX_PRODUCTS` | 80 | 4.4. With F14 prices, 80 products and the two listing-page charges of F15 cost at most $0.8891, below the $1 cap. The coffee listing had 55 products (F15) |
| `APIFY_MAX_CHARGE_USD` | 1 | 4.4 (the lowest cap the actor accepts, F14) |
| `APIFY_RUN_TIMEOUT_S` | 3600 | 4.4 |
| `APIFY_POLL_WAIT_S` | 60 | 4.4 (`waitForFinish`) |
| `APIFY_POLL_HTTP_TIMEOUT_S` | 90 | 4.4 |
| `APIFY_POLL_ERRORS_MAX` | 3 | 4.4 |
| `APIFY_POLL_ERROR_WAIT_S` | 15 | 4.4 |
| `APIFY_MAX_TOTAL_WAIT_S` | 4200 | 4.4 |
| `FIRST_DAY_S` | 86400 | 4.6 |
| `SIGNUP_TOLERANCE_S` | 300 | 4.6 (F19: the Death Wish Coffee email arrived 3 s before `signup_at`) |

## 4. Procedure
**Browser.** Playwright 1.48.0 (`requirements.txt`: `playwright==1.48.0`).
- Launch with `chromium.launch(headless=True, channel="chrome", args=["--lang=en-US"])`.
- Context: `locale="en-US"`, `timezone_id="America/New_York"`, viewport 1400 x 950.
- One page, one navigation at a time.
- Chrome is started at the beginning of a brand's run and closed after step 2 below.

**Plain HTTP.** Python `urllib.request`. Redirects are not followed: a 3xx is the response.
- Headers on every request: `User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36` and `Accept-Language: en-US,en;q=0.9`.
- Also `Accept: application/json` for Klaviyo and the where-to-buy API.
- Also `Authorization: Bearer <APIFY_TOKEN>` and `Content-Type: application/json` for Apify.

**No retries.** No request is ever repeated, with one exception: an Apify poll that fails (4.4).

**Blocked** has two definitions:
- **Chrome navigation:** the host of the page URL after the navigation (and, for the home page, after the settle wait) is not the expected host, or the document status is 403 or 429, or `document.title` contains (case-insensitive) `attention required` or `just a moment`. These two are the Cloudflare page titles (F4). Page text is not checked, because product descriptions can contain any words.
- **Plain HTTP request:** status 403 or 429.

The reason names the signal: `blocked: host=<host>`, `blocked: http_<status>` or `blocked: title=<phrase>`.

**Requests.** Every Chrome navigation and every HTTP request, including each Apify API call, counts as one in `requests`.

Order within a brand's run: (1) home page, (2) prices, (3) Klaviyo, (4) emails.

### 4.1 Home page (`offers`)
1. Navigate to `home.url` with `wait_until="load"` and `NAV_TIMEOUT_S`, then wait `HOME_SETTLE_S`. These checks, in this order, end this step; the home sub-part is then `could_not_look` with the reason given:
   - a Playwright timeout: `timeout`;
   - any other navigation error: `navigation_error: <message>`;
   - a blocked page: the blocked reason;
   - a document status of 400 or higher: `http_<status>`.
2. If `shopify_market_check` is true, evaluate `() => [window.Shopify?.country ?? null, window.Shopify?.currency?.active ?? null]`. The result is used in 4.3.
3. For each slot in the order of `brand_inputs.json`, run `page.query_selector_all(selector)`. Write one `offer_slot` record per slot, with one entry per matched element in document order: `outer_html` (`element.evaluate("e => e.outerHTML")`) and `text` (`element.inner_text()`). A slot with no match is written with `state` `not_found` and `elements` `[]`.
4. Nothing else from the page is stored.

| Home sub-part | State | Reason |
|---|---|---|
| Step 1 failed | `could_not_look` | as in step 1 |
| Every slot `found` | `ok` | empty |
| Otherwise | `partial` | `slots_not_found(<slot names, comma-separated, in config order>)` |

### 4.2 Klaviyo (`offers`, only when `klaviyo_company_id` is not `null`)
1. GET `https://static-forms.klaviyo.com/forms/api/v7/<klaviyo_company_id>/full-forms`.
2. The response is valid when the status is 200 and the body is a JSON object whose `full_forms` is a list of objects, each with a string `form_id`. A failure gives the Klaviyo sub-part `could_not_look`, with the reason `klaviyo_http_<status>`, `klaviyo_timeout`, `klaviyo_request_error: <message>` or `klaviyo_shape_changed`. No records are written.
3. Write the body unchanged to `raw/<brand>/<run_id>.klaviyo/full-forms.json`. Then write one `klaviyo_form` record per element of `full_forms`, in list order. An empty list is `ok` with 0 records (Jinx, F8).

### 4.3 Shopify prices (`prices`, route `shopify_products_json`)
1. Market check, from 4.1:
   - If the home sub-part is `could_not_look`, `prices` is `could_not_look` with the reason `market_unconfirmed`.
   - If the country is not `US` or the currency is not `USD`, `prices` is `could_not_look` with the reason `not_us(country=<value>,currency=<value>)`.
   
   In both cases no `products.json` request is sent.
2. For page `n` = 1, 2, …: navigate the same page to `https://<host>/products.json?limit=250&page=<n>` with `wait_until="load"` and `NAV_TIMEOUT_S`, and read the navigation response's `body()`. Check, in this order, and stop at the first failure:
   1. a Playwright timeout: `timeout`; any other navigation error: `navigation_error: <message>`;
   2. blocked: the blocked reason;
   3. status not 200: `http_<status>`;
   4. the `content-type` header does not start with `application/json`, or the body is not JSON: `not_json`;
   5. the body is not an object whose `products` is a list, or a product lacks an integer `id`, a non-empty string `handle` or a list `variants`, or a variant lacks `id` or `price`: `products_shape_changed`.
3. Write one `product` record per product of a valid page, in list order. A product whose key was already written in this run is skipped and counted in `duplicate_products`.
4. Paging ends in one of three ways:
   - A valid page with fewer than `PRODUCTS_PAGE_SIZE` products: the list is complete.
   - Page `MAX_PRODUCT_PAGES` is valid and has `PRODUCTS_PAGE_SIZE` products: the list is incomplete, reason `max_pages_reached`.
   - A page fails: page 1 failing gives `could_not_look` with the page's reason. A later page `n` failing gives `partial` with the reason `page_<n>: <reason>`.
   
   Page reasons are those of step 2.

`prices` is `ok` when the list is complete.

### 4.4 Apify prices (`prices`, route `apify_ecommerce`, Black Rifle only)
1. Read `APIFY_TOKEN` from `.env` at the repository root: the line that starts with `APIFY_TOKEN=`, the rest of the line with surrounding whitespace and one pair of surrounding quotes removed. If the file, the line or the value is missing, `prices` is `could_not_look` with the reason `missing_token`, and no request is sent.
2. Start the run: `POST https://api.apify.com/v2/acts/apify~e-commerce-scraping-tool/runs?maxTotalChargeUsd=1&timeout=3600` with exactly this body (`listing_url` from section 3):
   ```json
   {"listingUrls": [{"url": "https://www.blackriflecoffee.com/collections/coffee"}], "maxProductResults": 80, "additionalProperties": true, "deduplicateProducts": true}
   ```
   - Anything other than 201 with `data.id` gives `could_not_look` with the reason `apify_start_failed: http_<status>` or `apify_start_failed: <exception type>`.
   - The start is never sent twice, because a second start is charged again. When the start raises (for example a timeout), a run may have started anyway: `cost_usd` is 0 in the run result, and this is a case for section 9.
3. Poll `GET https://api.apify.com/v2/actor-runs/<id>?waitForFinish=60`, with an HTTP timeout of `APIFY_POLL_HTTP_TIMEOUT_S`, until `data.status` is `SUCCEEDED`, `FAILED`, `ABORTED` or `TIMED-OUT`.
   - A poll that raises or does not return 200: wait `APIFY_POLL_ERROR_WAIT_S` and poll again.
   - After `APIFY_POLL_ERRORS_MAX` failed polls in a row, or `APIFY_MAX_TOTAL_WAIT_S` after the start, stop with `could_not_look` and the reason `apify_wait_failed(run=<id>)`. `cost_usd` is the `usageTotalUsd` of the last successful poll, or 0 if there was none.
4. With the final run object, send three GETs, each once:
   - items: `https://api.apify.com/v2/datasets/<data.defaultDatasetId>/items?clean=true&format=json`;
   - errors: `https://api.apify.com/v2/datasets/<data.storageIds.datasets.errors>/items?clean=true&format=json`;
   - log: `https://api.apify.com/v2/logs/<id>`.
   
   If the items request fails or does not return a JSON list, `prices` is `could_not_look` with the reason `apify_items_failed: <http_<status> or exception type>`. A failed errors or log request adds `apify_errors_unread` or `apify_log_unread` to the reasons.
5. Write side files to `raw/black-rifle-coffee/<run_id>.apify/`:
   - `run.json`: the run object, with `data.userId` set to `"REDACTED"` and every `signature=<value>` inside `data.output` replaced by `signature=REDACTED`;
   - `errors.json`;
   - `log.txt`.
   
   The token is never written anywhere.
6. Take the items in list order.
   - An item's key comes from its `url`, which must match `^https://www\.blackriflecoffee\.com/products/([^/?#]+)$`. An item without a match is not written and is counted in `items_without_product_url`.
   - An item whose key was already taken is not written and is counted in `duplicate_items`.
   - An item without `offers.price`, or with it `null`, is still written and is counted in `items_without_price`.
7. Currency check on the items to be written:
   - If any `offers.priceCurrency` is neither `"USD"` nor `null`, `prices` is `could_not_look` with the reason `not_usd(<distinct values, sorted, comma-separated>)`, and no `product` record is written.
   - Otherwise write the records. The number of `null` values is `currency_not_reported`.
8. `listed` is the sum of `N` over the distinct `(url, page)` pairs in log lines matching `Found (\d+) products in the listing page: (\S+)\. Page: (\d+)` whose url equals `listing_url`. It is `null` when there is no such line.
9. `cost_usd` is `data.usageTotalUsd` of the final run object.

| `prices` state, checked in this order | State | Reason |
|---|---|---|
| A could_not_look case in steps 1 to 4 or 7 | `could_not_look` | as given there |
| `data.status` is not `SUCCEEDED` and no record was written | `could_not_look` | `apify_run_<status>` |
| `SUCCEEDED`, the log does not contain `The maximum number of results per run has been reached`, `listed` equals the number of records written, the errors dataset is `[]`, and the counts from step 6 and `currency_not_reported` are all 0 | `ok` | empty |
| Anything else | `partial` | what applies, joined with `; `, in this order: `apify_run_<status>`, `apify_max_results_reached`, `apify_listing_count_missing`, `apify_count_mismatch(got=<records>,listed=<listed>)`, `apify_errors=<n>`, `apify_errors_unread`, `apify_log_unread`, `items_without_product_url=<n>`, `duplicate_items=<n>`, `items_without_price=<n>`, `currency_not_reported(n=<n>)` |

With the item shape of F15, every Black Rifle run ends `partial` with the reason `currency_not_reported(n=<records>)`, because the response does not say which currency the prices are in.

### 4.5 Batiste prices (`prices`, route `batiste_wtb`)
1. **Listing.** GET `listing_url`. The title is the first match of `<title>\s*([^<]*?)\s*</title>` (case-insensitive), or empty. The listing is valid when the status is 200, the title does not start with `404 |`, and the body has at least one match of `href="(/products/[^"#?]+)"`. The product paths are the distinct matches in order of first appearance.
   - Write the body to `raw/batiste/<run_id>.batiste/listing.html`.
   - If the listing is invalid, `prices` is `could_not_look` with the reason `listing_http_<status>`, `listing_timeout`, `listing_request_error: <message>`, `listing_not_found` (the 404 title) or `listing_no_products`.
2. **Product pages.** GET `https://www.batistehair.com<path>` for each path. Each page gets one state:

   | Response | Page state | Counts as a failure |
   |---|---|---|
   | 3xx | `redirected`; the `Location` header is kept | no |
   | 200 and the title starts with `404 \|` | `not_found_page` | no |
   | 200 with exactly one tag matching `<a\b[^>]*\bdata-mm-ids="([^"]*)"[^>]*>`, whose `data-mm-wtbid="([^"]*)"` value equals `wtbid` | `widget`; its EANs are the `data-mm-ids` value split on `,`, empty strings dropped | no |
   | Any other 200 | `widget_missing` | yes |
   | Any other status, a timeout or an error | `failed`, with `http_<status>`, `timeout` or `request_error: <message>` | yes |
3. **EAN list.** Take the EANs of all `widget` pages in page order. When an EAN appears on more than one page, the first page wins and every page is listed in the record.
4. **Widget API.** For each EAN in order, GET `https://wtb-api-hub.swaven.com/wtb/v2/api/search/availabilities/<EAN>?wtbid=<wtbid>&lang=en&country=US&nextEndpointV2=true&applyTiedHouseLaw=true`.
   - The response is valid when the status is 200 and the body is a JSON object with a list `d`, an object `prd` whose `ean` equals the EAN, and an object `loc`.
   - A valid response with `loc.Country` `US` and `loc.ISOCurrencySymbol` `USD` gives the EAN `fetched`.
   - A valid response with any other country or currency: every EAN, including those already fetched, gets `not_us`, and every response is dropped. `prices` is `could_not_look` with the reason `not_us(country=<value>,currency=<value>)`. No further requests are sent.
   - A 403 whose body is JSON with a string `detail` starting with `Unauthorized ProductUIDs` (F13): that EAN gets `failed` with the `error` `unauthorized_product`, its `response` is `None`, and the loop continues with the next EAN.
   - Any other response (any other 403 and 429 give `blocked: http_<status>`; otherwise `http_<status>`, `timeout`, `request_error: <message>` or `shape_changed`): that EAN gets `failed` with this as its `error`, and every later EAN gets `not_attempted`. No further requests are sent.
5. **Records.** Write the `retailer_availability` records, one per EAN in order, only after step 4 has ended, so that `not_us` can still drop the responses.

| `prices` state, checked in this order | State | Reason |
|---|---|---|
| Step 1 failed, or `not_us` | `could_not_look` | as given there |
| No page is `widget`, so there is no EAN | `could_not_look` | `no_eans` |
| No EAN `fetched` and at least one EAN `failed` | `could_not_look` | the first failed EAN's `error`; then `; eans_not_attempted=<n>` if any |
| Every EAN `fetched` and no page counts as a failure | `ok` | empty |
| Anything else | `partial` | what applies, joined with `; `: `product_pages_failed=<n>`, the first failed EAN's `error` among EANs not refused as `unauthorized_product`, `eans_unauthorized=<n>`, `eans_not_attempted=<n>` |

### 4.6 Emails (`emails`)
No network. Each check below ends the part when it fails.
1. Find the entry in `part1/data/email_signups.json` whose `brand` equals the brand's `name` in `brands.json`.
   - No file or no entry: `could_not_look`, reason `no_signup_entry`.
   - `signup_at` is `null`: `could_not_look`, reason `not_signed_up(status=<entry status>)`.
2. If `email_sender_domains` is empty: `could_not_look`, reason `sender_domains_unknown`.
3. Read `inbox_export/export.json`.
   - Missing, or not JSON with the fields of section 3: `could_not_look`, reason `no_inbox_export`.
   - A sender domain not in `searched_domains`: `could_not_look`, reason `domain_not_searched(<domain>)`.
4. Check every message in `messages`, for all brands. A message is valid when all of these hold:
   - the file exists in `inbox_export/` and is ASCII;
   - it parses with `email.parser.BytesParser(policy=email.policy.default)`;
   - `X-Trial-Gmail-Id` equals the manifest `gmail_id`;
   - `X-Trial-Received-At` matches `^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$`;
   - `To` is exactly `TRIAL_INBOX <trial_inbox@redacted.invalid>`;
   - `X-Trial-Redaction` is present.
   
   An invalid message is counted in `eml_invalid`. The count covers every brand, because an invalid file's brand cannot be known.
5. The brand's messages are the valid ones whose `From` domain equals a sender domain or ends with `.` + a sender domain. The `From` domain is the part after the last `@` of `email.utils.parseaddr(str(msg["From"]))[1]`, lowercased.
6. The window starts at `signup_at − SIGNUP_TOLERANCE_S` and ends at `signup_at + FIRST_DAY_S`.
   - A message with start ≤ `X-Trial-Received-At` < end is written as an `email` record, in manifest order.
   - Messages before the window are counted in `before_signup`; messages after it in `after_first_day`.
7. `first_day_complete` is `exported_at ≥ signup_at + FIRST_DAY_S`.

| `emails` state, checked in this order | State | Reason |
|---|---|---|
| A could_not_look case in steps 1 to 3 | `could_not_look` | as given there |
| `first_day_complete`, `spam_checked` and `eml_invalid` 0 | `ok` | empty. 0 records here means that no email arrived |
| Anything else | `partial` | what applies, joined with `; `: `first_day_not_over(covered=<h>h)`, `spam_not_checked`, `eml_invalid=<n>` |

`<h>` is `(exported_at − signup_at)` in hours, formatted with two decimals. So "0 emails" (`ok`, 0 records) and "could not look" (`could_not_look`) are different states, and a run before the 24 hours are over always shows `first_day_not_over` with the hours covered.

## 5. Output
### Records
| `kind` | `key` | `url` | `fetched_at` |
|---|---|---|---|
| `product` (Shopify) | `product/<host>/<handle>` | `https://<host>/products/<handle>` | when the page response arrived |
| `product` (Apify) | `product/www.blackriflecoffee.com/<handle from url>` | the item's `url` | the item's `scrapedAt`, cut to whole seconds (`YYYY-MM-DDTHH:MM:SSZ`); when it is missing, when the items response arrived |
| `retailer_availability` | `wtb/<EAN>` | `https://www.batistehair.com<first product path>` (the page whose "SHOP NOW" button opens the widget) | when the request ended. For `not_attempted`, when the route stopped |
| `offer_slot` | `offer_slot/<home host>/<slot>` | `home.url` | when the settle wait ended |
| `klaviyo_form` | `klaviyo_form/<company id>/<form_id>` | the `full-forms` URL | when the response arrived |
| `email` | `email/<X-Trial-Gmail-Id>` | the entry's `signup_url`: signing up there brings the same email | `exported_at` |

`raw` per kind:
```json
{"route": "shopify_products_json", "page": 1, "product": {}}
{"route": "apify_ecommerce", "apify_run_id": "hnwXbDVmaBIo3D8pq", "item": {}}
{"route": "batiste_wtb", "ean": "5010724526705", "product_pages": ["/products/dry-shampoo/fragrance-bare"], "state": "fetched", "error": null, "response": {}}
{"route": "home_dom", "slot": "announcement_bar", "selector": "p.announcement-bar__message", "state": "found", "elements": [{"outer_html": "<p ...>", "text": "BUILD YOUR OWN ..."}]}
{"route": "klaviyo_full_forms", "company_id": "Q6RhjR", "form": {}}
{"route": "inbox_export", "file": "livingproof_20261110T044829Z_1a1c3c946076193d.eml", "sha256": "<of the file bytes>", "eml": "<the whole file as text>", "signup_at": "2026-11-10T04:47:06Z", "first_day_ends_at": "2026-11-11T04:47:06Z", "exported_at": "2026-11-10T07:26:17Z", "spam_checked": false}
```
- `product`, `item`, `response` and `form` are unchanged.
- `retailer_availability.state` is `fetched`, `failed`, `not_attempted` or `not_us`. `response` is `null` unless `fetched`.

**Personal data:**
- No full page is stored (F9).
- `.eml` files are accepted only in the redacted form of 4.6 step 4, so the inbox address never reaches `raw/`.
- `run.json` loses `userId` and URL signatures.
- The where-to-buy rows name retail stores, with their address and phone. These are businesses, so they are kept.

### Run result
- `source` is `brand_site_and_emails`.
- `expected_total` is `null`.
- `cost_usd` is the Apify charge from 4.4, and 0 for the other brands.

`extra`:
```json
{"parts": {
  "prices": {"state": "ok", "reason": "", "route": "shopify_products_json", "records": 66, "pages": 1, "complete": true, "duplicate_products": 0},
  "offers": {"state": "ok", "reason": "",
             "home": {"state": "ok", "reason": "", "market": {"country": "US", "currency": "USD"}, "slots_not_found": []},
             "klaviyo": {"state": "ok", "reason": "", "forms": 2}},
  "emails": {"state": "partial", "reason": "first_day_not_over(covered=2.65h); spam_not_checked",
             "signup_at": "2026-11-10T04:47:06Z", "first_day_ends_at": "2026-11-11T04:47:06Z", "exported_at": "2026-11-10T07:26:17Z",
             "first_day_complete": false, "spam_checked": false, "in_window": 1, "before_signup": 0, "after_first_day": 0, "eml_invalid": 0}
}}
```
- `market` is `null` when there is no market check.
- `klaviyo` is `null` when `klaviyo_company_id` is `null`.
- For the other price routes, `prices` holds `state`, `reason`, `route`, `records` and the counters below.
- For the Apify route: `run_id`, `run_status`, `listed`, `items`, `items_without_product_url`, `duplicate_items`, `items_without_price`, `currency_not_reported`, `errors` (the length of the errors dataset, or `null` if unread).
- For the Batiste route: `product_pages` (a list of `{"path", "state", "eans", "location", "error"}`), `eans`, `fetched`, `failed`, `not_attempted`.
- When a part stops at an earlier check (for example `not_signed_up`), the counters it never reached are `null`.

`offers` state:

| Condition, checked in this order | State | Reason |
|---|---|---|
| Every sub-part that exists (`home`, and `klaviyo` when it is not `null`) is `ok` | `ok` | empty |
| Every sub-part that exists is `could_not_look` | `could_not_look` | the sub-part reasons, as `home: <reason>; klaviyo: <reason>` |
| Anything else | `partial` | the reasons of the sub-parts that are not `ok`, as above |

Brand `status`:

| Condition, checked in this order | `status` | `reason` |
|---|---|---|
| Unexpected exception | as in the shared contract | |
| All three parts `ok` | `ok` | empty |
| All three parts `could_not_look` | `could_not_look` | `prices: <reason>; offers: <reason>; emails: <reason>` |
| Anything else | `partial` | `<part>: <reason>` for each part that is not `ok`, in the order prices, offers, emails, joined with `; ` |

## 6. Tests
Functions tested against the sample files, with no network. All are pure except `extract_slots`, which runs on a Playwright page filled with `page.set_content`, in a context with `java_script_enabled=False` and every request aborted.

```python
class ShapeError(Exception): ...

def parse_products_page(resp: dict) -> list[dict]: ...            # raises ShapeError (4.3 step 2)
def product_key(host: str, handle: str) -> str: ...
def market_ok(country: str | None, currency: str | None) -> bool: ...
def parse_batiste_listing(html: str) -> list[str]: ...            # product paths; raises ShapeError
def classify_batiste_page(status: int, location: str | None, html: str, wtbid: str) -> tuple[str, list[str]]: ...  # (page state, EANs)
def validate_wtb(resp: dict, ean: str) -> tuple[str, str]: ...    # (loc.Country, loc.ISOCurrencySymbol); raises ShapeError
def parse_klaviyo(resp: dict) -> list[dict]: ...                  # raises ShapeError
def apify_item_key(item: dict) -> str | None: ...
def apify_listed(log: str, listing_url: str) -> int | None: ...
def extract_slots(page, slots: dict[str, str]) -> list[dict]: ... # raw of each offer_slot record
def read_eml(path: str, manifest_gmail_id: str) -> dict | None: ...  # gmail_id, received_at, from_domain, sha256; None when invalid
def emails_part(signup: dict | None, sender_domains: list[str], manifest: dict | None, emls: list[dict | None]) -> tuple[str, str, list[dict]]: ...  # state, reason, in-window messages
def apify_prices_state(run_status: str, records: int, listed: int | None, max_hit: bool, errors: int | None, log_read: bool, counts: dict) -> tuple[str, str]: ...
    # counts has items_without_product_url, duplicate_items, items_without_price, currency_not_reported; errors None means the errors dataset was not read
def combine_parts(parts: dict[str, tuple[str, str]]) -> tuple[str, str]: ...
def redact_apify_run(run: dict) -> dict: ...
```

| Input | Expected |
|---|---|
| `products_jinx_page1_full.json` | 73 products, 142 variants; first key `product/www.thinkjinx.com/peanut-butter-bone-broth-biscuits`; fewer than 250, so it is the last page |
| `products_page2_empty.json` | 0 products |
| `products_livingproof_trimmed.json` | 3 products; first handle `the-classic-clean-dry-shampoo-set` |
| `products_deathwish_trimmed.json` | 3 products, 7 variants; first handle `peppermint-mocha-coffee` |
| Jinx page with `handle` removed from one product; `{"items": []}` | `ShapeError` |
| `market_ok("US", "USD")`, `("CA", "CAD")`, `(None, None)` | `True`, `False`, `False` |
| `batiste/listing_batiste-products.html` | 33 paths; first `/products/dry-shampoo/powder-bare-scent`, last `/products/dry-shampoo/fragrance-pink-pineapple` |
| `batiste/product_page_fragrance-bare.html`, status 200 | `("widget", ["5010724526705", "5010724527146", "5010724538333", "5010724532133"])` |
| status 301, location `https://www.batistehair.com/batiste-products`, empty body | `("redirected", [])` |
| `batiste/page_404_sitemap.html`, status 200 | `("not_found_page", [])` |
| the fragrance-bare page with its `data-mm-ids` tag removed, status 200 | `("widget_missing", [])` |
| `batiste/wtb_availabilities_5010724526705_full.json`, EAN `5010724526705` | `("US", "USD")`; `d` has 7 rows |
| `batiste_wtb_availabilities_trimmed.json`, EAN `5010724526705` | `("US", "USD")`; `d` has 3 rows |
| the full response with EAN `5010724527146`; `{}` | `ShapeError` |
| `klaviyo_forms_livingproof.json`, `_deathwish`, `_blackrifle`, `_jinx` | 5, 16, 16, 0 forms; first `form_id` `TgsYXf`, `YcKPdA`, `SzW6gs` |
| a Klaviyo response with `form_id` removed from one form | `ShapeError` |
| `apify/blackrifle_run2_items.json` | 55 keys, all distinct; first `product/www.blackriflecoffee.com/fall-coffee-lineup` |
| `apify/blackrifle_run2_log.txt`, `apify/blackrifle_run1_log.txt` | `apify_listed` 55 and 10; the max-results line only in run 1 |
| `apify_prices_state("SUCCEEDED", 55, 55, False, 0, True, counts)` with `currency_not_reported` 55 and the other counts 0 | `("partial", "currency_not_reported(n=55)")` |
| the same with `currency_not_reported` 0 | `("ok", "")` |
| `apify_prices_state("SUCCEEDED", 5, 10, True, 0, True, counts)` with all counts 0 | `("partial", "apify_max_results_reached; apify_count_mismatch(got=5,listed=10)")` |
| `apify_prices_state("FAILED", 0, None, False, None, False, counts)` with all counts 0 | `("could_not_look", "apify_run_FAILED")` |
| `redact_apify_run` on `{"data": {"userId": "u1", "output": {"results": "https://x/items?signature=abc"}}}` | `userId` `"REDACTED"`, URL ends `signature=REDACTED` |
| `extract_slots` on `home_slots/living-proof.html` with the Living Proof slots | counts 3, 2, 3, 1, 1; all `found` |
| `home_slots/death-wish-coffee.html` | 1, 9, 1; the second `banner_heading` text is `WHEN LIFE SURGES, SO SHOULD YOU` |
| `home_slots/jinx.html` | 2, 1, 1, 6, 1 |
| `home_slots/batiste.html` | 1 |
| an empty document with the Batiste slots | `community_signup` `not_found` |
| `read_eml` on the three files in `eml/` | ids `1a1c3c946076193d`, `1a1c3c89e9e9cf7d`, `1a1c3d099d8be175`; received `2026-11-10T04:48:29Z`, `04:47:45Z`, `04:56:27Z`; domains `livingproof.com`, `deathwishcoffee.com`, `blackriflecoffee.com` |
| `read_eml` with the wrong manifest id, or on a copy whose `To` is changed | `None` |
| `emails_part` for Living Proof with the `export.json` of section 3 | `("partial", "first_day_not_over(covered=2.65h); spam_not_checked")`, 1 message |
| the same for Death Wish Coffee | `first_day_not_over(covered=2.64h)`; the email 3 s before `signup_at` is in the window |
| the same for Black Rifle | `first_day_not_over(covered=2.52h)` |
| the same three with `exported_at` `2026-11-11T05:00:00Z` and `spam_checked` `true` | `("ok", "")`, 1 message each |
| Living Proof with `exported_at` `2026-11-11T05:00:00Z`, `spam_checked` `true` and no messages | `("ok", "")`, 0 messages |
| Jinx or Batiste (signup entry of `email_signups.json`) | `("could_not_look", "not_signed_up(status=not_signed_up)")` |
| `emails_part` with `manifest` `None` | `("could_not_look", "no_inbox_export")` |
| `combine_parts` with ok/ok/ok; could_not_look `a`/`b`/`c`; ok, partial `x`, could_not_look `y` | `("ok", "")`; `("could_not_look", "prices: a; offers: b; emails: c")`; `("partial", "offers: x; emails: y")` |

## 7. Done when
1. The tests pass.
2. `--brand living-proof` gives:
   - `prices` `ok`, with as many `product` records as `https://www.livingproof.com/products.json?limit=250` shows when opened by hand at the same time (66 on 2026-11-10);
   - `offers` `ok`, with 5 `offer_slot` records;
   - while `export.json` is the export of section 3, `emails` `partial` with the reason `first_day_not_over(covered=2.65h); spam_not_checked` and 1 `email` record;
   - status `partial`.
3. `--brand death-wish-coffee` gives the same pattern: 165 products on 2026-11-10, and 3 `offer_slot` records.
4. `--brand jinx` gives `prices` `ok` (73 products on 2026-11-10), `offers` `ok` with 0 `klaviyo_form` records, `emails` `could_not_look` with the reason `not_signed_up(status=not_signed_up)`, and status `partial`.
5. `--brand batiste` gives `offers` `ok` and `emails` `could_not_look`. For `prices`, one of two things happens:
   - `ok`, with one `retailer_availability` record per EAN, all `fetched` (63 on 2026-11-10), and 5 pages `redirected`;
   - or a `blocked: http_403` failure recorded as in 4.5. In that case, stop and report (section 9).
6. `--brand black-rifle-coffee` gives:
   - with a token: `prices` `partial` with the reason `currency_not_reported(n=<records>)` and `records` equal to `extra.parts.prices.listed`; `cost_usd` under 1 (0.4271 on 2026-11-10); the home sub-part `could_not_look` with a `blocked:` reason;
   - without a token: `prices` `could_not_look` with the reason `missing_token`, and `cost_usd` 0.
   
   Each run with a token is charged, so run it once.
7. A second run adds new files and leaves the first run's files unchanged.
8. Open the `url` of three `product` records per Shopify brand. The price shown for the first variant equals `raw.product.variants[0].price`. Open three Black Rifle records: the price shown equals `raw.item.offers.price`.
9. Two checks on `raw/`:
   - Every `To:` line in a `raw.eml` is `To: TRIAL_INBOX <trial_inbox@redacted.invalid>`.
   - The only `.html` file is the Batiste `listing.html`.

## 8. Where the pipeline finds each value
| Attribute | Location |
|---|---|
| product id, title, handle, vendor, type, tags | `raw.product.id`, `.title`, `.handle`, `.vendor`, `.product_type`, `.tags` (Shopify). Apify: `raw.item.name`, the handle in `key`; no id |
| variant price, compare-at price, available (USD) | `raw.product.variants[].price` and `.compare_at_price` (strings; `compare_at_price` is `null` when there is none), `.available` (boolean). Apify: `raw.item.offers.price` (one price per product, F15), and `raw.item.additionalProperties.variants[].price` and `.regularPrice` only in the F16 shape |
| published, updated | `raw.product.published_at`, `.updated_at` (store-local offset) |
| Batiste product name, EAN | `raw.response.prd.pname`, `raw.ean` |
| Batiste retailer price, stock, delivery | `raw.response.d[].rname`, `.sid`, `.sname`, `.pr`, `.currency`, `.av`, `.shd`, `.carturl` |
| Batiste widget location | `raw.response.loc` |
| home offer text | `raw.elements[].text` per `raw.slot`; markup in `raw.elements[].outer_html` |
| free-shipping threshold | `data-limit` (Living Proof) or `data-free-shipping-limit` (Jinx) in `raw.elements[].outer_html` of `free_shipping_message` (F7) |
| signup form wording and codes | `raw.form.name` and the texts inside `raw.form.live_form_versions` |
| email sender, subject, sent and received time | the `From`, `Subject`, `Date` and `X-Trial-Received-At` headers in `raw.eml` |
| email flow and message id | the `X-Kmail-Flow` and `X-Kmail-Message` headers |
| email offer code, discount, expiry, links | the `text/plain` part of `raw.eml` (rules in section 4-4 of `source_info.md`) |
| preheader | the first `display:none` `div` after `<body>` in the `text/html` part |
| first day covered | `extra.parts.emails.first_day_complete`, `covered=<h>h` in its reason |

## 9. Stop and report
Stop work and report, with the exact response, when any of these happen. Do not choose a behavior yourself.
- The where-to-buy API answers 403 or 429 (F13). Report the status, headers and body. Do not add waits or retries.
- The Apify start request raises. A run may have started and been charged without the collector knowing its ID; look it up in the Apify console before running again.
- The Batiste prices part ends `no_eans`.
- A `products.json` page 1 has exactly 250 products, or 0 products. Paging past page 1, and an empty store, were never observed.
- On the first implementation run, a home slot is `not_found`, the Living Proof, Death Wish Coffee, Jinx or Batiste home is blocked, or a market check is not `US`/`USD`.
- The Black Rifle home is not blocked. Its slots (F5) were never checked in headless Chrome.
- An Apify item has keys outside the union of the F15 and F16 shapes, an `inputUrl` other than `listing_url`, or an `unblocker-proxy-per-product` charge. Or the log has no `Found` line, or `listed` differs from the item count.
- A Klaviyo response has top-level keys other than those in F8.
- A Batiste product page returns 200 without the widget tag, or redirects somewhere other than `https://www.batistehair.com/batiste-products`.
- `email_signups.json` gets a `signup_at` for Batiste or Jinx. Their sender domain must be taken from their first real email, added to `email_sender_domains` and to the export query, before the part can be collected.
- An email from a signed-up brand arrives from a domain that is not in its `email_sender_domains`, or a manifest message is invalid (4.6 step 4).
- Anything else that makes a step in section 4 impossible to carry out as written.
