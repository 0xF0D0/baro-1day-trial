# Part 2 Brand Data Backbone: Design

- Date: 2026-11-10
- Status: draft for review
- Inputs: the brief (`BARO_Work_Trial.pdf`, pages 3 and 4), `infrastructure/README.md`, `infrastructure/SPEC.md`, `infrastructure/reducer.py`, and the analysis in `part2/docs/analysis.md`. The `infrastructure/` folder is not in this repository yet; this document calls its location `$INFRA`.
- Decisions are marked by who made them. **User** means the decision came from the design discussion. **Designer's call** means the designer chose it and the user has not confirmed it yet (see §19).

## 1. Intent

Build a service that receives webhooks from two vendors for many tenants and keeps each tenant's data correct, private and durable. A tenant's current state must equal `reducer.fold()` over every retained event, even though events arrive late, out of order, twice, or forged, and even though a customer can be erased at any time, retroactively.

The hard part is not the fold. The fold is fully specified and an in-memory oracle already reproduces every expected hash (`part2/analysis/oracle.py`). The hard part is producing that answer while keeping durability, two storage tiers, per-tenant encryption, erasure and tenant isolation correct at the same time.

The design favors the simplest structure that stays correct (User). Every speed-up has a slower path that is always correct: the full rebuild in §12. The one speed-up built from the start is incremental customer erasure (§11.1), because a requirement forces it. `replay.py` gives each request 10 seconds, and the generator always plans three customer erasures for the largest tenant, which has about one million events at large scale. Rebuilding that tenant from cold inside one erasure request would risk the timeout.

## 2. Goals, non-goals, anti-goals

### Goals
1. Pass `verify.py` on the supplied data and on a fresh seed, starting from empty storage, with the tenants file path given by configuration.
2. Acknowledge an event only after it is durable. A `kill -9` at any moment must not lose an acknowledged event, duplicate an event, or leave a half-written state visible to readers.
3. Keep recent events in a hot tier (Postgres) and older events in a cold tier (MinIO), with state reads that do not touch cold objects in the normal case.
4. Erase a customer or a tenant from every tier and every derived structure, block later arrivals, and state a time bound for physical removal.
5. Make cross-tenant access structurally impossible, not just filtered.
6. Expose the reported numbers as Prometheus metrics and provide a one-page runbook.
7. Deep dive: **crash safety** (User), proven by a fault-injection script.

### Non-goals
- A second reducer version. The design keeps raw canonical events and versions the snapshot so a later reducer can be backfilled (§17), but only v1 is built.
- Backups, KMS, read replicas, more than one worker, and automatic sharding. The design says where they would go in production.
- The other three deep dives beyond one paragraph each in the submitted design document.

### Anti-goals (would count as failure even if `verify.py` passes)
- Correctness that depends on a dataset observation rather than the SPEC. Measured values (72-hour lateness, 76-hour redelivery, erasure frequency) may tune performance but must never be required for a correct answer. The only exceptions are the domain assumptions the user accepted, listed in §18.
- Plaintext `customer_id` or PII anywhere outside the encrypted payload, including logs and metrics labels.
- Tiering, watermarks or retention driven by the wall clock. The replay clock is simulated (events are dated July to September 2026).
- A single process whose death stops ingest (User: no single point of failure on the ingest path).
- Consistent hashing or Redis to route reads (User).

## 3. Fixed inputs and constraints

- **Service interface**: exactly as in `SPEC.md`. Port 8080. Webhooks at `POST /webhooks/vendor-a` and `POST /webhooks/vendor-b`. Reads at `GET /tenants/{id}/state` and `GET /tenants/{id}/events?from_ms=&to_ms=&limit=&cursor=` with the tenant token. Erasure at `DELETE /tenants/{id}/customers/{customer_id}` and `DELETE /tenants/{id}` with the admin token.
- **Response codes**: reject with `4xx` (unknown tenant, bad signature, malformed). `replay.py` retries `5xx` and connection errors up to 10 attempts with a 10-second timeout per request, and never retries `4xx`. Genuine deliveries for an erased customer get `2xx` and are dropped. Genuine deliveries for an erased tenant get `2xx`, `404` or `410`, never `401`. Forged deliveries always get `4xx`. Reads of an erased tenant with its own token get `404` or `410`. A token used on another tenant's path gets `404` before the erased check (`410` is not allowed there).
- **Ordering**: state and range reads use `(occurred_at_ms, event_id)` with byte-wise (code point) comparison of `event_id`. Postgres columns that sort `event_id` use `COLLATE "C"`.
- **No timestamp tolerance** on vendor A signatures.
- **Configuration**: tenants file path by flag or environment variable. No tenant IDs or secrets in code. The KEK comes from an environment variable or file that stands in for a secret store.
- **Language**: Go (User).

## 4. Architecture

```
            LB (port 8080)
           /      |       \
      api node  api node  ...      ingest, reads, erasure (stateless, N >= 2)
           \      |       /
            Postgres  ---------  hot events, indexes over cold, manifest, pointers, tombstones, locks
               |
            MinIO     ---------  cold day buckets, snapshots (per tenant prefix)
               |
            worker (1)  -------  flush to cold, sweep, rebuilds
```

- api nodes are stateless and interchangeable (User). Any of them can ingest, read or erase. Losing one loses nothing.
- One worker runs background jobs (User). If it is down, ingest, reads and erasure keep working; only flushing, rebuilds and sweep pause. Erasure does not depend on the worker (§11).
- Postgres, MinIO and the LB are single containers in `docker compose` and would be managed services in production (User).
- `docker compose up` starts the LB, two api nodes, one worker, Postgres and MinIO. Two api nodes follow from the user's rule that ingest must not depend on one process. The LB is the builder's choice.

## 5. Ingest

1. Read only `account` (vendor A) or `shop_domain` (vendor B) from the raw body to pick the tenant. No match: `404`. Unparseable body: `400`.
2. Verify the signature over the exact received bytes with that tenant's secret. Failure: `401`. Signing secrets come from the tenants file and survive tenant erasure, so a forged delivery to an erased tenant still gets `4xx`.
3. Normalize to the canonical event per the SPEC table. `data/normalization_examples.json` wins if the table and the examples ever disagree. Unknown types keep their type and their payload verbatim, and take `customer_id` from the payload if present.
4. Compute `customer_key = HMAC(tenant key, customer_id)` when `customer_id` is not null.
5. In one Postgres transaction:
   - take the shared tenant-status lock (§13). If the tenant is erased, return `410` (Designer's call; `2xx` or `404` would also pass);
   - if `customer_key` is set, take the shared customer lock and check the tombstone. If the customer is erased, commit nothing and return `2xx`;
   - if `occurred_at_ms < cold_until + 1 day`, take the shared cold lock and read `cold_until` again. If the event is now late (`occurred_at_ms < cold_until`), follow §12;
   - otherwise `INSERT ... ON CONFLICT (tenant_id, event_id) DO NOTHING` into the hot table.
6. Commit with `synchronous_commit = on`, then return `2xx` (User: `2xx` only after commit). A duplicate returns `2xx` without changing anything.

Any internal error returns `5xx` so the sender retries.

## 6. Hot tier (Postgres)

Hot table, one row per event:

| Column | Notes |
|---|---|
| `tenant_id` | plaintext |
| `event_id` | plaintext, `COLLATE "C"` |
| `occurred_at_ms` | plaintext, bigint |
| `customer_key` | HMAC, nullable |
| `payload` | the canonical event, AES-GCM encrypted with the tenant DEK; AAD binds tenant and event_id |

Primary key `(tenant_id, event_id)`. Indexes on `(tenant_id, occurred_at_ms, event_id)` and `(tenant_id, customer_key)`. The hot tier holds every event with `occurred_at_ms >= cold_until`, which in steady state is the last 96 to 120 hours of event time for that tenant (§10), plus any late event still waiting for a rebuild (§12).

Other Postgres tables (names are the builder's choice):
- `tenants`: status (active or erased), erased time.
- `tenant_keys`: the tenant DEK wrapped by the KEK.
- `tenant_cold`: `cold_until`, current snapshot object, reducer version, `dirty` flag.
- `cold_manifest`: one row per tenant and day: current bucket object, generation, event count, bytes.
- `tombstones`: `(tenant_id, customer_key)`, status (pending or done), requested time.

Postgres is the single source of truth for which cold objects are current. A cold object that no pointer references is garbage.

### 6.1 Indexes over cold data (User: Postgres tables)

Two tables let an erasure touch only what it needs instead of opening every day bucket. Their rows are written in the same transaction as the flush that moves the data (§10), so an index can never miss an entry for a committed bucket.

- **`customer_days`** `(tenant_id, customer_key, day)`, primary key on all three. One row for each customer and each day bucket that holds that customer's events. Erasure reads it to find the buckets to open (§11.1).
- **`sku_moves`** `(tenant_id, sku_key, occurred_at_ms, event_id, line_no, value)`, primary key `(tenant_id, sku_key, occurred_at_ms, event_id, line_no)` with `event_id` in `COLLATE "C"`. `line_no` keeps the reducer's line order and allows two lines of one order with the same SKU. One row for each inventory movement in cold: an `inventory.adjusted` delta, or a line of the first `order.created` for its `order_id` (later duplicates do not touch inventory). `sku_key` is `HMAC(tenant key, sku)`. `value` holds the SKU, the kind and the amount, encrypted with the tenant DEK. Erasure reads it to refold only the affected SKUs (§11.1).

The plaintext rule for every Postgres table is the same: tenant ID, event ID, `occurred_at_ms`, day numbers and keyed HMACs are plaintext; everything else is ciphertext (Designer's call).

The cost is size. On the supplied data there are about 0.66 `customer_days` rows and 0.5 `sku_moves` rows per retained event, roughly 180 bytes per event in Postgres with row and index overhead, kept for as long as the events are kept. That is about 1 GB for the large data set. Lookups stay fast as the tables grow; only disk use grows. If Postgres size ever matters, the production path is to move both tables to MinIO as sorted, block-encrypted files (a base plus daily deltas, merged by compaction, read by range requests). This is not built.

## 7. Cold tier (MinIO)

Layout per tenant prefix (object names carry a generation so an object is never overwritten):

```
<tenant>/snapshot/<gen>.json.enc
<tenant>/buckets/<YYYY-MM-DD>/<gen>.jsonl.enc
```

All objects are encrypted with the tenant DEK (AES-GCM, AAD binds tenant and object name).

### 7.1 Day buckets (User: time-bucketed JSON, one day per bucket)
One object per tenant and UTC day of `occurred_at_ms`. It holds that day's canonical events as JSON lines, sorted by `(occurred_at_ms, event_id)`. A bucket is written once when its day is flushed and rewritten only by erasure or by a rebuild.

### 7.2 Snapshot
The fold state over every event before `cold_until`, as one object:
- `reducer_version`, `cold_until`;
- `event_count`, the customer key set, `orphan_refunds`, `orphan_shipments`;
- orders by `order_id`: gross, refunded, status;
- inventory and oversold by SKU;
- `messages_by_channel`, campaigns;
- the latest `message.received` time per day bucket (one number per day), so `last_contact_ms` can be recomputed when a bucket changes.

The snapshot holds enough to continue the fold exactly where it stopped. The port of `reducer.fold` must be able to start from a snapshot and must give the same hash as `reducer.fold` over all events.

## 8. State reads

1. Authenticate the tenant token. Token tenant differs from path tenant: `404`. Path tenant erased: `410`.
2. In one `REPEATABLE READ` transaction, read the `tenant_cold` row (snapshot pointer, `dirty`) and the tenant's hot rows in key order.
3. If not dirty: load the snapshot (from the api node's cache if present), fold the hot rows onto a copy, and return the 16-field result.
4. If dirty (§12): fold every bucket in the manifest and every hot row in key order. This is slow but correct, and only happens between a late-event arrival and the worker's rebuild.

Snapshot cache (Designer's call): each api node caches decrypted snapshots keyed by object name. Object names are immutable, so a cached copy is never stale for the pointer that was read in the same transaction. Entries expire after 1 hour so erased data does not linger in memory past the physical-removal bound.

Because every hot event has `occurred_at_ms >= cold_until` and every snapshot event is before it, "snapshot, then hot rows in key order" equals the fold over all events. Events with the same `occurred_at_ms` never straddle the boundary because the cut is on `occurred_at_ms`.

## 9. Range reads (`/events`)

- Merge two sorted streams in key order: cold buckets for the days in `[from_ms, to_ms)` that are before `cold_until`, read through the manifest in the same transaction; and hot rows in the range. Always merging both also covers late events waiting in hot.
- `limit` is capped at 1000 (Designer's call; `verify.py` uses 1000).
- The cursor is opaque: the last returned key plus the query range, authenticated with a per-tenant HMAC so it cannot be replayed against another tenant or edited.
- A page that starts inside a day bucket reads that bucket and skips to the cursor key. Caching decrypted buckets on api nodes is left to the builder.

## 10. Flush to cold (worker)

**Trigger.** Every 5 minutes the worker checks each tenant. The watermark is `W = (100th largest occurred_at_ms in that tenant's hot rows, or the largest if there are fewer than 100) − 96 hours`. If `W >= cold_until + 1 day`, the day starting at `cold_until` is flushed, and the check repeats until no full day is past `W`. In event time this is about once a day per tenant. Under replay, where event time moves fast, it catches up in a loop (Designer's call on the 5-minute interval and on using the 100th largest value, which keeps a few future-dated outliers from pushing `W` ahead).

96 hours is the SPEC's 72-hour lateness plus a margin (User). It only decides what moves. Correctness does not depend on it (§12). A dirty tenant (§12) is rebuilt before it is flushed again.

**Steps.** For the day `d = cold_until`:
1. Take the exclusive cold lock for the tenant.
2. Read the hot rows with `occurred_at_ms` in day `d`, in key order.
3. Write the bucket object for `d` (new generation). Fold the day onto the current snapshot and write a new snapshot object.
4. In one transaction: point the manifest and `tenant_cold` at the new objects, insert the day's `customer_days` and `sku_moves` rows, set `cold_until = d + 1 day`, delete the hot rows of day `d`, and commit. Release the lock.

A crash before step 4 leaves only unreferenced objects, which sweep deletes. A crash after step 4 leaves the flush done. Re-running the flush from the start is always safe.

**Concurrency.** Reads need no lock: they see either the old snapshot plus day `d` in hot, or the new snapshot without day `d` in hot, which give the same state. An ingest for day `d` (only possible for an event more than 96 hours late) takes the shared cold lock, so it waits for the flush to commit and then follows the late rules with the new `cold_until`. No event can land in hot after step 2 and be deleted in step 4 without being in the bucket.

## 11. Erasure

### 11.1 Customer erasure (synchronous; Designer's call)
The request returns `2xx` only after the customer is gone from state, reads and every current object. A read that runs while the request is in flight may still see the customer; once `2xx` is sent, no read will. The design document states this as the meaning of "from then on".

1. **Tombstone.** Take the exclusive customer lock, insert the tombstone (status pending), commit. From here on, ingest drops the customer's events. If the tombstone is already done, return `2xx` immediately.
2. **Lock.** Take the exclusive cold lock for the tenant.
3. **Find.** Read the customer's days from `customer_days`.
4. **Rewrite buckets.** For each of those days, read the bucket, remove the customer's events, keep them in memory, and write a new bucket generation.
5. **Update the snapshot** from the removed events:
   - subtract them from `event_count` and `messages_by_channel`; remove the key from the customer set;
   - remove the customer's orders whole (orders never mix customers; §18) and subtract the customer's orphan refunds and orphan shipments;
   - recompute the latest message time of each rewritten day, then `last_contact_ms` from the per-day values;
   - for every SKU in the customer's first `order.created` lines, read that SKU's rows from `sku_moves` in key order, leave out the rows of the removed events, and refold inventory and oversold from zero;
   - match the reducer's key presence: a SKU with no remaining movements leaves `inventory`, and a channel whose count drops to zero leaves `messages_by_channel`. Campaigns are never affected, because `ad.metric` has no customer.
6. Write the new snapshot object.
7. **Commit** in one transaction: point the manifest and `tenant_cold` at the new objects, delete the customer's hot rows by `customer_key`, delete the customer's `customer_days` rows and the removed events' `sku_moves` rows, mark the tombstone done. Release the lock and return `2xx`.

Any api node can run these steps, so erasure does not depend on the worker (Designer's call). If the node dies between steps 1 and 7, the client retries (it never got `2xx`) or the worker's sweep finishes pending tombstones. Every step reads current committed pointers, so a re-run is safe. Several pending erasures for the same tenant may be processed in one pass.

The 10-second replay timeout bounds how long one erasure may take before the client retries. On the supplied data a customer appears in about five day buckets, so one erasure reads and rewrites a handful of objects.

### 11.2 Tenant erasure
In one transaction: take the exclusive tenant-status lock, mark the tenant erased, delete its wrapped DEK, delete its hot rows, index rows, manifest rows and pointers; commit; return `2xx`. Cold objects become unreadable at once because the key is gone, and sweep deletes the tenant prefix. Signing secrets stay loaded from the tenants file so later deliveries can still be told apart: genuine ones get `410`, forged ones `401`.

## 12. Late events and full rebuild

An event is **late** when `occurred_at_ms < cold_until`, which means it arrived more than 96 hours after it happened. The SPEC says this does not happen for first deliveries, but the design does not rely on that.

- **Duplicate check.** Read the bucket for the event's day. If the event ID is there, or in hot, return `2xx` and do nothing. Redeliveries of cold events are caught this way, so deduplication covers all retained events, not a time window.
- **New late event.** Insert it into hot as usual and set `dirty` on `tenant_cold` in the same transaction, then return `2xx`. Reads on a dirty tenant use the slow path (§8).
- **Rebuild (worker).** Under the exclusive cold lock: move hot rows older than `cold_until` into their day buckets (new generations), then rebuild the snapshot and the tenant's `customer_days` and `sku_moves` rows from all buckets. Commit pointers, replace the index rows, delete the moved hot rows and clear `dirty` in one transaction. A metric counts rebuilds and their reason.

The same rebuild serves a reducer version change (§17) and is the reference the crash checker compares against.

## 13. Locks

| Lock | Shared by | Exclusive by |
|---|---|---|
| tenant status | every ingest | tenant erasure |
| customer `(tenant, customer_key)` | ingest of that customer's events | writing that customer's tombstone |
| tenant cold | ingest of an event dated before `cold_until + 1 day` | flush, customer erasure, rebuild, sweep work on that tenant |

Normal ingest takes only the tenant-status lock (shared) and, for events with a customer, that customer's lock (shared), so it never waits on flushes. Reads take no lock. Postgres advisory locks are suggested so shared holders do not write to rows; the exact mechanism is the builder's choice.

## 14. Sweep and the physical-removal bound

The worker runs sweep every hour (User):
- finish pending tombstones whose request died;
- delete cold objects that no pointer references and that are older than a grace period long enough for in-flight reads (Designer's call: 10 minutes);
- delete the prefixes of erased tenants;
- run `VACUUM` on the hot table and `CHECKPOINT`, with WAL recycling disabled so old WAL files are removed rather than reused.

**Stated bound** (Designer's call): an erased customer's or tenant's data is out of reads and state immediately once `2xx` is returned. Within **2 hours** (one sweep interval plus its run time) it is gone from MinIO and from Postgres WAL files. It is gone from every Postgres query, including the index tables, at once.

**Stated limits** (User: acknowledge, do not engineer around):
- **Postgres table files.** `DELETE` and `VACUUM` mark a row's space as reusable but do not overwrite it. The deleted row's ciphertext stays inside the table file until a new row takes that space, and there is no upper bound on when that happens. It is encrypted with the tenant DEK, which stays alive after a customer erasure. The same applies to the wrapped DEK row after a tenant erasure. Rewriting the table (`VACUUM FULL`) would close this gap but stops ingest while it runs, so it is not built. In production, DEKs in a KMS and volume encryption would cover it.
- **Raw disk blocks** below Postgres and MinIO (volume encryption in production).
- **Backups**: none in this setup. In production the backup retention adds to the bound.
- **Tombstones** keep the customer's HMAC key forever, because later arrivals must stay blocked. It is a keyed hash, not the ID.

## 15. Encryption and isolation

- **Keys** (User: tenant DEK only, no per-customer keys). The KEK wraps one DEK per tenant; the wrapped DEK lives in Postgres. Customer erasure deletes hot rows and rewrites cold objects. Per-customer keys stored in the same Postgres would leave the same traces as the rows they protect (§14), so they would add a key lookup per event without closing the gap. In production the DEKs would move to a KMS.
- **What is plaintext**: tenant ID, event ID, `occurred_at_ms`, day numbers, and keyed HMACs (`customer_key`, `sku_key`). Everything else, including `customer_id`, SKUs, amounts, PII and the whole `data` object, is inside AES-GCM ciphertext.
- **Isolation** (Designer's call): middleware turns the token into a tenant scope once, and storage functions take the scope and have no tenant ID parameter. Per-tenant keys are the second layer: another tenant's rows and objects cannot even be decrypted, because the AAD binds the tenant. MinIO access goes through per-tenant prefixes. Postgres row-level security is left out because it would need separate database roles and a per-transaction tenant setting for a third layer. The submitted design names it as production hardening.

## 16. Deep dive: crash safety (User)

**Claim.** Every operation that changes stored data follows one rule: write new immutable objects, then make them current with one Postgres transaction. Ingest is a single `INSERT` commit before `2xx`. So a crash at any point leaves either the old version or the new one, plus garbage that sweep removes.

**Evidence to produce.**
1. A fault-injection script that runs `replay.py` with aggressive settings (frequent flushes and sweeps) while a loop sends `SIGKILL` to random api nodes and to the worker at random intervals. Containers restart automatically.
2. Named crash points in each multi-step operation (after each object write and before each commit), switchable by configuration, so each window is hit on purpose rather than by luck.
3. After the run: sweep, then `verify.py`, then a consistency checker:
   - no event ID appears twice across hot and cold;
   - every pointer references an object that exists;
   - no unreferenced object remains after sweep;
   - for every tenant, a full rebuild gives the same state hash as snapshot plus hot.
4. A report: number of kills by target and crash point, and the checker and `verify.py` output.

## 17. Reducer versions (follow-up change request)

The generator's change-request stream and `shipment.patch` events suggest a v2 reducer that must be recomputed over all history. Canonical events are stored unchanged, including unknown types, and each snapshot records its reducer version. A new version would be backfilled by running the rebuild (§12) per tenant into snapshots of the new version, while reads keep using the old version until every tenant is done, then switching in one transaction. Only v1 is built.

## 18. Assumptions

1. **All events of one order belong to the customer who created it** (User: a mixed order makes no sense). Customer erasure removes the customer's orders whole and does not look for other customers' events on them. This is written into the submitted design document as an assumption.
2. The SPEC's 72-hour lateness bound and measured redelivery delays only tune performance (§10, §12).
3. Erasure requests can arrive at any rate; nothing assumes they are rare.

## 19. Designer's calls to confirm

These were proposed during the discussion without an explicit decision:
1. Customer erasure is synchronous, run by any api node under the tenant cold lock (§11.1).
2. The watermark uses the 100th largest hot `occurred_at_ms`, and the worker checks every 5 minutes (§10).
3. The physical-removal bound is 2 hours, with a 10-minute grace period for old objects (§14).
4. Snapshot cache on api nodes, keyed by object name, 1-hour TTL (§8).
5. `410` for genuine deliveries and reads of an erased tenant (§5, §8).
6. `limit` capped at 1000 (§9).
7. Isolation by scope type and per-tenant keys, without Postgres row-level security (§15).
8. Scale target: `verify.py` must pass on the supplied data and on a fresh small seed. Medium and large data are used for measurements and are expected to pass too.
9. Build order (§22).
10. In the index tables, SKUs are stored as keyed HMACs and amounts as ciphertext (§6.1).

## 20. Operations

- **Commands** (each one command): `docker compose up`; replay; verify; benchmark; crash test. Paths to `$INFRA` and the tenants file are parameters.
- **Metrics** (Prometheus): ingest results by outcome, ack latency histogram, state and range read latency split by hot-only and cold-touching, events and bytes per tier, flush, rebuild and sweep durations, index table sizes, rebuild count by reason, late-event count, erasure duration, pending tombstones, process RSS.
- **Runbook** (one page): start, what to watch, how to recover from a crash (restart; sweep cleans up), how to run the crash test.
- **Measurements** with method: ingest throughput, hot and cold read latency, bytes per event per tier, peak memory. The 96 to 120 hours of hot tail folded on each state read (about 45,000 events for the largest tenant in the large data set) is measured here rather than optimized in advance.

## 21. Left to the builder

- Go libraries, Postgres schema details, file encodings inside the encrypted objects, LB choice, metric names, the lock mechanism.
- How the Go fold port is tested, as long as it is checked against `reducer.fold` hashes on the supplied data and on a fresh seed, and checks that "snapshot then tail" equals a full fold at many split points.
- Where the submitted design document (at most 3 pages, with one paragraph for each deep dive not chosen) and the runbook live in the repository. They are separate deliverables written from this document.

## 22. Build order (Designer's call)

Each step ends with something that runs, so the work can stop after any step and still separate what is built from what is proposed:
1. Ingest, a hot table only, and state and range reads by a full fold. `verify.py` passes.
2. Flush to cold: day buckets, snapshot, the two index tables, and reads that merge cold and hot.
3. Erasure across both tiers, late events and rebuild.
4. The crash test (§16).
5. Sweep, metrics, runbook and measurements.
