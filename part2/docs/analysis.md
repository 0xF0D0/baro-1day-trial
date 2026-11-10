# Part 2 Brand Data Backbone: Analysis

- Date: 2026-11-10
- Sources: the brief (PDF pages 3 and 4) and the supplied `infrastructure/` folder (README, SPEC.md, four scripts, data). That folder is not in this repository yet; below, its location is written as `$INFRA`.
- Method: read every document and script, then reproduce the expected values with an in-memory oracle that implements the SPEC as written (`part2/analysis/oracle.py`). Machine: Apple M2 Pro, Python 3.14.2.
- Status: §8 and §9 were a first design direction written before the design discussion. The decisions that followed are in `docs/superpowers/specs/2026-11-10-part2-brand-data-backbone-design.md`, which supersedes them.

## 1. Summary

1. **The SPEC alone fully determines the answer.** On the supplied data and on freshly generated seed 7 data, the oracle matched 200/200 states and 48/48 range reads, with 0 mismatched webhook response decisions. There are no hidden rules outside the specification, and the normalization table agrees with the example file.
2. The hard part is not the logic that produces the answer. It is producing that answer **while keeping durability, tiering, encryption, erasure and isolation correct**.
3. Six traps change the design (§5): redeliveries past 72 hours, retroactive erasure, an order-dependent fold, sort collation, a simulated clock, and response codes for erased tenants.
4. There are signs of a follow-up change request (§6). Raw events must be kept unchanged and the reducer version must be tracked.
5. Recommended deep dive: **crash safety** (§7).

## 2. Requirements

### The five parts of the system

| Part | Requirement | How it is checked |
|---|---|---|
| 1. Ingest | Two vendor formats and signatures. Resolve each event to exactly one tenant or reject it. Handle duplicates, late arrivals and forgeries. Acknowledge only after durable storage; a crash must never lose an acknowledged event | verify.py check 1 (response codes) |
| 2. Tiered storage | Hot plus S3-compatible cold (MinIO is fine). Choose how data moves down and back up. Encrypt payloads with a per-tenant key | Design and measurements (outside verify.py) |
| 3. Reads | Current state, and time-range reads across both tiers (ordered by `(occurred_at_ms, event_id)`, paginated). Block access to other tenants by structure, not by filtering | verify.py checks 2, 4, 5 |
| 4. Erasure | Erase a customer or a tenant from every tier and every derived state, and keep later events from bringing it back. Keep `customer_id` only inside the encrypted payload. State a time bound for physical removal | verify.py checks 2, 3, and the design |
| 5. Operations | Expose reported numbers as Prometheus metrics. A one-page runbook (start, monitor, recover) | Design and measurements |

### Deep dive: pick one, one paragraph for each of the others

- **Cold hydration**: make a fully cold tenant (about 1 million events in the large data set) fast to read, and measure where the time goes.
- **Crash safety**: show with a fault-injection script that `kill -9` during compaction and tier moves never loses an acknowledged event, never duplicates one, and never leaves a half-written state.
- **Noisy neighbors**: show with numbers that, under a 1 GiB memory and 2 CPU limit, small tenants' reads are not starved while the largest tenant is ingesting and compacting.
- **Beyond one node**: for 1,000 tenants and thousands of events per second, design shard placement, rebalancing and node failure during compaction, and prototype as much as possible.

### Deliverables

- A design document of at most 3 pages: storage and tiering, late-event correctness, tenant isolation, erasure, the chosen deep dive. One paragraph for each deep dive not chosen.
- If implemented: `docker compose up`, and replay, verify and benchmark as one command each. A one-page runbook. Measurements (ingest throughput, hot and cold read latency, bytes per event per tier, peak memory) and how they were taken.
- If only designed or partly implemented: keep built behavior and measured numbers separate from proposals and plans.
- It can be re-run with a new seed. The tenants file path must be configurable, it must start from empty storage, and tenants or secrets must not be hard-coded.

## 3. Supplied material

| File | Contents |
|---|---|
| `SPEC.md` | Webhook formats, signatures, normalization table, read and erasure APIs |
| `reducer.py` | `fold(tenant_id, events)`. Its output is the correct state. Integers only |
| `replay.py` | Re-sends the delivery file with concurrency 8. Retries 5xx and connection errors, never 4xx. Waits for all in-flight webhooks before each erasure request |
| `verify.py` | Checks response codes, per-tenant state hashes, erased tenants, isolation (25 random pairs) and range reads (hash of the event_id list) |
| `generate.py` | Deterministic generator. `--seed`, `--scale small/medium/large` (about 130 thousand, 1.3 million, 6.5 million events), `--cr-out` |
| `data/tenants.json` | 200 tenants, api_token, per-vendor accounts and signing secrets, admin_token |
| `data/deliveries.jsonl.gz` | 100,560 deliveries |
| `data/expected/v1.json`, `ranges.json` | State hashes, forged seq list, lenient seq list, 48 range reads |

## 4. Data facts (supplied data, small, seed 20261104)

| Item | Value | What it means for the design |
|---|---|---|
| Deliveries | 100,560: 100,489 webhooks (A 25,398, B 75,091), 69 customer erasures, 2 tenant erasures | |
| Events | 98,561 unique, 97,901 retained after erasure | |
| Duplicates | 1,928 events delivered exactly twice. Bodies always identical; 507 have a different header (vendor A's `t`) | Deduplicate on event_id. Ignore the signature header |
| Forgeries | 355. Half signed with a random key, half with **the next tenant's real key** | Pick the tenant only by account or shop_domain, and verify with that tenant's key |
| Types | shipment.updated 50,791, order.created 17,800, inventory.adjusted 15,601, message.received 7,812, ads.metric 6,632, charge.refunded 966, **shipment.patch 887** | shipment.patch is an unknown type, not in the SPEC table |
| Sizes | Bodies 216 to 472 B (mean 318), canonical JSON mean 268 B | |
| Tenant sizes | Distributed as 1/(i+1)^1.1. t_0000 20,631, t_0001 9,669, t_0002 6,218, smallest tenants about 50 | In the large set t_0000 has about 1 million |
| Arrival delay (first delivery) | p50 5 min, p96 10 min, p99 23 h, max 71.9 h | |
| Out of order | 10,920 events (11%) arrive earlier in time than the latest event already seen for that tenant, by up to 71.6 h | §5.3 |
| Redelivery delay | Up to 76.0 h after the event, 1 beyond 72 h (seed 7: 75.8 h, 3 beyond) | §5.1 |
| Customer erasure | 23 tenants × 3 customers. 172 events stored before the request are removed retroactively; 110 arriving after it are blocked | §5.2 |
| Tenant erasure | t_0166, t_0189. 25 genuine deliveries arrive after the erasure (`lenient_seqs`) | §5.6 |
| Time span | Events from 2026-07-01 to the cutoff 2026-09-29 (90 days). The generator makes 120 days and splits deliveries after day 90 into the `--cr-out` stream | §5.5, §6 |

Seed 7 (small): 100,238 deliveries, 350 forgeries. The CR stream has 33,203 deliveries (129 forgeries, 40 lenient), and its seq numbers restart at 0.

## 5. Traps that change the design

### 5.1 Redeliveries cross the 72-hour line
The SPEC's "late arrivals up to 72 hours" is about first deliveries. generate.py re-sends duplicates up to 6 hours after the first delivery (`at + randint(1000, 6 * HOUR)`), so a redelivery can arrive up to 78 hours after the event.
- Impact: if the dedupe index covers only the hot window, a late redelivery of an event already moved to cold comes in as a new event and is counted twice.
- Response: deduplication must cover every retained event. Keep a permanent (tenant, event_id) index, or also check cold segments' event_id filters. Real vendors may have a longer limit, so do not rely on the bound.

### 5.2 Erasure is retroactive
The expected state is the fold over "all events minus the erased customers' events". Events from before the erasure request must also leave the state (172 events).
- After a customer erasure, the tenant's state is folded again from scratch. Snapshots from before that point are invalid too.
- Later arrivals (110 events) are blocked by a tombstone. `customer_id` cannot be kept in plaintext, so tombstones and lookup keys are keyed hashes (HMAC) made with the tenant key.

### 5.3 The fold depends on order
Inventory never goes below zero and the shortfall goes to `oversold_units`. For each order_id only the first order.created counts. The last shipment status wins, and refunds are capped at the gross amount. So events cannot be added one by one in arrival order, and 11% arrive out of order.
- Option A: fold everything at read time and invalidate a cache on writes. Simplest and safest.
- Option B: keep a snapshot of a settled range and refold only the tail. First deliveries are never more than 72 hours late (measured max 71.6 h), so everything before a per-tenant watermark W = (latest event time seen − 72 h − margin) is settled. State = fold(snapshot at W, events after W). A new event before W breaks the rule: drop the snapshot, refold everything, and count it in a metric.
- Porting note: the reducer runs `customers.add` before branching on type. So duplicate order.created events and unknown types still count toward the customer count. The snapshot contains the customer_id set, so the snapshot is encrypted too. The ported fold is tested by comparing hashes with reducer.fold.

### 5.4 Sorting is by code point
event_ids mix `evt_…` (A) and UUIDs (B), and the reducer sorts with Python string comparison. Postgres's default collation (en_US.UTF-8 and the like) treats `_` and `-` differently and can change the order. Use `COLLATE "C"` or bytea. The range-read check (`ids_sha256`) compares order, not just counts.

### 5.5 The clock is simulated
Event times are July to September 2026, while the real date is November 2026. A wall-clock rule such as "the last N days are hot" would send all data to cold at once. The SPEC also says not to enforce a signature timestamp tolerance.
- Base tiering, watermarks and physical-removal cycles on each tenant's event time.
- Make the clock injectable: the wall clock in production, event time in replay.

### 5.6 Response codes for erased tenants
- verify.py reads an erased tenant **with that tenant's own token** and accepts only 404 or 410. Removing the token and answering 401 fails.
- Genuine deliveries after erasure may get only 2xx, 404 or 410 (not 401). Forged deliveries must still get 4xx. So the signing secrets (from the configuration file) stay apart from destroying the data key, and the erased check comes after signature verification.
- The isolation check accepts only 401, 403 or 404 (not 410). When the token's tenant differs from the path's tenant, answer 404 before checking erasure.

### 5.7 Other points
- Signatures cover the raw received bytes. Verifying re-serialized bytes after parsing is wrong. Before the signature is checked, read only the account or shop_domain needed to pick the tenant.
- Unknown types (shipment.patch) are stored, acknowledged, counted in event_count and returned by the events endpoint. Their customer_id comes from the payload, so they are subject to customer erasure, and the customer_id also sits inside `data`. So the whole payload is encrypted.
- Pagination: t_0000's full range is 20,631 events, which is 21 pages at limit 1000, and about 1,000 pages in the large set. Use a keyset cursor on (occurred_at_ms, event_id) instead of OFFSET. Make the cursor opaque and bind it to the tenant (HMAC).
- replay.py waits for all in-flight webhooks before an erasure request. Real traffic has no such barrier. The supplied data never tests events arriving at the same moment as an erasure, but the design must handle that race with tombstones.
- The CR stream's seq numbers restart at 0, so keep its responses in a separate file.

## 6. Preparing for a follow-up change request

Evidence:
- generate.py `--cr-out` produces a delivery stream for days 90 to 120 and `invalid_cr.json`.
- verify.py `--invalid` is documented as "for the change request".
- shipment.patch appears from day 45, with carrier and status in `changes`. The v1 reducer ignores it, but the example file includes it.
- PDF page 4 says the work may be tested with new data, and may ask for "a new metric over the full hot and cold history, and what readers see while it is being computed".

Guess: a v2 reducer will apply shipment.patch, and the question will be how reads look while it is recomputed over the full hot and cold history.

Design requirements:
- Store canonical events unchanged (including unknown types; `data` kept verbatim).
- Tag state snapshots with the reducer version.
- A new version keeps answering with the old version until its backfill finishes, then switches atomically.

Since this is a guess, only v1 is implemented, and the design document covers this in one paragraph.

## 7. Deep dive comparison

| Option | Work | Evidence | Cost and risk | Overlap with required parts |
|---|---|---|---|---|
| Cold hydration | Generate the large set (about 4 GB generator RAM), cold segment format and snapshots, per-stage timing | Per-stage latency table | Per the baseline below, decoding is the bottleneck, so a binary or columnar format may be needed | Part 2 tiering, §6 backfill |
| **Crash safety** | Make ack, compaction, tier moves and erasure idempotent with atomic commits, and write a `kill -9` injection script | verify.py passes after repeated kills; checks for duplicates and orphan objects | Repeatable in minutes on small data | Parts 1, 2 and 4 already require the same properties |
| Noisy neighbors | 1 GiB, 2 CPU container limits, the large set, p99 of small-tenant reads while a big tenant ingests and compacts | Latency distribution, memory | Replaying 5 million deliveries alone is expected to take tens of minutes or more (not measured); repeated tuning | Part 5 metrics |
| Beyond one node | Design shard placement, rebalancing and node failure during compaction, plus a small prototype | Design and a partial prototype | Prototype scope is vague and the evidence weak | Little |

**Recommendation: crash safety.**
1. Required parts 1, 2 and 4 already demand "no acknowledged event lost" and "no half-written state". The extra work is mostly the verification script.
2. It can be proven repeatedly in minutes on small data.
3. It matches the brief's direction of being correct first, even if slower.
4. The time left after Part 1 is short.

Second choice: cold hydration, which overlaps with the §6 backfill.

Baseline (`part2/analysis/fold_bench.py`, 1 million events): `json.loads` 3.9 s, `reducer.fold` 1.2 s, zlib level 6 compression 3.9 s. Bytes per event: JSON 274 B, zlib 49.7 B; the data is replicated, so it compresses better than real data would. Decoding costs more than the fold itself.

## 8. First design direction (not final; superseded by the design spec)

- **Language**: Python. Import reducer.py as is and use it as the reference. Port a version that continues folding from a snapshot and verify it by comparing hashes with reducer.fold.
- **Hot**: Postgres (the same engine as Part 1). After tenant resolution and signature verification, commit `INSERT … ON CONFLICT DO NOTHING` (`synchronous_commit=on`) and then answer 2xx. Plaintext columns are only tenant_id, event_id (C collation), occurred_at_ms, type and customer_key (HMAC); payload and customer_id are ciphertext.
- **Cold**: MinIO. Segments per tenant × period, sorted, compressed and AES-GCM encrypted (AAD includes tenant and segment id). A Postgres manifest is the single source of truth. Move-down order: write the object under a deterministic key → read it back to check → in one transaction, register it in the manifest and delete the hot rows. A crash in between leaves only orphan objects, which GC cleans up.
- **State**: refold the tail onto a snapshot of the settled range (encrypted, tagged with the reducer version). On an erasure or a lateness-rule violation, refold everything.
- **Isolation**: middleware builds a TenantScope from the token once, and the storage API takes only the scope, with no tenant_id argument. Postgres RLS is a second layer and per-tenant keys a third (another tenant's data cannot even be decrypted).
- **Encryption**: a master key (KEK, from an environment variable or file standing in for a secret store) wraps the tenant DEKs. Still to decide: whether to add per-customer keys (crypto-shredding). With them, data becomes unrecoverable in every tier and backup at erasure time, and physical removal happens at the next compaction.
- **Erasure**: a customer erasure writes the tombstone, deletes hot rows and invalidates the snapshot in one transaction, and schedules cold segment rewrites. A tenant erasure destroys the DEK, deletes hot rows, deletes the cold prefix and writes a tenant tombstone (410 afterwards), in that order.
- **Metrics**: ingest counters by outcome, ack latency histogram, hot and cold read latency, bytes and events per tier, move-down and compaction latency, full refold count, RSS.

## 9. Open decisions at the time (since decided in the design spec)

1. Language and hot store (recommended: Python and Postgres)
2. Encryption unit: tenant DEK only, or per-customer DEKs as well
3. Deep dive (recommended: crash safety)
4. Physical-removal time bound (for example: hot immediately, cold within the next compaction cycle)
5. Whether to put the `infrastructure/` folder in the repository
6. Time allocation: after Part 1, write only the design document, or implement as well

## Reproduce

```sh
python3 part2/analysis/oracle.py $INFRA
python3 part2/analysis/fold_bench.py $INFRA
python3 $INFRA/generate.py --seed 7 --out /tmp/seed7 --cr-out /tmp/seed7-cr
python3 part2/analysis/oracle.py $INFRA /tmp/seed7
```
