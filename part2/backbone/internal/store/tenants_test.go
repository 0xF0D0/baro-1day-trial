package store_test

import (
	"bytes"
	"context"
	"errors"
	"sync"
	"testing"

	"backbone/internal/store"
	"backbone/internal/store/storetest"
)

func runBoth(t *testing.T, a, b func() error) {
	t.Helper()
	errs := make([]error, 2)
	var wg sync.WaitGroup
	for i, f := range []func() error{a, b} {
		wg.Add(1)
		go func() { defer wg.Done(); errs[i] = f() }()
	}
	wg.Wait()
	for _, err := range errs {
		if err != nil {
			t.Fatal(err)
		}
	}
}

func TestMigrateConcurrent(t *testing.T) {
	ctx := context.Background()
	// The race is timing-dependent, so repeat it on several empty schemas.
	for i := 0; i < 5; i++ {
		st1, kek := storetest.NewUnmigrated(t)
		st2 := storetest.Reopen(t, st1, kek)
		runBoth(t, func() error { return st1.Migrate(ctx) }, func() error { return st2.Migrate(ctx) })
		if err := st1.Migrate(ctx); err != nil {
			t.Fatal(err)
		}
	}
}

func TestEnsureTenantsConcurrent(t *testing.T) {
	ctx := context.Background()
	st1, kek := storetest.New(t)
	st2 := storetest.Reopen(t, st1, kek)
	ids := []string{"t_1", "t_2"}
	runBoth(t, func() error { return st1.EnsureTenants(ctx, ids) }, func() error { return st2.EnsureTenants(ctx, ids) })
	sc1, err := st1.Scope(ctx, "t_1")
	if err != nil {
		t.Fatal(err)
	}
	sc2, err := st2.Scope(ctx, "t_1")
	if err != nil {
		t.Fatal(err)
	}
	if sc1.TenantID() != "t_1" || !bytes.Equal(sc1.Keys().CustomerKey("c"), sc2.Keys().CustomerKey("c")) {
		t.Fatal("nodes disagree on tenant keys")
	}
}

func TestScopeErrors(t *testing.T) {
	ctx := context.Background()
	st1, kek := storetest.New(t)
	if _, err := st1.Scope(ctx, "t_missing"); err != nil {
		t.Fatalf("missing tenant should be created: %v", err)
	}
	if err := st1.EnsureTenants(ctx, []string{"t_1"}); err != nil {
		t.Fatal(err)
	}
	if _, err := st1.Pool().Exec(ctx, `UPDATE tenants SET status='erased' WHERE tenant_id='t_1'`); err != nil {
		t.Fatal(err)
	}
	if _, err := st1.Pool().Exec(ctx, `DELETE FROM tenant_keys WHERE tenant_id='t_1'`); err != nil {
		t.Fatal(err)
	}
	st2 := storetest.Reopen(t, st1, kek)
	if _, err := st2.Scope(ctx, "t_1"); !errors.Is(err, store.ErrTenantErased) {
		t.Fatalf("want ErrTenantErased, got %v", err)
	}
	// A restart must not resurrect a key for the erased tenant.
	if err := st2.EnsureTenants(ctx, []string{"t_1"}); err != nil {
		t.Fatal(err)
	}
	if _, err := st2.Scope(ctx, "t_1"); !errors.Is(err, store.ErrTenantErased) {
		t.Fatalf("want ErrTenantErased after EnsureTenants, got %v", err)
	}
}

func TestCiphertextStatisticsOff(t *testing.T) {
	ctx := context.Background()
	st, _ := storetest.New(t)
	for _, c := range []struct{ table, col string }{{"hot_events", "payload"}, {"tenant_keys", "wrapped_dek"}} {
		var target int
		err := st.Pool().QueryRow(ctx,
			`SELECT attstattarget FROM pg_attribute WHERE attrelid = $1::regclass AND attname = $2`,
			c.table, c.col).Scan(&target)
		if err != nil {
			t.Fatal(err)
		}
		if target != 0 {
			t.Fatalf("%s.%s attstattarget = %d, want 0", c.table, c.col, target)
		}
	}
}

func TestScopeCreatesMissingTenant(t *testing.T) {
	ctx := context.Background()
	st1, kek := storetest.New(t)
	st2 := storetest.Reopen(t, st1, kek)
	var sc1, sc2 store.Scope
	runBoth(t,
		func() (err error) { sc1, err = st1.Scope(ctx, "t_new"); return },
		func() (err error) { sc2, err = st2.Scope(ctx, "t_new"); return })
	if !bytes.Equal(sc1.Keys().CustomerKey("c"), sc2.Keys().CustomerKey("c")) {
		t.Fatal("nodes disagree on tenant keys")
	}
	var n int
	if err := st1.Pool().QueryRow(ctx, `SELECT count(*) FROM tenant_keys WHERE tenant_id='t_new'`).Scan(&n); err != nil || n != 1 {
		t.Fatalf("tenant_keys rows = %d, err %v", n, err)
	}
}

func TestEraseTenantWithoutRowStaysErased(t *testing.T) {
	ctx := context.Background()
	st, _ := storetest.New(t)
	if err := st.EraseTenant(ctx, "t_never"); err != nil {
		t.Fatal(err)
	}
	var status string
	if err := st.Pool().QueryRow(ctx, `SELECT status FROM tenants WHERE tenant_id='t_never'`).Scan(&status); err != nil || status != "erased" {
		t.Fatalf("status %q, err %v", status, err)
	}
	var n int
	if err := st.Pool().QueryRow(ctx, `SELECT count(*) FROM tenant_keys WHERE tenant_id='t_never'`).Scan(&n); err != nil || n != 0 {
		t.Fatalf("keys = %d, err %v", n, err)
	}
	if _, err := st.Scope(ctx, "t_never"); !errors.Is(err, store.ErrTenantErased) {
		t.Fatalf("scope: %v", err)
	}
	if err := st.EnsureTenants(ctx, []string{"t_never"}); err != nil {
		t.Fatal(err)
	}
	if err := st.Pool().QueryRow(ctx, `SELECT count(*) FROM tenant_keys WHERE tenant_id='t_never'`).Scan(&n); err != nil || n != 0 {
		t.Fatalf("key created after ensure: %d, err %v", n, err)
	}
}
