# Part 2 Plan 2: Cold Tier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move older events from the Postgres hot table into encrypted day buckets in MinIO, keep each tenant's state as a snapshot plus the hot tail, and keep every read, erasure and late arrival correct across both tiers, so that `verify.py` passes with the cold tier active.

**Architecture:** A worker flushes one tenant-day at a time. It writes the day's bucket and a new snapshot as new MinIO objects, then makes them current in one Postgres transaction that also inserts the day's index rows and deletes exactly the hot rows it read. State reads restore the snapshot and fold the hot rows on top. Range reads merge cold buckets with hot rows. Customer erasure rewrites only the customer's buckets and refolds only the affected SKUs, and an event older than `cold_until` marks the tenant dirty and sends its reads to a full-fold path.

**Tech Stack:** Go 1.24, `github.com/jackc/pgx/v5` v5.7.6, `github.com/minio/minio-go/v7` **v7.0.97** (later releases require Go 1.25), MinIO server in Docker, Postgres 17, nginx 1.27.

**Spec:** `docs/superpowers/specs/2026-11-10-part2-brand-data-backbone-design.md`. This plan implements §22 steps 2 and 3, minus the rebuild, using §5, §6, §6.1, §7, §8, §9, §10, §11, §12 (detection and slow path only) and §13. It builds on Plan 1 (`docs/superpowers/plans/2026-11-11-part2-plan1-foundation.md`), whose code is on `main`.

**Why erasure is in this plan.** Once flushing is on, Plan 1's hot-only erasure misses a customer's events that are already in cold. The supplied data erases customers from day 30 onward, so `verify.py` would fail. Cross-tier erasure therefore ships together with the cold tier.

**Not in this plan:** the rebuild of dirty tenants (Plan 3; until then a dirty tenant stops flushing and its reads take the full-fold path), sweep and physical deletion of replaced objects (Plan 3), the snapshot cache (Plan 3 or later), metrics, and the crash test.

**Branch:** `part2-plan2-cold`, cut from `main`.

**Supplied files:** `INFRA=/Users/kimbeomsu/Downloads/BARO_Work_Trial/infrastructure`, as in Plan 1.

## Global Constraints

- All of Plan 1's Global Constraints still hold: the interface, status codes, ordering, signatures, configuration, `synchronous_commit = on`, what may be plaintext, ciphertext statistics, logs and metric labels, no wall clock in data decisions, the empty-collection encoding, and English documents.
- **Lock order** (spec §13): 1 cold-writer, 2 tenant-status, 3 customer, 4 cold-commit, all Postgres advisory locks keyed with `lockKey(kind, []byte(tenant)[, customerKey])`. The kinds are `"cold-writer"`, `"tenant-status"`, `"customer"` and `"cold-commit"`. A transaction never takes a lower-numbered lock while holding a higher-numbered one.
- Every ingest holds 2 shared, then 3 shared if the event has a customer, then 4 shared while it reads `cold_until` and writes.
- Flush, cross-tier customer erasure and tenant erasure hold 1 exclusive for the whole operation. Their final writes also take 2 (shared for flush and customer erasure, exclusive for tenant erasure) and, for flush and customer erasure, 4 exclusive.
- **Objects are immutable.** Every object name ends in a random 16-byte hex ID and is never reused. New objects are written before the transaction that makes them current. A replaced object's name goes into `garbage` in that same transaction. Nothing deletes objects in this plan.
- **Object encryption:** each object is sealed whole with the tenant's payload key, using AAD `tenant + "\x00" + objectName`.
- **`cold_until`** is a UTC day boundary in ms. It starts at the minimum int64. Every hot row normally has `occurred_at_ms >= cold_until`, and a hot row older than it exists only while the tenant is dirty.
- **Deduplication covers both tiers:** the hot primary key, plus, for an event older than `cold_until`, a lookup in that day's bucket.
- **Flush parameters:** watermark rank 100, margin 96 hours, interval 5 minutes. All three are configurable, and tests and e2e use shorter values.

## Review Focus

1. A customer whose events span cold buckets, hot rows and SKUs shared with other customers is erased. The resulting state must equal `reducer.fold` over the remaining events. Tests: Task 1 `TestRemoveCustomerMatchesFoldWithoutThem`, Task 7 `TestEraseCustomerAcrossTiers`.
2. An ingest for the day being flushed commits between the flush's read and its commit. The event must not be lost, and the tenant becomes dirty. Test: Task 5 `TestFlushKeepsRowInsertedDuringFlush`.
3. A redelivery of an event that is already in cold must count once. Test: Task 4 `TestIngestDedupesAgainstColdBucket`.
4. Range pages cross the cold/hot boundary, including late hot rows that are older than `cold_until`. Pages must not repeat or skip events. Test: Task 6 `TestRangeAcrossTiers`.
5. A tenant with cold data is erased. Reads give `410`, no cold index rows remain, and a restart never re-creates its key. Test: Task 7 `TestEraseTenantWithColdData`.

---

### Task 1: Fold snapshot, per-SKU inventory moves and customer removal

**Files:**
- Modify: `part2/backbone/internal/fold/fold.go`
- Create: `part2/backbone/internal/fold/snapshot.go`, `part2/backbone/internal/fold/snapshot_test.go`

**Interfaces:**
- Consumes: Plan 1's `fold.State`, `Apply`, `Result`, `Fold` and `canon.Event`.
- Produces (all pure, no I/O):
  - `fold.Day(ms int64) int64` returns the UTC day number, `floor(ms / 86_400_000)`.
  - `fold.Snapshot` is exported with JSON tags:
    - `EventCount int64 "event_count"`
    - `Customers []string "customers"`: sorted customer keys
    - `Orders map[string]fold.OrderState "orders"`
    - `Inventory map[string]int64 "inventory"`
    - `Oversold map[string]int64 "oversold"`: keyed by SKU
    - `Messages map[string]int64 "messages_by_channel"`
    - `LastMessageByDay map[int64]int64 "last_message_by_day"`
    - `Campaigns map[string]fold.Campaign "campaigns"`
    - `OrphanRefunds int64 "orphan_refunds"`, `OrphanShipments int64 "orphan_shipments"`
  - `fold.OrderState{Gross, Refunded int64; Status string}` with JSON tags `gross`, `refunded`, `status`.
  - `(*State) Snapshot() fold.Snapshot` does not mutate the state. Its maps are never nil.
  - `fold.Restore(tenantID string, customerKey func(string) string, snap fold.Snapshot) *fold.State`.
  - `fold.Move{SKU string; Kind string; Amount int64; LineNo int}` is one inventory movement. `Kind` is `"adjust"` (an `inventory.adjusted` delta, with `LineNo` 0) or `"order"` (one line of a winning `order.created`, where `Amount` is the qty and `LineNo` is the line's index).
  - `(*State) ApplyMoves(e canon.Event) []fold.Move` is `Apply` that also returns the movements it applied, in application order. `Apply` becomes `ApplyMoves` with the result discarded.
  - `fold.RefoldSKU(moves []fold.Move) (stock, oversold int64)` replays one SKU's movements from zero, with the reducer's clamp rules.
  - `fold.RemoveCustomer(snap fold.Snapshot, customerKey string, removed []canon.Event, skuMoves map[string][]fold.Move, dayMax map[int64]*int64) fold.Snapshot` returns the snapshot of the snapshotted events minus `removed`. The arguments:
    - `removed` is every snapshotted event of one customer.
    - `skuMoves[sku]` holds the remaining movements, in key order, for every SKU that `AffectedSKUs(removed)` names.
    - `dayMax[day]` is the latest remaining `message.received` time on each day that `AffectedDays(removed)` names, or nil if that day has none left.
  - `fold.AffectedSKUs(removed []canon.Event) []string` and `fold.AffectedDays(removed []canon.Event) []int64` return sorted lists.

**Rules:**
- The state now keeps oversold per SKU (the `oversold_units` result is the sum) and the latest message time per day (`last_contact_ms` is the maximum over days). `Result()` output does not change.
- `RemoveCustomer` folds `removed` alone into a fresh state, x, and then applies these steps to the snapshot:
  1. Subtract x's event count, orphan counts, message counts and campaign sums.
  2. Delete every order in x's orders. Orders never mix customers (spec §18).
  3. Remove `customerKey` from the customer list.
  4. Set each affected day from `dayMax`, deleting the day when it is nil.
  5. Set each affected SKU from `RefoldSKU(skuMoves[sku])`, deleting the SKU from both maps when it has no moves.
  6. Drop any channel whose count reaches 0.
  7. Keep every campaign key, even after subtracting x's sums. Canonical `ad.metric` events carry no customer, so x contributes to a campaign only through a cross-vendor event with a customer. Whether such a key would survive the removal is not tracked.

- [ ] **Step 1: Write the failing tests**

```go
func TestSnapshotRestoreRoundTrip(t *testing.T) {
	// For every reducer fixture (testdata/*.events.jsonl), sorted: for k in {0, n/2, n}:
	// s := New(tid, identity); apply events[:k]; b, _ := json.Marshal(s.Snapshot()); var snap Snapshot; json.Unmarshal(b, &snap)
	// r := Restore(tid, identity, snap); apply events[k:] to r; jsonEqual(r.Result(), Fold(tid, events, identity))
}

func TestApplyMovesMatchesRefold(t *testing.T) {
	// For every fixture: collect ApplyMoves over all events, grouped by SKU in order;
	// for each SKU, RefoldSKU(moves) == (Result().Inventory[sku], that SKU's oversold from Snapshot().Oversold)
}

func TestRemoveCustomerMatchesFoldWithoutThem(t *testing.T) {
	// For the fixtures t_0016 and t_0018 and for 5 customers each (the 5 with the most events):
	// all := sorted events; removed := events of that customer; rest := all minus removed
	// snap := snapshot of folding all; moves := for each SKU in AffectedSKUs(removed), the ApplyMoves of folding rest, grouped by SKU
	// dayMax := for each day in AffectedDays(removed), the max occurred_at of message.received in rest that day (nil if none)
	// got := Restore(tid, identity, RemoveCustomer(snap, customerID, removed, moves, dayMax)).Result()
	// jsonEqual(got, Fold(tid, rest, identity))
}

func TestDayFloors(t *testing.T) // Day(0)==0, Day(86_399_999)==0, Day(86_400_000)==1, Day(-1)==-1
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `cd part2/backbone && go test ./internal/fold/...`
Expected: FAIL (undefined `Snapshot`, `Restore`, `ApplyMoves` and the rest).

- [ ] **Step 3: Implement the API above in `fold.go` and `snapshot.go`**

- [ ] **Step 4: Run the tests and see them pass**

Run: `cd part2/backbone && go test -count=1 ./internal/fold/...`
Expected: PASS, including every Plan 1 fold test unchanged.

- [ ] **Step 5: Commit**

```bash
git add part2/backbone/internal/fold
git commit -m "Add fold snapshots, per-SKU moves and customer removal"
```

### Task 2: MinIO client, configuration and test services

**Files:**
- Create: `part2/backbone/internal/cold/cold.go`, `cold_test.go`, `part2/backbone/internal/cold/coldtest/coldtest.go`
- Modify: `part2/backbone/internal/config/config.go`, `config_test.go`, `part2/docker-compose.yml`, `part2/backbone/go.mod`, `go.sum`

**Interfaces:**
- Produces:
  - `cold.Config{Endpoint, AccessKey, SecretKey, Bucket string}`.
  - `cold.Open(ctx context.Context, cfg cold.Config) (*cold.Client, error)` connects and creates the bucket if it is missing. Concurrent creation by two nodes must both succeed.
  - `(*Client) Put(ctx, name string, data []byte) error`.
  - `(*Client) Get(ctx, name string) ([]byte, error)`, which returns `cold.ErrNotFound` for a missing object.
  - `cold.ObjectName(tenantID, kind string, day int64) string` returns:
    - for `kind == "bucket"`: `<tenant>/buckets/<YYYY-MM-DD>/<32 hex>.jsonl.enc`;
    - for `kind == "snapshot"`: `<tenant>/snapshot/<32 hex>.json.enc` (`day` is ignored);
    - the hex part comes from 16 bytes of `crypto/rand`.
  - `coldtest.New(t *testing.T) *cold.Client` skips unless `BACKBONE_TEST_MINIO_ENDPOINT` and `BACKBONE_TEST_SECRETS_DIR` are set. It reads `minio_user` and `minio_password` from that directory and uses a fresh random bucket per test.
  - New config variables:
    - `BACKBONE_MINIO_ENDPOINT` (required);
    - `BACKBONE_MINIO_BUCKET` (default `backbone`);
    - `BACKBONE_MINIO_USER_FILE` and `BACKBONE_MINIO_PASSWORD_FILE` (both required; the files hold the credentials);
    - `BACKBONE_FLUSH_INTERVAL` (default `5m`), `BACKBONE_FLUSH_MARGIN` (default `96h`), `BACKBONE_WATERMARK_RANK` (default `100`).
    - Durations use `time.ParseDuration`. They are fields `MinioEndpoint, MinioBucket, MinioUserFile, MinioPasswordFile string; FlushInterval, FlushMargin time.Duration; WatermarkRank int`.

**Compose changes** (Designer's call: credentials stay out of files in git, and host-side tests can read them):
- Rename `kek-init` to `secrets-init`. On first start it writes `kek` (32 random bytes), `minio_user` and `minio_password` (random hex) into the bind mount `./out/secrets`, which `.gitignore` already covers through `part2/out/`. It never overwrites an existing file.
- Add a `minio` service:
  - Pin a `minio/minio` image tag that pulls, and record it.
  - Run `server /data` with the volume `miniodata`.
  - Read the root credentials from the secrets files; no credential value appears in the compose file.
  - Map port `127.0.0.1:59000:9000` and add a health check.
- The api services mount `./out/secrets:/secrets:ro`, get the new environment variables (endpoint `minio:9000`), and depend on `minio` being healthy.

- [ ] **Step 1: Write the failing tests**

```go
func TestLoadMinioAndFlushDefaults(t *testing.T) // required minio vars reported when missing; defaults: bucket "backbone", 5m, 96h, rank 100
func TestPutGetRoundTrip(t *testing.T)  // coldtest.New; Put("t_1/x", b) then Get == b; Get("t_1/missing") is ErrNotFound
func TestOpenTwiceSameBucket(t *testing.T) // two concurrent cold.Open on one bucket name both succeed
func TestObjectNameShape(t *testing.T) {
	// ObjectName("t_1","bucket", Day(1782864607912)) matches `^t_1/buckets/2026-07-01/[0-9a-f]{32}\.jsonl\.enc$`;
	// "snapshot" matches `^t_1/snapshot/[0-9a-f]{32}\.json\.enc$`; two calls never return the same name
}
```

- [ ] **Step 2: Start the services and see the tests fail**

Run: `TENANTS_FILE=$INFRA/data/tenants.json docker compose -f part2/docker-compose.yml up -d --wait postgres minio && cd part2/backbone && BACKBONE_TEST_MINIO_ENDPOINT=127.0.0.1:59000 BACKBONE_TEST_SECRETS_DIR=$PWD/../out/secrets go test ./internal/cold/... ./internal/config/...`
Expected: FAIL.

- [ ] **Step 3: Implement `cold`, `coldtest`, the config fields and the compose changes**

- [ ] **Step 4: Run the tests and see them pass**

Run: the same command as step 2.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add part2/backbone/internal/cold part2/backbone/internal/config part2/backbone/go.mod part2/backbone/go.sum part2/docker-compose.yml
git commit -m "Add MinIO client, cold-tier configuration and compose service"
```

### Task 3: Store wiring, cold schema and object codec

**Files:**
- Modify: `part2/backbone/internal/store/schema.sql`, `store.go`, `tenants.go`, `part2/backbone/internal/store/storetest/storetest.go`, `part2/backbone/cmd/api/main.go`
- Create: `part2/backbone/internal/store/objects.go`, `objects_test.go`

**Interfaces:**
- Consumes: `cold.Client`, `cold.ObjectName`, `fold.Snapshot`, `crypto.TenantKeys.Seal` and `Open`.
- Produces:
  - `store.Open(ctx, databaseURL string, kek *crypto.KEK, objects *cold.Client) (*store.Store, error)`. This is a signature change, and `main.go` builds the cold client from config.
  - `storetest.New` and `Reopen` also call `coldtest.New` (Reopen shares the same client) and skip unless both test databases are configured.
  - Internal helpers used by Tasks 4 to 7, in `objects.go`:
    - `(*Store) putBucket(ctx, sc Scope, day int64, events []canon.Event) (name string, err error)`
    - `(*Store) getBucket(ctx, sc Scope, name string) ([]canon.Event, error)`
    - `(*Store) putSnapshot(ctx, sc Scope, coldUntil int64, snap fold.Snapshot) (string, error)`
    - `(*Store) getSnapshot(ctx, sc Scope, name string) (fold.Snapshot, error)`
  - Bucket objects are JSON lines of canonical events in key order. Snapshot objects are `{"version":"v1","cold_until":<ms>,"state":<fold.Snapshot>}`. Both are sealed with AAD `tenant + "\x00" + name`.

Schema additions (append to `schema.sql`):

```sql
CREATE TABLE IF NOT EXISTS tenant_cold (
  tenant_id       text PRIMARY KEY REFERENCES tenants,
  cold_until      bigint NOT NULL DEFAULT (-9223372036854775807 - 1),
  snapshot_object text,
  reducer_version text NOT NULL DEFAULT 'v1',
  dirty           boolean NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS cold_manifest (
  tenant_id text NOT NULL,
  day       bigint NOT NULL,
  object    text NOT NULL,
  events    integer NOT NULL,
  bytes     integer NOT NULL,
  PRIMARY KEY (tenant_id, day)
);
CREATE TABLE IF NOT EXISTS garbage (
  object      text PRIMARY KEY,
  tenant_id   text NOT NULL,
  replaced_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS customer_days (
  tenant_id    text NOT NULL,
  customer_key bytea NOT NULL,
  day          bigint NOT NULL,
  PRIMARY KEY (tenant_id, customer_key, day)
);
CREATE TABLE IF NOT EXISTS sku_moves (
  tenant_id      text NOT NULL,
  sku_key        bytea NOT NULL,
  occurred_at_ms bigint NOT NULL,
  event_id       text COLLATE "C" NOT NULL,
  line_no        integer NOT NULL,
  value          bytea NOT NULL,
  PRIMARY KEY (tenant_id, sku_key, occurred_at_ms, event_id, line_no)
);
ALTER TABLE sku_moves ALTER COLUMN value SET STATISTICS 0;
CREATE INDEX IF NOT EXISTS sku_moves_event ON sku_moves (tenant_id, event_id);
```

`EnsureTenants` also inserts the tenant's `tenant_cold` row (`ON CONFLICT DO NOTHING`) in its per-tenant transaction. The `sku_moves.value` column holds the sealed JSON `{"sku":…,"kind":…,"amount":…}` with AAD `tenant + "\x00" + event_id + "\x00" + line_no`.

- [ ] **Step 1: Write the failing tests**

```go
func TestBucketObjectRoundTrip(t *testing.T) // putBucket 3 events then getBucket returns them in key order, JSON-equal
func TestObjectsAreSealedPerTenant(t *testing.T) {
	// raw cold.Client.Get(name) contains no event_id and no email; getBucket with another tenant's scope fails
}
func TestSnapshotObjectRoundTrip(t *testing.T) // putSnapshot then getSnapshot JSON-equal; version "v1" and cold_until kept
func TestEnsureTenantsCreatesColdRow(t *testing.T) // tenant_cold row exists with cold_until = math.MinInt64, dirty false
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `cd part2/backbone && BACKBONE_TEST_DATABASE_URL='postgres://postgres@127.0.0.1:55432/postgres?sslmode=disable' BACKBONE_TEST_MINIO_ENDPOINT=127.0.0.1:59000 BACKBONE_TEST_SECRETS_DIR=$PWD/../out/secrets go test ./internal/store/...`
Expected: FAIL.

- [ ] **Step 3: Implement the wiring, schema, helpers and the `main.go` change**

- [ ] **Step 4: Run the tests and see them pass**

Run: the same command as step 2, plus `go test ./...`.
Expected: PASS. Every Plan 1 store and api test passes unchanged, apart from the new `Open` signature.

- [ ] **Step 5: Commit**

```bash
git add part2/backbone
git commit -m "Wire the cold client into the store with schema and object codec"
```

### Task 4: Ingest with the cold-commit lock and late events

**Files:**
- Modify: `part2/backbone/internal/store/events.go`
- Test: `part2/backbone/internal/store/late_test.go`

**Interfaces:**
- Consumes: the Task 3 helpers and `fold.Day`.
- Produces: unchanged `Ingest` signature and results. Internally:
  - After the customer step, take `pg_advisory_xact_lock_shared(lockKey("cold-commit", tenant))`.
  - Read `cold_until` and `dirty` from `tenant_cold`.
  - If `ev.OccurredAtMs >= cold_until`, insert as before.
  - Otherwise the event is late:
    - If the `cold_manifest` row for `fold.Day(ev.OccurredAtMs)` exists and its bucket holds `ev.EventID`, return `Duplicate`.
    - Otherwise insert into `hot_events` (the primary key still dedupes against hot) and, when a row was inserted, `UPDATE tenant_cold SET dirty = true` in the same transaction.

- [ ] **Step 1: Write the failing tests**

Use an unexported test hook (`export_test.go`) to set `cold_until` and write a manifest row with `putBucket`, so these tests do not need Task 5's flush.

```go
func TestIngestDedupesAgainstColdBucket(t *testing.T) {
	// bucket for day D holds event e; cold_until = (D+1) days; Ingest(e) -> Duplicate; hot_events count 0; dirty false
}
func TestLateEventMarksDirty(t *testing.T) {
	// cold_until = (D+1) days; Ingest(new event on day D) -> Stored; row in hot_events; tenant_cold.dirty == true
}
func TestOnTimeEventDoesNotMarkDirty(t *testing.T) // event at cold_until exactly -> Stored, dirty false
```

- [ ] **Step 2: Run the tests and see them fail**

Run: the Task 3 command.
Expected: FAIL.

- [ ] **Step 3: Implement the late path in `Ingest`**

- [ ] **Step 4: Run the tests and see them pass**

Run: the Task 3 command, plus `go test ./...`.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add part2/backbone/internal/store
git commit -m "Take the cold-commit lock on ingest and handle late events"
```

### Task 5: Flush one tenant-day

**Files:**
- Create: `part2/backbone/internal/store/flush.go`, `flush_test.go`

**Interfaces:**
- Consumes: the Task 1 fold API and the Task 3 helpers.
- Produces: `(*Store) FlushDay(ctx context.Context, tenantID string, margin time.Duration, rank int) (bool, error)`. It flushes at most one day and reports whether it did. The worker calls it until it returns false.

**Algorithm (spec §10), in one `READ COMMITTED` transaction:**
1. Take `pg_advisory_xact_lock(lockKey("cold-writer", tenant))`. Return false if the tenant is erased or `tenant_cold.dirty` is set.
2. Compute the watermark: `W = (rank-th largest hot occurred_at_ms, or the largest if fewer rows) − margin`. Let `d` be the day of the earliest hot row at or after `cold_until`. Return false if there is no such row or if `W < (d+1)·86 400 000`.
3. Read the hot rows of day `d` in key order and keep their event IDs. Restore the current snapshot (or start a new state), apply them with `ApplyMoves`, and collect the `sku_moves` rows and the distinct `customer_days` keys.
4. Write the bucket with `putBucket` and the new snapshot with `putSnapshot`, using `cold_until = (d+1)` days.
5. Take `pg_advisory_xact_lock_shared(lockKey("tenant-status", tenant))` and `pg_advisory_xact_lock(lockKey("cold-commit", tenant))`. Then:
   - insert the `cold_manifest` row;
   - update `tenant_cold` (`cold_until`, `snapshot_object`);
   - insert the old snapshot object, if any, into `garbage`;
   - insert the `customer_days` rows (`ON CONFLICT DO NOTHING`) and the `sku_moves` rows;
   - run `DELETE FROM hot_events WHERE tenant_id = $1 AND event_id = ANY($2)` with exactly the IDs read in step 3;
   - set `dirty = true` if any hot row now has `occurred_at_ms < cold_until`;
   - commit, and return true.

- [ ] **Step 1: Write the failing tests**

An unexported hook `flushAfterRead func()` (set only from `export_test.go`) runs between steps 3 and 4.

```go
func TestFlushMovesOneDay(t *testing.T) {
	// ingest events on days D, D+1 and D+6 (rank 1, margin 96h, so W = (D+2) days + the last event's offset):
	// FlushDay -> true (day D in cold_manifest, its rows gone from hot, cold_until = D+1 days);
	// second call -> true (day D+1); third call -> false (day D+6 needs W >= D+7 days)
}
func TestFlushedStateEqualsFold(t *testing.T) {
	// load a reducer fixture (t_0018) through Ingest, flush until false with margin 0 and rank 1:
	// restore the stored snapshot, fold the remaining hot rows, compare with fold.Fold of the fixture
}
func TestFlushWritesIndexRows(t *testing.T) {
	// after a flush: customer_days has one row per (customer, day); sku_moves has one row per inventory movement of that day,
	// and the decrypted values equal ApplyMoves of the day
}
func TestFlushKeepsRowInsertedDuringFlush(t *testing.T) {
	// set flushAfterRead to Ingest one more event on day D; FlushDay -> true; that event is still in hot_events;
	// tenant_cold.dirty == true
}
func TestFlushSkipsDirtyTenant(t *testing.T) // dirty=true -> FlushDay false, nothing written
```

- [ ] **Step 2: Run the tests and see them fail**

Run: the Task 3 command.
Expected: FAIL.

- [ ] **Step 3: Implement `FlushDay`**

- [ ] **Step 4: Run the tests and see them pass**

Run: the Task 3 command with `-race`.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add part2/backbone/internal/store
git commit -m "Flush one tenant-day into a cold bucket and snapshot"
```

### Task 6: State and range reads across tiers

**Files:**
- Create: `part2/backbone/internal/store/reads.go`, `reads_test.go`
- Modify: `part2/backbone/internal/store/events.go` (`Range` moves to `reads.go`), `part2/backbone/internal/api/reads.go`, `api_test.go`

**Interfaces:**
- Produces:
  - `(*Store) State(ctx, sc Scope) (fold.Result, error)` runs one `REPEATABLE READ READ ONLY` transaction:
    - status first (erased gives `ErrTenantErased`), then `tenant_cold`;
    - not dirty: restore the snapshot (or a new state) and apply the hot rows in key order;
    - dirty: fold every manifest bucket and every hot row with `fold.Fold`.
  - `(*Store) Range(...)` keeps Plan 1's signature and runs in the same kind of transaction. It merges two streams in key order:
    - cold events from manifest buckets whose day overlaps `[fromMs, toMs)` and lies before `cold_until`, read in day order and stopping once `limit` cold events past `after` are collected;
    - hot rows in the range past `after` (`LIMIT limit`).

    It returns the first `limit` events of the merge.
  - The api state handler calls `State`. Both read handlers run under `context.WithTimeout(r.Context(), 60*time.Second)`.
  - `ScanAll` stays (hot only) for tests.

- [ ] **Step 1: Write the failing tests**

```go
func TestStateAcrossTiers(t *testing.T) // fixture t_0016 ingested, half flushed: State == fold.Fold(all events)
func TestStateDirtyUsesFullFold(t *testing.T) // after a late event: State == fold.Fold(all events including the late one)
func TestRangeAcrossTiers(t *testing.T) {
	// fixture ingested, days partly flushed, plus one late hot row older than cold_until:
	// page through [min, max+1) with limit 7: concatenated IDs == canon order of all events, no repeats
}
func TestRangeColdOnlyWindow(t *testing.T) // a window fully inside flushed days returns exactly those events
```

Also update `TestStateEndpoint` to run with a flush in the middle.

- [ ] **Step 2: Run the tests and see them fail**

Run: the Task 3 command, plus `./internal/api/...`.
Expected: FAIL.

- [ ] **Step 3: Implement `State`, the merged `Range` and the handler change**

- [ ] **Step 4: Run the tests and see them pass**

Run: the same command.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add part2/backbone/internal/store part2/backbone/internal/api
git commit -m "Read state and ranges across the cold and hot tiers"
```

### Task 7: Erasure across tiers

**Files:**
- Modify: `part2/backbone/internal/store/erase.go`
- Test: `part2/backbone/internal/store/erase_cold_test.go`

**Interfaces:**
- Produces: unchanged signatures.
  - **`EraseCustomer` (spec §11.1).** Transaction 1 (the tombstone) is unchanged. Transaction 2 becomes:
    1. Take the cold-writer lock. If the tenant is erased, mark the tombstone done.
    2. Read the customer's days from `customer_days`.
    3. For each day, read the bucket and split out the customer's events (match by `CustomerKey(customer_id)`). Write the remaining events as a new bucket, or plan to delete the manifest row if nothing remains. Record that day's remaining latest message time.
    4. For each SKU in `fold.AffectedSKUs(removed)`, read the remaining `sku_moves` rows for `SKUKey(sku)` in key order, skipping the removed event IDs, and decrypt them into `fold.Move`s.
    5. Build `fold.RemoveCustomer(snapshot, customerKeyHex, removed, moves, dayMax)` and write it as a new snapshot.
    6. Take tenant-status shared and cold-commit exclusive. Then:
       - update or delete the manifest rows and put the replaced objects into `garbage`;
       - point `tenant_cold.snapshot_object` at the new snapshot;
       - delete the customer's hot rows, their `customer_days` rows, and the removed events' `sku_moves` rows;
       - mark the tombstone done, and commit.
  - **`EraseTenant`.** First take the cold-writer lock, then tenant-status exclusive, in the same transaction. It also deletes the tenant's `tenant_cold`, `cold_manifest`, `customer_days` and `sku_moves` rows. Objects stay in MinIO until sweep (Plan 3), unreadable because the DEK is gone.

- [ ] **Step 1: Write the failing tests**

```go
func TestEraseCustomerAcrossTiers(t *testing.T) {
	// fixture t_0018 ingested; flush half the days; pick the customer with the most events that has events in cold and hot
	// and shares a SKU with another customer; EraseCustomer: State == fold.Fold(fixture minus that customer's events);
	// the customer's rows are gone from hot_events, customer_days and sku_moves; the replaced objects are in garbage
}
func TestEraseCustomerOnlyInCold(t *testing.T) // all of the customer's events flushed: same equality check
func TestEraseCustomerEmptiesADay(t *testing.T) // a day holding only that customer's events loses its manifest row
func TestEraseTenantWithColdData(t *testing.T) {
	// after flushes: EraseTenant -> State is ErrTenantErased; tenant_cold, cold_manifest, customer_days, sku_moves rows for it == 0;
	// Reopen + EnsureTenants creates no key and no tenant_cold row
}
```

- [ ] **Step 2: Run the tests and see them fail**

Run: the Task 3 command with `-race`.
Expected: FAIL.

- [ ] **Step 3: Implement the cross-tier erasure**

- [ ] **Step 4: Run the tests and see them pass**

Run: the same command, plus `go test ./...`.
Expected: PASS, including Plan 1's erasure tests.

- [ ] **Step 5: Commit**

```bash
git add part2/backbone/internal/store
git commit -m "Erase customers and tenants across both tiers"
```

### Task 8: Worker, compose and end-to-end with the cold tier

**Files:**
- Create: `part2/backbone/cmd/worker/main.go`, `part2/scripts/tier-stats.sh`
- Modify: `part2/backbone/Dockerfile` (build both binaries), `part2/docker-compose.yml` (add `worker`), `part2/scripts/e2e.sh`, `part2/README.md`

**Interfaces:**
- **Worker:** it loads config, the tenants registry, the KEK, the cold client and the store, then runs `Migrate` and `EnsureTenants`. Every `FlushInterval` it calls `FlushDay(tenant, FlushMargin, WatermarkRank)` for each registry tenant until it returns false. It logs, per tick, the number of days flushed and the tick duration (no tenant data). It shuts down gracefully on SIGTERM.
- **Compose:** a `worker` service with the same image, environment and mounts as the api nodes, plus `BACKBONE_FLUSH_INTERVAL=${FLUSH_INTERVAL:-5m}`. It depends on Postgres, MinIO and secrets-init, and uses `restart: unless-stopped`.
- **`e2e.sh`:** it exports `FLUSH_INTERVAL=${FLUSH_INTERVAL:-2s}` before `up`, runs replay and verify, then `tier-stats.sh`. It still exits with `verify.py`'s code.
- **`tier-stats.sh`:** it prints `hot=<rows in hot_events> cold=<sum of cold_manifest.events> dirty=<tenants with dirty>`, via `docker compose exec -T postgres psql`.

- [ ] **Step 1: Write the worker, compose service, scripts and README changes**

- [ ] **Step 2: Run the supplied data end to end**

Run: `INFRA=$INFRA part2/scripts/e2e.sh "$INFRA/data"`
Expected:
- `verify.py` prints state 200/200, isolation 0, ranges 48/48 and `PASS`.
- `tier-stats.sh` shows `cold` greater than `hot` and `dirty=0`.

- [ ] **Step 3: Run two fresh seeds end to end**

Run: `python3 "$INFRA/generate.py" --seed 7 --out /tmp/backbone-seed7`, then `e2e.sh` on it. Repeat with `--seed 42`.
Expected: `PASS` for both, with `cold > hot`.

- [ ] **Step 4: Check that no customer ID or path reached the logs**

Run: `TENANTS_FILE=$INFRA/data/tenants.json docker compose -f part2/docker-compose.yml logs | grep -c 'cus_'`
Expected: `0`.

- [ ] **Step 5: Commit**

```bash
git add part2/backbone/cmd part2/backbone/Dockerfile part2/docker-compose.yml part2/scripts part2/README.md
git commit -m "Add the flush worker and run end to end with the cold tier"
```

---

## Outcome and follow-ups (added after execution, 2026-11-11)

**Result.** All eight tasks are done and reviewed, and the whole-branch review found no Critical issue. End-to-end on the supplied data at the final commit:

| Flush margin | Result | Tiers | Dirty tenants |
|---|---|---|---|
| 96 h (default) | `PASS`: state 200/200, isolation 0 leaks, ranges 48/48 | hot 33,673, cold 64,115 | 0 |
| 1 h (stress) | `PASS` | hot 57,588, cold 40,200 | 4 (the full-fold read path ran) |

Seeds 7 and 42 also passed with the default margin and cold larger than hot. No `cus_` appears in any container log.

**Deviations from this plan.**
- The official `minio/minio` images did not pull. Compose uses `bitnamilegacy/minio:2025.7.23-debian-12-r5`, an unmaintained image that runs as root.
- `EnsureTenants` creates `tenant_cold` only for active tenants.
- The flush test that erases a tenant mid-flush marks it erased with SQL, because `EraseTenant` now takes the cold-writer lock.
- `cold_manifest.bytes` records the sealed size.
- The configuration rejects a non-positive flush interval, a watermark rank below 1 and a negative margin.
- `e2e.sh` creates `part2/out/secrets` as the user before starting compose.
- The README tells users to run `down -v` when upgrading from Plan 1's stack, because the KEK moved.

**Follow-ups for Plan 3 or later.**
1. **Rebuild dirty tenants.** Until then a dirty tenant stops flushing and every read folds everything.
2. **Sweep.** Delete the objects recorded in `garbage` and any unreferenced objects, run `VACUUM`, `pg_switch_wal()` and `CHECKPOINT`, and finish pending tombstones. Until this exists, an erased customer's old buckets stay in MinIO, readable with the live tenant DEK, so the 2-hour physical-removal bound is not yet met.
3. A late ingest reads its day's bucket from MinIO while holding the shared locks, which can delay other ingests behind a queued commit. Revisit with metrics.
4. Measure `EraseCustomer` for the heaviest customer of the largest tenant on large data against the 10-second replay timeout.
5. Snapshot cache, metrics, runbook and the crash test (spec §16).
