# Measurements

Measured with `part2/scripts/benchmark.sh` on the supplied data set (`$INFRA/data`). All numbers below come from one run. Nothing here is estimated.

## Machine and settings

- Host: Apple M2 Pro, 12 CPUs, 32 GiB RAM. Docker 24.0.2 with 6 CPUs and 7.8 GiB memory.
- Stack: compose defaults (two api nodes behind nginx, one worker, Postgres 17, MinIO). The only override is `FLUSH_INTERVAL=10s`, so the run settles quickly.
- Load: `replay.py` with its default concurrency, 8. Reads: `cmd/bench` with 5 rounds over all tenants and concurrency 8.

## Data set

- 100,560 deliveries for 200 tenants. That includes duplicates, forgeries and erasures.
- After the run, 97,788 events are stored: 23,214 in the hot tier and 74,574 in the cold tier.
- `verify.py`: `PASS`, with state 200/200 and ranges 48/48.

## Results

| Measure | Value | Method |
|---|---|---|
| Ingest throughput | 1,192 deliveries/s (100,560 in 84.4 s, 0 retries, 0 never succeeded) | `replay.py`'s own `done:` line |
| State read latency | p50 2.7 ms, p95 8.4 ms, p99 19.6 ms, max 64.8 ms (n=990) | Client side, `GET /tenants/{id}/state` through nginx. The server folds the snapshot and the hot tail. |
| Cold range read latency | p50 2.2 ms, p95 6.0 ms, p99 10.9 ms, max 24.1 ms (n=990) | First page of `GET /tenants/{id}/events` for the first UTC day of the deliveries, which sits in MinIO buckets |
| Hot range read latency | p50 1.5 ms, p95 4.3 ms, p99 7.8 ms, max 17.1 ms (n=990) | First page for the last UTC day of the deliveries, which sits in Postgres |
| Slowest state reads | t_0000 64.8 ms, t_0001 25.6 ms, t_0007 24.3 ms | Per-tenant maximum over the 5 rounds |
| Hot bytes per event | 1,764.5 | `pg_total_relation_size('hot_events') / count(*)` (table, indexes and TOAST) |
| Cold bytes per event | 271.5 | `sum(bytes) / sum(events)` from `cold_manifest` (sealed object sizes) |
| Index bytes per cold event | 330.7 | `pg_total_relation_size` of `customer_days` and `sku_moves`, over the cold event count |
| Peak memory | not measured in this run | See below |

The `n=990` count is 198 tenants × 5 rounds. Two tenants are erased by the data set and answer `410`, so `cmd/bench` skips them.

## Not measured

- **Peak memory.** The run read `/sys/fs/cgroup/memory.peak`, which this kernel does not provide, so every service printed `n/a`. The script now records two figures per service (commit "Measure peak memory with VmHWM and sampled cgroup memory"):
  - the process peak RSS, from `VmHWM` of PID 1;
  - a 2-second sample of cgroup `memory.current`, which includes page cache.

  It has not been run since that change.
- **Medium (about 1M deliveries) and large (about 5M) sets.** Not run. Generate one with `python3 $INFRA/generate.py --scale medium --out <dir>` and run `INFRA=$INFRA part2/scripts/benchmark.sh <dir>`.
- **The noisy-neighbour limits** (1 GiB, 2 CPUs per service). Not applied.
