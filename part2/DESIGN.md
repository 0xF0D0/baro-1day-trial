# Brand Data Backbone: Design

A Go service that ingests two vendors' webhooks for 200 tenants, keeps each tenant's state equal to `reducer.fold`, stores recent events in Postgres and older ones in MinIO, encrypts every payload with a per-tenant key, and erases customers and tenants across both tiers. The chosen deep dive is **crash safety**. The full design record is `docs/superpowers/specs/2026-11-10-part2-brand-data-backbone-design.md`; this document is the summary to read first.

## What is built and what is measured

| | Status |
|---|---|
| All five parts (ingest, tiers, reads, erasure, operations) | Built. `verify.py` passes on the supplied data at the final commit; earlier builds also passed fresh seeds 1, 2, 3, 7, 42 and 2026. |
| Crash safety deep dive | Built: named crash points, a `kill -9` harness and a consistency checker. Results below. |
| Measurements | Supplied data set only (`part2/docs/measurements.md`). Medium and large sets were not run. |
| Other deep dives | Proposals only (last section). |

Commands, each one line: `docker compose up`, `replay.sh`, `verify.sh`, `benchmark.sh`, `crash.sh` (see `README.md` and `RUNBOOK.md`).

## Storage and tiering

```
LB :8080 -> api nodes (2, stateless) -> Postgres (hot events, index tables, pointers, tombstones, locks)
                                     -> MinIO    (cold day buckets and one snapshot per tenant)
            worker (1): flush to cold, rebuild, sweep
```

- **Hot tier.** One Postgres row per event: tenant ID, event ID, `occurred_at_ms`, a keyed HMAC of the customer ID, and the canonical event as AES-GCM ciphertext. Ingest commits before it answers `2xx`.
- **Cold tier.** One encrypted object per tenant and UTC day (JSON lines in key order), plus one **snapshot** object: the fold state over every event before the tenant's `cold_until` boundary. Object names carry a random ID and are never reused.
- **Moving down.** Every 5 minutes the worker flushes each tenant's oldest hot day once it is 96 hours behind the tenant's recent events. It writes the bucket and a new snapshot, then commits in one transaction: pointers, the two index tables, `cold_until`, and deletion of exactly the rows it moved.
- **Reading.** State is the snapshot plus a fold of the hot rows (about 96–120 hours per tenant). Range reads merge the day buckets they need with hot rows, in `(occurred_at_ms, event_id)` order, with a signed cursor. Api nodes cache the decrypted snapshot per tenant for up to an hour, keyed by its immutable name; a janitor deletes expired entries and an erasure drops the tenant's entry.
- **Index tables.** `customer_days` (which day buckets hold a customer) and `sku_moves` (encrypted inventory movements per keyed SKU) let an erasure open only the buckets it needs and refold only the SKUs it touches.

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
  2. Under the tenant's cold-writer lock, rewrite only the day buckets that `customer_days` lists, and remove the customer from the snapshot. Orders are removed whole; only the affected SKUs are refolded.
  3. Commit the new pointers and delete the customer's hot and index rows.

  `2xx` means the customer is gone from state, reads and every current object. A request that dies midway is retried by the client or finished by sweep.
- **Tenant.** One transaction marks the tenant erased and deletes its wrapped DEK and all its rows. Its objects become unreadable at once, and sweep deletes the prefix. Genuine later deliveries get `410`, forged ones `401`.
- **Stated bound.** Data is out of reads and Postgres queries at `2xx`. It is gone from MinIO and Postgres WAL within **2 hours** while the worker runs: the hourly sweep deletes replaced objects after a 10-minute grace, then runs `VACUUM`, `pg_switch_wal()` and `CHECKPOINT` with WAL recycling off.
- **Stated limits.** Deleted rows stay inside Postgres table files until the space is reused (encrypted with a live tenant DEK). Raw disk blocks and backups are not covered. Tombstones keep the customer's keyed HMAC so later events stay blocked.
- **Assumption:** all events of one order belong to the customer who created it.

## Deep dive: crash safety

**Claim.** Every change to stored data follows one rule: write new immutable objects, then make them current in one Postgres transaction. A `kill -9` at any point therefore leaves either the old version or the new one, plus unreferenced objects that sweep deletes. Ingest is a single `INSERT` committed before `2xx`.

**Scope.** Tier moves (flush) and compaction (rebuild), killed in the worker. Api, Postgres and MinIO kills are not exercised.

**Evidence.**
1. **Six named crash points**, in flush and rebuild: after the bucket write, after the snapshot write, and just before commit. `TestCrashPoints` hits each one on purpose and shows four things:
   - nothing was committed: pointers, manifest, garbage, hot rows and index rows are unchanged;
   - the next run completes;
   - sweep removes the leftovers;
   - an audit of the tenant is clean.
2. **`crash.sh`** replays the supplied data with a 1-hour margin, 2-second flushes and 10-second sweeps. Meanwhile it `kill -9`s the worker at random and arms the crash points at a low probability. Last run:
   - 11 kills landed on a running worker;
   - flush crash points fired 26 times;
   - about 40 rebuilds ran;
   - `verify.py` passed.
3. **A checker** compares storage with the replay's acknowledgements. Expected events are every acknowledged event minus erased customers and tenants. Stored events are hot and cold, counted per occurrence. It also checks:
   - pointers, unreferenced objects and garbage;
   - the index tables, rebuilt from the buckets;
   - three tier invariants;
   - that the served state equals a full fold.
4. **Results.**
   - Right after a final `kill -9`, before any repair: lost 0, duplicate 0, bad pointer 0, state, index and invariant mismatches 0. Only leftovers for sweep remained.
   - After the settle and a grace-0 sweep: every count is 0, with expected = stored = 97,788 events.

**Gap.** At the chaos run's probability the three rebuild crash points rarely fire, because there are about 40 rebuilds against thousands of flushes. The in-process test covers them.

## Other deep dives (proposals, not built)

**Cold hydration.** A fully cold tenant's state is already one snapshot read, so the cost is a cold range scan. The plan:
- measure per-day bucket GET, decrypt and parse times for a 1M-event tenant;
- prefetch the next buckets of a range scan in parallel;
- split large days into fixed-size encrypted chunks so a page reads one chunk instead of a whole day;
- keep a small decrypted LRU of hot buckets on each api node.

**Noisy neighbors.**
- **Limits.** Run each service with a 1 GiB and 2-CPU limit.
- **Fairness.** Ingest goes through a per-tenant token bucket, and Postgres connection pools are split between ingest and reads, so the largest tenant's burst cannot take every connection. The worker processes one tenant at a time with a time budget per pass, so a big rebuild yields between days.
- **Evidence.** Plot small-tenant read p99 while the largest tenant ingests and rebuilds.

**Beyond one node.**
- **Placement.** Tenants map to shards by consistent hashing. Each shard has its own Postgres and a MinIO bucket prefix, and a small directory maps tenant to shard.
- **Rebalancing.** Copy the tenant's cold objects and snapshot, dual-write ingest for the hot tail, then switch the directory entry in one step.
- **Node failure mid-compaction.** This is the crash-safety rule again: an unfinished flush or rebuild leaves only unreferenced objects, and the next worker that takes the tenant's lock redoes it.
- **Throughput.** A few thousand events per second is mostly connection count and fsync rate per shard.

## What is next

1. **Run the benchmark on the medium and large sets.** On the large set, measure the hot-tail fold of the largest tenant.
2. **Reducer v2.** The SPEC hints at it with `shipment.patch`. Events are stored unchanged and each snapshot records its reducer version, so the plan is:
   - rebuild every tenant into v2 snapshots in the background;
   - keep serving v1 until every tenant is done;
   - switch in one transaction.

   Readers see consistent v1 state until the switch. A new metric over hot and cold history would use the same backfill.
3. Postgres row-level security, and the DEKs in a KMS.
