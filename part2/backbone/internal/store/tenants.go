package store

import (
	"context"
	"errors"
	"fmt"

	"backbone/internal/crypto"

	"github.com/jackc/pgx/v5"
)

// Scope is proof that a tenant is active and carries its keys. Only the
// store can create one.
type Scope struct {
	tenantID string
	keys     *crypto.TenantKeys
}

// TenantID returns the tenant the scope belongs to.
func (s Scope) TenantID() string { return s.tenantID }

// Keys returns the tenant's derived keys.
func (s Scope) Keys() *crypto.TenantKeys { return s.keys }

// EnsureTenants registers each tenant as active if new and gives active
// tenants without a key a wrapped DEK. Erased tenants never get a key.
func (s *Store) EnsureTenants(ctx context.Context, ids []string) error {
	for _, id := range ids {
		if err := s.ensureTenant(ctx, id); err != nil {
			return err
		}
	}
	return nil
}

func (s *Store) ensureTenant(ctx context.Context, id string) error {
	if _, err := s.pool.Exec(ctx,
		`INSERT INTO tenants (tenant_id, status) VALUES ($1, 'active') ON CONFLICT DO NOTHING`, id); err != nil {
		return fmt.Errorf("store: ensure tenant: %w", err)
	}
	var status string
	var hasKey bool
	err := s.pool.QueryRow(ctx,
		`SELECT t.status, EXISTS (SELECT 1 FROM tenant_keys k WHERE k.tenant_id = t.tenant_id)
		   FROM tenants t WHERE t.tenant_id = $1`, id).Scan(&status, &hasKey)
	if err != nil {
		return fmt.Errorf("store: ensure tenant: %w", err)
	}
	if status != "active" || hasKey {
		return nil
	}
	wrapped, err := s.kek.NewWrappedDEK(id)
	if err != nil {
		return fmt.Errorf("store: new dek: %w", err)
	}
	// The insert is conditional on the tenant still being active, so a
	// concurrent erasure cannot be followed by a fresh key.
	if _, err := s.pool.Exec(ctx,
		`INSERT INTO tenant_keys (tenant_id, wrapped_dek)
		 SELECT tenant_id, $2 FROM tenants WHERE tenant_id = $1 AND status = 'active'
		 ON CONFLICT DO NOTHING`, id, wrapped); err != nil {
		return fmt.Errorf("store: insert tenant key: %w", err)
	}
	return nil
}

// Scope returns the tenant's keys, always from the stored DEK.
func (s *Store) Scope(ctx context.Context, tenantID string) (Scope, error) {
	s.mu.Lock()
	keys, ok := s.keys[tenantID]
	s.mu.Unlock()
	if ok {
		return Scope{tenantID: tenantID, keys: keys}, nil
	}
	var wrapped []byte
	err := s.pool.QueryRow(ctx, `SELECT wrapped_dek FROM tenant_keys WHERE tenant_id = $1`, tenantID).Scan(&wrapped)
	if errors.Is(err, pgx.ErrNoRows) {
		var status string
		err = s.pool.QueryRow(ctx, `SELECT status FROM tenants WHERE tenant_id = $1`, tenantID).Scan(&status)
		if errors.Is(err, pgx.ErrNoRows) {
			return Scope{}, ErrUnknownTenant
		}
		if err != nil {
			return Scope{}, fmt.Errorf("store: tenant status: %w", err)
		}
		if status == "erased" {
			return Scope{}, ErrTenantErased
		}
		return Scope{}, fmt.Errorf("store: tenant %q is active but has no key", tenantID)
	}
	if err != nil {
		return Scope{}, fmt.Errorf("store: read tenant key: %w", err)
	}
	keys, err = s.kek.Unwrap(tenantID, wrapped)
	if err != nil {
		return Scope{}, fmt.Errorf("store: unwrap tenant key: %w", err)
	}
	s.mu.Lock()
	s.keys[tenantID] = keys
	s.mu.Unlock()
	return Scope{tenantID: tenantID, keys: keys}, nil
}
