// Package coldtest provides a MinIO-backed cold client for tests.
package coldtest

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"backbone/internal/cold"
)

// Config returns a cold.Config with a fresh random bucket name. It skips the test unless
// BACKBONE_TEST_MINIO_ENDPOINT and BACKBONE_TEST_SECRETS_DIR are set.
func Config(t *testing.T) cold.Config {
	t.Helper()
	endpoint := os.Getenv("BACKBONE_TEST_MINIO_ENDPOINT")
	dir := os.Getenv("BACKBONE_TEST_SECRETS_DIR")
	if endpoint == "" || dir == "" {
		t.Skip("BACKBONE_TEST_MINIO_ENDPOINT and BACKBONE_TEST_SECRETS_DIR not set")
	}
	read := func(name string) string {
		b, err := os.ReadFile(filepath.Join(dir, name))
		if err != nil {
			t.Fatalf("read %s: %v", name, err)
		}
		return strings.TrimSpace(string(b))
	}
	var r [8]byte
	if _, err := rand.Read(r[:]); err != nil {
		t.Fatal(err)
	}
	return cold.Config{
		Endpoint:  endpoint,
		AccessKey: read("minio_user"),
		SecretKey: read("minio_password"),
		Bucket:    "test-" + hex.EncodeToString(r[:]),
	}
}

// New opens a client on a fresh random bucket.
func New(t *testing.T) *cold.Client {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	c, err := cold.Open(ctx, Config(t))
	if err != nil {
		t.Fatalf("open cold client: %v", err)
	}
	return c
}
