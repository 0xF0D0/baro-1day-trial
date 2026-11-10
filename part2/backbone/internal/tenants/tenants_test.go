package tenants_test

import (
	"os"
	"path/filepath"
	"testing"

	"backbone/internal/tenants"
)

func TestRegistryLookups(t *testing.T) {
	reg, err := tenants.Load("testdata/tenants.json")
	if err != nil {
		t.Fatal(err)
	}
	if tn, ok := reg.ByAccount("acct_b"); !ok || tn.ID != "t_b" {
		t.Fatalf("ByAccount: %v %v", tn, ok)
	}
	if tn, ok := reg.ByShopDomain("a.shops.example"); !ok || tn.ID != "t_a" {
		t.Fatalf("ByShopDomain: %v %v", tn, ok)
	}
	if tn, ok := reg.ByToken("tok_a"); !ok || tn.ID != "t_a" || tn.VendorA.SigningSecret != "sec_a1" {
		t.Fatalf("ByToken: %v %v", tn, ok)
	}
	if tn, ok := reg.ByToken("nope"); ok || tn != nil {
		t.Fatalf("ByToken(nope): %v %v", tn, ok)
	}
	if tn, ok := reg.ByID("t_b"); !ok || tn.Name != "B" {
		t.Fatalf("ByID: %v %v", tn, ok)
	}
	if _, ok := reg.ByID("zz"); ok {
		t.Fatal("ByID(zz) found")
	}
	if !reg.IsAdmin("adm_test") || reg.IsAdmin("tok_a") || reg.IsAdmin("") {
		t.Fatal("IsAdmin wrong")
	}
	all := reg.All()
	if len(all) != 2 || all[0].ID != "t_a" || all[1].ID != "t_b" {
		t.Fatalf("All: %v", all)
	}
}

func TestParseRejectsDuplicates(t *testing.T) {
	mk := func(a, b string) string {
		return `{"admin_token":"x","tenants":[` + a + `,` + b + `]}`
	}
	ten := func(id, tok, acct, shop string) string {
		return `{"tenant_id":"` + id + `","name":"n","api_token":"` + tok + `","vendor_a":{"account":"` + acct + `","signing_secret":"s"},"vendor_b":{"shop_domain":"` + shop + `","signing_secret":"s"}}`
	}
	tenSecrets := func(secA, secB string) string {
		return `{"tenant_id":"t1","name":"n","api_token":"k1","vendor_a":{"account":"a1","signing_secret":"` + secA + `"},"vendor_b":{"shop_domain":"s1","signing_secret":"` + secB + `"}}`
	}
	cases := map[string]string{
		"emptysecretA": mk(tenSecrets("", "s"), ten("t2", "k2", "a2", "s2")),
		"emptysecretB": mk(tenSecrets("s", ""), ten("t2", "k2", "a2", "s2")),
		"account":      mk(ten("t1", "k1", "acct_a", "s1"), ten("t2", "k2", "acct_a", "s2")),
		"shop":         mk(ten("t1", "k1", "a1", "s"), ten("t2", "k2", "a2", "s")),
		"token":        mk(ten("t1", "k", "a1", "s1"), ten("t2", "k", "a2", "s2")),
		"id":           mk(ten("t1", "k1", "a1", "s1"), ten("t1", "k2", "a2", "s2")),
		"empty":        mk(ten("", "k1", "a1", "s1"), ten("t2", "k2", "a2", "s2")),
		"emptyaccount": mk(ten("t1", "k1", "", "s1"), ten("t2", "k2", "a2", "s2")),
	}
	for name, doc := range cases {
		if _, err := tenants.Parse([]byte(doc)); err == nil {
			t.Errorf("%s: expected error", name)
		}
	}
	if _, err := tenants.Parse([]byte("not json")); err == nil {
		t.Error("bad json accepted")
	}
}

func TestLoadSuppliedTenants(t *testing.T) {
	infra := os.Getenv("INFRA")
	if infra == "" {
		t.Skip("INFRA not set")
	}
	reg, err := tenants.Load(filepath.Join(infra, "data", "tenants.json"))
	if err != nil {
		t.Fatal(err)
	}
	if n := len(reg.All()); n != 200 {
		t.Fatalf("got %d tenants, want 200", n)
	}
}
