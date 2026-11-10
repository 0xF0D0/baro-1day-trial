package main

import (
	"context"
	"time"

	"backbone/internal/store"

	"github.com/prometheus/client_golang/prometheus"
)

const statsTimeout = 2 * time.Second

var (
	descTierEvents = prometheus.NewDesc("backbone_tier_events", "Events per tier.", []string{"tier"}, nil)
	descTierBytes  = prometheus.NewDesc("backbone_tier_bytes", "Stored bytes per tier.", []string{"tier"}, nil)
	descIndexBytes = prometheus.NewDesc("backbone_index_bytes", "Index table size in bytes.", []string{"table"}, nil)
	descTombstones = prometheus.NewDesc("backbone_pending_tombstones", "Tombstones not yet finished.", nil, nil)
	descGarbage    = prometheus.NewDesc("backbone_garbage_objects", "Cold objects waiting for deletion.", nil, nil)
	descDirty      = prometheus.NewDesc("backbone_dirty_tenants", "Tenants waiting for a rebuild.", nil, nil)
)

// statsCollector reads the storage gauges at scrape time.
type statsCollector struct {
	stats func(context.Context) (store.Stats, error)
}

func newStatsCollector(stats func(context.Context) (store.Stats, error)) *statsCollector {
	return &statsCollector{stats: stats}
}

func (c *statsCollector) Describe(ch chan<- *prometheus.Desc) {
	for _, d := range []*prometheus.Desc{descTierEvents, descTierBytes, descIndexBytes, descTombstones, descGarbage, descDirty} {
		ch <- d
	}
}

// Collect emits nothing when Stats fails or takes longer than two seconds.
func (c *statsCollector) Collect(ch chan<- prometheus.Metric) {
	ctx, cancel := context.WithTimeout(context.Background(), statsTimeout)
	defer cancel()
	s, err := c.stats(ctx)
	if err != nil {
		return
	}
	g := func(d *prometheus.Desc, v int64, lv ...string) {
		ch <- prometheus.MustNewConstMetric(d, prometheus.GaugeValue, float64(v), lv...)
	}
	g(descTierEvents, s.HotEvents, "hot")
	g(descTierEvents, s.ColdEvents, "cold")
	g(descTierBytes, s.HotBytes, "hot")
	g(descTierBytes, s.ColdBytes, "cold")
	g(descIndexBytes, s.CustomerDaysBytes, "customer_days")
	g(descIndexBytes, s.SKUMovesBytes, "sku_moves")
	g(descTombstones, s.PendingTombstones)
	g(descGarbage, s.GarbageObjects)
	g(descDirty, s.DirtyTenants)
}
