package cold_test

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"regexp"
	"sync"
	"testing"

	"backbone/internal/cold"
	"backbone/internal/cold/coldtest"
)

func TestPutGetRoundTrip(t *testing.T) {
	c := coldtest.New(t)
	ctx := context.Background()
	want := []byte("hello\x00world")
	if err := c.Put(ctx, "t_1/x", want); err != nil {
		t.Fatal(err)
	}
	got, err := c.Get(ctx, "t_1/x")
	if err != nil || !bytes.Equal(got, want) {
		t.Fatalf("got %q, %v", got, err)
	}
	if _, err := c.Get(ctx, "t_1/missing"); !errors.Is(err, cold.ErrNotFound) {
		t.Fatalf("missing object: want ErrNotFound, got %v", err)
	}
}

func TestOpenTwiceSameBucket(t *testing.T) {
	cfg := coldtest.Config(t)
	cfg.Bucket = fmt.Sprintf("race-%s", cold.ObjectName("x", "snapshot", 0)[11:23])
	var wg sync.WaitGroup
	errs := make([]error, 2)
	for i := range errs {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, errs[i] = cold.Open(context.Background(), cfg)
		}()
	}
	wg.Wait()
	for i, err := range errs {
		if err != nil {
			t.Fatalf("open %d: %v", i, err)
		}
	}
}

func TestObjectNameShape(t *testing.T) {
	day := int64(1782864607912 / 86_400_000)
	b := regexp.MustCompile(`^t_1/buckets/2026-07-01/[0-9a-f]{32}\.jsonl\.enc$`)
	s := regexp.MustCompile(`^t_1/snapshot/[0-9a-f]{32}\.json\.enc$`)
	n1, n2 := cold.ObjectName("t_1", "bucket", day), cold.ObjectName("t_1", "bucket", day)
	if !b.MatchString(n1) || n1 == n2 {
		t.Fatalf("bucket names: %q %q", n1, n2)
	}
	s1, s2 := cold.ObjectName("t_1", "snapshot", day), cold.ObjectName("t_1", "snapshot", 0)
	if !s.MatchString(s1) || !s.MatchString(s2) || s1 == s2 {
		t.Fatalf("snapshot names: %q %q", s1, s2)
	}
}
