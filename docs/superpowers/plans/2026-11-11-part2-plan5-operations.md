# Part 2 Plan 5: Metrics, Snapshot Cache, Benchmark and Runbook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the operations part:
- Prometheus metrics for the numbers spec §20 lists;
- the api snapshot cache (spec §8);
- a one-command benchmark that produces the required measurements (ingest throughput, hot and cold read latency, bytes per event per tier, peak memory) with their method;
- a one-page runbook.

**Architecture:**
- **Metrics.** One `internal/metrics` package holds a private Prometheus registry and every metric. The store records read, ingest and erasure metrics where it knows the facts. The api records webhook outcomes and ack latency. The worker records job durations, errors and rebuilds, and adds a storage collector that queries Postgres at scrape time. The api serves `/metrics` on its own listener and the load balancer hides it. The worker gets a small metrics listener.
- **Snapshot cache.** A store-level cache keeps one decrypted snapshot per tenant. A read gets a hit only when the cached entry's object name equals the pointer it just read.
- **Benchmark.** A Go read-load tool runs as a compose tool service, like the checker. A script replays a data set, waits for the tiers to settle, runs the read load, and collects storage and peak-memory numbers into a report.

**Tech Stack:** Go 1.24, pgx v5.7.6, minio-go v7.0.97, `github.com/prometheus/client_golang`, Postgres 17, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-11-10-part2-brand-data-backbone-design.md` §8 (snapshot cache), §20 (operations: commands, metrics, runbook, measurements), §15 (logs and metrics carry no customer data). This plan builds on Plans 1–4, all on `main`.

**Branch:** `part2-plan5-operations`, cut from `main`.

## Global Constraints

- All of Plan 1–4's Global Constraints still hold.
- **Never run `go mod tidy`**: it bumps `go.mod` to Go 1.25.
- **The Prometheus client.**
  - Add `github.com/prometheus/client_golang` with `go get github.com/prometheus/client_golang@v1.22.0`.
  - `go.mod` must still say `go 1.24` afterwards. If that version bumps it, use the newest release that does not, and record which.
- **No customer data in metrics.**
  - Metric labels use only the fixed values listed in this plan.
  - No label carries a tenant ID, customer ID, event ID, object name or raw path.
  - No metric name is built from input.
- **Metric names, label sets and label values, verbatim:**
  - `backbone_ingest_total{vendor, outcome}`
    - `vendor` ∈ `a`, `b`
    - `outcome` ∈ `stored`, `duplicate`, `customer_erased`, `tenant_erased`, `bad_request`, `unknown_tenant`, `bad_signature`, `error`
  - `backbone_ack_seconds{vendor}`, a histogram observed for every webhook answered `200`.
  - `backbone_read_seconds{kind, tier}`, a histogram.
    - `kind` ∈ `state`, `range`
    - `tier` is `cold` when the call read at least one object (snapshot or bucket), otherwise `hot`
  - `backbone_late_events_total`, counted when a late event is inserted.
  - `backbone_erasure_seconds{kind}`, a histogram with `kind` ∈ `customer`, `tenant`, observed for successful erasures.
  - `backbone_snapshot_cache_total{result}` with `result` ∈ `hit`, `miss`.
  - `backbone_job_seconds{job}`, a histogram with `job` ∈ `flush`, `rebuild`, `sweep`.
    - `flush` is one `FlushDay` that moved a day.
    - `rebuild` is one `Rebuild` that returned true.
    - `sweep` is one whole sweep, including maintenance.
  - `backbone_job_errors_total{job, class}`
    - `job` ∈ `flush`, `rebuild`, `sweep`, `maintain`
    - `class` comes from `metrics.ErrorClass`: `postgres_<SQLSTATE>` for a `*pgconn.PgError`, `object_not_found` for `cold.ErrNotFound`, `canceled` for context errors, otherwise `other`
  - `backbone_rebuilds_total{reason}` with `reason` = `late_events`.
  - `backbone_last_sweep_age_seconds`: seconds since the last completed sweep, or since worker start if none has completed.
  - Storage gauges, read at scrape time in the worker:
    - `backbone_tier_events{tier}` and `backbone_tier_bytes{tier}`, with `tier` ∈ `hot`, `cold`;
    - `backbone_index_bytes{table}`, with `table` ∈ `customer_days`, `sku_moves`;
    - `backbone_pending_tombstones`, `backbone_garbage_objects`, `backbone_dirty_tenants`.
  - The client's standard Go and process collectors (`process_resident_memory_bytes`).
- **Endpoints.**
  - The api serves `GET /metrics` on `BACKBONE_LISTEN`. nginx answers `404` for `/metrics`, so it is reachable only inside the compose network.
  - The worker serves `GET /metrics` on `BACKBONE_METRICS_LISTEN` (default `:9100`).
  - The worker's failure log lines gain a `class` field with the same value as the metric label.
- **Snapshot cache:**
  - It holds one entry per tenant: object name, decrypted snapshot, and insert time.
  - A lookup hits only when the name matches the pointer just read and the entry is younger than `BACKBONE_SNAPSHOT_CACHE_TTL` (default `1h`; `0` disables the cache).
  - Tenant erasure drops the tenant's entry on the node that ran it.
  - Cached snapshots are never mutated.
- **Commands:** benchmark is one command, `part2/scripts/benchmark.sh <data-dir>`, run as `INFRA=<supplied infrastructure dir> benchmark.sh <data-dir>`. It needs only Docker and `python3`.

## Review Focus

1. A metrics scrape after real traffic must contain no customer ID, tenant ID or raw path. Test: Task 1 `TestMetricsCarryNoInputData`.
2. The cache must never serve a snapshot after flush, rebuild or erasure moved the pointer. Test: Task 3 `TestCacheMissAfterPointerChange`.
3. A read must never change a cached snapshot. Test: Task 3 `TestCachedSnapshotNotMutated`.
4. A slow or unreachable Postgres must not hang a worker scrape or the worker loop. Test: Task 2 `TestStatsCollectorTimesOut`.
5. Every benchmark number must carry its method, and a figure the platform cannot provide must print `n/a`, never a guess. Check: Task 4, step 4.

---

### Task 1: Metrics package and api-side metrics

**Files:**
- Create: `part2/backbone/internal/metrics/metrics.go`, `metrics_test.go`
- Modify:
  - `part2/backbone/go.mod`, `go.sum`
  - `part2/backbone/internal/store/events.go`, `reads.go`, `erase.go`
  - `part2/backbone/internal/api/server.go`, `webhooks.go`, `api_test.go`
  - `part2/deploy/nginx.conf`

**Interfaces:**
- Produces, in package `metrics`:
  - every metric from the Global Constraints, as exported package variables (for example `IngestTotal *prometheus.CounterVec`);
  - `func Handler() http.Handler`, serving the private registry with the Go and process collectors;
  - `func ErrorClass(err error) string`;
  - `func Register(c prometheus.Collector)`, used by the worker in Task 2.
- **Store recording.**
  - `State` and `Range` observe `backbone_read_seconds` on success, with the tier as defined above.
  - `Ingest` increments `backbone_late_events_total` when it inserts a late row.
  - `EraseCustomer` and `EraseTenant` observe `backbone_erasure_seconds` on success.
- **Api recording.** The webhook handler increments `backbone_ingest_total` on every exit path, mapped to the outcome values, and observes `backbone_ack_seconds` when it answers `200`. `GET /metrics` is added to the mux.
- **nginx:** add `location = /metrics { return 404; }`.

- [ ] **Step 1: Write the failing tests**

```go
// internal/metrics
func TestErrorClass(t *testing.T) // &pgconn.PgError{Code:"40P01"} -> "postgres_40P01"; wrapped cold.ErrNotFound -> "object_not_found";
                                  // context.Canceled and DeadlineExceeded -> "canceled"; errors.New("x") -> "other"
func TestHandlerServesProcessMetrics(t *testing.T) // GET Handler() body contains "go_goroutines" and the backbone_ingest_total HELP line

// internal/api (existing test server helpers)
func TestIngestOutcomesCounted(t *testing.T) {
	// one webhook of each outcome the fixtures allow (stored, duplicate, bad_signature, unknown_tenant, bad_request, tenant_erased)
	// -> each backbone_ingest_total{vendor,outcome} rises by exactly 1 (read with prometheus/testutil.ToFloat64)
	// -> backbone_ack_seconds count rises only for the 200 answers
}
func TestMetricsCarryNoInputData(t *testing.T) {
	// replay a fixture with customer IDs through the handler, erase one customer, read state and a range;
	// GET /metrics -> 200; body contains none of: "cus_", "t_00", "/tenants/", any fixture event ID
}

// internal/store (metrics are package globals: assert deltas, read before and after)
func TestReadTierLabels(t *testing.T) // State of a never-flushed tenant -> tier hot; after a flush -> tier cold; a Range inside hot days -> hot; inside a flushed day -> cold
func TestLateAndErasureMetrics(t *testing.T) // a late insert raises backbone_late_events_total by 1; EraseCustomer adds one backbone_erasure_seconds{kind="customer"} sample
```

- [ ] **Step 2: Start the services and see the tests fail**

Run: `mkdir -p part2/out/secrets && TENANTS_FILE=$INFRA/data/tenants.json docker compose -f part2/docker-compose.yml up -d --wait postgres minio && cd part2/backbone && BACKBONE_TEST_DATABASE_URL='postgres://postgres@127.0.0.1:55432/postgres?sslmode=disable' BACKBONE_TEST_MINIO_ENDPOINT=127.0.0.1:59000 BACKBONE_TEST_SECRETS_DIR=$PWD/../out/secrets go test ./internal/metrics/... ./internal/api/... ./internal/store/...`
Expected: FAIL.

- [ ] **Step 3: Add the dependency, the package, the store and api recording, `/metrics` and the nginx rule**

- [ ] **Step 4: Run the tests and see them pass**

Run: the step 2 command with `-race`, then `go test -race ./...`, and check that `grep '^go ' go.mod` prints `go 1.24`.
Expected: PASS, `go 1.24`.

- [ ] **Step 5: Commit**

```bash
git add part2/backbone part2/deploy/nginx.conf
git commit -m "Add Prometheus metrics for ingest, reads and erasure"
```

### Task 2: Worker metrics

**Files:**
- Create: `part2/backbone/internal/store/stats.go`, `stats_test.go`, `part2/backbone/cmd/worker/collector.go`
- Modify:
  - `part2/backbone/cmd/worker/main.go`
  - `part2/backbone/internal/config/config.go`, `config_test.go`
  - `part2/docker-compose.yml`

**Interfaces:**
- Consumes: `metrics.ErrorClass`, `metrics.Register` and the job metrics (Task 1).
- Produces:

```go
// Stats is a point-in-time storage summary for the storage gauges.
type Stats struct {
	HotEvents, HotBytes, ColdEvents, ColdBytes int64
	CustomerDaysBytes, SKUMovesBytes           int64
	PendingTombstones, GarbageObjects, DirtyTenants int64
}

func (s *Store) Stats(ctx context.Context) (Stats, error)
```

- **`Stats` sources:**
  - `HotEvents` is `count(*)` of `hot_events`, and `HotBytes` is `pg_total_relation_size('hot_events')`.
  - `ColdEvents` and `ColdBytes` are `sum(events)` and `sum(bytes)` of `cold_manifest`.
  - The two index sizes are `pg_total_relation_size` of each table.
  - The other three are counts of pending tombstones, `garbage` rows and dirty `tenant_cold` rows.
  - All of it comes from one `REPEATABLE READ READ ONLY` transaction.
- **Collector** (`cmd/worker/collector.go`): a `prometheus.Collector` whose `Collect` calls `Stats` with a 2-second timeout. On error it emits no storage samples and counts nothing. It emits the storage gauges from the Global Constraints.
- **Worker:**
  - It observes `backbone_job_seconds`.
  - It increments `backbone_rebuilds_total{reason="late_events"}` when `Rebuild` returns true.
  - It increments `backbone_job_errors_total{job,class}` and adds `class` to each failure log line.
  - It keeps the last completed sweep time for `backbone_last_sweep_age_seconds`, registered as a `GaugeFunc`.
  - It registers the collector and serves `metrics.Handler()` on `cfg.MetricsListen`, in its own goroutine with read and write timeouts.
- **Config:** `BACKBONE_METRICS_LISTEN` (default `:9100`) becomes the field `MetricsListen string`.
- **Compose:** the worker passes `BACKBONE_METRICS_LISTEN=:9100`. Do not publish the port.

- [ ] **Step 1: Write the failing tests**

```go
// internal/store
func TestStats(t *testing.T) {
	// fixture t_0018 ingested and half flushed; one customer erased -> HotEvents and ColdEvents equal the hot row count and
	// sum(cold_manifest.events); HotBytes, ColdBytes and both index sizes > 0; GarbageObjects >= 1; PendingTombstones 0; DirtyTenants 0
}

// cmd/worker
func TestStatsCollectorTimesOut(t *testing.T) // a collector whose stats func blocks until ctx is done -> Collect returns within 3 s, no samples
func TestCollectorEmitsGauges(t *testing.T)   // a stats func returning fixed values -> testutil.CollectAndCompare matches the expected text

// internal/config
func TestLoadMetricsListen(t *testing.T) // default ":9100"; override kept
```

- [ ] **Step 2: Run the tests and see them fail**

Run: the Task 1 command with `./cmd/worker/... ./internal/config/...` added.
Expected: FAIL.

- [ ] **Step 3: Implement `Stats`, the collector, the worker recording and listener, the config field and the compose variable**

The collector takes a `func(context.Context) (store.Stats, error)`, so the tests can inject one.

- [ ] **Step 4: Run the tests and see them pass, then scrape a running worker**

Run: the step 2 command with `-race`, then `go test -race ./...`. Then from the repo root run `SETTLE_SECONDS=30 INFRA=$INFRA part2/scripts/e2e.sh "$INFRA/data"`, then `TENANTS_FILE=$INFRA/data/tenants.json docker compose -f part2/docker-compose.yml exec -T worker wget -qO- localhost:9100/metrics | grep -E '^backbone_(tier_events|job_seconds_count|last_sweep_age_seconds)'`.
Expected:
- Tests PASS. The e2e prints `PASS`.
- The scrape shows `backbone_tier_events{tier="cold"}` and `backbone_tier_events{tier="hot"}` summing to `97788`, a non-zero `backbone_job_seconds_count{job="flush"}`, and a `backbone_last_sweep_age_seconds` below 60.

- [ ] **Step 5: Commit**

```bash
git add part2/backbone part2/docker-compose.yml
git commit -m "Add worker metrics and a scrape-time storage collector"
```

### Task 3: Snapshot cache

**Files:**
- Create: `part2/backbone/internal/store/snapcache.go`, `snapcache_test.go`
- Modify:
  - `part2/backbone/internal/store/store.go`, `reads.go`, `erase.go`, `export_test.go`
  - `part2/backbone/internal/config/config.go`, `config_test.go`
  - `part2/backbone/cmd/api/main.go`, `part2/backbone/cmd/worker/main.go`
  - `part2/docker-compose.yml`

**Interfaces:**
- Consumes: `metrics.SnapshotCacheTotal` (Task 1).
- Produces:
  - `store.Open` keeps its signature.
  - `(*Store) SetSnapshotCacheTTL(ttl time.Duration)`, called once after `Open`; `0` disables the cache.
  - Inside the store, `State` gets its snapshot through the cache.
  - `EraseTenant` drops the tenant's entry, next to its existing key-cache cleanup.
  - Tests use the hook `SetSnapCacheClock(func() time.Time)` from `export_test.go`.
- **Config:** `BACKBONE_SNAPSHOT_CACHE_TTL` (default `1h`, must be 0 or more) becomes the field `SnapshotCacheTTL time.Duration`. The api calls `SetSnapshotCacheTTL(cfg.SnapshotCacheTTL)`; the worker never reads `State`, so it leaves the cache unset.
- **Compose:** api1 and api2 pass `BACKBONE_SNAPSHOT_CACHE_TTL=${SNAPSHOT_CACHE_TTL:-1h}`.

- [ ] **Step 1: Write the failing tests**

```go
func TestCacheHitOnSecondRead(t *testing.T)          // flushed tenant: two States -> one miss then one hit (testutil counter deltas); both equal fold.Fold
func TestCacheMissAfterPointerChange(t *testing.T)   // State (miss), FlushDay moves another day, State -> miss and equals fold; same after Rebuild and EraseCustomer
func TestCachedSnapshotNotMutated(t *testing.T)      // State, ingest a hot event, State, then ingest nothing and State again -> each equals fold.Fold of what was ingested so far
func TestCacheExpires(t *testing.T)                  // clock hook: State (miss), advance 61 min, State -> miss
func TestCacheDisabled(t *testing.T)                 // TTL 0 -> every State is a miss and no entry is kept
func TestEraseTenantDropsCacheEntry(t *testing.T)    // State (cached), EraseTenant -> the cache holds no entry for the tenant
func TestLoadSnapshotCacheTTL(t *testing.T)          // in internal/config: default 1h; "0s" accepted; "-1m" rejected
```

- [ ] **Step 2: Run the tests and see them fail**

Run: the Task 1 command with `./internal/config/...` added.
Expected: FAIL.

- [ ] **Step 3: Implement the cache, the wiring, the config field and the compose variable**

Guard the map with a mutex, keyed by tenant ID. `fold.Restore` copies the snapshot's contents, so the cached value can be shared read-only.

- [ ] **Step 4: Run the tests and see them pass**

Run: the step 2 command with `-race`, then `go test -race ./...`.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add part2/backbone part2/docker-compose.yml
git commit -m "Cache decrypted snapshots per tenant on api nodes"
```

### Task 4: Benchmark command and measurements

**Files:**
- Create:
  - `part2/backbone/cmd/bench/main.go`, `part2/backbone/internal/bench/bench.go`, `bench_test.go`
  - `part2/scripts/benchmark.sh`
  - `part2/docs/measurements.md`
- Modify: `part2/backbone/Dockerfile`, `part2/docker-compose.yml`, `part2/README.md`

**Interfaces:**
- Consumes: the metrics endpoints (Tasks 1 and 2), the cache (Task 3), and the `check` service pattern from Plan 4.
- Produces:

```go
package bench

// Windows picks the read windows from the deliveries file: cold is the first UTC day of delivery
// times, hot is the last UTC day.
func Windows(deliveries io.Reader) (coldFrom, coldTo, hotFrom, hotTo int64, err error)

// Summary is the latency summary of one request class.
type Summary struct{ Count int; P50, P95, P99, Max time.Duration }

// Summarize sorts the samples and takes nearest-rank percentiles.
func Summarize(samples []time.Duration) Summary
```

- **`cmd/bench`:**
  - Flags: `-target` (default `http://lb:8080`), `-tenants`, `-deliveries`, `-rounds` (default 5), `-concurrency` (default 8).
  - For every registry tenant, in each round, it sends three requests:
    - `GET /tenants/{id}/state`;
    - `GET /tenants/{id}/events` for the cold window;
    - `GET /tenants/{id}/events` for the hot window.

    Each uses the tenant's token, and each range request fetches the first page only.
  - It prints one line per class (`state`, `range_cold`, `range_hot`): `<class> count=<n> p50=<ms> p95=<ms> p99=<ms> max=<ms>`. It then prints the three tenant IDs with the slowest state reads, with their maximum state latency.
  - A `410` on a tenant's first state read marks the tenant erased. It is skipped for the rest of the run and counted as `skipped_erased=<n>` in the output. Any other non-200 answer counts as an error, and the run exits 1.
- **Image and compose:** the Dockerfile builds `/usr/local/bin/bench`. Compose gains a `bench` service with `profiles: ["tools"]`, the tenants file and `${DATA_DIR:-./out}:/data:ro`, and the entrypoint `/usr/local/bin/bench`.
- **`benchmark.sh`** (`INFRA=<dir> benchmark.sh <data-dir>`) runs these steps:
  1. `down -v`, then `up -d --build --wait`, with `FLUSH_INTERVAL=${FLUSH_INTERVAL:-10s}` and the compose defaults otherwise.
  2. Run `replay.sh` and keep its `done:` line; ingest throughput is that line's deliveries per second.
  3. Wait until the worker logs a `flush tick` with `"days_flushed":0` that starts after replay ended. The timeout is `SETTLE_TIMEOUT_S`, default 600.
  4. Run `verify.sh` and keep its summary lines.
  5. Build and run the `bench` service.
  6. Collect storage numbers from Postgres:
     - hot bytes per event: `pg_total_relation_size('hot_events') / count(*)`;
     - cold bytes per event: `sum(bytes) / sum(events)` from `cold_manifest`;
     - index bytes per cold event: both index tables, over `sum(events)`.
  7. For each of `api1 api2 worker postgres minio`, read peak memory with `docker compose exec -T <svc> cat /sys/fs/cgroup/memory.peak`, printed in MiB, or `n/a` if the file cannot be read.
  8. Write `part2/out/<data>/benchmark.txt` and print it. It holds the machine (`uname -m`, CPU count, Docker memory), the settings, each number with a one-line method, and verify's result.
- **`measurements.md`** records the runs of steps 2–4 below. For each data set it gives the report's numbers, the method and the machine. It keeps measured numbers apart from expectations. The large set is listed as not run unless it was.

- [ ] **Step 1: Write the failing tests**

```go
func TestWindows(t *testing.T)   // three delivery rows at known at_ms values spanning 3 days -> cold = first UTC day, hot = last UTC day
func TestSummarize(t *testing.T) // samples 1..100 ms -> P50 50 ms, P95 95 ms, P99 99 ms, Max 100 ms, Count 100; empty -> zero Summary
```

- [ ] **Step 2: Implement `internal/bench`, `cmd/bench`, the Dockerfile line, the compose service, `benchmark.sh` and the README "Benchmark" section; run `go test -race ./internal/bench/...`**

Expected: PASS.

- [ ] **Step 3: Run the benchmark on the supplied data**

Run: `INFRA=$INFRA part2/scripts/benchmark.sh "$INFRA/data"`
Expected:
- exit 0;
- verify `PASS`;
- three latency lines with `count` equal to `(200 − skipped_erased) × 5`;
- non-zero bytes per event for both tiers;
- a peak memory value or `n/a` for each service.

- [ ] **Step 4: Generate the medium set and run the benchmark on it**

Run: `python3 $INFRA/generate.py --scale medium --out part2/out/data-medium`, then `INFRA=$INFRA part2/scripts/benchmark.sh part2/out/data-medium`.
Expected: exit 0 and verify `PASS`. Every number in the report has a method line, and nothing is estimated.

- [ ] **Step 5: Write `measurements.md` from the two reports and commit**

```bash
git add part2/backbone part2/docker-compose.yml part2/scripts/benchmark.sh part2/docs/measurements.md part2/README.md
git commit -m "Add the benchmark command and record measurements"
```

### Task 5: Runbook

**Files:**
- Create: `part2/RUNBOOK.md`
- Modify: `part2/README.md`

**Content** (one page, English):
- **Start:** `docker compose up` with `TENANTS_FILE`, and the replay, verify, benchmark and crash test commands.
- **What to watch.** For each item, the metric and the condition that needs action:
  - `backbone_last_sweep_age_seconds` above 7200, which breaks the erasure bound;
  - `backbone_pending_tombstones` above 0 for longer than one sweep;
  - `backbone_dirty_tenants` above 0 across several flush intervals;
  - a rising `backbone_job_errors_total`, read by its `class`;
  - `backbone_ack_seconds` p99;
  - `backbone_tier_events{tier="hot"}` growing without bound, which means flush has stalled;
  - `process_resident_memory_bytes`.
- **How to scrape:** `docker compose exec -T api1 wget -qO- localhost:8080/metrics`, and the worker on `:9100`.
- **Recover from a crash:**
  - Restart the service. Leftovers are swept on the next sweep, and the worker also sweeps at startup.
  - Pending erasures finish in the sweep.
  - A dirty tenant is rebuilt on the next flush tick.
  - The crash test shows this (`crash.sh`).
- **Erasure bound:** immediate in reads and Postgres; within 2 hours in MinIO and the WAL while the worker runs. State what extends the bound.
- **Known limits:** link to the spec's stated limits.

- [ ] **Step 1: Write `RUNBOOK.md` and link it from the README**

- [ ] **Step 2: Check every command and metric name in it against the code**

Run: `grep -oE 'backbone_[a-z_]+' part2/RUNBOOK.md | sort -u`, and compare each name with `grep -rhoE 'backbone_[a-z_]+' part2/backbone/internal/metrics part2/backbone/cmd/worker | sort -u`.
Expected: every runbook name is defined in code.

- [ ] **Step 3: Commit**

```bash
git add part2/RUNBOOK.md part2/README.md
git commit -m "Add the one-page runbook"
```

---

## Outcome and follow-ups (added after execution, 2026-11-11)

**Result.** All five tasks are done and reviewed. Tasks 2–5 were built in parallel worktrees at the user's request and cherry-picked. The whole-branch review's fixes are applied (listed below).

- **Tests.** `go test -race ./...` passes, and `go.mod` stays on `go 1.24` (client_golang v1.22.0).
- **Benchmark, supplied data** (`part2/docs/measurements.md`):
  - `verify.py` passes.
  - Ingest: 1,189 deliveries/s, closed loop at concurrency 8.
  - State read: p50 4.7 ms, p99 60.4 ms.
  - Cold range, 111 tenants with cold data: p50 5.0 ms, p99 71.5 ms.
  - Hot range: p50 2.0 ms, p99 21.7 ms.
  - Bytes per event after `VACUUM FULL`: hot 583.7, cold 271.5.
  - Peak RSS: api about 30 MiB, worker 22.6 MiB, MinIO 332 MiB.
  - These come from a single run; an earlier run measured lower latencies.
- **Scrapes.** A worker scrape shows hot plus cold equal to 97,788 events. An api scrape shows outcome counts and cache hits. Neither contains `cus_`, and `/metrics` through nginx answers 404.

**Deviations from this plan.**
- `memory.peak` does not exist on this kernel. Peak memory is `VmHWM` of PID 1 (the process peak; for Postgres, the postmaster only), plus a 2-second sample of cgroup `memory.current`, which includes page cache.
- Plain gauges in `metrics.go` became a collector and a `GaugeFunc` in the worker.
- Fixes from the whole-branch review:
  - **Cold reads:** `range_cold` goes only to tenants with cold data (87 tenants never flush a day).
  - **Storage numbers:** they are measured after `VACUUM FULL`.
  - **Snapshot cache:** a janitor deletes expired entries, and every erased path drops the tenant's entry.
  - **Sweep age:** it moves only after a fully clean sweep.
  - **Histograms:** buckets are exponential, from 0.5 ms for reads and 10 ms for jobs.
  - **Method notes:** closed-loop ingest, cache misses, and empty hot pages.
- The submission design document `part2/DESIGN.md` was added on this branch.

**Follow-ups.**
1. Run the benchmark on the medium and large sets. The medium set is generated locally but has not been measured. Run several runs to characterize variance.
2. Add a `backbone_snapshot_cache_entries` gauge and singleflight for concurrent misses.
3. Add a unit test for the sweep-age rule and the janitor lifecycle (`Close`, re-`Set`).
