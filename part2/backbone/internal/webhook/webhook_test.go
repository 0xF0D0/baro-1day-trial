package webhook

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"testing"
)

func signA(secret, ts string, raw []byte) string {
	m := hmac.New(sha256.New, []byte(secret))
	m.Write([]byte(ts + "."))
	m.Write(raw)
	return hex.EncodeToString(m.Sum(nil))
}

func signB(secret string, raw []byte) string {
	m := hmac.New(sha256.New, []byte(secret))
	m.Write(raw)
	return base64.StdEncoding.EncodeToString(m.Sum(nil))
}

func TestVerifyA(t *testing.T) {
	raw := []byte(`{"id":"evt_1","account":"acct_a"}`)
	sig := signA("sec_a1", "1782950400", raw)
	good := "t=1782950400,v1=" + sig
	tampered := append(raw[:len(raw)-1:len(raw)-1], ' ')

	if err := VerifyA("sec_a1", good, raw); err != nil {
		t.Fatalf("good signature rejected: %v", err)
	}
	cases := []struct {
		name, secret, header string
		raw                  []byte
	}{
		{"other tenant key", "sec_b1", good, raw},
		{"tampered body", "sec_a1", good, tampered},
		{"missing t", "sec_a1", "v1=" + sig, raw},
		{"missing v1", "sec_a1", "t=1782950400", raw},
		{"empty header", "sec_a1", "", raw},
		{"undecodable v1", "sec_a1", "t=1782950400,v1=zz", raw},
	}
	for _, c := range cases {
		if err := VerifyA(c.secret, c.header, c.raw); !errors.Is(err, ErrBadSignature) {
			t.Errorf("%s: got %v, want ErrBadSignature", c.name, err)
		}
	}
	multi := "t=1,v1=00,v1=" + signA("sec_a1", "1", raw)
	if err := VerifyA("sec_a1", multi, raw); err != nil {
		t.Errorf("any v1 should match: %v", err)
	}
}

func TestVerifyB(t *testing.T) {
	raw := []byte(`{"shop_domain":"a.example"}`)
	if err := VerifyB("sec_a2", signB("sec_a2", raw), raw); err != nil {
		t.Fatalf("good signature rejected: %v", err)
	}
	for name, h := range map[string]string{
		"wrong key":  signB("sec_b2", raw),
		"empty":      "",
		"not base64": "!!!",
	} {
		if err := VerifyB("sec_a2", h, raw); !errors.Is(err, ErrBadSignature) {
			t.Errorf("%s: got %v, want ErrBadSignature", name, err)
		}
	}
}

func TestPeek(t *testing.T) {
	peeks := []struct {
		name string
		fn   func([]byte) (string, error)
		key  string
	}{
		{"account", PeekAccount, "account"},
		{"shop_domain", PeekShopDomain, "shop_domain"},
	}
	for _, p := range peeks {
		got, err := p.fn([]byte(`{"` + p.key + `":"v","id":"x"}`))
		if err != nil || got != "v" {
			t.Errorf("%s present: got %q, %v", p.name, got, err)
		}
		got, err = p.fn([]byte(`{"id":"x"}`))
		if err != nil || got != "" {
			t.Errorf("%s absent: got %q, %v", p.name, got, err)
		}
		if _, err = p.fn([]byte(`{not json`)); err == nil {
			t.Errorf("%s invalid JSON: want error", p.name)
		}
	}
}
