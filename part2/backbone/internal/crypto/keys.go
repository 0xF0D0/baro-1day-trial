// Package crypto holds the key hierarchy: a KEK wraps one DEK per tenant, and
// the DEK derives the payload, customer, SKU and cursor sub-keys.
package crypto

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/hkdf"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"os"
)

const keySize = 32

var errOpen = errors.New("crypto: authentication failed")

// KEK is the key-encryption key that wraps tenant DEKs.
type KEK struct{ aead cipher.AEAD }

// LoadKEK reads a KEK file, which must hold exactly 32 bytes.
func LoadKEK(path string) (*KEK, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read kek file: %w", err)
	}
	return NewKEK(b)
}

// NewKEK builds a KEK from exactly 32 bytes.
func NewKEK(key []byte) (*KEK, error) {
	if len(key) != keySize {
		return nil, fmt.Errorf("kek must be %d bytes, got %d", keySize, len(key))
	}
	a, err := newAEAD(key)
	if err != nil {
		return nil, err
	}
	return &KEK{aead: a}, nil
}

func newAEAD(key []byte) (cipher.AEAD, error) {
	blk, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	return cipher.NewGCM(blk)
}

func seal(a cipher.AEAD, aad, plaintext []byte) []byte {
	nonce := make([]byte, a.NonceSize())
	if _, err := rand.Read(nonce); err != nil {
		panic("crypto: random source failed")
	}
	return a.Seal(nonce, nonce, plaintext, aad)
}

func open(a cipher.AEAD, aad, sealed []byte) ([]byte, error) {
	n := a.NonceSize()
	if len(sealed) < n+a.Overhead() {
		return nil, errOpen
	}
	pt, err := a.Open(nil, sealed[:n], sealed[n:], aad)
	if err != nil {
		return nil, errOpen
	}
	return pt, nil
}

func dekAAD(tenantID string) []byte { return []byte("dek:" + tenantID) }

// NewWrappedDEK creates a random DEK and returns it sealed under the KEK,
// bound to the tenant.
func (k *KEK) NewWrappedDEK(tenantID string) ([]byte, error) {
	dek := make([]byte, keySize)
	if _, err := rand.Read(dek); err != nil {
		return nil, fmt.Errorf("generate dek: %w", err)
	}
	return seal(k.aead, dekAAD(tenantID), dek), nil
}

// Unwrap opens a wrapped DEK for the tenant and derives its sub-keys.
func (k *KEK) Unwrap(tenantID string, wrapped []byte) (*TenantKeys, error) {
	dek, err := open(k.aead, dekAAD(tenantID), wrapped)
	if err != nil {
		return nil, fmt.Errorf("unwrap dek: %w", err)
	}
	if len(dek) != keySize {
		return nil, errors.New("unwrap dek: bad length")
	}
	return newTenantKeys(dek)
}

// TenantKeys holds the sub-keys derived from one tenant DEK.
type TenantKeys struct {
	payload  cipher.AEAD
	customer []byte
	sku      []byte
	cursor   []byte
}

func newTenantKeys(dek []byte) (*TenantKeys, error) {
	derive := func(label string) ([]byte, error) {
		return hkdf.Key(sha256.New, dek, nil, label, keySize)
	}
	pk, err := derive("backbone/v1/payload")
	if err != nil {
		return nil, err
	}
	a, err := newAEAD(pk)
	if err != nil {
		return nil, err
	}
	tk := &TenantKeys{payload: a}
	if tk.customer, err = derive("backbone/v1/customer"); err != nil {
		return nil, err
	}
	if tk.sku, err = derive("backbone/v1/sku"); err != nil {
		return nil, err
	}
	if tk.cursor, err = derive("backbone/v1/cursor"); err != nil {
		return nil, err
	}
	return tk, nil
}

// Seal encrypts plaintext with AES-256-GCM; the result is a random 12-byte
// nonce followed by the ciphertext.
func (t *TenantKeys) Seal(aad, plaintext []byte) []byte { return seal(t.payload, aad, plaintext) }

// Open reverses Seal and fails if the AAD or ciphertext does not match.
func (t *TenantKeys) Open(aad, sealed []byte) ([]byte, error) { return open(t.payload, aad, sealed) }

func mac(key, msg []byte) []byte {
	h := hmac.New(sha256.New, key)
	h.Write(msg)
	return h.Sum(nil)
}

// CustomerKey is the keyed HMAC of a customer ID.
func (t *TenantKeys) CustomerKey(customerID string) []byte {
	return mac(t.customer, []byte(customerID))
}

// CustomerKeyHex is CustomerKey in lowercase hex.
func (t *TenantKeys) CustomerKeyHex(customerID string) string {
	return hex.EncodeToString(t.CustomerKey(customerID))
}

// SKUKey is the keyed HMAC of a SKU. Reserved for Plan 2.
func (t *TenantKeys) SKUKey(sku string) []byte { return mac(t.sku, []byte(sku)) }

// CursorMAC authenticates a pagination cursor.
func (t *TenantKeys) CursorMAC(msg []byte) []byte { return mac(t.cursor, msg) }
