package config_test

import (
	"strings"
	"testing"

	"backbone/internal/config"
)

func TestLoadReportsEveryMissingVariable(t *testing.T) {
	_, err := config.Load(func(string) string { return "" })
	for _, name := range []string{"BACKBONE_TENANTS_FILE", "BACKBONE_KEK_FILE", "BACKBONE_DATABASE_URL"} {
		if err == nil || !strings.Contains(err.Error(), name) {
			t.Fatalf("missing %s not reported: %v", name, err)
		}
	}
}

func TestLoadDefaultsListen(t *testing.T) {
	env := map[string]string{"BACKBONE_TENANTS_FILE": "a", "BACKBONE_KEK_FILE": "b", "BACKBONE_DATABASE_URL": "c"}
	cfg, err := config.Load(func(k string) string { return env[k] })
	if err != nil {
		t.Fatal(err)
	}
	if cfg.Listen != ":8080" || cfg.TenantsFile != "a" || cfg.KEKFile != "b" || cfg.DatabaseURL != "c" {
		t.Fatalf("unexpected config: %+v", cfg)
	}
}

func TestLoadListenOverride(t *testing.T) {
	env := map[string]string{"BACKBONE_LISTEN": ":9", "BACKBONE_TENANTS_FILE": "a", "BACKBONE_KEK_FILE": "b", "BACKBONE_DATABASE_URL": "c"}
	cfg, err := config.Load(func(k string) string { return env[k] })
	if err != nil || cfg.Listen != ":9" {
		t.Fatalf("got %+v, %v", cfg, err)
	}
}
