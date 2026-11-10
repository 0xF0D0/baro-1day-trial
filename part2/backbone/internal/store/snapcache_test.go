package store_test

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"backbone/internal/canon"
	"backbone/internal/metrics"
	"backbone/internal/store"

	"github.com/prometheus/client_golang/prometheus/testutil"
)

func cacheCount(result string) float64 {
	return testutil.ToFloat64(metrics.SnapshotCacheTotal.WithLabelValues(result))
}

// stateDeltas runs one State call, checks it against fold.Fold of all, and
// returns the hit and miss counter deltas it caused.
func stateDeltas(t *testing.T, st *store.Store, sc store.Scope, all []canon.Event) (hit, miss float64) {
	t.Helper()
	h, m := cacheCount("hit"), cacheCount("miss")
	assertStateEqualsFold(t, st, sc, all)
	return cacheCount("hit") - h, cacheCount("miss") - m
}

func wantDeltas(t *testing.T, what string, hit, miss, wantHit, wantMiss float64) {
	t.Helper()
	if hit != wantHit || miss != wantMiss {
		t.Fatalf("%s: hit %v miss %v, want hit %v miss %v", what, hit, miss, wantHit, wantMiss)
	}
}

func hotMessage(id string, at int64) canon.Event {
	return canon.Event{EventID: id, TenantID: "t_1", Type: "message.received", OccurredAtMs: at,
		Data: json.RawMessage(`{"channel":"email"}`)}
}

func TestCacheHitOnSecondRead(t *testing.T) {
	st, sc, events, _ := setupT18(t, 40)
	st.SetSnapshotCacheTTL(time.Hour)
	h, m := stateDeltas(t, st, sc, events)
	wantDeltas(t, "first", h, m, 0, 1)
	h, m = stateDeltas(t, st, sc, events)
	wantDeltas(t, "second", h, m, 1, 0)
}

func TestCacheMissAfterPointerChange(t *testing.T) {
	ctx := context.Background()
	st, sc, events, cu := setupT18(t, 20)
	st.SetSnapshotCacheTTL(time.Hour)
	h, m := stateDeltas(t, st, sc, events)
	wantDeltas(t, "prime", h, m, 0, 1)

	// FlushDay moves another day.
	if ok, err := st.FlushDay(ctx, "t_1", 0, 1); err != nil || !ok {
		t.Fatalf("flush: ok=%v err=%v", ok, err)
	}
	h, m = stateDeltas(t, st, sc, events)
	wantDeltas(t, "after flush", h, m, 0, 1)
	h, m = stateDeltas(t, st, sc, events)
	wantDeltas(t, "after flush again", h, m, 1, 0)

	// A late event dirties the tenant; Rebuild writes a new snapshot.
	cu = coldUntil(t, st, "t_1")
	late := hotMessage("late-cache-msg", cu-5)
	ingestAll(t, st, sc, []canon.Event{late})
	events = append(events, late)
	assertStateEqualsFold(t, st, sc, events) // dirty path, no cache lookup
	if ok, err := st.Rebuild(ctx, "t_1"); err != nil || !ok {
		t.Fatalf("rebuild: ok=%v err=%v", ok, err)
	}
	h, m = stateDeltas(t, st, sc, events)
	wantDeltas(t, "after rebuild", h, m, 0, 1)
	h, m = stateDeltas(t, st, sc, events)
	wantDeltas(t, "after rebuild again", h, m, 1, 0)

	// EraseCustomer writes a new snapshot.
	cust := pickCustomer(t, events, cu, "cold")
	if err := st.EraseCustomer(ctx, sc, cust); err != nil {
		t.Fatal(err)
	}
	rest := without(events, cust)
	h, m = stateDeltas(t, st, sc, rest)
	wantDeltas(t, "after erase customer", h, m, 0, 1)
	h, m = stateDeltas(t, st, sc, rest)
	wantDeltas(t, "after erase customer again", h, m, 1, 0)
}

func TestCachedSnapshotNotMutated(t *testing.T) {
	st, sc, events, cu := setupT18(t, 40)
	st.SetSnapshotCacheTTL(time.Hour)
	all := append([]canon.Event(nil), events...)
	assertStateEqualsFold(t, st, sc, all) // miss, caches

	e := hotMessage("hot-after-cache", cu+1000)
	ingestAll(t, st, sc, []canon.Event{e})
	all = append(all, e)
	h, m := stateDeltas(t, st, sc, all) // hit, hot row applied on a copy
	wantDeltas(t, "with hot event", h, m, 1, 0)

	h, m = stateDeltas(t, st, sc, all) // nothing new: must not double-apply
	wantDeltas(t, "again", h, m, 1, 0)
}

func TestCacheExpires(t *testing.T) {
	st, sc, events, _ := setupT18(t, 40)
	st.SetSnapshotCacheTTL(time.Hour)
	now := time.Now()
	st.SetSnapCacheClock(func() time.Time { return now })
	h, m := stateDeltas(t, st, sc, events)
	wantDeltas(t, "first", h, m, 0, 1)
	now = now.Add(59 * time.Minute)
	h, m = stateDeltas(t, st, sc, events)
	wantDeltas(t, "inside ttl", h, m, 1, 0)
	now = now.Add(2 * time.Minute) // 61 minutes after the insert
	h, m = stateDeltas(t, st, sc, events)
	wantDeltas(t, "after ttl", h, m, 0, 1)
}

func TestCacheDisabled(t *testing.T) {
	st, sc, events, _ := setupT18(t, 40)
	// No SetSnapshotCacheTTL call: the default is off.
	for i := 0; i < 2; i++ {
		h, m := stateDeltas(t, st, sc, events)
		wantDeltas(t, "default off", h, m, 0, 1)
	}
	st.SetSnapshotCacheTTL(0)
	h, m := stateDeltas(t, st, sc, events)
	wantDeltas(t, "ttl 0", h, m, 0, 1)
	if st.SnapCacheHas("t_1") {
		t.Fatal("disabled cache kept an entry")
	}
}

func TestEraseTenantDropsCacheEntry(t *testing.T) {
	st, sc, events, _ := setupT18(t, 40)
	st.SetSnapshotCacheTTL(time.Hour)
	assertStateEqualsFold(t, st, sc, events)
	if !st.SnapCacheHas("t_1") {
		t.Fatal("no entry after a cold read")
	}
	if err := st.EraseTenant(context.Background(), "t_1"); err != nil {
		t.Fatal(err)
	}
	if st.SnapCacheHas("t_1") {
		t.Fatal("entry kept after tenant erasure")
	}
}
