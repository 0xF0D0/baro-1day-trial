package store

import (
	"context"
	"sync"
	"time"

	"backbone/internal/fold"
	"backbone/internal/metrics"
)

// snapEntry is one cached snapshot. The snapshot object is immutable and has a
// unique name, so a match on the name means the content is the same.
type snapEntry struct {
	object   string
	snap     fold.Snapshot
	cachedAt time.Time
}

// snapCache keeps the newest decrypted snapshot per tenant. Cached snapshots
// are shared read-only: fold.Restore copies their contents.
type snapCache struct {
	mu      sync.Mutex
	ttl     time.Duration
	now     func() time.Time
	entries map[string]snapEntry
}

func newSnapCache() *snapCache {
	return &snapCache{now: time.Now, entries: map[string]snapEntry{}}
}

func (c *snapCache) get(tenant, object string) (fold.Snapshot, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.ttl <= 0 {
		return fold.Snapshot{}, false
	}
	e, ok := c.entries[tenant]
	if !ok || e.object != object || c.now().Sub(e.cachedAt) >= c.ttl {
		return fold.Snapshot{}, false
	}
	return e.snap, true
}

func (c *snapCache) put(tenant, object string, snap fold.Snapshot) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.ttl <= 0 {
		return
	}
	c.entries[tenant] = snapEntry{object: object, snap: snap, cachedAt: c.now()}
}

func (c *snapCache) drop(tenant string) {
	c.mu.Lock()
	delete(c.entries, tenant)
	c.mu.Unlock()
}

// SetSnapshotCacheTTL turns the snapshot cache on with the given entry
// lifetime; 0 turns it off and empties it. Call it once after Open.
func (s *Store) SetSnapshotCacheTTL(ttl time.Duration) {
	s.snaps.mu.Lock()
	defer s.snaps.mu.Unlock()
	s.snaps.ttl = ttl
	if ttl <= 0 {
		s.snaps.entries = map[string]snapEntry{}
	}
}

// cachedSnapshot returns the snapshot object through the cache and reports
// whether an object had to be read. The result must not be modified.
func (s *Store) cachedSnapshot(ctx context.Context, sc Scope, object string) (fold.Snapshot, bool, error) {
	tenant := sc.TenantID()
	if snap, ok := s.snaps.get(tenant, object); ok {
		metrics.SnapshotCacheTotal.WithLabelValues("hit").Inc()
		return snap, false, nil
	}
	metrics.SnapshotCacheTotal.WithLabelValues("miss").Inc()
	snap, err := s.getSnapshot(ctx, sc, object)
	if err != nil {
		return fold.Snapshot{}, true, err
	}
	s.snaps.put(tenant, object, snap)
	return snap, true, nil
}
