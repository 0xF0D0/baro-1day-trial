# Measurements

Measured with `part2/scripts/benchmark.sh` on the supplied data set (`$INFRA/data`). Every number below comes from one run, and nothing is estimated. The method for each one is the script's own.

## Machine and settings

- **Host:** Apple M2 Pro, 12 CPUs, 32 GiB RAM.
- **Docker:** 24.0.2, with 6 CPUs and 7.8 GiB memory.
- **Stack:** compose defaults: two api nodes behind nginx, one worker, Postgres 17 and MinIO. The only override is `FLUSH_INTERVAL=10s`, so the run settles quickly.
- **Load:** `replay.py` at its default concurrency of 8. Reads come from `cmd/bench`: 5 rounds over all tenants at concurrency 8.

## Data set

- **Deliveries:** 100,560 for 200 tenants, including duplicates, forgeries and erasures.
- **Stored after the run:** 97,788 events, 23,214 hot and 74,574 cold.
- **`verify.py`:** `PASS`, with state 200/200, isolation 0 and ranges 48/48.

## Results

| Measure | Value | Method |
|---|---|---|
| Ingest throughput | 1,183 deliveries/s (100,560 in 85.0 s, 0 retries, 0 never succeeded) | `replay.py`'s own `done:` line, through the load balancer |
| State read latency | p50 2.6 ms, p95 7.5 ms, p99 18.1 ms, max 35.1 ms (n=990) | Measured on the client, `GET /tenants/{id}/state` through nginx. The server folds the cached snapshot plus the hot tail. |
| Cold range read latency | p50 2.0 ms, p95 6.6 ms, p99 11.6 ms, max 20.8 ms (n=990) | First page of `GET /tenants/{id}/events` for the first UTC day of the deliveries, which is in MinIO buckets |
| Hot range read latency | p50 1.3 ms, p95 4.6 ms, p99 7.8 ms, max 25.0 ms (n=990) | First page for the last UTC day of the deliveries, which is in Postgres |
| Slowest state reads | t_0000 35.1 ms, t_0001 22.0 ms, t_0004 21.7 ms | Maximum per tenant over the 5 rounds |
| Hot bytes per event | 1,807.9 | `pg_total_relation_size('hot_events') / count(*)`: table, indexes and TOAST |
| Cold bytes per event | 271.5 | `sum(bytes) / sum(events)` from `cold_manifest`: sealed object sizes |
| Index bytes per cold event | 330.8 | `pg_total_relation_size` of `customer_days` plus `sku_moves`, divided by the cold event count |

`n=990` is 198 tenants × 5 rounds. The data set erases two tenants; they answer `410`, so `cmd/bench` skips them.

### Peak memory

| Service | Process peak RSS | Container peak, sampled |
|---|---|---|
| api1 | 30.9 MiB | 15.5 MiB |
| api2 | 27.8 MiB | 15.2 MiB |
| worker | 22.3 MiB | 9.8 MiB |
| postgres | 27.5 MiB (postmaster only) | 363.1 MiB |
| minio | 335.6 MiB | 446.1 MiB |

The two columns are measured differently:
- **Process peak RSS** is `VmHWM` of PID 1 from `/proc/1/status`, read at the end of the run. For the api, the worker and MinIO this is the whole server. For Postgres it is only the postmaster; backends are not included.
- **Container peak, sampled** is cgroup `memory.current`, sampled every 2 seconds, which includes page cache. A peak shorter than 2 seconds can fall between samples, which is why the api and worker samples are below their process peak.

## Not measured

- **Medium (about 1M deliveries) and large (about 5M) sets.** Not run. Generate one with `python3 $INFRA/generate.py --scale medium --out <dir>`, then run `INFRA=$INFRA part2/scripts/benchmark.sh <dir>`.
- **The noisy-neighbour limits** (1 GiB and 2 CPUs per service). Not applied.
