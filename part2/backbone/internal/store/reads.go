package store

import (
	"context"
	"fmt"
	"time"

	"backbone/internal/canon"
	"backbone/internal/fold"
	"backbone/internal/metrics"

	"github.com/jackc/pgx/v5"
)

// beginRead opens a REPEATABLE READ READ ONLY transaction whose first
// statement reads the tenant status, then reads the tenant's cold state.
func (s *Store) beginRead(ctx context.Context, sc Scope) (tx pgx.Tx, coldUntil int64, dirty bool, snapshot *string, err error) {
	tenant := sc.TenantID()
	tx, err = s.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.RepeatableRead, AccessMode: pgx.ReadOnly})
	if err != nil {
		return nil, 0, false, nil, fmt.Errorf("store: read begin: %w", err)
	}
	fail := func(e error) (pgx.Tx, int64, bool, *string, error) {
		_ = tx.Rollback(ctx)
		return nil, 0, false, nil, e
	}
	status, err := tenantStatus(ctx, tx, tenant)
	if err != nil {
		return fail(err)
	}
	if status == "erased" {
		s.forgetTenant(tenant)
		return fail(ErrTenantErased)
	}
	if err := tx.QueryRow(ctx, `SELECT cold_until, dirty, snapshot_object FROM tenant_cold WHERE tenant_id = $1`,
		tenant).Scan(&coldUntil, &dirty, &snapshot); err != nil {
		return fail(fmt.Errorf("store: read cold state: %w", err))
	}
	return tx, coldUntil, dirty, snapshot, nil
}

// State returns the tenant's folded state across both tiers. Unless the tenant
// is dirty it restores the snapshot and applies the hot rows in key order; a
// dirty tenant folds every manifest bucket and every hot row.
func (s *Store) State(ctx context.Context, sc Scope) (fold.Result, error) {
	start := time.Now()
	res, readCold, err := s.state(ctx, sc)
	if err == nil {
		observeRead("state", readCold, start)
	}
	return res, err
}

// observeRead records a successful read; tier is cold when it read at least
// one object.
func observeRead(kind string, readCold bool, start time.Time) {
	tier := "hot"
	if readCold {
		tier = "cold"
	}
	metrics.ReadSeconds.WithLabelValues(kind, tier).Observe(time.Since(start).Seconds())
}

func (s *Store) state(ctx context.Context, sc Scope) (fold.Result, bool, error) {
	tenant := sc.TenantID()
	tx, _, dirty, snapshot, err := s.beginRead(ctx, sc)
	if err != nil {
		return fold.Result{}, false, err
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	hot := []canon.Event{}
	if err := scanHot(ctx, tx, sc, `SELECT event_id, payload FROM hot_events WHERE tenant_id = $1
		ORDER BY occurred_at_ms, event_id`, []any{tenant},
		func(e canon.Event) error { hot = append(hot, e); return nil }); err != nil {
		return fold.Result{}, false, err
	}

	if dirty {
		objects, err := manifestObjects(ctx, tx, `SELECT object FROM cold_manifest WHERE tenant_id = $1 ORDER BY day`, tenant)
		if err != nil {
			return fold.Result{}, false, err
		}
		all := hot
		for _, name := range objects {
			b, err := s.getBucket(ctx, sc, name)
			if err != nil {
				return fold.Result{}, false, err
			}
			all = append(all, b...)
		}
		res, err := fold.Fold(tenant, all, sc.Keys().CustomerKeyHex)
		return res, len(objects) > 0, err
	}

	var st *fold.State
	readSnapshot := false
	if snapshot == nil {
		st = fold.New(tenant, sc.Keys().CustomerKeyHex)
	} else {
		snap, read, err := s.cachedSnapshot(ctx, sc, *snapshot)
		if err != nil {
			return fold.Result{}, false, err
		}
		readSnapshot = read
		st = fold.Restore(tenant, sc.Keys().CustomerKeyHex, snap)
	}
	for _, e := range hot {
		if err := st.Apply(e); err != nil {
			return fold.Result{}, false, err
		}
	}
	return st.Result(), readSnapshot, nil
}

// manifestObjects returns the object names selected by a query whose first
// column is the object name.
func manifestObjects(ctx context.Context, tx pgx.Tx, query string, args ...any) ([]string, error) {
	rows, err := tx.Query(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("store: read cold manifest: %w", err)
	}
	defer rows.Close()
	var out []string
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			return nil, fmt.Errorf("store: scan cold manifest: %w", err)
		}
		out = append(out, name)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("store: read cold manifest: %w", err)
	}
	return out, nil
}

// Range returns events with fromMs <= occurred_at_ms < toMs and a key strictly
// greater than after (when non-nil), in key order, at most limit of them. It
// merges cold buckets (days before cold_until) with hot rows, which include
// any late events still waiting for a rebuild.
func (s *Store) Range(ctx context.Context, sc Scope, fromMs, toMs int64, after *Key, limit int) ([]canon.Event, error) {
	start := time.Now()
	out, readCold, err := s.rangeRead(ctx, sc, fromMs, toMs, after, limit)
	if err == nil {
		observeRead("range", readCold, start)
	}
	return out, err
}

func (s *Store) rangeRead(ctx context.Context, sc Scope, fromMs, toMs int64, after *Key, limit int) ([]canon.Event, bool, error) {
	tenant := sc.TenantID()
	tx, coldUntil, _, _, err := s.beginRead(ctx, sc)
	if err != nil {
		return nil, false, err
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	afterMs, afterID := int64(-1<<63), ""
	if after != nil {
		afterMs, afterID = after.OccurredAtMs, after.EventID
	}
	merged := []canon.Event{}
	if toMs <= fromMs || limit < 1 {
		return merged, false, nil
	}

	hot := []canon.Event{}
	if err := scanHot(ctx, tx, sc, `SELECT event_id, payload FROM hot_events
		WHERE tenant_id = $1 AND occurred_at_ms >= $2 AND occurred_at_ms < $3
		  AND (occurred_at_ms, event_id) > ($4, $5::text COLLATE "C")
		ORDER BY occurred_at_ms, event_id LIMIT $6`,
		[]any{tenant, fromMs, toMs, afterMs, afterID, limit},
		func(e canon.Event) error { hot = append(hot, e); return nil }); err != nil {
		return nil, false, err
	}

	// Days of cold buckets that can hold events in the range: from the day of
	// fromMs (or of after, whichever is later) up to the last day before cold_until.
	firstDay := fold.Day(fromMs)
	if after != nil {
		firstDay = max(firstDay, fold.Day(after.OccurredAtMs))
	}
	lastDay := min(fold.Day(toMs-1), fold.Day(coldUntil)-1)
	cold := []canon.Event{}
	readCold := false
	if firstDay <= lastDay {
		objects, err := manifestObjects(ctx, tx, `SELECT object FROM cold_manifest
			WHERE tenant_id = $1 AND day >= $2 AND day <= $3 ORDER BY day`, tenant, firstDay, lastDay)
		if err != nil {
			return nil, false, err
		}
		readCold = len(objects) > 0
		for _, name := range objects {
			b, err := s.getBucket(ctx, sc, name)
			if err != nil {
				return nil, false, err
			}
			for _, e := range b {
				if e.OccurredAtMs < fromMs || e.OccurredAtMs >= toMs {
					continue
				}
				if after != nil && !canon.Less(canon.Event{OccurredAtMs: afterMs, EventID: afterID}, e) {
					continue
				}
				cold = append(cold, e)
			}
			if len(cold) >= limit {
				break
			}
		}
	}

	merged = append(merged, cold...)
	merged = append(merged, hot...)
	canon.Sort(merged)
	if len(merged) > limit {
		merged = merged[:limit]
	}
	return merged, readCold, nil
}
