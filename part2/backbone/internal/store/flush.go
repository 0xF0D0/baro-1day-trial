package store

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"time"

	"backbone/internal/canon"
	"backbone/internal/fold"

	"github.com/jackc/pgx/v5"
)

const msPerDay = int64(86_400_000)

// flushAfterRead is a test hook called between reading the day's hot rows and
// writing the objects. It is set only from export_test.go.
var flushAfterRead func()

// skuMoveDoc is the plaintext of one sku_moves value.
type skuMoveDoc struct {
	SKU    string `json:"sku"`
	Kind   string `json:"kind"`
	Amount int64  `json:"amount"`
}

func skuMoveAAD(tenant, eventID string, lineNo int) []byte {
	return []byte(tenant + "\x00" + eventID + "\x00" + strconv.Itoa(lineNo))
}

// sealSKUMove encrypts one inventory movement for the sku_moves table.
func sealSKUMove(sc Scope, eventID string, lineNo int, m fold.Move) ([]byte, error) {
	plain, err := json.Marshal(skuMoveDoc{SKU: m.SKU, Kind: m.Kind, Amount: m.Amount})
	if err != nil {
		return nil, fmt.Errorf("store: encode sku move: %w", err)
	}
	return sc.keys.Seal(skuMoveAAD(sc.tenantID, eventID, lineNo), plain), nil
}

// openSKUMove decrypts a sku_moves value; lineNo is the row's line_no.
func openSKUMove(sc Scope, eventID string, lineNo int, sealed []byte) (fold.Move, error) {
	plain, err := sc.keys.Open(skuMoveAAD(sc.tenantID, eventID, lineNo), sealed)
	if err != nil {
		return fold.Move{}, fmt.Errorf("store: open sku move: %w", err)
	}
	var d skuMoveDoc
	if err := json.Unmarshal(plain, &d); err != nil {
		return fold.Move{}, fmt.Errorf("store: decode sku move: %w", err)
	}
	return fold.Move{SKU: d.SKU, Kind: d.Kind, Amount: d.Amount, LineNo: lineNo}, nil
}

type moveRow struct {
	skuKey  []byte
	ms      int64
	eventID string
	lineNo  int
	sealed  []byte
}

// FlushDay moves the oldest unflushed hot day of the tenant into a cold bucket
// and a new snapshot. It flushes at most one day and reports whether it did.
// The watermark is the rank-th largest hot timestamp minus margin; a day is
// flushed only when the watermark has passed its end.
func (s *Store) FlushDay(ctx context.Context, tenantID string, margin time.Duration, rank int) (bool, error) {
	if rank < 1 {
		rank = 1
	}
	sc, err := s.Scope(ctx, tenantID)
	if errors.Is(err, ErrTenantErased) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.ReadCommitted})
	if err != nil {
		return false, fmt.Errorf("store: flush begin: %w", err)
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
	if dirty {
		return false, nil
	}

	// Watermark: the rank-th largest hot timestamp (or the largest, if fewer).
	var top *int64
	if err := tx.QueryRow(ctx, `SELECT min(t) FROM (SELECT occurred_at_ms AS t FROM hot_events
		WHERE tenant_id = $1 ORDER BY occurred_at_ms DESC LIMIT $2) x`, tenantID, rank).Scan(&top); err != nil {
		return false, fmt.Errorf("store: read watermark: %w", err)
	}
	var first *int64
	if err := tx.QueryRow(ctx, `SELECT min(occurred_at_ms) FROM hot_events
		WHERE tenant_id = $1 AND occurred_at_ms >= $2`, tenantID, coldUntil).Scan(&first); err != nil {
		return false, fmt.Errorf("store: read first hot row: %w", err)
	}
	if top == nil || first == nil {
		return false, nil
	}
	day := fold.Day(*first)
	newColdUntil := (day + 1) * msPerDay
	if *top-margin.Milliseconds() < newColdUntil {
		return false, nil
	}

	// Read the day's hot rows in key order.
	rows, err := tx.Query(ctx, `SELECT event_id, payload FROM hot_events
		WHERE tenant_id = $1 AND occurred_at_ms >= $2 AND occurred_at_ms < $3
		ORDER BY occurred_at_ms, event_id`, tenantID, day*msPerDay, newColdUntil)
	if err != nil {
		return false, fmt.Errorf("store: read day: %w", err)
	}
	var events []canon.Event
	var ids []string
	for rows.Next() {
		var id string
		var sealed []byte
		if err := rows.Scan(&id, &sealed); err != nil {
			rows.Close()
			return false, fmt.Errorf("store: scan day event: %w", err)
		}
		plain, err := sc.keys.Open(eventAAD(tenantID, id), sealed)
		if err != nil {
			rows.Close()
			return false, fmt.Errorf("store: decrypt event: %w", err)
		}
		var ev canon.Event
		if err := json.Unmarshal(plain, &ev); err != nil {
			rows.Close()
			return false, fmt.Errorf("store: decode event: %w", err)
		}
		events = append(events, ev)
		ids = append(ids, id)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return false, fmt.Errorf("store: read day: %w", err)
	}
	if len(events) == 0 {
		return false, nil
	}
	if flushAfterRead != nil {
		flushAfterRead()
	}

	// Fold the day onto the current snapshot and collect the index rows.
	var state *fold.State
	if oldSnapshot != nil {
		snap, err := s.getSnapshot(ctx, sc, *oldSnapshot)
		if err != nil {
			return false, err
		}
		state = fold.Restore(tenantID, sc.keys.CustomerKeyHex, snap)
	} else {
		state = fold.New(tenantID, sc.keys.CustomerKeyHex)
	}
	var moves []moveRow
	customers := map[string][]byte{}
	for _, ev := range events {
		for _, m := range state.ApplyMoves(ev) {
			sealed, err := sealSKUMove(sc, ev.EventID, m.LineNo, m)
			if err != nil {
				return false, err
			}
			moves = append(moves, moveRow{sc.keys.SKUKey(m.SKU), ev.OccurredAtMs, ev.EventID, m.LineNo, sealed})
		}
		if ev.CustomerID != nil {
			k := sc.keys.CustomerKey(*ev.CustomerID)
			customers[string(k)] = k
		}
	}

	// New immutable objects, written before the commit that makes them current.
	bucket, bucketBytes, err := s.putBucket(ctx, sc, day, events)
	if err != nil {
		return false, err
	}
	snapshot, err := s.putSnapshot(ctx, sc, newColdUntil, state.Snapshot())
	if err != nil {
		return false, err
	}

	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock_shared($1)`, lockKey("tenant-status", []byte(tenantID))); err != nil {
		return false, fmt.Errorf("store: tenant status lock: %w", err)
	}
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock($1)`, lockKey("cold-commit", []byte(tenantID))); err != nil {
		return false, fmt.Errorf("store: cold-commit lock: %w", err)
	}
	// Tenant erasure and late ingests can commit while the objects were being
	// written, so re-check before any Postgres write.
	status, err = tenantStatus(ctx, tx, tenantID)
	if err != nil {
		return false, err
	}
	if status == "erased" {
		s.forgetKeys(tenantID)
		return false, nil
	}
	if err := tx.QueryRow(ctx, `SELECT dirty FROM tenant_cold WHERE tenant_id = $1`, tenantID).Scan(&dirty); err != nil {
		return false, fmt.Errorf("store: re-read dirty: %w", err)
	}
	if dirty {
		return false, nil
	}
	if _, err := tx.Exec(ctx,
		`INSERT INTO cold_manifest (tenant_id, day, object, events, bytes) VALUES ($1, $2, $3, $4, $5)`,
		tenantID, day, bucket, len(events), bucketBytes); err != nil {
		return false, fmt.Errorf("store: insert manifest: %w", err)
	}
	if _, err := tx.Exec(ctx,
		`UPDATE tenant_cold SET cold_until = $2, snapshot_object = $3 WHERE tenant_id = $1`,
		tenantID, newColdUntil, snapshot); err != nil {
		return false, fmt.Errorf("store: update cold state: %w", err)
	}
	if oldSnapshot != nil {
		if _, err := tx.Exec(ctx, `INSERT INTO garbage (object, tenant_id) VALUES ($1, $2)`,
			*oldSnapshot, tenantID); err != nil {
			return false, fmt.Errorf("store: insert garbage: %w", err)
		}
	}
	batch := &pgx.Batch{}
	for _, k := range customers {
		batch.Queue(`INSERT INTO customer_days (tenant_id, customer_key, day) VALUES ($1, $2, $3)
			ON CONFLICT DO NOTHING`, tenantID, k, day)
	}
	for _, m := range moves {
		batch.Queue(`INSERT INTO sku_moves (tenant_id, sku_key, occurred_at_ms, event_id, line_no, value)
			VALUES ($1, $2, $3, $4, $5, $6)`, tenantID, m.skuKey, m.ms, m.eventID, m.lineNo, m.sealed)
	}
	if err := tx.SendBatch(ctx, batch).Close(); err != nil {
		return false, fmt.Errorf("store: insert index rows: %w", err)
	}
	if _, err := tx.Exec(ctx, `DELETE FROM hot_events WHERE tenant_id = $1 AND event_id = ANY($2)`,
		tenantID, ids); err != nil {
		return false, fmt.Errorf("store: delete flushed rows: %w", err)
	}
	if _, err := tx.Exec(ctx, `UPDATE tenant_cold SET dirty = EXISTS
		(SELECT 1 FROM hot_events WHERE tenant_id = $1 AND occurred_at_ms < $2) WHERE tenant_id = $1`,
		tenantID, newColdUntil); err != nil {
		return false, fmt.Errorf("store: set dirty: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return false, fmt.Errorf("store: flush commit: %w", err)
	}
	return true, nil
}
