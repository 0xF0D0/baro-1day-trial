package api_test

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strings"
	"testing"

	"backbone/internal/api"
	"backbone/internal/canon"
	"backbone/internal/fold"
	"backbone/internal/store"
	"backbone/internal/store/storetest"
	"backbone/internal/tenants"
)

type env struct {
	ts  *httptest.Server
	st  *store.Store
	log *bytes.Buffer
}

func newEnv(t *testing.T) *env {
	t.Helper()
	st, _ := storetest.New(t)
	reg, err := tenants.Load("testdata/tenants.json")
	if err != nil {
		t.Fatal(err)
	}
	if err := st.EnsureTenants(context.Background(), []string{"t_a", "t_b"}); err != nil {
		t.Fatal(err)
	}
	buf := &bytes.Buffer{}
	ts := httptest.NewServer(api.NewServer(reg, st, slog.New(slog.NewJSONHandler(buf, nil))))
	t.Cleanup(ts.Close)
	return &env{ts: ts, st: st, log: buf}
}

func (e *env) do(t *testing.T, method, path, token string, body []byte, hdr map[string]string) (int, []byte) {
	t.Helper()
	req, err := http.NewRequest(method, e.ts.URL+path, bytes.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	for k, v := range hdr {
		req.Header.Set(k, v)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	b, _ := io.ReadAll(resp.Body)
	return resp.StatusCode, b
}

func sigA(secret string, body []byte) map[string]string {
	m := hmac.New(sha256.New, []byte(secret))
	m.Write([]byte("1700000000."))
	m.Write(body)
	return map[string]string{"Vendor-A-Signature": "t=1700000000,v1=" + hex.EncodeToString(m.Sum(nil))}
}

func sigB(secret string, body []byte) map[string]string {
	m := hmac.New(sha256.New, []byte(secret))
	m.Write(body)
	return map[string]string{"X-VendorB-Hmac-SHA256": base64.StdEncoding.EncodeToString(m.Sum(nil))}
}

func bodyA(account, id, typ string, created any, obj string) []byte {
	return []byte(fmt.Sprintf(`{"id":%q,"type":%q,"created":%v,"account":%q,"livemode":true,"data":{"object":%s}}`,
		id, typ, created, account, obj))
}

func adMetric(account, id string, created int) []byte {
	return bodyA(account, id, "ads.metric", created, `{"campaign_id":"cmp_1","spend":100,"impressions":10,"clicks":1}`)
}

func orderBody(account, id string, created int, customer string) []byte {
	return bodyA(account, id, "order.created", created, fmt.Sprintf(
		`{"order_id":"ord_%s","customer":{"id":%q,"email":"x@mail.example","name":"X Y"},"line_items":[{"sku":"S1","quantity":2,"unit_amount":500}],"currency":"usd"}`, id, customer))
}

func invB(domain, id, ts string) []byte {
	return []byte(fmt.Sprintf(`{"event_uuid":%q,"event":"inventory.adjusted","shop_domain":%q,"timestamp":%q,"api_version":"1","payload":{"sku":"SKU-1","delta":5,"reason":"initial"}}`,
		id, domain, ts))
}

func (e *env) postA(t *testing.T, secret string, body []byte) int {
	t.Helper()
	c, _ := e.do(t, "POST", "/webhooks/vendor-a", "", body, sigA(secret, body))
	return c
}

func TestWebhookStatusCodes(t *testing.T) {
	e := newEnv(t)
	good := adMetric("acct_a", "evt_1", 1000)
	cases := []struct {
		name string
		path string
		body []byte
		hdr  map[string]string
		want int
	}{
		{"valid A", "/webhooks/vendor-a", good, sigA("sec_a1", good), 200},
		{"duplicate", "/webhooks/vendor-a", good, sigA("sec_a1", good), 200},
		{"bad json", "/webhooks/vendor-a", []byte(`{bad`), nil, 400},
		{"unknown account", "/webhooks/vendor-a", adMetric("acct_zz", "evt_2", 1), sigA("sec_a1", adMetric("acct_zz", "evt_2", 1)), 404},
		{"wrong secret", "/webhooks/vendor-a", good, sigA("sec_b1", good), 401},
		{"no signature", "/webhooks/vendor-a", good, nil, 401},
		{"fractional created", "/webhooks/vendor-a", adMetric("acct_a", "evt_3", 0), nil, 400},
		{"valid B", "/webhooks/vendor-b", invB("a.shops.example", "b-1", "2026-07-01T00:10:07.912Z"),
			sigB("sec_a2", invB("a.shops.example", "b-1", "2026-07-01T00:10:07.912Z")), 200},
		{"unknown shop", "/webhooks/vendor-b", invB("zz.shops.example", "b-2", "2026-07-01T00:10:07.912Z"), nil, 404},
		{"oversize", "/webhooks/vendor-a", bytes.Repeat([]byte("x"), 2<<20), nil, 400},
	}
	// "fractional created" needs a valid signature over the malformed body.
	frac := bodyA("acct_a", "evt_3", "ads.metric", "1.5", `{"campaign_id":"c","spend":1,"impressions":1,"clicks":1}`)
	cases[6].body, cases[6].hdr = frac, sigA("sec_a1", frac)
	for _, c := range cases {
		code, body := e.do(t, "POST", c.path, "", c.body, c.hdr)
		if code != c.want {
			t.Errorf("%s: got %d want %d", c.name, code, c.want)
		}
		if len(body) != 0 {
			t.Errorf("%s: unexpected response body %q", c.name, body)
		}
	}

	// Customer erasure: a genuine delivery is 200 and invisible.
	ord := orderBody("acct_a", "evt_o1", 2000, "cus_1")
	if c := e.postA(t, "sec_a1", ord); c != 200 {
		t.Fatalf("order: %d", c)
	}
	if c, _ := e.do(t, "DELETE", "/tenants/t_a/customers/cus_1", "adm_test", nil, nil); c != 204 {
		t.Fatalf("erase customer: %d", c)
	}
	ord2 := orderBody("acct_a", "evt_o2", 2001, "cus_1")
	if c := e.postA(t, "sec_a1", ord2); c != 200 {
		t.Fatalf("erased customer delivery: %d", c)
	}
	_, b := e.do(t, "GET", "/tenants/t_a/events?from_ms=0&to_ms=9999999", "tok_a", nil, nil)
	if strings.Contains(string(b), "evt_o1") || strings.Contains(string(b), "evt_o2") {
		t.Fatalf("erased customer events visible: %s", b)
	}

	// Tenant erasure: genuine 410, forged 401.
	if c, _ := e.do(t, "DELETE", "/tenants/t_b", "adm_test", nil, nil); c != 204 {
		t.Fatal(c)
	}
	gb := adMetric("acct_b", "evt_b1", 5)
	if c := e.postA(t, "sec_b1", gb); c != 410 {
		t.Errorf("genuine after tenant erase: %d", c)
	}
	if c := e.postA(t, "random", gb); c != 401 {
		t.Errorf("forged after tenant erase: %d", c)
	}
}

func canonical(t *testing.T, bodies ...[]byte) []canon.Event {
	t.Helper()
	var out []canon.Event
	for _, b := range bodies {
		ev, err := canon.FromVendorA(b, "t_a")
		if err != nil {
			t.Fatal(err)
		}
		out = append(out, ev)
	}
	return out
}

func TestStateEndpoint(t *testing.T) {
	e := newEnv(t)

	// A tenant with no events: empty maps, not null.
	code, body := e.do(t, "GET", "/tenants/t_a/state", "tok_a", nil, nil)
	if code != 200 || !bytes.Contains(body, []byte(`"inventory":{}`)) {
		t.Fatalf("empty state: %d %s", code, body)
	}

	bodies := [][]byte{
		orderBody("acct_a", "evt_s1", 3000, "cus_9"),
		adMetric("acct_a", "evt_s2", 1000),
		adMetric("acct_a", "evt_s3", 2000),
	}
	for _, b := range bodies {
		if c := e.postA(t, "sec_a1", b); c != 200 {
			t.Fatal(c)
		}
	}
	sc, err := e.st.Scope(context.Background(), "t_a")
	if err != nil {
		t.Fatal(err)
	}
	want, err := fold.Fold("t_a", canonical(t, bodies...), sc.Keys().CustomerKeyHex)
	if err != nil {
		t.Fatal(err)
	}
	wb, _ := json.Marshal(want)
	code, body = e.do(t, "GET", "/tenants/t_a/state", "tok_a", nil, nil)
	if code != 200 {
		t.Fatal(code)
	}
	var g, w any
	_ = json.Unmarshal(body, &g)
	_ = json.Unmarshal(wb, &w)
	if !reflect.DeepEqual(g, w) {
		t.Fatalf("state mismatch:\n got %s\nwant %s", body, wb)
	}

	for _, c := range []struct {
		name, path, tok string
		want            int
	}{
		{"no auth", "/tenants/t_a/state", "", 401},
		{"bad token", "/tenants/t_a/state", "nope", 401},
		{"other tenant", "/tenants/t_b/state", "tok_a", 404},
	} {
		if code, _ := e.do(t, "GET", c.path, c.tok, nil, nil); code != c.want {
			t.Errorf("%s: %d want %d", c.name, code, c.want)
		}
	}
	if c, _ := e.do(t, "DELETE", "/tenants/t_b", "adm_test", nil, nil); c != 204 {
		t.Fatal(c)
	}
	if c, _ := e.do(t, "GET", "/tenants/t_b/state", "tok_b", nil, nil); c != 410 {
		t.Errorf("erased own: %d", c)
	}
	if c, _ := e.do(t, "GET", "/tenants/t_b/state", "tok_a", nil, nil); c != 404 {
		t.Errorf("erased other: %d", c)
	}
}

type page struct {
	Events []struct {
		EventID string `json:"event_id"`
	} `json:"events"`
	NextCursor *string `json:"next_cursor"`
}

func TestEventsEndpoint(t *testing.T) {
	e := newEnv(t)
	for i := 1; i <= 5; i++ {
		if c := e.postA(t, "sec_a1", adMetric("acct_a", fmt.Sprintf("evt_%d", i), i*1000)); c != 200 {
			t.Fatal(c)
		}
	}
	var ids []string
	var nexts []bool
	path := "/tenants/t_a/events?from_ms=0&to_ms=100000&limit=2"
	cursor := ""
	for range 5 {
		u := path
		if cursor != "" {
			u += "&cursor=" + cursor
		}
		code, body := e.do(t, "GET", u, "tok_a", nil, nil)
		if code != 200 {
			t.Fatalf("%d %s", code, body)
		}
		var p page
		if err := json.Unmarshal(body, &p); err != nil {
			t.Fatal(err)
		}
		for _, ev := range p.Events {
			ids = append(ids, ev.EventID)
		}
		nexts = append(nexts, p.NextCursor != nil)
		if p.NextCursor == nil {
			break
		}
		cursor = *p.NextCursor
	}
	if want := []string{"evt_1", "evt_2", "evt_3", "evt_4", "evt_5"}; !reflect.DeepEqual(ids, want) {
		t.Errorf("ids %v", ids)
	}
	if !reflect.DeepEqual(nexts, []bool{true, true, false}) {
		t.Errorf("next cursors %v", nexts)
	}

	for _, p := range []string{
		"/tenants/t_a/events?to_ms=10",
		"/tenants/t_a/events?from_ms=0&to_ms=10&limit=0",
		"/tenants/t_a/events?from_ms=0&to_ms=10&limit=abc",
	} {
		if c, _ := e.do(t, "GET", p, "tok_a", nil, nil); c != 400 {
			t.Errorf("%s: %d", p, c)
		}
	}

	code, body := e.do(t, "GET", "/tenants/t_a/events?from_ms=500000&to_ms=600000", "tok_a", nil, nil)
	if code != 200 || string(body) != `{"events":[],"next_cursor":null}` {
		t.Errorf("empty window: %d %s", code, body)
	}
}

func TestEventsCursorTampering(t *testing.T) {
	e := newEnv(t)
	for _, acct := range []struct{ a, s string }{{"acct_a", "sec_a1"}, {"acct_b", "sec_b1"}} {
		for i := 1; i <= 3; i++ {
			if c := e.postA(t, acct.s, adMetric(acct.a, fmt.Sprintf("evt_%s_%d", acct.a, i), i*1000)); c != 200 {
				t.Fatal(c)
			}
		}
	}
	_, body := e.do(t, "GET", "/tenants/t_a/events?from_ms=0&to_ms=100000&limit=1", "tok_a", nil, nil)
	var p page
	_ = json.Unmarshal(body, &p)
	if p.NextCursor == nil {
		t.Fatal("no cursor")
	}
	cur := *p.NextCursor
	if c, _ := e.do(t, "GET", "/tenants/t_a/events?from_ms=0&to_ms=100000&limit=1&cursor="+cur, "tok_a", nil, nil); c != 200 {
		t.Fatalf("intact cursor: %d", c)
	}
	flip := []byte(cur)
	if flip[len(flip)-3] == 'A' {
		flip[len(flip)-3] = 'B'
	} else {
		flip[len(flip)-3] = 'A'
	}
	if c, _ := e.do(t, "GET", "/tenants/t_a/events?from_ms=0&to_ms=100000&limit=1&cursor="+string(flip), "tok_a", nil, nil); c != 400 {
		t.Errorf("flipped: %d", c)
	}
	if c, _ := e.do(t, "GET", "/tenants/t_b/events?from_ms=0&to_ms=100000&limit=1&cursor="+cur, "tok_b", nil, nil); c != 400 {
		t.Errorf("other tenant: %d", c)
	}
	if c, _ := e.do(t, "GET", "/tenants/t_a/events?from_ms=0&to_ms=99999&limit=1&cursor="+cur, "tok_a", nil, nil); c != 400 {
		t.Errorf("different to_ms: %d", c)
	}
}

func TestErasureEndpoints(t *testing.T) {
	e := newEnv(t)
	if c := e.postA(t, "sec_a1", orderBody("acct_a", "evt_e1", 1000, "cus_1")); c != 200 {
		t.Fatal(c)
	}
	if c, _ := e.do(t, "DELETE", "/tenants/t_a/customers/cus_1", "tok_a", nil, nil); c != 401 {
		t.Errorf("tenant token: %d", c)
	}
	if c, _ := e.do(t, "DELETE", "/tenants/t_a/customers/cus_1", "adm_test", nil, nil); c != 204 {
		t.Errorf("admin: %d", c)
	}
	_, b := e.do(t, "GET", "/tenants/t_a/events?from_ms=0&to_ms=100000", "tok_a", nil, nil)
	if strings.Contains(string(b), "evt_e1") {
		t.Errorf("customer event survived: %s", b)
	}
	for i := 0; i < 2; i++ {
		if c, _ := e.do(t, "DELETE", "/tenants/t_b", "adm_test", nil, nil); c != 204 {
			t.Errorf("tenant erase #%d: %d", i, c)
		}
	}
	if c, _ := e.do(t, "DELETE", "/tenants/t_b/customers/cus_1", "adm_test", nil, nil); c != 204 {
		t.Errorf("customer of erased tenant: %d", c)
	}
	if c, _ := e.do(t, "DELETE", "/tenants/t_zz", "adm_test", nil, nil); c != 404 {
		t.Errorf("unknown tenant: %d", c)
	}
	if c, _ := e.do(t, "GET", "/healthz", "", nil, nil); c != 200 {
		t.Errorf("healthz: %d", c)
	}
}

func TestLogsCarryNoPathsOrIDs(t *testing.T) {
	e := newEnv(t)
	e.do(t, "DELETE", "/tenants/t_a/customers/cus_secret", "adm_test", nil, nil)
	b := orderBody("acct_a", "evt_l1", 1, "cus_secret")
	e.postA(t, "sec_a1", b)
	e.do(t, "POST", "/webhooks/vendor-a", "", []byte(`{bad cus_secret`), nil)
	e.do(t, "GET", "/nowhere/cus_secret?x=cus_secret", "tok_a", nil, nil)
	out := e.log.String()
	if !strings.Contains(out, "DELETE /tenants/{id}/customers/{customer_id}") ||
		!strings.Contains(out, "POST /webhooks/vendor-a") {
		t.Errorf("route templates missing: %s", out)
	}
	for _, bad := range []string{"cus_secret", "/tenants/t_a/customers", "acct_a", "evt_l1", "nowhere"} {
		if strings.Contains(out, bad) {
			t.Errorf("log contains %q: %s", bad, out)
		}
	}
}

func TestParseLimit(t *testing.T) {
	for in, want := range map[string]int{"": 1000, "5000": 1000, "7": 7} {
		if got, err := api.ParseLimit(in); err != nil || got != want {
			t.Errorf("%q: %d %v", in, got, err)
		}
	}
	for _, in := range []string{"0", "-1", "abc"} {
		if _, err := api.ParseLimit(in); err == nil {
			t.Errorf("%q: want error", in)
		}
	}
}
