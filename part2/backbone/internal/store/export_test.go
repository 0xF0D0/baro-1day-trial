package store

// LockKey exposes lockKey to the external store tests.
func LockKey(kind string, parts ...[]byte) int64 { return lockKey(kind, parts...) }
