package store

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"

	"backbone/internal/canon"
	"backbone/internal/cold"
	"backbone/internal/fold"
)

// objectAAD binds a sealed object to its tenant and its (immutable) name.
func objectAAD(tenant, name string) []byte { return []byte(tenant + "\x00" + name) }

// snapshotDoc is the plaintext of a snapshot object.
type snapshotDoc struct {
	Version   string        `json:"version"`
	ColdUntil int64         `json:"cold_until"`
	State     fold.Snapshot `json:"state"`
}

// putBucket seals the day's events (JSON lines in key order) into a new
// immutable object and returns its name and the sealed object's size in bytes.
func (s *Store) putBucket(ctx context.Context, sc Scope, day int64, events []canon.Event) (string, int, error) {
	sorted := append([]canon.Event(nil), events...)
	canon.Sort(sorted)
	var buf bytes.Buffer
	for _, e := range sorted {
		line, err := json.Marshal(e)
		if err != nil {
			return "", 0, fmt.Errorf("store: encode bucket event: %w", err)
		}
		buf.Write(line)
		buf.WriteByte('\n')
	}
	name := cold.ObjectName(sc.tenantID, "bucket", day)
	sealed := sc.keys.Seal(objectAAD(sc.tenantID, name), buf.Bytes())
	if err := s.objects.Put(ctx, name, sealed); err != nil {
		return "", 0, fmt.Errorf("store: put bucket: %w", err)
	}
	return name, len(sealed), nil
}

// getBucket reads and opens a bucket object.
func (s *Store) getBucket(ctx context.Context, sc Scope, name string) ([]canon.Event, error) {
	sealed, err := s.objects.Get(ctx, name)
	if err != nil {
		return nil, fmt.Errorf("store: get bucket: %w", err)
	}
	plain, err := sc.keys.Open(objectAAD(sc.tenantID, name), sealed)
	if err != nil {
		return nil, fmt.Errorf("store: open bucket: %w", err)
	}
	events := []canon.Event{}
	for _, line := range bytes.Split(plain, []byte{'\n'}) {
		if len(line) == 0 {
			continue
		}
		var e canon.Event
		if err := json.Unmarshal(line, &e); err != nil {
			return nil, fmt.Errorf("store: decode bucket event: %w", err)
		}
		events = append(events, e)
	}
	return events, nil
}

// putSnapshot seals a snapshot of the state folded up to coldUntil.
func (s *Store) putSnapshot(ctx context.Context, sc Scope, coldUntil int64, snap fold.Snapshot) (string, error) {
	plain, err := json.Marshal(snapshotDoc{Version: "v1", ColdUntil: coldUntil, State: snap})
	if err != nil {
		return "", fmt.Errorf("store: encode snapshot: %w", err)
	}
	name := cold.ObjectName(sc.tenantID, "snapshot", fold.Day(coldUntil))
	if err := s.objects.Put(ctx, name, sc.keys.Seal(objectAAD(sc.tenantID, name), plain)); err != nil {
		return "", fmt.Errorf("store: put snapshot: %w", err)
	}
	return name, nil
}

// getSnapshot reads and opens a snapshot object.
func (s *Store) getSnapshot(ctx context.Context, sc Scope, name string) (fold.Snapshot, error) {
	sealed, err := s.objects.Get(ctx, name)
	if err != nil {
		return fold.Snapshot{}, fmt.Errorf("store: get snapshot: %w", err)
	}
	plain, err := sc.keys.Open(objectAAD(sc.tenantID, name), sealed)
	if err != nil {
		return fold.Snapshot{}, fmt.Errorf("store: open snapshot: %w", err)
	}
	var doc snapshotDoc
	if err := json.Unmarshal(plain, &doc); err != nil {
		return fold.Snapshot{}, fmt.Errorf("store: decode snapshot: %w", err)
	}
	if doc.Version != "v1" {
		return fold.Snapshot{}, fmt.Errorf("store: unknown snapshot version %q", doc.Version)
	}
	return doc.State, nil
}
