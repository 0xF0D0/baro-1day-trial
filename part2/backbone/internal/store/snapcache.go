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
	stop    chan struct{} // closes the janitor; nil when none runs
	done    chan struct{}
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

// sweep deletes every entry older than the TTL.
func (c *snapCache) sweep() {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.ttl <= 0 {
		return
	}
	now := c.now()
	for k, e := range c.entries {
		if now.Sub(e.cachedAt) >= c.ttl {
			delete(c.entries, k)
		}
	}
}

// stopJanitor stops the janitor goroutine, if any, and waits for it.
func (c *snapCache) stopJanitor() {
	c.mu.Lock()
	stop, done := c.stop, c.done
	c.stop, c.done = nil, nil
	c.mu.Unlock()
	if stop != nil {
		close(stop)
		<-done
	}
}

func (c *snapCache) startJanitor(ttl time.Duration) {
	every := ttl / 4
	if every > time.Minute {
		every = time.Minute
	}
	if every <= 0 {
		every = time.Millisecond
	}
	stop, done := make(chan struct{}), make(chan struct{})
	c.mu.Lock()
	c.stop, c.done = stop, done
	c.mu.Unlock()
	go func() {
		defer close(done)
		t := time.NewTicker(every)
		defer t.Stop()
		for {
			select {
			case <-stop:
				return
			case <-t.C:
				c.sweep()
			}
		}
	}()
}

// SetSnapshotCacheTTL turns the snapshot cache on with the given entry
// lifetime; 0 turns it off and empties it. A positive TTL starts a janitor
// that deletes expired entries, replacing any earlier one; Close stops it.
func (s *Store) SetSnapshotCacheTTL(ttl time.Duration) {
	s.snaps.stopJanitor()
	s.snaps.mu.Lock()
	s.snaps.ttl = ttl
	if ttl <= 0 {
		s.snaps.entries = map[string]snapEntry{}
	}
	s.snaps.mu.Unlock()
	if ttl > 0 {
		s.snaps.startJanitor(ttl)
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
