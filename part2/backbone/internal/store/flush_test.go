package store_test

import (
	"bufio"
	"context"
	"encoding/json"
	"os"
	"reflect"
	"strconv"
	"testing"
	"time"

	"backbone/internal/canon"
	"backbone/internal/fold"
	"backbone/internal/store"
	"backbone/internal/store/storetest"
)

const margin96 = 96 * time.Hour

func ingestAll(t *testing.T, st *store.Store, sc store.Scope, evs []canon.Event) {
	t.Helper()
	for _, e := range evs {
		if res, err := st.Ingest(context.Background(), sc, e); err != nil || res != store.Stored {
			t.Fatalf("ingest %s: res=%v err=%v", e.EventID, res, err)
		}
	}
}

func coldUntil(t *testing.T, st *store.Store, tenant string) int64 {
	t.Helper()
	var v int64
	if err := st.Pool().QueryRow(context.Background(),
		`SELECT cold_until FROM tenant_cold WHERE tenant_id = $1`, tenant).Scan(&v); err != nil {
		t.Fatal(err)
	}
	return v
}

func TestFlushMovesOneDay(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	d := int64(100)
	ingestAll(t, st, sc, []canon.Event{
		mkEvent("e-d", d*msDay+7, "c1"),
		mkEvent("e-d1", (d+1)*msDay+7, "c2"),
		mkEvent("e-d6", (d+6)*msDay+7, "c3"),
	})
	ok, err := st.FlushDay(ctx, "t_1", margin96, 1)
	if err != nil || !ok {
		t.Fatalf("first flush: ok=%v err=%v", ok, err)
	}
	if n := count(t, st, `SELECT count(*) FROM cold_manifest WHERE tenant_id='t_1' AND day=$1`, d); n != 1 {
		t.Fatalf("manifest rows for day D: %d", n)
	}
	if n := count(t, st, `SELECT count(*) FROM cold_manifest WHERE tenant_id='t_1' AND day=$1 AND bytes > 0`, d); n != 1 {
		t.Fatalf("manifest bytes not recorded")
	}
	if n := count(t, st, `SELECT count(*) FROM hot_events WHERE tenant_id='t_1'`); n != 2 {
		t.Fatalf("hot rows: %d", n)
	}
	if got := coldUntil(t, st, "t_1"); got != (d+1)*msDay {
		t.Fatalf("cold_until %d", got)
	}
	if ok, err = st.FlushDay(ctx, "t_1", margin96, 1); err != nil || !ok {
		t.Fatalf("second flush: ok=%v err=%v", ok, err)
	}
	if got := coldUntil(t, st, "t_1"); got != (d+2)*msDay {
		t.Fatalf("cold_until %d", got)
	}
	if ok, err = st.FlushDay(ctx, "t_1", margin96, 1); err != nil || ok {
		t.Fatalf("third flush: ok=%v err=%v", ok, err)
	}
	if n := count(t, st, `SELECT count(*) FROM garbage WHERE tenant_id='t_1'`); n != 1 {
		t.Fatalf("garbage rows: %d", n)
	}
}

func TestFlushedStateEqualsFold(t *testing.T) {
	ctx := context.Background()
	st, _ := storetest.New(t)
	const tenant = "t_0018"
	if err := st.EnsureTenants(ctx, []string{tenant}); err != nil {
		t.Fatal(err)
	}
	sc, err := st.Scope(ctx, tenant)
	if err != nil {
		t.Fatal(err)
	}
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
		events = append(events, e)
	}
	if err := rd.Err(); err != nil {
		t.Fatal(err)
	}
	ingestAll(t, st, sc, events)

	flushed := 0
	for {
		ok, err := st.FlushDay(ctx, tenant, 0, 1)
		if err != nil {
			t.Fatal(err)
		}
		if !ok {
			break
		}
		flushed++
	}
	if flushed == 0 {
		t.Fatal("nothing flushed")
	}

	var obj *string
	if err := st.Pool().QueryRow(ctx, `SELECT snapshot_object FROM tenant_cold WHERE tenant_id=$1`, tenant).Scan(&obj); err != nil {
		t.Fatal(err)
	}
	if obj == nil {
		t.Fatal("no snapshot")
	}
	snap, err := st.GetSnapshot(ctx, sc, *obj)
	if err != nil {
		t.Fatal(err)
	}
	state := fold.Restore(tenant, sc.Keys().CustomerKeyHex, snap)
	if err := st.ScanAll(ctx, sc, func(e canon.Event) error { return state.Apply(e) }); err != nil {
		t.Fatal(err)
	}
	want, err := fold.Fold(tenant, events, sc.Keys().CustomerKeyHex)
	if err != nil {
		t.Fatal(err)
	}
	if got := state.Result(); !reflect.DeepEqual(got, want) {
		t.Fatalf("restored+hot result differs from full fold:\n got %+v\nwant %+v", got, want)
	}
}

func orderEvent(id string, ms int64, cust, sku string, qty int) canon.Event {
	e := mkEvent(id, ms, cust)
	e.Data = json.RawMessage(`{"order_id":"o-` + id + `","lines":[{"sku":"` + sku + `","qty":` + strconv.Itoa(qty) + `,"unit_cents":100}]}`)
	return e
}

func TestFlushWritesIndexRows(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	d := int64(100)
	adj := mkEvent("e-adj", d*msDay+1, "")
	adj.Type = "inventory.adjusted"
	adj.Data = json.RawMessage(`{"sku":"S1","delta":10}`)
	dayEvents := []canon.Event{
		adj,
		orderEvent("e-o1", d*msDay+2, "c1", "S1", 3),
		orderEvent("e-o2", d*msDay+3, "c1", "S2", 4),
		orderEvent("e-o3", d*msDay+4, "c2", "S1", 2),
	}
	ingestAll(t, st, sc, dayEvents)
	ingestAll(t, st, sc, []canon.Event{mkEvent("e-late", (d+6)*msDay, "c9")})
	if ok, err := st.FlushDay(ctx, "t_1", margin96, 1); err != nil || !ok {
		t.Fatalf("flush: ok=%v err=%v", ok, err)
	}
	// One row per (customer, day): c1 and c2, not c9, not twice.
	if n := count(t, st, `SELECT count(*) FROM customer_days WHERE tenant_id='t_1'`); n != 2 {
		t.Fatalf("customer_days rows: %d", n)
	}
	want := map[string]fold.Move{}
	x := fold.New("t_1", sc.Keys().CustomerKeyHex)
	for _, e := range dayEvents {
		for _, m := range x.ApplyMoves(e) {
			want[e.EventID+"/"+strconv.Itoa(m.LineNo)] = m
		}
	}
	if len(want) != 4 {
		t.Fatalf("test setup: %d moves", len(want))
	}
	rows, err := st.Pool().Query(ctx, `SELECT sku_key, occurred_at_ms, event_id, line_no, value FROM sku_moves WHERE tenant_id='t_1'`)
	if err != nil {
		t.Fatal(err)
	}
	defer rows.Close()
	got := 0
	for rows.Next() {
		var key, val []byte
		var ms int64
		var id string
		var line int
		if err := rows.Scan(&key, &ms, &id, &line, &val); err != nil {
			t.Fatal(err)
		}
		m, err := store.OpenSKUMove(sc, id, line, val)
		if err != nil {
			t.Fatal(err)
		}
		w, ok := want[id+"/"+strconv.Itoa(line)]
		if !ok || !reflect.DeepEqual(m, w) {
			t.Fatalf("move %s/%d: got %+v want %+v", id, line, m, w)
		}
		if !reflect.DeepEqual(key, sc.Keys().SKUKey(m.SKU)) {
			t.Fatalf("sku_key mismatch for %s", id)
		}
		got++
	}
	if got != len(want) {
		t.Fatalf("sku_moves rows %d want %d", got, len(want))
	}
}

func TestFlushKeepsRowInsertedDuringFlush(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	d := int64(100)
	ingestAll(t, st, sc, []canon.Event{
		mkEvent("e-d", d*msDay+7, "c1"),
		mkEvent("e-d6", (d+6)*msDay+7, "c3"),
	})
	store.SetFlushAfterRead(func() {
		if res, err := st.Ingest(ctx, sc, mkEvent("e-during", d*msDay+9, "c1")); err != nil || res != store.Stored {
			t.Errorf("ingest during flush: res=%v err=%v", res, err)
		}
	})
	defer store.SetFlushAfterRead(nil)
	ok, err := st.FlushDay(ctx, "t_1", margin96, 1)
	if err != nil || !ok {
		t.Fatalf("flush: ok=%v err=%v", ok, err)
	}
	if n := count(t, st, `SELECT count(*) FROM hot_events WHERE tenant_id='t_1' AND event_id='e-during'`); n != 1 {
		t.Fatalf("row inserted during flush is gone")
	}
	var dirty bool
	if err := st.Pool().QueryRow(ctx, `SELECT dirty FROM tenant_cold WHERE tenant_id='t_1'`).Scan(&dirty); err != nil || !dirty {
		t.Fatalf("dirty=%v err=%v", dirty, err)
	}
}

func TestFlushSkipsDirtyTenant(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	d := int64(100)
	ingestAll(t, st, sc, []canon.Event{mkEvent("e-d", d*msDay+7, "c1"), mkEvent("e-d6", (d+6)*msDay+7, "c3")})
	if _, err := st.Pool().Exec(ctx, `UPDATE tenant_cold SET dirty = true WHERE tenant_id='t_1'`); err != nil {
		t.Fatal(err)
	}
	ok, err := st.FlushDay(ctx, "t_1", margin96, 1)
	if err != nil || ok {
		t.Fatalf("ok=%v err=%v", ok, err)
	}
	if n := count(t, st, `SELECT count(*) FROM cold_manifest`); n != 0 {
		t.Fatalf("manifest rows: %d", n)
	}
	if n := count(t, st, `SELECT count(*) FROM hot_events`); n != 2 {
		t.Fatalf("hot rows: %d", n)
	}
}

func TestFlushStopsWhenTenantErasedDuringFlush(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	d := int64(100)
	ingestAll(t, st, sc, []canon.Event{
		orderEvent("e-o1", d*msDay+2, "c1", "S1", 3),
		mkEvent("e-d6", (d+6)*msDay+7, "c3"),
	})
	store.SetFlushAfterRead(func() {
		// EraseTenant would wait for the flush's cold-writer lock, so mark the
		// tenant erased directly; FlushDay must notice at its commit re-check.
		if _, err := st.Pool().Exec(ctx, `DELETE FROM tenant_keys WHERE tenant_id = 't_1'`); err != nil {
			t.Errorf("delete key: %v", err)
		}
		if _, err := st.Pool().Exec(ctx, `UPDATE tenants SET status = 'erased' WHERE tenant_id = 't_1'`); err != nil {
			t.Errorf("mark erased: %v", err)
		}
	})
	defer store.SetFlushAfterRead(nil)
	ok, err := st.FlushDay(ctx, "t_1", margin96, 1)
	if err != nil || ok {
		t.Fatalf("flush: ok=%v err=%v", ok, err)
	}
	for _, tbl := range []string{"cold_manifest", "sku_moves", "customer_days"} {
		if n := count(t, st, `SELECT count(*) FROM `+tbl+` WHERE tenant_id='t_1'`); n != 0 {
			t.Fatalf("%s rows after erased flush: %d", tbl, n)
		}
	}
}
