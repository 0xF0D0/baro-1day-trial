package store

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"

	"backbone/internal/canon"
	"backbone/internal/fold"
	"backbone/internal/metrics"

	"github.com/jackc/pgx/v5"
)

// IngestResult is the outcome of one Ingest call.
type IngestResult int

const (
	// Stored means the event was inserted.
	Stored IngestResult = iota
	// Duplicate means the tenant already held an event with this ID.
	Duplicate
	// CustomerErased means the customer has a tombstone; nothing was written.
	CustomerErased
	// TenantErased means the tenant is erased; nothing was written.
	TenantErased
)

// Key is a position in canonical event order.
type Key struct {
	OccurredAtMs int64
	EventID      string
}

func eventAAD(tenantID, eventID string) []byte {
	return []byte(tenantID + "\x00" + eventID)
}

// Ingest stores one event in a single READ COMMITTED transaction. It holds
// the shared tenant-status lock, then (for customer events) the shared
// customer lock, so erasure of either cannot interleave with the insert,
// and finally the shared cold-commit lock while it reads cold_until. An event
// older than cold_until is late: it is deduplicated against its day bucket
// and, when stored, marks the tenant dirty.
func (s *Store) Ingest(ctx context.Context, sc Scope, ev canon.Event) (IngestResult, error) {
	tenant := sc.TenantID()
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.ReadCommitted})
	if err != nil {
		return 0, fmt.Errorf("store: ingest begin: %w", err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock_shared($1)`, lockKey("tenant-status", []byte(tenant))); err != nil {
		return 0, fmt.Errorf("store: tenant status lock: %w", err)
	}
	status, err := tenantStatus(ctx, tx, tenant)
	if err != nil {
		return 0, err
	}
	if status == "erased" {
		s.forgetKeys(tenant)
		return TenantErased, nil
	}

	var customerKey []byte
	if ev.CustomerID != nil {
		customerKey = sc.Keys().CustomerKey(*ev.CustomerID)
		if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock_shared($1)`,
			lockKey("customer", []byte(tenant), customerKey)); err != nil {
			return 0, fmt.Errorf("store: customer lock: %w", err)
		}
		var erased bool
		if err := tx.QueryRow(ctx,
			`SELECT EXISTS (SELECT 1 FROM tombstones WHERE tenant_id = $1 AND customer_key = $2)`,
			tenant, customerKey).Scan(&erased); err != nil {
			return 0, fmt.Errorf("store: tombstone check: %w", err)
		}
		if erased {
			return CustomerErased, nil
		}
	}

	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock_shared($1)`, lockKey("cold-commit", []byte(tenant))); err != nil {
		return 0, fmt.Errorf("store: cold-commit lock: %w", err)
	}
	var coldUntil int64
	var dirty bool
	if err := tx.QueryRow(ctx, `SELECT cold_until, dirty FROM tenant_cold WHERE tenant_id = $1`, tenant).
		Scan(&coldUntil, &dirty); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return 0, ErrUnknownTenant
		}
		return 0, fmt.Errorf("store: read cold state: %w", err)
	}
	late := ev.OccurredAtMs < coldUntil
	if late {
		var object string
		err := tx.QueryRow(ctx, `SELECT object FROM cold_manifest WHERE tenant_id = $1 AND day = $2`,
			tenant, fold.Day(ev.OccurredAtMs)).Scan(&object)
		if err != nil && !errors.Is(err, pgx.ErrNoRows) {
			return 0, fmt.Errorf("store: read cold manifest: %w", err)
		}
		if err == nil {
			bucket, err := s.getBucket(ctx, sc, object)
			if err != nil {
				return 0, err
			}
			for _, b := range bucket {
				if b.EventID == ev.EventID {
					return Duplicate, nil
				}
			}
		}
	}

	plain, err := json.Marshal(ev)
	if err != nil {
		return 0, fmt.Errorf("store: marshal event: %w", err)
	}
	sealed := sc.Keys().Seal(eventAAD(tenant, ev.EventID), plain)
	tag, err := tx.Exec(ctx,
		`INSERT INTO hot_events (tenant_id, event_id, occurred_at_ms, customer_key, payload)
		 VALUES ($1, $2, $3, $4, $5) ON CONFLICT (tenant_id, event_id) DO NOTHING`,
		tenant, ev.EventID, ev.OccurredAtMs, customerKey, sealed)
	if err != nil {
		return 0, fmt.Errorf("store: insert event: %w", err)
	}
	if late && tag.RowsAffected() > 0 {
		if _, err := tx.Exec(ctx, `UPDATE tenant_cold SET dirty = true WHERE tenant_id = $1`, tenant); err != nil {
			return 0, fmt.Errorf("store: mark dirty: %w", err)
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return 0, fmt.Errorf("store: ingest commit: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return Duplicate, nil
	}
	if late {
		metrics.LateEventsTotal.Inc()
	}
	return Stored, nil
}

func tenantStatus(ctx context.Context, tx pgx.Tx, tenant string) (string, error) {
	var status string
	err := tx.QueryRow(ctx, `SELECT status FROM tenants WHERE tenant_id = $1`, tenant).Scan(&status)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", ErrUnknownTenant
	}
	if err != nil {
		return "", fmt.Errorf("store: tenant status: %w", err)
	}
	return status, nil
}

// ScanAll calls fn for every hot event of the tenant in key order, inside one
// snapshot. It returns ErrTenantErased if the tenant is erased.
func (s *Store) ScanAll(ctx context.Context, sc Scope, fn func(canon.Event) error) error {
	return s.read(ctx, sc, `SELECT event_id, payload FROM hot_events WHERE tenant_id = $1
		ORDER BY occurred_at_ms, event_id`, []any{sc.TenantID()}, fn)
}

// read runs query in a REPEATABLE READ READ ONLY transaction whose first
// statement reads the tenant status, and feeds each decrypted event to fn.
func (s *Store) read(ctx context.Context, sc Scope, query string, args []any, fn func(canon.Event) error) error {
	tenant := sc.TenantID()
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.RepeatableRead, AccessMode: pgx.ReadOnly})
	if err != nil {
		return fmt.Errorf("store: read begin: %w", err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck
	status, err := tenantStatus(ctx, tx, tenant)
	if err != nil {
		return err
	}
	if status == "erased" {
		s.forgetKeys(tenant)
		return ErrTenantErased
	}
	return scanHot(ctx, tx, sc, query, args, fn)
}

// scanHot runs query inside tx and feeds each decrypted event to fn.
func scanHot(ctx context.Context, tx pgx.Tx, sc Scope, query string, args []any, fn func(canon.Event) error) error {
	tenant := sc.TenantID()
	rows, err := tx.Query(ctx, query, args...)
	if err != nil {
		return fmt.Errorf("store: read events: %w", err)
	}
	defer rows.Close()
	for rows.Next() {
		var id string
		var sealed []byte
		if err := rows.Scan(&id, &sealed); err != nil {
			return fmt.Errorf("store: scan event: %w", err)
		}
		plain, err := sc.Keys().Open(eventAAD(tenant, id), sealed)
		if err != nil {
			return fmt.Errorf("store: decrypt event: %w", err)
		}
		var ev canon.Event
		if err := json.Unmarshal(plain, &ev); err != nil {
			return fmt.Errorf("store: decode event: %w", err)
		}
		if err := fn(ev); err != nil {
			return err
		}
	}
	if err := rows.Err(); err != nil {
		return fmt.Errorf("store: read events: %w", err)
	}
	return nil
}
