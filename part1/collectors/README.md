# Raw collectors: shared contract

Each source has one raw collector. A collector **fetches the source's raw data and writes it to disk, and stops there**. Loading into the single table is done later by the main pipeline, which reads these files.

- Everything for one source lives in `part1/collectors/<nn_name>/`: the collector, its `spec.md`, the research notes (`source_info.md`) and the captured samples that the tests read (`samples/`).
- Source-specific requirements are in each folder's `spec.md`. Where this document and a `spec.md` disagree, the `spec.md` wins.

## 0. Three rules that come first
1. **Do not guess.** A `spec.md` states every value, timeout and choice the collector needs. If something is missing, or the site behaves in a way the spec does not describe, stop and report. Do not add a fallback, a default or an alternative method that the spec does not contain.
2. **Failures are recorded as failures.** Whatever goes wrong must be visible in the files the pipeline reads: in the run result, and in the record when it concerns one item. A run is never reported as `ok` while anything in scope is missing.
3. **Keep it small.** A collector fetches the data and writes it down. Nothing else.
   - **No retries.** Every request is attempted once. A failed request is recorded and the collector moves on. Running again is the pipeline's decision, not the collector's.
   - **One file.** `source_collector.py` plus `brand_inputs.json`. No shared library, no base class, no plugin or config layer, no logging framework. The standard library plus the one package the source needs (Playwright for browser sources; Apify is called over its REST API with the standard library).
   - **Only data the pipeline will use.** Each record carries the source's response for that item. No extra lookups, no debug dumps, no page snapshots, unless the spec names them.
   - **No code for cases the spec does not list.** No speculative options, flags or branches.
   - **Few tests.** Only for the code that parses real samples.
   - A spec should fit in about 150 lines and a collector in about 200. Needing much more is a sign that it is doing too much; say so instead of writing it.

## 1. Layout
```
part1/collectors/
  README.md                       this document
  brands.json                     the five brands: name and slug
  01_google_ads_transparency/
    spec.md                       requirements for this source
    source_collector.py           the collector
    brand_inputs.json             how this source finds each brand (domain, page ID, search term, ...)
    requirements.txt              dependencies used only by this collector
    source_info.md                research notes for this source
    samples/                      real responses captured from the source; read by the tests
    tests/                        parser tests; no network
    raw/<brand>/<run_id>.jsonl    records from one run
    raw/<brand>/<run_id>.run.json result of one run
    raw/<brand>/<run_id>.<name>/  side files of one run (only when the spec asks for them)
    media/<brand>/                downloaded media (only when the spec asks for it)
```
- `<brand>` is the slug: `batiste`, `living-proof`, `death-wish-coffee`, `black-rifle-coffee`, `jinx`.
- `<run_id>` is the UTC time the run started, for example `20261110T083000Z`.

## 2. How to run
Setup, once, from the repository root:
```
python3 -m venv .venv
.venv/bin/pip install -r part1/requirements.txt
```
- Sources 1, 3, 5, 7 and 10 drive a browser. They start the Google Chrome installed on the machine (`channel="chrome"`), so Chrome must be installed and `playwright install` is not needed. Source 7 opens a visible window.
- The other collectors use only the standard library.
- Collectors that call Apify (sources 2, 3, 4, 6, 8, 9, and parts of 5 and 10) read `APIFY_TOKEN` from `.env` at the repository root; copy `.env.example`. Without a token they record `could_not_look` with reason `missing_token`.
- `part1/requirements.txt` pins one Playwright version for every collector and also installs what the loader needs. Each collector folder's own `requirements.txt` names the same version.

Then, with that environment's Python:
```
.venv/bin/python part1/collectors/<nn_name>/source_collector.py --brand death-wish-coffee
.venv/bin/python part1/collectors/<nn_name>/source_collector.py --all
```
- `--all` runs the five brands one after another. A failure in one brand does not stop the others.

| Exit code | Meaning |
|---|---|
| 0 | Every requested brand finished and wrote its run result. This includes `partial` and `could_not_look` |
| 1 | At least one brand hit an unexpected exception. Its run result was still written |
| 2 | Invalid arguments. Nothing was run |

## 3. Record file (`.jsonl`)
One record per line, written as soon as the record is complete.

```json
{"key": "...", "kind": "ad", "url": "https://...", "fetched_at": "2026-11-10T08:30:12Z", "raw": {}}
```

| Field | Meaning |
|---|---|
| `key` | A stable identifier for the item within this source. The same item must get the same key in every run |
| `kind` | The type of item, for example `ad`, `product`, `review`, `search_result`, `interest_point`, `post`, `listing`, `offer`, `email` |
| `url` | The address a person can open on the live site to check this item |
| `fetched_at` | UTC time the item was fetched |
| `raw` | What the source returned. Not interpreted and not renamed. A spec may add fields that describe how the fetch went (for example a per-item state and error) |

- The only thing removed from `raw` is personal data (names of private individuals, profile URLs, the inbox address). What is removed is stated in the `spec.md`.
- While a run is in progress the file is named `<run_id>.jsonl.part`. It is renamed to `.jsonl` just before the run result is written.

## 4. Run result file (`.run.json`)
One per run, written last. The pipeline reads only runs that have this file.

```json
{
  "source": "google_ads_transparency",
  "brand": "death-wish-coffee",
  "run_id": "20261110T083000Z",
  "started_at": "2026-11-10T08:30:00Z",
  "finished_at": "2026-11-10T08:33:10Z",
  "status": "ok",
  "reason": "",
  "records": 30,
  "records_by_kind": {"ad": 30},
  "expected_total": 30,
  "requests": 31,
  "cost_usd": 0,
  "extra": {}
}
```

| `status` | When it is used |
|---|---|
| `ok` | Everything in scope was collected. A search that genuinely returned nothing is also `ok`, with `records` 0 |
| `partial` | Only part was collected. What was collected is in the record file. `reason` says what is missing |
| `could_not_look` | The source could not be reached (blocked, CAPTCHA, login wall, missing token, response shape changed). `reason` is required |

- The `spec.md` defines exactly which condition gives which status and what `reason` contains.
- `expected_total` is filled only when the source reports an exact total. Otherwise it is `null`.
- `cost_usd` is the amount charged by Apify. It is 0 when no paid service is used.
- `extra` holds source-specific counters defined in the `spec.md`.

**A run result is always written.** The collector wraps each brand's run so that an unexpected exception still renames the record file and writes a run result: `partial` if at least one record was written, otherwise `could_not_look`, with `reason` set to `exception: <type>: <message>`.

If the process is killed, a `.jsonl.part` file is left with no run result. The pipeline treats that run as failed and ignores its records.

## 5. What a collector does not do
- It does not write to the database.
- It does not change or delete files from earlier runs. Every run writes new files.
- It does not decide whether an item is "active" or "ended". The pipeline decides that by comparing runs.
- It does not interpret or compute values (text recognition, date conversion, classification).

## 6. Rules every collector follows
- **Stop when blocked.** If a CAPTCHA, puzzle, login wall or block page appears, stop there and record it. Do not work around it.
- **Request spacing.** Leave the interval set in the `spec.md` between requests to the same site. Do not send requests in parallel.
- **Secrets.** Tokens are read from `.env` at the repository root. They are never written to logs or files. If a token is missing, record `could_not_look` with `reason` `missing_token`.
- **Personal data.** Names and profiles of private individuals are not stored.
- **Tests.** Code that parses responses is tested against the real responses in `part1/collectors/<nn_name>/samples/`. Tests do not use the network.
