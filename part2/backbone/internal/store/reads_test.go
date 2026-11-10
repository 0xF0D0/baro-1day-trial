package store_test

import (
	"bufio"
	"context"
	"encoding/json"
	"os"
	"reflect"
	"testing"

	"backbone/internal/canon"
	"backbone/internal/fold"
	"backbone/internal/store"
)

// loadFixture reads the t_0016 events and rewrites them to tenant t_1.
func loadFixture(t *testing.T) []canon.Event {
	t.Helper()
	fh, err := os.Open("../fold/testdata/t_0016.events.jsonl")
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

// flushN flushes up to n days with rank 1 and margin 0 and returns how many it flushed.
func flushN(t *testing.T, st *store.Store, n int) int {
	t.Helper()
	done := 0
	for done < n {
		ok, err := st.FlushDay(context.Background(), "t_1", 0, 1)
		if err != nil {
			t.Fatal(err)
		}
		if !ok {
			break
		}
		done++
	}
	return done
}

func lateEvent(id string, ms int64) canon.Event {
	e := mkEvent(id, ms, "")
	e.Type = "inventory.adjusted"
	e.Data = json.RawMessage(`{"sku":"LATE-SKU","delta":7}`)
	return e
}

func TestStateAcrossTiers(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	events := loadFixture(t)
	ingestAll(t, st, sc, events)
	if n := flushN(t, st, 40); n != 40 {
		t.Fatalf("flushed %d days", n)
	}
	if n := count(t, st, `SELECT count(*) FROM hot_events WHERE tenant_id='t_1'`); n == 0 || n == len(events) {
		t.Fatalf("hot rows %d of %d: not split across tiers", n, len(events))
	}
	got, err := st.State(ctx, sc)
	if err != nil {
		t.Fatal(err)
	}
	want, err := fold.Fold("t_1", events, sc.Keys().CustomerKeyHex)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("state differs from full fold:\n got %+v\nwant %+v", got, want)
	}
}

func TestStateEmptyTenant(t *testing.T) {
	st, sc := newScope(t)
	got, err := st.State(context.Background(), sc)
	if err != nil {
		t.Fatal(err)
	}
	want, _ := fold.Fold("t_1", nil, sc.Keys().CustomerKeyHex)
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %+v want %+v", got, want)
	}
}

func TestStateDirtyUsesFullFold(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	events := loadFixture(t)
	ingestAll(t, st, sc, events)
	flushN(t, st, 30)
	cu := coldUntil(t, st, "t_1")
	late := lateEvent("evt-late-state", cu-msDay/2)
	ingestAll(t, st, sc, []canon.Event{late})
	var dirty bool
	if err := st.Pool().QueryRow(ctx, `SELECT dirty FROM tenant_cold WHERE tenant_id='t_1'`).Scan(&dirty); err != nil || !dirty {
		t.Fatalf("dirty=%v err=%v", dirty, err)
	}
	got, err := st.State(ctx, sc)
	if err != nil {
		t.Fatal(err)
	}
	want, err := fold.Fold("t_1", append(append([]canon.Event(nil), events...), late), sc.Keys().CustomerKeyHex)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("dirty state differs from full fold:\n got %+v\nwant %+v", got, want)
	}
}

func TestStateErased(t *testing.T) {
	st, sc := newScope(t)
	if _, err := st.Pool().Exec(context.Background(), `UPDATE tenants SET status='erased' WHERE tenant_id='t_1'`); err != nil {
		t.Fatal(err)
	}
	if _, err := st.State(context.Background(), sc); err != store.ErrTenantErased {
		t.Fatalf("got %v", err)
	}
}

func TestRangeAcrossTiers(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	events := loadFixture(t)
	ingestAll(t, st, sc, events)
	flushN(t, st, 40)
	cu := coldUntil(t, st, "t_1")
	late := lateEvent("evt-late-range", cu-msDay/2)
	ingestAll(t, st, sc, []canon.Event{late})

	all := append(append([]canon.Event(nil), events...), late)
	canon.Sort(all)
	lo, hi := all[0].OccurredAtMs, all[len(all)-1].OccurredAtMs+1

	var ids []string
	var after *store.Key
	for range 1000 {
		page, err := st.Range(ctx, sc, lo, hi, after, 7)
		if err != nil {
			t.Fatal(err)
		}
		if page == nil {
			t.Fatal("nil page")
		}
		if len(page) == 0 {
			break
		}
		for _, e := range page {
			ids = append(ids, e.EventID)
		}
		last := page[len(page)-1]
		after = &store.Key{OccurredAtMs: last.OccurredAtMs, EventID: last.EventID}
	}
	want := make([]string, len(all))
	for i, e := range all {
		want[i] = e.EventID
	}
	if !reflect.DeepEqual(ids, want) {
		t.Fatalf("paged ids differ: got %d want %d", len(ids), len(want))
	}
}

func TestRangeColdOnlyWindow(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	events := loadFixture(t)
	ingestAll(t, st, sc, events)
	flushN(t, st, 40)
	cu := coldUntil(t, st, "t_1")
	// A window strictly inside flushed days, not aligned to day edges.
	from, to := cu-30*msDay+1000, cu-10*msDay-1000
	var want []string
	sorted := append([]canon.Event(nil), events...)
	canon.Sort(sorted)
	for _, e := range sorted {
		if e.OccurredAtMs >= from && e.OccurredAtMs < to {
			want = append(want, e.EventID)
		}
	}
	if len(want) == 0 {
		t.Fatal("empty window")
	}
	got, err := st.Range(ctx, sc, from, to, nil, 100000)
	if err != nil {
		t.Fatal(err)
	}
	ids := []string{}
	for _, e := range got {
		ids = append(ids, e.EventID)
	}
	if !reflect.DeepEqual(ids, want) {
		t.Fatalf("got %d events want %d", len(ids), len(want))
	}
	// Empty and inverted windows return an empty, non-nil slice.
	for _, w := range [][2]int64{{to, to}, {to, from}} {
		r, err := st.Range(ctx, sc, w[0], w[1], nil, 10)
		if err != nil || r == nil || len(r) != 0 {
			t.Fatalf("window %v: %v %v", w, r, err)
		}
	}
}
