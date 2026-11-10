package store

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5"
)

// forgetKeys drops the tenant's cached keys.
func (s *Store) forgetKeys(tenantID string) {
	s.mu.Lock()
	delete(s.keys, tenantID)
	s.mu.Unlock()
}

// EraseCustomer removes every hot event of the customer and leaves a done
// tombstone. It is idempotent. The tombstone commits first (under the
// exclusive customer lock) so that later ingests are refused; the delete runs
// in a second transaction.
func (s *Store) EraseCustomer(ctx context.Context, sc Scope, customerID string) error {
	tenant := sc.TenantID()
	customerKey := sc.Keys().CustomerKey(customerID)

	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.ReadCommitted})
	if err != nil {
		return fmt.Errorf("store: erase customer begin: %w", err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck
	// Same lock order as Ingest: tenant status (shared), then customer.
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock_shared($1)`, lockKey("tenant-status", []byte(tenant))); err != nil {
		return fmt.Errorf("store: tenant status lock: %w", err)
	}
	status, err := tenantStatus(ctx, tx, tenant)
	if err != nil {
		return err
	}
	if status == "erased" {
		s.forgetKeys(tenant)
		return nil // the whole tenant is already gone
	}
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock($1)`, lockKey("customer", []byte(tenant), customerKey)); err != nil {
		return fmt.Errorf("store: customer lock: %w", err)
	}
	if _, err := tx.Exec(ctx,
		`INSERT INTO tombstones (tenant_id, customer_key, status) VALUES ($1, $2, 'pending') ON CONFLICT DO NOTHING`,
		tenant, customerKey); err != nil {
		return fmt.Errorf("store: insert tombstone: %w", err)
	}
	var tombstone string
	if err := tx.QueryRow(ctx,
		`SELECT status FROM tombstones WHERE tenant_id = $1 AND customer_key = $2`,
		tenant, customerKey).Scan(&tombstone); err != nil {
		return fmt.Errorf("store: read tombstone: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("store: erase customer commit: %w", err)
	}
	if tombstone == "done" {
		return nil
	}

	tx2, err := s.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.ReadCommitted})
	if err != nil {
		return fmt.Errorf("store: erase customer begin: %w", err)
	}
	defer tx2.Rollback(ctx) //nolint:errcheck
	if _, err := tx2.Exec(ctx, `SELECT pg_advisory_xact_lock_shared($1)`, lockKey("tenant-status", []byte(tenant))); err != nil {
		return fmt.Errorf("store: tenant status lock: %w", err)
	}
	if _, err := tx2.Exec(ctx,
		`DELETE FROM hot_events WHERE tenant_id = $1 AND customer_key = $2`, tenant, customerKey); err != nil {
		return fmt.Errorf("store: delete customer events: %w", err)
	}
	if _, err := tx2.Exec(ctx,
		`UPDATE tombstones SET status = 'done' WHERE tenant_id = $1 AND customer_key = $2`,
		tenant, customerKey); err != nil {
		return fmt.Errorf("store: finish tombstone: %w", err)
	}
	if err := tx2.Commit(ctx); err != nil {
		return fmt.Errorf("store: erase customer commit: %w", err)
	}
	return nil
}

// EraseTenant marks the tenant erased and deletes its key, events and
// tombstones in one transaction, then drops its cached keys. It is idempotent.
func (s *Store) EraseTenant(ctx context.Context, tenantID string) error {
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.ReadCommitted})
	if err != nil {
		return fmt.Errorf("store: erase tenant begin: %w", err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock($1)`, lockKey("tenant-status", []byte(tenantID))); err != nil {
		return fmt.Errorf("store: tenant status lock: %w", err)
	}
	tag, err := tx.Exec(ctx,
		`UPDATE tenants SET status = 'erased', erased_at = now() WHERE tenant_id = $1 AND status <> 'erased'`, tenantID)
	if err != nil {
		return fmt.Errorf("store: mark tenant erased: %w", err)
	}
	if tag.RowsAffected() == 0 {
		if _, err := tenantStatus(ctx, tx, tenantID); err != nil {
			return err // unknown tenant; an already erased one returns nil below
		}
	}
	for _, q := range []string{
		`DELETE FROM tenant_keys WHERE tenant_id = $1`,
		`DELETE FROM hot_events WHERE tenant_id = $1`,
		`DELETE FROM tombstones WHERE tenant_id = $1`,
	} {
		if _, err := tx.Exec(ctx, q, tenantID); err != nil {
			return fmt.Errorf("store: erase tenant data: %w", err)
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("store: erase tenant commit: %w", err)
	}
	s.forgetKeys(tenantID)
	return nil
}
