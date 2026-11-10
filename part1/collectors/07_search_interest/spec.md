# Spec: source 7, Google Trends search interest raw collector

- Shared contract: `part1/collectors/README.md`. Read it first; this document adds only what is specific to this source.
- Research notes: `part1/collectors/07_search_interest/source_info.md`. Where they differ from this spec (search terms, request plan, date window), this spec is newer.
- Every fact below was observed on the live site on 2026-11-10 from a US datacenter IP (VPN). If the site behaves differently, or a step needs something this spec does not give, stop and report. Do not guess.

## 1. What to build
One file, `source_collector.py`. Given a brand, it reads the brand's weekly Google Trends interest in the US over the last 12 months and writes one record per week. No paid service, no retries.

Trends values are relative: within one request the highest week of all requested terms is 100. So each brand gets two series:
- **Solo** (`interest_point`): the brand's term alone. 100 is the brand's own highest week.
- **Compared** (`interest_point_compared`): the five terms in one request. 100 is the highest week of any brand, so brands can be compared. This request is made once per process and every brand run writes its own series from it.

It does not convert dates, drop the unfinished week or compare values. It stores no other widget (related queries, subregions).

## 2. Facts about the source
| # | Fact | Sample or log in `part1/collectors/07_search_interest/samples/` |
|---|---|---|
| F1 | No login is needed. Headless Chrome got HTTP 429 on its first explore page. Headed Chrome (`channel="chrome"`) that opens `https://trends.google.com/trends/` first and then explore pages gets data | `source_info.md` section 2, `probe_log_20261110T1045Z.json` |
| F2 | `https://trends.google.com/trends/explore?date=2025-11-10%202026-11-10&geo=US&q=<terms>` shows the date filter `11/10/25 - 11/10/26`. Terms are percent-encoded and joined with a literal comma; five terms make one comparison | `trends_page_compare5_qualified.png` |
| F3 | Each explore page sends exactly one `GET /trends/api/widgetdata/multiline`, answered 1.4 to 2.9 s after the navigation starts. Its URL parameter `req` is JSON with `time` (`"2025-11-10 2026-11-10"`), `resolution` (`"WEEK"`) and `comparisonItem[i]` = `{"geo": {"country": "US"}, "complexKeywordsRestriction": {"keyword": [{"type": "BROAD", "value": "<term i>"}]}}` in address order. The address with `date=today%2012-m` sends the same `req` | `probe_log_20261110T1045Z.json`, line 1 of `multiline_batiste_term.txt` and `multiline_batiste_term_fixed.txt` |
| F4 | The body is a line `)]}',`, a newline, then `{"default": {"timelineData": [...], "averages": [...]}}`. Each point has `time` (UTC seconds of a Sunday 00:00, as a string; points 604800 s apart), `value` (integers 0 to 100) and `hasData` (booleans) with one entry per term, plus `formattedTime`, `formattedAxisTime`, `formattedValue`. Only the last point has `"isPartial": true`. The window above gives 53 points, `1762646400` (2025-11-09) to `1794096000` (2026-11-08) | all 15 `multiline_*.txt` |
| F5 | In the five-term request Black Rifle Coffee holds the 100 and its values equal its solo values. The same request repeated 3 minutes later was identical; repeated 5 h 40 min later, 7 of 53 values differed by 1 | `multiline_compare5_qualified_fixed.txt`, `multiline_black_rifle_coffee_fixed.txt`, `multiline_batiste_term*.txt` |
| F6 | All five terms of section 3 return data: no 0 and no `hasData` false. Four solo series (all but Black Rifle Coffee) have their 100 in the same week, 2026-04-12 | `multiline_*_fixed.txt` |
| F7 | Blocking: the 9th explore page in 5 minutes (6 to 15 s apart) returned 429 and moved to `https://www.google.com/sorry/index?...`, a reCAPTCHA page whose text says `unusual traffic`. A new browser 56 minutes later was still blocked; 5 h 33 min later the home page and 7 explore pages, 25 to 28 s apart, all returned data | `source_info.md` 2-1, `probe_log_20261110T1045Z.json`, `part1/collectors/06_google_results/samples/google_search_captcha_sorry_page.html` |
| F8 | Every explore page shows the banner `Classic Explore is expiring soon` | `trends_page_compare5_qualified.png` |

## 3. Input
`brand_inputs.json`:
```json
{
  "batiste": {"term": "Batiste dry shampoo"},
  "living-proof": {"term": "Living Proof shampoo"},
  "death-wish-coffee": {"term": "Death Wish Coffee"},
  "black-rifle-coffee": {"term": "Black Rifle Coffee"},
  "jinx": {"term": "Jinx dog food"}
}
```
Terms are sent exactly as written. "Batiste", "Jinx" and "Living Proof" alone also mean a surname, a game character and an English phrase, so each carries a category word. The comparison set is the five terms in `brands.json` order.

| Constant | Value |
|---|---|
| `NAV_TIMEOUT_S` | 45 |
| `TIMESERIES_TIMEOUT_S` | 20 |
| `NAV_SPACING_S` | 28 |

## 4. Procedure
Playwright, `chromium.launch(headless=False, channel="chrome")`, context `locale="en-US"`, `timezone_id="America/New_York"`. One browser and one page for the whole process. The collector only navigates and reads the `multiline` responses the page requests itself. Before every navigation, wait until `NAV_SPACING_S` has passed since the previous one started. Every navigation is made once.

**Blocked** means: after a navigation the page's host is not `trends.google.com`, or the document status is 400 or higher, or the page text contains `unusual traffic`. After a block the process makes no more navigations. Other errors do not stop the process.

**Window.** Once per process: `end` is today's date in `America/New_York`, `start` the same day one year earlier (29 February becomes 28 February), `window` = `"<start> <end>"`, for example `2025-11-10 2026-11-10`. The explore address is `https://trends.google.com/trends/explore?date=<quote(window)>&geo=US&q=<terms>`, each term `urllib.parse.quote(term, safe="")`, joined with `,`.

1. **Home.** First brand run only. Open `https://trends.google.com/trends/`. If the navigation raises or is blocked, the process makes no more navigations.
2. **Compared series.** First brand run only. Open the explore address of the comparison set and wait up to `TIMESERIES_TIMEOUT_S` for the first `/trends/api/widgetdata/multiline` response. The first check that applies gives the series its error: the navigation raised (`navigation: <message>`), the page is blocked (`blocked`), no response in time (`timeout`), the status is not 200 (`http_<status>`), `parse_multiline` raised (`shape_changed: <message>`). If none applies, the series is fetched. The outcome is kept for every brand run of the process.
3. **Solo series.** Every brand run. The same as step 2 with the brand's term alone.
4. **Write** one `interest_point` record per solo point, then one `interest_point_compared` record per compared point, each in `timelineData` order.

A series that was not attempted because the process had stopped gets the error that stopped it: `blocked`, or `home: <message>` when step 1 raised.

`--all` runs the brands in `brands.json` order, so a clean `--all` makes 7 navigations and `--brand <slug>` makes 3.

## 5. Output
| Field | `interest_point` | `interest_point_compared` |
|---|---|---|
| `key` | `<term>\|US\|<point.time>` | `<term>\|US\|<point.time>\|vs:<the five terms joined with ,>` |
| `url` | the solo explore address | the comparison explore address |
| `fetched_at` | when the multiline response arrived | the same, so it is earlier than `started_at` in every brand run after the first |
| `raw.point` | the `timelineData` item, unchanged | the same; it holds all five values |
| `raw.series_index` | 0 | the index of the brand's term in the comparison set |
| `raw.request` | the `req` object of the multiline request URL, unchanged (the `token` parameter is not kept) | the same |

`\|` is a plain `|`. Example keys: `Batiste dry shampoo|US|1762646400` and `Batiste dry shampoo|US|1762646400|vs:Batiste dry shampoo,Living Proof shampoo,Death Wish Coffee,Black Rifle Coffee,Jinx dog food`. A week keeps its key in every run because `point.time` is the start of the week.

Run result: `source` is `search_interest`, `expected_total` is `null`, `requests` counts the navigations made during this brand run (the first run of a process also makes the home and comparison navigations), and `extra` is `{"window": "2025-11-10 2026-11-10"}`.

| Condition, checked in this order | `status` | `reason` |
|---|---|---|
| Chrome did not start | `could_not_look` | `browser: <message>` |
| Neither series fetched | `could_not_look` | `solo: <error>; compared: <error>` |
| One series not fetched | `partial` | `solo: <error>` or `compared: <error>` |
| Both fetched | `ok` | empty |

## 6. Tests
Three pure functions, tested against the sample files. Each sample holds the request URL on line 1, the status on line 2 and the body from line 3. No network.

```python
def make_window(today: date) -> str: ...
def explore_url(terms: list[str], window: str) -> str: ...
def parse_multiline(url: str, body: str, terms: list[str], window: str) -> tuple[dict, list[dict]]: ...
    # returns (req, points); raises ValueError when the body does not start with ")]}'", the JSON is bad,
    # req.time != window, req.resolution != "WEEK", the terms differ, timelineData is empty,
    # a point lacks time/value/hasData, value or hasData has the wrong length, or two times are not 604800 apart
```

`W` is `2025-11-10 2026-11-10`; `SET` is the comparison set.

| Input | Expected |
|---|---|
| `make_window` for 2026-11-10, 2028-02-29, 2027-03-01 | `2025-11-10 2026-11-10`, `2027-02-28 2028-02-29`, `2026-03-01 2027-03-01` |
| `explore_url(["Batiste dry shampoo"], W)` | `https://trends.google.com/trends/explore?date=2025-11-10%202026-11-10&geo=US&q=Batiste%20dry%20shampoo` |
| `explore_url(SET, W)` | the same with `q=Batiste%20dry%20shampoo,Living%20Proof%20shampoo,Death%20Wish%20Coffee,Black%20Rifle%20Coffee,Jinx%20dog%20food` |
| `multiline_batiste_dry_shampoo_fixed.txt`, `["Batiste dry shampoo"]`, `W` | 53 points; point 0 `time` `1762646400`, `value` `[21]`; point 22 `value` `[100]`; point 52 `time` `1794096000`, `value` `[22]`, `isPartial` true; no other point has `isPartial` |
| `multiline_living_proof_shampoo_fixed.txt`, `multiline_death_wish_coffee_fixed.txt`, `multiline_jinx_dog_food_fixed.txt` | 53 points each; first and last value `[23]`/`[18]`, `[39]`/`[30]`, `[11]`/`[11]` |
| `multiline_compare5_qualified_fixed.txt`, `SET`, `W` | 53 points; point 0 `[9, 21, 11, 100, 7]`; point 52 `[10, 17, 9, 61, 7]`; index 3 of every point equals the values of `multiline_black_rifle_coffee_fixed.txt` |
| `multiline_batiste_term.txt` (a `today 12-m` page), `["Batiste"]`, `W` | 53 points; `req` equal to that of `multiline_batiste_term_fixed.txt` |
| `multiline_batiste_term_fixed.txt` with `["Batiste dry shampoo"]`; the Batiste dry shampoo file with window `2025-11-11 2026-11-11`; the same body without its first line; the same with point 30 `time` raised by 86400 | `ValueError` each |

## 7. Done when
1. The tests pass.
2. `--all` gives five `ok` run results with `requests` 3, 1, 1, 1, 1 and, in each, as many records of each kind as the window has weeks (53 for `2025-11-10 2026-11-10`).
3. For three `batiste` solo records and three `jinx` compared records, opening `url` and pointing at the week shows `raw.point.value[raw.series_index]`, or a number 1 away from it (F5).
4. A second run adds new files, leaves the first run's files unchanged, and with the same `extra.window` gives the same keys. If it is blocked instead, the run that hit the block says `blocked` and no later run of that process navigated.

## 8. Where the pipeline finds each value
| Attribute | Location |
|---|---|
| keyword | `raw.request.comparisonItem[raw.series_index].complexKeywordsRestriction.keyword[0].value` |
| solo or compared | `kind` |
| week_start | `raw.point.time` (UTC seconds, Sunday 00:00) |
| value (0 to 100) | `raw.point.value[raw.series_index]` |
| has_data | `raw.point.hasData[raw.series_index]` |
| is_partial | `raw.point.isPartial`, absent on finished weeks |
| geo, timeframe | `raw.request.comparisonItem[raw.series_index].geo.country`, `raw.request.time` |
| comparison_set | `raw.request.comparisonItem[].complexKeywordsRestriction.keyword[0].value` |
| source_url, collected_at | `url`, `fetched_at` |
