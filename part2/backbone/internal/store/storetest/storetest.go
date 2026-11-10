// Package storetest builds isolated stores for tests.
package storetest

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"net/url"
	"os"
	"testing"

	"backbone/internal/crypto"
	"backbone/internal/store"

	"github.com/jackc/pgx/v5"
)

const envURL = "BACKBONE_TEST_DATABASE_URL"

// New returns a migrated store on a fresh schema, dropped on cleanup. It
// skips the test when BACKBONE_TEST_DATABASE_URL is unset.
func New(t *testing.T) (*store.Store, *crypto.KEK) {
	t.Helper()
	base := lookup(t)
	ctx := context.Background()

	var rnd [8]byte
	if _, err := rand.Read(rnd[:]); err != nil {
		t.Fatal(err)
	}
	schema := "t_" + hex.EncodeToString(rnd[:])

	admin, err := pgx.Connect(ctx, base)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	if _, err := admin.Exec(ctx, "CREATE SCHEMA "+schema); err != nil {
		admin.Close(ctx)
		t.Fatalf("create schema: %v", err)
	}
	t.Cleanup(func() {
		_, _ = admin.Exec(context.Background(), "DROP SCHEMA "+schema+" CASCADE")
		admin.Close(context.Background())
	})

	u, err := url.Parse(base)
	if err != nil {
		t.Fatal(err)
	}
	q := u.Query()
	q.Set("search_path", schema)
	u.RawQuery = q.Encode()

	keyBytes := make([]byte, 32)
	if _, err := rand.Read(keyBytes); err != nil {
		t.Fatal(err)
	}
	kek, err := crypto.NewKEK(keyBytes)
	if err != nil {
		t.Fatal(err)
	}
	st, err := store.Open(ctx, u.String(), kek)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	t.Cleanup(st.Close)
	if err := st.Migrate(ctx); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	return st, kek
}

// Reopen returns a second store on the same schema, standing in for another
// node or a restart.
func Reopen(t *testing.T, st *store.Store, kek *crypto.KEK) *store.Store {
	t.Helper()
	var schema string
	if err := st.Pool().QueryRow(context.Background(), "SELECT current_schema()").Scan(&schema); err != nil {
		t.Fatal(err)
	}
	u, err := url.Parse(lookup(t))
	if err != nil {
		t.Fatal(err)
	}
	q := u.Query()
	q.Set("search_path", schema)
	u.RawQuery = q.Encode()
	st2, err := store.Open(context.Background(), u.String(), kek)
	if err != nil {
		t.Fatalf("reopen: %v", err)
	}
	t.Cleanup(st2.Close)
	return st2
}

func lookup(t *testing.T) string {
	t.Helper()
	v := getenv(envURL)
	if v == "" {
		t.Skip(envURL + " is not set")
	}
	return v
}

func getenv(k string) string { return os.Getenv(k) }
