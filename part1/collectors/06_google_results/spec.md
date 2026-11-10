# Spec: source 6, Google search results raw collector

- Shared contract: `part1/collectors/README.md`. Read it first; this document adds only what is specific to this source.
- Research notes: `part1/collectors/06_google_results/source_info.md` (sections 11 to 14). Where they differ from this spec, this spec is newer.
- Every fact below was observed on 2026-11-10 in a real request, or read from Apify's API or documentation that day. If the Actor or the API behaves differently, or a step needs something this spec does not give, stop and report. Do not guess.

## 1. What to build
One file, `source_collector.py`, standard library only. Given a brand, it starts one run of the Apify Actor `apify/google-search-scraper` with the brand's 20 fixed search terms, waits for it, downloads the run's dataset and writes one record per search term: page 1 of Google's US desktop results for that term. No retries.

The brief asks this source: "For the brand's top 20 search terms: who ranks and who buys ads". This collector covers **who ranks**. **Who buys ads is not collected**: on 2026-11-10 it was decided to record ads as `could_not_look` for every search term, because two Actors returned no ads for these brand terms while a person saw ads for the same term that day (F6). Ad extraction is therefore off, and every record and every run result says `"ads": "could_not_look"`. The empty `paidResults` in the Actor's output only means that ads were not requested. It is not a count of ads.

It does not request Google itself (F1), choose or change the search terms, extract or classify any value, or save result-page HTML.

## 2. Facts about the source
| # | Fact |
|---|---|
| F1 | Google search in automated Chrome, from a US datacenter IP and from a Korean IP, redirected to `https://www.google.com/sorry/index` (reCAPTCHA) on the first search. Hence the Actor |
| F2 | Actor `apify/google-search-scraper` (ID `nFJndFXA5zjCTuudP`) charges per event. Free-plan prices: `search-page-scraped` $0.0045 per results page; `apify-actor-start` $0.00005 per GB of memory; `ads-scraped` $0.0065 per page, only when `focusOnPaidAds` is on. The other add-ons are charged only when enabled in the input |
| F3 | A start request with `maxTotalChargeUsd` below 0.5 is rejected with HTTP 400 `max-total-charge-usd-below-minimum`, and no run is created. With `maxTotalChargeUsd=0.5&timeout=300` the start returned HTTP 201 with `data.id`, `data.defaultDatasetId` and `status` `READY`; the run used 1024 MB and reached `SUCCEEDED` after 91 seconds for 3 terms |
| F4 | Run statuses: `READY`, `RUNNING`, `TIMING-OUT`, `ABORTING` (not finished) and `SUCCEEDED`, `FAILED`, `TIMED-OUT`, `ABORTED` (finished). `GET /v2/actor-runs/<id>?waitForFinish=60` waits up to 60 seconds (the API maximum) before answering. A run that reaches its `timeout` ends as `TIMED-OUT` |
| F5 | `GET /v2/datasets/<id>/items?format=json` returned a JSON array with one item per term. `searchQuery.term` equals the submitted term character for character; `searchQuery.page` is `1`, `countryCode` `"US"`, `device` `"DESKTOP"`; `#error` is `false`. `organicResults` held 6, 7 and 9 results, each with `position` (1, 2, 3, ...), `url`, `title`, `description`, `websiteTitle` |
| F6 | With `focusOnPaidAds: true` the three brand terms returned empty `paidResults` after the Actor's own three retries, and the saved result HTML had empty ad slots. A person's Chrome showed 2 "Sponsored" results for `batiste dry shampoo` the same day. A second Actor (`cheapapi/google-serp-scraper`) also returned no ads |
| F7 | On social and community results `websiteTitle` is `<platform> · <account or page name>` (middle dot U+00B7), for example a Facebook page name or a YouTube channel name. On other results it is a site name without `·` |
| F8 | Charges reach the run record after its status does: the first read showing `SUCCEEDED` counted 2 of 3 pages; a later read counted 3 |
| F9 | The Google autocomplete order changes within hours (4 of 10 suggestions for `death wish coffee` changed in 3 hours), so the terms are fixed in `brand_inputs.json` and never rebuilt |
| F10 | A result for a person's profile page can carry `personalInfo` (`rawText`, `location`, `companyName`); seen once, on 2026-11-11, for the term `black rifle coffee owner` |
| F11 | Result text can contain email addresses, among them a named employee's from a careers page (seen 2026-11-11) |
| F12 | A result can be a private person's own Facebook post, with their name in the URL path (seen once, 2026-11-11) |

Samples are in `part1/collectors/06_google_results/samples/`: `apify/trial_run_dataset.json` (F5 to F7), `apify/trial_run_summary.json` and `apify/trial_run_poll_log.md` (F3, F8), `apify/actor_pricing.json` (F2), `apify/start_rejected_min_charge.json` (F3), `google_search_captcha_sorry_page.html` (F1). F4 is from Apify's documentation.

Cost: 20 pages × $0.0045 + $0.00005 = **$0.09005 per brand**, $0.45025 for `--all`.

## 3. Input
`brand_inputs.json` holds each brand's 20 search terms, in order, as fixed on 2026-11-10 (recipe in `source_info.md` sections 6-4 and 13). The order is the term's rank, 1 to 20.
```json
{
  "batiste": {"keywords": ["batiste dry shampoo", "batiste dry shampoo dark hair", "...", "batiste dry shampoo kroger"]},
  "living-proof": {"keywords": ["living proof dry shampoo", "living proof", "...", "living proof ulta"]},
  "death-wish-coffee": {"keywords": ["death wish coffee", "...", "death wish coffee mugs"]},
  "black-rifle-coffee": {"keywords": ["black rifle coffee", "...", "black rifle coffee review"]},
  "jinx": {"keywords": ["jinx dog food", "...", "jinx dog food lawsuit"]}
}
```

Actor input, built from the terms. Ad extraction and every paid add-on are off; `linkProspecting` is not sent, which keeps that add-on off:
```json
{"queries": "<the 20 terms joined with \n>", "maxPagesPerQuery": 1, "countryCode": "us", "languageCode": "en",
 "focusOnPaidAds": false, "mobileResults": false, "includeUnfilteredResults": false,
 "saveHtml": false, "saveHtmlToKeyValueStore": false, "includeIcons": false,
 "aiOverview": {"scrapeFullAiOverview": false}, "aiModeSearch": {"enableAiMode": false},
 "geminiSearch": {"enableGemini": false}, "chatGptSearch": {"enableChatGpt": false}, "copilotSearch": {"enableCopilot": false},
 "perplexitySearch": {"enablePerplexity": false, "returnImages": false, "returnRelatedQuestions": false},
 "maximumLeadsEnrichmentRecords": 0, "verifyLeadsEnrichmentEmails": false, "websiteContentScraper": {"enable": false}}
```
This is the trial input (`samples/apify/trial_input.json`) with `focusOnPaidAds` and `saveHtmlToKeyValueStore` set to `false`.

## 4. Procedure
Standard library `urllib.request`. Every request goes to `https://api.apify.com` with the header `Authorization: Bearer <APIFY_TOKEN>`, one at a time, once. A request **fails** when it raises an error, times out, or returns a status other than the one named.

1. **Start.** `POST /v2/acts/apify~google-search-scraper/runs?maxTotalChargeUsd=0.5&timeout=600&memory=1024`, body = the Actor input, `Content-Type: application/json`, timeout 30 s. Expect 201 with `data.id` and `data.defaultDatasetId`.
2. **Wait.** Repeat `GET /v2/actor-runs/<id>?waitForFinish=60` (timeout 90 s, expect 200) until `data.status` is one of the four finished statuses. The run's own `timeout=600` guarantees it finishes (F4).
3. **Dataset.** `GET /v2/datasets/<defaultDatasetId>/items?format=json` (timeout 60 s, expect 200 and a JSON array).
4. **Charges.** Let `pages` be the number of dataset items with `#error` equal to `false`. Read `GET /v2/actor-runs/<id>` (timeout 30 s) every 5 seconds, at most 12 times, until `data.chargedEventCounts["search-page-scraped"]` is at least `pages` (F8). `cost_usd` is `data.usageTotalUsd` of the last successful run read in step 2 or 4. If a read fails, stop reading; the status does not change.
5. **Match.** For each term, in file order, take the first dataset item whose `searchQuery.term` equals the term. Its `error` is:
   - `missing` when there is no such item;
   - `actor_error` when its `#error` is not `false`;
   - `no_organic_results` when `organicResults` is missing or an empty list;
   - otherwise `null`: the page is good.
6. **Names.** In every stored item, set each `organicResults[i].websiteTitle` that contains `·` to `null` (F7). `url` and `title` are kept: they are the public address and headline of the ranked page and are needed to check the record against Google. Also remove the key `personalInfo` from every entry of `organicResults`, `paidResults`, `paidProducts` and `suggestedResults` (F10): it holds a person's location and employer. Then, in the same lists: (a) an entry whose `url` is a person's own Facebook page (first path segment like `jane.doe.12345`, a path starting `/people/`, or `/profile.php`; F12) gets the name segment of the path replaced by `REDACTED` in `url` (and in `link` and `displayedUrl` when they hold it; for `/people/<name>/<id>` both name and id, for `/profile.php` the whole query), and `title` and `description` set to `null`; (b) in every string value anywhere in the item (result entries, the AI overview, related questions), except the values of the keys `url` and `link`, each email address is replaced by `REDACTED@<its domain>` (F11). The redacted URL depends only on the input, so the row key stays the same between runs.
7. **Write** one record per term, 20 in total, unless the status is `could_not_look`; then write none.

## 5. Output
One record per search term:
| Field | Value |
|---|---|
| `key` | The term, for example `batiste dry shampoo`. It stays the same in every run; a position inside the page would not |
| `kind` | `search_results_page` |
| `url` | `"https://www.google.com/search?" + urlencode({"q": term, "gl": "us", "hl": "en"})`, for example `https://www.google.com/search?q=batiste+dry+shampoo&gl=us&hl=en` |
| `fetched_at` | The run's `finishedAt`, to whole seconds. The Actor does not report a time per page |
| `raw.keyword_index` | The term's place in `brand_inputs.json`, 1 to 20 |
| `raw.serp` | The dataset item after step 6 (names and `personalInfo` removed), or `null` when `missing` |
| `raw.error` | `null`, `missing`, `actor_error` or `no_organic_results` |
| `raw.ads` | Always `could_not_look` |

Run result: `source` is `google_results`, `expected_total` is `null`, `requests` counts every HTTP request sent, `cost_usd` is from step 4 (0 when no run was created). `extra` is `{"apify_run_id": "<id>", "apify_status": "<last status read>", "ads": "could_not_look"}`.

`ok` means all 20 terms have a good page. Ads are outside its scope and are `could_not_look` in every record and in `extra`.

| Condition, checked in this order | `status` | `reason` |
|---|---|---|
| `APIFY_TOKEN` missing in `.env` | `could_not_look` | `missing_token` |
| Step 1 failed | `could_not_look` | `apify_start: <HTTP status and error.type, or the error message>` |
| A request in step 2 or 3 failed | `could_not_look` | `apify_wait: <...>` or `apify_dataset: <...>` |
| No term has a good page | `could_not_look` | `no_results: apify_status=<status>` |
| All 20 terms have a good page | `ok` | empty |
| Anything else | `partial` | the counts that are not 0, joined with `; `: `missing=<n>`, `actor_error=<n>`, `no_organic_results=<n>`, then `apify_status=<status>` when it is not `SUCCEEDED` |

## 6. Tests
Eight pure functions, tested against the samples. No network.
```python
def actor_input(keywords: list[str]) -> dict: ...
def search_url(term: str) -> str: ...
def match(keywords: list[str], items: list[dict]) -> list[tuple[dict | None, str | None]]: ...  # (item, error) per term
def remove_names(item: dict) -> dict: ...  # returns a copy
def drop_personal_info(serp: dict) -> dict: ...  # returns a copy, no `personalInfo` in any result entry
def redact_personal_pages(serp: dict) -> dict: ...  # returns a copy; person's own Facebook page: name out of the URL, title/description None
def redact_emails(serp: dict) -> dict: ...  # returns a copy; emails in any text of the item become REDACTED@domain
def is_personal_profile_url(url: object) -> bool: ...
```

| Input | Expected |
|---|---|
| `actor_input(["batiste dry shampoo", "death wish coffee", "jinx dog food"])` | `samples/apify/trial_input.json` with `focusOnPaidAds` and `saveHtmlToKeyValueStore` `false` |
| `search_url("batiste dry shampoo blonde 3.81oz. (pack of 4)")` | `https://www.google.com/search?q=batiste+dry+shampoo+blonde+3.81oz.+%28pack+of+4%29&gl=us&hl=en` |
| `match` with those 3 terms and `trial_run_dataset.json` | 3 items, error `null`, with 7, 6 and 9 organic results |
| `match` with Batiste's 20 terms and `trial_run_dataset.json` | term 1 good; terms 2 to 20 `(None, "missing")` |
| `match` with `["jinx dog food"]`, that item with `#error` `true` | `actor_error` |
| `match` with `["jinx dog food"]`, that item with `organicResults` `[]` | `no_organic_results` |
| `remove_names` on the `death wish coffee` item | `websiteTitle` of results 2 and 3 (0-based) is `None`; the others stay `Death Wish Coffee`, `Amazon.com`, `Walmart`, `Wikipedia` |
| `remove_names` on the `jinx dog food` item | results 3 and 8 changed, nothing else |

## 7. Done when
1. The tests pass.
2. `--brand batiste` ends `ok` with 20 records and `cost_usd` 0.09005. Every record has `raw.ads` `could_not_look`, and no `websiteTitle` contains `·`.
3. A second run adds new files and leaves the first run's files unchanged.
4. For three `batiste` records, a person opens `url` from a US IP in a private window: the first organic result has the same domain as `raw.serp.organicResults[0].url`. If not, report it with a screenshot.

## 8. Where the pipeline finds each value
| Attribute | Location |
|---|---|
| keyword, keyword rank | record `key`, `raw.keyword_index` |
| search context (country, language, device, page) | `raw.serp.searchQuery` |
| observed_at | record `fetched_at` |
| position, url, title, description, result type | `raw.serp.organicResults[]`: `position`, `url`, `title`, `description`, `type` |
| domain, url_key | host of `url` without `www.`; `url` without the `srsltid` parameter |
| domain_class, store order | `domain` looked up in `source_info.md` section 14-1, results in `position` order |
| who buys ads | `raw.ads` (always `could_not_look`); never `raw.serp.paidResults` |
| AI Overview shown | presence of `raw.serp.aiOverview` |
