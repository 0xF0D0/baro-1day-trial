package store

import (
	"context"

	"backbone/internal/canon"
	"backbone/internal/fold"
)

// LockKey exposes lockKey to the external store tests.
func LockKey(kind string, parts ...[]byte) int64 { return lockKey(kind, parts...) }

// Test-only access to the object codec helpers.

func (s *Store) PutBucket(ctx context.Context, sc Scope, day int64, events []canon.Event) (string, error) {
	return s.putBucket(ctx, sc, day, events)
}

func (s *Store) GetBucket(ctx context.Context, sc Scope, name string) ([]canon.Event, error) {
	return s.getBucket(ctx, sc, name)
}

func (s *Store) PutSnapshot(ctx context.Context, sc Scope, coldUntil int64, snap fold.Snapshot) (string, error) {
	return s.putSnapshot(ctx, sc, coldUntil, snap)
}

func (s *Store) GetSnapshot(ctx context.Context, sc Scope, name string) (fold.Snapshot, error) {
	return s.getSnapshot(ctx, sc, name)
}

// SetColdUntil sets the tenant's cold_until directly, without a flush.
func (s *Store) SetColdUntil(ctx context.Context, tenant string, coldUntil int64) error {
	_, err := s.pool.Exec(ctx, `UPDATE tenant_cold SET cold_until = $2 WHERE tenant_id = $1`, tenant, coldUntil)
	return err
}

// AddManifestBucket writes a bucket with putBucket and records it in
// cold_manifest, without a flush.
func (s *Store) AddManifestBucket(ctx context.Context, sc Scope, day int64, events []canon.Event) error {
	name, err := s.putBucket(ctx, sc, day, events)
	if err != nil {
		return err
	}
	_, err = s.pool.Exec(ctx,
		`INSERT INTO cold_manifest (tenant_id, day, object, events, bytes) VALUES ($1, $2, $3, $4, 0)`,
		sc.tenantID, day, name, len(events))
	return err
}

// SetFlushAfterRead installs a hook that FlushDay calls between reading the
// day's rows and writing the objects. Pass nil to remove it.
func SetFlushAfterRead(f func()) { flushAfterRead = f }

// SealSKUMove and OpenSKUMove expose the sku_moves value codec.
func SealSKUMove(sc Scope, eventID string, lineNo int, m fold.Move) ([]byte, error) {
	return sealSKUMove(sc, eventID, lineNo, m)
}

func OpenSKUMove(sc Scope, eventID string, lineNo int, sealed []byte) (fold.Move, error) {
	return openSKUMove(sc, eventID, lineNo, sealed)
}
