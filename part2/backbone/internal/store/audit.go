package store

import (
	"context"
	"encoding/json"
	"fmt"
	"slices"
	"strconv"

	"backbone/internal/canon"
	"backbone/internal/fold"

	"github.com/jackc/pgx/v5"
)

// Audit is what one tenant's storage holds, for the crash checker.
type Audit struct {
	Erased       bool
	Dirty        bool
	HotIDs       []string // event IDs in hot_events
	ColdIDs      []string // event IDs in the manifest's buckets, one entry per occurrence
	BadPointers  []string // manifest or snapshot objects that are missing or fail to open
	Unreferenced []string // objects under "<tenant>/" that neither the snapshot pointer, the manifest nor garbage references
	GarbageRows  int
	StateMatches bool // fold.Fold over every cold and hot event equals State (snapshot + hot)

	// IndexMatches: the tenant's customer_days and sku_moves rows equal what
	// buildIndexRows produces over every manifest bucket in day order. False
	// when BadPointers is not empty.
	IndexMatches bool
	// TierViolations names the broken tier invariants (fixed messages, no
	// customer data).
	TierViolations []string
}

const (
	violHotBelowCold = "hot row below cold_until in a tenant that is not dirty"
	violDayPastCold  = "manifest day ends after cold_until"
	violSnapshotCold = "snapshot cold-until differs from tenant_cold.cold_until"
)

// Audit reads the tenant's storage in one REPEATABLE READ READ ONLY
// transaction and takes no locks, so it is meant for a quiet system.
func (s *Store) Audit(ctx context.Context, tenantID string) (Audit, error) {
	var a Audit
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.RepeatableRead, AccessMode: pgx.ReadOnly})
	if err != nil {
		return a, fmt.Errorf("store: audit begin: %w", err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	status, err := tenantStatus(ctx, tx, tenantID)
	if err != nil {
		return a, err
	}
	if status == "erased" {
		names, err := s.objects.List(ctx, tenantID+"/")
		if err != nil {
			return a, err
		}
		a.Erased = true
		a.Unreferenced = names
		a.StateMatches = true
		a.IndexMatches = true
		return a, nil
	}
	sc, err := s.Scope(ctx, tenantID)
	if err != nil {
		return a, err
	}

	var snapshot *string
	var coldUntil int64
	if err := tx.QueryRow(ctx, `SELECT dirty, snapshot_object, cold_until FROM tenant_cold WHERE tenant_id = $1`,
		tenantID).Scan(&a.Dirty, &snapshot, &coldUntil); err != nil {
		return a, fmt.Errorf("store: audit cold state: %w", err)
	}

	hot := []canon.Event{}
	if err := scanHot(ctx, tx, sc, `SELECT event_id, payload FROM hot_events WHERE tenant_id = $1
		ORDER BY occurred_at_ms, event_id`, []any{tenantID},
		func(e canon.Event) error { hot = append(hot, e); return nil }); err != nil {
		return a, err
	}
	for _, e := range hot {
		a.HotIDs = append(a.HotIDs, e.EventID)
	}

	var manifest []string
	var manifestDays []int64
	mrows, err := tx.Query(ctx, `SELECT day, object FROM cold_manifest WHERE tenant_id = $1 ORDER BY day`, tenantID)
	if err != nil {
		return a, fmt.Errorf("store: audit manifest: %w", err)
	}
	for mrows.Next() {
		var d int64
		var o string
		if err := mrows.Scan(&d, &o); err != nil {
			mrows.Close()
			return a, fmt.Errorf("store: audit manifest: %w", err)
		}
		manifestDays = append(manifestDays, d)
		manifest = append(manifest, o)
	}
	mrows.Close()
	if err := mrows.Err(); err != nil {
		return a, fmt.Errorf("store: audit manifest: %w", err)
	}
	garbage, err := manifestObjects(ctx, tx, `SELECT object FROM garbage WHERE tenant_id = $1`, tenantID)
	if err != nil {
		return a, err
	}
	a.GarbageRows = len(garbage)

	keep := map[string]struct{}{}
	for _, o := range manifest {
		keep[o] = struct{}{}
	}
	for _, o := range garbage {
		keep[o] = struct{}{}
	}
	if snapshot != nil {
		keep[*snapshot] = struct{}{}
	}

	cold := []canon.Event{}
	buckets := make([][]canon.Event, 0, len(manifest))
	for _, name := range manifest {
		b, err := s.getBucket(ctx, sc, name)
		if err != nil {
			a.BadPointers = append(a.BadPointers, name)
			continue
		}
		for _, e := range b {
			a.ColdIDs = append(a.ColdIDs, e.EventID)
		}
		cold = append(cold, b...)
		buckets = append(buckets, b)
	}
	var snap fold.Snapshot
	snapCold := coldUntil
	if snapshot != nil {
		doc, err := s.getSnapshotDoc(ctx, sc, *snapshot)
		if err != nil {
			a.BadPointers = append(a.BadPointers, *snapshot)
		} else {
			snap, snapCold = doc.State, doc.ColdUntil
		}
	}

	// Tier invariants.
	if !a.Dirty {
		for _, e := range hot {
			if e.OccurredAtMs < coldUntil {
				a.TierViolations = append(a.TierViolations, violHotBelowCold)
				break
			}
		}
	}
	for _, d := range manifestDays {
		if (d+1)*msPerDay > coldUntil {
			a.TierViolations = append(a.TierViolations, violDayPastCold)
			break
		}
	}
	if snapCold != coldUntil {
		a.TierViolations = append(a.TierViolations, violSnapshotCold)
	}

	names, err := s.objects.List(ctx, tenantID+"/")
	if err != nil {
		return a, err
	}
	for _, n := range names {
		if _, ok := keep[n]; !ok {
			a.Unreferenced = append(a.Unreferenced, n)
		}
	}

	if len(a.BadPointers) > 0 {
		return a, nil
	}
	if a.IndexMatches, err = indexMatches(ctx, tx, sc, buckets); err != nil {
		return a, err
	}
	want, err := fold.Fold(tenantID, append(append([]canon.Event{}, hot...), cold...), sc.Keys().CustomerKeyHex)
	if err != nil {
		return a, err
	}
	var got fold.Result
	if a.Dirty {
		got = want // State folds every bucket and hot row when dirty
	} else {
		st := fold.New(tenantID, sc.Keys().CustomerKeyHex)
		if snapshot != nil {
			st = fold.Restore(tenantID, sc.Keys().CustomerKeyHex, snap)
		}
		for _, e := range hot {
			if err := st.Apply(e); err != nil {
				return a, err
			}
		}
		got = st.Result()
	}
	wj, err := json.Marshal(want)
	if err != nil {
		return a, err
	}
	gj, err := json.Marshal(got)
	if err != nil {
		return a, err
	}
	a.StateMatches = slices.Equal(wj, gj)
	return a, nil
}

// indexMatches reports whether the tenant's customer_days and sku_moves rows
// equal what buildIndexRows produces over the buckets in day order, folding
// with a fresh state exactly as Rebuild does.
func indexMatches(ctx context.Context, tx pgx.Tx, sc Scope, buckets [][]canon.Event) (bool, error) {
	tenantID := sc.tenantID
	state := fold.New(tenantID, sc.keys.CustomerKeyHex)
	type moveKey struct {
		sku     string
		ms      int64
		eventID string
		lineNo  int
	}
	wantMoves := map[moveKey]fold.Move{}
	wantDays := map[string]struct{}{}
	for _, b := range buckets {
		events := append([]canon.Event(nil), b...)
		canon.Sort(events)
		moves, pairs, err := buildIndexRows(sc, state, events)
		if err != nil {
			return false, err
		}
		for _, m := range moves {
			mv, err := openSKUMove(sc, m.eventID, m.lineNo, m.sealed)
			if err != nil {
				return false, err
			}
			wantMoves[moveKey{string(m.skuKey), m.ms, m.eventID, m.lineNo}] = mv
		}
		for _, p := range pairs {
			wantDays[string(p.key)+"\x00"+strconv.FormatInt(p.day, 10)] = struct{}{}
		}
	}

	rows, err := tx.Query(ctx, `SELECT customer_key, day FROM customer_days WHERE tenant_id = $1`, tenantID)
	if err != nil {
		return false, fmt.Errorf("store: audit customer_days: %w", err)
	}
	gotDays := map[string]struct{}{}
	for rows.Next() {
		var k []byte
		var d int64
		if err := rows.Scan(&k, &d); err != nil {
			rows.Close()
			return false, fmt.Errorf("store: audit customer_days: %w", err)
		}
		gotDays[string(k)+"\x00"+strconv.FormatInt(d, 10)] = struct{}{}
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return false, fmt.Errorf("store: audit customer_days: %w", err)
	}
	if len(gotDays) != len(wantDays) {
		return false, nil
	}
	for k := range wantDays {
		if _, ok := gotDays[k]; !ok {
			return false, nil
		}
	}

	rows, err = tx.Query(ctx, `SELECT sku_key, occurred_at_ms, event_id, line_no, value FROM sku_moves WHERE tenant_id = $1`, tenantID)
	if err != nil {
		return false, fmt.Errorf("store: audit sku_moves: %w", err)
	}
	defer rows.Close()
	n := 0
	for rows.Next() {
		var k []byte
		var ms int64
		var id string
		var line int
		var sealed []byte
		if err := rows.Scan(&k, &ms, &id, &line, &sealed); err != nil {
			return false, fmt.Errorf("store: audit sku_moves: %w", err)
		}
		n++
		want, ok := wantMoves[moveKey{string(k), ms, id, line}]
		if !ok {
			return false, nil
		}
		got, err := openSKUMove(sc, id, line, sealed)
		if err != nil || got != want {
			return false, nil
		}
	}
	if err := rows.Err(); err != nil {
		return false, fmt.Errorf("store: audit sku_moves: %w", err)
	}
	return n == len(wantMoves), nil
}
