// Command api runs the backbone HTTP service.
package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"backbone/internal/api"
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

	srv := &http.Server{
		Addr:              cfg.Listen,
		Handler:           api.NewServer(reg, st, log),
		ReadHeaderTimeout: 10 * time.Second,  // slow-header clients are dropped quickly
		ReadTimeout:       30 * time.Second,  // whole request, headers plus body
		WriteTimeout:      60 * time.Second,  // the spec's 60-second read deadline
		IdleTimeout:       120 * time.Second, // keep-alive connections are reaped after two idle minutes
	}
	errc := make(chan error, 1)
	go func() { errc <- srv.ListenAndServe() }()
	log.Info("listening", "addr", cfg.Listen, "tenants", len(ids))
	select {
	case err := <-errc:
		return err
	case <-ctx.Done():
	}
	// 8s leaves headroom inside Docker's default 10s stop grace period.
	sctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()
	if err := srv.Shutdown(sctx); err != nil && !errors.Is(err, http.ErrServerClosed) {
		return err
	}
	return nil
}
