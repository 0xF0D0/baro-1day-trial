package main

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"backbone/internal/store"

	"github.com/prometheus/client_golang/prometheus/testutil"
)

func TestStatsCollectorTimesOut(t *testing.T) {
	c := newStatsCollector(func(ctx context.Context) (store.Stats, error) {
		<-ctx.Done()
		return store.Stats{}, ctx.Err()
	})
	start := time.Now()
	n := testutil.CollectAndCount(c)
	if d := time.Since(start); d > 3*time.Second {
		t.Fatalf("Collect took %s", d)
	}
	if n != 0 {
		t.Fatalf("got %d samples, want 0", n)
	}
}

func TestStatsCollectorError(t *testing.T) {
	c := newStatsCollector(func(context.Context) (store.Stats, error) { return store.Stats{}, errors.New("x") })
	if n := testutil.CollectAndCount(c); n != 0 {
		t.Fatalf("got %d samples, want 0", n)
	}
}

func TestCollectorEmitsGauges(t *testing.T) {
	c := newStatsCollector(func(context.Context) (store.Stats, error) {
		return store.Stats{HotEvents: 1, HotBytes: 2, ColdEvents: 3, ColdBytes: 4,
			CustomerDaysBytes: 5, SKUMovesBytes: 6, PendingTombstones: 7, GarbageObjects: 8, DirtyTenants: 9}, nil
	})
	const want = `
# HELP backbone_dirty_tenants Tenants waiting for a rebuild.
# TYPE backbone_dirty_tenants gauge
backbone_dirty_tenants 9
# HELP backbone_garbage_objects Cold objects waiting for deletion.
# TYPE backbone_garbage_objects gauge
backbone_garbage_objects 8
# HELP backbone_index_bytes Index table size in bytes.
# TYPE backbone_index_bytes gauge
backbone_index_bytes{table="customer_days"} 5
backbone_index_bytes{table="sku_moves"} 6
# HELP backbone_pending_tombstones Tombstones not yet finished.
# TYPE backbone_pending_tombstones gauge
backbone_pending_tombstones 7
# HELP backbone_tier_bytes Stored bytes per tier.
# TYPE backbone_tier_bytes gauge
backbone_tier_bytes{tier="cold"} 4
backbone_tier_bytes{tier="hot"} 2
# HELP backbone_tier_events Events per tier.
# TYPE backbone_tier_events gauge
backbone_tier_events{tier="cold"} 3
backbone_tier_events{tier="hot"} 1
`
	if err := testutil.CollectAndCompare(c, strings.NewReader(want)); err != nil {
		t.Fatal(err)
	}
}
