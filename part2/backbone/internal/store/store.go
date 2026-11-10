// Package store is the Postgres layer: schema, tenant key rows and scopes.
package store

import (
	"context"
	_ "embed"
	"errors"
	"fmt"
	"sync"

	"backbone/internal/cold"
	"backbone/internal/crypto"

	"github.com/jackc/pgx/v5/pgxpool"
)

//go:embed schema.sql
var schemaSQL string

var (
	// ErrTenantErased means the tenant exists but its key was destroyed.
	ErrTenantErased = errors.New("store: tenant erased")
	// ErrUnknownTenant means the tenant has no row.
	ErrUnknownTenant = errors.New("store: unknown tenant")
)

// Store wraps the connection pool and the key-encryption key.
type Store struct {
	pool *pgxpool.Pool
	kek  *crypto.KEK

	objects *cold.Client

	mu   sync.Mutex
	keys map[string]*crypto.TenantKeys

	snaps *snapCache
}

// Open connects to Postgres with synchronous_commit=on for every session.
func Open(ctx context.Context, databaseURL string, kek *crypto.KEK, objects *cold.Client) (*Store, error) {
	cfg, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		return nil, fmt.Errorf("store: parse database url: %w", err)
	}
	cfg.ConnConfig.RuntimeParams["synchronous_commit"] = "on"
	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		return nil, fmt.Errorf("store: open pool: %w", err)
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("store: ping: %w", err)
	}
	return &Store{pool: pool, kek: kek, objects: objects, keys: map[string]*crypto.TenantKeys{}, snaps: newSnapCache()}, nil
}

// Close stops the snapshot cache janitor and releases the pool.
func (s *Store) Close() {
	s.snaps.stopJanitor()
	s.pool.Close()
}

// Ping checks that the database is reachable.
func (s *Store) Ping(ctx context.Context) error { return s.pool.Ping(ctx) }

// Pool exposes the pool to sibling packages that run their own queries.
func (s *Store) Pool() *pgxpool.Pool { return s.pool }

// Migrate applies schema.sql under a session advisory lock on one connection.
func (s *Store) Migrate(ctx context.Context) error {
	conn, err := s.pool.Acquire(ctx)
	if err != nil {
		return fmt.Errorf("store: acquire: %w", err)
	}
	defer conn.Release()
	key := lockKey("migrate")
	if _, err := conn.Exec(ctx, "SELECT pg_advisory_lock($1)", key); err != nil {
		return fmt.Errorf("store: migrate lock: %w", err)
	}
	defer func() {
		// Use a fresh context so the unlock still runs after cancellation.
		_, _ = conn.Exec(context.WithoutCancel(ctx), "SELECT pg_advisory_unlock($1)", key)
	}()
	if _, err := conn.Exec(ctx, schemaSQL); err != nil {
		return fmt.Errorf("store: migrate: %w", err)
	}
	return nil
}

// Objects returns the cold-tier client the store was opened with.
func (s *Store) Objects() *cold.Client { return s.objects }
