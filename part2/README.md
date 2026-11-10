# Part 2: Brand Data Backbone

A Go service that ingests vendor webhooks into an encrypted Postgres hot table and serves state and range reads, with customer and tenant erasure. A worker moves older events into encrypted day buckets in MinIO (the cold tier), and reads span both tiers. Two api nodes sit behind an nginx load balancer on port 8080.

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

## Worker and tier statistics

The `worker` compose service runs the same image with the `worker` binary. Every flush interval it walks the tenant registry and flushes one day at a time per tenant until nothing is left to flush, moving events older than the watermark from `hot_events` into encrypted day buckets in MinIO. The watermark is the rank-th largest event time among a tenant's hot events minus the margin, in event time, not wall-clock time. It logs one line per tick with the number of days flushed and the tick duration; a failing tenant is logged by tenant ID only, and the loop continues. It stops cleanly on SIGTERM.

`part2/scripts/tier-stats.sh <data-dir>` prints `hot=<rows in hot_events> cold=<events in cold buckets> dirty=<tenants marked dirty>` from the running Postgres. `e2e.sh` uses a 2s flush interval (override with `FLUSH_INTERVAL`) so the cold tier is exercised during the replay, and runs `tier-stats.sh` after verify; its exit code is still the verifier's.

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
