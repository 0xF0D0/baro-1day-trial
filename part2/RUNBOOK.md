# Runbook

One page for the operator. Settings are in `README.md`.

## Start

```sh
export INFRA=<supplied infrastructure dir>
export TENANTS_FILE=$INFRA/data/tenants.json      # compose refuses to parse without it
mkdir -p part2/out/secrets
docker compose -f part2/docker-compose.yml up -d --build --wait
part2/scripts/replay.sh "$INFRA/data"             # send all deliveries
part2/scripts/verify.sh "$INFRA/data"             # state, isolation and range checks
INFRA=$INFRA part2/scripts/benchmark.sh "$INFRA/data"
part2/scripts/crash.sh "$INFRA/data"              # kill -9 the worker during a replay
```

**`e2e.sh`, `benchmark.sh` and `crash.sh` wipe all storage (`down -v`) and rebuild the stack with their own settings.** Never run them against data you need.
A replay needs empty storage. Run `docker compose ... down -v` first, or use `part2/scripts/e2e.sh "$INFRA/data"`.
Compose settings: `FLUSH_INTERVAL` (default 5m), `FLUSH_MARGIN`, `SWEEP_INTERVAL` (default 1h), `GARBAGE_GRACE`, `SNAPSHOT_CACHE_TTL`. `SETTLE_SECONDS` is read by `e2e.sh` only.

## Scrape metrics

```sh
docker compose -f part2/docker-compose.yml exec -T api1 wget -qO- localhost:8080/metrics
docker compose -f part2/docker-compose.yml exec -T worker wget -qO- localhost:9100/metrics
```

nginx answers 404 for `/metrics`, so the api metrics are reachable only inside the compose network.
Storage gauges and job metrics come from the worker. Ingest and read metrics come from each api node.
No Prometheus server is bundled; point one at these endpoints to get rates and `histogram_quantile` percentiles.

## What to watch

| Metric | Act when | Meaning |
|---|---|---|
| `backbone_last_sweep_age_seconds` | above 7200 | The 2-hour erasure bound is broken. Check the worker. |
| `backbone_pending_tombstones` | above 0 for longer than one sweep | An erasure is not finishing. Read the worker log. |
| `backbone_dirty_tenants` | above 0 across several flush intervals | Rebuilds are not completing. |
| `backbone_job_errors_total` | rising | Read it by `class` (`postgres_<SQLSTATE>`, `object_not_found`, `canceled`, `other`) and by `job`. |
| `backbone_ack_seconds` | p99 well above its baseline | Ingest is slow. Check Postgres first. |
| `backbone_tier_events{tier="hot"}` | grows without bound | Flush has stalled. |
| `process_resident_memory_bytes` | keeps climbing | Memory pressure. Check the largest tenant's reads. |

## Recover from a crash

1. Restart the service: `docker compose -f part2/docker-compose.yml up -d <service>`.
2. Nothing is lost. Every change writes new objects first and commits once in Postgres, so a crash leaves the old or the new version.
3. Leftover objects are deleted by the next sweep. The worker also sweeps at startup.
4. Pending customer erasures finish in that sweep.
5. A dirty tenant is rebuilt on the next flush tick.
6. Check with `part2/scripts/tier-stats.sh "$INFRA/data"`. `pending` should be 0 after the next sweep and `dirty` 0 after the next flush tick.

`crash.sh` shows this on purpose. It ends with `verify.py` and the consistency checker, and writes `part2/out/<name>/crash-report.txt`.

## Erasure bound

- Reads and Postgres queries: the data is gone as soon as the erasure returns 2xx.
- MinIO and Postgres WAL files: gone within 2 hours (one sweep interval plus its run time), while the worker runs.
- The bound grows by the worker's downtime. A longer `SWEEP_INTERVAL` or `GARBAGE_GRACE` (default 10m) also extends it.
- Backups would add their retention. This setup has none.

## Known limits

Not covered, by design: deleted rows stay in Postgres table files until the space is reused, raw disk blocks below Postgres and MinIO, and the HMAC key kept in each tombstone.
See "Stated limits" in section 14 of the design spec, `../docs/superpowers/specs/2026-11-10-part2-brand-data-backbone-design.md`.
