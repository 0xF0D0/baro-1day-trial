package store_test

import (
	"bytes"
	"context"
	"encoding/json"
	"math"
	"testing"

	"backbone/internal/canon"
	"backbone/internal/fold"
	"backbone/internal/store"
	"backbone/internal/store/storetest"
)

func newObjScope(t *testing.T, id string) (*store.Store, store.Scope) {
	t.Helper()
	ctx := context.Background()
	st, _ := storetest.New(t)
	if err := st.EnsureTenants(ctx, []string{id, "other"}); err != nil {
		t.Fatal(err)
	}
	sc, err := st.Scope(ctx, id)
	if err != nil {
		t.Fatal(err)
	}
	return st, sc
}

func sampleEvents() []canon.Event {
	cid := "cust-1"
	mk := func(id string, ms int64) canon.Event {
		return canon.Event{
			EventID: id, TenantID: "t_1", Type: "message.sent", OccurredAtMs: ms,
			CustomerID: &cid, Data: json.RawMessage(`{"email":"jane@example.com","channel":"sms"}`),
		}
	}
	// Deliberately out of key order.
	return []canon.Event{mk("evt-c", 300), mk("evt-a", 100), mk("evt-b", 200)}
}

func TestBucketObjectRoundTrip(t *testing.T) {
	ctx := context.Background()
	st, sc := newObjScope(t, "t_1")
	name, err := st.PutBucket(ctx, sc, 5, sampleEvents())
	if err != nil {
		t.Fatal(err)
	}
	got, err := st.GetBucket(ctx, sc, name)
	if err != nil {
		t.Fatal(err)
	}
	want := sampleEvents()
	canon.Sort(want)
	gj, _ := json.Marshal(got)
	wj, _ := json.Marshal(want)
	if !bytes.Equal(gj, wj) {
		t.Fatalf("round trip mismatch:\n got %s\nwant %s", gj, wj)
	}
}

func TestObjectsAreSealedPerTenant(t *testing.T) {
	ctx := context.Background()
	st, sc := newObjScope(t, "t_1")
	name, err := st.PutBucket(ctx, sc, 5, sampleEvents())
	if err != nil {
		t.Fatal(err)
	}
	raw, err := st.Objects().Get(ctx, name)
	if err != nil {
		t.Fatal(err)
	}
	for _, s := range []string{"evt-a", "jane@example.com", "cust-1"} {
		if bytes.Contains(raw, []byte(s)) {
			t.Fatalf("raw object contains %q", s)
		}
	}
	other, err := st.Scope(ctx, "other")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := st.GetBucket(ctx, other, name); err == nil {
		t.Fatal("another tenant's scope opened the bucket")
	}
}

func TestSnapshotObjectRoundTrip(t *testing.T) {
	ctx := context.Background()
	st, sc := newObjScope(t, "t_1")
	state := fold.New("t_1", func(c string) string { return c })
	for _, e := range sampleEvents() {
		if err := state.Apply(e); err != nil {
			t.Fatal(err)
		}
	}
	snap := state.Snapshot()
	coldUntil := int64(3 * 86400000)
	name, err := st.PutSnapshot(ctx, sc, coldUntil, snap)
	if err != nil {
		t.Fatal(err)
	}
	got, err := st.GetSnapshot(ctx, sc, name)
	if err != nil {
		t.Fatal(err)
	}
	gj, _ := json.Marshal(got)
	wj, _ := json.Marshal(snap)
	if !bytes.Equal(gj, wj) {
		t.Fatalf("snapshot mismatch:\n got %s\nwant %s", gj, wj)
	}
	sealed, err := st.Objects().Get(ctx, name)
	if err != nil {
		t.Fatal(err)
	}
	plain, err := sc.Keys().Open([]byte("t_1\x00"+name), sealed)
	if err != nil {
		t.Fatal(err)
	}
	var doc struct {
		Version   string `json:"version"`
		ColdUntil int64  `json:"cold_until"`
	}
	if err := json.Unmarshal(plain, &doc); err != nil {
		t.Fatal(err)
	}
	if doc.Version != "v1" || doc.ColdUntil != coldUntil {
		t.Fatalf("doc = %+v", doc)
	}
}

func TestEnsureTenantsCreatesColdRow(t *testing.T) {
	ctx := context.Background()
	st, _ := newObjScope(t, "t_1")
	var until int64
	var dirty bool
	var snap *string
	err := st.Pool().QueryRow(ctx,
		`SELECT cold_until, dirty, snapshot_object FROM tenant_cold WHERE tenant_id = 't_1'`).Scan(&until, &dirty, &snap)
	if err != nil {
		t.Fatal(err)
	}
	if until != math.MinInt64 || dirty || snap != nil {
		t.Fatalf("cold row = %d %v %v", until, dirty, snap)
	}
}
