// Command bench measures read latency through the load balancer: for every
// tenant and round it reads the state and the first page of a cold-day and a
// hot-day range. It never prints customer IDs.
package main

import (
	"compress/gzip"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"sort"
	"sync"
	"time"

	"backbone/internal/bench"
	"backbone/internal/tenants"
)

type sample struct {
	class  string
	tenant string
	d      time.Duration
}

func main() {
	ok, err := run()
	if err != nil {
		fmt.Fprintln(os.Stderr, "bench: error:", err)
		os.Exit(2)
	}
	if !ok {
		os.Exit(1)
	}
}

func ms(d time.Duration) string { return fmt.Sprintf("%.1f", float64(d)/float64(time.Millisecond)) }

func run() (bool, error) {
	target := flag.String("target", "http://lb:8080", "base URL of the load balancer")
	tenantsPath := flag.String("tenants", "", "path to tenants.json")
	deliveries := flag.String("deliveries", "", "path to deliveries.jsonl.gz")
	rounds := flag.Int("rounds", 5, "rounds per tenant")
	conc := flag.Int("concurrency", 8, "concurrent requests")
	flag.Parse()
	if *tenantsPath == "" || *deliveries == "" || *rounds < 1 || *conc < 1 {
		return false, fmt.Errorf("-tenants and -deliveries are required; -rounds and -concurrency must be >= 1")
	}
	reg, err := tenants.Load(*tenantsPath)
	if err != nil {
		return false, err
	}
	f, err := os.Open(*deliveries)
	if err != nil {
		return false, err
	}
	defer f.Close()
	gz, err := gzip.NewReader(f)
	if err != nil {
		return false, err
	}
	cf, ct, hf, ht, err := bench.Windows(gz)
	if err != nil {
		return false, err
	}

	client := &http.Client{Timeout: 90 * time.Second}
	get := func(url, token string) (int, time.Duration, error) {
		req, err := http.NewRequest(http.MethodGet, url, nil)
		if err != nil {
			return 0, 0, err
		}
		req.Header.Set("Authorization", "Bearer "+token)
		start := time.Now()
		resp, err := client.Do(req)
		if err != nil {
			return 0, time.Since(start), err
		}
		_, _ = io.Copy(io.Discard, resp.Body)
		resp.Body.Close()
		return resp.StatusCode, time.Since(start), nil
	}

	all := reg.All()
	var mu sync.Mutex
	samples := map[string][]time.Duration{}
	stateMax := map[string]time.Duration{}
	skipped, errs := 0, 0

	type job struct {
		t     int
		class string
		url   string
	}
	erased := map[int]bool{} // tenants whose first state read answered 410
	for round := 0; round < *rounds; round++ {
		var jobs []job
		for i, t := range all {
			base := *target + "/tenants/" + t.ID
			jobs = append(jobs,
				job{i, "state", base + "/state"},
				job{i, "range_cold", fmt.Sprintf("%s/events?from_ms=%d&to_ms=%d", base, cf, ct)},
				job{i, "range_hot", fmt.Sprintf("%s/events?from_ms=%d&to_ms=%d", base, hf, ht)},
			)
		}
		// The first state read of each tenant decides whether it is erased; do it
		// before the rest of the round so a 410 skips all three requests.
		if round == 0 {
			probe := make([]int, len(all))
			var wg sync.WaitGroup
			sem := make(chan struct{}, *conc)
			for i, t := range all {
				wg.Add(1)
				sem <- struct{}{}
				go func() {
					defer wg.Done()
					defer func() { <-sem }()
					code, d, err := get(*target+"/tenants/"+t.ID+"/state", t.APIToken)
					mu.Lock()
					defer mu.Unlock()
					probe[i] = code
					switch {
					case err != nil:
						errs++
					case code == http.StatusGone:
						skipped++
					case code == http.StatusOK:
						samples["state"] = append(samples["state"], d)
						stateMax[t.ID] = max(stateMax[t.ID], d)
					default:
						errs++
					}
				}()
			}
			wg.Wait()
			for i, c := range probe {
				if c == http.StatusGone {
					erased[i] = true
				}
			}
		}
		var wg sync.WaitGroup
		sem := make(chan struct{}, *conc)
		for _, j := range jobs {
			if erased[j.t] {
				continue
			}
			if round == 0 && j.class == "state" {
				continue // measured by the probe
			}
			wg.Add(1)
			sem <- struct{}{}
			go func() {
				defer wg.Done()
				defer func() { <-sem }()
				t := all[j.t]
				code, d, err := get(j.url, t.APIToken)
				mu.Lock()
				defer mu.Unlock()
				if err != nil || code != http.StatusOK {
					errs++
					return
				}
				samples[j.class] = append(samples[j.class], d)
				if j.class == "state" {
					stateMax[t.ID] = max(stateMax[t.ID], d)
				}
			}()
		}
		wg.Wait()
	}

	for _, c := range []string{"state", "range_cold", "range_hot"} {
		s := bench.Summarize(samples[c])
		fmt.Printf("%s count=%d p50=%s p95=%s p99=%s max=%s\n", c, s.Count, ms(s.P50), ms(s.P95), ms(s.P99), ms(s.Max))
	}
	type kv struct {
		id string
		d  time.Duration
	}
	var slow []kv
	for id, d := range stateMax {
		slow = append(slow, kv{id, d})
	}
	sort.Slice(slow, func(i, j int) bool {
		if slow[i].d != slow[j].d {
			return slow[i].d > slow[j].d
		}
		return slow[i].id < slow[j].id
	})
	for i := 0; i < len(slow) && i < 3; i++ {
		fmt.Printf("slowest_state tenant=%s max=%s\n", slow[i].id, ms(slow[i].d))
	}
	fmt.Printf("skipped_erased=%d\n", skipped)
	fmt.Printf("errors=%d\n", errs)
	return errs == 0, nil
}
