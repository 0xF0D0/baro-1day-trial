package api

import (
	"crypto/hmac"
	"encoding/base64"
	"encoding/json"
	"errors"
	"strings"

	"backbone/internal/crypto"
	"backbone/internal/store"
)

var errBadCursor = errors.New("bad cursor")

type cursorPayload struct {
	From int64  `json:"f"`
	To   int64  `json:"t"`
	Ms   int64  `json:"o"`
	ID   string `json:"i"`
}

var b64 = base64.RawURLEncoding

// encodeCursor returns base64url(payload) "." base64url(MAC(payload)).
func encodeCursor(keys *crypto.TenantKeys, from, to int64, last store.Key) string {
	payload, _ := json.Marshal(cursorPayload{From: from, To: to, Ms: last.OccurredAtMs, ID: last.EventID})
	return b64.EncodeToString(payload) + "." + b64.EncodeToString(keys.CursorMAC(payload))
}

// decodeCursor verifies the MAC under the tenant's key and that the cursor was
// issued for the same window.
func decodeCursor(keys *crypto.TenantKeys, cursor string, from, to int64) (store.Key, error) {
	p, m, ok := strings.Cut(cursor, ".")
	if !ok {
		return store.Key{}, errBadCursor
	}
	payload, err := b64.DecodeString(p)
	if err != nil {
		return store.Key{}, errBadCursor
	}
	mac, err := b64.DecodeString(m)
	if err != nil || !hmac.Equal(mac, keys.CursorMAC(payload)) {
		return store.Key{}, errBadCursor
	}
	var c cursorPayload
	if err := json.Unmarshal(payload, &c); err != nil || c.From != from || c.To != to {
		return store.Key{}, errBadCursor
	}
	return store.Key{OccurredAtMs: c.Ms, EventID: c.ID}, nil
}
