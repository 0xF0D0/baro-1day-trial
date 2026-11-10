# Spec: source 1, Google Ads Transparency Center raw collector

- Shared contract: `part1/collectors/README.md`. Read it first; this document adds only what is specific to this source.
- Research notes: `part1/collectors/01_google_ads_transparency/source_info.md`. Where they differ from this spec, this spec is newer.
- Every fact below was observed on the live site on 2026-11-10. If the site behaves differently, or a step needs something this spec does not give, stop and report. Do not guess.

## 1. What to build
One file, `source_collector.py`. Given a brand, it reads every Google ad creative that points to the brand's domain from the Ads Transparency Center and writes one record per creative. No paid service, no retries.

It does not extract ad text, decide which ads are "running now", convert dates, or download images and videos. It writes the responses down so that can be done later.

## 2. Facts about the source
| # | Fact |
|---|---|
| F1 | `https://adstransparency.google.com/?region=US&domain=<domain>&hl=en` opens without login, in headless Chrome |
| F2 | On load the page sends `SearchService/SearchCreatives`, twice with the same body. The response has `1` (array of ads), `4` and `5` (lowest and highest possible total, as strings; equal when the count is exact), and `2` (next-page token) only when more pages exist. At most 40 ads per response. A domain with no ads returns `{}` |
| F3 | To load the next page: click the element with the text `See all ads` once, then scroll to the bottom. A single scroll does not always send the next request; scrolling again every 2.5 seconds does (Living Proof, headless: 232 ads, 7 responses). The last page has no `2` |
| F8 | Page loads 3 seconds apart get HTTP 429 on the document after about 9 loads (every brand on 2026-11-10). 10 seconds apart, all 33 Death Wish Coffee details loaded |
| F9 | A pass of the five brands on 2026-11-10 loaded 169 details (23, 4, 33, 66 and 43), 12 seconds each with the spacing of F8: 34 of the pass's 35 minutes. An ad's detail rarely changes from one hour to the next |
| F4 | Every list item has the keys `1` (advertiser ID), `2` (creative ID), `3` (preview), `4` (format), `6` (first shown), `7` (last shown), `12` (advertiser name), `13`, `14` (domain). The list is ordered by last shown, newest first, and includes ads that ended months ago |
| F5 | Opening `https://adstransparency.google.com/advertiser/<1>/creative/<2>?region=US&hl=en` sends `LookupService/GetCreativeById`, answered within 1 to 4 seconds. Its `1` has the keys `1`, `2`, `4`, `5`, `8`, `17`, `22`; `5` is the array of variations and `22` holds the advertiser name |
| F6 | A variation is `{"3": {"2": "<img src=...>"}}` (image preview) or `{"1": {"4": "<url>"}}` (script preview). A plain GET of the script URL returns 60 to 150 KB of JavaScript |
| F7 | Ads pointing to a brand's domain also come from other advertisers, some of them private individuals advertising under their own name |

Samples for all of these are in `part1/collectors/01_google_ads_transparency/samples/`. Ads per domain on 2026-11-10, and how many were last shown within 7 days: Batiste 67 / 23, Living Proof 232 / 43, Death Wish Coffee 39 / 34, Black Rifle Coffee 36 / 4, Jinx 319 / 66.

## 3. Input
`brand_inputs.json`:
```json
{
  "batiste": {"domain": "batistehair.com", "named_advertiser_ids": ["AR09009539290362806273"]},
  "living-proof": {"domain": "livingproof.com", "named_advertiser_ids": ["AR07298081684325400577"]},
  "death-wish-coffee": {"domain": "deathwishcoffee.com", "named_advertiser_ids": ["AR06827167829175828481", "AR00565706807029268481"]},
  "black-rifle-coffee": {"domain": "blackriflecoffee.com", "named_advertiser_ids": ["AR02712956018534383617"]},
  "jinx": {"domain": "thinkjinx.com", "named_advertiser_ids": ["AR05357902879204048897"]}
}
```
`named_advertiser_ids` are the brand's own accounts (and one agency for Death Wish Coffee). Only their names are kept and only their script previews are fetched (F7).

| Constant | Value |
|---|---|
| `LIST_TIMEOUT_S` | 30 |
| `PAGE_TIMEOUT_S` | 10 |
| `SCROLL_EVERY_S` | 2.5 |
| `MAX_LIST_RESPONSES` | 50 |
| `DETAIL_WINDOW_DAYS` | 7 |
| `DETAIL_TIMEOUT_S` | 20 |
| `DETAIL_SPACING_S` | 10 (F8) |
| `DETAIL_REFRESH_HOURS` | 24 |
| `MAX_FAILURES_IN_A_ROW` | 5 |
| `SCRIPT_TIMEOUT_S` | 20 |

## 4. Procedure
Playwright, `chromium.launch(headless=True, channel="chrome")`, context `locale="en-US"`, `viewport={"width": 1400, "height": 950}`. One page, one request at a time. Wait `DETAIL_SPACING_S` before every page navigation except the first one of the process. The collector only reads responses to requests the page sends itself; the script preview GET in step 5 is the one exception.

**Blocked** means: after a navigation the page's host is not `adstransparency.google.com`, or the document status is 400 or higher, or the page text contains `unusual traffic`; or a `SearchCreatives` or `GetCreativeById` response has a status other than 200. The first signal of a run is written to `extra.block_signal` (`check`, `host`, `path`, `status`), otherwise `null`.

1. **List.** Open the list URL and wait up to `LIST_TIMEOUT_S` for the first `SearchCreatives` response. Collect ads from every `SearchCreatives` response, de-duplicated by `2`.
2. **Paging.** If the latest response has `2`: click `See all ads` once, then repeat: scroll to the bottom every `SCROLL_EVERY_S` for up to `PAGE_TIMEOUT_S` until a response containing an ad not seen before arrives. The list is complete when a response without `2` arrives. If no new response arrives, or `MAX_LIST_RESPONSES` is reached, the list is incomplete; go on with the ads collected.
3. **Scope.** An ad gets a detail request when `int(item["7"]["1"]) >= run_start_epoch - DETAIL_WINDOW_DAYS * 86400`. Older ads are written from the list alone with `detail_state` `skipped_old`.
   An in-scope ad whose detail was fetched less than `DETAIL_REFRESH_HOURS` before this run's start, according to the brand's earlier `raw/<brand>/*.jsonl` files (`detail_state` `fetched`, `fetched_at` inside the window, no script file `null`), is written without loading its detail page: `detail_state` `skipped_recent`, with `raw.detail` and `raw.script_files` copied from the latest such record and `raw.detail_fetched_at` set to that record's `fetched_at`. It counts as in scope and is not a failure.
4. **Detail.** For each in-scope ad in list order, open its detail URL and wait up to `DETAIL_TIMEOUT_S` for `GetCreativeById`. It is valid when its `1.1` and `1.2` match the list item and `1.5` is a list. Otherwise `detail_state` is `failed` with `detail_error` `timeout`, `invalid` or `blocked` (a navigation that raises counts as `timeout`). After `MAX_FAILURES_IN_A_ROW` failed ads in a row, or as soon as one is `blocked`, make no more detail requests: the remaining in-scope ads get `not_attempted`.
5. **Script previews.** Only when the advertiser is in `named_advertiser_ids`: for each variation with `["1"]["4"]`, GET the URL once (`context.request.get`, `SCRIPT_TIMEOUT_S`) and write the body gzipped to `raw/<brand>/<run_id>.scripts/<creative id>_<variation index>.js.gz`.
6. **Names.** When the advertiser is not in `named_advertiser_ids`, set `list_item["12"]` and `detail["22"]` to `null`.
7. **Write** the record, then go on to the next ad.

## 5. Output
One record per creative:
| Field | Value |
|---|---|
| `key` | `<item.1>/<item.2>`, for example `AR09009539290362806273/CR18313658679477403649` |
| `kind` | `ad` |
| `url` | `https://adstransparency.google.com/advertiser/<item.1>/creative/<item.2>?region=US` |
| `fetched_at` | When the detail response arrived; without one, when the list response arrived |
| `raw.list_item` | The list item |
| `raw.detail` | `1` of the detail response (for `skipped_recent`, copied from the earlier record), or `null` |
| `raw.detail_state` | `fetched`, `skipped_old`, `skipped_recent`, `failed` or `not_attempted` |
| `raw.detail_error` | `null`, `timeout`, `invalid` or `blocked` |
| `raw.script_files` | Object from variation index to file path relative to `raw/<brand>/`, or to `null` when the GET failed. `{}` when there was nothing to fetch. Copied from the earlier record for `skipped_recent` |
| `raw.detail_fetched_at` | When the detail in `raw.detail` was read: equal to `fetched_at` for `fetched`, the earlier record's `fetched_at` for `skipped_recent`, else `null` |

Run result: `source` is `google_ads_transparency`. `expected_total` is `int(4)` when `4` equals `5`, else `null`. `requests` counts page navigations, scrolls and script GETs. `extra` is `{"list_complete": true, "total_min": 200, "total_max": 300, "in_scope": 43, "details_fetched": 43, "details_skipped_recent": 0, "block_signal": null}`.

| Condition, checked in this order | `status` | `reason` |
|---|---|---|
| Chrome did not start, or the list page did not load | `could_not_look` | `browser: <message>` |
| The list page is blocked | `could_not_look` | `blocked` |
| No `SearchCreatives` response in time | `could_not_look` | `list_timeout` |
| The first response is not `{}` and an item lacks `1`, `2`, `4` or `7` | `could_not_look` | `list_shape_changed` |
| The first response is `{}` | `ok` | empty; 0 records |
| List complete, ad count equals `expected_total` when that is set, every in-scope detail `fetched` or `skipped_recent`, no script file `null` | `ok` | empty |
| Anything else | `partial` | what applies, joined with `; `: `list_incomplete` or `count_mismatch(expected=<n>, got=<m>)`, `details_failed=<n>`, `details_not_attempted=<n>`, `scripts_failed=<n>` |

## 6. Tests
Three pure functions, tested against the sample files (use each file's `response` object). No network.

```python
def parse_list(resp: dict) -> tuple[list[dict], str | None, int | None, int | None]: ...  # items, next token, total min, total max; raises ValueError on a bad shape
def in_scope(item: dict, run_start_epoch: int) -> bool: ...
def script_urls(detail: dict) -> dict[int, str]: ...  # detail = the response's `1` (as in raw.detail); variation index -> url
```

| Input | Expected |
|---|---|
| `list_deathwishcoffee.json` | 30 items, no token, totals 30 and 30 |
| `list_batiste_page1.json` | 40 items, token starts with `CgoAP7zmiMGEloKvEhBXJNEL`, totals 67 and 67 |
| `list_batiste_page1.json` + `list_batiste_page2.json`, de-duplicated | 67 ads; the first key is `AR09009539290362806273/CR18313658679477403649` |
| `list_livingproof_page1.json` | totals 200 and 300 |
| `list_zero.json` | 0 items, no token, totals `None` |
| Death Wish list with `2` removed from one item | `ValueError` |
| Death Wish list, run start `2026-11-10T08:00:00Z` | 25 in scope, 5 out |
| `detail_text_3_variations.json` | `script_urls` is `{}` |
| `detail_script_video.json` | `script_urls` has one entry, index 0, URL starting with `https://displayads-formats.googleusercontent.com/ads/preview/content.js` |

## 7. Done when
1. The tests pass.
2. `--brand death-wish-coffee` ends `ok` with as many records as the list page shows.
3. `--brand batiste` ends `ok` with more than 40 records.
4. `--brand living-proof` ends `ok` with `expected_total` `null` and a record count between `extra.total_min` and `extra.total_max`.
5. A second run adds new files and leaves the first run's files unchanged.
6. No `black-rifle-coffee` record contains an advertiser name other than `Black Rifle Coffee Company LLC`.

## 8. Where the pipeline finds each value
| Attribute | Location |
|---|---|
| creative_id, advertiser_id | `raw.list_item.2`, `raw.list_item.1` |
| advertiser_name, domain | `raw.list_item.12`, `raw.list_item.14` |
| format | `raw.list_item.4` (1 text, 2 image, 3 video) |
| first_shown_at, last_shown_at | `raw.list_item.6.1`, `raw.list_item.7.1` (UTC seconds) |
| last-shown date as the site displays it | `raw.detail.17[].5` |
| variations | `raw.detail.5[]`; image URL in `3.2`, or inside the script file |
