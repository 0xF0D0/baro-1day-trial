package store_test

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sync"
	"testing"

	"backbone/internal/canon"
	"backbone/internal/store"
	"backbone/internal/store/storetest"
)

func count(t *testing.T, st *store.Store, query string, args ...any) int {
	t.Helper()
	var n int
	if err := st.Pool().QueryRow(context.Background(), query, args...).Scan(&n); err != nil {
		t.Fatal(err)
	}
	return n
}

func TestEraseCustomerRemovesAllTypes(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	cus1, cus2 := "cus_1", "cus_2"
	events := []canon.Event{
		mkEvent("evt_1", 100, cus1),
		{EventID: "evt_2", TenantID: "t_1", Type: "message.received", OccurredAtMs: 200,
			CustomerID: &cus1, Data: json.RawMessage(`{"body":"hi"}`)},
		{EventID: "evt_3", TenantID: "t_1", Type: "shipment.patch", OccurredAtMs: 300,
			CustomerID: &cus1, Data: json.RawMessage(`{"customer_id":"cus_1","status":"sent"}`)},
		mkEvent("evt_4", 400, cus2),
	}
	for _, ev := range events {
		if res, err := st.Ingest(ctx, sc, ev); err != nil || res != store.Stored {
			t.Fatalf("ingest %s: %v, %v", ev.EventID, res, err)
		}
	}
	for i := 0; i < 2; i++ {
		if err := st.EraseCustomer(ctx, sc, cus1); err != nil {
			t.Fatalf("erase %d: %v", i, err)
		}
		got := scanAll(t, st, sc)
		if len(got) != 1 || got[0].EventID != "evt_4" {
			t.Fatalf("after erase %d: %+v", i, got)
		}
		key := sc.Keys().CustomerKey(cus1)
		var status string
		if err := st.Pool().QueryRow(ctx,
			`SELECT status FROM tombstones WHERE tenant_id = 't_1' AND customer_key = $1`, key).Scan(&status); err != nil || status != "done" {
			t.Fatalf("tombstone: %q, %v", status, err)
		}
	}
	res, err := st.Ingest(ctx, sc, mkEvent("evt_5", 500, cus1))
	if err != nil || res != store.CustomerErased {
		t.Fatalf("late ingest: %v, %v", res, err)
	}
}

func TestEraseCustomerRacesIngest(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	const n = 50
	results := make([]store.IngestResult, n)
	errs := make([]error, n)
	var wg sync.WaitGroup
	started := make(chan struct{}, n)
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			results[i], errs[i] = st.Ingest(ctx, sc, mkEvent(fmt.Sprintf("evt_%03d", i), int64(i), "cus_1"))
			started <- struct{}{}
		}(i)
	}
	for i := 0; i < 10; i++ {
		<-started
	}
	if err := st.EraseCustomer(ctx, sc, "cus_1"); err != nil {
		t.Fatal(err)
	}
	wg.Wait()
	for i := 0; i < n; i++ {
		if errs[i] != nil {
			t.Fatalf("ingest %d: %v", i, errs[i])
		}
		if results[i] != store.Stored && results[i] != store.CustomerErased {
			t.Fatalf("ingest %d: unexpected result %v", i, results[i])
		}
	}
	for _, e := range scanAll(t, st, sc) {
		if e.CustomerID != nil && *e.CustomerID == "cus_1" {
			t.Fatalf("surviving cus_1 event %s", e.EventID)
		}
	}
	key := sc.Keys().CustomerKey("cus_1")
	if c := count(t, st, `SELECT count(*) FROM hot_events WHERE tenant_id = 't_1' AND customer_key = $1`, key); c != 0 {
		t.Fatalf("%d rows remain", c)
	}
}

func TestEraseTenant(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	if _, err := st.Ingest(ctx, sc, mkEvent("evt_1", 1, "cus_1")); err != nil {
		t.Fatal(err)
	}
	if err := st.EraseCustomer(ctx, sc, "cus_1"); err != nil {
		t.Fatal(err)
	}
	if _, err := st.Ingest(ctx, sc, mkEvent("evt_2", 2, "cus_2")); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 2; i++ {
		if err := st.EraseTenant(ctx, "t_1"); err != nil {
			t.Fatalf("erase %d: %v", i, err)
		}
	}
	if _, err := st.Scope(ctx, "t_1"); !errors.Is(err, store.ErrTenantErased) {
		t.Fatalf("scope: %v", err)
	}
	for _, tbl := range []string{"hot_events", "tenant_keys", "tombstones"} {
		if c := count(t, st, `SELECT count(*) FROM `+tbl+` WHERE tenant_id = 't_1'`); c != 0 {
			t.Fatalf("%s has %d rows", tbl, c)
		}
	}
	res, err := st.Ingest(ctx, sc, mkEvent("evt_3", 3, "cus_2"))
	if err != nil || res != store.TenantErased {
		t.Fatalf("ingest after erase: %v, %v", res, err)
	}
	if err := st.ScanAll(ctx, sc, func(canon.Event) error { return nil }); !errors.Is(err, store.ErrTenantErased) {
		t.Fatalf("scan after erase: %v", err)
	}
}

func TestEraseTenantSurvivesRestart(t *testing.T) {
	ctx := context.Background()
	st, kek := storetest.New(t)
	if err := st.EnsureTenants(ctx, []string{"t_1", "t_2"}); err != nil {
		t.Fatal(err)
	}
	if err := st.EraseTenant(ctx, "t_1"); err != nil {
		t.Fatal(err)
	}
	st2 := storetest.Reopen(t, st, kek)
	if err := st2.EnsureTenants(ctx, []string{"t_1", "t_2"}); err != nil {
		t.Fatal(err)
	}
	if c := count(t, st2, `SELECT count(*) FROM tenant_keys WHERE tenant_id = 't_1'`); c != 0 {
		t.Fatalf("t_1 key recreated")
	}
	if _, err := st2.Scope(ctx, "t_1"); !errors.Is(err, store.ErrTenantErased) {
		t.Fatalf("scope t_1: %v", err)
	}
	if _, err := st2.Scope(ctx, "t_2"); err != nil {
		t.Fatalf("scope t_2: %v", err)
	}
}
