// Command worker flushes older events from the hot table into the cold tier.
package main

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"sync/atomic"
	"syscall"
	"time"

	"backbone/internal/cold"
	"backbone/internal/config"
	"backbone/internal/crashpoint"
	"backbone/internal/crypto"
	"backbone/internal/metrics"
	"backbone/internal/store"
	"backbone/internal/tenants"

	"github.com/prometheus/client_golang/prometheus"
)

func main() {
	log := slog.New(slog.NewJSONHandler(os.Stderr, nil))
	if err := run(log); err != nil {
		log.Error("fatal", "err", err.Error())
		os.Exit(1)
	}
}

func run(log *slog.Logger) error {
	cfg, err := config.Load(os.Getenv)
	if err != nil {
		return err
	}
	if err := crashpoint.Arm(cfg.CrashPoints, cfg.CrashProbability); err != nil {
		return err
	}
	if len(cfg.CrashPoints) > 0 {
		log.Warn("crash points armed", "points", cfg.CrashPoints, "probability", cfg.CrashProbability)
	}
	reg, err := tenants.Load(cfg.TenantsFile)
	if err != nil {
		return err
	}
	kek, err := crypto.LoadKEK(cfg.KEKFile)
	if err != nil {
		return err
	}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()

	user, err := os.ReadFile(cfg.MinioUserFile)
	if err != nil {
		return fmt.Errorf("read minio user file: %w", err)
	}
	pass, err := os.ReadFile(cfg.MinioPasswordFile)
	if err != nil {
		return fmt.Errorf("read minio password file: %w", err)
	}
	objects, err := cold.Open(ctx, cold.Config{
		Endpoint:  cfg.MinioEndpoint,
		AccessKey: strings.TrimSpace(string(user)),
		SecretKey: strings.TrimSpace(string(pass)),
		Bucket:    cfg.MinioBucket,
	})
	if err != nil {
		return err
	}
	st, err := store.Open(ctx, cfg.DatabaseURL, kek, objects)
	if err != nil {
		return err
	}
	defer st.Close()
	if err := st.Migrate(ctx); err != nil {
		return err
	}
	var ids []string
	for _, t := range reg.All() {
		ids = append(ids, t.ID)
	}
	if err := st.EnsureTenants(ctx, ids); err != nil {
		return err
	}

	// lastSweep is the unix-nano time of the last completed sweep, or of the
	// worker start until one completes.
	var lastSweep atomic.Int64
	lastSweep.Store(time.Now().UnixNano())
	metrics.Register(prometheus.NewGaugeFunc(prometheus.GaugeOpts{
		Name: "backbone_last_sweep_age_seconds",
		Help: "Seconds since the last completed sweep (or worker start).",
	}, func() float64 { return time.Since(time.Unix(0, lastSweep.Load())).Seconds() }))
	metrics.Register(newStatsCollector(st.Stats))
	mux := http.NewServeMux()
	mux.Handle("GET /metrics", metrics.Handler())
	srv := &http.Server{
		Addr: cfg.MetricsListen, Handler: mux,
		ReadTimeout: 10 * time.Second, WriteTimeout: 10 * time.Second,
	}
	go func() {
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Error("metrics server failed", "err", err.Error())
		}
	}()
	defer srv.Close()

	log.Info("worker started", "tenants", len(ids), "interval", cfg.FlushInterval.String(), "sweep_interval", cfg.SweepInterval.String())
	flushTicker := time.NewTicker(cfg.FlushInterval)
	defer flushTicker.Stop()
	sweepTicker := time.NewTicker(cfg.SweepInterval)
	defer sweepTicker.Stop()
	// One loop serves both tickers, so rebuild, flush and sweep never overlap.
	tick(ctx, log, cfg, st, ids)
	// Sweep once at startup too, so a worker that restarts more often than the
	// sweep interval still sweeps.
	sweep(ctx, log, cfg, st, ids, &lastSweep)
	for {
		select {
		case <-ctx.Done():
			log.Info("worker stopping")
			return nil
		case <-flushTicker.C:
			tick(ctx, log, cfg, st, ids)
		case <-sweepTicker.C:
			sweep(ctx, log, cfg, st, ids, &lastSweep)
		}
	}
}

// tick rebuilds a dirty tenant, then flushes it until no day is left to flush.
// An error from one tenant is logged by tenant ID and does not stop the others.
func tick(ctx context.Context, log *slog.Logger, cfg config.Config, st *store.Store, ids []string) {
	start := time.Now()
	days := 0
	for _, id := range ids {
		if ctx.Err() != nil {
			break
		}
		rebuildStart := time.Now()
		rebuilt, err := st.Rebuild(ctx, id)
		if err != nil {
			if ctx.Err() == nil {
				class := metrics.ErrorClass(err)
				metrics.JobErrorsTotal.WithLabelValues("rebuild", class).Inc()
				log.Error("rebuild failed", "tenant", id, "class", class)
			}
			continue
		}
		if rebuilt {
			metrics.JobSeconds.WithLabelValues("rebuild").Observe(time.Since(rebuildStart).Seconds())
			metrics.RebuildsTotal.WithLabelValues("late_events").Inc()
			log.Info("tenant rebuilt", "tenant", id)
		}
		for ctx.Err() == nil {
			flushStart := time.Now()
			ok, err := st.FlushDay(ctx, id, cfg.FlushMargin, cfg.WatermarkRank)
			if err != nil {
				if ctx.Err() == nil {
					class := metrics.ErrorClass(err)
					metrics.JobErrorsTotal.WithLabelValues("flush", class).Inc()
					log.Error("flush failed", "tenant", id, "class", class)
				}
				break
			}
			if !ok {
				break
			}
			metrics.JobSeconds.WithLabelValues("flush").Observe(time.Since(flushStart).Seconds())
			days++
		}
	}
	log.Info("flush tick", "days_flushed", days, "duration_ms", time.Since(start).Milliseconds())
}

// sweep deletes expired garbage, leftovers and erased customers' objects for
// every registry tenant (erased tenants stay in the registry), then runs
// Postgres maintenance.
func sweep(ctx context.Context, log *slog.Logger, cfg config.Config, st *store.Store, ids []string, lastSweep *atomic.Int64) {
	start := time.Now()
	var total store.SweepResult
	clean := true
	for _, id := range ids {
		if ctx.Err() != nil {
			return
		}
		r, err := st.SweepTenant(ctx, id, cfg.GarbageGrace)
		total.Tombstones += r.Tombstones
		total.GarbageDeleted += r.GarbageDeleted
		total.OrphansDeleted += r.OrphansDeleted
		if err != nil {
			clean = false
		}
		if err != nil && ctx.Err() == nil {
			class := metrics.ErrorClass(err)
			metrics.JobErrorsTotal.WithLabelValues("sweep", class).Inc()
			log.Error("sweep failed", "tenant", id, "class", class)
		}
	}
	if err := st.Maintain(ctx); err != nil {
		if ctx.Err() == nil {
			class := metrics.ErrorClass(err)
			metrics.JobErrorsTotal.WithLabelValues("maintain", class).Inc()
			log.Error("maintenance failed", "class", class)
		}
		return
	}
	if !clean {
		// Failures are counted in job_errors_total; the sweep age keeps growing.
		return
	}
	metrics.JobSeconds.WithLabelValues("sweep").Observe(time.Since(start).Seconds())
	lastSweep.Store(time.Now().UnixNano())
	log.Info("sweep done", "tombstones", total.Tombstones, "garbage_deleted", total.GarbageDeleted,
		"orphans_deleted", total.OrphansDeleted, "duration_ms", time.Since(start).Milliseconds())
}
