package store

import (
	"context"
	"encoding/json"
	"fmt"
	"slices"

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
}

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
		return a, nil
	}
	sc, err := s.Scope(ctx, tenantID)
	if err != nil {
		return a, err
	}

	var snapshot *string
	if err := tx.QueryRow(ctx, `SELECT dirty, snapshot_object FROM tenant_cold WHERE tenant_id = $1`,
		tenantID).Scan(&a.Dirty, &snapshot); err != nil {
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

	manifest, err := manifestObjects(ctx, tx, `SELECT object FROM cold_manifest WHERE tenant_id = $1 ORDER BY day`, tenantID)
	if err != nil {
		return a, err
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
	}
	var snap fold.Snapshot
	if snapshot != nil {
		if snap, err = s.getSnapshot(ctx, sc, *snapshot); err != nil {
			a.BadPointers = append(a.BadPointers, *snapshot)
		}
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
