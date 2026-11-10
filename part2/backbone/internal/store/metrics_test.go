package store_test

import (
	"context"
	"testing"

	"backbone/internal/metrics"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/testutil"
	dto "github.com/prometheus/client_model/go"
)

func histCount(o prometheus.Observer) uint64 {
	var m dto.Metric
	if err := o.(prometheus.Metric).Write(&m); err != nil {
		panic(err)
	}
	return m.GetHistogram().GetSampleCount()
}

func readCount(kind, tier string) uint64 {
	return histCount(metrics.ReadSeconds.WithLabelValues(kind, tier))
}

func TestReadTierLabels(t *testing.T) {
	ctx := context.Background()
	st, sc, events, cu := setupT18(t, 0)

	b := readCount("state", "hot")
	if _, err := st.State(ctx, sc); err != nil {
		t.Fatal(err)
	}
	if got := readCount("state", "hot") - b; got != 1 {
		t.Errorf("never-flushed state hot delta %d want 1", got)
	}
	// Range inside hot days (nothing flushed).
	b = readCount("range", "hot")
	if _, err := st.Range(ctx, sc, 0, 1<<62, nil, 10); err != nil {
		t.Fatal(err)
	}
	if got := readCount("range", "hot") - b; got != 1 {
		t.Errorf("hot range delta %d want 1", got)
	}
	_ = events
	_ = cu

	st2, sc2, _, cu2 := setupT18(t, 2)
	b = readCount("state", "cold")
	if _, err := st2.State(ctx, sc2); err != nil {
		t.Fatal(err)
	}
	if got := readCount("state", "cold") - b; got != 1 {
		t.Errorf("flushed state cold delta %d want 1", got)
	}
	b = readCount("range", "cold")
	if _, err := st2.Range(ctx, sc2, 0, cu2, nil, 1000); err != nil {
		t.Fatal(err)
	}
	if got := readCount("range", "cold") - b; got != 1 {
		t.Errorf("cold range delta %d want 1", got)
	}
	b = readCount("range", "hot")
	if _, err := st2.Range(ctx, sc2, cu2, cu2+msDay, nil, 1000); err != nil {
		t.Fatal(err)
	}
	if got := readCount("range", "hot") - b; got != 1 {
		t.Errorf("hot-days range delta %d want 1", got)
	}
}

func TestLateAndErasureMetrics(t *testing.T) {
	ctx := context.Background()
	st, sc := newScope(t)
	day := int64(100)
	if err := st.SetColdUntil(ctx, "t_1", (day+1)*msDay); err != nil {
		t.Fatal(err)
	}
	lb := testutil.ToFloat64(metrics.LateEventsTotal)
	e := mkEvent("evt-late-m", day*msDay+9, "c1")
	if _, err := st.Ingest(ctx, sc, e); err != nil {
		t.Fatal(err)
	}
	if _, err := st.Ingest(ctx, sc, e); err != nil { // duplicate: not counted
		t.Fatal(err)
	}
	if got := testutil.ToFloat64(metrics.LateEventsTotal) - lb; got != 1 {
		t.Errorf("late delta %v want 1", got)
	}
	cb := histCount(metrics.ErasureSeconds.WithLabelValues("customer"))
	if err := st.EraseCustomer(ctx, sc, "c1"); err != nil {
		t.Fatal(err)
	}
	if got := histCount(metrics.ErasureSeconds.WithLabelValues("customer")) - cb; got != 1 {
		t.Errorf("customer erasure samples %d want 1", got)
	}
	tb := histCount(metrics.ErasureSeconds.WithLabelValues("tenant"))
	if err := st.EraseTenant(ctx, "t_1"); err != nil {
		t.Fatal(err)
	}
	if got := histCount(metrics.ErasureSeconds.WithLabelValues("tenant")) - tb; got != 1 {
		t.Errorf("tenant erasure samples %d want 1", got)
	}
}
