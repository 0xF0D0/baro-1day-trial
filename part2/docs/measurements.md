# Measurements

Measured with `part2/scripts/benchmark.sh` on the supplied data set (`$INFRA/data`). Every number below comes from one run, and nothing is estimated. The method for each one is the script's own.

## Machine and settings

- **Host:** Apple M2 Pro, 12 CPUs, 32 GiB RAM.
- **Docker:** 24.0.2, with 6 CPUs and 7.8 GiB memory.
- **Stack:** compose defaults: two api nodes behind nginx, one worker, Postgres 17 and MinIO. The only override is `FLUSH_INTERVAL=10s`, so the run settles quickly.
- **Load:** `replay.py` at its default concurrency of 8. Reads come from `cmd/bench`: 5 rounds over all tenants at concurrency 8.

## Data set

- **Deliveries:** 100,560 for 200 tenants, including duplicates, forgeries and erasures.
- **Stored after the run:** 97,788 events, 23,214 hot and 74,574 cold. 111 tenants have cold data on the first day.
- **`verify.py`:** `PASS`, with state 200/200, isolation 0 and ranges 48/48.

## Results

| Measure | Value | Method |
|---|---|---|
| Ingest throughput | 1,189 deliveries/s (100,560 in 84.6 s, 0 retries, 0 never succeeded) | `replay.py`'s own `done:` line, through the load balancer. Closed loop: `replay.py` at its fixed concurrency of 8, through nginx, with the worker flushing every 10 s. It measures the system under that client, not its ceiling. |
| State read latency | p50 4.7 ms, p95 22.8 ms, p99 60.4 ms, max 267.8 ms (n=990) | Measured on the client, `GET /tenants/{id}/state` through nginx. The first read per api node misses the snapshot cache and later reads hit it. Tenants with no cold data have no snapshot, so their state is a hot read. |
| Cold range read latency | p50 5.0 ms, p95 28.5 ms, p99 71.5 ms, max 199.1 ms (n=555, 111 tenants) | First page of `GET /tenants/{id}/events` for the first UTC day of the deliveries, which is in MinIO buckets. Sent only to the 111 tenants that have a `cold_manifest` row for the earliest manifest day. The other tenants have too few events for the watermark to flush a day, so a first-day read there would be a hot read. |
| Hot range read latency | p50 2.0 ms, p95 9.7 ms, p99 21.7 ms, max 74.7 ms (n=990) | First page for the last UTC day of the deliveries, which is in Postgres. Some tenants have no event on that day, so their page is empty but still a hot read. |
| Slowest state reads | t_0053 267.8 ms, t_0054 190.5 ms, t_0052 181.1 ms | Maximum per tenant over the 5 rounds |
| Hot bytes per event | 583.7 | `pg_total_relation_size('hot_events') / count(*)`: table, indexes and TOAST. Measured after `VACUUM FULL` of `hot_events`, `customer_days` and `sku_moves`; flush deletes leave dead space that `DELETE` and autovacuum do not return. |
| Cold bytes per event | 271.5 | `sum(bytes) / sum(events)` from `cold_manifest`: sealed day-bucket bytes only. Snapshots and MinIO's on-disk overhead are excluded. |
| Index bytes per cold event | 279.1 | `pg_total_relation_size` of `customer_days` plus `sku_moves`, divided by the cold event count, after `VACUUM FULL` |

`n=990` is 198 tenants x 5 rounds. The data set erases two tenants; they answer `410`, so `cmd/bench` skips them. The cold range count is 111 tenants x 5 rounds. nginx opens a new upstream connection per request (no upstream keepalive); the bench client keeps `MaxIdleConnsPerHost` equal to the concurrency.

### Peak memory

| Service | Process peak RSS | Container peak, sampled |
|---|---|---|
| api1 | 30.0 MiB | 14.9 MiB |
| api2 | 30.7 MiB | 18.2 MiB |
| worker | 22.6 MiB | 10.7 MiB |
| postgres | 27.5 MiB (postmaster only) | 367.9 MiB |
| minio | 332.3 MiB | 446.6 MiB |

The two columns are measured differently:
- **Process peak RSS** is `VmHWM` of PID 1 from `/proc/1/status`, read at the end of the run. For the api, the worker and MinIO this is the whole server. For Postgres it is only the postmaster; backends are not included.
- **Container peak, sampled** is cgroup `memory.current`, sampled every 2 seconds, which includes page cache. A peak shorter than 2 seconds can fall between samples, which is why the api and worker samples are below their process peak.

## Not measured

- **Medium (about 1M deliveries) and large (about 5M) sets.** Not run. Generate one with `python3 $INFRA/generate.py --scale medium --out <dir>`, then run `INFRA=$INFRA part2/scripts/benchmark.sh <dir>`.
- **The noisy-neighbour limits** (1 GiB and 2 CPUs per service). Not applied.
