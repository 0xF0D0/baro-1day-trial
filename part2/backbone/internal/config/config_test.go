package config_test

import (
	"strings"
	"testing"
	"time"

	"backbone/internal/config"
)

func TestLoadReportsEveryMissingVariable(t *testing.T) {
	_, err := config.Load(func(string) string { return "" })
	for _, name := range []string{"BACKBONE_TENANTS_FILE", "BACKBONE_KEK_FILE", "BACKBONE_DATABASE_URL",
		"BACKBONE_MINIO_ENDPOINT", "BACKBONE_MINIO_USER_FILE", "BACKBONE_MINIO_PASSWORD_FILE"} {
		if err == nil || !strings.Contains(err.Error(), name) {
			t.Fatalf("missing %s not reported: %v", name, err)
		}
	}
}

func TestLoadDefaultsListen(t *testing.T) {
	env := validEnv()
	cfg, err := config.Load(func(k string) string { return env[k] })
	if err != nil {
		t.Fatal(err)
	}
	if cfg.Listen != ":8080" || cfg.TenantsFile != "a" || cfg.KEKFile != "b" || cfg.DatabaseURL != "c" {
		t.Fatalf("unexpected config: %+v", cfg)
	}
}

func TestLoadMetricsListen(t *testing.T) {
	env := validEnv()
	cfg, err := config.Load(func(k string) string { return env[k] })
	if err != nil {
		t.Fatal(err)
	}
	if cfg.MetricsListen != ":9100" {
		t.Fatalf("default %q", cfg.MetricsListen)
	}
	env["BACKBONE_METRICS_LISTEN"] = ":9200"
	cfg, err = config.Load(func(k string) string { return env[k] })
	if err != nil || cfg.MetricsListen != ":9200" {
		t.Fatalf("override %q %v", cfg.MetricsListen, err)
	}
}

func TestLoadListenOverride(t *testing.T) {
	env := validEnv()
	env["BACKBONE_LISTEN"] = ":9"
	cfg, err := config.Load(func(k string) string { return env[k] })
	if err != nil || cfg.Listen != ":9" {
		t.Fatalf("got %+v, %v", cfg, err)
	}
}

func validEnv() map[string]string {
	return map[string]string{
		"BACKBONE_TENANTS_FILE": "a", "BACKBONE_KEK_FILE": "b", "BACKBONE_DATABASE_URL": "c",
		"BACKBONE_MINIO_ENDPOINT": "m:9000", "BACKBONE_MINIO_USER_FILE": "u", "BACKBONE_MINIO_PASSWORD_FILE": "p",
	}
}

func TestLoadMinioAndFlushDefaults(t *testing.T) {
	env := validEnv()
	cfg, err := config.Load(func(k string) string { return env[k] })
	if err != nil {
		t.Fatal(err)
	}
	if cfg.MinioEndpoint != "m:9000" || cfg.MinioUserFile != "u" || cfg.MinioPasswordFile != "p" {
		t.Fatalf("unexpected minio config: %+v", cfg)
	}
	if cfg.MinioBucket != "backbone" || cfg.FlushInterval != 5*time.Minute || cfg.FlushMargin != 96*time.Hour || cfg.WatermarkRank != 100 {
		t.Fatalf("unexpected defaults: %+v", cfg)
	}
	env["BACKBONE_MINIO_BUCKET"] = "b2"
	env["BACKBONE_FLUSH_INTERVAL"] = "2s"
	env["BACKBONE_FLUSH_MARGIN"] = "1h"
	env["BACKBONE_WATERMARK_RANK"] = "7"
	cfg, err = config.Load(func(k string) string { return env[k] })
	if err != nil || cfg.MinioBucket != "b2" || cfg.FlushInterval != 2*time.Second || cfg.FlushMargin != time.Hour || cfg.WatermarkRank != 7 {
		t.Fatalf("overrides: %+v, %v", cfg, err)
	}
	env["BACKBONE_FLUSH_MARGIN"] = "soon"
	if _, err := config.Load(func(k string) string { return env[k] }); err == nil {
		t.Fatal("bad duration accepted")
	}
}

func TestLoadRejectsNonPositiveFlushSettings(t *testing.T) {
	for name, val := range map[string]string{
		"BACKBONE_FLUSH_INTERVAL": "0s", "BACKBONE_WATERMARK_RANK": "0",
	} {
		for _, v := range []string{val, "-1" + map[bool]string{true: "s", false: ""}[name == "BACKBONE_FLUSH_INTERVAL"]} {
			env := validEnv()
			env[name] = v
			if _, err := config.Load(func(k string) string { return env[k] }); err == nil {
				t.Fatalf("%s=%q accepted", name, v)
			}
		}
	}
}

func TestLoadRejectsNegativeFlushMargin(t *testing.T) {
	env := validEnv()
	env["BACKBONE_FLUSH_MARGIN"] = "-1h"
	if _, err := config.Load(func(k string) string { return env[k] }); err == nil {
		t.Fatal("negative margin accepted")
	}
	env["BACKBONE_FLUSH_MARGIN"] = "0s"
	if _, err := config.Load(func(k string) string { return env[k] }); err != nil {
		t.Fatalf("zero margin rejected: %v", err)
	}
}

func TestLoadSweepDefaultsAndValidation(t *testing.T) {
	env := validEnv()
	cfg, err := config.Load(func(k string) string { return env[k] })
	if err != nil || cfg.SweepInterval != time.Hour || cfg.GarbageGrace != 10*time.Minute {
		t.Fatalf("defaults: %+v, %v", cfg, err)
	}
	env["BACKBONE_SWEEP_INTERVAL"] = "0s"
	if _, err := config.Load(func(k string) string { return env[k] }); err == nil {
		t.Fatal("zero sweep interval accepted")
	}
	env["BACKBONE_SWEEP_INTERVAL"] = "10s"
	env["BACKBONE_GARBAGE_GRACE"] = "-1m"
	if _, err := config.Load(func(k string) string { return env[k] }); err == nil {
		t.Fatal("negative grace accepted")
	}
	env["BACKBONE_GARBAGE_GRACE"] = "0s"
	cfg, err = config.Load(func(k string) string { return env[k] })
	if err != nil || cfg.GarbageGrace != 0 || cfg.SweepInterval != 10*time.Second {
		t.Fatalf("zero grace: %+v, %v", cfg, err)
	}
}

func TestLoadCrashSettings(t *testing.T) {
	env := validEnv()
	cfg, err := config.Load(func(k string) string { return env[k] })
	if err != nil || len(cfg.CrashPoints) != 0 || cfg.CrashProbability != 0 {
		t.Fatalf("defaults: %+v, %v", cfg, err)
	}
	env["BACKBONE_CRASH_POINTS"] = " flush.after_bucket , rebuild.before_commit "
	env["BACKBONE_CRASH_PROBABILITY"] = "0.25"
	cfg, err = config.Load(func(k string) string { return env[k] })
	if err != nil || len(cfg.CrashPoints) != 2 || cfg.CrashPoints[0] != "flush.after_bucket" ||
		cfg.CrashPoints[1] != "rebuild.before_commit" || cfg.CrashProbability != 0.25 {
		t.Fatalf("parsed: %+v, %v", cfg, err)
	}
	for _, bad := range []string{"1.5", "-0.1"} {
		env["BACKBONE_CRASH_PROBABILITY"] = bad
		if _, err := config.Load(func(k string) string { return env[k] }); err == nil {
			t.Fatalf("probability %s accepted", bad)
		}
	}
}
