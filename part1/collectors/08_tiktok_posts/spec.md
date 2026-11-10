# Spec: source 8, TikTok posts raw collector

- Shared contract: `part1/collectors/README.md`. Read it first; this document adds only what is specific to this source.
- Research notes: `part1/collectors/08_tiktok_posts/source_info.md` (sections 11 and 12). Where they differ from this spec, this spec is newer.
- Every fact below was observed on 2026-11-10 in real Apify runs, API responses and tiktok.com pages. If Apify behaves differently, or a step needs something this spec does not give, stop and report. Do not guess.

## 1. What to build
One file, `source_collector.py`. Given a brand, it runs the Apify Actor `clockworks/tiktok-scraper` twice, with two inputs, and writes one record per post returned:

| Path | Asks for |
|---|---|
| `profile_popular` | The first 10 posts of the brand's own profile, sorted by Popular |
| `hashtag` | The first 30 posts of the brand's hashtag feed |

The brief asks for "top posts about the brand: creator, views, likes and date". The collector does not rank, filter or extract; the pipeline picks the top posts later. It never contacts tiktok.com itself and downloads no video, image or subtitle files. No retries.

## 2. Facts about the source
| # | Fact |
|---|---|
| F1 | Pricing per event, FREE plan: $0.0037 per result, $0.001 per run start. Other events (filters, sorting, downloads, comments, transcripts, AI) are charged only when the input turns them on. One brand therefore costs $0.038 + $0.112 = $0.15 |
| F2 | The Actor's minimum `maxTotalChargeUsd` is 0.5. A start with 0.10 was rejected with HTTP 400 `max-total-charge-usd-below-minimum`, and no run was created |
| F3 | The two inputs in section 3 (with 10 results each) finished `SUCCEEDED` in 15 and 16 s. The start response, sent with `waitForFinish=60`, already carried the final status and `usageTotalUsd` 0.038, and `chargedEventCounts` was 10 `result` + 1 `actor-start` |
| F4 | The profile path returned the same 10 posts, in the same order, as the Popular tab of `https://www.tiktok.com/@deathwishcoffee`, and each `playCount` equals the view count on the tile (1.8M = 1800000). That order is by likes |
| F5 | Each item is one post. `id` is a string of digits. `webVideoUrl` is `https://www.tiktok.com/@<authorMeta.name>/video/<id>`; for a slideshow it redirects to `/photo/<id>` |
| F6 | The hashtag feed is in no order of views, likes or date, and includes the brand's own posts. On TikTok's tag pages, 20 of the first 20 posts were about the brand or its product for each of the four other chosen tags, and 8 of 10 for `#deathwishcoffee` in the Apify run, versus 0 for `#jinx` (Arcane character), 11 for `#livingproof` and 18 for `#batiste` (the musician Jon Batiste). Every chosen tag has more than 30 posts (smallest: `jinxdogfood`, 159) |
| F7 | Items carry creators' personal data: display name, bio, bio link, avatar and profile URL in `authorMeta`; for a creator's original sound, `musicMeta.musicAuthor` is their display name and `musicMeta.coverMediumUrl` their avatar; display names in `mentions` and `detailedMentions`; a place in `locationMeta`; the display name of an original sound's author is also written into `musicMeta.musicName` |
| F8 | Apify API: run statuses `READY`, `RUNNING`, `TIMING-OUT`, `ABORTING` (not finished) and `SUCCEEDED`, `FAILED`, `TIMED-OUT`, `ABORTED` (finished). `waitForFinish` is at most 60 s. `timeout` on the start request stops the run after that many seconds. `GET /datasets/<id>/items` without `limit` returns every item in order |
| F9 | An Apify run can end `SUCCEEDED` with 0 items (seen by the source 4 thread on Amazon Actors) |

Samples: `part1/collectors/08_tiktok_posts/samples/apify/` (both runs: input, run record, items) and `samples/hashtag_check_20261110.json` (F6).

## 3. Input
`brand_inputs.json`:
```json
{
  "batiste": {"profile": "batiste", "hashtag": "batistedryshampoo"},
  "living-proof": {"profile": "livingproofinc", "hashtag": "livingproofhair"},
  "death-wish-coffee": {"profile": "deathwishcoffee", "hashtag": "deathwishcoffee"},
  "black-rifle-coffee": {"profile": "blackriflecoffee", "hashtag": "blackriflecoffee"},
  "jinx": {"profile": "jinx", "hashtag": "jinxdogfood"}
}
```
Handles without `@`, hashtags without `#`. The user chose these hashtags (F6).

Run input for `profile_popular` (the Actor input; `<profile>` replaced):
```json
{"profiles": ["<profile>"], "profileScrapeSections": ["videos"], "profileSorting": "popular",
 "excludePinnedPosts": false, "resultsPerPage": 10, "maxFollowersPerProfile": 0, "maxFollowingPerProfile": 0,
 "shouldDownloadVideos": false, "shouldDownloadCovers": false, "shouldDownloadSlideshowImages": false,
 "shouldDownloadAvatars": false, "shouldDownloadMusicCovers": false, "downloadSubtitlesOptions": "NEVER_DOWNLOAD_SUBTITLES",
 "commentsPerPost": 0, "scrapeRelatedVideos": false, "scrapeAdditionalAuthorMeta": false, "proxyCountryCode": "None"}
```
Run input for `hashtag`: `{"hashtags": ["<hashtag>"], "resultsPerPage": 30}` plus the ten fields from `shouldDownloadVideos` to `proxyCountryCode` above, with the same values.

| Constant | Value |
|---|---|
| `START_URL` | `https://api.apify.com/v2/acts/clockworks~tiktok-scraper/runs?timeout=300&maxTotalChargeUsd=0.5&waitForFinish=60` |
| `MAX_WAIT_S` | 420 |
| `HTTP_TIMEOUT_S` | 90 |

The token is `APIFY_TOKEN` in `.env` at the repository root: the line starting with `APIFY_TOKEN=`, value stripped of spaces and of one pair of surrounding quotes. It is sent only as `Authorization: Bearer <token>`.

## 4. Procedure
Standard library only (`urllib.request`, `json`). One request at a time, each with `HTTP_TIMEOUT_S`. Every request is sent once; a request that raises or returns an unexpected status ends the path with the error shown. Waiting for a run (step 2) is not a retry. Requests go to Apify, not TikTok, so no spacing is added.

1. **Token.** If it is missing or empty, write the run result `could_not_look` / `missing_token` with 0 records, 0 requests and cost 0, and stop.
2. **Run.** For each path, `profile_popular` first:
   - POST the path's input as JSON to `START_URL`. Anything but HTTP 201 ends the path: `start_http_<status>`, or `start_error` if the request raised.
   - While `data.status` is not finished (F8): if `MAX_WAIT_S` has passed since the POST, end the path with `wait_exceeded`; otherwise GET `https://api.apify.com/v2/actor-runs/<data.id>?waitForFinish=60` and take its `data`. A failed GET ends the path with `poll_error`.
   - The path's cost is `round(data.usageTotalUsd, 6)` from the last run object read; 0 if the start failed.
   - If the final status is not `SUCCEEDED`, end the path with `run_<status>` (for example `run_TIMED-OUT`).
3. **Items.** GET `https://api.apify.com/v2/datasets/<data.defaultDatasetId>/items?format=json`. A failed GET, or a body that is not a JSON array, ends the path with `dataset_error`. Note the time the response arrived.
4. **Records.** For each item, in order, `position` being its 1-based index in the array: skip it and count it in `bad_items` if `id` is not a string of digits or `webVideoUrl` is not a string; skip it, without counting it as bad, if its `id` was already written in this path. Otherwise remove personal data (section 5) and write the record.
5. **Path state.** `failed` if the path ended early in steps 2 or 3, or no record was written (`no_items`). `incomplete` if fewer records than requested (`short(<got>/<requested>)`) or any `bad_items` (`bad_items=<n>`). Otherwise `complete`.

`requests` counts every HTTP request sent to Apify.

## 5. Output
One record per post and path:
| Field | Value |
|---|---|
| `key` | `<path>/<id>`, for example `profile_popular/7106601227126885674` |
| `kind` | `post` |
| `url` | `item.webVideoUrl` |
| `fetched_at` | When the dataset response arrived |
| `raw.path`, `raw.query` | `profile_popular` or `hashtag`, and the handle or hashtag from `brand_inputs.json` |
| `raw.position` | The item's 1-based index in the dataset |
| `raw.item` | The dataset item, with personal data removed |

A post found by both paths gives two records with the same `id` and different keys. The pipeline joins them by `id`.

**Personal data removed** (set to `null` when the key exists; missing keys are not added), in every item including the brand's own: `authorMeta.nickName`, `.signature`, `.bioLink`, `.avatar`, `.originalAvatarUrl`, `.profileUrl`; `musicMeta.musicAuthor`, `.coverMediumUrl`, `.originalCoverMediumUrl`; `mentions`; `nickName` and `profileUrl` in each `detailedMentions` entry; `locationMeta`. The title of a creator's original sound ends in their display name (`original sound - <name>`, also localized): when `musicMeta.musicOriginal` is `true` and `musicMeta.musicName` is a string containing ` - `, only the part before the first ` - ` is kept (`original sound`); the title of a published track is kept as it is. Kept: the handle `authorMeta.name`, `authorMeta.id`, `verified` and the public counts. The caption `text` is kept as published.

Run result: `source` is `tiktok_posts`. `expected_total` is `null`. `cost_usd` is the sum of both paths' costs (a start that raised adds 0; its reason shows `start_error`). `extra`:
```json
{"profile_popular": {"query": "deathwishcoffee", "state": "complete", "error": null, "apify_run_id": "n2AqBFXajcYSVlXCC", "records": 10, "bad_items": 0, "cost_usd": 0.038},
 "hashtag": {"query": "deathwishcoffee", "state": "complete", "error": null, "apify_run_id": "DyYwrr03sEqM1ZF2r", "records": 30, "bad_items": 0, "cost_usd": 0.112}}
```

| Condition, checked in this order | `status` | `reason` |
|---|---|---|
| No token | `could_not_look` | `missing_token` |
| Both paths `failed` | `could_not_look` | `profile_popular: <error>; hashtag: <error>` |
| Both paths `complete` | `ok` | empty |
| Anything else | `partial` | `<path>: <error>` for each path that is not `complete`, joined with `; ` |

## 6. Tests
Four pure functions, tested against `part1/collectors/08_tiktok_posts/samples/apify/`. No network.

```python
def run_input(path: str, query: str) -> dict: ...
def path_records(dataset: object, path: str, query: str) -> tuple[list[dict], int]: ...  # raw objects (personal data removed), bad_items; ValueError if not a list
def remove_personal(item: dict) -> dict: ...  # returns a copy
def cut_sound_title(item: dict) -> dict: ...  # returns a copy; original sound title cut at the first " - " (called by remove_personal)
def decide_status(paths: dict[str, dict]) -> tuple[str, str]: ...  # path -> {"state", "error"}
```

| Input | Expected |
|---|---|
| `run_input("profile_popular", "deathwishcoffee")` | equals `input` in `profile_run.json` |
| `run_input("hashtag", "deathwishcoffee")` | equals `input` in `hashtag_run.json` with `resultsPerPage` 30 |
| items of `profile_deathwishcoffee_popular_10.json` | 10 records; position 1 is `7106601227126885674`, position 10 is `7077553857361956142`; 0 bad |
| items of `hashtag_deathwishcoffee_10.json` | 10 records; position 7 is `7704412939951901966` |
| profile items with `id` removed from the 3rd, plus `{"error": "x"}` appended | 9 records, 2 bad; `7082765480859094318` keeps position 4 |
| `{"items": []}` | `ValueError` |
| hashtag item 9 (`7623471337998191903`) with every removed field set to `"x"` | those fields `None`; `authorMeta.name` `amiyatok`, `playCount` 2266, `detailedMentions[0].name` `deathwishcoffee`; the argument still holds `"x"` |
| hashtag item 1 | no `locationMeta` key added |
| each row of the status table except the first | that row's `status` and `reason` |

## 7. Done when
1. The tests pass.
2. `--brand death-wish-coffee` ends `ok` with 40 records and `cost_usd` 0.15.
3. Right after it, the Popular tab of `https://www.tiktok.com/@deathwishcoffee` shows the `profile_popular` records in position order, with view counts matching `playCount`.
4. `--all` ends `ok` for all five brands.
5. A second run adds new files and leaves the first run's files unchanged.
6. No record has a non-null value in a removed field.

Steps 2 and 4 cost $0.90. Ask the user before any other paid run.

## 8. Where the pipeline finds each value
`item` is `raw.item`.
| Attribute | Location |
|---|---|
| post_id, url | `item.id`, `item.webVideoUrl` |
| posted_at | `item.createTime` (UTC seconds), `item.createTimeISO` |
| creator_handle, creator_verified, creator_followers | `item.authorMeta.name`, `.verified`, `.fans` (rounded by TikTok) |
| creator_is_brand | `item.authorMeta.name` equals the brand's `profile` |
| views, likes | `item.playCount` (as precise as TikTok shows it, F4), `item.diggCount` |
| comments, shares, saves | `item.commentCount`, `item.shareCount`, `item.collectCount` |
| caption, hashtags, mentions | `item.text`; `item.hashtags[].name` plus `#` words in `text` (the list can be empty when the text has some); `item.detailedMentions[].name` |
| sound, duration_s | `item.musicMeta.musicName`, `.musicOriginal`; `item.videoMeta.duration` |
| is_ad, is_sponsored, has_shop_product | `item.isAd`, `item.isSponsored` (meaning not established), `item.hasTikTokShopProduct` |
| surfaced_by, rank | `raw.path`, `raw.query`, `raw.position` |
| brand account snapshot | `authorMeta.fans`, `.heart`, `.video` of any `profile_popular` record |
