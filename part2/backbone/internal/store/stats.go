package store

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5"
)

// Stats is a point-in-time storage summary for the storage gauges.
type Stats struct {
	HotEvents, HotBytes, ColdEvents, ColdBytes      int64
	CustomerDaysBytes, SKUMovesBytes                int64
	PendingTombstones, GarbageObjects, DirtyTenants int64
}

// Stats summarizes the whole store from one REPEATABLE READ READ ONLY
// transaction, so the numbers agree with each other.
func (s *Store) Stats(ctx context.Context) (Stats, error) {
	var st Stats
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.RepeatableRead, AccessMode: pgx.ReadOnly})
	if err != nil {
		return st, fmt.Errorf("store: stats begin: %w", err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck
	err = tx.QueryRow(ctx, `SELECT
		(SELECT count(*) FROM hot_events),
		pg_total_relation_size('hot_events'),
		(SELECT coalesce(sum(events), 0) FROM cold_manifest)::bigint,
		(SELECT coalesce(sum(bytes), 0) FROM cold_manifest)::bigint,
		pg_total_relation_size('customer_days'),
		pg_total_relation_size('sku_moves'),
		(SELECT count(*) FROM tombstones WHERE status = 'pending'),
		(SELECT count(*) FROM garbage),
		(SELECT count(*) FROM tenant_cold WHERE dirty)`).Scan(
		&st.HotEvents, &st.HotBytes, &st.ColdEvents, &st.ColdBytes,
		&st.CustomerDaysBytes, &st.SKUMovesBytes,
		&st.PendingTombstones, &st.GarbageObjects, &st.DirtyTenants)
	if err != nil {
		return Stats{}, fmt.Errorf("store: stats: %w", err)
	}
	return st, nil
}
