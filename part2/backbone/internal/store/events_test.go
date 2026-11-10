package store_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"math/rand"
	"reflect"
	"testing"

	"backbone/internal/canon"
	"backbone/internal/store"
	"backbone/internal/store/storetest"
)

func newScope(t *testing.T) (*store.Store, store.Scope) {
	t.Helper()
	st, _ := storetest.New(t)
	ctx := context.Background()
	if err := st.EnsureTenants(ctx, []string{"t_1"}); err != nil {
		t.Fatal(err)
	}
	sc, err := st.Scope(ctx, "t_1")
	if err != nil {
		t.Fatal(err)
	}
	return st, sc
}

func mkEvent(id string, ms int64, cust string) canon.Event {
	ev := canon.Event{
		EventID: id, TenantID: "t_1", Type: "order.created", OccurredAtMs: ms,
		Data: json.RawMessage(`{"email":"x@example.com","n":1}`),
	}
	if cust != "" {
		ev.CustomerID = &cust
	}
	return ev
}

func scanAll(t *testing.T, st *store.Store, sc store.Scope) []canon.Event {
	t.Helper()
	var out []canon.Event
	err := st.ScanAll(context.Background(), sc, func(e canon.Event) error {
		out = append(out, e)
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	return out
}

func eventJSON(t *testing.T, e canon.Event) any {
	t.Helper()
	b, err := json.Marshal(e)
	if err != nil {
		t.Fatal(err)
	}
	var v any
	if err := json.Unmarshal(b, &v); err != nil {
		t.Fatal(err)
	}
	return v
}

func TestIngestStoresAndDedupes(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	ev := mkEvent("evt_1", 100, "cus_1")
	for i, want := range []store.IngestResult{store.Stored, store.Duplicate} {
		got, err := st.Ingest(ctx, sc, ev)
		if err != nil || got != want {
			t.Fatalf("ingest %d: got %v, %v want %v", i, got, err, want)
		}
	}
	got := scanAll(t, st, sc)
	if len(got) != 1 || !reflect.DeepEqual(eventJSON(t, got[0]), eventJSON(t, ev)) {
		t.Fatalf("scan mismatch: %+v", got)
	}
}

func TestIngestEncrypts(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	if _, err := st.Ingest(ctx, sc, mkEvent("evt_1", 100, "cus_1")); err != nil {
		t.Fatal(err)
	}
	var payload, ck []byte
	err := st.Pool().QueryRow(ctx, `SELECT payload, customer_key FROM hot_events`).Scan(&payload, &ck)
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Contains(payload, []byte("cus_1")) || bytes.Contains(payload, []byte("x@example.com")) {
		t.Fatal("payload contains plaintext")
	}
	if !bytes.Equal(ck, sc.Keys().CustomerKey("cus_1")) {
		t.Fatal("customer_key mismatch")
	}
}

func TestIngestDropsErasedCustomer(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	_, err := st.Pool().Exec(ctx,
		`INSERT INTO tombstones (tenant_id, customer_key, status) VALUES ('t_1', $1, 'done')`,
		sc.Keys().CustomerKey("cus_1"))
	if err != nil {
		t.Fatal(err)
	}
	got, err := st.Ingest(ctx, sc, mkEvent("evt_1", 100, "cus_1"))
	if err != nil || got != store.CustomerErased {
		t.Fatalf("got %v, %v", got, err)
	}
	if n := len(scanAll(t, st, sc)); n != 0 {
		t.Fatalf("scan returned %d events", n)
	}
	// Other customers and customer-less events are unaffected.
	for _, ev := range []canon.Event{mkEvent("evt_2", 1, "cus_2"), mkEvent("evt_3", 2, "")} {
		if got, err := st.Ingest(ctx, sc, ev); err != nil || got != store.Stored {
			t.Fatalf("got %v, %v", got, err)
		}
	}
}

func TestIngestErasedTenant(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	if _, err := st.Pool().Exec(ctx, `UPDATE tenants SET status='erased'`); err != nil {
		t.Fatal(err)
	}
	got, err := st.Ingest(ctx, sc, mkEvent("evt_1", 100, "cus_1"))
	if err != nil || got != store.TenantErased {
		t.Fatalf("got %v, %v", got, err)
	}
	err = st.ScanAll(ctx, sc, func(canon.Event) error { return nil })
	if !errors.Is(err, store.ErrTenantErased) {
		t.Fatalf("scan: want ErrTenantErased, got %v", err)
	}
	_, err = st.Range(ctx, sc, 0, 1000, nil, 10)
	if !errors.Is(err, store.ErrTenantErased) {
		t.Fatalf("range: want ErrTenantErased, got %v", err)
	}
}

func shuffled(evs []canon.Event) []canon.Event {
	out := append([]canon.Event(nil), evs...)
	rand.Shuffle(len(out), func(i, j int) { out[i], out[j] = out[j], out[i] })
	return out
}

func TestScanAllOrder(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	evs := []canon.Event{
		mkEvent("evt_a_1", 5, ""), mkEvent("evt_a-1", 5, ""),
		mkEvent("0f0e8a6c-0000-4000-8000-000000000000", 5, ""), mkEvent("evt_z", 4, "cus_1"),
	}
	for _, ev := range shuffled(evs) {
		if _, err := st.Ingest(ctx, sc, ev); err != nil {
			t.Fatal(err)
		}
	}
	want := append([]canon.Event(nil), evs...)
	canon.Sort(want)
	got := scanAll(t, st, sc)
	if len(got) != len(want) {
		t.Fatalf("got %d events", len(got))
	}
	for i := range want {
		if got[i].EventID != want[i].EventID {
			t.Fatalf("pos %d: got %s want %s", i, got[i].EventID, want[i].EventID)
		}
	}
}

func TestRangePagingTies(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	var in, expect []canon.Event
	for i := 0; i < 25; i++ {
		id := fmt.Sprintf("evt_%02d", i)
		if i%3 == 0 {
			id = fmt.Sprintf("%08x-0000-4000-8000-000000000000", i*7919)
		}
		in = append(in, mkEvent(id, 1000, ""))
	}
	for i := 0; i < 5; i++ {
		in = append(in, mkEvent(fmt.Sprintf("evt_lo%d", i), 999, ""), mkEvent(fmt.Sprintf("evt_hi%d", i), 1001, ""))
	}
	for _, ev := range in {
		if ev.OccurredAtMs < 1001 {
			expect = append(expect, ev)
		}
	}
	canon.Sort(expect)
	for _, ev := range shuffled(in) {
		if _, err := st.Ingest(ctx, sc, ev); err != nil {
			t.Fatal(err)
		}
	}
	var got []canon.Event
	var after *store.Key
	for {
		page, err := st.Range(ctx, sc, 999, 1001, after, 1)
		if err != nil {
			t.Fatal(err)
		}
		if len(page) == 0 {
			break
		}
		last := page[len(page)-1]
		got = append(got, page...)
		after = &store.Key{OccurredAtMs: last.OccurredAtMs, EventID: last.EventID}
	}
	if len(got) != len(expect) {
		t.Fatalf("got %d events, want %d", len(got), len(expect))
	}
	for i := range expect {
		if got[i].EventID != expect[i].EventID {
			t.Fatalf("pos %d: got %s want %s", i, got[i].EventID, expect[i].EventID)
		}
	}
}
