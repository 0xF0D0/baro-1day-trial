package crypto_test

import (
	"bytes"
	"os"
	"path/filepath"
	"testing"

	"backbone/internal/crypto"
)

func newKEK(t *testing.T) *crypto.KEK {
	t.Helper()
	kek, err := crypto.NewKEK(bytes.Repeat([]byte{7}, 32))
	if err != nil {
		t.Fatal(err)
	}
	return kek
}

func TestWrapIsBoundToTenant(t *testing.T) {
	kek := newKEK(t)
	w, err := kek.NewWrappedDEK("t_1")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := kek.Unwrap("t_1", w); err != nil {
		t.Fatalf("unwrap own tenant: %v", err)
	}
	if _, err := kek.Unwrap("t_2", w); err == nil {
		t.Fatal("unwrap with another tenant must fail")
	}
}

func TestNewKEKLength(t *testing.T) {
	if _, err := crypto.NewKEK(make([]byte, 31)); err == nil {
		t.Fatal("31-byte key must fail")
	}
}

func TestSealOpen(t *testing.T) {
	kek := newKEK(t)
	w, _ := kek.NewWrappedDEK("t_1")
	tk, err := kek.Unwrap("t_1", w)
	if err != nil {
		t.Fatal(err)
	}
	aad, p := []byte("t_1|evt_1"), []byte("hello")
	s1 := tk.Seal(aad, p)
	got, err := tk.Open(aad, s1)
	if err != nil || !bytes.Equal(got, p) {
		t.Fatalf("round trip: %v %q", err, got)
	}
	if _, err := tk.Open([]byte("other"), s1); err == nil {
		t.Fatal("wrong aad must fail")
	}
	if _, err := tk.Open(aad, s1[:5]); err == nil {
		t.Fatal("short input must fail")
	}
	if bytes.Equal(s1, tk.Seal(aad, p)) {
		t.Fatal("two seals must differ")
	}
}

func TestSubkeys(t *testing.T) {
	kek := newKEK(t)
	w1, _ := kek.NewWrappedDEK("t_1")
	w2, _ := kek.NewWrappedDEK("t_2")
	a, _ := kek.Unwrap("t_1", w1)
	b, _ := kek.Unwrap("t_1", w1)
	c, _ := kek.Unwrap("t_2", w2)
	if len(a.CustomerKey("cus_1")) != 32 {
		t.Fatal("customer key must be 32 bytes")
	}
	if bytes.Equal(a.CustomerKey("cus_1"), a.SKUKey("cus_1")) {
		t.Fatal("customer and sku keys must differ")
	}
	if !bytes.Equal(a.CustomerKey("cus_1"), b.CustomerKey("cus_1")) {
		t.Fatal("same DEK must give same key")
	}
	if bytes.Equal(a.CustomerKey("cus_1"), c.CustomerKey("cus_1")) {
		t.Fatal("different tenants must differ")
	}
	if bytes.Equal(a.CustomerKey("cus_1"), a.CustomerKey("cus_2")) {
		t.Fatal("different customers must differ")
	}
	if len(a.CustomerKeyHex("cus_1")) != 64 {
		t.Fatal("hex must be 64 chars")
	}
	if !bytes.Equal(a.CursorMAC([]byte("m")), b.CursorMAC([]byte("m"))) || bytes.Equal(a.CursorMAC([]byte("m")), c.CursorMAC([]byte("m"))) {
		t.Fatal("cursor MAC determinism/tenant separation")
	}
}

func TestLoadKEKLength(t *testing.T) {
	dir := t.TempDir()
	bad := filepath.Join(dir, "bad")
	good := filepath.Join(dir, "good")
	os.WriteFile(bad, make([]byte, 31), 0o600)
	os.WriteFile(good, make([]byte, 32), 0o600)
	if _, err := crypto.LoadKEK(bad); err == nil {
		t.Fatal("31-byte file must fail")
	}
	if _, err := crypto.LoadKEK(good); err != nil {
		t.Fatalf("32-byte file: %v", err)
	}
	if _, err := crypto.LoadKEK(filepath.Join(dir, "missing")); err == nil {
		t.Fatal("missing file must fail")
	}
}
