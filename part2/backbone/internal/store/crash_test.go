package store_test

import (
	"context"
	"fmt"
	"slices"
	"testing"

	"backbone/internal/canon"
	"backbone/internal/crashpoint"
	"backbone/internal/store"
)

type crashed struct{}

// pointers captures everything a commit would change.
func pointers(t *testing.T, st *store.Store) string {
	t.Helper()
	ctx := context.Background()
	var cu int64
	var snap *string
	var dirty bool
	if err := st.Pool().QueryRow(ctx, `SELECT cold_until, snapshot_object, dirty FROM tenant_cold WHERE tenant_id='t_1'`).
		Scan(&cu, &snap, &dirty); err != nil {
		t.Fatal(err)
	}
	s := fmt.Sprintf("cold_until=%d snapshot=%v dirty=%v", cu, snap, dirty)
	if snap != nil {
		s = fmt.Sprintf("cold_until=%d snapshot=%s dirty=%v", cu, *snap, dirty)
	}
	m := manifestSet(t, st)
	days := make([]int64, 0, len(m))
	for d := range m {
		days = append(days, d)
	}
	slices.Sort(days)
	for _, d := range days {
		s += fmt.Sprintf(" m%d=%s", d, m[d])
	}
	g := garbageSet(t, st)
	keys := make([]string, 0, len(g))
	for k := range g {
		keys = append(keys, k)
	}
	slices.Sort(keys)
	s += fmt.Sprintf(" garbage=%v hot=%d customer_days=%d sku_moves=%d", keys,
		count(t, st, `SELECT count(*) FROM hot_events WHERE tenant_id='t_1'`),
		count(t, st, `SELECT count(*) FROM customer_days WHERE tenant_id='t_1'`),
		count(t, st, `SELECT count(*) FROM sku_moves WHERE tenant_id='t_1'`))
	return s
}

func runCrashing(t *testing.T, name string, f func() error) {
	t.Helper()
	if err := crashpoint.Arm([]string{name}, 1); err != nil {
		t.Fatal(err)
	}
	restore := crashpoint.Intercept(func() { panic(crashed{}) })
	defer restore()
	defer crashpoint.Arm(nil, 0) //nolint:errcheck
	hit := false
	func() {
		defer func() {
			if r := recover(); r != nil {
				if _, ok := r.(crashed); !ok {
					panic(r)
				}
				hit = true
			}
		}()
		err := f()
		t.Fatalf("%s: call returned without crashing (err=%v)", name, err)
	}()
	if !hit {
		t.Fatalf("%s: no crash", name)
	}
}

// crashSetup returns a store ready for the point's operation and every ingested event.
func crashSetup(t *testing.T, name string) (*store.Store, []canon.Event, []canon.Event) {
	t.Helper()
	if name[:5] == "flush" {
		st, sc := newScope(t)
		events := loadT18(t)
		ingestAll(t, st, sc, events)
		// One day is already flushed, so the crashed transaction also wrote
		// index rows and a garbage row that must roll back.
		if ok, err := st.FlushDay(context.Background(), "t_1", 0, 1); err != nil || !ok {
			t.Fatalf("setup flush: ok=%v err=%v", ok, err)
		}
		return st, events, nil
	}
	st, _, all, late, _ := rebuildSetup(t)
	return st, all, late
}

func TestCrashPoints(t *testing.T) {
	for _, name := range crashpoint.Names {
		t.Run(name, func(t *testing.T) {
			ctx := context.Background()
			st, all, _ := crashSetup(t, name)
			before := pointers(t, st)
			objectsBefore, err := st.Objects().List(ctx, "t_1/")
			if err != nil {
				t.Fatal(err)
			}
			isFlush := name[:5] == "flush"
			runCrashing(t, name, func() error {
				if isFlush {
					_, err := st.FlushDay(ctx, "t_1", 0, 1)
					return err
				}
				_, err := st.Rebuild(ctx, "t_1")
				return err
			})
			if after := pointers(t, st); after != before {
				t.Fatalf("crash changed pointers:\n before %s\n after  %s", before, after)
			}
			objectsAfter, err := st.Objects().List(ctx, "t_1/")
			if err != nil {
				t.Fatal(err)
			}
			if len(objectsAfter) <= len(objectsBefore) {
				t.Fatalf("no new objects exist at the crash: %d -> %d", len(objectsBefore), len(objectsAfter))
			}

			if isFlush {
				for {
					ok, err := st.FlushDay(ctx, "t_1", 0, 1)
					if err != nil {
						t.Fatal(err)
					}
					if !ok {
						break
					}
				}
			} else if ok, err := st.Rebuild(ctx, "t_1"); err != nil || !ok {
				t.Fatalf("rebuild: ok=%v err=%v", ok, err)
			}
			res, err := st.SweepTenant(ctx, "t_1", 0)
			if err != nil {
				t.Fatal(err)
			}
			if res.OrphansDeleted < 1 {
				t.Fatalf("sweep deleted no orphans: %+v", res)
			}
			a := audit(t, st)
			var got, want []string
			got = append(append(got, a.HotIDs...), a.ColdIDs...)
			for _, e := range all {
				want = append(want, e.EventID)
			}
			slices.Sort(got)
			slices.Sort(want)
			if !slices.Equal(got, want) {
				t.Fatalf("ids: got %d, want %d (or repeats)", len(got), len(want))
			}
			if len(a.BadPointers) != 0 || len(a.Unreferenced) != 0 || a.GarbageRows != 0 || !a.StateMatches ||
				!a.IndexMatches || len(a.TierViolations) != 0 {
				t.Fatalf("not clean: %+v", a)
			}
			sc, err := st.Scope(ctx, "t_1")
			if err != nil {
				t.Fatal(err)
			}
			assertStateEqualsFold(t, st, sc, all)
		})
	}
}

func TestCrashedRebuildThenRedeliveryIsDuplicate(t *testing.T) {
	ctx := context.Background()
	st, _, late := crashSetup(t, "rebuild.before_commit")
	runCrashing(t, "rebuild.before_commit", func() error {
		_, err := st.Rebuild(ctx, "t_1")
		return err
	})
	sc, err := st.Scope(ctx, "t_1")
	if err != nil {
		t.Fatal(err)
	}
	res, err := st.Ingest(ctx, sc, late[0])
	if err != nil || res != store.Duplicate {
		t.Fatalf("redelivery: res=%v err=%v", res, err)
	}
}
