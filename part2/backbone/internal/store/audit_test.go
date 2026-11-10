package store_test

import (
	"context"
	"slices"
	"testing"

	"backbone/internal/canon"
	"backbone/internal/cold"
	"backbone/internal/fold"
	"backbone/internal/store"
)

// flushAllT18 ingests t_0018, flushes every day and sweeps with no grace.
func flushAllT18(t *testing.T) (*store.Store, store.Scope, []canon.Event) {
	t.Helper()
	ctx := context.Background()
	st, sc := newScope(t)
	events := loadT18(t)
	ingestAll(t, st, sc, events)
	for {
		ok, err := st.FlushDay(ctx, "t_1", 0, 1)
		if err != nil {
			t.Fatal(err)
		}
		if !ok {
			break
		}
	}
	if _, err := st.SweepTenant(ctx, "t_1", 0); err != nil {
		t.Fatal(err)
	}
	return st, sc, events
}

func audit(t *testing.T, st *store.Store) store.Audit {
	t.Helper()
	a, err := st.Audit(context.Background(), "t_1")
	if err != nil {
		t.Fatal(err)
	}
	return a
}

func TestAuditCleanAfterFlush(t *testing.T) {
	st, _, events := flushAllT18(t)
	a := audit(t, st)
	var got []string
	got = append(got, a.HotIDs...)
	got = append(got, a.ColdIDs...)
	var want []string
	for _, e := range events {
		want = append(want, e.EventID)
	}
	slices.Sort(got)
	slices.Sort(want)
	if !slices.Equal(got, want) {
		t.Fatalf("ids: got %d, want %d (or repeats)", len(got), len(want))
	}
	if len(a.BadPointers) != 0 || len(a.Unreferenced) != 0 || a.GarbageRows != 0 || a.Dirty || a.Erased || !a.StateMatches {
		t.Fatalf("not clean: %+v", a)
	}
	if !a.IndexMatches || len(a.TierViolations) != 0 {
		t.Fatalf("index or tier: %+v", a)
	}
}

func TestAuditFindsMissingIndexRow(t *testing.T) {
	ctx := context.Background()
	st, _, _ := flushAllT18(t)
	tag, err := st.Pool().Exec(ctx, `DELETE FROM customer_days WHERE ctid IN
		(SELECT ctid FROM customer_days WHERE tenant_id = 't_1' LIMIT 1)`)
	if err != nil || tag.RowsAffected() != 1 {
		t.Fatalf("delete customer_days: %v %v", tag, err)
	}
	if a := audit(t, st); a.IndexMatches || len(a.BadPointers) != 0 {
		t.Fatalf("want index mismatch: %+v", a)
	}
}

func TestAuditFindsMissingSKUMove(t *testing.T) {
	ctx := context.Background()
	st, _, _ := flushAllT18(t)
	tag, err := st.Pool().Exec(ctx, `DELETE FROM sku_moves WHERE ctid IN
		(SELECT ctid FROM sku_moves WHERE tenant_id = 't_1' LIMIT 1)`)
	if err != nil || tag.RowsAffected() != 1 {
		t.Fatalf("delete sku_moves: %v %v", tag, err)
	}
	if a := audit(t, st); a.IndexMatches {
		t.Fatalf("want index mismatch: %+v", a)
	}
}

func TestAuditFindsColdUntilMovedBack(t *testing.T) {
	ctx := context.Background()
	st, _, _ := flushAllT18(t)
	// Hot rows sit above cold_until after a full flush, so move cold_until
	// below the oldest manifest day and below nothing hot: the manifest day and
	// the snapshot both disagree, and any hot row below it is a violation.
	cu := coldUntil(t, st, "t_1")
	var hotMin int64
	if err := st.Pool().QueryRow(ctx, `SELECT coalesce(min(occurred_at_ms), 0) FROM hot_events WHERE tenant_id = 't_1'`).Scan(&hotMin); err != nil {
		t.Fatal(err)
	}
	if hotMin == 0 {
		t.Skip("fixture leaves no hot rows")
	}
	if err := st.SetColdUntil(ctx, "t_1", hotMin+1); err != nil {
		t.Fatal(err)
	}
	a := audit(t, st)
	if len(a.TierViolations) == 0 {
		t.Fatalf("want a tier violation (cold_until %d -> %d): %+v", cu, hotMin+1, a)
	}
}

func TestAuditFindsUnreferencedObject(t *testing.T) {
	ctx := context.Background()
	st, sc, _ := flushAllT18(t)
	name := cold.ObjectName("t_1", "bucket", 5)
	if err := st.Objects().Put(ctx, name, []byte("x")); err != nil {
		t.Fatal(err)
	}
	_ = sc
	a := audit(t, st)
	if !slices.Equal(a.Unreferenced, []string{name}) {
		t.Fatalf("unreferenced: %v", a.Unreferenced)
	}
}

func TestAuditFindsBadPointer(t *testing.T) {
	ctx := context.Background()
	st, _, _ := flushAllT18(t)
	var name string
	for _, o := range manifestSet(t, st) {
		name = o
		break
	}
	if err := st.Objects().Delete(ctx, name); err != nil {
		t.Fatal(err)
	}
	a := audit(t, st)
	if !slices.Equal(a.BadPointers, []string{name}) || a.StateMatches {
		t.Fatalf("bad pointers: %+v", a)
	}
}

func TestAuditFindsDuplicate(t *testing.T) {
	ctx := context.Background()
	st, sc, _ := flushAllT18(t)
	var day int64
	var name string
	for d, o := range manifestSet(t, st) {
		day, name = d, o
		break
	}
	b, err := st.GetBucket(ctx, sc, name)
	if err != nil || len(b) == 0 {
		t.Fatalf("bucket: %v", err)
	}
	if err := st.AddManifestBucket(ctx, sc, day-100000, b[:1]); err != nil {
		t.Fatal(err)
	}
	a := audit(t, st)
	n := 0
	for _, id := range a.ColdIDs {
		if id == b[0].EventID {
			n++
		}
	}
	if n != 2 {
		t.Fatalf("event appears %d times in ColdIDs, want 2", n)
	}
}

func TestAuditFindsStateMismatch(t *testing.T) {
	ctx := context.Background()
	st, sc, _ := flushAllT18(t)
	name, err := st.PutSnapshot(ctx, sc, coldUntil(t, st, "t_1"), fold.New("t_1", sc.Keys().CustomerKeyHex).Snapshot())
	if err != nil {
		t.Fatal(err)
	}
	if _, err := st.Pool().Exec(ctx, `UPDATE tenant_cold SET snapshot_object = $1 WHERE tenant_id = 't_1'`, name); err != nil {
		t.Fatal(err)
	}
	a := audit(t, st)
	if len(a.BadPointers) != 0 || a.StateMatches {
		t.Fatalf("want state mismatch: %+v", a)
	}
}

func TestAuditErasedTenant(t *testing.T) {
	ctx := context.Background()
	st, _, _ := flushAllT18(t)
	before, err := st.Objects().List(ctx, "t_1/")
	if err != nil || len(before) == 0 {
		t.Fatalf("objects: %v %v", before, err)
	}
	if err := st.EraseTenant(ctx, "t_1"); err != nil {
		t.Fatal(err)
	}
	a := audit(t, st)
	slices.Sort(a.Unreferenced)
	slices.Sort(before)
	if !a.Erased || !slices.Equal(a.Unreferenced, before) || !a.StateMatches || !a.IndexMatches || len(a.TierViolations) != 0 {
		t.Fatalf("erased audit: %+v", a)
	}
	if _, err := st.SweepTenant(ctx, "t_1", 0); err != nil {
		t.Fatal(err)
	}
	a = audit(t, st)
	if !a.Erased || len(a.Unreferenced) != 0 {
		t.Fatalf("after sweep: %+v", a)
	}
}
