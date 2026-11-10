package store

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"

	"backbone/internal/canon"

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
// customer lock, so erasure of either cannot interleave with the insert.
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
	if err := tx.Commit(ctx); err != nil {
		return 0, fmt.Errorf("store: ingest commit: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return Duplicate, nil
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

// Range returns events with fromMs <= occurred_at_ms < toMs and a key strictly
// greater than after (when non-nil), in key order, at most limit of them.
func (s *Store) Range(ctx context.Context, sc Scope, fromMs, toMs int64, after *Key, limit int) ([]canon.Event, error) {
	afterMs, afterID := int64(-1<<63), ""
	if after != nil {
		afterMs, afterID = after.OccurredAtMs, after.EventID
	}
	out := []canon.Event{}
	err := s.read(ctx, sc, `SELECT event_id, payload FROM hot_events
		WHERE tenant_id = $1 AND occurred_at_ms >= $2 AND occurred_at_ms < $3
		  AND (occurred_at_ms, event_id) > ($4, $5::text COLLATE "C")
		ORDER BY occurred_at_ms, event_id LIMIT $6`,
		[]any{sc.TenantID(), fromMs, toMs, afterMs, afterID, limit},
		func(e canon.Event) error { out = append(out, e); return nil })
	if err != nil {
		return nil, err
	}
	return out, nil
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
		return ErrTenantErased
	}
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
