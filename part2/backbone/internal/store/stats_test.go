package store_test

import (
	"context"
	"testing"
)

func TestStats(t *testing.T) {
	ctx := context.Background()
	st, sc, events, cu := setupT18(t, 40)
	cust := pickCustomer(t, events, cu, "both")
	if err := st.EraseCustomer(ctx, sc, cust); err != nil {
		t.Fatal(err)
	}
	got, err := st.Stats(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if want := int64(count(t, st, `SELECT count(*) FROM hot_events`)); got.HotEvents != want {
		t.Errorf("HotEvents %d want %d", got.HotEvents, want)
	}
	if want := int64(count(t, st, `SELECT coalesce(sum(events),0) FROM cold_manifest`)); got.ColdEvents != want || want == 0 {
		t.Errorf("ColdEvents %d want %d (non-zero)", got.ColdEvents, want)
	}
	if want := int64(count(t, st, `SELECT coalesce(sum(bytes),0) FROM cold_manifest`)); got.ColdBytes != want {
		t.Errorf("ColdBytes %d want %d", got.ColdBytes, want)
	}
	for name, v := range map[string]int64{"HotBytes": got.HotBytes, "ColdBytes": got.ColdBytes,
		"CustomerDaysBytes": got.CustomerDaysBytes, "SKUMovesBytes": got.SKUMovesBytes} {
		if v <= 0 {
			t.Errorf("%s = %d, want > 0", name, v)
		}
	}
	if got.GarbageObjects < 1 {
		t.Errorf("GarbageObjects %d want >= 1", got.GarbageObjects)
	}
	if got.PendingTombstones != 0 || got.DirtyTenants != 0 {
		t.Errorf("PendingTombstones %d DirtyTenants %d want 0", got.PendingTombstones, got.DirtyTenants)
	}
}
