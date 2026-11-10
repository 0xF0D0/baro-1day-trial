package store

import (
	"crypto/sha256"
	"encoding/binary"
)

// lockKey derives a 64-bit advisory lock key from a lock kind and parts.
// It is the first 8 bytes of SHA-256 over the kind followed by each part
// prefixed with its 4-byte big-endian length.
func lockKey(kind string, parts ...[]byte) int64 {
	h := sha256.New()
	h.Write([]byte(kind))
	for _, p := range parts {
		var n [4]byte
		binary.BigEndian.PutUint32(n[:], uint32(len(p)))
		h.Write(n[:])
		h.Write(p)
	}
	return int64(binary.BigEndian.Uint64(h.Sum(nil)[:8]))
}
