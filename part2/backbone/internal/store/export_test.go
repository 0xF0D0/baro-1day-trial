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
