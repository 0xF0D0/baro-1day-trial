package store_test

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"os"
	"reflect"
	"testing"

	"backbone/internal/canon"
	"backbone/internal/fold"
	"backbone/internal/store"
	"backbone/internal/store/storetest"
)

// loadT18 reads the t_0018 fixture and rewrites it to tenant t_1.
func loadT18(t *testing.T) []canon.Event {
	t.Helper()
	fh, err := os.Open("../fold/testdata/t_0018.events.jsonl")
	if err != nil {
		t.Fatal(err)
	}
	defer fh.Close()
	var events []canon.Event
	rd := bufio.NewScanner(fh)
	rd.Buffer(make([]byte, 1<<20), 1<<20)
	for rd.Scan() {
		var e canon.Event
		if err := json.Unmarshal(rd.Bytes(), &e); err != nil {
			t.Fatal(err)
		}
		e.TenantID = "t_1"
		events = append(events, e)
	}
	if err := rd.Err(); err != nil {
		t.Fatal(err)
	}
	return events
}

func without(events []canon.Event, cust string) []canon.Event {
	var out []canon.Event
	for _, e := range events {
		if e.CustomerID == nil || *e.CustomerID != cust {
			out = append(out, e)
		}
	}
	return out
}

func ofCustomer(events []canon.Event, cust string) []canon.Event {
	var out []canon.Event
	for _, e := range events {
		if e.CustomerID != nil && *e.CustomerID == cust {
			out = append(out, e)
		}
	}
	return out
}

func garbageSet(t *testing.T, st *store.Store) map[string]bool {
	t.Helper()
	rows, err := st.Pool().Query(context.Background(), `SELECT object FROM garbage WHERE tenant_id = 't_1'`)
	if err != nil {
		t.Fatal(err)
	}
	defer rows.Close()
	out := map[string]bool{}
	for rows.Next() {
		var o string
		if err := rows.Scan(&o); err != nil {
			t.Fatal(err)
		}
		out[o] = true
	}
	return out
}

func manifestSet(t *testing.T, st *store.Store) map[int64]string {
	t.Helper()
	rows, err := st.Pool().Query(context.Background(), `SELECT day, object FROM cold_manifest WHERE tenant_id = 't_1'`)
	if err != nil {
		t.Fatal(err)
	}
	defer rows.Close()
	out := map[int64]string{}
	for rows.Next() {
		var d int64
		var o string
		if err := rows.Scan(&d, &o); err != nil {
			t.Fatal(err)
		}
		out[d] = o
	}
	return out
}

func snapshotObject(t *testing.T, st *store.Store) string {
	t.Helper()
	var s *string
	if err := st.Pool().QueryRow(context.Background(),
		`SELECT snapshot_object FROM tenant_cold WHERE tenant_id = 't_1'`).Scan(&s); err != nil || s == nil {
		t.Fatalf("snapshot object: %v", err)
	}
	return *s
}

// pickCustomer returns the customer with the most events among those that have
// events on both sides of coldUntil and share a SKU with another customer
// (when needShared) and, when needBoth is false, whose events are all cold.
func pickCustomer(t *testing.T, events []canon.Event, coldUntil int64, mode string) string {
	t.Helper()
	counts := map[string]int{}
	for _, e := range events {
		if e.CustomerID != nil {
			counts[*e.CustomerID]++
		}
	}
	best, bestN := "", 0
	for c, n := range counts {
		mine := ofCustomer(events, c)
		cold, hot := 0, 0
		for _, e := range mine {
			if e.OccurredAtMs < coldUntil {
				cold++
			} else {
				hot++
			}
		}
		switch mode {
		case "both":
			if cold == 0 || hot == 0 {
				continue
			}
			shared := false
			others := map[string]bool{}
			for _, s := range fold.AffectedSKUs(without(events, c)) {
				others[s] = true
			}
			for _, s := range fold.AffectedSKUs(mine) {
				if others[s] {
					shared = true
				}
			}
			if !shared {
				continue
			}
		case "cold":
			if cold == 0 || hot != 0 {
				continue
			}
		}
		if n > bestN || (n == bestN && c < best) {
			best, bestN = c, n
		}
	}
	if best == "" {
		t.Fatalf("no customer for mode %s", mode)
	}
	return best
}

func setupT18(t *testing.T, flushDays int) (*store.Store, store.Scope, []canon.Event, int64) {
	t.Helper()
	st, sc := newScope(t)
	events := loadT18(t)
	ingestAll(t, st, sc, events)
	if got := flushN(t, st, flushDays); got != flushDays {
		t.Fatalf("flushed %d days, want %d", got, flushDays)
	}
	return st, sc, events, coldUntil(t, st, "t_1")
}

func assertErasedEqualsFold(t *testing.T, st *store.Store, sc store.Scope, events []canon.Event, cust string) {
	t.Helper()
	ctx := context.Background()
	got, err := st.State(ctx, sc)
	if err != nil {
		t.Fatal(err)
	}
	want, err := fold.Fold("t_1", without(events, cust), sc.Keys().CustomerKeyHex)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("state after erase differs from fold:\n got %+v\nwant %+v", got, want)
	}
	key := sc.Keys().CustomerKey(cust)
	if n := count(t, st, `SELECT count(*) FROM hot_events WHERE tenant_id='t_1' AND customer_key=$1`, key); n != 0 {
		t.Fatalf("hot rows left: %d", n)
	}
	if n := count(t, st, `SELECT count(*) FROM customer_days WHERE tenant_id='t_1' AND customer_key=$1`, key); n != 0 {
		t.Fatalf("customer_days left: %d", n)
	}
	var ids []string
	for _, e := range ofCustomer(events, cust) {
		ids = append(ids, e.EventID)
	}
	if n := count(t, st, `SELECT count(*) FROM sku_moves WHERE tenant_id='t_1' AND event_id = ANY($1)`, ids); n != 0 {
		t.Fatalf("sku_moves left: %d", n)
	}
	// Range over everything must not return the customer's events.
	all, err := st.Range(ctx, sc, -1<<62, 1<<62, nil, 100000)
	if err != nil {
		t.Fatal(err)
	}
	if len(all) != len(without(events, cust)) {
		t.Fatalf("range returned %d events, want %d", len(all), len(without(events, cust)))
	}
	for _, e := range all {
		if e.CustomerID != nil && *e.CustomerID == cust {
			t.Fatal("range returned an erased customer's event")
		}
	}
}

func TestEraseCustomerAcrossTiers(t *testing.T) {
	ctx := context.Background()
	st, sc, events, cu := setupT18(t, 40)
	cust := pickCustomer(t, events, cu, "both")
	oldSnap := snapshotObject(t, st)
	oldManifest := manifestSet(t, st)
	touched := map[string]bool{}
	for _, e := range ofCustomer(events, cust) {
		if e.OccurredAtMs < cu {
			touched[oldManifest[fold.Day(e.OccurredAtMs)]] = true
		}
	}
	if len(touched) == 0 {
		t.Fatal("test setup: no cold buckets touched")
	}
	if err := st.EraseCustomer(ctx, sc, cust); err != nil {
		t.Fatal(err)
	}
	assertErasedEqualsFold(t, st, sc, events, cust)
	g := garbageSet(t, st)
	if !g[oldSnap] {
		t.Fatal("old snapshot not in garbage")
	}
	for o := range touched {
		if !g[o] {
			t.Fatalf("replaced bucket %s not in garbage", o)
		}
	}
	if snapshotObject(t, st) == oldSnap {
		t.Fatal("snapshot pointer unchanged")
	}
	// Idempotent.
	if err := st.EraseCustomer(ctx, sc, cust); err != nil {
		t.Fatal(err)
	}
	assertErasedEqualsFold(t, st, sc, events, cust)
}

func TestEraseCustomerOnlyInCold(t *testing.T) {
	ctx := context.Background()
	st, sc, events, cu := setupT18(t, 40)
	cust := pickCustomer(t, events, cu, "cold")
	if err := st.EraseCustomer(ctx, sc, cust); err != nil {
		t.Fatal(err)
	}
	assertErasedEqualsFold(t, st, sc, events, cust)
}

func TestEraseCustomerEmptiesADay(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	d := int64(100)
	events := []canon.Event{
		orderEvent("e-a1", d*msDay+2, "c1", "S1", 3),
		orderEvent("e-a2", d*msDay+3, "c1", "S2", 1),
		orderEvent("e-b1", (d+1)*msDay+2, "c2", "S1", 2),
		mkEvent("e-z", (d+6)*msDay+7, "c9"),
	}
	ingestAll(t, st, sc, events)
	if n := flushN(t, st, 2); n != 2 {
		t.Fatalf("flushed %d", n)
	}
	m := manifestSet(t, st)
	if len(m) != 2 {
		t.Fatalf("manifest %v", m)
	}
	dayObj := m[d]
	if err := st.EraseCustomer(ctx, sc, "c1"); err != nil {
		t.Fatal(err)
	}
	if n := count(t, st, `SELECT count(*) FROM cold_manifest WHERE tenant_id='t_1' AND day=$1`, d); n != 0 {
		t.Fatalf("manifest row for emptied day remains")
	}
	if !garbageSet(t, st)[dayObj] {
		t.Fatal("emptied bucket not in garbage")
	}
	assertErasedEqualsFold(t, st, sc, events, "c1")
}

func TestEraseTenantWithColdData(t *testing.T) {
	ctx := context.Background()
	st, kek := storetest.New(t)
	if err := st.EnsureTenants(ctx, []string{"t_1"}); err != nil {
		t.Fatal(err)
	}
	sc, err := st.Scope(ctx, "t_1")
	if err != nil {
		t.Fatal(err)
	}
	ingestAll(t, st, sc, loadT18(t))
	if n := flushN(t, st, 20); n != 20 {
		t.Fatalf("flushed %d", n)
	}
	if err := st.EraseTenant(ctx, "t_1"); err != nil {
		t.Fatal(err)
	}
	if _, err := st.State(ctx, sc); !errors.Is(err, store.ErrTenantErased) {
		t.Fatalf("state: %v", err)
	}
	for _, tbl := range []string{"tenant_cold", "cold_manifest", "customer_days", "sku_moves", "hot_events", "tenant_keys"} {
		if n := count(t, st, `SELECT count(*) FROM `+tbl+` WHERE tenant_id='t_1'`); n != 0 {
			t.Fatalf("%s rows after erase: %d", tbl, n)
		}
	}
	st2 := storetest.Reopen(t, st, kek)
	if err := st2.EnsureTenants(ctx, []string{"t_1"}); err != nil {
		t.Fatal(err)
	}
	for _, tbl := range []string{"tenant_cold", "tenant_keys"} {
		if n := count(t, st2, `SELECT count(*) FROM `+tbl+` WHERE tenant_id='t_1'`); n != 0 {
			t.Fatalf("%s recreated after reopen: %d", tbl, n)
		}
	}
}
