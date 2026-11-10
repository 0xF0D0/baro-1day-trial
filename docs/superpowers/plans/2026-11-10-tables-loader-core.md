# Market Radar Tables and Loader Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the eight Postgres tables and a loader that applies collector runs to them (insert, update, end, reopen), with the mapper for source 5 (retail shelf).

**Architecture:** The loader reads each run's two files, asks that source's mapper for rows and scopes, and applies them in one transaction per run. Mappers are pure functions with no SQL; every SQL statement lives in the loader. Ending rules run after the rows are written, per scope.

**Tech Stack:** Python 3 (standard library plus `psycopg` 3), PostgreSQL 16, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-10-market-radar-tables-design.md`. Read it first; this plan does not repeat its rules. The collector contract is `part1/collectors/README.md`; source 5 is `part1/collectors/05_retail_shelf/spec.md`.

## Global Constraints
- Own code. No paid service is used by the loader.
- Re-run safe. Loading twice creates no duplicates. A disappeared item is marked ended, never deleted.
- Honest gaps. "Could not look" is recorded as that, never as "nothing found". Partial collection is marked.
- Clean collection. No names or profiles of private individuals are stored or added.
- The target is a local Postgres; the loader is one command another person can run on their machine.
- Every row keeps the URL and fetch time needed to compare it with the live site.
- Request count, duration and cost per run stay available (from the run result).
- Python standard library plus `psycopg` 3 only. No ORM, no migration tool, no other package.
- No retries. A failure is reported and recorded.
- Tests use `unittest` against a real Postgres. The database is not mocked.
- Code, comments and documents are in English.
- One commit per task, on this plan's branch. Nothing under `part1/collectors/` is changed.

## Review Focus
1. Two records with the same row key in one run: the later one wins, with no SQL error (Task 2).
2. A run whose `.jsonl` is missing, or has a line that is not JSON: that run fails with the file and line named, and the other runs still load (Task 2).
3. A price shown as a range or with a thousands separator, `$18.00 - $46.00`, `$1,299.00` (Task 4).
4. A record kind or retailer the mapper does not know: an error, not a silent skip (Task 4).
5. The database cannot be reached: one line naming the address, exit code 1, no traceback (Task 5).

---

## File structure
```
part1/pipeline/
  schema.sql               the eight tables
  requirements.txt         psycopg[binary]
  README.md                how to set up and run (Task 5)
  db.py                    connection and schema bootstrap
  model.py                 Row, Scope, MappedRun, MapError, column lists
  load.py                  discover, load_run, load_all, main
  mappers/__init__.py      MAPPERS registry
  mappers/retail_shelf.py  source 5
  tests/support.py         test database, run-file writer, fake mapper
  tests/test_schema.py  test_load.py  test_ending.py  test_retail_shelf.py  test_cli.py
```
Run every test with `.venv/bin/python -m unittest discover -s part1/pipeline/tests -v` from the repository root. `tests/support.py` puts `part1/pipeline` on `sys.path`; every test module imports `support` first.

---

### Task 1: Database bootstrap and schema

**Files:**
- Create: `part1/pipeline/schema.sql`, `part1/pipeline/requirements.txt`, `part1/pipeline/db.py`, `part1/pipeline/model.py`, `part1/pipeline/tests/support.py`, `part1/pipeline/tests/test_schema.py`
- Modify: `.env.example` (append `DATABASE_URL=postgresql://localhost:5432/market_radar`)

**Interfaces:**
- Produces, in `db.py`:
  - `DEFAULT_URL = "postgresql://localhost:5432/market_radar"`
  - `database_url() -> str`: `DATABASE_URL` from the environment, else from the repository's `.env`, else `DEFAULT_URL`. The repository root is `Path(__file__).resolve().parents[2]`.
  - `connect(url: str) -> psycopg.Connection`: autocommit off.
  - `ensure_schema(conn) -> None`: executes `schema.sql` and commits; safe to run again.
- Produces, in `model.py`:
```python
COMMON_COLUMNS = ("source", "brand", "kind", "key", "scope", "url", "fetched_at",
                  "first_seen_at", "last_seen_at", "ended_at", "last_run_id", "raw")
TABLE_COLUMNS = {
    "ads": ("channel", "advertiser_id", "advertiser_name", "format", "headline", "body", "cta",
            "landing_url", "landing_domain", "started_at", "last_shown_at", "variation_count",
            "placements", "offer_code"),
    "products": ("retailer", "product_id", "title", "price", "price_max", "list_price", "currency",
                 "rating", "review_count", "rank", "sponsored", "availability", "seller_name", "sold_count"),
    "reviews": ("product_key", "rating", "title", "body", "review_date", "verified", "helpful_votes"),
    "search_rankings": ("keyword", "keyword_rank", "position", "result_url", "domain", "title",
                        "description", "result_type"),
    "search_interest": ("keyword", "series", "week_start", "value", "has_data", "is_partial", "geo"),
    "posts": ("post_id", "posted_at", "creator_handle", "creator_is_brand", "creator_followers",
              "views", "likes", "comments", "shares", "saves", "caption", "hashtags", "surfaced_by"),
}

@dataclass(frozen=True)
class Row:
    table: str                 # a key of TABLE_COLUMNS
    kind: str
    key: str
    scope: str
    url: str | None
    fetched_at: str            # ISO 8601 UTC, the record's fetched_at
    raw: dict
    columns: dict[str, object] # own columns; a name left out keeps the stored value

@dataclass(frozen=True)
class Scope:
    name: str
    status: str                # ok | partial | could_not_look
    reason: str

@dataclass(frozen=True)
class MappedRun:
    rows: list[Row]
    scopes: list[Scope]
    not_fetched: int = 0       # records that said their item was not fetched

class MapError(Exception):     # message starts with the record key
    pass
```
- Produces, in `tests/support.py`:
  - `TEST_URL`: `TEST_DATABASE_URL` from the environment, else `postgresql://localhost:5432/market_radar_test`.
  - `ts(run_id: str) -> datetime`: `"20261110T100000Z"` gives `2026-11-10 10:00:00+00:00`.
  - `class DbTestCase(unittest.TestCase)`: `setUp` creates a schema named `t_` plus 8 random hex digits in the test database, builds `self.url` (the test URL with `options=-csearch_path=<schema>`), opens `self.conn` with it, runs `ensure_schema`, and makes `self.dir`, an empty temporary collectors directory. `tearDown` drops the schema and closes. A failed connection fails the test with the message `Postgres not reachable at <url>`; it is not skipped.
  - `DbTestCase.write_run(source, brand, run_id, status="ok", records=(), reason="", extra=None) -> Path`: writes `<self.dir>/<source>/raw/<brand>/<run_id>.jsonl` and `.run.json` (`started_at` and `finished_at` are the run id as ISO time, `records` the count, `expected_total` null, `requests` 0, `cost_usd` 0, `extra` or `{}`) and returns the `.run.json` path.
  - `DbTestCase.table(name: str) -> list[dict]`: all rows of a table as dicts, ordered by its primary key.
  - `rec(key, kind="product", table="products", scope="all", **raw) -> dict`: a collector record `{"key", "kind", "url": "https://example.test/" + key, "fetched_at": "2026-11-10T00:00:00Z", "raw": {"table": table, "scope": scope, **raw}}`.
  - `FAKE`: a mapper object (same three attributes as a mapper module, Task 2) with `SOURCE = "fake"`, `ENDING = {("products", "product"): "absent", ("reviews", "review"): "never", ("ads", "ad"): "source_date"}` and `map_run` that, per record: counts it as not fetched and gives no row when `raw.get("state") == "not_fetched"`; raises `MapError(key)` when `raw.get("bad")`; otherwise gives `Row(table=raw["table"], kind, key, scope=raw["scope"], url, fetched_at, raw, columns=raw.get("columns", DEFAULT_COLUMNS[table]))`. Its scopes are `run["extra"]["scopes"]` (a list of `[name, status, reason]`) when present, else one `Scope("all", run["status"], run["reason"])`.
  - `DEFAULT_COLUMNS = {"products": {"retailer": "shop"}, "reviews": {"product_key": "p"}, "ads": {"channel": "google"}}`

- [ ] **Step 1: Prepare the environment.** Run `pg_isready -h localhost -p 5432`. If it does not report "accepting connections", start the installed server with `/opt/homebrew/opt/postgresql@16/bin/pg_ctl -D /opt/homebrew/var/postgresql@16 -l /opt/homebrew/var/log/postgresql@16.log start` (this does not register a login service). Then `createdb market_radar` and `createdb market_radar_test`; "already exists" is fine. Then `python3 -m venv .venv && .venv/bin/pip install -r part1/pipeline/requirements.txt` after creating `requirements.txt` with the single line `psycopg[binary]`. If the server does not start or the package does not install for this Python, stop and report; do not switch driver or database.

- [ ] **Step 2: Write the failing tests** in `tests/test_schema.py`:
```python
class SchemaTest(support.DbTestCase):
    def test_tables_and_columns(self):
        for table, own in model.TABLE_COLUMNS.items():
            self.assertEqual(self.columns(table), list(model.COMMON_COLUMNS + own))
        self.assertEqual(self.columns("runs"), ["source", "brand", "run_id", "started_at", "finished_at",
            "status", "reason", "records", "expected_total", "requests", "cost_usd", "extra", "result", "loaded_at"])
        self.assertEqual(self.columns("run_scopes"), ["source", "brand", "run_id", "scope", "status", "reason"])

    def test_primary_keys(self):
        self.assertEqual(self.primary_key("products"), ["source", "brand", "kind", "key"])
        self.assertEqual(self.primary_key("runs"), ["source", "brand", "run_id"])
        self.assertEqual(self.primary_key("run_scopes"), ["source", "brand", "run_id", "scope"])

    def test_ensure_schema_twice(self):
        db.ensure_schema(self.conn)   # the second time; setUp ran the first
```
`columns(table)` and `primary_key(table)` are helpers on the test class that read `information_schema` for the test's schema, in ordinal order.

- [ ] **Step 3: Run them.** Expected: FAIL (no `db` module).

- [ ] **Step 4: Write `model.py` as given above, `db.py` with the three functions, and `schema.sql`.** `schema.sql` is eight `CREATE TABLE IF NOT EXISTS` statements. Item tables: the common columns of design section 6.1 in that order with those types and constraints, then the own columns in `TABLE_COLUMNS` order with the types and `NOT NULL` marks of design section 6.2, then the primary key. `runs` and `run_scopes` exactly as design section 6.3. No schema name in the statements.

- [ ] **Step 5: Run the tests.** Expected: 3 tests, OK.

- [ ] **Step 6: Commit** the files of this task: `Add pipeline schema and database bootstrap`.

---

### Task 2: Recording runs and writing rows

**Files:**
- Create: `part1/pipeline/load.py`, `part1/pipeline/tests/test_load.py`

**Interfaces:**
- Consumes: `db`, `model`, `support` from Task 1.
- A mapper is any object with `SOURCE: str`, `ENDING: dict[tuple[str, str], str]` (`(table, kind)` to `absent`, `source_date` or `never`) and `map_run(run: dict, records: list[dict]) -> MappedRun`. `mappers` arguments below are `dict[str, mapper]` keyed by `SOURCE`.
- Produces, in `load.py`:
```python
@dataclass
class Outcome:
    source: str
    brand: str
    run_id: str
    status: str            # the run result's status
    result: str            # applied | superseded | empty_no_mapper | no_mapper | failed | already_loaded
    inserted: int = 0      # new rows
    updated: int = 0       # existing rows rewritten
    ended: int = 0         # rows whose ended_at went from NULL (or no row) to a value in this run
    not_fetched: int = 0
    error: str = ""

def discover(collectors_dir: Path) -> list[Path]   # every *.run.json under <collectors_dir>/*/raw/*/, sorted by (source, brand, run_id) read from the files
def load_run(conn, run_path: Path, mappers: dict) -> Outcome   # one transaction; commits or rolls back itself; never raises for a bad run
def load_all(conn, collectors_dir: Path, mappers: dict) -> list[Outcome]   # load_run for each discovered path, in order
```
- `load_run` follows design section 7.1 and 7.2 in this order:
  1. Read the run result. If `(source, brand, run_id)` is in `runs`: `already_loaded`.
  2. Read the `.jsonl` beside it, skipping blank lines. Missing file: `failed`, error `records file missing`. A line that is not JSON: `failed`, error `<file name>:<line number>: not JSON`.
  3. No mapper for the source: with zero records, write `runs` (`result` `empty_no_mapper`) and one `run_scopes` row (`all`, the run's status and reason), result `empty_no_mapper`; with records, write nothing, result `no_mapper`.
  4. A run with `result = 'applied'` and a greater `run_id` exists for this source and brand: write `runs` only, `superseded`.
  5. Call `map_run`. `MapError`: `failed`, error is its message. A row whose table is not in `TABLE_COLUMNS`, whose `columns` has a name not in that table's list, or whose `(table, kind)` is not in the mapper's `ENDING`: `failed`.
  6. Write `runs` (`applied`), `run_scopes` from the mapped scopes, then the rows in order per section 7.2. `first_seen_at` and `last_seen_at` are the run's `started_at`. For a `source_date` kind, `ended_at` is the row's `last_shown_at` when that is more than `SOURCE_DATE_DAYS = 3` days before `started_at`, else NULL; for the other policies NULL. `last_shown_at` may arrive as a `datetime` or as an ISO 8601 string. Column values are passed to Postgres as the mapper gave them (strings for numbers and times are valid); `raw` is stored as `jsonb`. No statement names a schema.
  7. Any exception from step 5 or 6: roll back, `failed`, error is the exception text.
- Task 3 adds the `absent` rule to step 6; this task leaves a marked place for it.

- [ ] **Step 1: Write the failing tests** in `tests/test_load.py` (`T1 = "20261110T100000Z"`, `T2 = "20261110T110000Z"`, `M = {"fake": support.FAKE}`, `load = lambda self: load_all(self.conn, self.dir, M)`):
```python
def test_first_run_inserts(self):
    self.write_run("fake", "b", T1, records=[rec("a"), rec("b")])
    out = self.load()
    self.assertEqual([(o.result, o.inserted, o.updated, o.ended) for o in out], [("applied", 2, 0, 0)])
    rows = self.table("products")
    self.assertEqual([r["key"] for r in rows], ["a", "b"])
    for r in rows:
        self.assertEqual((r["first_seen_at"], r["last_seen_at"], r["ended_at"]), (ts(T1), ts(T1), None))
        self.assertEqual((r["source"], r["brand"], r["kind"], r["scope"], r["last_run_id"]), ("fake", "b", "product", "all", T1))
        self.assertEqual(r["url"], "https://example.test/" + r["key"])
        self.assertEqual(r["raw"], {"table": "products", "scope": "all"})
    self.assertEqual([(r["result"], r["status"], r["records"]) for r in self.table("runs")], [("applied", "ok", 2)])
    self.assertEqual([(r["scope"], r["status"], r["reason"]) for r in self.table("run_scopes")], [("all", "ok", "")])

def test_same_run_twice_changes_nothing(self):
    self.write_run("fake", "b", T1, records=[rec("a")])
    self.load(); before = (self.table("products"), self.table("runs"), self.table("run_scopes"))
    self.assertEqual([o.result for o in self.load()], ["already_loaded"])
    self.assertEqual((self.table("products"), self.table("runs"), self.table("run_scopes")), before)

def test_could_not_look_run_is_recorded(self):
    self.write_run("fake", "b", T1, status="could_not_look", reason="blocked")
    self.assertEqual([o.result for o in self.load()], ["applied"])
    self.assertEqual(self.table("products"), [])
    self.assertEqual([(r["scope"], r["status"], r["reason"]) for r in self.table("run_scopes")], [("all", "could_not_look", "blocked")])

def test_older_run_after_newer_is_superseded(self):
    self.write_run("fake", "b", T2, records=[rec("a")]); self.load()
    self.write_run("fake", "b", T1, records=[rec("a"), rec("b")])
    self.assertEqual([o.result for o in self.load()], ["superseded", "already_loaded"])
    self.assertEqual([r["key"] for r in self.table("products")], ["a"])
    self.assertEqual([(r["run_id"], r["result"]) for r in self.table("runs")], [(T1, "superseded"), (T2, "applied")])
    self.assertEqual([r["run_id"] for r in self.table("run_scopes")], [T2])

def test_rejected_record_fails_only_its_run(self):
    self.write_run("fake", "b1", T1, records=[rec("x", bad=True), rec("y")])
    self.write_run("fake", "b2", T1, records=[rec("z")])
    out = self.load()
    self.assertEqual([o.result for o in out], ["failed", "applied"])
    self.assertIn("x", out[0].error)
    self.assertEqual([(r["brand"], r["key"]) for r in self.table("products")], [("b2", "z")])
    self.assertEqual([r["brand"] for r in self.table("runs")], ["b2"])

def test_not_fetched_record_gives_no_row(self):
    self.write_run("fake", "b", T1, records=[rec("a"), rec("b", state="not_fetched")])
    out = self.load()
    self.assertEqual((out[0].result, out[0].inserted, out[0].not_fetched), ("applied", 1, 1))
    self.assertEqual([r["key"] for r in self.table("products")], ["a"])

def test_left_out_column_keeps_value(self):
    self.write_run("fake", "b", T1, records=[rec("a", columns={"retailer": "shop", "title": "T", "price": "9.99"})]); self.load()
    self.write_run("fake", "b", T2, records=[rec("a", columns={"retailer": "shop", "title": None})]); self.load()
    row = self.table("products")[0]
    self.assertEqual((row["title"], row["price"], row["last_run_id"]), (None, Decimal("9.99"), T2))

def test_empty_run_without_mapper_is_recorded(self):
    self.write_run("nomap", "b", T1, status="could_not_look", reason="blocked")
    self.write_run("nomap", "b", T2, records=[rec("a")])
    self.assertEqual([o.result for o in self.load()], ["empty_no_mapper", "no_mapper"])
    self.assertEqual([(r["run_id"], r["result"]) for r in self.table("runs")], [(T1, "empty_no_mapper")])
    self.assertEqual([(r["scope"], r["status"]) for r in self.table("run_scopes")], [("all", "could_not_look")])

def test_same_key_twice_later_wins(self):
    cols = lambda t: {"retailer": "shop", "title": t}
    self.write_run("fake", "b", T1, records=[rec("a", columns=cols("first")), rec("a", columns=cols("second"))])
    out = self.load()
    self.assertEqual((out[0].result, out[0].inserted), ("applied", 1))
    self.assertEqual([r["title"] for r in self.table("products")], ["second"])

def test_broken_records_file_fails_run(self):
    p = self.write_run("fake", "b1", T1, records=[rec("a")])
    with open(p.with_name(T1 + ".jsonl"), "a") as f: f.write("not json\n")
    q = self.write_run("fake", "b2", T1, records=[rec("a")]); q.with_name(T1 + ".jsonl").unlink()
    out = self.load()
    self.assertEqual([o.result for o in out], ["failed", "failed"])
    self.assertIn(T1 + ".jsonl:2: not JSON", out[0].error)
    self.assertIn("records file missing", out[1].error)
    self.assertEqual(self.table("runs"), [])

def test_unknown_column_fails_run(self):
    self.write_run("fake", "b", T1, records=[rec("a", columns={"retailer": "shop", "nope": 1})])
    self.assertEqual([o.result for o in self.load()], ["failed"])
```

- [ ] **Step 2: Run them.** Expected: FAIL (no `load` module).
- [ ] **Step 3: Write `load.py`** with `Outcome`, `discover`, `load_run`, `load_all` as specified. A leftover `<run_id>.jsonl.part` has no `.run.json`, so `discover` never returns it.
- [ ] **Step 4: Run all tests.** Expected: Task 1's 3 and these 11, OK.
- [ ] **Step 5: Commit**: `Add loader: record runs and write rows`.

---

### Task 3: Ending and reopening

**Files:**
- Modify: `part1/pipeline/load.py` (step 6 of `load_run`)
- Create: `part1/pipeline/tests/test_ending.py`

**Interfaces:**
- Consumes: Task 2's `load_run`.
- Produces: the `absent` rule of design section 7.4. After the rows of a run are written, for every mapped scope whose status is `ok`, and every `(table, kind)` whose policy in the mapper's `ENDING` is `absent`: rows with that source, brand, kind and scope, with `last_run_id` other than this run and `ended_at` NULL, get `ended_at =` the run's `started_at`. These rows count in `Outcome.ended`.

- [ ] **Step 1: Write the failing tests** in `tests/test_ending.py` (`T1`, `T2`, `M`, `load` as in Task 2; `T3 = "20261110T120000Z"`; `by_key = lambda rows: {r["key"]: r for r in rows}`):
```python
def test_ok_run_ends_missing_and_inserts_new(self):
    self.write_run("fake", "b", T1, records=[rec("a"), rec("b"), rec("c")]); self.load()
    self.write_run("fake", "b", T2, records=[rec("a"), rec("c"), rec("d")])
    out = [o for o in self.load() if o.run_id == T2][0]
    self.assertEqual((out.inserted, out.updated, out.ended), (1, 2, 1))
    p = by_key(self.table("products"))
    self.assertEqual((p["b"]["ended_at"], p["b"]["last_seen_at"]), (ts(T2), ts(T1)))
    self.assertEqual((p["a"]["first_seen_at"], p["a"]["last_seen_at"], p["a"]["ended_at"]), (ts(T1), ts(T2), None))
    self.assertEqual((p["d"]["first_seen_at"], p["d"]["ended_at"]), (ts(T2), None))

def test_partial_run_ends_nothing(self):
    self.write_run("fake", "b", T1, records=[rec("a"), rec("b"), rec("c")]); self.load()
    self.write_run("fake", "b", T2, status="partial", reason="x", records=[rec("a")]); self.load()
    self.assertEqual([r["ended_at"] for r in self.table("products")], [None, None, None])

def test_item_returns(self):
    self.write_run("fake", "b", T1, records=[rec("a"), rec("b")]); self.load()
    self.write_run("fake", "b", T2, records=[rec("a")]); self.load()
    self.assertEqual(by_key(self.table("products"))["b"]["ended_at"], ts(T2))
    self.write_run("fake", "b", T3, records=[rec("a"), rec("b")]); self.load()
    b = by_key(self.table("products"))["b"]
    self.assertEqual((b["first_seen_at"], b["last_seen_at"], b["ended_at"]), (ts(T1), ts(T3), None))

def test_never_kind_is_not_ended(self):
    self.write_run("fake", "b", T1, records=[rec("p"), rec("r1", kind="review", table="reviews")]); self.load()
    self.write_run("fake", "b", T2, records=[rec("p")]); self.load()
    self.assertEqual(self.table("reviews")[0]["ended_at"], None)

def test_only_ok_scope_ends(self):
    scopes = lambda s2: {"scopes": [["s1", "ok", ""], ["s2", s2, "" if s2 == "ok" else "blocked"]]}
    self.write_run("fake", "b", T1, records=[rec("a", scope="s1"), rec("b", scope="s2")], extra=scopes("ok")); self.load()
    self.write_run("fake", "b", T2, status="partial", reason="s2: blocked", extra=scopes("could_not_look")); self.load()
    p = by_key(self.table("products"))
    self.assertEqual((p["a"]["ended_at"], p["b"]["ended_at"]), (ts(T2), None))

def test_source_date(self):
    ad = lambda key, shown: rec(key, kind="ad", table="ads", columns={"channel": "google", "last_shown_at": shown})
    self.write_run("fake", "b", T1, status="partial", reason="x",
                   records=[ad("old", "2026-11-06T00:00:00Z"), ad("new", "2026-11-09T00:00:00Z")]); self.load()
    a = by_key(self.table("ads"))
    self.assertEqual((a["old"]["ended_at"], a["new"]["ended_at"]), (datetime(2026, 11, 6, tzinfo=timezone.utc), None))
    self.write_run("fake", "b", T2, records=[ad("old", "2026-11-10T00:00:00Z")]); self.load()
    a = by_key(self.table("ads"))
    self.assertEqual((a["old"]["ended_at"], a["new"]["ended_at"]), (None, None))   # reopened; absence does not end a source_date kind

def test_not_fetched_keeps_stored_row(self):
    self.write_run("fake", "b", T1, records=[rec("a", scope="s1")], extra={"scopes": [["s1", "ok", ""]]}); self.load()
    self.write_run("fake", "b", T2, status="partial", reason="x",
                   records=[rec("a", scope="s1", state="not_fetched")], extra={"scopes": [["s1", "partial", "x"]]}); self.load()
    a = self.table("products")[0]
    self.assertEqual((a["last_seen_at"], a["ended_at"], a["last_run_id"]), (ts(T1), None, T1))
```

- [ ] **Step 2: Run them.** Expected: the first, third and fifth FAIL (nothing is ended yet); the others pass.
- [ ] **Step 3: Add the `absent` rule** to `load_run`.
- [ ] **Step 4: Run all tests.** Expected: 21 tests, OK.
- [ ] **Step 5: Commit**: `Add ending and reopening rules to the loader`.

---

### Task 4: Source 5 mapper

**Files:**
- Create: `part1/pipeline/mappers/__init__.py`, `part1/pipeline/mappers/retail_shelf.py`, `part1/pipeline/tests/test_retail_shelf.py`

**Interfaces:**
- Consumes: `model` from Task 1.
- Produces, in `mappers/retail_shelf.py`:
  - `SOURCE = "retail_shelf"`
  - `ENDING = {("products", "product"): "absent", ("reviews", "review"): "never"}`
  - `map_run(run: dict, records: list[dict]) -> MappedRun`
  - `parse_price(text: str) -> tuple[Decimal, Decimal | None]`: `"$12.99"` gives `(12.99, None)`, `"$18.00 - $46.00"` gives `(18.00, 46.00)`, `"$1,299.00"` gives `(1299.00, None)`; anything else raises `ValueError`.
- Produces, in `mappers/__init__.py`: `MAPPERS = {retail_shelf.SOURCE: retail_shelf}`.
- Scopes: one per entry of `run["extra"]["cells"]`: `Scope(cell["retailer"], cell["status"], cell["reason"])`. Every row's `scope` is its `raw.retailer`.
- Every product row returns all fourteen `products` columns; every review row all seven `reviews` columns. Nothing is left out (source 5 has no column that depends on a second fetch). `product_id` is the record key after the first `:`. `currency` is `"USD"`. `seller_name` and `sold_count` are `None`. Prices and the product `rating` are `Decimal` values with 2 decimal places (a float from the source is converted through its `str`); `None` stays `None`. With `li = raw.listing_item` and `r = raw.review`:

| Column | ulta | target | sephora | chewy |
|---|---|---|---|---|
| `title` | `li.productName` | `li.title` | `li.displayName` | `li.name` |
| `price`, `price_max` | `parse_price(li.salePrice or li.listPrice)` | `li.price`, `None` | `parse_price(li.listPrice)` | `parse_price(li.displayPrice)` |
| `list_price` | lower end of `li.listPrice` when `li.salePrice` is not null, else `None` | `li.regularPrice` when it differs from `li.price`, else `None` | `None` | lower end of `li.strikePrice` when not null, else `None` |
| `rating`, `review_count` | `li.rating`, `li.reviewCount` | `li.rating`, `li.reviewCount` | `li.rating`, `li.reviews` | `li.rating`, `li.ratingCount` |
| `rank` | `raw.rank` | `raw.rank` | `raw.rank` | `raw.rank` |
| `sponsored` | `li.sponsored` | `li.isSponsored` | `li.sponsored` | `None` |
| `availability` | `None` | `li.availability` | `None` | `"IN_STOCK"` when `li.inStock` is true, `"OUT_OF_STOCK"` when false, `None` when absent |
| review `rating` | `r.metrics.rating` | `r.reviewRating.ratingValue` | as target | `r.rating` |
| review `title`, `body` | `r.details.headline`, `r.details.comments` | `r.name`, `r.reviewBody` | as target | `r.title`, `r.reviewText` |
| review `review_date` | UTC date of `r.details.created_date` (milliseconds since 1970) | date part of `r.datePublished` | as target | date part of `r.reviewDate` |
| review `verified`, `helpful_votes` | `r.badges.is_verified_buyer`, `r.metrics.helpful_votes` | `None`, `None` | `None`, `None` | `None`, `r.helpfulVotes` |

  - Review `product_key` is `raw.product_key`.
  - A null price field gives `None` for `price` and `price_max`. A price string `parse_price` rejects, a `raw.retailer` outside these four, or a record kind other than `product` and `review`, raises `MapError` starting with the record key.
  - Not yet seen on the live sites, so stated here as the rule and tested only with made-up values: Ulta's `salePrice` being set, and Sephora's `onSaleData` being other than `"NONE"` (it is ignored).

- [ ] **Step 1: Write the failing tests** in `tests/test_retail_shelf.py`. `SAMPLES` is `part1/collectors/05_retail_shelf/samples` of this repository; `items(name)` returns the `items` list of a sample file. `product(retailer, li, rank=1, key=...)` and `review(retailer, product_key, r, key=...)` build collector records with `raw` shaped as in section 5 of the source 5 spec. `RUN` is a run result with `extra = {"cells": [{"retailer": "ulta", "status": "ok", "reason": "", "selected": 10}, {"retailer": "target", "status": "could_not_look", "reason": "missing_token", "selected": 0}]}`.
```python
ULTA_LI = {"productId": "pimprod2045775", "productName": "Light Dry Shampoo - Mellow Melon", "brandName": "Batiste",
           "listPrice": "$12.99", "salePrice": None, "rating": 4.5, "reviewCount": 28849, "sponsored": False}
ULTA_R = {"ugc_id": 589138362, "details": {"headline": "I Stick With Batiste", "comments": "I love this specific Batiste dry shampoo",
          "created_date": 1793021408804}, "badges": {"is_verified_buyer": False}, "metrics": {"rating": 5, "helpful_votes": 0}}

def test_parse_price(self):
    self.assertEqual(parse_price("$12.99"), (Decimal("12.99"), None))
    self.assertEqual(parse_price("$18.00 - $46.00"), (Decimal("18.00"), Decimal("46.00")))
    self.assertEqual(parse_price("$1,299.00"), (Decimal("1299.00"), None))
    for bad in ("", "12.99", "from $5", "$5 - "):
        with self.assertRaises(ValueError): parse_price(bad)

def test_ulta_product(self):
    row = map_run(RUN, [product("ulta", ULTA_LI, key="ulta:pimprod2045775")]).rows[0]
    self.assertEqual((row.table, row.kind, row.key, row.scope), ("products", "product", "ulta:pimprod2045775", "ulta"))
    self.assertEqual(row.columns, {"retailer": "ulta", "product_id": "pimprod2045775", "title": "Light Dry Shampoo - Mellow Melon",
        "price": Decimal("12.99"), "price_max": None, "list_price": None, "currency": "USD", "rating": Decimal("4.50"),
        "review_count": 28849, "rank": 1, "sponsored": False, "availability": None, "seller_name": None, "sold_count": None})

def test_ulta_range_and_sale(self):
    cols = lambda **kw: map_run(RUN, [product("ulta", {**ULTA_LI, **kw}, key="ulta:x")]).rows[0].columns
    c = cols(listPrice="$12.99 - $20.99")
    self.assertEqual((c["price"], c["price_max"], c["list_price"]), (Decimal("12.99"), Decimal("20.99"), None))
    c = cols(listPrice="$12.99", salePrice="$9.74")
    self.assertEqual((c["price"], c["price_max"], c["list_price"]), (Decimal("9.74"), None, Decimal("12.99")))

def test_target_product(self):
    li = items("apify/target_al_store2581_4brands.json")[0]        # tcin 75561114
    c = map_run(RUN, [product("target", li, key="target:75561114")]).rows[0].columns
    self.assertEqual((c["title"], c["price"], c["price_max"], c["list_price"], c["rating"], c["review_count"], c["sponsored"], c["availability"]),
        ("Batiste Brunette Dry Shampoo - 3.81oz", Decimal("8.99"), None, None, Decimal("4.27"), 567, True, "IN_STOCK"))
    sale = next(i for i in items("apify/target_al_store2581_4brands.json") if i["tcin"] == "17079185")
    c = map_run(RUN, [product("target", sale, key="target:17079185")]).rows[0].columns
    self.assertEqual((c["price"], c["list_price"]), (Decimal("9.99"), Decimal("11.59")))

def test_sephora_product(self):
    its = items("apify/sephora_search_igview_bestselling_3.json")
    c = map_run(RUN, [product("sephora", its[0], key="sephora:P525776")]).rows[0].columns
    self.assertEqual((c["title"], c["price"], c["price_max"], c["rating"], c["review_count"], c["sponsored"]),
        ("Sheer Clean Non-Aerosol Dry Shampoo Mist", Decimal("33.00"), None, Decimal("4.57"), 341, False))
    c = map_run(RUN, [product("sephora", its[2], key="sephora:P399330")]).rows[0].columns
    self.assertEqual((c["price"], c["price_max"], c["review_count"]), (Decimal("18.00"), Decimal("46.00"), 4379))

def test_chewy_product(self):
    li = items("apify/chewy_search_jinx_parseforge.json")[0]       # partNumber 845310
    c = map_run(RUN, [product("chewy", li, key="chewy:845310")]).rows[0].columns
    self.assertEqual((c["price"], c["list_price"], c["rating"], c["review_count"], c["sponsored"], c["availability"]),
        (Decimal("47.34"), Decimal("52.99"), Decimal("4.58"), 1260, None, "IN_STOCK"))
    self.assertTrue(c["title"].startswith("Jinx Beef, Brown Rice & Sweet Potato"))

def test_reviews(self):
    row = map_run(RUN, [review("ulta", "ulta:pimprod2045775", ULTA_R, key="ulta:pimprod2045775:589138362")]).rows[0]
    self.assertEqual((row.table, row.kind, row.scope), ("reviews", "review", "ulta"))
    self.assertEqual(row.columns, {"product_key": "ulta:pimprod2045775", "rating": 5, "title": "I Stick With Batiste",
        "body": "I love this specific Batiste dry shampoo", "review_date": date(2026, 10, 26), "verified": False, "helpful_votes": 0})
    t = map_run(RUN, [review("target", "target:88498115", items("apify/target_reviews_A-88498115.json")[0], key="target:88498115:h0")]).rows[0].columns
    self.assertEqual((t["rating"], t["title"], t["review_date"], t["verified"], t["helpful_votes"]), (5, "Go to coffee", date(2026, 10, 25), None, None))
    c = map_run(RUN, [review("chewy", "chewy:845310", items("apify/chewy_reviews_alc_845310.json")[0], key="chewy:845310:r0")]).rows[0].columns
    self.assertEqual((c["rating"], c["title"], c["review_date"], c["verified"], c["helpful_votes"]), (1, "Disappointed", date(2026, 11, 7), None, 0))

def test_scopes_and_empty_run(self):
    m = map_run(RUN, [])
    self.assertEqual((m.rows, m.not_fetched), ([], 0))
    self.assertEqual(m.scopes, [Scope("ulta", "ok", ""), Scope("target", "could_not_look", "missing_token")])

def test_unknown_inputs_are_errors(self):
    for bad in (product("walmart", ULTA_LI, key="walmart:1"),
                {**product("ulta", ULTA_LI, key="ulta:2"), "kind": "listing"},
                product("ulta", {**ULTA_LI, "listPrice": "call for price"}, key="ulta:3")):
        with self.assertRaises(MapError) as e: map_run(RUN, [bad])
        self.assertTrue(str(e.exception).startswith(bad["key"]))

def test_registry(self):
    self.assertIs(mappers.MAPPERS["retail_shelf"], mappers.retail_shelf)
```

- [ ] **Step 2: Run them.** Expected: FAIL (no `mappers` package).
- [ ] **Step 3: Write `mappers/retail_shelf.py` and `mappers/__init__.py`** as specified.
- [ ] **Step 4: Run all tests.** Expected: 31 tests, OK.
- [ ] **Step 5: Commit**: `Add retail shelf mapper`.

---

### Task 5: Command line and a load of the real runs

**Files:**
- Modify: `part1/pipeline/load.py` (add `main`)
- Create: `part1/pipeline/tests/test_cli.py`, `part1/pipeline/README.md`

**Interfaces:**
- Consumes: `load_all`, `db`, `mappers.MAPPERS`.
- Produces: `main(argv: list[str] | None = None, mappers: dict | None = None) -> int` in `load.py`, and `if __name__ == "__main__": sys.exit(main())`.
  - One option: `--collectors-dir <path>`, default `part1/collectors` of the repository the script is in. `mappers` defaults to `MAPPERS`.
  - Connects with `db.database_url()`, runs `ensure_schema`, then `load_all`.
  - Prints one line for every outcome except `already_loaded`:
    `<source> <brand> <run_id> <status> <result> inserted=<n> updated=<n> ended=<n> not_fetched=<n>`, followed by ` error=<text>` when the result is `failed`.
  - Then one summary line: `runs: applied=<n> superseded=<n> empty_no_mapper=<n> failed=<n> already_loaded=<n> no_mapper=<sources>`, where `<sources>` is the sorted, comma-separated sources that had `no_mapper` outcomes, or `-`.
  - Returns 1 when any outcome is `failed`, else 0.
  - When the database cannot be reached: prints `cannot connect to <url>: <error>` with any password removed from the URL, and returns 1.

- [ ] **Step 1: Write the failing tests** in `tests/test_cli.py`. `capture(self, fn)` calls `fn()` with stdout and stderr captured together and returns `(return value, text)`. `cli(self)` sets `DATABASE_URL` to `self.url` in `os.environ` for the call and returns `self.capture(lambda: main(["--collectors-dir", str(self.dir)], mappers={"fake": support.FAKE}))`. (Do not name a helper `run`; `unittest.TestCase` owns that name.)
```python
def test_lines_summary_and_second_run(self):
    self.write_run("fake", "b", T1, records=[rec("a"), rec("b")])
    self.write_run("nomap", "b", T1, records=[rec("a")])
    code, text = self.cli()
    self.assertEqual(code, 0)
    self.assertEqual(text.splitlines(), [
        "fake b 20261110T100000Z ok applied inserted=2 updated=0 ended=0 not_fetched=0",
        "nomap b 20261110T100000Z ok no_mapper inserted=0 updated=0 ended=0 not_fetched=0",
        "runs: applied=1 superseded=0 empty_no_mapper=0 failed=0 already_loaded=0 no_mapper=nomap"])
    code, text = self.cli()
    self.assertEqual(text.splitlines(), [
        "nomap b 20261110T100000Z ok no_mapper inserted=0 updated=0 ended=0 not_fetched=0",
        "runs: applied=0 superseded=0 empty_no_mapper=0 failed=0 already_loaded=1 no_mapper=nomap"])

def test_failed_run_returns_1(self):
    self.write_run("fake", "b", T1, records=[rec("x", bad=True)])
    code, text = self.cli()
    self.assertEqual(code, 1)
    self.assertIn("fake b 20261110T100000Z ok failed inserted=0 updated=0 ended=0 not_fetched=0 error=x", text)

def test_unreachable_database_returns_1(self):
    with mock.patch.dict(os.environ, {"DATABASE_URL": "postgresql://u:secret@localhost:1/nope"}):
        code, text = self.capture(lambda: main(["--collectors-dir", str(self.dir)]))
    self.assertEqual(code, 1)
    self.assertIn("cannot connect to postgresql://u@localhost:1/nope", text)
    self.assertNotIn("secret", text); self.assertNotIn("Traceback", text)
```

- [ ] **Step 2: Run them.** Expected: FAIL (`main` not defined).
- [ ] **Step 3: Add `main`** as specified.
- [ ] **Step 4: Run all tests.** Expected: 34 tests, OK.
- [ ] **Step 5: Write `part1/pipeline/README.md`** (under 40 lines): what the loader does in three sentences, the setup (a running local Postgres, `createdb market_radar`, the virtual environment, `DATABASE_URL`), the command, the output lines, and the test command with `TEST_DATABASE_URL`.
- [ ] **Step 6: Load the real runs.** The run files are not in git; they are in the main checkout, whose path the dispatch gives. Run
  `.venv/bin/python part1/pipeline/load.py --collectors-dir <main checkout>/part1/collectors`
  and then check, with `psql market_radar`:
  - `SELECT count(*) FROM products WHERE source = 'retail_shelf'` equals the number of distinct `product` keys per brand, summed, in the `05_retail_shelf` run files; the same for `reviews` and `review` keys. (On 2026-11-10 that was 20 and 200.)
  - `SELECT brand, scope, status, reason FROM run_scopes WHERE source = 'retail_shelf'` shows `ulta` `ok` for `batiste` and `living-proof`, and `could_not_look` for every other cell.
  - Every run with no records from a source without a mapper is in `runs` with `result = 'empty_no_mapper'`; the summary line names the sources that have records and no mapper.
  - Running the same command again prints no `applied` line and the same counts.
  Report the printed output and the four results. If a count differs, stop and report; do not adjust the data.
- [ ] **Step 7: Commit**: `Add loader command and README`.
