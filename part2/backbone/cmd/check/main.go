// Command check compares the replay's acknowledged deliveries with what
// storage holds. It only reads and never prints customer IDs.
package main

import (
	"compress/gzip"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strings"

	"backbone/internal/check"
	"backbone/internal/cold"
	"backbone/internal/config"
	"backbone/internal/crypto"
	"backbone/internal/store"
	"backbone/internal/tenants"
)

func main() {
	ok, err := run()
	if err != nil {
		fmt.Fprintln(os.Stderr, "check: error:", err)
		os.Exit(2)
	}
	if !ok {
		fmt.Println("CHECK FAIL")
		os.Exit(1)
	}
	fmt.Println("CHECK PASS")
}

func run() (bool, error) {
	deliveries := flag.String("deliveries", "", "path to deliveries.jsonl.gz")
	responses := flag.String("responses", "", "path to replay_responses.json")
	flag.Parse()
	if *deliveries == "" || *responses == "" {
		return false, fmt.Errorf("both -deliveries and -responses are required")
	}
	cfg, err := config.Load(os.Getenv)
	if err != nil {
		return false, err
	}
	reg, err := tenants.Load(cfg.TenantsFile)
	if err != nil {
		return false, err
	}
	kek, err := crypto.LoadKEK(cfg.KEKFile)
	if err != nil {
		return false, err
	}

	rb, err := os.ReadFile(*responses)
	if err != nil {
		return false, fmt.Errorf("read responses: %w", err)
	}
	var resp map[string]*int
	if err := json.Unmarshal(rb, &resp); err != nil {
		return false, fmt.Errorf("parse responses: %w", err)
	}
	f, err := os.Open(*deliveries)
	if err != nil {
		return false, fmt.Errorf("open deliveries: %w", err)
	}
	defer f.Close()
	gz, err := gzip.NewReader(f)
	if err != nil {
		return false, fmt.Errorf("gunzip deliveries: %w", err)
	}
	exp, err := check.Expected(reg, gz, resp)
	if err != nil {
		return false, err
	}

	ctx := context.Background()
	user, err := os.ReadFile(cfg.MinioUserFile)
	if err != nil {
		return false, fmt.Errorf("read minio user file: %w", err)
	}
	pass, err := os.ReadFile(cfg.MinioPasswordFile)
	if err != nil {
		return false, fmt.Errorf("read minio password file: %w", err)
	}
	objects, err := cold.Open(ctx, cold.Config{
		Endpoint:  cfg.MinioEndpoint,
		AccessKey: strings.TrimSpace(string(user)),
		SecretKey: strings.TrimSpace(string(pass)),
		Bucket:    cfg.MinioBucket,
	})
	if err != nil {
		return false, err
	}
	st, err := store.Open(ctx, cfg.DatabaseURL, kek, objects)
	if err != nil {
		return false, err
	}
	defer st.Close()

	audits := map[string]store.Audit{}
	expected := 0
	for _, t := range reg.All() {
		a, err := st.Audit(ctx, t.ID)
		if err != nil {
			return false, fmt.Errorf("audit %s: %w", t.ID, err)
		}
		audits[t.ID] = a
		expected += len(exp.Events[t.ID])
	}
	stored := map[string]bool{}
	for id, a := range audits {
		for _, e := range a.HotIDs {
			stored[id+"/"+e] = true
		}
		for _, e := range a.ColdIDs {
			stored[id+"/"+e] = true
		}
	}

	problems := check.Compare(exp, audits)
	counts := map[string]int{}
	for i, p := range problems {
		counts[p.Kind]++
		if i < 20 {
			fmt.Printf("problem: tenant=%s kind=%s detail=%s\n", p.Tenant, p.Kind, p.Detail)
		}
	}
	fmt.Printf("check: tenants=%d expected=%d stored=%d\n", len(audits), expected, len(stored))
	fmt.Printf("lost=%d unexpected=%d duplicate=%d bad_pointer=%d unreferenced=%d garbage=%d dirty=%d state_mismatch=%d unparsed=%d\n",
		counts["lost"], counts["unexpected"], counts["duplicate"], counts["bad_pointer"], counts["unreferenced"],
		counts["garbage"], counts["dirty"], counts["state_mismatch"], counts["unparsed"])
	return len(problems) == 0, nil
}
