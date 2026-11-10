package store_test

import (
	"context"
	"testing"

	"backbone/internal/canon"
	"backbone/internal/fold"
	"backbone/internal/store"
)

const msDay = int64(24 * 3600 * 1000)

type pgxRow interface{ Scan(...any) error }

func dirtyAndHot(t *testing.T, ctx context.Context, q func(string, ...any) pgxRow) (bool, int) {
	t.Helper()
	var dirty bool
	if err := q(`SELECT dirty FROM tenant_cold WHERE tenant_id = 't_1'`).Scan(&dirty); err != nil {
		t.Fatal(err)
	}
	var n int
	if err := q(`SELECT count(*) FROM hot_events WHERE tenant_id = 't_1'`).Scan(&n); err != nil {
		t.Fatal(err)
	}
	return dirty, n
}

func TestIngestDedupesAgainstColdBucket(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	day := int64(100)
	e := mkEvent("evt-cold", day*msDay+5, "c1")
	if err := st.AddManifestBucket(ctx, sc, day, []canon.Event{e}); err != nil {
		t.Fatal(err)
	}
	if err := st.SetColdUntil(ctx, "t_1", (day+1)*msDay); err != nil {
		t.Fatal(err)
	}
	if fold.Day(e.OccurredAtMs) != day {
		t.Fatal("bad day")
	}
	res, err := st.Ingest(ctx, sc, e)
	if err != nil {
		t.Fatal(err)
	}
	if res != store.Duplicate {
		t.Fatalf("got %v want Duplicate", res)
	}
	dirty, n := dirtyAndHot(t, ctx, func(q string, a ...any) pgxRow { return st.Pool().QueryRow(ctx, q, a...) })
	if dirty || n != 0 {
		t.Fatalf("dirty=%v hot=%d", dirty, n)
	}
}

func TestLateEventMarksDirty(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	day := int64(100)
	if err := st.AddManifestBucket(ctx, sc, day, []canon.Event{mkEvent("evt-cold", day*msDay+5, "c1")}); err != nil {
		t.Fatal(err)
	}
	if err := st.SetColdUntil(ctx, "t_1", (day+1)*msDay); err != nil {
		t.Fatal(err)
	}
	late := mkEvent("evt-late", day*msDay+9, "c1")
	res, err := st.Ingest(ctx, sc, late)
	if err != nil || res != store.Stored {
		t.Fatalf("res=%v err=%v", res, err)
	}
	dirty, n := dirtyAndHot(t, ctx, func(q string, a ...any) pgxRow { return st.Pool().QueryRow(ctx, q, a...) })
	if !dirty || n != 1 {
		t.Fatalf("dirty=%v hot=%d", dirty, n)
	}
	// A repeat of the late event dedupes against hot.
	res, err = st.Ingest(ctx, sc, late)
	if err != nil || res != store.Duplicate {
		t.Fatalf("repeat res=%v err=%v", res, err)
	}
}

func TestLateEventWithoutBucketMarksDirty(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	if err := st.SetColdUntil(ctx, "t_1", 50*msDay); err != nil {
		t.Fatal(err)
	}
	res, err := st.Ingest(ctx, sc, mkEvent("evt-x", 10*msDay, ""))
	if err != nil || res != store.Stored {
		t.Fatalf("res=%v err=%v", res, err)
	}
	dirty, _ := dirtyAndHot(t, ctx, func(q string, a ...any) pgxRow { return st.Pool().QueryRow(ctx, q, a...) })
	if !dirty {
		t.Fatal("want dirty")
	}
}

func TestOnTimeEventDoesNotMarkDirty(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	cu := 101 * msDay
	if err := st.SetColdUntil(ctx, "t_1", cu); err != nil {
		t.Fatal(err)
	}
	res, err := st.Ingest(ctx, sc, mkEvent("evt-ontime", cu, "c1"))
	if err != nil || res != store.Stored {
		t.Fatalf("res=%v err=%v", res, err)
	}
	dirty, n := dirtyAndHot(t, ctx, func(q string, a ...any) pgxRow { return st.Pool().QueryRow(ctx, q, a...) })
	if dirty || n != 1 {
		t.Fatalf("dirty=%v hot=%d", dirty, n)
	}
}
