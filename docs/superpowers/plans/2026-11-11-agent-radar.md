# Agent Radar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add what the agents read on top of the six tables: a `changes` log, an `ad_angles` table filled from a labels file, and three views (`radar_running`, `radar_angles`, `radar_response`).

**Architecture:** The loader already compares each row with its stored state; it now also writes that comparison to `changes` in the same transaction. Angles are read outside the loader (by a model or a person) into a committed file keyed by the hash of the ad text; `load.py` copies them into `ad_angles` after its runs. The three views are plain SQL in `schema.sql`, dropped and created on every schema check.

**Tech Stack:** Python 3 standard library, `psycopg` 3, PostgreSQL 16, `unittest` against a real Postgres. The official `anthropic` package only in `angles.py --label`.

**Spec:** `docs/superpowers/specs/2026-11-11-agent-radar-design.md` (binding). It builds on `docs/superpowers/specs/2026-11-10-market-radar-tables-design.md`.

## Global Constraints

1. Hand-written code. At least one source is collected without a paid scraping service.
2. Rerun-safe. Running twice creates no duplicates. A missing item is marked ended, never deleted.
3. Honest gaps. A source that could not be reached is recorded as "could not look", never as "nothing found". Partial collection is marked.
4. Clean collection. No one else's account. No personal data of private individuals. Requests are spaced.
5. Local Postgres, one command: `python part1/pipeline/load.py` fills everything.
6. Every record keeps its source URL and fetch time.
7. The six item tables, the mappers and the collectors are not changed.
8. Documents and code comments are in English. No absolute local paths, tokens or keys in any committed file.
9. The loader's existing behaviour and its existing 186 tests stay as they are, except the three places this plan names (`test_schema.TABLES`, the base-table filter in `test_schema`, the lines `test_cli` expects).
10. Tests run with `TEST_DATABASE_URL=postgresql://localhost:5432/market_radar_test .venv/bin/python -m unittest discover -s part1/pipeline/tests` from the repository root. Every task ends with the whole suite green.

## Review Focus

1. A second load of the same files writes no `changes` rows, and a failed run leaves none behind (Task 1).
2. Numbers that are equal but written differently (`12.990`, `12.99`; `7` and `7.0`) are not a change (Task 1).
3. An ad first seen late in its life and ended a few days later is not `not_working` (Task 3).
4. An evidence phrase that is not in the ad's words, or that carries an `@` handle, never reaches `ad_angles` (Tasks 2 and 5).
5. A labels file with one bad line fails the angles step and leaves the loaded runs and the old `ad_angles` rows in place (Task 2).

---

### Task 1: `changes`, written by the loader

**Files:**
- Modify: `part1/pipeline/schema.sql` (add the table and two indexes, spec 3.1)
- Modify: `part1/pipeline/model.py` (add `TRACKED`)
- Modify: `part1/pipeline/load.py` (`_write_rows`, `_end_absent`)
- Modify: `part1/pipeline/tests/test_schema.py` (`TABLES` gains `"changes"`)
- Test: `part1/pipeline/tests/test_changes.py` (new)

**Interfaces:**
- Produces: `model.TRACKED: dict[str, tuple[str, ...]]`, exactly the table of spec 3.3 (`reviews` and `search_interest` map to `()`).
- Produces: table `changes` with the columns of spec 3.1. Later tasks read it with `change = 'appeared'` and `change = 'changed'`.
- Consumes: `support.FAKE` (its `ENDING` has `("products","product"): "absent"` and `("ads","ad"): "source_date"`), `support.rec(key, kind, table, scope, **raw)` where `raw["columns"]` becomes the row's columns.

- [ ] **Step 1: Write the failing tests** in `test_changes.py`, in the style of `test_ending.py` (`T1`, `T2`, `T3`, `M = {"fake": support.FAKE}`, `load_all(self.conn, self.dir, M)`). A helper `changes()` returns `self._query("SELECT * FROM changes ORDER BY id")`. A helper `prod(key, **columns)` returns `rec(key, columns={"retailer": "shop", **columns})`.

```python
def test_first_load_writes_nothing(self):
    self.write_run("fake", "b", T1, records=[prod("a", price="12.99")]); self.load()
    self.assertEqual(self.changes(), [])

def test_new_key_after_a_complete_look_appears(self):
    self.write_run("fake", "b", T1, records=[prod("a")]); self.load()
    self.write_run("fake", "b", T2, records=[prod("a"), prod("n")]); self.load()
    self.assertEqual([(c["change"], c["key"], c["table_name"], c["kind"], c["changed_at"], c["run_id"], c["field"])
                      for c in self.changes()], [("appeared", "n", "products", "product", ts(T2), T2, None)])

def test_new_key_after_a_partial_look_does_not_appear(self):
    self.write_run("fake", "b", T1, status="partial", reason="x", records=[prod("a")]); self.load()
    self.write_run("fake", "b", T2, records=[prod("a"), prod("n")]); self.load()
    self.assertEqual(self.changes(), [])

def test_changed_values_one_row_per_column(self):
    self.write_run("fake", "b", T1, records=[prod("a", price="12.99", rank=3, sponsored=False, availability="IN_STOCK")]); self.load()
    self.write_run("fake", "b", T2, records=[prod("a", price="10.50", rank=3, sponsored=True, availability=None)]); self.load()
    self.assertEqual(sorted((c["field"], c["old_value"], c["new_value"]) for c in self.changes()),
                     [("availability", "IN_STOCK", None), ("price", "12.99", "10.5"), ("sponsored", "false", "true")])
    self.assertEqual({c["change"] for c in self.changes()}, {"changed"})

def test_equal_numbers_written_differently_are_not_a_change(self):
    self.write_run("fake", "b", T1, records=[prod("a", price="12.99", rating="4.50", review_count=30000000)]); self.load()
    self.write_run("fake", "b", T2, records=[prod("a", price="12.990", rating="4.5", review_count=30000000)]); self.load()
    self.assertEqual(self.changes(), [])

def test_untracked_and_left_out_columns_are_not_compared(self):
    self.write_run("fake", "b", T1, records=[prod("a", price="5", title="old")]); self.load()
    self.write_run("fake", "b", T2, records=[prod("a", title="new")]); self.load()   # price left out, title not tracked
    self.assertEqual(self.changes(), [])

def test_ended_by_absence_then_reappeared(self):
    self.write_run("fake", "b", T1, records=[prod("a"), prod("b")]); self.load()
    self.write_run("fake", "b", T2, records=[prod("a")]); self.load()
    self.write_run("fake", "b", T3, records=[prod("a"), prod("b")]); self.load()
    self.assertEqual([(c["change"], c["key"], c["changed_at"]) for c in self.changes()],
                     [("ended", "b", ts(T2)), ("reappeared", "b", ts(T3))])

def test_source_date_policy(self):
    ad = lambda key, shown: rec(key, kind="ad", table="ads", columns={"channel": "google", "last_shown_at": shown})
    self.write_run("fake", "b", T1, records=[ad("live", "2026-11-09T00:00:00Z"), ad("old", "2026-10-01T00:00:00Z")]); self.load()
    self.assertEqual(self.changes(), [])                       # "old" was inserted already ended
    later = "20261120T100000Z"
    self.write_run("fake", "b", later, records=[ad("live", "2026-11-09T00:00:00Z"), ad("old", "2026-10-02T00:00:00Z")]); self.load()
    self.assertEqual([(c["change"], c["key"], c["changed_at"]) for c in self.changes()], [("ended", "live", ts(later))])
    again = "20261121T100000Z"
    self.write_run("fake", "b", again, records=[ad("live", "2026-11-21T00:00:00Z")]); self.load()
    self.assertEqual([(c["change"], c["key"]) for c in self.changes()][1:], [("reappeared", "live")])

def test_second_load_superseded_and_failed_runs_write_nothing(self):
    self.write_run("fake", "b", T1, records=[prod("a")]); self.load()
    self.write_run("fake", "b", T3, records=[prod("a"), prod("n")]); self.load()
    before = self.changes()
    self.load()                                                                    # same files again
    self.write_run("fake", "b", T2, records=[prod("a"), prod("x")]); self.load()   # older than T3: superseded
    bad = "20261110T130000Z"
    self.write_run("fake", "b", bad, records=[prod("a", price="1"), rec("z", bad=True)]); self.load()   # fails to map
    self.assertEqual(self.changes(), before)
```

Add one more test with two scopes through `extra={"scopes": [...]}`: scope `s1` was `ok` in T1 and scope `s2` was `partial`; in T2 a new key in `s1` appears and a new key in `s2` does not.

- [ ] **Step 2: Run them and see them fail** (`relation "changes" does not exist`).

- [ ] **Step 3: Implement.**
  - `schema.sql`: `CREATE TABLE IF NOT EXISTS changes (...)` with a `CHECK` on `change`, and the two indexes with `CREATE INDEX IF NOT EXISTS`.
  - `load.py`: a helper `_change_text(value) -> str | None` (NULL stays NULL; `bool` gives `true`/`false`; numbers in plain decimal notation without exponent or trailing zeros, e.g. `Decimal("10.50")` gives `10.5` and `30000000` gives `30000000`; anything else `str`).
  - `_write_rows`: read the tracked columns together with `ended_at` before writing. For an update, compare what the database held before with what it holds after the `UPDATE` (use `RETURNING` on the tracked columns the mapper supplied), so both sides are in the column's type. Write `reappeared` when the row had an `ended_at` and now has none, `ended` when it had none and now has one, `changed` per differing column. For an insert with `ended_at` NULL, write `appeared` when an earlier complete look exists: one query on `run_scopes` joined to `runs` (`result = 'applied'`, `status = 'ok'`, same source, brand and scope name, `run_id` smaller than this run's); cache the answer per scope for the run.
  - `_end_absent`: add `RETURNING key` to both `UPDATE` statements and write one `ended` row per returned key (`table_name`, `kind` from the loop).
  - `changed_at` is the run's `started_at`; `run_id` the run's.

- [ ] **Step 4: Run the whole suite; all green.** `test_schema` needs `"changes"` in `TABLES`.

- [ ] **Step 5: Commit** (`Record what changed between runs in a changes table`).

---

### Task 2: `ad_angles`, the labels file, and the pending list

**Files:**
- Modify: `part1/pipeline/schema.sql` (table `ad_angles`, spec 5.4)
- Create: `part1/pipeline/angles.py`
- Create: `part1/pipeline/labels/ad_angles.jsonl` (empty file)
- Modify: `part1/pipeline/load.py` (`main`: `--labels`, the angles step, the `angles:` line)
- Modify: `part1/pipeline/tests/test_schema.py` (`TABLES` gains `"ad_angles"`), `part1/pipeline/tests/test_cli.py` (expected lines)
- Test: `part1/pipeline/tests/test_angles.py` (new)

**Interfaces (all in `angles.py`):**

```python
OFFER = ("discount", "free_gift", "bundle", "subscription", "giveaway", "free_shipping", "none")
MESSAGE = ("benefit", "ingredient", "convenience", "proof", "personal_fit", "novelty", "gifting", "availability", "brand", "none")
VOICE = ("brand", "creator", "customer", "expert", "celebrity_event")
LIST_VERSION = 1
LABELS_FILE = Path(__file__).resolve().parent / "labels" / "ad_angles.jsonl"

class LabelError(Exception):          # .line (1-based, 0 when not tied to a line), .reason; str() is "line <n>: <reason>"
def ad_text(headline, body) -> str    # spec 5.2; "" when both are empty
def text_hash(text: str) -> str       # SHA-256 hex of the UTF-8 text
def check_label(label: dict) -> str | None        # reason, or None when the line's own shape is valid
def check_evidence(label: dict, text: str) -> str | None   # reason when an evidence is not in `text`
def read_labels(path: Path) -> dict[str, dict]    # hash -> label; raises LabelError; a missing file gives {}
def apply_labels(conn, path: Path = LABELS_FILE) -> tuple[int, int, int]   # (labeled, not_labeled, no_text) ads; raises LabelError; does not commit
def pending(conn, path: Path = LABELS_FILE) -> list[dict]   # spec 5.3, most-used text first, then by hash
def main(argv: list[str] | None = None) -> int    # --pending prints one JSON object per line
```

`check_label` enforces: the keys of spec 5.2 are all present; values are in the lists; `list_version` equals `LIST_VERSION`; `text_sha256` is 64 lower-case hex; an evidence is a non-empty string of at most 12 whitespace-separated words without `@` when its value is not `none` (offer, message) and not `brand` (voice), and `None` otherwise. Reasons are short fixed strings, for example `angle_offer not in list`, `offer_evidence missing`, `voice_evidence not expected`, `message_evidence has a handle`, `message_evidence longer than 12 words`.

`check_evidence` compares after the same whitespace normalisation as `ad_text`; reason for example `offer_evidence not in the ad text`.

- [ ] **Step 1: Write the failing tests** in `test_angles.py` (a `DbTestCase`; insert `ads` rows with a small helper `ad(key, headline, body, brand="b", channel="meta")` that runs an `INSERT` with `source='fake'`, `kind='ad'`, `scope='all'`, `first_seen_at`/`last_seen_at` set, `last_run_id='r'`, `raw='{}'`; write labels with a helper `line(text, **over)` that builds a valid line for `text_hash(text)`).

```python
def test_ad_text_and_hash(self):
    self.assertEqual(angles.ad_text("  Save   20%\n", " Bundled for\tthe busy "), "Save 20%\nBundled for the busy")
    self.assertEqual(angles.ad_text(None, "x"), "\nx")
    self.assertEqual(angles.ad_text(" ", None), "")
    self.assertEqual(angles.text_hash("a"), hashlib.sha256(b"a").hexdigest())

def test_check_label_reasons(self):
    good = line("Save 20%\nfor the busy", angle_offer="discount", offer_evidence="Save 20%")
    self.assertIsNone(angles.check_label(good))
    for change, reason in [({"angle_offer": "sale"}, "angle_offer not in list"),
                           ({"offer_evidence": None}, "offer_evidence missing"),
                           ({"angle_offer": "none"}, "offer_evidence not expected"),
                           ({"offer_evidence": "ask @someone"}, "offer_evidence has a handle"),
                           ({"offer_evidence": " ".join(["w"] * 13)}, "offer_evidence longer than 12 words"),
                           ({"voice_evidence": "x"}, "voice_evidence not expected"),
                           ({"list_version": 2}, "list_version is not 1")]:
        self.assertEqual(angles.check_label({**good, **change}), reason)

def test_apply_counts_and_rows(self):
    ad("1", "Save 20%", "for the busy"); ad("2", "Save 20%", "for the busy"); ad("3", "Other", "words"); ad("4", None, " ")
    self.write_labels([line("Save 20%\nfor the busy", angle_offer="discount", offer_evidence="Save 20%",
                            angle_message="convenience", message_evidence="for the busy")])
    self.assertEqual(angles.apply_labels(self.conn, self.labels), (2, 1, 1))
    rows = self.table("ad_angles")
    self.assertEqual([(r["key"], r["angle_offer"], r["offer_evidence"], r["angle_message"], r["angle_voice"], r["voice_evidence"])
                      for r in rows], [("1", "discount", "Save 20%", "convenience", "brand", None),
                                       ("2", "discount", "Save 20%", "convenience", "brand", None)])
    self.assertEqual(angles.apply_labels(self.conn, self.labels), (2, 1, 1))      # again: same rows, no duplicates
    self.assertEqual(len(self.table("ad_angles")), 2)

def test_apply_rejects_evidence_that_is_not_in_the_text(self):
    ad("1", "Save 20%", "for the busy")
    self.write_labels([line("Save 20%\nfor the busy", angle_offer="discount", offer_evidence="Half price")])
    with self.assertRaises(angles.LabelError) as e:
        angles.apply_labels(self.conn, self.labels)
    self.assertEqual(str(e.exception), "line 1: offer_evidence not in the ad text")

def test_read_labels_names_the_line(self):
    # line 2 is not JSON; then a duplicate hash on line 2; then a bad value on line 3
    ...  # each case: assertRaises(LabelError), str() starts with "line <n>: "

def test_unknown_hash_and_missing_file_are_fine(self):
    ad("1", "A", "b")
    self.write_labels([line("no such ad\nat all")])
    self.assertEqual(angles.apply_labels(self.conn, self.labels), (0, 1, 0))
    self.assertEqual(angles.apply_labels(self.conn, self.dir / "none.jsonl"), (0, 1, 0))

def test_pending(self):
    ad("1", "Save 20%", "x", brand="b1", channel="meta"); ad("2", "Save 20%", "x", brand="b2", channel="site")
    ad("3", "Solo", "y"); ad("4", None, None); ad("5", "Done", "z")
    self.write_labels([line("Done\nz")])
    self.assertEqual(angles.pending(self.conn, self.labels), [
        {"text_sha256": angles.text_hash("Save 20%\nx"), "text": "Save 20%\nx", "brands": ["b1", "b2"],
         "channels": ["meta", "site"], "kinds": ["ad"], "ads": 2},
        {"text_sha256": angles.text_hash("Solo\ny"), "text": "Solo\ny", "brands": ["b"], "channels": ["meta"],
         "kinds": ["ad"], "ads": 1}])
```

Add to `test_cli.py`: the `cli()` helper passes `"--labels", str(self.dir / "labels.jsonl")`; every expected output gains the line `angles: labeled=0 not_labeled=0 no_text=0` just before the `runs:` line; one new test writes an `ads` row through the fake mapper (`rec("x", kind="ad", table="ads", columns={"channel": "meta", "headline": "H", "body": "B"})`) plus a labels file whose single line has a value outside the list, and asserts the exit code 1, the line `angles: failed: line 1: angle_offer not in list` just before the `runs:` line, and that the run's row is still in `ads`.

- [ ] **Step 2: Run them and see them fail** (`No module named 'angles'`).

- [ ] **Step 3: Implement `angles.py`, the table, and the step in `load.py`.**
  - `apply_labels`: read the labels; select `source, brand, kind, key, headline, body` from `ads`; `DELETE FROM ad_angles`; insert a row for each ad whose text hash has a label, after `check_evidence` against that ad's text (a failure raises `LabelError` with the label's line). It does not commit; the caller does.
  - `load.py` `main`: new argument `--labels` (default `angles.LABELS_FILE`). After `load_all`, call `apply_labels` and commit; on `LabelError` roll back and remember the reason. Print the `angles:` line, or `angles: failed: <LabelError text>`, right before the `runs:` line. The exit code is 1 when a run failed or the angles step failed.
  - `main` of `angles.py`: `--pending` connects like `load.py` does (`db.database_url()`, `db.connect`), prints `json.dumps(obj, ensure_ascii=False)` per line, returns 0. `--labels` as in `load.py`.

- [ ] **Step 4: Run the whole suite; all green.**

- [ ] **Step 5: Commit** (`Add ad_angles, filled from a labels file keyed by the ad text`).

---

### Task 3: `radar_running` and `radar_response`

**Files:**
- Modify: `part1/pipeline/schema.sql` (two views, at the end)
- Modify: `part1/pipeline/tests/test_schema.py` (`test_ensure_schema_twice` lists base tables only: add `AND table_type = 'BASE TABLE'` to its query, since views also appear in `information_schema.tables`)
- Test: `part1/pipeline/tests/test_radar_views.py` (new)

**Interfaces:**
- Consumes: tables `ads`, `changes`, `ad_angles`, `posts`, `products`, `search_rankings`.
- Produces: view `radar_running` with the columns of spec 4, in that order; view `radar_response` with the columns of spec 7, in that order. Task 4 reads `radar_running`.
- At the end of `schema.sql`: `DROP VIEW IF EXISTS radar_response; DROP VIEW IF EXISTS radar_running;` then the two `CREATE VIEW` statements, so the definitions in the file always win.

- [ ] **Step 1: Write the failing tests.** Rows are inserted with SQL helpers (`ad(key, **columns)`, `post(...)`, `product(...)`, `ranking(...)`, `change(...)`), with defaults for the common columns; times are given as ISO strings.

```python
def test_destination_and_subject(self):
    cases = [  # landing_domain, landing_url, destination, subject_type, subject
        ("livingproof.com", "https://www.livingproof.com/products/sheer-clean-mist?x=1#top", "brand_site", "product", "sheer-clean-mist"),
        ("livingproof.com", "https://www.livingproof.com/collections/holiday-kits/products/the-set/", "brand_site", "product", "the-set"),
        ("livingproof.com", "https://www.livingproof.com/collections/holiday-kits", "brand_site", "collection", "collections/holiday-kits"),
        ("livingproof.com", "https://www.livingproof.com/pages/dry-shampoo", "brand_site", "page", "pages/dry-shampoo"),
        ("livingproof.com", "https://www.livingproof.com/", "brand_site", "home", "home"),
        ("buy.batistehair.com", "https://buy.batistehair.com/social/abc", "brand_site", "page", "social/abc"),
        ("ulta.com", "https://www.ulta.com/p/berry-disco-pimprod1", "retailer", "retailer_product", "ulta.com/p/berry-disco-pimprod1"),
        ("example.org", "https://example.org/x", "other", "other", "example.org/x"),
        ("thinkjinx.com", None, "brand_site", None, None),
        (None, None, None, None, None)]
    ...  # one ad per case; compare (destination, subject_type, subject) per key

def test_days_live_and_verdict(self):
    cases = [  # started_at, first_seen_at, last_seen_at, ended_at, appeared row?, start_basis, days_live, status, verdict
        ("2026-10-01", "2026-11-01", "2026-11-10", None,         False, "source",     40,  "live",  "working"),
        ("2026-11-01", "2026-11-01", "2026-11-10", "2026-11-04", False, "source",     3,   "ended", "not_working"),
        ("2026-11-01", "2026-11-01", "2026-11-10", "2026-11-08", False, "source",     7,   "ended", "not_working"),
        ("2026-11-01", "2026-11-01", "2026-11-10", "2026-11-09", False, "source",     8,   "ended", "undecided"),
        ("2026-04-01", "2026-11-01", "2026-11-10", "2026-10-18", False, "source",     200, "ended", "working"),
        ("2026-10-11", "2026-11-01", "2026-11-10", None,         False, "source",     30,  "live",  "working"),
        ("2026-11-01", "2026-11-01", "2026-11-10", None,         False, "source",     9,   "live",  "undecided"),
        (None,         "2026-11-01", "2026-11-10", "2026-11-04", False, "first_seen", 3,   "ended", "undecided"),
        (None,         "2026-11-01", "2026-11-10", "2026-11-04", True,  "first_seen", 3,   "ended", "not_working"),
        (None,         "2026-10-01", "2026-11-10", None,         False, "first_seen", 40,  "live",  "working")]
    ...  # all times at 00:00:00Z; assert (start_basis, days_live, status, verdict) per key

def test_angle_columns(self):
    # labeled ad: the three values from ad_angles, angle_state "labeled"
    # ad with text and no row: (None, None, None, "not_labeled")
    # ad with empty headline and body: (None, None, None, "no_text")

def test_running_has_one_row_per_ad_and_the_spec_columns(self):
    self.assertEqual(self.columns("radar_running"), [
        "source", "brand", "channel", "kind", "key", "url", "fetched_at", "format", "headline", "body", "cta",
        "landing_url", "landing_domain", "offer_code", "variation_count", "destination", "subject_type", "subject",
        "started", "start_basis", "ended_at", "status", "days_live", "verdict",
        "angle_offer", "angle_message", "angle_voice", "angle_state"])

def test_response_rows(self):
    # a post with views 100, likes 5, comments 0, shares None, saves 2, followers 50, creator_is_brand False:
    #   rows for views, likes, comments, saves (not shares); nature "post", place "tiktok", by_brand False, better "higher";
    #   views row: baseline "followers", baseline_value 50, ratio 2, verdict "working"; the others have all four NULL
    # a post with views 10, followers 50: views row ratio 0.2, verdict None; a post with followers 0: ratio None, verdict None
    # products: source amazon kind product (rank 2, rating 4.5, review_count 10, sold_count None) gives 3 rows,
    #   rank "lower", the others "higher", place = retailer, label = title, by_brand None;
    #   source tiktok_shop kind search_result gives no rows; source brand_site_and_emails gives no rows
    # a search ranking (keyword "k w", domain "d.com", position 3): one row, nature "search_result", place "google",
    #   label "k w -> d.com", metric "position", value 3, better "lower"
    self.assertEqual(self.columns("radar_response"), [
        "source", "brand", "key", "url", "fetched_at", "first_seen_at", "last_seen_at", "ended_at", "nature", "place",
        "label", "by_brand", "metric", "value", "better", "baseline", "baseline_value", "ratio",
        "previous_value", "moved", "moved_at", "verdict"])

def test_response_last_move(self):
    # changes rows for a product's rank: 5 -> 4 at T1, 4 -> 2 at T2 (the product's rank is now 2)
    #   the rank row has previous_value 4, moved -2, moved_at T2; its rating row has all three NULL
    # an ended item keeps its rows and shows its ended_at
```

- [ ] **Step 2: Run them and see them fail.**

- [ ] **Step 3: Write the two views** from spec 4 and 7. The brand domains and the retailer list are `VALUES` lists inside the view. A domain matches a list entry when it is equal to it or ends with `.` followed by it. `days_live` is `floor` of the difference in days. `ratio`, `previous_value` and `moved` are `numeric`.

- [ ] **Step 4: Run the whole suite; all green.**

- [ ] **Step 5: Commit** (`Add radar_running and radar_response views`).

---

### Task 4: `radar_angles`

**Files:**
- Modify: `part1/pipeline/schema.sql` (the view; its `DROP VIEW IF EXISTS radar_angles;` comes before the drop of `radar_running`)
- Test: `part1/pipeline/tests/test_radar_views.py` (add a class)

**Interfaces:**
- Consumes: `radar_running`.
- Produces: view `radar_angles` with the columns of spec 6, in that order.

- [ ] **Step 1: Write the failing tests.**

```python
def test_groups_and_counts(self):
    # Brand b, subject "product"/"mist": four labeled ads
    #   1: offer discount, message benefit,    voice brand,   live,  started 2 days before the latest look, 2 days
    #   2: offer none,     message benefit,    voice creator, live,  started 40 days before, working
    #   3: offer none,     message ingredient, voice brand,   started 20 days before with a source start, ended 3 days later, not_working
    #   4: offer discount, message none,       voice brand,   live,  started 10 days before
    # plus one not-labeled ad on the same subject and one labeled ad of brand c: neither changes brand b's rows
    # the latest look is the greatest last_seen_at over all ads
    rows = {(r["angle_kind"], r["angle"]): r for r in self._query(
        "SELECT * FROM radar_angles WHERE brand = 'b' AND subject = 'mist'")}
    self.assertEqual(sorted(rows), [("message", "benefit"), ("message", "ingredient"), ("offer", "discount"),
                                    ("voice", "brand"), ("voice", "creator")])
    r = rows[("message", "benefit")]
    self.assertEqual((r["ads"], r["live"], r["started_last_7d"], r["oldest_days_live"], r["working"], r["not_working"]),
                     (2, 2, 1, 40, 1, 0))
    r = rows[("voice", "brand")]
    self.assertEqual((r["ads"], r["live"], r["started_last_7d"], r["oldest_days_live"], r["working"], r["not_working"]),
                     (3, 2, 1, 10, 0, 1))
    self.assertEqual(rows[("offer", "discount")]["ads"], 2)

def test_ads_without_a_subject_group_under_null(self):
    # two labeled owned-channel ads of brand b without landing_url: rows with subject_type None and subject None

def test_columns(self):
    self.assertEqual(self.columns("radar_angles"), ["brand", "subject_type", "subject", "angle_kind", "angle", "ads",
                                                    "live", "started_last_7d", "oldest_days_live", "working", "not_working"])
```

- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Write the view** (spec 6). `started_last_7d` counts ads whose `started` is at or after the latest look minus 7 days.
- [ ] **Step 4: Run the whole suite; all green.**
- [ ] **Step 5: Commit** (`Add radar_angles: angles by brand and by what is sold`).

---

### Task 5: `angles.py --label`

**Files:**
- Modify: `part1/pipeline/angles.py`
- Modify: `part1/pipeline/requirements.txt`, `part1/requirements.txt` (add `anthropic`, pinned as `>=` the installed major.minor and `<` the next major)
- Test: `part1/pipeline/tests/test_angles.py` (add a class; no network)

**Interfaces (added to `angles.py`):**

```python
DEFAULT_MODEL = "claude-opus-5-5"
PROMPT_VERSION = "prompt-v1"

class LabelFailure(Exception):            # one text could not be labeled; .reason
def read_key() -> str | None              # ANTHROPIC_API_KEY from the environment, else from .env at the repository root
def answer_schema() -> dict               # JSON schema of the six fields; enums are OFFER, MESSAGE, VOICE; evidences are strings, "" meaning none
def ask_model(client, model: str, text: str) -> dict       # one request; the six fields; raises LabelFailure
def label_pending(conn, path: Path, client, model: str, now: str) -> tuple[int, int]   # (labeled, failed); appends lines
```

The request, exactly (the `anthropic` package's documented shapes):

```python
kwargs = dict(
    model=model, max_tokens=4000,
    system=SYSTEM_PROMPT,                                   # the angle lists and rules of spec 5.1, written by the implementer
    messages=[{"role": "user", "content": text}],
    output_config={"effort": "low", "format": {"type": "json_schema", "schema": answer_schema()}})
if model == DEFAULT_MODEL:                                  # refusal fallback, on by default for this model
    kwargs.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    response = client.beta.messages.create(**kwargs)
else:
    response = client.messages.create(**kwargs)
```

- The client is `anthropic.Anthropic(api_key=key, max_retries=0)`: one request per text, sent once. A text that fails stays pending for the next run.
- `ask_model` turns an empty evidence string into `None` before returning.
- `ask_model` raises `LabelFailure("refusal")` or `LabelFailure("max_tokens")` from `response.stop_reason`, `LabelFailure("not_json")` when the first `text` block does not parse, and turns `anthropic.RateLimitError`, `anthropic.APIStatusError` and `anthropic.APIConnectionError` into `LabelFailure("api: <class name>")`. `anthropic.AuthenticationError` and `anthropic.PermissionDeniedError` are not caught there: `main` prints `label: could not look: auth` and returns 1.
- `label_pending`: for each text of `pending(conn, path)`: ask; build the line (`text_sha256`, `list_version`, `labeled_by` `<model>/<PROMPT_VERSION>`, `labeled_at` `now`, the six fields); it counts as failed when `check_label` or `check_evidence` gives a reason; otherwise append the line and flush. A text that already has a line is never asked again.
- `main --label`: without a key print `label: could not look: missing_key` and return 1 with nothing written. The model is `os.environ.get("ANGLE_MODEL", DEFAULT_MODEL)`. Print one line per failed text (`label: failed <first 12 hex of the hash>: <reason>`) and then `label: labeled=<n> failed=<n> pending=<n>` (pending = texts still without a line); return 0 when `failed` is 0, else 1.

- [ ] **Step 1: Write the failing tests** with a fake client: an object whose `beta.messages.create` and `messages.create` record their keyword arguments and return `SimpleNamespace(stop_reason=..., content=[SimpleNamespace(type="text", text=...)])` from a queue.

```python
def test_valid_answer_is_appended(self):          # one pending text; the fake answers with evidence that is in the text
    # label_pending returns (1, 0); the file has one line; read_labels accepts it; labeled_by == "claude-opus-5-5/prompt-v1"
    # the call went to beta.messages.create with betas and fallbacks == "default", max_tokens 4000,
    # output_config["effort"] == "low", and the schema's enums equal OFFER, MESSAGE, VOICE

def test_other_model_uses_the_plain_endpoint(self):   # model "claude-haiku-5-5": messages.create, no betas, no fallbacks

def test_bad_answers_write_nothing(self):
    # evidence not in the text; a handle in an evidence; stop_reason "refusal"; stop_reason "max_tokens"; text that is not JSON
    # each: label_pending returns (0, 1) and the file stays empty

def test_labeled_text_is_not_asked_again(self):   # a text with a line: the fake client is never called

def test_main_without_key(self):
    # ANTHROPIC_API_KEY unset and read_key patched to None: prints "label: could not look: missing_key", returns 1, file untouched

def test_answer_schema(self):
    s = angles.answer_schema()
    self.assertEqual(s["required"], ["angle_offer", "offer_evidence", "angle_message", "message_evidence", "angle_voice", "voice_evidence"])
    self.assertIs(s["additionalProperties"], False)
    self.assertEqual(s["properties"]["angle_offer"]["enum"], list(angles.OFFER))
    self.assertEqual(s["properties"]["voice_evidence"], {"type": "string"})
```

- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.** `import anthropic` happens inside the functions that need it, so that `load.py` and `--pending` work without the package. Install it in `.venv` (`.venv/bin/pip install anthropic`) and pin what was installed.
- [ ] **Step 4: Run the whole suite; all green.** Do not run `--label` against the real API: the main session does that.
- [ ] **Step 5: Commit** (`Add angles.py --label: ask a model for the angles of pending ad texts`).

---

### After the tasks (main session)

1. Update `part1/pipeline/README.md`: the tables and views, `--labels`, the `angles:` line, `angles.py --pending` and `--label`, the key in `.env`.
2. Run `angles.py --label` with the real key, read a sample of the lines against their texts, and commit the labels file.
3. Drop and reload the local database from the run files and compare with section 10 of the spec; report the `changes` counts and ten rows read by hand.
4. Whole-branch review, then push and open the PR.
