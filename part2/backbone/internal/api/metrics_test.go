package api_test

import (
	"strings"
	"testing"

	"backbone/internal/metrics"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/testutil"
	dto "github.com/prometheus/client_model/go"
)

func ingestCount(vendor, outcome string) float64 {
	return testutil.ToFloat64(metrics.IngestTotal.WithLabelValues(vendor, outcome))
}

func ackSamples(vendor string) uint64 {
	var m dto.Metric
	if err := metrics.AckSeconds.WithLabelValues(vendor).(prometheus.Metric).Write(&m); err != nil {
		panic(err)
	}
	return m.GetHistogram().GetSampleCount()
}

func TestIngestOutcomesCounted(t *testing.T) {
	e := newEnv(t)
	type key struct{ vendor, outcome string }
	outcomes := []string{"stored", "duplicate", "customer_erased", "tenant_erased", "bad_request", "unknown_tenant", "bad_signature", "error"}
	before := map[key]float64{}
	for _, v := range []string{"a", "b"} {
		for _, o := range outcomes {
			before[key{v, o}] = ingestCount(v, o)
		}
	}
	ackBeforeA, ackBeforeB := ackSamples("a"), ackSamples("b")

	good := adMetric("acct_a", "evt_m1", 1000)
	post := func(path string, body []byte, hdr map[string]string, want int) {
		t.Helper()
		if c, _ := e.do(t, "POST", path, "", body, hdr); c != want {
			t.Fatalf("%s: got %d want %d", path, c, want)
		}
	}
	post("/webhooks/vendor-a", good, sigA("sec_a1", good), 200) // stored
	post("/webhooks/vendor-a", good, sigA("sec_a1", good), 200) // duplicate
	post("/webhooks/vendor-a", good, sigA("sec_b1", good), 401) // bad_signature
	unk := adMetric("acct_zz", "evt_m2", 1)
	post("/webhooks/vendor-a", unk, sigA("sec_a1", unk), 404) // unknown_tenant
	post("/webhooks/vendor-a", []byte(`{bad`), nil, 400)      // bad_request
	b := invB("a.shops.example", "b-m1", "2026-07-01T00:10:07.912Z")
	post("/webhooks/vendor-b", b, sigB("sec_a2", b), 200) // b stored
	ord := orderBody("acct_a", "evt_mo1", 2000, "cus_m")
	post("/webhooks/vendor-a", ord, sigA("sec_a1", ord), 200) // stored
	if c, _ := e.do(t, "DELETE", "/tenants/t_a/customers/cus_m", "adm_test", nil, nil); c != 204 {
		t.Fatal(c)
	}
	ord2 := orderBody("acct_a", "evt_mo2", 2001, "cus_m")
	post("/webhooks/vendor-a", ord2, sigA("sec_a1", ord2), 200) // customer_erased
	if c, _ := e.do(t, "DELETE", "/tenants/t_b", "adm_test", nil, nil); c != 204 {
		t.Fatal(c)
	}
	gb := adMetric("acct_b", "evt_mb1", 5)
	post("/webhooks/vendor-a", gb, sigA("sec_b1", gb), 410) // tenant_erased

	want := map[key]float64{
		{"a", "stored"}: 2, {"a", "duplicate"}: 1, {"a", "bad_signature"}: 1,
		{"a", "unknown_tenant"}: 1, {"a", "bad_request"}: 1, {"a", "customer_erased"}: 1,
		{"a", "tenant_erased"}: 1, {"b", "stored"}: 1,
	}
	for k, b0 := range before {
		if got := ingestCount(k.vendor, k.outcome) - b0; got != want[k] {
			t.Errorf("%v: delta %v want %v", k, got, want[k])
		}
	}
	// 200 answers: A stored x2, duplicate, customer_erased = 4; B stored = 1.
	if got := ackSamples("a") - ackBeforeA; got != 4 {
		t.Errorf("ack a: %d want 4", got)
	}
	if got := ackSamples("b") - ackBeforeB; got != 1 {
		t.Errorf("ack b: %d want 1", got)
	}
}

func TestMetricsCarryNoInputData(t *testing.T) {
	e := newEnv(t)
	o1 := orderBody("acct_a", "evt_nd1", 1000, "cus_nd")
	o2 := orderBody("acct_a", "evt_nd2", 1001, "cus_other")
	e.postA(t, "sec_a1", o1)
	e.postA(t, "sec_a1", o2)
	e.do(t, "DELETE", "/tenants/t_a/customers/cus_nd", "adm_test", nil, nil)
	e.do(t, "GET", "/tenants/t_a/state", "tok_a", nil, nil)
	e.do(t, "GET", "/tenants/t_a/events?from_ms=0&to_ms=99999", "tok_a", nil, nil)
	code, body := e.do(t, "GET", "/metrics", "", nil, nil)
	if code != 200 {
		t.Fatalf("metrics: %d", code)
	}
	for _, bad := range []string{"cus_", "t_00", "/tenants/", "evt_nd", "t_a", "acct_a"} {
		if strings.Contains(string(body), bad) {
			t.Errorf("metrics body contains %q", bad)
		}
	}
}
