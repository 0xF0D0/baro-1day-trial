// Package config reads the service configuration from environment variables.
package config

import (
	"fmt"
	"strconv"
	"strings"
	"time"
)

// Config holds the process-level settings.
type Config struct {
	Listen        string
	MetricsListen string
	TenantsFile   string
	KEKFile       string
	DatabaseURL   string

	MinioEndpoint     string
	MinioBucket       string
	MinioUserFile     string
	MinioPasswordFile string

	FlushInterval time.Duration
	FlushMargin   time.Duration
	WatermarkRank int

	SweepInterval time.Duration
	GarbageGrace  time.Duration

	// SnapshotCacheTTL is how long an api node keeps a decrypted snapshot; 0 disables the cache.
	SnapshotCacheTTL time.Duration

	CrashPoints      []string
	CrashProbability float64
}

// Load builds a Config from getenv. It reports every missing required variable at once.
func Load(getenv func(string) string) (Config, error) {
	cfg := Config{
		Listen:      getenv("BACKBONE_LISTEN"),
		TenantsFile: getenv("BACKBONE_TENANTS_FILE"),
		KEKFile:     getenv("BACKBONE_KEK_FILE"),
		DatabaseURL: getenv("BACKBONE_DATABASE_URL"),

		MinioEndpoint:     getenv("BACKBONE_MINIO_ENDPOINT"),
		MinioBucket:       getenv("BACKBONE_MINIO_BUCKET"),
		MinioUserFile:     getenv("BACKBONE_MINIO_USER_FILE"),
		MinioPasswordFile: getenv("BACKBONE_MINIO_PASSWORD_FILE"),
	}
	if cfg.MinioBucket == "" {
		cfg.MinioBucket = "backbone"
	}
	cfg.MetricsListen = getenv("BACKBONE_METRICS_LISTEN")
	if cfg.MetricsListen == "" {
		cfg.MetricsListen = ":9100"
	}
	if cfg.Listen == "" {
		cfg.Listen = ":8080"
	}
	var missing []string
	for _, r := range []struct{ name, val string }{
		{"BACKBONE_TENANTS_FILE", cfg.TenantsFile},
		{"BACKBONE_KEK_FILE", cfg.KEKFile},
		{"BACKBONE_DATABASE_URL", cfg.DatabaseURL},
		{"BACKBONE_MINIO_ENDPOINT", cfg.MinioEndpoint},
		{"BACKBONE_MINIO_USER_FILE", cfg.MinioUserFile},
		{"BACKBONE_MINIO_PASSWORD_FILE", cfg.MinioPasswordFile},
	} {
		if r.val == "" {
			missing = append(missing, r.name)
		}
	}
	if len(missing) > 0 {
		return Config{}, fmt.Errorf("missing required environment variables: %s", strings.Join(missing, ", "))
	}
	var err error
	if cfg.FlushInterval, err = duration(getenv, "BACKBONE_FLUSH_INTERVAL", 5*time.Minute); err != nil {
		return Config{}, err
	}
	if cfg.FlushInterval <= 0 {
		return Config{}, fmt.Errorf("BACKBONE_FLUSH_INTERVAL must be positive")
	}
	if cfg.FlushMargin, err = duration(getenv, "BACKBONE_FLUSH_MARGIN", 96*time.Hour); err != nil {
		return Config{}, err
	}
	if cfg.FlushMargin < 0 {
		return Config{}, fmt.Errorf("BACKBONE_FLUSH_MARGIN must not be negative")
	}
	if cfg.SweepInterval, err = duration(getenv, "BACKBONE_SWEEP_INTERVAL", time.Hour); err != nil {
		return Config{}, err
	}
	if cfg.SweepInterval <= 0 {
		return Config{}, fmt.Errorf("BACKBONE_SWEEP_INTERVAL must be positive")
	}
	if cfg.GarbageGrace, err = duration(getenv, "BACKBONE_GARBAGE_GRACE", 10*time.Minute); err != nil {
		return Config{}, err
	}
	if cfg.GarbageGrace < 0 {
		return Config{}, fmt.Errorf("BACKBONE_GARBAGE_GRACE must not be negative")
	}
	if cfg.SnapshotCacheTTL, err = duration(getenv, "BACKBONE_SNAPSHOT_CACHE_TTL", time.Hour); err != nil {
		return Config{}, err
	}
	if cfg.SnapshotCacheTTL < 0 {
		return Config{}, fmt.Errorf("BACKBONE_SNAPSHOT_CACHE_TTL must not be negative")
	}
	for _, p := range strings.Split(getenv("BACKBONE_CRASH_POINTS"), ",") {
		if p = strings.TrimSpace(p); p != "" {
			cfg.CrashPoints = append(cfg.CrashPoints, p)
		}
	}
	if v := getenv("BACKBONE_CRASH_PROBABILITY"); v != "" {
		if cfg.CrashProbability, err = strconv.ParseFloat(v, 64); err != nil {
			return Config{}, fmt.Errorf("BACKBONE_CRASH_PROBABILITY: %w", err)
		}
		if !(cfg.CrashProbability >= 0 && cfg.CrashProbability <= 1) {
			return Config{}, fmt.Errorf("BACKBONE_CRASH_PROBABILITY must be within [0, 1]")
		}
	}
	cfg.WatermarkRank = 100
	if v := getenv("BACKBONE_WATERMARK_RANK"); v != "" {
		if cfg.WatermarkRank, err = strconv.Atoi(v); err != nil {
			return Config{}, fmt.Errorf("BACKBONE_WATERMARK_RANK: %w", err)
		}
		if cfg.WatermarkRank < 1 {
			return Config{}, fmt.Errorf("BACKBONE_WATERMARK_RANK must be at least 1")
		}
	}
	return cfg, nil
}

func duration(getenv func(string) string, name string, def time.Duration) (time.Duration, error) {
	v := getenv(name)
	if v == "" {
		return def, nil
	}
	d, err := time.ParseDuration(v)
	if err != nil {
		return 0, fmt.Errorf("%s: %w", name, err)
	}
	return d, nil
}
