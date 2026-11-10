package store_test

import (
	"context"
	"errors"
	"reflect"
	"testing"
	"time"

	"backbone/internal/cold"
	"backbone/internal/store"
)

func objectGone(t *testing.T, st *store.Store, name string) bool {
	t.Helper()
	_, err := st.Objects().Get(context.Background(), name)
	if errors.Is(err, cold.ErrNotFound) {
		return true
	}
	if err != nil {
		t.Fatal(err)
	}
	return false
}

func TestSweepFinishesPendingTombstone(t *testing.T) {
	ctx := context.Background()
	st, sc, events, cu := setupT18(t, 20)
	cust := pickCustomer(t, events, cu, "both")
	key := sc.Keys().CustomerKey(cust)
	if _, err := st.Pool().Exec(ctx,
		`INSERT INTO tombstones (tenant_id, customer_key, status) VALUES ('t_1', $1, 'pending')`, key); err != nil {
		t.Fatal(err)
	}
	res, err := st.SweepTenant(ctx, "t_1", time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	if res.Tombstones != 1 {
		t.Fatalf("tombstones finished: %d, want 1", res.Tombstones)
	}
	assertErasedEqualsFold(t, st, sc, events, cust)
	if n := count(t, st, `SELECT count(*) FROM tombstones WHERE tenant_id='t_1' AND status='done'`); n != 1 {
		t.Fatalf("done tombstones: %d", n)
	}
}

func TestSweepDeletesErasedCustomerObjects(t *testing.T) {
	ctx := context.Background()
	st, sc, events, cu := setupT18(t, 40)
	cust := pickCustomer(t, events, cu, "both")
	if err := st.EraseCustomer(ctx, sc, cust); err != nil {
		t.Fatal(err)
	}
	replaced := garbageSet(t, st)
	if len(replaced) == 0 {
		t.Fatal("no garbage after erasure")
	}
	res, err := st.SweepTenant(ctx, "t_1", 0)
	if err != nil {
		t.Fatal(err)
	}
	if res.GarbageDeleted < 1 {
		t.Fatalf("garbage deleted: %d", res.GarbageDeleted)
	}
	for o := range replaced {
		if !objectGone(t, st, o) {
			t.Fatalf("replaced object %s still readable", o)
		}
	}
	if n := count(t, st, `SELECT count(*) FROM garbage WHERE tenant_id='t_1'`); n != 0 {
		t.Fatalf("garbage rows left: %d", n)
	}
	assertErasedEqualsFold(t, st, sc, events, cust)
}

func TestSweepRespectsGrace(t *testing.T) {
	ctx := context.Background()
	st, sc, events, cu := setupT18(t, 40)
	cust := pickCustomer(t, events, cu, "both")
	if err := st.EraseCustomer(ctx, sc, cust); err != nil {
		t.Fatal(err)
	}
	before := garbageSet(t, st)
	res, err := st.SweepTenant(ctx, "t_1", time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	if res.GarbageDeleted != 0 {
		t.Fatalf("garbage deleted within grace: %d", res.GarbageDeleted)
	}
	if after := garbageSet(t, st); !reflect.DeepEqual(before, after) {
		t.Fatalf("garbage rows changed: %v -> %v", before, after)
	}
	for o := range before {
		if objectGone(t, st, o) {
			t.Fatalf("object %s deleted within grace", o)
		}
	}
}

func TestSweepDeletesOrphans(t *testing.T) {
	ctx := context.Background()
	st, _, _, _ := setupT18(t, 5)
	name := cold.ObjectName("t_1", "bucket", 19000)
	if err := st.Objects().Put(ctx, name, []byte("leftover")); err != nil {
		t.Fatal(err)
	}
	res, err := st.SweepTenant(ctx, "t_1", time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	if res.OrphansDeleted != 1 {
		t.Fatalf("orphans deleted: %d, want 1", res.OrphansDeleted)
	}
	if !objectGone(t, st, name) {
		t.Fatal("orphan still readable")
	}
}

func TestSweepKeepsReferencedObjects(t *testing.T) {
	ctx := context.Background()
	st, sc, all, _, _ := rebuildSetup(t)
	if ok, err := st.Rebuild(ctx, "t_1"); err != nil || !ok {
		t.Fatalf("rebuild: ok=%v err=%v", ok, err)
	}
	res, err := st.SweepTenant(ctx, "t_1", 0)
	if err != nil {
		t.Fatal(err)
	}
	if res.GarbageDeleted < 1 {
		t.Fatalf("rebuild left no garbage to delete: %+v", res)
	}
	if res.OrphansDeleted != 0 {
		t.Fatalf("orphans deleted: %d, want 0", res.OrphansDeleted)
	}
	for _, obj := range manifestSet(t, st) {
		if _, err := st.GetBucket(ctx, sc, obj); err != nil {
			t.Fatalf("manifest object %s: %v", obj, err)
		}
	}
	if _, err := st.GetSnapshot(ctx, sc, snapshotObject(t, st)); err != nil {
		t.Fatalf("snapshot: %v", err)
	}
	assertStateEqualsFold(t, st, sc, all)
}

func TestSweepErasedTenantPrefix(t *testing.T) {
	ctx := context.Background()
	st, sc, events, cu := setupT18(t, 20)
	// Leave garbage rows behind, as an erasure of a customer does.
	if err := st.EraseCustomer(ctx, sc, pickCustomer(t, events, cu, "both")); err != nil {
		t.Fatal(err)
	}
	if len(garbageSet(t, st)) == 0 {
		t.Fatal("no garbage")
	}
	if err := st.EraseTenant(ctx, "t_1"); err != nil {
		t.Fatal(err)
	}
	if left, _ := st.Objects().List(ctx, "t_1/"); len(left) == 0 {
		t.Fatal("test setup: no objects")
	}
	res, err := st.SweepTenant(ctx, "t_1", time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	if res.OrphansDeleted == 0 {
		t.Fatalf("nothing deleted: %+v", res)
	}
	if left, err := st.Objects().List(ctx, "t_1/"); err != nil || len(left) != 0 {
		t.Fatalf("objects left: %v, %v", left, err)
	}
	if n := count(t, st, `SELECT count(*) FROM garbage WHERE tenant_id='t_1'`); n != 0 {
		t.Fatalf("garbage rows left: %d", n)
	}
}

func TestMaintainRuns(t *testing.T) {
	st, _, _, _ := setupT18(t, 1)
	if err := st.Maintain(context.Background()); err != nil {
		t.Fatal(err)
	}
}
