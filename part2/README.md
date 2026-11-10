# Part 2: Brand Data Backbone

A Go service that ingests vendor webhooks into an encrypted Postgres table and serves state and range reads, with customer and tenant erasure. Two api nodes sit behind an nginx load balancer on port 8080.

## Requirements

Docker with Compose v2, Python 3 (only for the supplied `replay.py` and `verify.py`), and the supplied `infrastructure/` folder.

## Environment

| Variable | Used by | Meaning |
|---|---|---|
| `INFRA` | scripts | Path of the supplied `infrastructure/` folder (not in this repository). Required. |
| `TENANTS_FILE` | compose | Absolute path of the `tenants.json` to load. Required for every `docker compose` command, including `down` and the Postgres-only command, because the compose file refuses to parse without it. The scripts set it from the data directory. |
| `BACKBONE_TEST_DATABASE_URL` | Go tests | Postgres to test against, `postgres://postgres@127.0.0.1:55432/postgres?sslmode=disable` for the Postgres-only container below. Without it the store and api tests skip. |
| `BACKBONE_TENANTS_FILE`, `BACKBONE_KEK_FILE`, `BACKBONE_DATABASE_URL` | api | Set by compose. `BACKBONE_LISTEN` is optional (default `:8080`). |
| `TARGET` | replay, verify | Service URL, default `http://localhost:8080`. |

The key-encryption key (32 random bytes) is created once by the `kek-init` service in the `secrets` volume.

## Run

```sh
export INFRA=~/Downloads/BARO_Work_Trial/infrastructure
export TENANTS_FILE=$INFRA/data/tenants.json
docker compose -f part2/docker-compose.yml up -d --build --wait
part2/scripts/replay.sh "$INFRA/data"   # sends all deliveries, writes part2/out/<name>/replay_responses.json
part2/scripts/verify.sh "$INFRA/data"   # state, isolation and range checks
```

A replay must start from empty storage: run `down -v` (see Stop) before `up`, or use `scripts/e2e.sh`. Replaying again over existing data makes deliveries from before a tenant's erasure get 410, and verify fails.

Each script takes the data directory as its only argument.

## End to end

`part2/scripts/e2e.sh <data-dir>` destroys the stack and its volumes, starts it from empty storage with that directory's `tenants.json`, replays and verifies. It exits with the verifier's exit code.

```sh
part2/scripts/e2e.sh "$INFRA/data"
python3 "$INFRA/generate.py" --seed 7 --out /path/to/seed7 && part2/scripts/e2e.sh /path/to/seed7
```

## Stop

`TENANTS_FILE` must be set for these too.

```sh
export TENANTS_FILE=$INFRA/data/tenants.json
docker compose -f part2/docker-compose.yml down      # keep data
docker compose -f part2/docker-compose.yml down -v   # also drop the database and the KEK
```

## Go tests

Postgres alone is published on `127.0.0.1:55432`:

```sh
export TENANTS_FILE=$INFRA/data/tenants.json
docker compose -f part2/docker-compose.yml up -d --wait postgres
(cd part2/backbone && BACKBONE_TEST_DATABASE_URL='postgres://postgres@127.0.0.1:55432/postgres?sslmode=disable' go test -race -count=1 ./...)
docker compose -f part2/docker-compose.yml down
```
