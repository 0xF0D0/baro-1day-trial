package store

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
)

// SweepResult counts what one tenant sweep did.
type SweepResult struct {
	Tombstones     int // pending customer erasures finished
	GarbageDeleted int // replaced objects deleted after the grace period
	OrphansDeleted int // unreferenced objects deleted (all objects of an erased tenant)
}

// SweepTenant finishes the tenant's pending erasures, deletes replaced objects
// older than grace and deletes objects nothing references. It is the only code
// that deletes cold objects. Deleting is idempotent, and each part takes the
// cold-writer lock in its own transaction.
func (s *Store) SweepTenant(ctx context.Context, tenantID string, grace time.Duration) (SweepResult, error) {
	var res SweepResult
	erased, err := s.sweepPart(ctx, tenantID, &res, func(tx pgx.Tx) error { return nil })
	if err != nil || erased {
		return res, err
	}

	sc, err := s.Scope(ctx, tenantID)
	if errors.Is(err, ErrTenantErased) {
		_, err = s.sweepPart(ctx, tenantID, &res, func(tx pgx.Tx) error { return nil })
		return res, err
	}
	if err != nil {
		return res, err
	}

	// The three passes run independently: a failure in one is kept and does
	// not skip the others. The counts keep accumulating.
	var errs []error
	if err := s.sweepTombstones(ctx, tenantID, sc, &res); err != nil {
		errs = append(errs, err)
	}
	erased, err = s.sweepGarbage(ctx, tenantID, grace, &res)
	if err != nil {
		errs = append(errs, err)
	}
	if erased {
		return res, errors.Join(errs...)
	}
	if err := s.sweepOrphans(ctx, tenantID, &res); err != nil {
		errs = append(errs, err)
	}
	return res, errors.Join(errs...)
}

// sweepTombstones finishes the tenant's pending customer erasures. One failing
// tombstone does not stop the others. finishErasure takes the lock itself.
func (s *Store) sweepTombstones(ctx context.Context, tenantID string, sc Scope, res *SweepResult) error {
	rows, err := s.pool.Query(ctx, `SELECT customer_key FROM tombstones WHERE tenant_id = $1 AND status = 'pending'`, tenantID)
	if err != nil {
		return fmt.Errorf("store: read tombstones: %w", err)
	}
	var keys [][]byte
	for rows.Next() {
		var k []byte
		if err := rows.Scan(&k); err != nil {
			rows.Close()
			return fmt.Errorf("store: scan tombstone: %w", err)
		}
		keys = append(keys, k)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return fmt.Errorf("store: read tombstones: %w", err)
	}
	var errs []error
	for _, k := range keys {
		if err := s.finishErasure(ctx, sc, k); err != nil {
			errs = append(errs, err)
			continue
		}
		res.Tombstones++
	}
	return errors.Join(errs...)
}

// sweepGarbage deletes replaced objects past the grace period: object first,
// then its row.
func (s *Store) sweepGarbage(ctx context.Context, tenantID string, grace time.Duration, res *SweepResult) (erased bool, err error) {
	return s.sweepPart(ctx, tenantID, res, func(tx pgx.Tx) error {
		grows, err := tx.Query(ctx, `SELECT object FROM garbage
			WHERE tenant_id = $1 AND replaced_at < now() - make_interval(secs => $2)`,
			tenantID, grace.Seconds())
		if err != nil {
			return fmt.Errorf("store: read garbage: %w", err)
		}
		var objs []string
		for grows.Next() {
			var o string
			if err := grows.Scan(&o); err != nil {
				grows.Close()
				return fmt.Errorf("store: scan garbage: %w", err)
			}
			objs = append(objs, o)
		}
		grows.Close()
		if err := grows.Err(); err != nil {
			return fmt.Errorf("store: read garbage: %w", err)
		}
		for _, o := range objs {
			if err := s.objects.Delete(ctx, o); err != nil {
				return err
			}
			if _, err := tx.Exec(ctx, `DELETE FROM garbage WHERE object = $1`, o); err != nil {
				return fmt.Errorf("store: delete garbage row: %w", err)
			}
			res.GarbageDeleted++
		}
		return nil
	})
}

// sweepOrphans deletes leftovers of crashed operations: objects in the prefix
// that are neither current nor garbage.
func (s *Store) sweepOrphans(ctx context.Context, tenantID string, res *SweepResult) error {
	_, err := s.sweepPart(ctx, tenantID, res, func(tx pgx.Tx) error {
		keep := map[string]struct{}{}
		for _, q := range []string{
			`SELECT snapshot_object FROM tenant_cold WHERE tenant_id = $1 AND snapshot_object IS NOT NULL`,
			`SELECT object FROM cold_manifest WHERE tenant_id = $1`,
			`SELECT object FROM garbage WHERE tenant_id = $1`,
		} {
			krows, err := tx.Query(ctx, q, tenantID)
			if err != nil {
				return fmt.Errorf("store: read references: %w", err)
			}
			for krows.Next() {
				var o string
				if err := krows.Scan(&o); err != nil {
					krows.Close()
					return fmt.Errorf("store: scan reference: %w", err)
				}
				keep[o] = struct{}{}
			}
			krows.Close()
			if err := krows.Err(); err != nil {
				return fmt.Errorf("store: read references: %w", err)
			}
		}
		names, err := s.objects.List(ctx, tenantID+"/")
		if err != nil {
			return err
		}
		for _, n := range names {
			if _, ok := keep[n]; ok {
				continue
			}
			if err := s.objects.Delete(ctx, n); err != nil {
				return err
			}
			res.OrphansDeleted++
		}
		return nil
	})
	return err
}

// sweepPart runs one part of a sweep in a transaction holding the tenant's
// cold-writer lock. If the tenant is erased (checked after taking the lock) it
// instead deletes every object under the tenant's prefix and its garbage rows,
// counts them as orphans, and reports erased = true without calling fn.
func (s *Store) sweepPart(ctx context.Context, tenantID string, res *SweepResult, fn func(tx pgx.Tx) error) (erased bool, err error) {
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.ReadCommitted})
	if err != nil {
		return false, fmt.Errorf("store: sweep begin: %w", err)
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
		names, err := s.objects.List(ctx, tenantID+"/")
		if err != nil {
			return true, err
		}
		for _, n := range names {
			if err := s.objects.Delete(ctx, n); err != nil {
				return true, err
			}
			res.OrphansDeleted++
		}
		if _, err := tx.Exec(ctx, `DELETE FROM garbage WHERE tenant_id = $1`, tenantID); err != nil {
			return true, fmt.Errorf("store: delete garbage rows: %w", err)
		}
		if err := tx.Commit(ctx); err != nil {
			return true, fmt.Errorf("store: sweep commit: %w", err)
		}
		return true, nil
	}
	if err := fn(tx); err != nil {
		return false, err
	}
	if err := tx.Commit(ctx); err != nil {
		return false, fmt.Errorf("store: sweep commit: %w", err)
	}
	return false, nil
}

// Maintain vacuums the tables that held erased rows, then switches the WAL
// segment and checkpoints, so the erased rows leave the WAL. Each statement
// runs on its own outside any transaction.
func (s *Store) Maintain(ctx context.Context) error {
	for _, t := range []string{"hot_events", "customer_days", "sku_moves", "tenant_keys", "tombstones"} {
		if _, err := s.pool.Exec(ctx, `VACUUM `+t); err != nil {
			return fmt.Errorf("store: vacuum %s: %w", t, err)
		}
	}
	if _, err := s.pool.Exec(ctx, `SELECT pg_switch_wal()`); err != nil {
		return fmt.Errorf("store: switch wal: %w", err)
	}
	if _, err := s.pool.Exec(ctx, `CHECKPOINT`); err != nil {
		return fmt.Errorf("store: checkpoint: %w", err)
	}
	return nil
}
