// Package config reads the service configuration from environment variables.
package config

import (
	"fmt"
	"strings"
)

// Config holds the process-level settings.
type Config struct {
	Listen      string
	TenantsFile string
	KEKFile     string
	DatabaseURL string
}

// Load builds a Config from getenv. It reports every missing required variable at once.
func Load(getenv func(string) string) (Config, error) {
	cfg := Config{
		Listen:      getenv("BACKBONE_LISTEN"),
		TenantsFile: getenv("BACKBONE_TENANTS_FILE"),
		KEKFile:     getenv("BACKBONE_KEK_FILE"),
		DatabaseURL: getenv("BACKBONE_DATABASE_URL"),
	}
	if cfg.Listen == "" {
		cfg.Listen = ":8080"
	}
	var missing []string
	for _, r := range []struct{ name, val string }{
		{"BACKBONE_TENANTS_FILE", cfg.TenantsFile},
		{"BACKBONE_KEK_FILE", cfg.KEKFile},
		{"BACKBONE_DATABASE_URL", cfg.DatabaseURL},
	} {
		if r.val == "" {
			missing = append(missing, r.name)
		}
	}
	if len(missing) > 0 {
		return Config{}, fmt.Errorf("missing required environment variables: %s", strings.Join(missing, ", "))
	}
	return cfg, nil
}
