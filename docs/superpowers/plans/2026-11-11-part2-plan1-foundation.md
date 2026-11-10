# Part 2 Plan 1: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Go service that ingests both vendors' webhooks into an encrypted Postgres hot table, answers state and range reads by folding every retained event, and erases customers and tenants, so that `verify.py` passes on the supplied data and on a fresh seed with two api nodes behind an LB.

**Architecture:** One Go module at `part2/backbone`, in three layers: pure logic (`config`, `tenants`, `webhook`, `canon`, `fold`), storage and keys (`crypto`, `store`), and HTTP (`api`, `cmd/api`). In this plan every event stays in the hot table. There is no cold tier, worker, snapshot or MinIO yet; those come in Plan 2. State reads therefore fold all hot rows, which is the spec's always-correct path.

**Tech Stack:** Go 1.24 (stdlib `net/http`, `crypto/hkdf`, `log/slog`), `github.com/jackc/pgx/v5`, Postgres 17, nginx 1.27, Docker Compose v2. Python 3 is used only for the fixture generator and for the supplied `replay.py` and `verify.py`.

**Spec:** `docs/superpowers/specs/2026-11-10-part2-brand-data-backbone-design.md`. This plan implements §22 step 1 and uses §3, §4, §5, §6, §8, §9, §11, §13 and §15. Hot-only erasure is included here because `verify.py` checks erasure.

**Branch:** `part2-plan1-foundation`, cut from the commit that contains the spec.

**Supplied files:** `$INFRA` is the brief's `infrastructure/` folder (locally `~/Downloads/BARO_Work_Trial/infrastructure`). It is not in the repository. Scripts and the fixture generator read it from the `INFRA` environment variable.

## Global Constraints

- Service interface exactly as `$INFRA/SPEC.md`. Port 8080.
- Response codes: unknown tenant `404`, bad or missing signature `401`, malformed `400`. A genuine delivery for an erased customer gets `200` and is dropped. A genuine delivery for an erased tenant gets `410`. Forged deliveries always get `4xx`. A read of an erased tenant with its own token gets `410`. A token used on another tenant's path gets `404` before the erased check. Erasure requests get `204`. Internal errors get `500`, so the sender retries.
- Ordering is `(occurred_at_ms, event_id)` with byte-wise comparison of `event_id`. Postgres columns that sort `event_id` use `COLLATE "C"`.
- No timestamp tolerance on vendor A signatures. Signatures are verified over the exact received bytes, before anything else in the body is used.
- Configuration comes from environment variables: tenants file path, KEK file path, database URL. No tenant IDs or secrets in code. The KEK file holds exactly 32 bytes.
- `synchronous_commit = on` for every transaction. Ingest returns `2xx` only after its transaction commits.
- Plaintext in Postgres is limited to tenant ID, event ID, `occurred_at_ms` and keyed HMACs. Everything else, including `customer_id`, PII and the whole canonical event, is AES-GCM ciphertext whose AAD binds the tenant and the event ID.
- Every ciphertext column has `SET STATISTICS 0`.
- No log line or metric label carries a request path, body or customer ID. Log route templates. The LB access log is off and its error log is at `crit`.
- No wall-clock time in any data decision.
- Empty maps and lists encode as `{}` and `[]`, never `null`. Python's `json.dumps` writes `{}` and `[]`, while Go writes `null` for a nil map or slice, so every map and slice that reaches JSON is created non-nil. The only values that may be `null` are `last_contact_ms`, `customer_id` and `next_cursor`.
- Locks are Postgres advisory transaction locks: tenant status (shared by ingest, exclusive by tenant erasure) and customer (shared by that customer's ingest, exclusive while writing its tombstone). They are always taken in that order.
- Committed documents are in English.

## Review Focus

1. Two api nodes start at the same instant on empty storage. Migrations must not fail, and both nodes must use the same DEK for each tenant. Tests: Task 6 `TestMigrateConcurrent`, `TestEnsureTenantsConcurrent`.
2. The service restarts after a tenant erasure. The tenant must stay erased (`410`), and no new DEK may be created for it. Test: Task 8 `TestEraseTenantSurvivesRestart`.
3. A customer is erased while their events are still arriving. Once the erasure returns, none of their rows remain, and later deliveries are dropped. Test: Task 8 `TestEraseCustomerRacesIngest`.
4. Range pages run over many events with the same `occurred_at_ms` and mixed `evt_…` and UUID IDs. Pages must not repeat or skip events. Test: Task 7 `TestRangePagingTies`.
5. A cursor is edited, issued for another tenant, or reused with a different range. The answer is `400`, never data. Test: Task 9 `TestEventsCursorTampering`.

---

### Task 1: Module, configuration and tenant registry

**Files:**
- Create: `part2/backbone/go.mod` (`module backbone`, `go 1.24`)
- Create: `part2/backbone/internal/config/config.go`, `config_test.go`
- Create: `part2/backbone/internal/tenants/tenants.go`, `tenants_test.go`, `testdata/tenants.json`
- Modify: `.gitignore` (add `part2/out/`)

**Interfaces:**
- Produces:
  - `config.Config{Listen, TenantsFile, KEKFile, DatabaseURL string}` and `config.Load(getenv func(string) string) (config.Config, error)`. The variables are `BACKBONE_LISTEN` (default `:8080`), `BACKBONE_TENANTS_FILE`, `BACKBONE_KEK_FILE` and `BACKBONE_DATABASE_URL`; the last three are required.
  - `tenants.Tenant{ID, Name, APIToken string; VendorA tenants.VendorA; VendorB tenants.VendorB}`, `tenants.VendorA{Account, SigningSecret string}` and `tenants.VendorB{ShopDomain, SigningSecret string}`.
  - `tenants.Load(path string) (*tenants.Registry, error)` and `tenants.Parse(data []byte) (*tenants.Registry, error)`.
  - Registry methods: `ByAccount(string) (*Tenant, bool)`, `ByShopDomain(string) (*Tenant, bool)`, `ByToken(string) (*Tenant, bool)`, `ByID(string) (*Tenant, bool)`, `IsAdmin(token string) bool`, and `All() []*Tenant`, sorted by ID.

`testdata/tenants.json` holds two synthetic tenants, which Task 9 copies:

```json
{"admin_token":"adm_test","tenants":[
 {"tenant_id":"t_a","name":"A","api_token":"tok_a","vendor_a":{"account":"acct_a","signing_secret":"sec_a1"},"vendor_b":{"shop_domain":"a.shops.example","signing_secret":"sec_a2"}},
 {"tenant_id":"t_b","name":"B","api_token":"tok_b","vendor_a":{"account":"acct_b","signing_secret":"sec_b1"},"vendor_b":{"shop_domain":"b.shops.example","signing_secret":"sec_b2"}}]}
```

- [ ] **Step 1: Write the failing tests**

```go
func TestLoadReportsEveryMissingVariable(t *testing.T) {
	_, err := config.Load(func(string) string { return "" })
	for _, name := range []string{"BACKBONE_TENANTS_FILE", "BACKBONE_KEK_FILE", "BACKBONE_DATABASE_URL"} {
		if err == nil || !strings.Contains(err.Error(), name) {
			t.Fatalf("missing %s not reported: %v", name, err)
		}
	}
}

func TestLoadDefaultsListen(t *testing.T) {
	env := map[string]string{"BACKBONE_TENANTS_FILE": "a", "BACKBONE_KEK_FILE": "b", "BACKBONE_DATABASE_URL": "c"}
	cfg, err := config.Load(func(k string) string { return env[k] })
	// expect err == nil and cfg.Listen == ":8080"
}

func TestRegistryLookups(t *testing.T) {
	reg, _ := tenants.Load("testdata/tenants.json")
	// ByAccount("acct_b").ID == "t_b"; ByShopDomain("a.shops.example").ID == "t_a"
	// ByToken("tok_a").ID == "t_a"; ByToken("nope") is (nil, false)
	// IsAdmin("adm_test") && !IsAdmin("tok_a"); All() IDs == ["t_a", "t_b"]
}

func TestParseRejectsDuplicates(t *testing.T) // two tenants sharing account "acct_a" -> error

func TestLoadSuppliedTenants(t *testing.T) // skip unless INFRA is set; len(Load($INFRA/data/tenants.json).All()) == 200
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `cd part2/backbone && go test ./internal/config/... ./internal/tenants/...`
Expected: FAIL (packages do not exist yet).

- [ ] **Step 3: Implement `config.Load` and the registry**

Index tokens by their SHA-256 so lookups do not compare raw tokens. `IsAdmin` uses `subtle.ConstantTimeCompare`. `Parse` rejects empty or duplicate tenant IDs, accounts, shop domains and tokens.

- [ ] **Step 4: Run the tests and see them pass**

Run: `cd part2/backbone && go test ./internal/config/... ./internal/tenants/...`
Expected: PASS (`TestLoadSuppliedTenants` passes with `INFRA` set, skips otherwise).

- [ ] **Step 5: Commit**

```bash
git add .gitignore part2/backbone/go.mod part2/backbone/internal/config part2/backbone/internal/tenants
git commit -m "Add backbone module with config and tenant registry"
```

### Task 2: Webhook signatures and tenant peeking

**Files:**
- Create: `part2/backbone/internal/webhook/webhook.go`, `webhook_test.go`

**Interfaces:**
- Produces:
  - `webhook.HeaderA = "Vendor-A-Signature"` and `webhook.HeaderB = "X-VendorB-Hmac-SHA256"`.
  - `webhook.ErrBadSignature`.
  - `webhook.PeekAccount(raw []byte) (string, error)` and `webhook.PeekShopDomain(raw []byte) (string, error)`. The error is returned only for invalid JSON; an absent field gives `""`.
  - `webhook.VerifyA(secret, header string, raw []byte) error` checks `hex(HMAC_SHA256(secret, "<t>.<raw>"))` against every `v1=` value in `t=<t>,v1=<hex>[,v1=…]`.
  - `webhook.VerifyB(secret, header string, raw []byte) error` checks `base64std(HMAC_SHA256(secret, raw))`.

- [ ] **Step 1: Write the failing tests**

```go
func signA(secret, ts string, raw []byte) string // test helper: hex HMAC of ts+"."+raw

func TestVerifyA(t *testing.T) {
	raw := []byte(`{"id":"evt_1","account":"acct_a"}`)
	good := "t=1782950400,v1=" + signA("sec_a1", "1782950400", raw)
	// VerifyA("sec_a1", good, raw) == nil
	// VerifyA("sec_b1", good, raw) is ErrBadSignature            (another tenant's real key)
	// VerifyA("sec_a1", good, append(raw[:len(raw)-1:len(raw)-1], ' ')) is ErrBadSignature
	// VerifyA("sec_a1", "v1="+signA(...), raw) and ("t=1782950400", raw) are ErrBadSignature
	// VerifyA("sec_a1", "t=1,v1=00,v1="+signA("sec_a1", "1", raw), raw) == nil  (any v1, no tolerance)
}

func TestVerifyB(t *testing.T) {
	// valid base64 HMAC -> nil; HMAC with "sec_b2" for tenant secret "sec_a2" -> ErrBadSignature; "" -> ErrBadSignature
}

func TestPeek(t *testing.T) {
	// PeekAccount([]byte(`{"account":"acct_a","id":"x"}`)) == "acct_a", nil
	// PeekAccount([]byte(`{"id":"x"}`)) == "", nil
	// PeekAccount([]byte(`{not json`)) returns a non-nil error; same three cases for PeekShopDomain
}
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `cd part2/backbone && go test ./internal/webhook/...`
Expected: FAIL.

- [ ] **Step 3: Implement the four functions**

Compare MACs with `hmac.Equal` on decoded bytes. An undecodable hex or base64 value counts as a mismatch.

- [ ] **Step 4: Run the tests and see them pass**

Run: `cd part2/backbone && go test ./internal/webhook/...`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add part2/backbone/internal/webhook
git commit -m "Add vendor signature verification"
```

### Task 3: Canonical events

**Files:**
- Create: `part2/backbone/internal/canon/event.go` (Event, ordering), `data.go` (typed data), `vendor_a.go`, `vendor_b.go`, `canon_test.go`
- Create: `part2/backbone/internal/canon/testdata/normalization_examples.json` (a copy of `$INFRA/data/normalization_examples.json`)

**Interfaces:**
- Produces:
  - `canon.Event{EventID string "event_id"; TenantID string "tenant_id"; Type string "type"; OccurredAtMs int64 "occurred_at_ms"; CustomerID *string "customer_id"; Data json.RawMessage "data"}`. The quoted names are the JSON tags; a nil `CustomerID` encodes as `null`.
  - Typed data with the SPEC's exact JSON keys:
    - `canon.OrderCreated{OrderID; Lines []canon.Line; Email; Name}` and `canon.Line{SKU "sku"; Qty int64 "qty"; UnitCents int64 "unit_cents"}`
    - `canon.OrderRefunded{OrderID; AmountCents int64}`
    - `canon.AdMetric{CampaignID; SpendCents, Impressions, Clicks int64}`
    - `canon.ShipmentUpdated{OrderID, Status, Carrier, Tracking}`
    - `canon.InventoryAdjusted{SKU; Delta int64; Reason}`
    - `canon.MessageReceived{Channel, Email, Body}`
  - `canon.FromVendorA(raw []byte, tenantID string) (canon.Event, error)` and `canon.FromVendorB(raw []byte, tenantID string) (canon.Event, error)`. Both return `canon.ErrMalformed` (wrapped) for anything they cannot map.
  - `canon.Less(a, b canon.Event) bool` and `canon.Sort(events []canon.Event)`.

- [ ] **Step 1: Copy the examples and write the failing tests**

Run: `cp "$INFRA/data/normalization_examples.json" part2/backbone/internal/canon/testdata/`

```go
func TestNormalizationExamples(t *testing.T) {
	// For each example {vendor "a"|"b", body, canonical}: raw := json.Marshal(body);
	// ev := FromVendorA/B(raw, canonical["tenant_id"]); jsonEqual(t, json.Marshal(ev), canonical)
	// jsonEqual decodes both sides with UseNumber and compares with reflect.DeepEqual.
	// The 7 examples cover every type, including the unknown type shipment.patch.
}

func TestVendorAUnknownType(t *testing.T) {
	raw := []byte(`{"id":"evt_9","type":"payout.paid","created":1782950400123,"account":"acct_a","livemode":true,"data":{"object":{"customer_id":"cus_1","amount":5}}}`)
	// Type == "payout.paid", *CustomerID == "cus_1", Data JSON-equal to {"customer_id":"cus_1","amount":5}
}

func TestUnknownTypeWithoutCustomer(t *testing.T) // vendor B "shop.note" with payload {"text":"x"} -> CustomerID == nil

func TestEmptyLinesEncodeAsArray(t *testing.T) // A order.created with "line_items": [] -> json.Marshal(ev) contains `"lines":[]`

func TestVendorBTimestamp(t *testing.T) // "2026-07-01T12:00:00.123Z" -> OccurredAtMs == 1782907200123

func TestMalformed(t *testing.T) {
	// A with "created": 1.5; A order.created without "line_items"; B with "timestamp": "2026-07-01 12:00";
	// A with quantity 2.5 -> each errors.Is(err, canon.ErrMalformed)
}

func TestLessIsBytewise(t *testing.T) {
	// same ms: "0f0e8a6c-…" < "evt_a"; "evt_a-1" < "evt_a_1" ('-' 0x2d < '_' 0x5f);
	// a smaller OccurredAtMs sorts first whatever the IDs
}
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `cd part2/backbone && go test ./internal/canon/...`
Expected: FAIL.

- [ ] **Step 3: Implement normalization per the SPEC table**

- Decode with `json.Decoder.UseNumber()`. Every integer field must be an integral `json.Number`, or the result is `ErrMalformed`.
- Vendor B times go through `time.Parse(time.RFC3339Nano, …)` and `UnixMilli()`, and the value must end in `Z`.
- Known types marshal their typed data.
- Unknown types keep the vendor object or payload bytes as `Data`, and take `customer_id` from it when it is a string.

- [ ] **Step 4: Run the tests and see them pass**

Run: `cd part2/backbone && go test ./internal/canon/...`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add part2/backbone/internal/canon
git commit -m "Add canonical event normalization and ordering"
```

### Task 4: Fold port with reducer fixtures

**Files:**
- Create: `part2/backbone/tools/gen_fixtures.py`
- Create: `part2/backbone/internal/fold/fold.go`, `fold_test.go`, `testdata/*.events.jsonl`, `testdata/*.expected.json` (generated)

**Interfaces:**
- Consumes: `canon.Event`, the typed data structs, `canon.Less`, `canon.Sort`.
- Produces:
  - `fold.Campaign{SpendCents "spend_cents", Impressions "impressions", Clicks "clicks" int64}`.
  - `fold.Result`, with the reducer's 16 keys as JSON tags: `TenantID string`; `EventCount, OrderCount, GrossCents, RefundedCents, NetCents, OpenOrders, OversoldUnits, CustomerCount, OrphanRefunds, OrphanShipments int64`; `ShipmentStatusCounts, Inventory, MessagesByChannel map[string]int64`; `LastContactMs *int64`; `Campaigns map[string]fold.Campaign`. Maps are never nil.
  - `fold.New(tenantID string, customerKey func(customerID string) string) *fold.State`.
  - `(*State) Apply(e canon.Event) error`. Callers apply events in `canon.Less` order. It returns an error only when a known type's data cannot be decoded.
  - `(*State) Result() fold.Result`. It does not mutate the state.
  - `fold.Fold(tenantID string, events []canon.Event, customerKey func(string) string) (fold.Result, error)`. It sorts a copy and applies every event.

**Generator.** `python3 -I tools/gen_fixtures.py "$INFRA"` is run from `part2/backbone`.
- It executes `part2/analysis/oracle.py` (path: `Path(__file__).resolve().parents[2] / "analysis" / "oracle.py"`) with `sys.argv = [oracle, infra]`, with its stdout redirected. It then uses the oracle's `store` (retained events per tenant) and `reducer`.
- Real tenants: take the first 4 tenant IDs, in sorted order, that have 200 to 1500 retained events. At least 2 of them must have erased customers, and together they must cover all 7 event types. Assert coverage.
- For each of them, write `testdata/<tid>.events.jsonl` with the events shuffled by `random.Random(7)`, and `testdata/<tid>.expected.json` with `json.dumps(reducer.fold(tid, events), sort_keys=True)`.
- Edge cases, each for tenant `t_edge`: write `testdata/edge_<name>.events.jsonl` and its expected file the same way, with these contents:
  1. `empty`: no events.
  2. `orphans_and_caps`: refund of o1 at t=1 before o1's `order.created` at t=2 (gross 1000); refunds of 600 at t=3 and t=4; a shipment for o2 (never created) at t=5.
  3. `duplicate_order`: two `order.created` for o1 at the same t=10. One has event_id `evt_b` (sku A, qty 1, customer cus_1). The other has event_id `0aa1b2c3-0000-4000-8000-000000000000` (sku B, qty 2, customer cus_2). The UUID sorts first, so sku A must never appear in inventory.
  4. `inventory_clamp`: `inventory.adjusted` A −10 at t=1, +3 at t=2, then an order for A with qty 5 at t=3.
  5. `shipment_status`: o1 shipped then delivered; o2 fully refunded; o3 untouched.
  6. `unknown_and_null`: a `shipment.patch` as the only event of cus_9; two `ad.metric` events for the same campaign (customer null); `message.received` on two channels at different times.

- [ ] **Step 1: Write the generator and run it**

Run: `cd part2/backbone && python3 -I tools/gen_fixtures.py "$INFRA"`
Expected: it prints the 4 chosen tenant IDs and writes 10 fixture pairs under `internal/fold/testdata/`.

- [ ] **Step 2: Write the failing tests**

```go
func identity(s string) string { return s }

func TestFoldMatchesReducer(t *testing.T) {
	// For every testdata/*.events.jsonl: events := readJSONL; exp := read matching .expected.json;
	// got := Fold(exp["tenant_id"], events, identity); jsonEqual(t, json.Marshal(got), exp)
}

func TestApplyContinuesFromAnyPoint(t *testing.T) {
	// For every fixture with n events, sorted: for k in {0, 1, n/3, n/2, n-1, n} (deduplicated, within range):
	// s := New(tid, identity); apply events[:k]; _ = s.Result(); _ = s.Result(); apply events[k:];
	// jsonEqual(s.Result(), Fold(tid, events, identity))
}

func TestEmptyResultShape(t *testing.T) {
	// json.Marshal(Fold("t_edge", nil, identity)) contains `"inventory":{}`, `"campaigns":{}`,
	// `"shipment_status_counts":{}`, `"messages_by_channel":{}` and `"last_contact_ms":null`, and no other null
	// (checked on the bytes, not only after decoding, because a decoded null and {} can both look empty)
}
```

- [ ] **Step 3: Run the tests and see them fail**

Run: `cd part2/backbone && go test ./internal/fold/...`
Expected: FAIL.

- [ ] **Step 4: Port `reducer.fold`**

Follow `$INFRA/reducer.py` line by line:
- `customers.add` runs before the type branch, through `customerKey`.
- `event_count` counts every applied event.
- Terminal statuses are `delivered` and `returned`.
- `Result` derives the order aggregates from the orders map.

- [ ] **Step 5: Run the tests and see them pass**

Run: `cd part2/backbone && go test ./internal/fold/...`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add part2/backbone/tools part2/backbone/internal/fold
git commit -m "Port reducer fold with reducer-generated fixtures"
```

### Task 5: Keys

**Files:**
- Create: `part2/backbone/internal/crypto/keys.go`, `keys_test.go`

**Interfaces:**
- Produces:
  - `crypto.LoadKEK(path string) (*crypto.KEK, error)`. The file must be exactly 32 bytes.
  - `crypto.NewKEK(key []byte) (*crypto.KEK, error)`.
  - `(*KEK) NewWrappedDEK(tenantID string) ([]byte, error)` makes a random 32-byte DEK and seals it with AAD `"dek:" + tenantID`.
  - `(*KEK) Unwrap(tenantID string, wrapped []byte) (*crypto.TenantKeys, error)`.
  - `(*TenantKeys) Seal(aad, plaintext []byte) []byte` returns a random 12-byte nonce followed by the ciphertext.
  - `(*TenantKeys) Open(aad, sealed []byte) ([]byte, error)`.
  - `(*TenantKeys) CustomerKey(customerID string) []byte` and `CustomerKeyHex(customerID string) string` (32-byte HMAC-SHA256).
  - `(*TenantKeys) SKUKey(sku string) []byte`, reserved for Plan 2.
  - `(*TenantKeys) CursorMAC(msg []byte) []byte`.

Sub-keys come from `crypto/hkdf.Key(sha256.New, dek, nil, label, 32)` with the labels `backbone/v1/payload`, `backbone/v1/customer`, `backbone/v1/sku` and `backbone/v1/cursor`. Payload encryption is AES-256-GCM.

- [ ] **Step 1: Write the failing tests**

```go
func TestWrapIsBoundToTenant(t *testing.T) {
	kek, _ := crypto.NewKEK(bytes.Repeat([]byte{7}, 32))
	w, _ := kek.NewWrappedDEK("t_1")
	// Unwrap("t_1", w) succeeds; Unwrap("t_2", w) returns an error
}

func TestSealOpen(t *testing.T) {
	// Open(aad, Seal(aad, p)) == p; Open([]byte("other"), sealed) errors; two Seal calls on the same p differ
}

func TestSubkeys(t *testing.T) {
	// CustomerKey("cus_1") != SKUKey("cus_1"); two Unwraps of the same w give equal CustomerKey("cus_1");
	// DEKs of t_1 and t_2 give different CustomerKey("cus_1")
}

func TestLoadKEKLength(t *testing.T) // 31-byte file -> error; 32-byte file -> ok
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `cd part2/backbone && go test ./internal/crypto/...`
Expected: FAIL.

- [ ] **Step 3: Implement the key functions**

- [ ] **Step 4: Run the tests and see them pass**

Run: `cd part2/backbone && go test ./internal/crypto/...`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add part2/backbone/internal/crypto
git commit -m "Add KEK, tenant DEK and derived keys"
```

### Task 6: Store foundation

**Files:**
- Create: `part2/backbone/internal/store/schema.sql` (embedded), `store.go`, `tenants.go`, `locks.go`, `tenants_test.go`
- Create: `part2/backbone/internal/store/storetest/storetest.go`
- Create: `part2/docker-compose.yml` (only the `postgres` service for now)

**Interfaces:**
- Consumes: `crypto.KEK`, `crypto.TenantKeys`.
- Produces:
  - `store.Open(ctx context.Context, databaseURL string, kek *crypto.KEK) (*store.Store, error)` and `(*Store) Close()`.
  - `(*Store) Migrate(ctx) error`.
  - `(*Store) EnsureTenants(ctx, ids []string) error`.
  - `(*Store) Scope(ctx, tenantID string) (store.Scope, error)`.
  - `store.Scope` has unexported fields, so only the store can make one. Its methods are `TenantID() string` and `Keys() *crypto.TenantKeys`.
  - `store.ErrTenantErased` and `store.ErrUnknownTenant`.
  - `storetest.New(t *testing.T) (*store.Store, *crypto.KEK)` and `storetest.Reopen(t *testing.T, st *store.Store, kek *crypto.KEK) *store.Store`. The second makes a second store on the same schema and stands in for another node or a restart.

Schema (`schema.sql`):

```sql
CREATE TABLE IF NOT EXISTS tenants (
  tenant_id text PRIMARY KEY,
  status    text NOT NULL CHECK (status IN ('active', 'erased')),
  erased_at timestamptz
);
CREATE TABLE IF NOT EXISTS tenant_keys (
  tenant_id   text PRIMARY KEY REFERENCES tenants,
  wrapped_dek bytea NOT NULL
);
ALTER TABLE tenant_keys ALTER COLUMN wrapped_dek SET STATISTICS 0;
CREATE TABLE IF NOT EXISTS hot_events (
  tenant_id      text NOT NULL,
  event_id       text COLLATE "C" NOT NULL,
  occurred_at_ms bigint NOT NULL,
  customer_key   bytea,
  payload        bytea NOT NULL,
  PRIMARY KEY (tenant_id, event_id)
);
CREATE INDEX IF NOT EXISTS hot_events_order ON hot_events (tenant_id, occurred_at_ms, event_id);
CREATE INDEX IF NOT EXISTS hot_events_customer ON hot_events (tenant_id, customer_key) WHERE customer_key IS NOT NULL;
ALTER TABLE hot_events ALTER COLUMN payload SET STATISTICS 0;
CREATE TABLE IF NOT EXISTS tombstones (
  tenant_id    text NOT NULL,
  customer_key bytea NOT NULL,
  status       text NOT NULL CHECK (status IN ('pending', 'done')),
  requested_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, customer_key)
);
```

**Behavior:**
- `Open` sets the pool runtime parameter `synchronous_commit=on`.
- `Migrate` runs `schema.sql` while holding a session `pg_advisory_lock` on `lockKey("migrate")`, on one connection.
- `EnsureTenants` does, per ID: `INSERT INTO tenants … ON CONFLICT DO NOTHING` with status `active`. If the status is `active` and the tenant has no key row, it inserts `kek.NewWrappedDEK(id)` with `ON CONFLICT DO NOTHING`. It never creates a key for an erased tenant.
- `Scope` returns cached keys, or else reads and unwraps the stored DEK. It always uses the stored DEK, never one it generated itself. A missing key row gives `ErrTenantErased` if the tenant is erased and `ErrUnknownTenant` if the tenant does not exist.
- `locks.go` has `lockKey(kind string, parts ...[]byte) int64`, the first 8 bytes of SHA-256 over the kind and the length-prefixed parts.
- `storetest.New` skips the test unless `BACKBONE_TEST_DATABASE_URL` is set. It creates a schema `t_<random hex>`, opens the store with `search_path=<schema>` added to the URL, migrates, and drops the schema on cleanup.
- The compose `postgres` service: image `postgres:17`, `POSTGRES_HOST_AUTH_METHOD=trust`, port `127.0.0.1:55432:5432`, a `pg_isready` healthcheck, and the volume `pgdata`.

- [ ] **Step 1: Write the failing tests**

```go
func TestMigrateConcurrent(t *testing.T) {
	// st1, kek := storetest.New(t); st2 := storetest.Reopen(t, st1, kek)
	// run st1.Migrate and st2.Migrate in two goroutines -> both nil; st1.Migrate again -> nil
}

func TestEnsureTenantsConcurrent(t *testing.T) {
	// st1, st2 as above; EnsureTenants(ctx, []string{"t_1","t_2"}) on both concurrently -> nil
	// sc1, _ := st1.Scope(ctx, "t_1"); sc2, _ := st2.Scope(ctx, "t_1")
	// bytes.Equal(sc1.Keys().CustomerKey("c"), sc2.Keys().CustomerKey("c"))
}

func TestScopeErrors(t *testing.T) {
	// Scope(ctx, "t_missing") -> ErrUnknownTenant
	// after SQL: UPDATE tenants SET status='erased' WHERE tenant_id='t_1'; DELETE FROM tenant_keys WHERE tenant_id='t_1'
	// a fresh store's Scope(ctx, "t_1") -> ErrTenantErased
}

func TestCiphertextStatisticsOff(t *testing.T) {
	// attstattarget from pg_attribute for hot_events.payload and tenant_keys.wrapped_dek == 0
}
```

- [ ] **Step 2: Start Postgres and see the tests fail**

Run: `docker compose -f part2/docker-compose.yml up -d --wait postgres && cd part2/backbone && BACKBONE_TEST_DATABASE_URL='postgres://postgres@127.0.0.1:55432/postgres?sslmode=disable' go test ./internal/store/...`
Expected: FAIL.

- [ ] **Step 3: Implement `Open`, `Migrate`, `EnsureTenants`, `Scope`, the lock key and `storetest`**

- [ ] **Step 4: Run the tests and see them pass**

Run: the same command as step 2.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add part2/docker-compose.yml part2/backbone/internal/store
git commit -m "Add Postgres store with schema, tenant keys and scopes"
```

### Task 7: Ingest and reads in the store

**Files:**
- Create: `part2/backbone/internal/store/events.go`, `events_test.go`

**Interfaces:**
- Consumes: `store.Scope`, `canon.Event`, `canon.Sort`, `crypto.TenantKeys`.
- Produces:
  - `store.IngestResult` with the constants `store.Stored`, `store.Duplicate`, `store.CustomerErased` and `store.TenantErased`.
  - `(*Store) Ingest(ctx, sc store.Scope, ev canon.Event) (store.IngestResult, error)`.
  - `store.Key{OccurredAtMs int64; EventID string}`.
  - `(*Store) ScanAll(ctx, sc store.Scope, fn func(canon.Event) error) error` calls `fn` for every hot event in key order.
  - `(*Store) Range(ctx, sc store.Scope, fromMs, toMs int64, after *store.Key, limit int) ([]canon.Event, error)` returns events with `fromMs <= occurred_at_ms < toMs` and key strictly greater than `after`, in key order, at most `limit` of them.

**Behavior:**
- `Ingest` runs one `READ COMMITTED` transaction:
  1. `pg_advisory_xact_lock_shared(lockKey("tenant-status", tenant))`, then read the status. If erased, return `TenantErased`.
  2. If `CustomerID != nil`: `pg_advisory_xact_lock_shared(lockKey("customer", tenant, customerKey))`, then check `tombstones`. If a tombstone exists, return `CustomerErased` and write nothing.
  3. `INSERT … ON CONFLICT (tenant_id, event_id) DO NOTHING`. The payload is `Seal(tenant + "\x00" + event_id, json.Marshal(ev))`. Zero rows affected means `Duplicate`.
- `ScanAll` and `Range` each run one `REPEATABLE READ READ ONLY` transaction whose first statement reads the tenant status; erased gives `ErrTenantErased`. They decrypt each payload with the same AAD. `Range` filters with `(occurred_at_ms, event_id) > ($after_ms, $after_id)` and `ORDER BY occurred_at_ms, event_id LIMIT $limit`.
- Plan 2 adds the cold-commit lock and the `cold_until` check to `Ingest`. Do not add them here.

- [ ] **Step 1: Write the failing tests**

```go
func TestIngestStoresAndDedupes(t *testing.T) {
	// ev of cus_1 -> Stored; same ev again -> Duplicate; ScanAll yields exactly [ev] (JSON-equal)
}

func TestIngestEncrypts(t *testing.T) {
	// ingest an order.created with email "x@example.com" for cus_1;
	// raw SELECT payload FROM hot_events contains neither "cus_1" nor "x@example.com";
	// SELECT customer_key equals sc.Keys().CustomerKey("cus_1")
}

func TestIngestDropsErasedCustomer(t *testing.T) {
	// INSERT INTO tombstones (tenant_id, customer_key, status) VALUES ('t_1', CustomerKey("cus_1"), 'done');
	// Ingest of a cus_1 event -> CustomerErased; ScanAll yields nothing
}

func TestIngestErasedTenant(t *testing.T) {
	// UPDATE tenants SET status='erased' -> Ingest -> TenantErased; ScanAll -> ErrTenantErased
}

func TestScanAllOrder(t *testing.T) {
	// ingest, in shuffled order, events at ms 5 with IDs "evt_a_1", "evt_a-1", "0f0e8a6c-0000-4000-8000-000000000000"
	// plus one at ms 4; ScanAll order equals canon.Sort of the same events
}

func TestRangePagingTies(t *testing.T) {
	// 25 events at ms 1000 with mixed evt_/UUID IDs, 5 at ms 999, 5 at ms 1001
	// page with limit 1 from after=nil, passing the last event's key as after each time, over [999, 1001)
	// -> exactly the 30 events at 999 and 1000 in canon order, no repeats; ms 1001 never returned
}
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `cd part2/backbone && BACKBONE_TEST_DATABASE_URL='postgres://postgres@127.0.0.1:55432/postgres?sslmode=disable' go test ./internal/store/...`
Expected: FAIL.

- [ ] **Step 3: Implement `Ingest`, `ScanAll` and `Range`**

- [ ] **Step 4: Run the tests and see them pass**

Run: the same command as step 2.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add part2/backbone/internal/store
git commit -m "Add encrypted ingest and ordered reads to the store"
```

### Task 8: Erasure in the store

**Files:**
- Create: `part2/backbone/internal/store/erase.go`, `erase_test.go`

**Interfaces:**
- Consumes: `store.Scope`, the lock keys.
- Produces:
  - `(*Store) EraseCustomer(ctx, sc store.Scope, customerID string) error`.
  - `(*Store) EraseTenant(ctx, tenantID string) error`. It is idempotent and returns nil for a tenant that is already erased.

**Behavior** (spec §11.1 and §11.2, hot tier only):
- `EraseCustomer`:
  1. Transaction 1: `pg_advisory_xact_lock(lockKey("customer", tenant, key))`, then `INSERT INTO tombstones … status 'pending' ON CONFLICT DO NOTHING`. Commit. If the tombstone was already `done`, return nil.
  2. Transaction 2: shared tenant-status lock; `DELETE FROM hot_events WHERE tenant_id = $1 AND customer_key = $2`; `UPDATE tombstones SET status = 'done'`. Commit.
- `EraseTenant`, in one transaction: `pg_advisory_xact_lock(lockKey("tenant-status", tenant))`, set the status to `erased` and `erased_at = now()`, then delete the tenant's `tenant_keys`, `hot_events` and `tombstones` rows. Commit, then drop the tenant's cached keys.
- Any operation that sees `ErrTenantErased` drops that tenant's cached keys.

- [ ] **Step 1: Write the failing tests**

```go
func TestEraseCustomerRemovesAllTypes(t *testing.T) {
	// cus_1: order.created, message.received, and shipment.patch (unknown type, customer_id in payload); cus_2: one event
	// EraseCustomer(cus_1) -> nil; ScanAll yields only cus_2's event; tombstone status is 'done'
	// EraseCustomer(cus_1) again -> nil; a later Ingest of a new cus_1 event -> CustomerErased
}

func TestEraseCustomerRacesIngest(t *testing.T) {
	// 50 goroutines each ingest a distinct cus_1 event; after 10 of them have returned, call EraseCustomer(cus_1)
	// wait for all goroutines: every result is Stored or CustomerErased; ScanAll yields zero cus_1 events
}

func TestEraseTenant(t *testing.T) {
	// EraseTenant("t_1") -> nil; Scope(ctx, "t_1") -> ErrTenantErased;
	// row counts for t_1 in hot_events, tenant_keys, tombstones == 0; EraseTenant("t_1") again -> nil
}

func TestEraseTenantSurvivesRestart(t *testing.T) {
	// EraseTenant("t_1"); st2 := storetest.Reopen(...); st2.EnsureTenants(ctx, []string{"t_1","t_2"})
	// tenant_keys has no row for t_1; st2.Scope(ctx, "t_1") -> ErrTenantErased; t_2 still works
}
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `cd part2/backbone && BACKBONE_TEST_DATABASE_URL='postgres://postgres@127.0.0.1:55432/postgres?sslmode=disable' go test ./internal/store/...`
Expected: FAIL.

- [ ] **Step 3: Implement `EraseCustomer` and `EraseTenant`**

- [ ] **Step 4: Run the tests and see them pass**

Run: the same command as step 2.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add part2/backbone/internal/store
git commit -m "Add customer and tenant erasure for the hot tier"
```

### Task 9: HTTP API

**Files:**
- Create: `part2/backbone/internal/api/server.go` (routes, `/healthz`), `webhooks.go`, `reads.go`, `erase.go`, `cursor.go`, `logging.go`, `api_test.go`, `testdata/tenants.json` (a copy of Task 1's file)

**Interfaces:**
- Consumes: `tenants.Registry`, `webhook.*`, `canon.FromVendorA/B`, `fold.Fold`, `store.Store` (all of Tasks 6 to 8), `crypto.TenantKeys.CursorMAC` and `CustomerKeyHex`.
- Produces: `api.NewServer(reg *tenants.Registry, st *store.Store, log *slog.Logger) http.Handler`.

**Routes and behavior** (Go 1.22 `ServeMux` patterns):
- `POST /webhooks/vendor-a` and `POST /webhooks/vendor-b`. The body is capped by `http.MaxBytesReader` at 1 MiB; over the cap gives `400`. Steps, in order:
  1. Peek. Invalid JSON gives `400`.
  2. Registry lookup. A missing or unknown account or shop domain gives `404`.
  3. Verify the signature with that tenant's secret. Failure gives `401`.
  4. Normalize. `ErrMalformed` gives `400`.
  5. `Scope`. `ErrTenantErased` gives `410`.
  6. `Ingest`. `Stored`, `Duplicate` and `CustomerErased` give `200`; `TenantErased` gives `410`; an error gives `500`.
- `GET /tenants/{id}/state`. `Authorization: Bearer <token>` is required; a missing or unknown token gives `401`. A token whose tenant differs from `{id}` gives `404`. Then `Scope` and `ScanAll`; `ErrTenantErased` from either gives `410`. The body is `fold.Fold` over the scanned events, with `customerKey = sc.Keys().CustomerKeyHex`.
- `GET /tenants/{id}/events`:
  - Authorization is the same as for state.
  - `from_ms` and `to_ms` are required integers; otherwise `400`.
  - `limit` defaults to 1000 and is capped at 1000; a value below 1 or not an integer gives `400`.
  - Fetch `limit + 1` rows to decide whether a next page exists. The response is `{"events":[…],"next_cursor":<string or null>}`.
  - The cursor is `base64url(json{"f":from,"t":to,"o":last_ms,"i":last_id}) + "." + base64url(CursorMAC(payload))`. A bad MAC, a different tenant's MAC, or an `f`/`t` that differs from the query gives `400`.
- `DELETE /tenants/{id}/customers/{customer_id}` and `DELETE /tenants/{id}`. `Authorization: Bearer <admin_token>` is required, otherwise `401`. A tenant not in the registry gives `404`. Customer erasure: `Scope`; `ErrTenantErased` gives `204`; then `EraseCustomer` and `204`. Tenant erasure: `EraseTenant`, then `204`.
- `GET /healthz` gives `200` when the database answers a ping.
- The logging middleware writes one line per request with `r.Pattern`, status and duration, and nothing else from the request.

- [ ] **Step 1: Write the failing tests**

Use `httptest.Server` with `storetest.New`, the copied `testdata/tenants.json` and `EnsureTenants(["t_a","t_b"])`. Sign request bodies with the test secrets.

```go
func TestWebhookStatusCodes(t *testing.T) {
	// table: valid A order.created -> 200; same delivery again -> 200; `{bad` -> 400; account "acct_zz" -> 404;
	// t_a's body signed with t_b's secret "sec_b1" -> 401; no signature header -> 401;
	// valid signature but "created": 1.5 -> 400; valid B inventory.adjusted -> 200
	// after DELETE /tenants/t_b: genuine t_b delivery -> 410, t_b body with a random secret -> 401
	// after DELETE /tenants/t_a/customers/cus_1: genuine cus_1 delivery -> 200 and absent from /events
}

func TestStateEndpoint(t *testing.T) {
	// after 3 ingested events, GET /tenants/t_a/state with tok_a -> 200, body JSON-equal to fold.Fold of those 3
	// a tenant with no events -> 200 and the body bytes contain "inventory":{} (not null)
	// no Authorization -> 401; "Bearer nope" -> 401; tok_a on /tenants/t_b/state -> 404
	// after DELETE /tenants/t_b: tok_b on /tenants/t_b/state -> 410; tok_a on /tenants/t_b/state -> 404
}

func TestEventsEndpoint(t *testing.T) {
	// 5 events; limit=2 gives pages of 2, 2, 1 with next_cursor non-null, non-null, null; IDs in canon order
	// missing from_ms -> 400; limit=0 -> 400; limit=abc -> 400
	// a window with no events -> body bytes are exactly {"events":[],"next_cursor":null}
	//   (verify.py iterates body["events"], so null there would crash it)
}

func TestParseLimit(t *testing.T) // "" -> 1000; "5000" -> 1000; "7" -> 7; "0" and "-1" -> error

func TestEventsCursorTampering(t *testing.T) {
	// take page 1's next_cursor: flip one character -> 400;
	// same cursor with tok_b on /tenants/t_b/events with the same from/to -> 400;
	// same cursor with a different to_ms -> 400
}

func TestErasureEndpoints(t *testing.T) {
	// DELETE customer with tok_a -> 401; with adm_test -> 204 and the customer's events gone from /events;
	// DELETE /tenants/t_b -> 204, again -> 204; DELETE /tenants/t_zz -> 404
}

func TestLogsCarryNoPathsOrIDs(t *testing.T) {
	// slog JSON handler writing to a buffer; send DELETE /tenants/t_a/customers/cus_secret and one webhook
	// buffer contains "DELETE /tenants/{id}/customers/{customer_id}" and contains neither "cus_secret"
	// nor "/tenants/t_a/customers"
}
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `cd part2/backbone && BACKBONE_TEST_DATABASE_URL='postgres://postgres@127.0.0.1:55432/postgres?sslmode=disable' go test ./internal/api/...`
Expected: FAIL.

- [ ] **Step 3: Implement the handlers, cursor and logging middleware**

- [ ] **Step 4: Run the tests and see them pass**

Run: the same command as step 2.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add part2/backbone/internal/api
git commit -m "Add HTTP API for webhooks, reads and erasure"
```

### Task 10: Binary, compose, LB and end-to-end run

**Files:**
- Create: `part2/backbone/cmd/api/main.go`, `part2/backbone/Dockerfile`
- Modify: `part2/docker-compose.yml` (add `kek-init`, `api1`, `api2`, `lb`)
- Create: `part2/deploy/nginx.conf`
- Create: `part2/scripts/replay.sh`, `part2/scripts/verify.sh`, `part2/scripts/e2e.sh`
- Create: `part2/README.md` (how to run, in English)

**Interfaces:**
- Consumes: everything above.
- Produces: the `docker compose` stack and the three scripts. Each script takes the data directory as `$1` and requires `INFRA`.

**Behavior:**
- `main`: `config.Load(os.Getenv)` → `tenants.Load` → `crypto.LoadKEK` → `store.Open` → `Migrate` → `EnsureTenants(ids from the registry)` → `http.Server{Addr: cfg.Listen, Handler: api.NewServer(…), ReadHeaderTimeout: 10 * time.Second}`. `SIGTERM` triggers a graceful shutdown.
- The Dockerfile builds in `golang:1.24` (`CGO_ENABLED=0 go build ./cmd/api`) and runs in `alpine:3.20`, which has `wget` for the healthcheck.
- Compose services:
  - `kek-init`: `alpine:3.20`, `sh -c '[ -s /secrets/kek ] || head -c 32 /dev/urandom > /secrets/kek'`, with the volume `secrets`.
  - `api1` and `api2`: built from `./backbone`. Environment: `BACKBONE_DATABASE_URL=postgres://postgres@postgres:5432/postgres?sslmode=disable`, `BACKBONE_TENANTS_FILE=/config/tenants.json`, `BACKBONE_KEK_FILE=/secrets/kek`. Volumes: `${TENANTS_FILE:?set TENANTS_FILE}:/config/tenants.json:ro` and `secrets:/secrets:ro`. They depend on `postgres` (healthy) and `kek-init` (completed successfully), use `restart: unless-stopped`, and have a healthcheck `wget -qO- http://localhost:8080/healthz`.
  - `lb`: `nginx:1.27-alpine`, port `8080:8080`, depends on both api services being healthy, and mounts `./deploy/nginx.conf`.
- `nginx.conf`:

```nginx
error_log /dev/stderr crit;
events {}
http {
  access_log off;
  upstream api { server api1:8080; server api2:8080; }
  server {
    listen 8080;
    client_max_body_size 1m;
    location / {
      proxy_pass http://api;
      proxy_http_version 1.1;
      proxy_set_header Connection "";
    }
  }
}
```

- `e2e.sh <data-dir>`:
  1. `docker compose -f part2/docker-compose.yml down -v`
  2. `TENANTS_FILE=<absolute data-dir>/tenants.json docker compose … up -d --build --wait`
  3. `replay.sh <data-dir>`, which runs `python3 "$INFRA/replay.py" --target http://localhost:8080 --tenants … --deliveries … --responses-out part2/out/<name>/replay_responses.json`
  4. `verify.sh <data-dir>`, which runs `python3 "$INFRA/verify.py"` with `--expected`, `--responses` and `--ranges` from that directory.

  It exits with `verify.py`'s exit code.

- [ ] **Step 1: Write `main`, the Dockerfile, the compose services, `nginx.conf`, the scripts and the README**

- [ ] **Step 2: Run the supplied data end to end**

Run: `INFRA=~/Downloads/BARO_Work_Trial/infrastructure part2/scripts/e2e.sh "$INFRA/data"`
Expected: `verify.py` prints `state: 200 tenants match, 0 do not`, `isolation: 0 cross-tenant reads allowed`, `ranges: 48 of 48 windows match` and `PASS`.

- [ ] **Step 3: Run a fresh seed end to end**

Run: `python3 "$INFRA/generate.py" --seed 7 --out /tmp/backbone-seed7 && INFRA=… part2/scripts/e2e.sh /tmp/backbone-seed7`
Expected: `PASS`.

- [ ] **Step 4: Check that one api node can die**

Run: start `replay.sh` on the supplied data, run `docker compose -f part2/docker-compose.yml kill api1` while it runs, then `docker compose … start api1`, and run `verify.sh`.
Expected: replay reports `0 never succeeded`, and verify prints `PASS`.

- [ ] **Step 5: Check that no customer ID reached the logs**

Run: `docker compose -f part2/docker-compose.yml logs api1 api2 lb postgres | grep -c 'cus_'`
Expected: `0`.

- [ ] **Step 6: Commit**

```bash
git add part2/backbone/cmd part2/backbone/Dockerfile part2/docker-compose.yml part2/deploy part2/scripts part2/README.md
git commit -m "Add api binary, compose stack and end-to-end scripts"
```

---

## Outcome and follow-ups (added after execution, 2026-11-11)

**Result.** All ten tasks are done and reviewed, and the whole-branch review found no Critical issue. End-to-end on the supplied data at the final commit: 100,560 deliveries in 74.4 s with 0 retries, state 200/200, isolation 0 leaks, ranges 48/48, `PASS`, and no `cus_` in any container log. The fresh seed 7 run also passed, as did a run with one api node killed mid-replay.

**Deviations from this plan.**
- Task 4: the fixtures use t_0010, t_0011, t_0016 and t_0018. The first four tenants in the 200–1500 band had no erased customers, so the generator takes two with erasures and two without.
- Task 6: the migration test runs on fresh empty schemas (`storetest.NewUnmigrated`), because the planned shape could not fail. `EnsureTenants` takes the shared tenant-status lock so it cannot add a key during a tenant erasure.
- pgx is pinned to v5.7.6, because later versions require Go 1.25.
- The final review added `Store.Ping`, the rejection of empty signing secrets, a deterministic erase-versus-ingest lock-order test, and a test that an unsigned malformed delivery gets `401`.

**Open decisions and follow-ups for Plan 2 or later.**
1. **Normalization strictness.** A genuine, signed delivery with a null or missing field that the reducer never reads (`email`, `name`, `carrier`, `tracking`, `reason`, `body`) gets `400`. The sender never retries a `400`, so the event would be lost. The supplied and generated data never contain such a delivery. This needs an explicit decision.
2. **Cross-vendor type names (resolved).** An unknown-type delivery whose type name equals a known type (for example a vendor B `order.created`) is still stored verbatim, as the SPEC requires. If its data lacks a field that `reducer.py` reads for that type, or has the wrong JSON type, the fold now counts it like an unknown type: `event_count` and the customer only. The reference reducer raises `KeyError` there, so this case is undefined. Well-formed events are applied as before.
3. **Operations.**
   - A `500` records no cause; log a fixed reason code per call site.
   - Every startup's `CREATE INDEX IF NOT EXISTS` briefly blocks writers. Skip the DDL when the schema version is current.
   - The key cache has no TTL.
   - `Ingest` does not check that the event's tenant matches the scope.
4. **Hardening (dev compose).** The containers run as root, the KEK file is created `0644`, nginx resolves its upstreams once at start, and the server has no `IdleTimeout`.
