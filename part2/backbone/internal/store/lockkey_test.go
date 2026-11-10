package store

import "testing"

func TestLockKey(t *testing.T) {
	if lockKey("migrate") != lockKey("migrate") {
		t.Fatal("not deterministic")
	}
	if lockKey("a", []byte("bc")) == lockKey("a", []byte("b"), []byte("c")) {
		t.Fatal("parts must be length-prefixed")
	}
}
