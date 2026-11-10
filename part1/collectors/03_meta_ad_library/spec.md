# Spec: source 3, Meta Ad Library raw collector

- Shared contract: `part1/collectors/README.md`. Read it first; this document adds only what is specific to this source.
- Research notes: `part1/collectors/03_meta_ad_library/source_info.md`. Where they differ from this spec, this spec is newer.
- Every fact below was observed on 2026-11-10, on the live site, in two paid Apify runs or in the Apify API documentation. If something behaves differently, or a step needs something this spec does not give, stop and report. Do not guess.

## 1. What to build
One file, `source_collector.py`. For each of a brand's Facebook pages it reads the number of active US ads from the Ad Library page, fetches those ads with the Apify Actor `apify/facebook-ads-scraper`, downloads each ad's image and video files, and writes one record per ad. Playwright (only to read the count) and the standard library; Apify is called over its REST API. No retries.

The Actor is needed because the page carries only the first 30 ads and the site refuses the request for the rest from datacenter IPs (F3). The page is needed because the Actor's output has no total (F6); without the count the collector cannot tell whether it got everything.

It does not extract values, filter by placement, decide which ads are running, or download HD video or resized images.

## 2. Facts about the source
| # | Fact |
|---|---|
| F1 | The list URL `https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&view_all_page_id=<page_id>&search_type=page&media_type=all` opens without login in headless Chrome (`channel="chrome"`). The first document response is a 403 page that reloads itself. The second, within 3 seconds, is 200 and carries the data. A plain HTTP GET receives only the 403 page, so a browser is needed |
| F2 | The 200 document has one `<script type="application/json" ... data-sjs>` block containing the key `search_results_connection`. That object's `count` (an integer) is the number the page shows as `~N results`. A page with no active US ads has `count` 0 |
| F3 | The document lists at most 30 ads. The rest come from a request the page sends on scroll. From a datacenter IP the site refused it every time (69 of 69); from a residential IP it allowed it every time (29 of 29). The document itself loaded with data from both |
| F4 | `https://www.facebook.com/ads/library/?id=<adArchiveID>` shows that ad with its Library ID, start date and platforms |
| F5 | The Actor takes the list URL in `startUrls` and writes one dataset item per ad. For Living Proof (`count` 98) it returned in 64 s the same 98 ads that were collected directly, although the run was started from the datacenter IP of F3 |
| F6 | Every item has these fields:<br>- `adArchiveID`: a string of digits<br>- `pageId`<br>- `isActive`: always `true`<br>- `inputUrl`: the URL sent<br>- `startDate`, `publisherPlatform`, `snapshot`<br>`snapshot.images`, `snapshot.videos` and `snapshot.cards` are lists. Items have no total count and no fetch time |
| F7 | Price: $0.0058 per dataset item, with no start fee. In both test runs the charge was exactly items × $0.0058. The run's own charge counters lag for several minutes after the run ends |
| F8 | Apify API:<br>- `POST /v2/acts/<actor>/runs` takes `timeout`, `maxItems`, `maxTotalChargeUsd` and `waitForFinish` (at most 60 s)<br>- terminal run statuses: `SUCCEEDED`, `FAILED`, `TIMED-OUT`, `ABORTED`; the others are `READY`, `RUNNING`, `TIMING-OUT`, `ABORTING`<br>- `GET /v2/datasets/<id>/items` returns all items when no `limit` is given |
| F9 | Where the media is:<br>- `IMAGE` ads: `snapshot.images[]`<br>- `VIDEO` ads: `snapshot.videos[]`<br>- `DCO` and `DPA` ads: `snapshot.cards[]`; a card can hold an image, a video, both or neither<br>Every video with `videoHdUrl` also has `videoSdUrl`. Media URLs are signed and expire in 3 to 4 days. Their hosts end in `.fbcdn.net`, and a plain GET downloads them. The last path segment is unique per file and stays the same across fetches |
| F10 | Living Proof: SD videos are up to 3.5 MB and original images about 0.7 MB (median). Its 98 ads have 273 distinct files under the media choice in section 3 |
| F11 | In a partner ad, `snapshot.pageId` differs from the item's `pageId`. `snapshot.pageName`, `pageProfileUri`, `pageProfilePictureUrl` and `pageId` then describe the creator's account. This was 11 of 98 Living Proof ads and 99 of 250 Jinx ads. In one Jinx ad, `snapshot.brandedContent` points to a page other than the brand's. Creator names appear in no other field |

Samples are in `part1/collectors/03_meta_ad_library/samples/`: `site/` for the page, `apify/` for Actor items and run objects. Active US ads on 2026-11-10: Batiste 4 + 8, Living Proof 98, Death Wish Coffee 47, Black Rifle Coffee 19, Jinx 250.

## 3. Input
`brand_inputs.json`:
```json
{
  "batiste": {"page_ids": ["95597922197", "230750427654291"]},
  "living-proof": {"page_ids": ["40730897173"]},
  "death-wish-coffee": {"page_ids": ["159943490729618"]},
  "black-rifle-coffee": {"page_ids": ["497476893723547"]},
  "jinx": {"page_ids": ["2012712129023317"]}
}
```

Choices made with the user on 2026-11-10: both Batiste pages; one record per ad; media = original images, SD videos and video preview images; partner ads kept with the creator fields removed; all placements kept.

| Constant | Value |
|---|---|
| `COUNT_TIMEOUT_S` | 30 |
| `SITE_SPACING_S` | 15 |
| `RESULTS_MARGIN` | 50 |
| `RESULTS_MAX` | 1000 |
| `PRICE_USD` | 0.0058 |
| `RUN_TIMEOUT_S` | 1800 |
| `WAIT_LIMIT_S` | 2100 |
| `HTTP_TIMEOUT_S` | 90 |
| `MEDIA_TIMEOUT_S` | 60 |
| `MEDIA_SPACING_S` | 1 |

## 4. Procedure
If `APIFY_TOKEN` is missing from `.env`, write the run result (`could_not_look`, `missing_token`) and stop before any request.

Requests are made one at a time, with `SITE_SPACING_S` between navigations to `www.facebook.com` (also across brands) and `MEDIA_SPACING_S` between media GETs. A page that gets a reason skips its remaining steps, except where a step says otherwise.

1. **Counts.** Start Playwright (`chromium.launch(headless=True, channel="chrome")`, context `locale="en-US"`) and keep the body of every response whose `request.resource_type` is `document`. For each page ID:
   - Open the list URL with `wait_until="domcontentloaded"`. Call `page.wait_for_timeout(500)` until a kept body contains `search_results_connection` or `COUNT_TIMEOUT_S` has passed.
   - No such body: the reason is `blocked` when the page's host is not `www.facebook.com` or its path starts with `/checkpoint` or `/login` (the brand's remaining pages then get `not_attempted` and are not opened), otherwise `count_timeout`.
   - Otherwise `count = parse_site_count(body)`; a `ValueError` gives `count_shape_changed`. A page with `count` 0 is done.

   Close the browser after the last page.
2. **Run.** For each page with `count` above 0, compute `limit = min(count + RESULTS_MARGIN, RESULTS_MAX)` and `cap = ceil(limit * 58 / 100) / 100` with an integer ceiling (148 gives 0.86). Send `POST https://api.apify.com/v2/acts/apify~facebook-ads-scraper/runs?timeout=1800&maxItems=<limit>&maxTotalChargeUsd=<cap>&waitForFinish=60`, with `Authorization: Bearer <token>` and this body:
   ```json
   {"startUrls": [{"url": "<list URL>"}], "resultsLimit": <limit>, "activeStatus": "active", "onlyTotal": false,
    "includeAboutPage": false, "isDetailsPerAd": false, "enrichWithEcommerceData": false}
   ```
   The response's `data` is the run. A non-2xx response or an error gives `apify_start_failed: <http status or error>`.
3. **Wait.** While the run's `status` is not terminal (F8), send `GET https://api.apify.com/v2/actor-runs/<id>?waitForFinish=60`; this is waiting, not retrying. A failed GET gives `apify_poll_failed: <http status or error>`. A run still not terminal `WAIT_LIMIT_S` after the POST gives `apify_wait_exceeded`.
4. **Items.** `GET https://api.apify.com/v2/datasets/<defaultDatasetId>/items?format=json&clean=1`; a failed GET gives `apify_dataset_failed: <http status or error>`. Then, in order:
   - A run that ended other than `SUCCEEDED` also gives `apify_run_<status in lower case, "-" as "_">`; its items are still used.
   - If any item lacks a digit-string `adArchiveID` or a `snapshot` whose `images`, `videos` and `cards` are lists, the reason is `apify_shape_changed` and nothing from the page is written.
   - Items whose `adArchiveID` was already seen in this brand run are skipped.
   - Fewer distinct ads than `count` gives `incomplete: got=<n> count=<count>`; the ads received are still written. More than `count` is fine (ads that started in the meantime).
5. **Each ad, in dataset order:** call `remove_partner_fields(item)`. For each `(field, url)` in `media_targets(item)`, the file is `media/<brand>/<last path segment of url>`. If it exists (from this or an earlier run), use it with no request. Otherwise GET the URL once (`MEDIA_TIMEOUT_S`, a Chrome `User-Agent`) and write the body on HTTP 200; any other outcome makes the entry `null`. Then write the record.

`remove_partner_fields(item)`: if `str(snapshot.pageId) != str(item.pageId)`, set `snapshot.pageName`, `pageProfileUri`, `pageProfilePictureUrl` and `pageId` to `null`. If `snapshot.brandedContent` is an object whose `pageId` differs from `item.pageId`, set its `pageName`, `pageProfileUri` and `pageId` to `null`.

`media_targets(item)` returns `(field path, url)` for the non-null values of `snapshot.images[i].originalImageUrl`, then `snapshot.videos[i]` `videoSdUrl` and `videoPreviewImageUrl`, then `snapshot.cards[i]` `originalImageUrl`, `videoSdUrl` and `videoPreviewImageUrl`.

## 5. Output
One record per ad:
| Field | Value |
|---|---|
| `key` | `item.adArchiveID`, for example `1776927800243326` |
| `kind` | `ad` |
| `url` | `https://www.facebook.com/ads/library/?id=<adArchiveID>` (F4) |
| `fetched_at` | The run's `finishedAt`, to the second, for example `2026-11-10T08:55:17Z` |
| `raw.page_id` | The page ID the ad was fetched for |
| `raw.item` | The Actor's item, after `remove_partner_fields` |
| `raw.media` | Object from field path (for example `snapshot.cards[0].originalImageUrl`) to `media/<brand>/<name>`, or to `null` when the GET failed |

Run result: `source` is `meta_ad_library`. `expected_total` is the sum of the pages' `count` when every page has one, else `null`. `requests` counts page navigations, Apify API requests and media GETs. `cost_usd` is items read × `PRICE_USD` (F7), summed over the runs. `extra` is like `{"counts": {"40730897173": 98}, "runs": {"40730897173": "<run id>"}, "media_files": 350, "media_failed": 0}`, where `media_files` counts `raw.media` entries and `media_failed` the `null` ones. `extra.pages` is like `{"40730897173": {"ads_complete": true, "reasons": []}}`, one entry per page ID in input order (`{}` when no page ID is known). `ads_complete` is true when the page's ad list was read in full (it has a count and no page reason); media download failures do not affect it. `reasons` are the page reasons that name the page.

A page reason is written `<reason>(<page_id>)`, plus `: <detail>` when it has one, for example `incomplete(2012712129023317): got=240 count=250`.

| Condition, checked in this order | `status` | `reason` |
|---|---|---|
| No token | `could_not_look` | `missing_token` |
| Chrome did not start | `could_not_look` | `browser: <message>` |
| No page has a reason and no media entry is `null` | `ok` | empty |
| 0 records written | `could_not_look` | the page reasons, joined with `; ` |
| Anything else | `partial` | the page reasons, then `media_failed=<n>` if above 0, joined with `; ` |

A brand whose pages all have `count` 0 is `ok` with 0 records.

## 6. Tests
Three pure functions, tested against `part1/collectors/03_meta_ad_library/samples/`. No network.
```python
def parse_site_count(html: str) -> int: ...                  # ValueError if the block, the key or an integer count is missing
def media_targets(item: dict) -> list[tuple[str, str]]: ...
def remove_partner_fields(item: dict) -> None: ...            # changes item in place
```
| Input | Expected |
|---|---|
| `site/list_page_livingproof.html` | 98 |
| `site/list_page_zero.html` | 0 |
| `site/challenge_403.html` | `ValueError` |
| `media_targets` over all items of `apify/items_livingproof_98.json` | 350 pairs, 273 distinct last path segments |
| item `1107817355342261` (VIDEO) | `snapshot.videos[0].videoSdUrl`, `snapshot.videos[0].videoPreviewImageUrl` |
| item `2233227510961160` | no pair for `snapshot.cards[1]`, a card without media |
| `remove_partner_fields` over the 98 items | 11 items change; in each, the four `snapshot` fields are `null` and `snapshot.brandedContent.pageId` is still `40730897173` |
| item `1776927800243326` with `brandedContent` `{"pageId": "111", "pageIsDeleted": false, "pageProfileUri": "https://www.facebook.com/x/", "pageName": "X"}` | `brandedContent.pageId`, `pageName` and `pageProfileUri` are `null`; nothing else changes |

## 7. Done when
These runs cost money. At the counts of 2026-11-10, items 2 to 4 fetch 50 ads ($0.29), and one `--all` run fetches 426 ads ($2.47).
1. The tests pass.
2. `--brand black-rifle-coffee` ends `ok`, with `records` at least `expected_total` and a file for every non-null `raw.media` entry.
3. `--brand batiste` ends `ok`, with both page IDs in `extra.counts`.
4. A second run of item 2 adds new files, leaves the first run's files unchanged, and downloads no media file that already exists.
5. Without `APIFY_TOKEN` the run ends `could_not_look` / `missing_token` with `requests` 0.
6. For three records, `url` shows the same Library ID, and a start date equal to the UTC date of `raw.item.startDateFormatted`.
7. In the Jinx records, every `raw.item.snapshot.pageName` is `Jinx` or `null`.

## 8. Where the pipeline finds each value
Field meanings are in `source_info.md` sections 4 to 7, which use snake_case names (`ad_archive_id`) for the same fields.

| Attribute | Location |
|---|---|
| ad_id, page_id, page_name | `raw.item.adArchiveID`, `raw.item.pageId`, `raw.item.pageName` |
| is_active, started_at | `raw.item.isActive`, `raw.item.startDate` (UTC seconds, midnight US Pacific) |
| placements | `raw.item.publisherPlatform[]` |
| creative group | `raw.item.collationId`, `raw.item.collationCount` |
| format | `raw.item.snapshot.displayFormat` (`IMAGE`, `VIDEO`, `DCO`, `DPA`) |
| body, title, caption, landing URL, call to action | `raw.item.snapshot.body.text`, `.title`, `.caption`, `.linkUrl`, `.ctaText`; per card in `snapshot.cards[]` |
| partner ad | `raw.item.snapshot.brandedContent` is not `null` |
| media files | `raw.media` (field path to file) |
| reach, spend | `raw.item.reachEstimate`, `raw.item.spend`: empty for US commercial ads |
