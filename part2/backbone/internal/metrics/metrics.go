// Package metrics holds the Prometheus metrics of the backbone. Labels use
// only fixed values; no label carries tenant, customer or event data.
package metrics

import (
	"context"
	"errors"
	"net/http"

	"backbone/internal/cold"

	"github.com/jackc/pgx/v5/pgconn"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/collectors"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var registry = prometheus.NewRegistry()

var (
	IngestTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "backbone_ingest_total", Help: "Webhook deliveries by vendor and outcome.",
	}, []string{"vendor", "outcome"})
	AckSeconds = prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Name: "backbone_ack_seconds", Help: "Time to answer a webhook with 200.",
		Buckets: prometheus.DefBuckets,
	}, []string{"vendor"})
	ReadSeconds = prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Name: "backbone_read_seconds", Help: "State and range read time by kind and tier.",
		Buckets: prometheus.DefBuckets,
	}, []string{"kind", "tier"})
	LateEventsTotal = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "backbone_late_events_total", Help: "Late events inserted behind the cold boundary.",
	})
	ErasureSeconds = prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Name: "backbone_erasure_seconds", Help: "Successful erasure time by kind.",
		Buckets: prometheus.DefBuckets,
	}, []string{"kind"})
	SnapshotCacheTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "backbone_snapshot_cache_total", Help: "Snapshot cache lookups by result.",
	}, []string{"result"})
	JobSeconds = prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Name: "backbone_job_seconds", Help: "Worker job duration.",
		Buckets: []float64{.01, .05, .1, .5, 1, 5, 15, 60, 300},
	}, []string{"job"})
	JobErrorsTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "backbone_job_errors_total", Help: "Worker job failures by job and error class.",
	}, []string{"job", "class"})
	RebuildsTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "backbone_rebuilds_total", Help: "Snapshot rebuilds by reason.",
	}, []string{"reason"})
)

func init() {
	registry.MustRegister(
		collectors.NewGoCollector(),
		collectors.NewProcessCollector(collectors.ProcessCollectorOpts{}),
		IngestTotal, AckSeconds, ReadSeconds, LateEventsTotal, ErasureSeconds,
		SnapshotCacheTotal, JobSeconds, JobErrorsTotal, RebuildsTotal,
	)
	// Create every fixed series up front so scrapes show zeros and rate()
	// works from the first event.
	for _, v := range []string{"a", "b"} {
		AckSeconds.WithLabelValues(v)
		for _, o := range []string{"stored", "duplicate", "customer_erased", "tenant_erased",
			"bad_request", "unknown_tenant", "bad_signature", "error"} {
			IngestTotal.WithLabelValues(v, o)
		}
	}
	for _, k := range []string{"state", "range"} {
		for _, tier := range []string{"hot", "cold"} {
			ReadSeconds.WithLabelValues(k, tier)
		}
	}
	for _, k := range []string{"customer", "tenant"} {
		ErasureSeconds.WithLabelValues(k)
	}
	for _, r := range []string{"hit", "miss"} {
		SnapshotCacheTotal.WithLabelValues(r)
	}
	for _, j := range []string{"flush", "rebuild", "sweep"} {
		JobSeconds.WithLabelValues(j)
	}
	RebuildsTotal.WithLabelValues("late_events")
}

// Register adds a collector (for example scrape-time gauges) to the registry.
func Register(c prometheus.Collector) { registry.MustRegister(c) }

// Handler serves the private registry.
func Handler() http.Handler {
	return promhttp.HandlerFor(registry, promhttp.HandlerOpts{})
}

// ErrorClass maps an error to a fixed label value.
func ErrorClass(err error) string {
	var pg *pgconn.PgError
	switch {
	case errors.As(err, &pg):
		return "postgres_" + pg.Code
	case errors.Is(err, cold.ErrNotFound):
		return "object_not_found"
	case errors.Is(err, context.Canceled), errors.Is(err, context.DeadlineExceeded):
		return "canceled"
	}
	return "other"
}
