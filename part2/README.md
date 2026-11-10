# Part 2: Brand Data Backbone

A Go service that ingests vendor webhooks into an encrypted Postgres hot table and serves state and range reads, with customer and tenant erasure. A worker moves older events into encrypted day buckets in MinIO (the cold tier), and reads span both tiers. Two api nodes sit behind an nginx load balancer on port 8080.

Operating it: [RUNBOOK.md](RUNBOOK.md) (start, metrics to watch, crash recovery, erasure bound). Measured numbers: [docs/measurements.md](docs/measurements.md).

## Requirements

Docker with Compose v2, Python 3 (only for the supplied `replay.py` and `verify.py`), and the supplied `infrastructure/` folder.

## Environment

| Variable | Used by | Meaning |
|---|---|---|
| `INFRA` | scripts | Path of the supplied `infrastructure/` folder (not in this repository). Required. |
| `TENANTS_FILE` | compose | Absolute path of the `tenants.json` to load. Required for every `docker compose` command, including `down` and the Postgres-only command, because the compose file refuses to parse without it. The scripts set it from the data directory. |
| `BACKBONE_TEST_DATABASE_URL` | Go tests | Postgres to test against, `postgres://postgres@127.0.0.1:55432/postgres?sslmode=disable` for the Postgres-only container below. Without it the store and api tests skip. |
| `BACKBONE_TEST_MINIO_ENDPOINT`, `BACKBONE_TEST_SECRETS_DIR` | Go tests | MinIO to test against (`127.0.0.1:59000`) and the directory holding its `minio_user` and `minio_password` files (`part2/out/secrets`). Without them the cold-tier tests skip. |
| `BACKBONE_TENANTS_FILE`, `BACKBONE_KEK_FILE`, `BACKBONE_DATABASE_URL` | api | Set by compose. `BACKBONE_LISTEN` is optional (default `:8080`). |
| `BACKBONE_MINIO_ENDPOINT`, `BACKBONE_MINIO_USER_FILE`, `BACKBONE_MINIO_PASSWORD_FILE` | api | Required; set by compose (`minio:9000` and files under `/secrets`). `BACKBONE_MINIO_BUCKET` is optional (default `backbone`). |
| `BACKBONE_FLUSH_INTERVAL`, `BACKBONE_FLUSH_MARGIN`, `BACKBONE_WATERMARK_RANK` | api, worker | Optional cold-tier flush settings: durations such as `5m` and `96h` (defaults), and the rank-watermark count (default `100`). The interval must be positive, the margin must not be negative and the rank at least 1; otherwise the process refuses to start. The worker is the only process that flushes. |
| `BACKBONE_SWEEP_INTERVAL`, `BACKBONE_GARBAGE_GRACE` | worker | Optional sweep settings: how often the worker sweeps (default `1h`, must be positive) and how long a replaced object waits in `garbage` before it is deleted (default `10m`, must not be negative). |
| `SWEEP_INTERVAL`, `GARBAGE_GRACE`, `SETTLE_SECONDS` | compose, e2e | Set the worker's `BACKBONE_SWEEP_INTERVAL` and `BACKBONE_GARBAGE_GRACE` (`e2e.sh` defaults them to `10s` and `20s`). `SETTLE_SECONDS` (default `0`) is how long `e2e.sh` waits after verify before it prints the tier statistics, so the sweep can settle. |
| `FLUSH_INTERVAL`, `FLUSH_MARGIN`, `WATERMARK_RANK` | compose | Set the worker's `BACKBONE_FLUSH_INTERVAL` (default `5m`; `e2e.sh` defaults it to `2s`), `BACKBONE_FLUSH_MARGIN` (default `96h`) and `BACKBONE_WATERMARK_RANK` (default `100`). |
| `TARGET` | replay, verify | Service URL, default `http://localhost:8080`. |

The `secrets-init` service creates three secrets once, in `part2/out/secrets` (gitignored): the key-encryption key `kek` (32 random bytes) and the MinIO credentials `minio_user` and `minio_password`. It never overwrites an existing file, and `down -v` does not remove them. MinIO runs from `bitnamilegacy/minio:2025.7.23-debian-12-r5` because Docker Hub no longer serves `minio/minio`; its S3 port is published on `127.0.0.1:59000`.

## Run

```sh
export INFRA=~/Downloads/BARO_Work_Trial/infrastructure
export TENANTS_FILE=$INFRA/data/tenants.json
mkdir -p part2/out/secrets   # create it as yourself; a rootful Docker daemon would create it as root
docker compose -f part2/docker-compose.yml up -d --build --wait
part2/scripts/replay.sh "$INFRA/data"   # sends all deliveries, writes part2/out/<name>/replay_responses.json
part2/scripts/verify.sh "$INFRA/data"   # state, isolation and range checks
```

Upgrading from the earlier stack (key-encryption key in a named volume): the key now lives in `part2/out/secrets`, and an existing `pgdata` volume holds data keys wrapped by the old key, so that state is unreadable. Run `down -v` first (or delete the old volumes).

A replay must start from empty storage: run `down -v` (see Stop) before `up`, or use `scripts/e2e.sh`. Replaying again over existing data makes deliveries from before a tenant's erasure get 410, and verify fails.

Each script takes the data directory as its only argument.

## End to end

`part2/scripts/e2e.sh <data-dir>` destroys the stack and its volumes, starts it from empty storage with that directory's `tenants.json`, replays, verifies and prints the tier statistics. It exits with the verifier's exit code.

```sh
part2/scripts/e2e.sh "$INFRA/data"
python3 "$INFRA/generate.py" --seed 7 --out /path/to/seed7 && part2/scripts/e2e.sh /path/to/seed7
```

## Crash test

`part2/scripts/crash.sh <data-dir>` replays the data while the worker is hit with `kill -9` every 3 to 10 seconds, only in rounds where the worker container is running and not restarting, and its six crash points are armed (`flush.after_bucket`, `flush.after_snapshot`, `flush.before_commit`, `rebuild.after_bucket`, `rebuild.after_snapshot`, `rebuild.before_commit`, each firing with probability `0.002`). After the replay it keeps the chaos going for `CHAOS_TAIL_S` (30s), stops it, kills the worker one last time and stops it, so the store is left as a crash left it, and saves the worker log. It then runs `tier-stats.sh` and the consistency checker with `-unsettled` (the pre-settle check: `dirty`, `unreferenced` and `garbage` are counted but do not fail it). Next it recreates the worker disarmed with a garbage grace of 0, waits for one `sweep done`, stops the worker, and runs `verify.sh`, `tier-stats.sh` and the full consistency checker. It exits 0 only if `verify.py`, the pre-settle check and the full check all pass. The script tears the stack down with `down -v` before it starts.

```sh
export INFRA=~/Downloads/BARO_Work_Trial/infrastructure
part2/scripts/crash.sh "$INFRA/data"
```

Settings (environment, defaults): `FLUSH_MARGIN=1h`, `FLUSH_INTERVAL=2s`, `SWEEP_INTERVAL=10s`, `GARBAGE_GRACE=20s`, `CRASH_POINTS` (all six), `CRASH_PROBABILITY=0.002`, `KILL_MIN_S=3`, `KILL_MAX_S=10` (`KILL_MAX_S >= KILL_MIN_S >= 1`), `CHAOS_TAIL_S=30`, `SETTLE_TIMEOUT_S=180`.

The report, `part2/out/<name>/crash-report.txt` (also printed), holds the settings, the number of external kills counted while the worker was running, the crash point hits per name and the points never hit, the rebuilds, flush ticks and sweeps seen, the replay `done:` line, `verify.py`'s summary lines, the tier-stats line before and after the settle, and the summary lines of the pre-settle and full checks. The worker logs are `worker-chaos.log` and `worker-settle.log` in the same directory. A run needs at least a few kills, a crash point hit and a rebuild to mean anything; the report shows them so you can check.

Scope: only the worker is killed (flush is the tier move, rebuild is the compaction). Kills of the api, Postgres and MinIO, ingest, and customer-erasure rewrites are not covered by this harness. The six crash points are also hit one by one, deterministically, in `TestCrashPoints`.

## Worker and tier statistics

The `worker` compose service runs the same image with the `worker` binary. Every flush interval it walks the tenant registry and flushes one day at a time per tenant until nothing is left to flush, moving events older than the watermark from `hot_events` into encrypted day buckets in MinIO. The watermark is the rank-th largest event time among a tenant's hot events minus the margin, in event time, not wall-clock time. It logs one line per tick with the number of days flushed and the tick duration; a failing tenant is logged by tenant ID only, and the loop continues. Before flushing a tenant, the worker rebuilds it from its cold buckets if a late event marked it dirty. On a separate sweep interval it deletes `garbage` objects older than the grace period, deletes objects that nothing references (leftovers of crashed operations), finishes pending customer erasures, then runs Postgres maintenance (`VACUUM` of the hot tables, `pg_switch_wal()`, `CHECKPOINT`) and logs the totals and the sweep duration. One loop serves both intervals, so rebuild, flush and sweep never overlap. It stops cleanly on SIGTERM.

`part2/scripts/tier-stats.sh <data-dir>` prints `hot=<rows in hot_events> cold=<events in cold buckets> dirty=<tenants marked dirty> garbage=<rows in garbage> pending=<pending tombstones>` from the running Postgres. `e2e.sh` uses a 2s flush interval (override with `FLUSH_INTERVAL`) so the cold tier is exercised during the replay, and runs `tier-stats.sh` after verify and an optional `SETTLE_SECONDS` wait; its exit code is still the verifier's.

## Benchmark

`INFRA=<supplied infrastructure dir> part2/scripts/benchmark.sh <data-dir>` measures the stack on one data set. It starts from `down -v` and `up -d --build --wait` (with `FLUSH_INTERVAL=10s` unless set), runs `replay.sh` and keeps its `done:` line (ingest throughput), waits until the worker logs a `flush tick` with `"days_flushed":0` after the replay ended (the first tick logged after the replay is skipped, because it may have started earlier; `SETTLE_TIMEOUT_S`, default 600), runs `verify.sh`, then runs the `bench` tool service (`cmd/bench`).

`bench` takes the first and the last UTC day of the delivery times as the cold and the hot window. For every tenant and each of `ROUNDS` rounds (default 5) it reads `/state` and the first page of `/events` for each window, through the load balancer with the tenant's own token, `CONCURRENCY` (default 8) at a time. It prints `state`, `range_cold` and `range_hot` lines (`count`, `p50`, `p95`, `p99`, `max` in ms, nearest-rank), the three tenants with the slowest state reads, `skipped_erased` (a `410` on a tenant's first state read skips that tenant) and `errors`; any other non-200 answer is an error and the exit code is 1.

The script then reads from Postgres the hot bytes per event, the cold bytes per event (`cold_manifest`) and the index bytes per cold event (`customer_days` and `sku_moves`), and the peak memory of `api1`, `api2`, `worker`, `postgres` and `minio` from `/sys/fs/cgroup/memory.peak` (`n/a` if unreadable). It writes `part2/out/<name>/benchmark.txt` (machine, settings, each number with a one-line method, verify's result) and prints it. The exit code is 0 only if verify and `bench` both succeed. It never prints customer IDs.

```sh
export INFRA=~/Downloads/BARO_Work_Trial/infrastructure
part2/scripts/benchmark.sh "$INFRA/data"
```

## Stop

`TENANTS_FILE` must be set for these too.

```sh
export TENANTS_FILE=$INFRA/data/tenants.json
docker compose -f part2/docker-compose.yml down      # keep data
docker compose -f part2/docker-compose.yml down -v   # also drop the database and the MinIO data (the secrets in `part2/out/secrets` stay)
```

## Go tests

Postgres is published on `127.0.0.1:55432` and MinIO on `127.0.0.1:59000`; starting `minio` also creates the secrets the cold-tier tests read:

```sh
export TENANTS_FILE=$INFRA/data/tenants.json
mkdir -p part2/out/secrets
docker compose -f part2/docker-compose.yml up -d --wait postgres minio
(cd part2/backbone && BACKBONE_TEST_MINIO_ENDPOINT=127.0.0.1:59000 BACKBONE_TEST_SECRETS_DIR="$PWD/../out/secrets" BACKBONE_TEST_DATABASE_URL='postgres://postgres@127.0.0.1:55432/postgres?sslmode=disable' go test -race -count=1 ./...)
docker compose -f part2/docker-compose.yml down
```
