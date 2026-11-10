package store_test

import (
	"context"
	"encoding/json"
	"reflect"
	"sort"
	"testing"

	"backbone/internal/canon"
	"backbone/internal/fold"
	"backbone/internal/store"
)

// rebuildSetup ingests t_0016, flushes every possible day, then ingests three
// late events dated in flushed days. The first is order-sensitive: an
// inventory.adjusted just before a cold order.created that consumes the SKU.
// It returns the scope, every event, the late events and cold_until.
func rebuildSetup(t *testing.T) (*store.Store, store.Scope, []canon.Event, []canon.Event, int64) {
	t.Helper()
	st, sc := newScope(t)
	events := loadFixture(t)
	ingestAll(t, st, sc, events)
	if n := flushN(t, st, 1000); n == 0 {
		t.Fatal("nothing flushed")
	}
	cu := coldUntil(t, st, "t_1")

	var cold []canon.Event
	for _, e := range events {
		if e.OccurredAtMs < cu {
			cold = append(cold, e)
		}
	}
	canon.Sort(cold)

	// Find a cold order whose SKU's stock the adjustment changes the outcome of.
	var adj canon.Event
	found := false
	for _, e := range cold {
		if e.Type != "order.created" {
			continue
		}
		var d struct {
			Lines []struct {
				SKU string `json:"sku"`
			} `json:"lines"`
		}
		if json.Unmarshal(e.Data, &d) != nil || len(d.Lines) == 0 {
			continue
		}
		for _, delta := range []string{"-100000", "100000"} {
			a := canon.Event{EventID: "late-adj", TenantID: "t_1", Type: "inventory.adjusted", OccurredAtMs: e.OccurredAtMs - 1,
				Data: json.RawMessage(`{"sku":"` + d.Lines[0].SKU + `","delta":` + delta + `}`)}
			right, err1 := fold.Fold("t_1", append(append([]canon.Event(nil), events...), a), sc.Keys().CustomerKeyHex)
			// The same adjustment applied after the day's other events.
			moved := a
			moved.OccurredAtMs = (fold.Day(e.OccurredAtMs)+1)*msDay - 1
			wrong, err2 := fold.Fold("t_1", append(append([]canon.Event(nil), events...), moved), sc.Keys().CustomerKeyHex)
			if err1 != nil || err2 != nil {
				t.Fatal(err1, err2)
			}
			if !reflect.DeepEqual(right, wrong) {
				adj, found = a, true
				break
			}
		}
		if found {
			break
		}
	}
	if !found {
		t.Fatal("no order-sensitive late adjustment in the fixture")
	}
	cust := "cus_late"
	late := []canon.Event{
		adj,
		{EventID: "late-msg", TenantID: "t_1", Type: "message.received", OccurredAtMs: cold[0].OccurredAtMs + 1,
			Data: json.RawMessage(`{"channel":"email"}`)},
		{EventID: "late-ord", TenantID: "t_1", Type: "order.created", OccurredAtMs: cu - 5, CustomerID: &cust,
			Data: json.RawMessage(`{"order_id":"o-late","lines":[{"sku":"LATE-SKU","qty":2,"unit_cents":100}]}`)},
	}
	ingestAll(t, st, sc, late)
	if count(t, st, `SELECT count(*) FROM tenant_cold WHERE tenant_id='t_1' AND dirty`) != 1 {
		t.Fatal("tenant should be dirty")
	}
	return st, sc, append(append([]canon.Event(nil), events...), late...), late, cu
}

func assertStateEqualsFold(t *testing.T, st *store.Store, sc store.Scope, all []canon.Event) {
	t.Helper()
	got, err := st.State(context.Background(), sc)
	if err != nil {
		t.Fatal(err)
	}
	want, err := fold.Fold("t_1", all, sc.Keys().CustomerKeyHex)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("state differs from fold:\n got %+v\nwant %+v", got, want)
	}
}

func TestRebuildClearsDirtyAndMatchesFold(t *testing.T) {
	ctx := context.Background()
	st, sc, all, late, cu := rebuildSetup(t)
	oldSnap := snapshotObject(t, st)
	oldManifest := manifestSet(t, st)
	ok, err := st.Rebuild(ctx, "t_1")
	if err != nil || !ok {
		t.Fatalf("rebuild: ok=%v err=%v", ok, err)
	}
	if count(t, st, `SELECT count(*) FROM tenant_cold WHERE tenant_id='t_1' AND dirty`) != 0 {
		t.Fatal("still dirty")
	}
	if n := count(t, st, `SELECT count(*) FROM hot_events WHERE tenant_id='t_1' AND occurred_at_ms < $1`, cu); n != 0 {
		t.Fatalf("%d late rows left in hot", n)
	}
	if got := coldUntil(t, st, "t_1"); got != cu {
		t.Fatalf("cold_until changed: %d -> %d", cu, got)
	}
	assertStateEqualsFold(t, st, sc, all)

	manifest := manifestSet(t, st)
	g := garbageSet(t, st)
	if !g[oldSnap] || snapshotObject(t, st) == oldSnap {
		t.Fatal("snapshot not replaced")
	}
	for _, e := range late {
		day := fold.Day(e.OccurredAtMs)
		evs, err := st.GetBucket(ctx, sc, manifest[day])
		if err != nil {
			t.Fatal(err)
		}
		in := false
		for _, x := range evs {
			if x.EventID == e.EventID {
				in = true
			}
		}
		if !in {
			t.Fatalf("late event %s missing from its bucket", e.EventID)
		}
		if old, had := oldManifest[day]; had && !g[old] {
			t.Fatalf("replaced bucket %s not in garbage", old)
		}
	}
	if n := count(t, st, `SELECT count(*) FROM cold_manifest WHERE tenant_id='t_1' AND (bytes <= 0 OR events <= 0)`); n != 0 {
		t.Fatalf("manifest rows without counts: %d", n)
	}
}

func TestRebuildIndexRowsMatchBuckets(t *testing.T) {
	ctx := context.Background()
	st, sc, _, _, _ := rebuildSetup(t)
	if ok, err := st.Rebuild(ctx, "t_1"); err != nil || !ok {
		t.Fatalf("rebuild: ok=%v err=%v", ok, err)
	}
	var bucketEvents []canon.Event
	for _, obj := range manifestSet(t, st) {
		evs, err := st.GetBucket(ctx, sc, obj)
		if err != nil {
			t.Fatal(err)
		}
		bucketEvents = append(bucketEvents, evs...)
	}
	canon.Sort(bucketEvents)

	type cd struct {
		key string
		day int64
	}
	wantDays := map[cd]bool{}
	type mk struct {
		ms   int64
		id   string
		line int
	}
	wantMoves := map[mk]fold.Move{}
	state := fold.New("t_1", sc.Keys().CustomerKeyHex)
	for _, e := range bucketEvents {
		if e.CustomerID != nil {
			wantDays[cd{string(sc.Keys().CustomerKey(*e.CustomerID)), fold.Day(e.OccurredAtMs)}] = true
		}
		for _, m := range state.ApplyMoves(e) {
			wantMoves[mk{e.OccurredAtMs, e.EventID, m.LineNo}] = m
		}
	}

	rows, err := st.Pool().Query(ctx, `SELECT customer_key, day FROM customer_days WHERE tenant_id='t_1'`)
	if err != nil {
		t.Fatal(err)
	}
	gotDays := map[cd]bool{}
	for rows.Next() {
		var k []byte
		var d int64
		if err := rows.Scan(&k, &d); err != nil {
			t.Fatal(err)
		}
		gotDays[cd{string(k), d}] = true
	}
	rows.Close()
	if !reflect.DeepEqual(gotDays, wantDays) {
		t.Fatalf("customer_days: got %d pairs, want %d", len(gotDays), len(wantDays))
	}

	mrows, err := st.Pool().Query(ctx, `SELECT occurred_at_ms, event_id, line_no, value FROM sku_moves WHERE tenant_id='t_1'`)
	if err != nil {
		t.Fatal(err)
	}
	gotMoves := map[mk]fold.Move{}
	for mrows.Next() {
		var k mk
		var v []byte
		if err := mrows.Scan(&k.ms, &k.id, &k.line, &v); err != nil {
			t.Fatal(err)
		}
		m, err := store.OpenSKUMove(sc, k.id, k.line, v)
		if err != nil {
			t.Fatal(err)
		}
		gotMoves[k] = m
	}
	mrows.Close()
	if !reflect.DeepEqual(gotMoves, wantMoves) {
		keys := []mk{}
		for k := range wantMoves {
			if _, ok := gotMoves[k]; !ok {
				keys = append(keys, k)
			}
		}
		sort.Slice(keys, func(i, j int) bool { return keys[i].ms < keys[j].ms })
		t.Fatalf("sku_moves: got %d rows, want %d (missing %d)", len(gotMoves), len(wantMoves), len(keys))
	}
}

func TestRebuildKeepsLateRowArrivingDuringRebuild(t *testing.T) {
	ctx := context.Background()
	st, sc, all, _, cu := rebuildSetup(t)
	arriving := canon.Event{EventID: "late-during", TenantID: "t_1", Type: "message.received", OccurredAtMs: cu - 9,
		Data: json.RawMessage(`{"channel":"sms"}`)}
	store.SetRebuildAfterRead(func() {
		if res, err := st.Ingest(ctx, sc, arriving); err != nil || res != store.Stored {
			t.Errorf("ingest during rebuild: res=%v err=%v", res, err)
		}
	})
	defer store.SetRebuildAfterRead(nil)
	if ok, err := st.Rebuild(ctx, "t_1"); err != nil || !ok {
		t.Fatalf("rebuild: ok=%v err=%v", ok, err)
	}
	store.SetRebuildAfterRead(nil)
	if n := count(t, st, `SELECT count(*) FROM hot_events WHERE tenant_id='t_1' AND event_id='late-during'`); n != 1 {
		t.Fatalf("arriving row hot count %d, want 1", n)
	}
	if count(t, st, `SELECT count(*) FROM tenant_cold WHERE tenant_id='t_1' AND dirty`) != 1 {
		t.Fatal("tenant should still be dirty")
	}
	all = append(all, arriving)
	assertStateEqualsFold(t, st, sc, all)
	if ok, err := st.Rebuild(ctx, "t_1"); err != nil || !ok {
		t.Fatalf("second rebuild: ok=%v err=%v", ok, err)
	}
	if count(t, st, `SELECT count(*) FROM tenant_cold WHERE tenant_id='t_1' AND dirty`) != 0 {
		t.Fatal("still dirty after second rebuild")
	}
	assertStateEqualsFold(t, st, sc, all)
}

func TestRebuildSkipsCleanTenant(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	events := loadFixture(t)
	ingestAll(t, st, sc, events)
	flushN(t, st, 1000)
	before := count(t, st, `SELECT count(*) FROM garbage WHERE tenant_id='t_1'`)
	ok, err := st.Rebuild(ctx, "t_1")
	if err != nil || ok {
		t.Fatalf("rebuild of clean tenant: ok=%v err=%v", ok, err)
	}
	if after := count(t, st, `SELECT count(*) FROM garbage WHERE tenant_id='t_1'`); after != before {
		t.Fatalf("garbage rows %d -> %d", before, after)
	}
}

func TestEraseAfterRebuild(t *testing.T) {
	ctx := context.Background()
	st, sc, all, _, _ := rebuildSetup(t)
	if ok, err := st.Rebuild(ctx, "t_1"); err != nil || !ok {
		t.Fatalf("rebuild: ok=%v err=%v", ok, err)
	}
	counts := map[string]int{}
	for _, e := range all {
		if e.CustomerID != nil {
			counts[*e.CustomerID]++
		}
	}
	best := ""
	for c, n := range counts {
		if best == "" || n > counts[best] || (n == counts[best] && c < best) {
			best = c
		}
	}
	if err := st.EraseCustomer(ctx, sc, best); err != nil {
		t.Fatal(err)
	}
	assertErasedEqualsFold(t, st, sc, all, best)
}

func TestRedeliveryAfterRebuildIsDuplicate(t *testing.T) {
	ctx := context.Background()
	st, sc, _, late, _ := rebuildSetup(t)
	if ok, err := st.Rebuild(ctx, "t_1"); err != nil || !ok {
		t.Fatalf("rebuild: ok=%v err=%v", ok, err)
	}
	res, err := st.Ingest(ctx, sc, late[0])
	if err != nil || res != store.Duplicate {
		t.Fatalf("redelivery: res=%v err=%v", res, err)
	}
}
