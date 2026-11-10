# Part 2 Plan 3: Rebuild and Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put dirty tenants back on the fast path by rebuilding their cold data, and make erased data physically disappear within the stated bound. The bound needs four things: deleting replaced and orphaned objects and erased tenants' prefixes, finishing erasures whose request died, and running `VACUUM`, `pg_switch_wal()` and `CHECKPOINT`.

**Architecture:** Both jobs run in the existing worker and take the tenant's cold-writer lock, like flush and erasure.
- **Rebuild** moves the late hot rows into their day buckets and recomputes the snapshot and the tenant's `customer_days` and `sku_moves` rows from every bucket. It commits in one transaction.
- **Sweep** runs per tenant. It finishes pending tombstones, deletes `garbage` objects past their grace period, and deletes objects that no pointer references. Erased tenants lose their whole prefix. After all tenants it runs the Postgres maintenance step once.

**Tech Stack:** Go 1.24, pgx v5.7.6, minio-go v7.0.97, Postgres 17, the `bitnamilegacy/minio` image already in compose.

**Spec:** `docs/superpowers/specs/2026-11-10-part2-brand-data-backbone-design.md`, §12 (rebuild) and §14 (sweep and the bound), with §11.1 for finishing erasures and §13 for locks. This plan builds on Plans 1 and 2, both on `main`.

**Not in this plan:** the snapshot cache, Prometheus metrics, the runbook, measurements, and the crash test.

**Branch:** `part2-plan3-rebuild-sweep`, cut from `main`.

## Global Constraints

- All of Plan 1's and Plan 2's Global Constraints still hold, including the lock order: 1 cold-writer, 2 tenant-status, 3 customer, 4 cold-commit. Each is a Postgres advisory lock built with `lockKey(kind, []byte(tenant)[, customerKey])`.
- **Never run `go mod tidy`**: it bumps `go.mod` to Go 1.25. Add dependencies with `go get module@version`.
- **Rebuild and sweep work on one tenant at a time, holding the cold-writer lock** (`pg_advisory_xact_lock(lockKey("cold-writer", []byte(tenant)))`) for the whole tenant step. Rebuild's commit also takes tenant-status shared and cold-commit exclusive, then re-checks the status, exactly as flush does.
- **Objects stay immutable.** Rebuild writes new objects and records the replaced ones in `garbage` in its commit transaction. Sweep is the only code that deletes objects. Deleting is idempotent: a missing object counts as deleted.
- **Grace period:** a `garbage` object is deleted only once `replaced_at < now() − grace`. The default grace is 10 minutes. Reads have a 60-second deadline. An object that nothing references and that is not in `garbage` is a leftover of a crashed operation, and sweep deletes it immediately, because it holds the tenant's cold-writer lock.
- **A tenant's prefix is `<tenant>/` with the trailing slash**, so `t_1/` never matches `t_10/…`. Object names come from `cold.ObjectName`: `<tenant>/snapshot/<id>.json.enc` and `<tenant>/buckets/<YYYY-MM-DD>/<id>.jsonl.enc`.
- **Postgres maintenance** runs once per sweep, outside any transaction:
  - `VACUUM` on `hot_events`, `customer_days`, `sku_moves`, `tenant_keys` and `tombstones`;
  - then `SELECT pg_switch_wal()`;
  - then `CHECKPOINT`.

  The compose Postgres runs with `wal_recycle=off`.
- **Defaults:** sweep interval 1 hour (must be positive), garbage grace 10 minutes (must be 0 or more; tests and e2e use short values).
- **Stated bound** (spec §14): 2 hours, assuming the worker runs. The worker logs the duration of each completed sweep.

## Review Focus

1. A late event arrives while a rebuild of the same tenant runs. It must not be lost, and the tenant stays dirty until a later rebuild. Test: Task 2 `TestRebuildKeepsLateRowArrivingDuringRebuild`.
2. A customer erasure whose request died after the tombstone committed must still finish, and the customer must be gone from state and from every current object. Test: Task 3 `TestSweepFinishesPendingTombstone`.
3. An erased customer's old bucket objects must be gone from MinIO after one sweep past the grace period. Test: Task 3 `TestSweepDeletesErasedCustomerObjects`.
4. A sweep must never delete an object a current pointer references, including right after a flush or a rebuild. Test: Task 3 `TestSweepKeepsReferencedObjects`.
5. After a rebuild, erasing a customer must still give the reducer result, which shows the rebuilt index rows are complete. Test: Task 2 `TestEraseAfterRebuild`.

---

### Task 1: Erase a customer by key

**Files:**
- Modify: `part2/backbone/internal/store/erase.go`, `erase_cold_test.go`, `export_test.go`

**Interfaces:**
- Produces:
  - `(*Store) finishErasure(ctx context.Context, sc Scope, customerKey []byte) error` is the current second part of `EraseCustomer` (`eraseCustomerCold` and `planColdErase`), driven by the customer key instead of the ID.
    - Bucket events are matched by `ev.CustomerID != nil && bytes.Equal(sc.Keys().CustomerKey(*ev.CustomerID), customerKey)`.
    - `fold.RemoveCustomer` receives `hex.EncodeToString(customerKey)`, which equals `CustomerKeyHex(id)`.
  - `EraseCustomer(ctx, sc, customerID)` keeps its signature and calls `finishErasure(ctx, sc, sc.Keys().CustomerKey(customerID))`.
  - `export_test.go` exposes it as `FinishErasure`.
  - Sweep (Task 3) needs this function because a tombstone stores only the key.

- [ ] **Step 1: Write the failing test**

```go
func TestFinishErasureByKey(t *testing.T) {
	// fixture t_0018 ingested, half its days flushed; pick a customer with both cold and hot events;
	// insert its pending tombstone directly (as if EraseCustomer's first transaction committed and the request died);
	// FinishErasure(sc, CustomerKey(cus)) -> nil; State == fold.Fold(fixture minus cus); tombstone status done;
	// no customer_days row for the key; no hot row for the key
}
```

- [ ] **Step 2: Start the services and see the test fail**

Run: `mkdir -p part2/out/secrets && TENANTS_FILE=$INFRA/data/tenants.json docker compose -f part2/docker-compose.yml up -d --wait postgres minio && cd part2/backbone && BACKBONE_TEST_DATABASE_URL='postgres://postgres@127.0.0.1:55432/postgres?sslmode=disable' BACKBONE_TEST_MINIO_ENDPOINT=127.0.0.1:59000 BACKBONE_TEST_SECRETS_DIR=$PWD/../out/secrets go test ./internal/store/...`
Expected: FAIL (undefined `FinishErasure`).

- [ ] **Step 3: Refactor the cold part of `EraseCustomer` into `finishErasure`, keyed by the customer key**

- [ ] **Step 4: Run the tests and see them pass**

Run: the same command as step 2, with `-race`.
Expected: PASS, including every existing erasure test.

- [ ] **Step 5: Commit**

```bash
git add part2/backbone/internal/store
git commit -m "Drive cross-tier customer erasure by the customer key"
```

### Task 2: Rebuild a dirty tenant

**Files:**
- Create: `part2/backbone/internal/store/rebuild.go`, `rebuild_test.go`
- Modify: `part2/backbone/internal/store/export_test.go`, and `flush.go` only to share its `sku_moves` and `customer_days` row building

**Interfaces:**
- Consumes: `putBucket` (it sorts with `canon.Sort`), `getBucket`, `putSnapshot`, `sealSKUMove`, `fold.New`, `fold.Day`, `(*fold.State).ApplyMoves` and `Snapshot`.
- Produces: `(*Store) Rebuild(ctx context.Context, tenantID string) (bool, error)`. It returns false without writing anything when the tenant is erased or not dirty.

**Algorithm (spec §12), in one `READ COMMITTED` transaction:**
1. Take the cold-writer lock. Read the status and `tenant_cold` (`cold_until`, `dirty`, `snapshot_object`). Return false if the tenant is erased or not dirty.
2. Read the hot rows with `occurred_at_ms < cold_until` and keep their event IDs. These are the late rows.
3. Group the late rows by `fold.Day`. For each day, take that day's existing bucket (if any) plus the late rows. Skip any late row whose event ID is already in the bucket. Write the merged events as a new bucket with `putBucket`.
4. Rebuild from every bucket, unchanged and new, in day order:
   - a fresh `fold.New(tenant, CustomerKeyHex)`;
   - `ApplyMoves` over each bucket's events, building every `sku_moves` row and every `customer_days` pair exactly as `FlushDay` builds them. Share one helper with `FlushDay` rather than copying its code.

   Then write the new snapshot with the unchanged `cold_until`. The hook `rebuildAfterRead`, unexported and set from `export_test.go` as `SetRebuildAfterRead`, runs here.
5. Take tenant-status shared and cold-commit exclusive. Re-check that the tenant is not erased; if it is, return false. Then:
   - upsert the manifest rows of the rewritten days, with real event counts and byte sizes;
   - insert the replaced bucket objects and the old snapshot into `garbage`;
   - point `tenant_cold.snapshot_object` at the new snapshot;
   - replace all the tenant's `customer_days` and `sku_moves` rows (delete, then insert; use `CopyFrom` for `sku_moves`);
   - delete exactly the hot rows read in step 2;
   - set `dirty = EXISTS (hot row with occurred_at_ms < cold_until)`;
   - commit, and return true.

- [ ] **Step 1: Write the failing tests**

```go
func TestRebuildClearsDirtyAndMatchesFold(t *testing.T) {
	// fixture t_0016 ingested; flush with rank 1, margin 0 until false; then ingest 3 late events dated in flushed days, one order-sensitive
	// (an inventory.adjusted that a later cold order.created consumes); dirty == true; Rebuild -> true;
	// dirty == false; no hot row older than cold_until; State == fold.Fold(all events); every late event is in its day's bucket
}
func TestRebuildIndexRowsMatchBuckets(t *testing.T) {
	// after Rebuild: customer_days == distinct (CustomerKey, day) over all bucket events;
	// decrypted sku_moves == ApplyMoves over all bucket events in canon.Sort order
}
func TestRebuildKeepsLateRowArrivingDuringRebuild(t *testing.T) {
	// SetRebuildAfterRead to Ingest another late event; Rebuild -> true; that event is still in hot_events and dirty == true;
	// a second Rebuild -> true and dirty == false; State == fold.Fold(all events)
}
func TestRebuildSkipsCleanTenant(t *testing.T) // dirty == false -> Rebuild false and no new garbage row
func TestEraseAfterRebuild(t *testing.T) {
	// the TestRebuildClearsDirtyAndMatchesFold setup and Rebuild, then EraseCustomer(the customer with the most events);
	// State == fold.Fold(all events minus that customer's)
}
func TestRedeliveryAfterRebuildIsDuplicate(t *testing.T) // Ingest one of the rebuilt late events again -> Duplicate
```

- [ ] **Step 2: Run the tests and see them fail**

Run: the Task 1 command.
Expected: FAIL.

- [ ] **Step 3: Implement `Rebuild`**

- [ ] **Step 4: Run the tests and see them pass**

Run: the Task 1 command, with `-race`.
Expected: PASS, including every existing flush test.

- [ ] **Step 5: Commit**

```bash
git add part2/backbone/internal/store
git commit -m "Rebuild dirty tenants from their cold buckets"
```

### Task 3: Sweep and Postgres maintenance

**Files:**
- Modify: `part2/backbone/internal/cold/cold.go`, `cold_test.go`, `part2/docker-compose.yml`
- Create: `part2/backbone/internal/store/sweep.go`, `sweep_test.go`

**Interfaces:**
- Consumes: `finishErasure` (Task 1).
- Produces:
  - `(*cold.Client) List(ctx context.Context, prefix string) ([]string, error)` returns every object name under the prefix, recursively and sorted.
  - `(*cold.Client) Delete(ctx context.Context, name string) error` returns nil when the object is already absent.
  - `(*Store) SweepTenant(ctx context.Context, tenantID string, grace time.Duration) (SweepResult, error)`.
  - `store.SweepResult{Tombstones, GarbageDeleted, OrphansDeleted int}`.
  - `(*Store) Maintain(ctx context.Context) error`.

**`SweepTenant` behavior:**
- **Erased tenant** (status `erased`): under the cold-writer lock, delete every object under `<tenant>/` and the tenant's `garbage` rows. Count the objects as `OrphansDeleted`.
- **Live tenant:** do these in order. Each part takes the cold-writer lock in its own transaction and reads the pointers only after taking it.
  1. For each `pending` tombstone, call `finishErasure` with its key.
  2. Delete the `garbage` objects whose `replaced_at < now() − grace`. Delete each object first, then its row.
  3. List `<tenant>/`. Delete every object that is not the current snapshot, not a manifest bucket, and not in `garbage`.

**`Maintain`:** run the maintenance statements from the Global Constraints on the pool, outside any transaction.

**Compose:** the `postgres` service adds `-c wal_recycle=off` to its existing `command:`.

- [ ] **Step 1: Write the failing tests**

```go
// internal/cold
func TestListAndDelete(t *testing.T) {
	// coldtest.New; Put "t_1/a", "t_1/b/c", "t_10/x"; List("t_1/") == ["t_1/a", "t_1/b/c"]
	// Delete("t_1/a") then List("t_1/") == ["t_1/b/c"]; Delete("t_1/a") again -> nil; Get("t_1/a") is ErrNotFound
}

// internal/store
func TestSweepFinishesPendingTombstone(t *testing.T) {
	// fixture t_0018, half flushed; insert a pending tombstone for a customer with cold and hot events;
	// SweepTenant -> Tombstones == 1; State == fold.Fold(fixture minus that customer); tombstone done
}
func TestSweepDeletesErasedCustomerObjects(t *testing.T) {
	// EraseCustomer on a customer with cold events; remember the replaced object names from garbage;
	// SweepTenant(grace 0) -> GarbageDeleted >= 1; Get on each replaced name is ErrNotFound; garbage has no rows for them
}
func TestSweepRespectsGrace(t *testing.T) // after an erasure, SweepTenant(grace 1h) -> GarbageDeleted == 0 and the garbage rows remain
func TestSweepDeletesOrphans(t *testing.T) {
	// Put cold.ObjectName(tenant, "bucket", someDay) with no pointer and no garbage row; SweepTenant -> OrphansDeleted == 1; Get is ErrNotFound
}
func TestSweepKeepsReferencedObjects(t *testing.T) {
	// after flushes and a rebuild: SweepTenant(grace 0); every manifest object and the snapshot object can still be read with
	// GetBucket/GetSnapshot; State unchanged
}
func TestSweepErasedTenantPrefix(t *testing.T) // after flushes, EraseTenant then SweepTenant -> List("<tenant>/") is empty; no garbage rows
func TestMaintainRuns(t *testing.T) // Maintain(ctx) == nil
```

- [ ] **Step 2: Run the tests and see them fail**

Run: the Task 1 command, with `./internal/cold/...` added.
Expected: FAIL.

- [ ] **Step 3: Implement `List`, `Delete`, `SweepTenant`, `Maintain` and the compose change**

- [ ] **Step 4: Run the tests and see them pass**

Run: recreate Postgres with the new command (`TENANTS_FILE=$INFRA/data/tenants.json docker compose -f part2/docker-compose.yml up -d --wait postgres minio`), check `docker compose … exec -T postgres psql -U postgres -tAc 'SHOW wal_recycle'` prints `off`, then the step 2 command with `-race`.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add part2/backbone/internal part2/docker-compose.yml
git commit -m "Sweep replaced and orphaned objects and finish pending erasures"
```

### Task 4: Worker schedule, configuration and end-to-end

**Files:**
- Modify: `part2/backbone/internal/config/config.go`, `config_test.go`, `part2/backbone/cmd/worker/main.go`, `part2/docker-compose.yml`, `part2/scripts/e2e.sh`, `part2/scripts/tier-stats.sh`, `part2/README.md`

**Interfaces:**
- **Config:**
  - `BACKBONE_SWEEP_INTERVAL` (default `1h`, must be positive) becomes the field `SweepInterval time.Duration`.
  - `BACKBONE_GARBAGE_GRACE` (default `10m`, must be 0 or more) becomes the field `GarbageGrace time.Duration`.
- **Worker:**
  - On each flush tick, for every registry tenant: call `Rebuild` (log when it returns true), then flush until false.
  - On a separate sweep ticker: `SweepTenant(tenant, GarbageGrace)` for every registry tenant (erased tenants stay in the registry, so their prefixes are covered), then `Maintain`, then one log line with the totals and the sweep duration.
  - One loop serves both tickers through `select`, so rebuild, flush and sweep never overlap inside the worker.
  - An error for one tenant is logged with the tenant ID and a fixed message, and the loop moves on.
- **Compose:** the worker gets `BACKBONE_SWEEP_INTERVAL=${SWEEP_INTERVAL:-1h}` and `BACKBONE_GARBAGE_GRACE=${GARBAGE_GRACE:-10m}`.
- **`e2e.sh`:**
  - It defaults to `SWEEP_INTERVAL=10s` and `GARBAGE_GRACE=20s` for its run, as it already does for `FLUSH_INTERVAL`.
  - After verify it waits `${SETTLE_SECONDS:-0}` seconds, then runs `tier-stats.sh`.
  - It still exits with `verify.py`'s code.
- **`tier-stats.sh`** prints `hot=<n> cold=<n> dirty=<n> garbage=<rows in garbage> pending=<pending tombstones>`.
- **README:** the two new settings, `SETTLE_SECONDS`, and what sweep does.

- [ ] **Step 1: Write the failing config test**

```go
func TestLoadSweepDefaultsAndValidation(t *testing.T) // 1h and 10m defaults; "0s" sweep rejected; "-1m" grace rejected; "0s" grace accepted
```

- [ ] **Step 2: Implement the config, the worker schedule, compose, scripts and README**

- [ ] **Step 3: Run the supplied data with the default margin**

Run: `SETTLE_SECONDS=60 part2/scripts/e2e.sh "$INFRA/data"`, with `INFRA` exported as the supplied `infrastructure` folder.
Expected: `verify.py` prints `PASS` (state 200/200, isolation 0, ranges 48/48), and `tier-stats.sh` shows `dirty=0 garbage=0 pending=0`.

- [ ] **Step 4: Run with a 1-hour margin to force late events**

Run: `FLUSH_MARGIN=1h SETTLE_SECONDS=60 part2/scripts/e2e.sh "$INFRA/data"`
Expected: `PASS` and `dirty=0 garbage=0 pending=0`. Plan 2 left 4 dirty tenants here, so this shows the rebuild cleared them.

- [ ] **Step 5: Check the logs**

Run: `TENANTS_FILE=$INFRA/data/tenants.json docker compose -f part2/docker-compose.yml logs | grep -c 'cus_'`
Expected: `0`. The worker logs show sweep lines and no rebuild, flush or sweep failures.

- [ ] **Step 6: Commit**

```bash
git add part2/backbone part2/docker-compose.yml part2/scripts part2/README.md
git commit -m "Schedule rebuild and sweep in the worker and verify end to end"
```
