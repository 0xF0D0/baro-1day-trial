// Command worker flushes older events from the hot table into the cold tier.
package main

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"backbone/internal/cold"
	"backbone/internal/config"
	"backbone/internal/crypto"
	"backbone/internal/store"
	"backbone/internal/tenants"
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

	log.Info("worker started", "tenants", len(ids), "interval", cfg.FlushInterval.String())
	ticker := time.NewTicker(cfg.FlushInterval)
	defer ticker.Stop()
	for {
		tick(ctx, log, cfg, st, ids)
		select {
		case <-ctx.Done():
			log.Info("worker stopping")
			return nil
		case <-ticker.C:
		}
	}
}

// tick flushes every tenant until none has a day left to flush. An error from
// one tenant is logged by tenant ID and does not stop the others.
func tick(ctx context.Context, log *slog.Logger, cfg config.Config, st *store.Store, ids []string) {
	start := time.Now()
	days := 0
	for _, id := range ids {
		for ctx.Err() == nil {
			ok, err := st.FlushDay(ctx, id, cfg.FlushMargin, cfg.WatermarkRank)
			if err != nil {
				if ctx.Err() == nil {
					log.Error("flush failed", "tenant", id)
				}
				break
			}
			if !ok {
				break
			}
			days++
		}
	}
	log.Info("flush tick", "days_flushed", days, "duration_ms", time.Since(start).Milliseconds())
}
