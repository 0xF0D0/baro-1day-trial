package store

import (
	"bytes"
	"context"
	"encoding/hex"
	"fmt"
	"time"

	"backbone/internal/canon"
	"backbone/internal/fold"
	"backbone/internal/metrics"

	"github.com/jackc/pgx/v5"
)

// forgetKeys drops the tenant's cached keys and cached snapshot, so that no
// path that forgets an erased tenant's keys leaves decrypted data in memory.
func (s *Store) forgetKeys(tenantID string) {
	s.mu.Lock()
	delete(s.keys, tenantID)
	s.mu.Unlock()
	s.snaps.drop(tenantID)
}

// forgetTenant drops everything cached for an erased tenant.
func (s *Store) forgetTenant(tenantID string) {
	s.forgetKeys(tenantID)
}

// EraseCustomer removes every hot event of the customer and leaves a done
// tombstone. It is idempotent. The tombstone commits first (under the
// exclusive customer lock) so that later ingests are refused; the delete runs
// in a second transaction.
func (s *Store) EraseCustomer(ctx context.Context, sc Scope, customerID string) error {
	start := time.Now()
	err := s.eraseCustomer(ctx, sc, customerID)
	if err == nil {
		s.snaps.drop(sc.TenantID())
		metrics.ErasureSeconds.WithLabelValues("customer").Observe(time.Since(start).Seconds())
	}
	return err
}

func (s *Store) eraseCustomer(ctx context.Context, sc Scope, customerID string) error {
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

	return s.finishErasure(ctx, sc, customerKey)
}

// coldPlan is the object work of one customer erasure, prepared before the
// commit locks are taken.
type coldPlan struct {
	replaceDays map[int64]string // day -> new bucket object
	replaceN    map[int64]int    // day -> remaining event count
	replaceB    map[int64]int    // day -> new bucket size in bytes
	deleteDays  []int64          // days whose bucket becomes empty
	oldObjects  []string         // replaced buckets
	oldSnapshot *string
	newSnapshot string
	removedIDs  []string
}

// finishErasure is the second transaction of EraseCustomer, driven by the
// customer key alone, because a pending tombstone stores only the key. It
// holds the cold-writer lock for its whole length, so a flush that already
// read the customer's hot rows finishes first and the erasure then sees its
// output.
func (s *Store) finishErasure(ctx context.Context, sc Scope, customerKey []byte) error {
	tenant := sc.TenantID()

	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.ReadCommitted})
	if err != nil {
		return fmt.Errorf("store: erase customer begin: %w", err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock($1)`, lockKey("cold-writer", []byte(tenant))); err != nil {
		return fmt.Errorf("store: cold-writer lock: %w", err)
	}
	status, err := tenantStatus(ctx, tx, tenant)
	if err != nil {
		return err
	}
	if status == "erased" {
		s.forgetKeys(tenant)
		if _, err := tx.Exec(ctx,
			`UPDATE tombstones SET status = 'done' WHERE tenant_id = $1 AND customer_key = $2`,
			tenant, customerKey); err != nil {
			return fmt.Errorf("store: finish tombstone: %w", err)
		}
		if err := tx.Commit(ctx); err != nil {
			return fmt.Errorf("store: erase customer commit: %w", err)
		}
		return nil
	}

	plan, err := s.planColdErase(ctx, tx, sc, customerKey)
	if err != nil {
		return err
	}

	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock_shared($1)`, lockKey("tenant-status", []byte(tenant))); err != nil {
		return fmt.Errorf("store: tenant status lock: %w", err)
	}
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock($1)`, lockKey("cold-commit", []byte(tenant))); err != nil {
		return fmt.Errorf("store: cold-commit lock: %w", err)
	}
	status, err = tenantStatus(ctx, tx, tenant)
	if err != nil {
		return err
	}
	if status == "erased" {
		s.forgetKeys(tenant)
		return nil
	}
	for day, obj := range plan.replaceDays {
		if _, err := tx.Exec(ctx, `UPDATE cold_manifest SET object = $3, events = $4, bytes = $5 WHERE tenant_id = $1 AND day = $2`,
			tenant, day, obj, plan.replaceN[day], plan.replaceB[day]); err != nil {
			return fmt.Errorf("store: update manifest: %w", err)
		}
	}
	for _, day := range plan.deleteDays {
		if _, err := tx.Exec(ctx, `DELETE FROM cold_manifest WHERE tenant_id = $1 AND day = $2`, tenant, day); err != nil {
			return fmt.Errorf("store: delete manifest: %w", err)
		}
	}
	if plan.newSnapshot != "" {
		if _, err := tx.Exec(ctx, `UPDATE tenant_cold SET snapshot_object = $2 WHERE tenant_id = $1`,
			tenant, plan.newSnapshot); err != nil {
			return fmt.Errorf("store: update snapshot pointer: %w", err)
		}
	}
	for _, q := range []string{
		`DELETE FROM hot_events WHERE tenant_id = $1 AND customer_key = $2`,
		`DELETE FROM customer_days WHERE tenant_id = $1 AND customer_key = $2`,
	} {
		if _, err := tx.Exec(ctx, q, tenant, customerKey); err != nil {
			return fmt.Errorf("store: delete customer rows: %w", err)
		}
	}
	if len(plan.removedIDs) > 0 {
		if _, err := tx.Exec(ctx, `DELETE FROM sku_moves WHERE tenant_id = $1 AND event_id = ANY($2)`,
			tenant, plan.removedIDs); err != nil {
			return fmt.Errorf("store: delete sku moves: %w", err)
		}
	}
	if _, err := tx.Exec(ctx,
		`UPDATE tombstones SET status = 'done' WHERE tenant_id = $1 AND customer_key = $2`,
		tenant, customerKey); err != nil {
		return fmt.Errorf("store: finish tombstone: %w", err)
	}
	// Garbage rows are the last writes before COMMIT, so the grace period
	// starts when the replacement is final, not when the transaction began.
	garbage := plan.oldObjects
	if plan.oldSnapshot != nil {
		garbage = append(garbage, *plan.oldSnapshot)
	}
	for _, o := range garbage {
		if _, err := tx.Exec(ctx, `INSERT INTO garbage (object, tenant_id) VALUES ($1, $2) ON CONFLICT DO NOTHING`,
			o, tenant); err != nil {
			return fmt.Errorf("store: insert garbage: %w", err)
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("store: erase customer commit: %w", err)
	}
	return nil
}

// planColdErase rewrites the customer's buckets and the snapshot as new
// objects. It changes nothing in Postgres.
func (s *Store) planColdErase(ctx context.Context, tx pgx.Tx, sc Scope, customerKey []byte) (coldPlan, error) {
	tenant := sc.TenantID()
	plan := coldPlan{replaceDays: map[int64]string{}, replaceN: map[int64]int{}, replaceB: map[int64]int{}}

	rows, err := tx.Query(ctx, `SELECT day FROM customer_days WHERE tenant_id = $1 AND customer_key = $2 ORDER BY day`,
		tenant, customerKey)
	if err != nil {
		return plan, fmt.Errorf("store: read customer days: %w", err)
	}
	var days []int64
	for rows.Next() {
		var d int64
		if err := rows.Scan(&d); err != nil {
			rows.Close()
			return plan, fmt.Errorf("store: scan customer day: %w", err)
		}
		days = append(days, d)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return plan, fmt.Errorf("store: read customer days: %w", err)
	}
	if len(days) == 0 {
		return plan, nil
	}

	var removed []canon.Event
	remaining := map[int64][]canon.Event{}
	oldObject := map[int64]string{}
	for _, day := range days {
		var obj string
		if err := tx.QueryRow(ctx, `SELECT object FROM cold_manifest WHERE tenant_id = $1 AND day = $2`,
			tenant, day).Scan(&obj); err != nil {
			return plan, fmt.Errorf("store: read manifest row: %w", err)
		}
		events, err := s.getBucket(ctx, sc, obj)
		if err != nil {
			return plan, err
		}
		keep := make([]canon.Event, 0, len(events))
		hit := false
		for _, ev := range events {
			if ev.CustomerID != nil && bytes.Equal(sc.Keys().CustomerKey(*ev.CustomerID), customerKey) {
				removed = append(removed, ev)
				plan.removedIDs = append(plan.removedIDs, ev.EventID)
				hit = true
			} else {
				keep = append(keep, ev)
			}
		}
		if !hit {
			continue
		}
		remaining[day] = keep
		oldObject[day] = obj
	}
	if len(removed) == 0 {
		return plan, nil
	}

	for day, keep := range remaining {
		plan.oldObjects = append(plan.oldObjects, oldObject[day])
		if len(keep) == 0 {
			plan.deleteDays = append(plan.deleteDays, day)
			continue
		}
		name, size, err := s.putBucket(ctx, sc, day, keep)
		if err != nil {
			return plan, err
		}
		plan.replaceDays[day] = name
		plan.replaceN[day] = len(keep)
		plan.replaceB[day] = size
	}

	// Latest remaining message time of each affected day, with fold semantics.
	dayMax := map[int64]*int64{}
	for _, day := range fold.AffectedDays(removed) {
		x := fold.New(tenant, sc.Keys().CustomerKeyHex)
		for _, ev := range remaining[day] {
			if err := x.Apply(ev); err != nil {
				return plan, err
			}
		}
		if v, ok := x.Snapshot().LastMessageByDay[day]; ok {
			v := v
			dayMax[day] = &v
		} else {
			dayMax[day] = nil
		}
	}

	removedSet := make(map[string]struct{}, len(plan.removedIDs))
	for _, id := range plan.removedIDs {
		removedSet[id] = struct{}{}
	}
	moves := map[string][]fold.Move{}
	for _, sku := range fold.AffectedSKUs(removed) {
		mrows, err := tx.Query(ctx, `SELECT event_id, line_no, value FROM sku_moves
			WHERE tenant_id = $1 AND sku_key = $2 ORDER BY occurred_at_ms, event_id, line_no`,
			tenant, sc.Keys().SKUKey(sku))
		if err != nil {
			return plan, fmt.Errorf("store: read sku moves: %w", err)
		}
		list := []fold.Move{}
		for mrows.Next() {
			var id string
			var line int
			var sealed []byte
			if err := mrows.Scan(&id, &line, &sealed); err != nil {
				mrows.Close()
				return plan, fmt.Errorf("store: scan sku move: %w", err)
			}
			if _, gone := removedSet[id]; gone {
				continue
			}
			m, err := openSKUMove(sc, id, line, sealed)
			if err != nil {
				mrows.Close()
				return plan, err
			}
			list = append(list, m)
		}
		mrows.Close()
		if err := mrows.Err(); err != nil {
			return plan, fmt.Errorf("store: read sku moves: %w", err)
		}
		moves[sku] = list
	}

	var coldUntil int64
	if err := tx.QueryRow(ctx, `SELECT cold_until, snapshot_object FROM tenant_cold WHERE tenant_id = $1`,
		tenant).Scan(&coldUntil, &plan.oldSnapshot); err != nil {
		return plan, fmt.Errorf("store: read cold state: %w", err)
	}
	if plan.oldSnapshot == nil {
		return plan, fmt.Errorf("store: customer has cold days but the tenant has no snapshot")
	}
	snap, err := s.getSnapshot(ctx, sc, *plan.oldSnapshot)
	if err != nil {
		return plan, err
	}
	next := fold.RemoveCustomer(snap, hex.EncodeToString(customerKey), removed, moves, dayMax)
	plan.newSnapshot, err = s.putSnapshot(ctx, sc, coldUntil, next)
	if err != nil {
		return plan, err
	}
	return plan, nil
}

// EraseTenant marks the tenant erased and deletes its key, events and
// tombstones, and its cold-tier index rows in one transaction, then drops its cached keys. It is idempotent.
func (s *Store) EraseTenant(ctx context.Context, tenantID string) error {
	start := time.Now()
	err := s.eraseTenant(ctx, tenantID)
	if err == nil {
		metrics.ErasureSeconds.WithLabelValues("tenant").Observe(time.Since(start).Seconds())
	}
	return err
}

func (s *Store) eraseTenant(ctx context.Context, tenantID string) error {
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.ReadCommitted})
	if err != nil {
		return fmt.Errorf("store: erase tenant begin: %w", err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck
	// Lock order: cold-writer, then tenant status.
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock($1)`, lockKey("cold-writer", []byte(tenantID))); err != nil {
		return fmt.Errorf("store: cold-writer lock: %w", err)
	}
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
		`DELETE FROM tenant_cold WHERE tenant_id = $1`,
		`DELETE FROM cold_manifest WHERE tenant_id = $1`,
		`DELETE FROM customer_days WHERE tenant_id = $1`,
		`DELETE FROM sku_moves WHERE tenant_id = $1`,
	} {
		if _, err := tx.Exec(ctx, q, tenantID); err != nil {
			return fmt.Errorf("store: erase tenant data: %w", err)
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("store: erase tenant commit: %w", err)
	}
	s.forgetTenant(tenantID)
	return nil
}
