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

// The grace period runs from the moment the replacing commit writes the
// garbage row, not from the start of the transaction. A rebuild that waits for
// the cold-writer lock must not backdate its garbage rows by the wait.
func TestGraceRunsFromReplacement(t *testing.T) {
	ctx := context.Background()
	st, _, _, _, _ := rebuildSetup(t)
	before := garbageSet(t, st)

	conn, err := st.Pool().Acquire(ctx)
	if err != nil {
		t.Fatal(err)
	}
	tx, err := conn.Begin(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock($1)`, store.LockKey("cold-writer", []byte("t_1"))); err != nil {
		t.Fatal(err)
	}
	go func() {
		time.Sleep(3 * time.Second)
		_ = tx.Rollback(ctx)
		conn.Release()
	}()
	ok, err := st.Rebuild(ctx, "t_1")
	if err != nil || !ok {
		t.Fatalf("rebuild: %v %v", ok, err)
	}
	var fresh []string
	for o := range garbageSet(t, st) {
		if !before[o] {
			fresh = append(fresh, o)
		}
	}
	if len(fresh) == 0 {
		t.Fatal("rebuild replaced no objects")
	}
	var age float64
	if err := st.Pool().QueryRow(ctx,
		`SELECT extract(epoch FROM now() - min(replaced_at)) FROM garbage WHERE object = ANY($1)`, fresh).Scan(&age); err != nil {
		t.Fatal(err)
	}
	t.Logf("replaced_at is %.2fs old right after the commit", age)
	if age > 1 {
		t.Errorf("garbage rows backdated by %.2fs", age)
	}
	if _, err := st.SweepTenant(ctx, "t_1", 2*time.Second); err != nil {
		t.Fatal(err)
	}
	for _, o := range fresh {
		if objectGone(t, st, o) {
			t.Errorf("an object replaced moments ago was deleted under a 2s grace")
		}
	}
}

// A pending tombstone that cannot be finished must not stop the other
// tombstones or the garbage and orphan passes.
func TestSweepPassesAreIndependent(t *testing.T) {
	ctx := context.Background()
	st, sc, events, cu := setupT18(t, 20)
	cust := pickCustomer(t, events, cu, "both")
	badKey := sc.Keys().CustomerKey(cust)
	otherKey := sc.Keys().CustomerKey("cus_does_not_exist")

	// Corrupt a bucket the customer appears in, so erasing the customer fails.
	var obj string
	if err := st.Pool().QueryRow(ctx, `SELECT m.object FROM customer_days d
		JOIN cold_manifest m ON m.tenant_id = d.tenant_id AND m.day = d.day
		WHERE d.tenant_id = 't_1' AND d.customer_key = $1 LIMIT 1`, badKey).Scan(&obj); err != nil {
		t.Fatal(err)
	}
	if err := st.Objects().Put(ctx, obj, []byte("not a sealed object")); err != nil {
		t.Fatal(err)
	}
	for _, k := range [][]byte{badKey, otherKey} {
		if _, err := st.Pool().Exec(ctx,
			`INSERT INTO tombstones (tenant_id, customer_key, status) VALUES ('t_1', $1, 'pending')`, k); err != nil {
			t.Fatal(err)
		}
	}
	orphan := "t_1/buckets/1999-01-01/orphan.jsonl.enc"
	if err := st.Objects().Put(ctx, orphan, []byte("x")); err != nil {
		t.Fatal(err)
	}

	res, err := st.SweepTenant(ctx, "t_1", time.Hour)
	if err == nil {
		t.Fatal("sweep reported no error although a tombstone cannot be finished")
	}
	if res.Tombstones != 1 {
		t.Errorf("tombstones finished: %d, want 1 (the one that can be)", res.Tombstones)
	}
	if res.OrphansDeleted < 1 || !objectGone(t, st, orphan) {
		t.Errorf("orphan pass did not run after the tombstone failure: %+v", res)
	}
	if n := count(t, st, `SELECT count(*) FROM tombstones WHERE tenant_id='t_1' AND status='pending'`); n != 1 {
		t.Errorf("pending tombstones: %d, want 1", n)
	}
}
