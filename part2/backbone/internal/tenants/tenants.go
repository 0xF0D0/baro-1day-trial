// Package tenants loads the tenant registry from the supplied tenants file.
package tenants

import (
	"crypto/sha256"
	"crypto/subtle"
	"encoding/json"
	"fmt"
	"os"
	"sort"
)

// VendorA holds a tenant's vendor A account and signing secret.
type VendorA struct {
	Account       string `json:"account"`
	SigningSecret string `json:"signing_secret"`
}

// VendorB holds a tenant's vendor B shop domain and signing secret.
type VendorB struct {
	ShopDomain    string `json:"shop_domain"`
	SigningSecret string `json:"signing_secret"`
}

// Tenant is one registered tenant.
type Tenant struct {
	ID       string  `json:"tenant_id"`
	Name     string  `json:"name"`
	APIToken string  `json:"api_token"`
	VendorA  VendorA `json:"vendor_a"`
	VendorB  VendorB `json:"vendor_b"`
}

type file struct {
	AdminToken string   `json:"admin_token"`
	Tenants    []Tenant `json:"tenants"`
}

// Registry indexes tenants by ID, vendor identity and API token.
type Registry struct {
	adminHash [sha256.Size]byte
	all       []*Tenant
	byID      map[string]*Tenant
	byAccount map[string]*Tenant
	byShop    map[string]*Tenant
	byToken   map[[sha256.Size]byte]*Tenant
}

// Load reads and parses the tenants file at path.
func Load(path string) (*Registry, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read tenants file: %w", err)
	}
	return Parse(data)
}

// Parse builds a Registry from tenants JSON. It rejects empty or duplicate
// tenant IDs, accounts, shop domains and tokens.
func Parse(data []byte) (*Registry, error) {
	var f file
	if err := json.Unmarshal(data, &f); err != nil {
		return nil, fmt.Errorf("parse tenants file: %w", err)
	}
	if f.AdminToken == "" {
		return nil, fmt.Errorf("parse tenants file: empty admin token")
	}
	r := &Registry{
		adminHash: sha256.Sum256([]byte(f.AdminToken)),
		byID:      map[string]*Tenant{},
		byAccount: map[string]*Tenant{},
		byShop:    map[string]*Tenant{},
		byToken:   map[[sha256.Size]byte]*Tenant{},
	}
	for i := range f.Tenants {
		t := &f.Tenants[i]
		for _, v := range []struct{ field, val string }{
			{"tenant_id", t.ID},
			{"api_token", t.APIToken},
			{"vendor_a.account", t.VendorA.Account},
			{"vendor_b.shop_domain", t.VendorB.ShopDomain},
		} {
			if v.val == "" {
				return nil, fmt.Errorf("tenant at index %d: empty %s", i, v.field)
			}
		}
		th := sha256.Sum256([]byte(t.APIToken))
		if _, dup := r.byID[t.ID]; dup {
			return nil, fmt.Errorf("duplicate tenant id %q", t.ID)
		}
		if _, dup := r.byAccount[t.VendorA.Account]; dup {
			return nil, fmt.Errorf("duplicate vendor A account %q", t.VendorA.Account)
		}
		if _, dup := r.byShop[t.VendorB.ShopDomain]; dup {
			return nil, fmt.Errorf("duplicate vendor B shop domain %q", t.VendorB.ShopDomain)
		}
		if _, dup := r.byToken[th]; dup {
			return nil, fmt.Errorf("duplicate api token for tenant %q", t.ID)
		}
		r.byID[t.ID] = t
		r.byAccount[t.VendorA.Account] = t
		r.byShop[t.VendorB.ShopDomain] = t
		r.byToken[th] = t
		r.all = append(r.all, t)
	}
	sort.Slice(r.all, func(i, j int) bool { return r.all[i].ID < r.all[j].ID })
	return r, nil
}

// ByAccount finds a tenant by vendor A account.
func (r *Registry) ByAccount(account string) (*Tenant, bool) {
	t, ok := r.byAccount[account]
	return t, ok
}

// ByShopDomain finds a tenant by vendor B shop domain.
func (r *Registry) ByShopDomain(domain string) (*Tenant, bool) {
	t, ok := r.byShop[domain]
	return t, ok
}

// ByToken finds a tenant by API token, looking up the token's SHA-256.
func (r *Registry) ByToken(token string) (*Tenant, bool) {
	t, ok := r.byToken[sha256.Sum256([]byte(token))]
	return t, ok
}

// ByID finds a tenant by ID.
func (r *Registry) ByID(id string) (*Tenant, bool) {
	t, ok := r.byID[id]
	return t, ok
}

// IsAdmin reports whether token is the admin token, in constant time.
func (r *Registry) IsAdmin(token string) bool {
	h := sha256.Sum256([]byte(token))
	return subtle.ConstantTimeCompare(h[:], r.adminHash[:]) == 1
}

// All returns every tenant sorted by ID.
func (r *Registry) All() []*Tenant {
	return append([]*Tenant{}, r.all...)
}
