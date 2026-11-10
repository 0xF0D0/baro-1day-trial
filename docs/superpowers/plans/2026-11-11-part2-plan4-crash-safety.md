# Part 2 Plan 4: Crash Safety of Tier Moves and Compaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show that `kill -9` during a tier move (flush) or a compaction (rebuild) never loses an acknowledged event, never duplicates one, and never leaves a half-written state.

**Architecture:**
- **Named crash points.** Six crash points sit in `FlushDay` and `Rebuild`. They are off unless the worker is started with them armed. Store tests hit each one on purpose by turning the exit into a panic.
- **Chaos harness.** A script replays the supplied data with aggressive settings. While it runs, it `kill -9`s the worker at random and arms the crash points at a low probability. Then it disarms, lets the worker settle and sweep with grace 0, and runs `verify.py` and a Go consistency checker.
- **Checker.** It compares what is stored against the acknowledged deliveries. It ships as a compose tool service, so the harness needs only Docker and `python3`.

**Tech Stack:** Go 1.24, pgx v5.7.6, minio-go v7.0.97, Postgres 17, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-11-10-part2-brand-data-backbone-design.md` §16. The user narrowed it to tier moves and compaction:
- **Tier move** is `FlushDay`. **Compaction** is `Rebuild`. Both run in the worker, so the worker is the only kill target.
- Ingest, erasure races, and api, Postgres and MinIO kills are out of scope.

This plan builds on Plans 1–3, all on `main`.

**Branch:** `part2-plan4-crash-safety`, cut from `main`.

## Global Constraints

- All of Plan 1–3's Global Constraints still hold, including the lock order: 1 cold-writer, 2 tenant-status, 3 customer, 4 cold-commit.
- **Never run `go mod tidy`**: it bumps `go.mod` to Go 1.25.
- **Crash points are test-only and off by default.**
  - Only the worker's `main` arms them, from `BACKBONE_CRASH_POINTS`, a comma-separated list with an empty default.
  - Disarmed, `crashpoint.Hit` does nothing.
  - Armed, a fired point writes exactly one line to stderr, `{"level":"WARN","msg":"crash point","point":"<name>"}`, then exits with status `137`. It runs no deferred calls, as a real `kill -9` would.
- **The six crash point names, verbatim:** `flush.after_bucket`, `flush.after_snapshot`, `flush.before_commit`, `rebuild.after_bucket`, `rebuild.after_snapshot`, `rebuild.before_commit`.
- **The checker and the harness never print a customer ID.** They print tenant IDs, event IDs, object names and counts only. The deliveries file is read but never echoed.
- **The harness needs only Docker and `python3`.** The checker runs from the compose image, not from a host Go toolchain.
- **"Acknowledged"** means a response status from 200 through 299 in `replay_responses.json`. Its keys are delivery `seq` strings; each value is a status or `null`, where `null` means the delivery never succeeded.
- **The stored set must equal the expected set exactly.** The expected set is every acknowledged webhook event, minus the events of customers whose erasure was acknowledged, minus every event of tenants whose erasure was acknowledged. Matching is by the canonical `event_id` and `customer_id`, decided with `internal/canon`, as the api does.

## Review Focus

1. A crash at any of the six points must commit nothing, and the next run must complete. Test: Task 2 `TestCrashPoints`.
2. Objects written before a crash must be removed by sweep, and no referenced object may be removed. Test: Task 2 `TestCrashPoints` (`OrphansDeleted >= 1`, then a clean `Audit`).
3. A late event redelivered after a crashed rebuild must still be answered as a duplicate. Test: Task 2 `TestCrashedRebuildThenRedeliveryIsDuplicate`.
4. Redeliveries, forged deliveries, never-succeeded deliveries, and events that reached an erased customer after the erasure must not cause false checker failures. Test: Task 3 `TestExpected`.
5. Disarmed crash points must never fire. Test: Task 2 `TestHitDisarmedNeverExits`.

---

### Task 1: Store audit

**Files:**
- Create: `part2/backbone/internal/store/audit.go`, `audit_test.go`

**Interfaces:**
- Produces:

```go
// Audit is what one tenant's storage holds, for the crash checker.
type Audit struct {
	Erased       bool
	Dirty        bool
	HotIDs       []string // event IDs in hot_events
	ColdIDs      []string // event IDs in the manifest's buckets, one entry per occurrence
	BadPointers  []string // manifest or snapshot objects that are missing or fail to open
	Unreferenced []string // objects under "<tenant>/" that neither the snapshot pointer, the manifest nor garbage references
	GarbageRows  int
	StateMatches bool // fold.Fold over every cold and hot event equals State (snapshot + hot)
}

func (s *Store) Audit(ctx context.Context, tenantID string) (Audit, error)
```

**Behavior:**
- Read Postgres in one `REPEATABLE READ READ ONLY` transaction, and take no locks; the audit runs on a quiet system.
- **Erased tenant:** set `Erased` and list every object under `<tenant>/` as `Unreferenced`. Leave the other fields zero and set `StateMatches` to true.
- **`StateMatches` is computed** only when `BadPointers` is empty; otherwise it is false.
- **Ordering:** cold events are ordered as `fold.Fold` expects. Compare the two `fold.Result` values as JSON.

- [ ] **Step 1: Write the failing tests**

```go
func TestAuditCleanAfterFlush(t *testing.T) {
	// fixture t_0018 ingested; FlushDay(rank 1, margin 0) until false; SweepTenant(grace 0); Audit ->
	// HotIDs ∪ ColdIDs == fixture IDs, no repeats; BadPointers, Unreferenced empty; GarbageRows 0; Dirty false; StateMatches true
}
func TestAuditFindsUnreferencedObject(t *testing.T) // Put cold.ObjectName(tenant, "bucket", day) with no pointer -> listed in Unreferenced
func TestAuditFindsBadPointer(t *testing.T)         // Objects().Delete one manifest object -> listed in BadPointers, StateMatches false
func TestAuditFindsDuplicate(t *testing.T)          // AddManifestBucket on an empty day with an event already in another bucket -> that ID twice in ColdIDs
func TestAuditFindsStateMismatch(t *testing.T)      // point tenant_cold.snapshot_object at PutSnapshot(fold.New(...).Snapshot()) -> StateMatches false
func TestAuditErasedTenant(t *testing.T)            // flush, EraseTenant -> Erased true, Unreferenced == the objects still under the prefix; after SweepTenant -> empty
```

- [ ] **Step 2: Start the services and see the tests fail**

Run: `mkdir -p part2/out/secrets && TENANTS_FILE=$INFRA/data/tenants.json docker compose -f part2/docker-compose.yml up -d --wait postgres minio && cd part2/backbone && BACKBONE_TEST_DATABASE_URL='postgres://postgres@127.0.0.1:55432/postgres?sslmode=disable' BACKBONE_TEST_MINIO_ENDPOINT=127.0.0.1:59000 BACKBONE_TEST_SECRETS_DIR=$PWD/../out/secrets go test ./internal/store/...`
Expected: FAIL (undefined `Audit`).

- [ ] **Step 3: Implement `Audit`**

- [ ] **Step 4: Run the tests and see them pass**

Run: the step 2 command with `-race`.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add part2/backbone/internal/store
git commit -m "Add a per-tenant storage audit for the crash checker"
```

### Task 2: Named crash points

**Files:**
- Create: `part2/backbone/internal/crashpoint/crashpoint.go`, `crashpoint_test.go`, `part2/backbone/internal/store/crash_test.go`
- Modify:
  - `part2/backbone/internal/store/flush.go`, `rebuild.go`
  - `part2/backbone/internal/config/config.go`, `config_test.go`
  - `part2/backbone/cmd/worker/main.go`
  - `part2/docker-compose.yml`

**Interfaces:**
- Consumes: `Audit` (Task 1).
- Produces:

```go
package crashpoint

// Names lists every crash point, in the order of the Global Constraints.
var Names = []string{...}

// Arm enables points with the given probability per hit. An empty list disarms; otherwise every
// name must be in Names and probability must be in (0, 1].
func Arm(points []string, probability float64) error

// Hit fires the point when it is armed and the draw succeeds. It is safe for concurrent use.
func Hit(name string)

// Intercept replaces the exit for tests and returns a function that restores it.
func Intercept(exit func()) (restore func())
```

- **Placement**, in `FlushDay`:
  - `flush.after_bucket` right after `putBucket`;
  - `flush.after_snapshot` right after `putSnapshot`;
  - `flush.before_commit` right before `tx.Commit`.
- **Placement**, in `Rebuild`:
  - `rebuild.after_bucket` after each `putBucket` in its loop;
  - `rebuild.after_snapshot` right after `putSnapshot`;
  - `rebuild.before_commit` right before `tx.Commit`.
- **Config:**
  - `BACKBONE_CRASH_POINTS` (comma-separated, spaces trimmed, default empty) becomes the field `CrashPoints []string`.
  - `BACKBONE_CRASH_PROBABILITY` (default `0`, must be within `[0, 1]`) becomes the field `CrashProbability float64`.
- **Worker:** call `crashpoint.Arm(cfg.CrashPoints, cfg.CrashProbability)` before opening the store. Treat an error as fatal. When points are armed, log `crash points armed` with the list.
- **Compose:** the worker gets `BACKBONE_CRASH_POINTS=${CRASH_POINTS:-}` and `BACKBONE_CRASH_PROBABILITY=${CRASH_PROBABILITY:-0}`.

- [ ] **Step 1: Write the failing tests**

```go
// internal/crashpoint
func TestArmValidates(t *testing.T)        // unknown name -> error; probability 0 or 1.5 with points -> error; nil points -> nil
func TestHitDisarmedNeverExits(t *testing.T) // Intercept counts calls; Arm(nil, 0); Hit every name 1000 times -> 0 exits
func TestHitArmedFires(t *testing.T)       // Arm([flush.after_bucket], 1); Hit("flush.after_bucket") -> 1 exit; Hit("rebuild.after_bucket") -> still 1

// internal/config
func TestLoadCrashSettings(t *testing.T)   // defaults empty and 0; " flush.after_bucket , rebuild.before_commit " -> two trimmed names; "1.5" and "-0.1" rejected

// internal/store
func TestCrashPoints(t *testing.T) {
	// table over the six names; flush cases: fixture t_0018 ingested; rebuild cases: flushed, then 3 late events ingested (dirty).
	// Arm([name], 1); Intercept(func() { panic(crashed{}) }); run FlushDay(rank 1, margin 0) or Rebuild and recover crashed{}.
	// Right after the crash: tenant_cold (cold_until, snapshot_object, dirty), cold_manifest rows, hot_events count and garbage
	// rows are exactly as before the call.
	// Then Arm(nil, 0); finish (FlushDay until false, or Rebuild -> true); SweepTenant(grace 0) -> OrphansDeleted >= 1;
	// Audit: no repeats across HotIDs and ColdIDs, their union == every ingested ID, BadPointers and Unreferenced empty,
	// GarbageRows 0, StateMatches true; State == fold.Fold(every ingested event).
}
func TestCrashedRebuildThenRedeliveryIsDuplicate(t *testing.T) {
	// rebuild case crashed at rebuild.before_commit; Ingest one of the late events again -> Duplicate
}
```

- [ ] **Step 2: Run the tests and see them fail**

Run: the Task 1 command with `./internal/crashpoint/... ./internal/config/...` added.
Expected: FAIL.

- [ ] **Step 3: Implement the package, the six hits, the config fields, worker arming and the compose variables**

- [ ] **Step 4: Run the tests and see them pass**

Run: the step 2 command with `-race`, then `go test -race ./...`.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add part2/backbone part2/docker-compose.yml
git commit -m "Add named crash points to flush and rebuild"
```

### Task 3: Consistency checker

**Files:**
- Create:
  - `part2/backbone/internal/check/check.go`, `check_test.go`
  - `part2/backbone/cmd/check/main.go`
- Modify: `part2/backbone/Dockerfile`, `part2/docker-compose.yml`

**Interfaces:**
- Consumes: `store.Audit` (Task 1), `tenants.Registry`, `webhook.PeekAccount`, `webhook.PeekShopDomain`, `canon.FromVendorA`, `canon.FromVendorB`.
- Produces:

```go
package check

type Expectation struct {
	Events        map[string]map[string]bool // tenant -> event IDs that must be stored
	ErasedTenants map[string]bool
	Unparsed      int // acknowledged webhook deliveries whose tenant or event could not be resolved
}

// Expected reads deliveries (JSON lines, already decompressed) and the replay responses.
func Expected(reg *tenants.Registry, deliveries io.Reader, responses map[string]*int) (Expectation, error)

type Problem struct {
	Tenant string
	Kind   string // lost, unexpected, duplicate, bad_pointer, unreferenced, garbage, dirty, state_mismatch, unparsed
	Detail string // an event ID, an object name or a count; never a customer ID
}

// Compare checks every audited tenant against the expectation.
func Compare(exp Expectation, audits map[string]store.Audit) []Problem
```

**Delivery rows** carry `seq` and `kind`:
- `webhook` rows carry `path` and `body`. For `/webhooks/vendor-a`, peek the account and look up `ByAccount`, then `FromVendorA`. For `/webhooks/vendor-b`, peek the shop domain and look up `ByShopDomain`, then `FromVendorB`.
- `erase_customer` rows carry `tenant_id` and `customer_id`.
- `erase_tenant` rows carry `tenant_id`.

**`Compare` rules:**
- **lost:** an expected ID that is in neither `HotIDs` nor `ColdIDs`.
- **unexpected:** a stored ID that is not expected. A non-empty store for an erased tenant also counts.
- **duplicate:** an ID that appears more than once across `HotIDs` and `ColdIDs`.
- **The others** map one to one onto the `Audit` fields. `garbage` fires when `GarbageRows > 0`.
- **unparsed:** when `Unparsed > 0`, one problem on tenant `-`, with the count as its detail.

**`cmd/check`:**
- Flags: `-deliveries <path to deliveries.jsonl.gz>` and `-responses <path to replay_responses.json>`.
- It reads the same environment as the worker (`config.Load`) and audits every registry tenant.
- It prints the first 20 problems, then two summary lines:
  - `check: tenants=<n> expected=<n> stored=<distinct stored IDs>`
  - `lost=<n> unexpected=<n> duplicate=<n> bad_pointer=<n> unreferenced=<n> garbage=<n> dirty=<n> state_mismatch=<n> unparsed=<n>`
- It ends with `CHECK PASS` and exit 0, or `CHECK FAIL` and exit 1.

**Image and compose:**
- The Dockerfile also builds `/usr/local/bin/check`.
- Compose gains a `check` service with `profiles: ["tools"]` and the worker's database, tenants, KEK and MinIO settings. Its entrypoint is `/usr/local/bin/check`.
- Its volumes are the tenants file, `./out/secrets:/secrets:ro`, `${DATA_DIR:-./out}:/data:ro` and `./out:/out:ro`.

- [ ] **Step 1: Write the failing tests**

```go
func TestExpected(t *testing.T) {
	// a registry from tenants.Parse with two tenants; JSON lines built with real vendor A and B bodies:
	// - an event delivered twice, both 200 -> expected once
	// - an event answered 401 (forged) and one answered null (never succeeded) -> not expected
	// - customer C: one event before and one after an erase_customer row answered 204 -> neither expected
	// - an erase_customer answered null -> that customer's events stay expected
	// - tenant T2 erase_tenant answered 204 -> ErasedTenants[T2], no events of T2 expected
	// - an acknowledged body for an unknown shop domain -> Unparsed == 1
}
func TestCompare(t *testing.T) // one audit per rule above yields exactly that Kind; a clean audit yields no problem; no Detail contains "cus_"
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `cd part2/backbone && go test ./internal/check/...`
Expected: FAIL.

- [ ] **Step 3: Implement `Expected`, `Compare`, `cmd/check`, the Dockerfile line and the compose service**

- [ ] **Step 4: Run the tests and see them pass, then run the checker on a clean replay**

Run: `go test -race ./internal/check/...`, then from the repo root `SETTLE_SECONDS=60 INFRA=$INFRA part2/scripts/e2e.sh "$INFRA/data"`, then `DATA_DIR=$INFRA/data TENANTS_FILE=$INFRA/data/tenants.json docker compose -f part2/docker-compose.yml run --rm check -deliveries /data/deliveries.jsonl.gz -responses /out/data/replay_responses.json`.
Expected:
- Tests PASS.
- The e2e prints `PASS` and `garbage=0`.
- The checker prints all nine counts as 0 and `CHECK PASS`.

- [ ] **Step 5: Commit**

```bash
git add part2/backbone part2/docker-compose.yml
git commit -m "Add the crash consistency checker"
```

### Task 4: Chaos harness and report

**Files:**
- Create: `part2/scripts/crash.sh`
- Modify: `part2/README.md`

**Interfaces:**
- Consumes:
  - the compose variables from Task 2 (`CRASH_POINTS`, `CRASH_PROBABILITY`);
  - the `check` service from Task 3;
  - the existing `replay.sh`, `verify.sh` and `tier-stats.sh`.
- Produces: `part2/scripts/crash.sh <data-dir>`, run as `INFRA=<supplied infrastructure dir> crash.sh <data-dir>`. It exits 0 only if both `verify.py` and the checker pass.

**Settings**, all overridable from the environment, with these defaults:
- `FLUSH_MARGIN=1h`, `FLUSH_INTERVAL=2s`, `SWEEP_INTERVAL=10s`, `GARBAGE_GRACE=20s`
- `CRASH_POINTS` = all six names, comma-separated; `CRASH_PROBABILITY=0.02`
- `KILL_MIN_S=3`, `KILL_MAX_S=10`, `CHAOS_TAIL_S=30`, `SETTLE_TIMEOUT_S=180`

**Steps the script runs:**
1. `down -v`, then `up -d --build --wait`, with the settings exported.
2. Start a background kill loop. Each round it:
   - sleeps a random whole number of seconds in `[KILL_MIN_S, KILL_MAX_S]`;
   - runs `docker compose kill -s KILL worker`, counting only kills that succeed;
   - runs `docker compose start worker`.
3. Run `replay.sh`, then sleep `CHAOS_TAIL_S`, then stop the kill loop.
4. Save `docker compose logs worker` to `part2/out/<data>/worker-chaos.log`. Count the `"msg":"crash point"` lines per point, and the `tenant rebuilt` and `flush tick` lines.
5. Settle: recreate the worker disarmed and sweeping with grace 0 (`CRASH_POINTS= CRASH_PROBABILITY=0 GARBAGE_GRACE=0s docker compose up -d worker`). Wait until its log shows `sweep done`, up to `SETTLE_TIMEOUT_S`; a timeout is a failure. Then `docker compose stop worker`.
6. Run `verify.sh`, `tier-stats.sh`, and the `check` service with `DATA_DIR=<data-dir>`.
7. Write `part2/out/<data>/crash-report.txt` and print it. It holds:
   - the settings;
   - the successful external kills;
   - the crash point hits per name;
   - the rebuilds and flush ticks seen;
   - `verify.py`'s summary lines;
   - the tier-stats line;
   - the checker's summary lines.

**README:** a "Crash test" section with the command, what it does, what the report shows, and the fact that the six crash points are also hit one by one in `TestCrashPoints`.

- [ ] **Step 1: Write `crash.sh` and the README section**

- [ ] **Step 2: Run the chaos harness**

Run: `INFRA=$INFRA part2/scripts/crash.sh "$INFRA/data"`
Expected:
- Exit 0.
- The report shows `verify.py` `PASS` (state 200/200, isolation 0, ranges 48/48), with `0 never succeeded` in the replay line.
- The checker shows `lost=0 unexpected=0 duplicate=0 bad_pointer=0 unreferenced=0 garbage=0 dirty=0 state_mismatch=0 unparsed=0` and `CHECK PASS`.
- There are at least 10 successful kills, at least one crash point hit, and at least one rebuild.

- [ ] **Step 3: Run the plain end-to-end again with crash points off**

Run: `SETTLE_SECONDS=60 INFRA=$INFRA part2/scripts/e2e.sh "$INFRA/data"`
Expected: `PASS` and `dirty=0 garbage=0 pending=0`.

- [ ] **Step 4: Check the logs**

Run: `grep -c 'cus_' part2/out/data/worker-chaos.log part2/out/data/crash-report.txt`
Expected: `0` for both.

- [ ] **Step 5: Commit**

```bash
git add part2/scripts/crash.sh part2/README.md
git commit -m "Add the crash test harness for tier moves and compaction"
```
