package store

import (
	"context"
	"errors"
	"fmt"
	"sort"

	"backbone/internal/canon"
	"backbone/internal/fold"

	"github.com/jackc/pgx/v5"
)

// rebuildAfterRead is a test hook called after Rebuild has read the late rows
// and before it writes any object. It is set only from export_test.go.
var rebuildAfterRead func()

// Rebuild folds the tenant's late hot rows (older than cold_until) into the
// cold day buckets, writes a new snapshot and replaces the tenant's index rows,
// so a dirty tenant returns to the fast read path. It reports whether it
// rebuilt; it does nothing for an erased or clean tenant. Rows that arrive
// while it runs stay in hot and leave the tenant dirty for the next rebuild.
func (s *Store) Rebuild(ctx context.Context, tenantID string) (bool, error) {
	sc, err := s.Scope(ctx, tenantID)
	if errors.Is(err, ErrTenantErased) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.ReadCommitted})
	if err != nil {
		return false, fmt.Errorf("store: rebuild begin: %w", err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock($1)`, lockKey("cold-writer", []byte(tenantID))); err != nil {
		return false, fmt.Errorf("store: cold-writer lock: %w", err)
	}
	status, err := tenantStatus(ctx, tx, tenantID)
	if err != nil {
		return false, err
	}
	if status == "erased" {
		s.forgetKeys(tenantID)
		return false, nil
	}
	var coldUntil int64
	var dirty bool
	var oldSnapshot *string
	if err := tx.QueryRow(ctx, `SELECT cold_until, dirty, snapshot_object FROM tenant_cold WHERE tenant_id = $1`,
		tenantID).Scan(&coldUntil, &dirty, &oldSnapshot); err != nil {
		return false, fmt.Errorf("store: read cold state: %w", err)
	}
	if !dirty {
		return false, nil
	}

	// The late rows, in key order. Their IDs are exactly the rows deleted at
	// commit; a row that arrives later is not read and so not deleted.
	var late []canon.Event
	if err := scanHot(ctx, tx, sc, `SELECT event_id, payload FROM hot_events
		WHERE tenant_id = $1 AND occurred_at_ms < $2 ORDER BY occurred_at_ms, event_id`,
		[]any{tenantID, coldUntil}, func(e canon.Event) error { late = append(late, e); return nil }); err != nil {
		return false, err
	}
	lateIDs := make([]string, 0, len(late))
	lateByDay := map[int64][]canon.Event{}
	for _, e := range late {
		lateIDs = append(lateIDs, e.EventID)
		d := fold.Day(e.OccurredAtMs)
		lateByDay[d] = append(lateByDay[d], e)
	}

	// Existing buckets, by day.
	mrows, err := tx.Query(ctx, `SELECT day, object FROM cold_manifest WHERE tenant_id = $1 ORDER BY day`, tenantID)
	if err != nil {
		return false, fmt.Errorf("store: read manifest: %w", err)
	}
	var days []int64
	oldObject := map[int64]string{}
	for mrows.Next() {
		var d int64
		var o string
		if err := mrows.Scan(&d, &o); err != nil {
			mrows.Close()
			return false, fmt.Errorf("store: scan manifest: %w", err)
		}
		days = append(days, d)
		oldObject[d] = o
	}
	mrows.Close()
	if err := mrows.Err(); err != nil {
		return false, fmt.Errorf("store: read manifest: %w", err)
	}
	for d := range lateByDay {
		if _, ok := oldObject[d]; !ok {
			days = append(days, d)
		}
	}
	sort.Slice(days, func(i, j int) bool { return days[i] < days[j] })

	// Merge the late rows into their days and fold every bucket in day order.
	// Events within a day are in canonical order once sorted.
	state := fold.New(tenantID, sc.keys.CustomerKeyHex)
	var moves []moveRow
	var pairs []customerDay
	type rewritten struct {
		object string
		events int
		bytes  int
	}
	rewrites := map[int64]rewritten{}
	var replaced []string
	merged := map[int64][]canon.Event{}
	for _, d := range days {
		var events []canon.Event
		if obj, ok := oldObject[d]; ok {
			events, err = s.getBucket(ctx, sc, obj)
			if err != nil {
				return false, err
			}
		}
		if add := lateByDay[d]; len(add) > 0 {
			have := make(map[string]struct{}, len(events))
			for _, e := range events {
				have[e.EventID] = struct{}{}
			}
			grew := false
			for _, e := range add {
				if _, dup := have[e.EventID]; dup {
					continue
				}
				events = append(events, e)
				grew = true
			}
			if grew {
				merged[d] = events
			}
		}
		canon.Sort(events)
		m, p, err := buildIndexRows(sc, state, events)
		if err != nil {
			return false, err
		}
		moves = append(moves, m...)
		pairs = append(pairs, p...)
	}
	if rebuildAfterRead != nil {
		rebuildAfterRead()
	}

	// New immutable objects, written before the commit that makes them current.
	for d, events := range merged {
		name, size, err := s.putBucket(ctx, sc, d, events)
		if err != nil {
			return false, err
		}
		rewrites[d] = rewritten{name, len(events), size}
		if old, ok := oldObject[d]; ok {
			replaced = append(replaced, old)
		}
	}
	snapshot, err := s.putSnapshot(ctx, sc, coldUntil, state.Snapshot())
	if err != nil {
		return false, err
	}
	if oldSnapshot != nil {
		replaced = append(replaced, *oldSnapshot)
	}

	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock_shared($1)`, lockKey("tenant-status", []byte(tenantID))); err != nil {
		return false, fmt.Errorf("store: tenant status lock: %w", err)
	}
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock($1)`, lockKey("cold-commit", []byte(tenantID))); err != nil {
		return false, fmt.Errorf("store: cold-commit lock: %w", err)
	}
	status, err = tenantStatus(ctx, tx, tenantID)
	if err != nil {
		return false, err
	}
	if status == "erased" {
		s.forgetKeys(tenantID)
		return false, nil
	}
	for d, r := range rewrites {
		if _, err := tx.Exec(ctx, `INSERT INTO cold_manifest (tenant_id, day, object, events, bytes)
			VALUES ($1, $2, $3, $4, $5)
			ON CONFLICT (tenant_id, day) DO UPDATE SET object = $3, events = $4, bytes = $5`,
			tenantID, d, r.object, r.events, r.bytes); err != nil {
			return false, fmt.Errorf("store: upsert manifest: %w", err)
		}
	}
	for _, o := range replaced {
		if _, err := tx.Exec(ctx, `INSERT INTO garbage (object, tenant_id) VALUES ($1, $2) ON CONFLICT DO NOTHING`,
			o, tenantID); err != nil {
			return false, fmt.Errorf("store: insert garbage: %w", err)
		}
	}
	if _, err := tx.Exec(ctx, `UPDATE tenant_cold SET snapshot_object = $2 WHERE tenant_id = $1`,
		tenantID, snapshot); err != nil {
		return false, fmt.Errorf("store: update snapshot pointer: %w", err)
	}
	for _, q := range []string{
		`DELETE FROM customer_days WHERE tenant_id = $1`,
		`DELETE FROM sku_moves WHERE tenant_id = $1`,
	} {
		if _, err := tx.Exec(ctx, q, tenantID); err != nil {
			return false, fmt.Errorf("store: clear index rows: %w", err)
		}
	}
	dayRows := make([][]any, len(pairs))
	for i, p := range pairs {
		dayRows[i] = []any{tenantID, p.key, p.day}
	}
	if _, err := tx.CopyFrom(ctx, pgx.Identifier{"customer_days"},
		[]string{"tenant_id", "customer_key", "day"}, pgx.CopyFromRows(dayRows)); err != nil {
		return false, fmt.Errorf("store: copy customer_days: %w", err)
	}
	moveRows := make([][]any, len(moves))
	for i, m := range moves {
		moveRows[i] = []any{tenantID, m.skuKey, m.ms, m.eventID, m.lineNo, m.sealed}
	}
	if _, err := tx.CopyFrom(ctx, pgx.Identifier{"sku_moves"},
		[]string{"tenant_id", "sku_key", "occurred_at_ms", "event_id", "line_no", "value"},
		pgx.CopyFromRows(moveRows)); err != nil {
		return false, fmt.Errorf("store: copy sku_moves: %w", err)
	}
	if _, err := tx.Exec(ctx, `DELETE FROM hot_events WHERE tenant_id = $1 AND event_id = ANY($2)`,
		tenantID, lateIDs); err != nil {
		return false, fmt.Errorf("store: delete late rows: %w", err)
	}
	if _, err := tx.Exec(ctx, `UPDATE tenant_cold SET dirty = EXISTS
		(SELECT 1 FROM hot_events WHERE tenant_id = $1 AND occurred_at_ms < $2) WHERE tenant_id = $1`,
		tenantID, coldUntil); err != nil {
		return false, fmt.Errorf("store: set dirty: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return false, fmt.Errorf("store: rebuild commit: %w", err)
	}
	return true, nil
}
