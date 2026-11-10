# Brand Data Backbone: Design

A Go service that ingests two vendors' webhooks for 200 tenants, keeps each tenant's state equal to `reducer.fold`, stores recent events in Postgres and older ones in MinIO, encrypts every payload with a per-tenant key, and erases customers and tenants across both tiers. The chosen deep dive is **crash safety**. The full design record is `docs/superpowers/specs/2026-11-10-part2-brand-data-backbone-design.md`; this document is the summary to read first.

## What is built and what is measured

| | Status |
|---|---|
| All five parts (ingest, tiers, reads, erasure, operations) | Built. At the final commit `verify.py` passes on the supplied data and on a freshly generated seed (11); earlier builds also passed seeds 1, 2, 3, 7, 42 and 2026. |
| Crash safety deep dive | Built: named crash points, a `kill -9` harness and a consistency checker. Results below. |
| Measurements | Supplied data set only (`part2/docs/measurements.md`). Medium and large sets were not run. |
| Other deep dives | Proposals only (last section). |

Commands, each one line: `docker compose up`, `replay.sh`, `verify.sh`, `benchmark.sh`, `crash.sh` (see `README.md` and `RUNBOOK.md`).

## Storage and tiering

**The insight that shaped cold storage.** The reducer's state is mostly counts, sums and maps keyed by order or customer, and an order belongs to one customer (our stated assumption). A folded **snapshot** therefore lets us remove a customer by subtraction instead of refolding history; `last_contact_ms` is a max, so the snapshot keeps the max per day. The only order-dependent, cross-customer part is inventory and oversold, so we keep a per-SKU movement log and refold just the SKUs a customer touched. Hence the schema below. Objects are never edited in place: a change writes a new version under a new name, and one Postgres transaction switches the pointers.

```
LB :8080 -> api nodes (2, stateless) -> Postgres (hot events, index tables, pointers, tombstones, locks)
                                     -> MinIO    (cold day buckets and one snapshot per tenant)
            worker (1): flush to cold, rebuild, sweep
```

### Cold schema

**MinIO objects.** Each object is sealed with AES-GCM under the tenant DEK, with additional data binding the tenant and the object name. Names carry a random ID and are never reused.

| Object | Name | Content |
|---|---|---|
| Day bucket | `<tenant>/buckets/<YYYY-MM-DD>/<id>.jsonl.enc` | That UTC day's canonical events, one JSON line each, sorted by `(occurred_at_ms, event_id)` |
| Snapshot | `<tenant>/snapshot/<id>.json.enc` | `{version, cold_until, state}`. `state` is the fold over every event before `cold_until`. See the field list below. |

The snapshot's `state` holds:
- `event_count`;
- `customers`, the set of customer keys (hex HMAC; no raw ID);
- `orders`, `order_id` → gross, refunded and status;
- `inventory` and `oversold` per SKU;
- `messages_by_channel`;
- `last_message_by_day`, which is day → latest message time and is used to recompute `last_contact_ms`;
- `campaigns`, with spend, impressions and clicks;
- `orphan_refunds` and `orphan_shipments`.

**Postgres tables: what is current.** Plaintext columns are limited to tenant and event IDs, times, day numbers and keyed HMACs. Everything else is ciphertext.

| Table | Primary key | Role |
|---|---|---|
| `tenant_cold` | tenant | `cold_until` (a UTC day boundary), current `snapshot_object`, `reducer_version`, `dirty` |
| `cold_manifest` | tenant, day | current bucket `object`, `events`, sealed `bytes` |
| `garbage` | object | objects a commit replaced, and `replaced_at`, for sweep |
| `customer_days` | tenant, customer_key, day | which day buckets hold a customer |
| `sku_moves` | tenant, sku_key, occurred_at_ms, event_id, line_no | one cold inventory movement. `value` is sealed `{sku, kind, amount}`: an adjustment, or a line of the first `order.created` |
| `hot_events` | tenant, event_id | hot tier: `occurred_at_ms`, `customer_key`, sealed canonical event |
| `tombstones` | tenant, customer_key | erased customers, `pending` or `done` |

### How the tiers work

- **Ingest.** One encrypted row in `hot_events`, committed before `2xx`.
- **Moving down.** Every 5 minutes the worker flushes each tenant's oldest hot day once it is 96 hours behind the tenant's recent events. It writes the bucket and a new snapshot. One transaction then upserts `cold_manifest`, moves `tenant_cold`, inserts the day's `customer_days` and `sku_moves` rows, records the replaced objects in `garbage`, and deletes exactly the hot rows it moved.
- **Reading.**
  - **State** is the snapshot plus a fold of the hot rows, about 96–120 hours per tenant.
  - **Range reads** merge the manifest's day buckets with hot rows in `(occurred_at_ms, event_id)` order, with a signed cursor.
  - **Snapshot cache.** Api nodes cache the decrypted snapshot per tenant for up to an hour, keyed by its name. A janitor deletes expired entries, and an erasure drops the tenant's entry.

## Late-event correctness

Correctness never depends on the SPEC's 72-hour lateness or on observed delays; those only tune the 96-hour margin.

- **Dedup across all history.** A redelivery is checked against hot rows and, if older than `cold_until`, against that day's bucket. A duplicate returns `2xx` and changes nothing.
- **A late new event** (older than `cold_until`) is inserted into hot and marks the tenant **dirty** in the same transaction. Reads of a dirty tenant fold every bucket and every hot row, which is slow but exact. On the next tick the worker **rebuilds** the tenant: it merges the late rows into their day buckets, recomputes the snapshot and index rows from every bucket, and clears `dirty` unless another late row arrived meanwhile.
- **Order-dependent folds** (inventory, oversold, first `order.created`) are therefore always folded in key order. With a 1-hour margin to force late events, the supplied data produces 37 to 48 rebuilds per run and still passes `verify.py`.

## Tenant isolation

- **By construction.** Middleware turns the bearer token into a tenant scope once. Storage functions take that scope and have no tenant-ID parameter, so a handler cannot ask for another tenant's rows.
- **By key.** Each tenant has its own DEK, wrapped by a KEK. Payload, HMAC, cursor and object sub-keys are derived from it, and AES-GCM additional data binds the tenant (and the event ID or object name). Another tenant's rows and objects would not even decrypt. MinIO objects live under per-tenant prefixes.
- **Not built:** Postgres row-level security as a third layer (production hardening).

## Erasure

- **Customer.** Synchronous, on any api node:
  1. Commit a tombstone. From then on, ingest drops that customer's events, including future arrivals.
  2. Under the tenant's cold-writer lock, rewrite only the day buckets that `customer_days` lists, and subtract the customer from the snapshot. Orders are removed whole; only the affected SKUs are refolded from `sku_moves`.
  3. Commit the new pointers and delete the customer's hot and index rows.

  `2xx` means the customer is gone from state, reads and every current object. A request that dies midway is retried by the client or finished by sweep.
- **Tenant.** One transaction marks the tenant erased and deletes its wrapped DEK and all its rows. Its objects become unreadable at once, and sweep deletes the prefix. Genuine later deliveries get `410`, forged ones `401`.
- **Stated bound.** Data is out of reads and Postgres queries at `2xx`. It is gone from MinIO and Postgres WAL within **2 hours** while the worker runs: the hourly sweep deletes replaced objects after a 10-minute grace, then runs `VACUUM`, `pg_switch_wal()` and `CHECKPOINT` with WAL recycling off.
- **Stated limits.** Deleted rows stay inside Postgres table files until the space is reused (encrypted with a live tenant DEK). Raw disk blocks and backups are not covered. Tombstones keep the customer's keyed HMAC so later events stay blocked.
- **Assumption:** all events of one order belong to the customer who created it.

## Deep dive: crash safety

**Claim.** Every change to stored data follows one rule: write new objects (never edit one in place), then make them current in one Postgres transaction. A `kill -9` at any point therefore leaves either the old version or the new one, plus unreferenced objects that sweep deletes. Ingest is a single `INSERT` committed before `2xx`.

**Scope.** Tier moves (flush) and compaction (rebuild), killed in the worker. Api, Postgres and MinIO kills are not exercised.

**Evidence.**
1. **Six named crash points** in flush and rebuild: after the bucket write, after the snapshot write, and just before commit. `TestCrashPoints` hits each one. Each time, nothing was committed, the next run completes, sweep removes the leftovers, and an audit of the tenant is clean.
2. **`crash.sh`** replays the supplied data with a 1-hour margin, 2-second flushes and 10-second sweeps, while it `kill -9`s the worker at random and arms the crash points at a low probability. Last run on `main`: 12 kills landed on a running worker, 37 rebuilds ran, and `verify.py` passed.
3. **A checker** compares storage with the replay's acknowledgements: every acknowledged event, minus erased customers and tenants, against hot and cold counted per occurrence. It also checks pointers, unreferenced objects, garbage, the index tables rebuilt from the buckets, three tier invariants, and the served state against a full fold.
   - **Right after a final `kill -9`, before any repair:** lost, duplicates, bad pointers, and state, index and invariant mismatches are all 0. Only leftovers for sweep remain.
   - **After the settle and a grace-0 sweep:** every count is 0, with expected = stored = 97,788.

**Gap.** At the chaos run's probability the three rebuild crash points rarely fire, because there are about 40 rebuilds against thousands of flushes. The in-process test covers them.

## Other deep dives (proposals, not built)

**Cold hydration.** A fully cold tenant's state is already one snapshot read, so the cost is the cold range scan. Measure bucket GET, decrypt and parse per day for a 1M-event tenant. Then prefetch the next buckets in parallel, split large days into fixed-size encrypted chunks so a page reads one chunk, and keep a small decrypted LRU of buckets on each api node.

**Noisy neighbors.** Give each service a 1 GiB and 2-CPU limit. Put a per-tenant token bucket on ingest and split the Postgres pools between ingest and reads, so one tenant's burst cannot take every connection. Have the worker take one tenant at a time with a time budget per pass, so a big rebuild yields between days. Prove it with small-tenant read p99 while the largest tenant ingests and rebuilds.

**Beyond one node.** Consistent hashing maps tenants to shards, each with its own Postgres and MinIO prefix, through a small tenant-to-shard directory. Rebalancing copies the cold objects and snapshot, dual-writes the hot tail, then switches the directory entry in one step. A node failure mid-compaction is the crash-safety rule again: an unfinished flush or rebuild leaves only unreferenced objects, and the next worker to take the tenant's lock redoes it.

## What is next

1. Benchmark the medium and large sets, including the hot-tail fold of the largest tenant.
2. Reducer v2, which the SPEC hints at with `shipment.patch`. Events are stored unchanged and snapshots record their version, so every tenant is rebuilt into v2 snapshots in the background and the switch happens in one transaction. Readers keep consistent v1 state until then; a new metric over hot and cold history would use the same backfill.
3. Postgres row-level security, and the DEKs in a KMS.
