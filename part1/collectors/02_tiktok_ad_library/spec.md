# Spec: source 2, TikTok ads (Creative Center Top Ads, US) raw collector

- Shared contract: `part1/collectors/README.md`. Read it first; this document adds only what is specific to this source.
- Research notes: `part1/collectors/02_tiktok_ad_library/source_info.md` (decision at the top, sections 9-1 and 12). Where they differ from this spec, this spec is newer.
- Every fact below was observed on 2026-11-10 in real responses. If the API, the actor or the media server behaves differently, or a step needs something this spec does not give, stop and report. Do not guess.

## 1. What to build
One file, `source_collector.py`. Given a brand, it runs the Apify actor `fetch_cat/tiktok-ads-library-scraper` once. The actor searches TikTok Creative Center Top Ads in the US over the last 180 days with the brand's keywords. The collector keeps the rows that mention the brand, downloads each kept row's video and cover image, and writes one record per kept row. No retries.

TikTok publishes no US ad library. Top Ads holds only high-performing auction ads that their advertisers allowed to be shown, so this is a sample of US ads, not every ad. The user accepted this limitation on 2026-11-10.

The keyword search is loose. Most rows are other advertisers' ads that share a word with the keyword: short dramas, games, other coffee brands. The user decided that rows not mentioning the brand are dropped, and only their ad IDs are listed in the run result. Known gap: a brand ad whose text and brand name never mention the brand is dropped too.

It does not decide whether an ad is "running now" (the rows carry no dates), and it does not interpret `ctr`, `costIndex` or the industry and objective keys.

## 2. Facts about the source
| # | Fact |
|---|---|
| F1 | `POST https://api.apify.com/v2/acts/fetch_cat~tiktok-ads-library-scraper/runs?build=0.1.30&timeout=300&memory=512&maxTotalChargeUsd=0.25&waitForFinish=60`, with the actor input as the JSON body, returns 201 and the run object in `data`. The run's `options` echo build `0.1.30` and `maxTotalChargeUsd` 0.25. The actor has no minimum cap. The actor reads Creative Center without login or proxy, 20 rows per page per keyword, until a page has fewer than 20 rows. The Jinx input (2 keywords) finished in 4.8 s; 9 keywords took 38 s |
| F2 | `GET /v2/actor-runs/<id>?waitForFinish=60` returns the run object. Terminal statuses are `SUCCEEDED`, `FAILED`, `TIMED-OUT`, `ABORTED`. `GET /v2/datasets/<defaultDatasetId>/items?format=json&clean=false` returns a JSON list of rows, one per unique ad, in `rank` order |
| F3 | Every row has the same 29 keys, among them `adId` (19-digit string), `detailUrl` (`https://ads.tiktok.com/business/creativecenter/topads/<adId>`), `adText`, `brandName` (`null` in 106 of 296 rows), `advertiserName` (always `null`), `keyword`, `videoUrl` (the highest quality in `videoUrls`), `coverImageUrl`, `mediaExpiresAt` (6.0 to 6.6 h after `scrapedAt`), `likes`, `ctr`, `costIndex`, `industryKey`, `objectiveKey`, `durationSeconds`, `countryCode` (`US`), `periodDays` (180), `rank`. No row has a shown date |
| F4 | `GET /v2/key-value-stores/<defaultKeyValueStoreId>/records/RUN_SUMMARY` returns `status`, `requestedSources`, `processedSources`, `saved`, `duplicatesSkipped`, `failed`, `emptySources`, `errors`, `warnings`, `startedAt`, `finishedAt`. In both runs: `status` `SUCCEEDED`, `failed` 0, `errors` and `warnings` empty, `saved` equal to the number of rows. A keyword with no Top Ads adds no rows and counts in `emptySources`; the run is still `SUCCEEDED` |
| F5 | Pricing is in `run.pricingInfo.pricingPerEvent.actorChargeEvents`: `apify-actor-start` $0.005 (once at 512 MB), `apify-default-dataset-item` $0.00020537 per row. Apify settles the charge 14 to 25 s after the run ends; read at once, `usageTotalUsd` is too low. Once settled it equalled start price + rows × row price in both runs (0.06578952 for 296 rows, 0.00602685 for 5) |
| F6 | Of 296 rows from all five brands' keywords, 3 mention a brand: `7531018269878140936` (Living Proof) and `7609180755211075600`, `7619486503161118737` (Jinx, creator ads with `@Jinx` and `#JinxPartner`). The Jinx run 3 hours later returned the same 5 ad IDs |
| F7 | `ctr` is a percentile band (0.39 = "Top 39%") and `costIndex` 0, 1, 2 means budget Low, Medium, High. Another actor shows the same 13 ads with these labels and equal values |
| F8 | A plain GET of `videoUrl` (no cookies, no extra headers) returns 200 `video/mp4`, 2 to 11 MB in 2 to 4 s. A plain GET of `coverImageUrl` returns 200 `image/jpeg`, 90 to 520 KB |
| F9 | `detailUrl` without login redirects to the Top Ads list, which asks to log in after 4 ads. A record's `url` can be checked only with a Creative Center login |
| F10 | `adText` can contain @mentions of people (13 of 296 rows had a mention) |

Samples are in `part1/collectors/02_tiktok_ad_library/samples/`: `apify_fetchcat_dataset.json` (296 rows), `apify_fetchcat_run_summary.json`, `apify_fetchcat_run_settled.json`, `apify_fetchcat_run_at_finish.json`, `apify_fetchcat_run_log.txt`, `apify_fetchcat_jinx_verify_run.json` (the exact Jinx input below), `apify_media_get_results.json`, `apify_dataxplorer_label_evidence.json`, `creative_center_detail_without_login.json`. Rows and brand mentions per brand: Batiste 0 / 0, Living Proof 18 / 1, Death Wish Coffee 224 / 0, Black Rifle Coffee 49 / 0, Jinx 5 / 2.

## 3. Input
`brand_inputs.json`:
```json
{
  "batiste": {"keywords": ["Batiste"], "match_terms": ["batiste"], "kept_mentions": []},
  "living-proof": {"keywords": ["Living Proof"], "match_terms": ["living proof", "livingproof"], "kept_mentions": []},
  "death-wish-coffee": {"keywords": ["Death Wish Coffee", "Death Wish"], "match_terms": ["death wish coffee", "deathwishcoffee"], "kept_mentions": []},
  "black-rifle-coffee": {"keywords": ["Black Rifle Coffee", "Black Rifle", "BRCC"], "match_terms": ["black rifle coffee", "blackriflecoffee", "brcc"], "kept_mentions": []},
  "jinx": {"keywords": ["Jinx", "thinkjinx"], "match_terms": ["@jinx", "#jinxpartner", "thinkjinx"], "kept_mentions": ["jinx"]}
}
```
- A row mentions the brand when a `match_terms` entry is a substring of `adText.lower()` or `brandName.lower()`. Plain `jinx` would also match unrelated uses of the word, so Jinx uses its account mention, partner hashtag and domain.
- `kept_mentions` are account names (lowercase, without `@`) that stay in `adText`.

Actor input, exactly: `{"keywords": <keywords>, "regions": ["US"], "period": "180", "sortBy": "for_you", "maxItems": 1000}`.

The token is the text after `APIFY_TOKEN=` in `.env` at the repository root, with spaces and quotes stripped. API calls send `Authorization: Bearer <token>`.

| Constant | Value |
|---|---|
| `ACTOR_BUILD` | `0.1.30` |
| `RUN_TIMEOUT_S` / `RUN_MEMORY_MB` | 300 / 512 |
| `MAX_TOTAL_CHARGE_USD` | 0.25 (the most a run can cost is 0.005 + 1000 × 0.00020537 = $0.21) |
| `ITEM_LIMIT` | 1000 (the actor's maximum `maxItems`) |
| `RUN_WAIT_S` | 360, counted from the start request |
| `API_TIMEOUT_S` | 90 |
| `VIDEO_TIMEOUT_S` / `COVER_TIMEOUT_S` | 60 / 30 |
| `MEDIA_SPACING_S` | 2 |

## 4. Procedure
Standard library only (`urllib.request`, `json`, `hashlib`, `re`). One request at a time, each sent once.

1. **Start.** Send the start request of F1 with the values of section 3. Keep `data` as the run.
2. **Wait.** While the run's status is not terminal and less than `RUN_WAIT_S` has passed, send the GET of F2 with `waitForFinish=60` and keep its `data`. Waiting like this is not a retry.
3. **Rows.** GET the dataset (F2) once, whatever the run's final status. A body that is not JSON counts as a failed request. Check the list with `check_rows`.
4. **Summary.** GET `RUN_SUMMARY` (F4) once. HTTP 404, or any other failure, means it is missing.
5. **Select.** For each row in order: `find_match_terms(row, match_terms)`. An empty result adds `adId` to `extra.unmatched_ad_ids`, and nothing else is written for that row. Otherwise the row is kept.
6. **Personal data.** For a kept row, apply `remove_personal_data`:
   - `brandName` and `advertiserName` become `null` unless, lowercased, they contain one of the `match_terms`. They can hold a person's name.
   - Each mention in `adText`, matched by `@[^\s#@]+`, becomes `@<removed>` unless its name is in `kept_mentions`. Only the first word of a two-word display name is removed.
7. **Media.** For a kept row, GET `videoUrl` and then `coverImageUrl` once each, with `VIDEO_TIMEOUT_S` and `COVER_TIMEOUT_S`, no added headers, and `MEDIA_SPACING_S` before every media GET except the first of the run. Status 200 with `Content-Type` `video/mp4` (video) or `image/jpeg` (cover) is success: write the body to `media/<brand>/<run_id>/<adId>.mp4` or `.jpg`. Anything else is a failure, recorded in the record. The URLs expire about 6 h after the actor read them (F3), so they are fetched in the same run.
8. **Write** the record, then go on to the next row.

## 5. Output
One record per kept row:
| Field | Value |
|---|---|
| `key` | `adId` |
| `kind` | `ad` |
| `url` | `detailUrl` (needs a Creative Center login, F9) |
| `fetched_at` | When the dataset response arrived |
| `raw.item` | The row, with step 6 applied |
| `raw.matched_terms` | The `match_terms` found in step 5 |
| `raw.video`, `raw.cover` | `{"file": "media/<brand>/<run_id>/<adId>.mp4", "bytes": 10682762, "sha256": "...", "error": null}`. On failure `file`, `bytes` and `sha256` are `null` and `error` is `http_<status>`, `content_type: <value>` or `request_error: <message>` |

Run result: `source` is `tiktok_ads`. `expected_total` is `null`. `requests` counts API calls plus media GETs. `cost_usd` is `cost_usd(run, rows)` from the last run object, because `usageTotalUsd` is not settled yet when the collector finishes (F5). `extra` is `{"apify_run_id": "...", "rows": 5, "unmatched_ad_ids": ["..."], "run_summary": {}}`. `rows` is the number of dataset rows, and `run_summary` is `null` when it is missing.

Problems, in this order:
1. `apify_run_<status>` when the final status is not `SUCCEEDED`.
2. `run_summary_missing`.
3. `actor_summary_not_clean` when any of these holds: the summary's `status` is not `SUCCEEDED`, `failed` is not 0, `errors` or `warnings` is not empty, or `saved` differs from `rows`.
4. `item_limit_reached` when `rows` is `ITEM_LIMIT`.
5. `media_failed=<n>`, where n is the number of failed video and cover files.

| Condition, checked in this order | `status` | `reason` |
|---|---|---|
| No token | `could_not_look` | `missing_token` |
| The start, wait or dataset request failed | `could_not_look` | `apify_start: <error>`, `apify_wait: <error>` or `apify_dataset: <error>` |
| The run is not terminal after `RUN_WAIT_S` | `could_not_look` | `apify_wait_timeout` |
| `check_rows` failed | `could_not_look` | `item_shape_changed: <message>` |
| No problems | `ok` | empty. 0 records means no Top Ad mentions the brand |
| Problems and 0 rows | `could_not_look` | the problems, joined with `; ` |
| Problems and at least one row | `partial` | the problems, joined with `; ` |

## 6. Tests
Four pure functions, tested against the sample files. No network.

```python
def check_rows(rows) -> None: ...  # ValueError unless a list of dicts that each have adId, detailUrl, adText, brandName, advertiserName, keyword, videoUrl, coverImageUrl
def find_match_terms(row: dict, match_terms: list[str]) -> list[str]: ...
def remove_personal_data(row: dict, match_terms: list[str], kept_mentions: list[str]) -> dict: ...
def cost_usd(run: dict, rows: int) -> float: ...  # start price + rows × row price, rounded to 8 places
```

| Input | Expected |
|---|---|
| `response` of `apify_fetchcat_dataset.json` | `check_rows` passes |
| the same with `videoUrl` removed from row 0 | `ValueError` |
| dataset rows grouped by `keyword` into the brands of section 3 | Batiste 0, Living Proof 18, Death Wish Coffee 224, Black Rifle Coffee 49, Jinx 5 |
| `find_match_terms` on each brand's rows | Living Proof: only `7531018269878140936` with `["living proof", "livingproof"]`. Jinx: `7619486503161118737` and `7609180755211075600`, each `["@jinx", "#jinxpartner"]`. All other rows `[]` |
| `remove_personal_data` of `7531018269878140936`, Living Proof terms | `adText` ends with `Inspo: @<removed>  #livingproofinc #coffeetray #summeressentials #hairtok`; `brandName` stays `Living Proof` |
| the same row with `brandName` `Some Person` | `brandName` is `None`; `find_match_terms` still gives `["livingproof"]` |
| `remove_personal_data` of `7609180755211075600`, Jinx terms and `["jinx"]` | `adText` unchanged |
| `cost_usd` of `response` in `apify_fetchcat_run_settled.json`, 296 rows | 0.06578952 (its settled `usageTotalUsd`) |
| `cost_usd` of `run_final` in `apify_fetchcat_jinx_verify_run.json`, 5 rows | 0.00602685 (the last `usage_reads` value) |

## 7. Done when
1. The tests pass.
2. `--brand jinx` ends `ok`. Every record has a video and a cover file whose size and SHA-256 match the record.
3. `--brand batiste` ends `ok`.
4. A second run adds new files and leaves the first run's files unchanged.
5. `--all` costs less than $0.50 in total, and no `adText` contains a mention other than `@<removed>` or a kept one.

## 8. Where the pipeline finds each value
The attributes were confirmed by the user on 2026-11-10 (`source_info.md` section 9-1).

| Attribute | Location |
|---|---|
| ad_id, detail_url | `raw.item.adId`, `raw.item.detailUrl` |
| brand, match_basis | the run result's `brand`, `raw.matched_terms` |
| ad_text, brand_name_raw | `raw.item.adText`, `raw.item.brandName` |
| likes, ctr_percentile, budget_tier | `raw.item.likes`, `raw.item.ctr` (0.39 = top 39%), `raw.item.costIndex` (0 Low, 1 Medium, 2 High) |
| objective, industry | `raw.item.objectiveKey`, `raw.item.industryKey` (codes; the actor gives no names) |
| duration_sec, video_file, cover_image | `raw.item.durationSeconds`, `raw.video.file`, `raw.cover.file` |
| region, lookback_days, search_keyword, rank | `raw.item.countryCode`, `raw.item.periodDays`, `raw.item.keyword`, `raw.item.rank` (collection order, not popularity) |
| collected_via, collected_at | `fetch_cat` build `0.1.30`; record `fetched_at` |
| is_active | not in the data; the rows carry no shown dates |
