// Package webhook verifies vendor webhook signatures and peeks at the tenant
// selector of a raw body. It depends on the standard library only.
package webhook

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
)

const (
	HeaderA = "Vendor-A-Signature"
	HeaderB = "X-VendorB-Hmac-SHA256"
)

// ErrBadSignature is returned for any missing, malformed or mismatching signature.
var ErrBadSignature = errors.New("bad signature")

// PeekAccount returns the top-level "account" string of raw, or "" if absent.
// The error is non-nil only for invalid JSON.
func PeekAccount(raw []byte) (string, error) { return peek(raw, "account") }

// PeekShopDomain returns the top-level "shop_domain" string of raw, or "" if absent.
// The error is non-nil only for invalid JSON.
func PeekShopDomain(raw []byte) (string, error) { return peek(raw, "shop_domain") }

func peek(raw []byte, key string) (string, error) {
	var m map[string]json.RawMessage
	if err := json.Unmarshal(raw, &m); err != nil {
		return "", err
	}
	var s string
	if v, ok := m[key]; ok && json.Unmarshal(v, &s) == nil {
		return s, nil
	}
	return "", nil
}

// VerifyA checks header "t=<t>,v1=<hex>[,v1=...]" against
// hex(HMAC_SHA256(secret, "<t>.<raw>")). Any v1 may match; there is no
// timestamp tolerance.
func VerifyA(secret, header string, raw []byte) error {
	var ts string
	var hasT bool
	var sigs []string
	for _, part := range strings.Split(header, ",") {
		k, v, ok := strings.Cut(strings.TrimSpace(part), "=")
		if !ok {
			continue
		}
		switch k {
		case "t":
			ts, hasT = v, true
		case "v1":
			sigs = append(sigs, v)
		}
	}
	if !hasT || len(sigs) == 0 {
		return ErrBadSignature
	}
	m := hmac.New(sha256.New, []byte(secret))
	m.Write([]byte(ts + "."))
	m.Write(raw)
	want := m.Sum(nil)
	match := false
	for _, s := range sigs {
		got, err := hex.DecodeString(s)
		if err == nil && hmac.Equal(got, want) {
			match = true
		}
	}
	if !match {
		return ErrBadSignature
	}
	return nil
}

// VerifyB checks header against base64std(HMAC_SHA256(secret, raw)).
func VerifyB(secret, header string, raw []byte) error {
	got, err := base64.StdEncoding.DecodeString(header)
	if err != nil {
		return ErrBadSignature
	}
	m := hmac.New(sha256.New, []byte(secret))
	m.Write(raw)
	if !hmac.Equal(got, m.Sum(nil)) {
		return ErrBadSignature
	}
	return nil
}
