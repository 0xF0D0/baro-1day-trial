package check_test

import (
	"encoding/json"
	"fmt"
	"strings"
	"testing"

	"backbone/internal/check"
	"backbone/internal/store"
	"backbone/internal/tenants"
)

const regJSON = `{"admin_token":"adm","tenants":[
 {"tenant_id":"t_a","name":"A","api_token":"tok_a","vendor_a":{"account":"acct_a","signing_secret":"s1"},"vendor_b":{"shop_domain":"a.shops.example","signing_secret":"s2"}},
 {"tenant_id":"t_b","name":"B","api_token":"tok_b","vendor_a":{"account":"acct_b","signing_secret":"s3"},"vendor_b":{"shop_domain":"b.shops.example","signing_secret":"s4"}}]}`

func bodyA(id, acct, cust string) string {
	return fmt.Sprintf(`{"id":%q,"type":"charge.refunded","created":1785824006510,"account":%q,"livemode":true,"data":{"object":{"order_id":"o1","customer_id":%q,"amount_refunded":5}}}`, id, acct, cust)
}

func bodyB(id, shop, cust string) string {
	return fmt.Sprintf(`{"event_uuid":%q,"event":"shipment.updated","shop_domain":%q,"timestamp":"2026-09-11T14:42:53.172Z","api_version":"1","payload":{"order_id":"o1","customer_id":%q,"status":"label_created","carrier":"usps","tracking":"1Z"}}`, id, shop, cust)
}

func TestExpected(t *testing.T) {
	reg, err := tenants.Parse([]byte(regJSON))
	if err != nil {
		t.Fatal(err)
	}
	var lines []string
	resp := map[string]*int{}
	seq := 0
	add := func(row map[string]any, status *int) {
		row["seq"] = seq
		b, _ := json.Marshal(row)
		lines = append(lines, string(b))
		resp[fmt.Sprint(seq)] = status
		seq++
	}
	st := func(n int) *int { return &n }
	hook := func(path, body string, status *int) {
		add(map[string]any{"kind": "webhook", "path": path, "body": body}, status)
	}
	// delivered twice, both 200 -> once
	hook("/webhooks/vendor-a", bodyA("evt_dup", "acct_a", "cus_keep"), st(200))
	hook("/webhooks/vendor-a", bodyA("evt_dup", "acct_a", "cus_keep"), st(200))
	// forged and never-succeeded
	hook("/webhooks/vendor-a", bodyA("evt_forged", "acct_a", "cus_keep"), st(401))
	hook("/webhooks/vendor-b", bodyB("evt_null", "a.shops.example", "cus_keep"), nil)
	// vendor B ok
	hook("/webhooks/vendor-b", bodyB("evt_b", "b.shops.example", "cus_keep"), st(200))
	// customer C erased (204): before and after
	hook("/webhooks/vendor-a", bodyA("evt_c_before", "acct_a", "cus_c"), st(200))
	add(map[string]any{"kind": "erase_customer", "tenant_id": "t_a", "customer_id": "cus_c"}, st(204))
	hook("/webhooks/vendor-a", bodyA("evt_c_after", "acct_a", "cus_c"), st(200))
	// erase customer not acknowledged
	hook("/webhooks/vendor-a", bodyA("evt_d", "acct_a", "cus_d"), st(200))
	add(map[string]any{"kind": "erase_customer", "tenant_id": "t_a", "customer_id": "cus_d"}, nil)
	// tenant erase
	hook("/webhooks/vendor-a", bodyA("evt_t2", "acct_b", "cus_x"), st(200))
	add(map[string]any{"kind": "erase_tenant", "tenant_id": "t_b"}, st(204))
	// unknown shop
	hook("/webhooks/vendor-b", bodyB("evt_unk", "zzz.shops.example", "cus_x"), st(200))
	// unknown shop unacknowledged -> ignored
	hook("/webhooks/vendor-b", bodyB("evt_unk2", "zzz.shops.example", "cus_x"), st(400))

	exp, err := check.Expected(reg, strings.NewReader(strings.Join(lines, "\n")+"\n"), resp)
	if err != nil {
		t.Fatal(err)
	}
	got := map[string]bool{}
	for id := range exp.Events["t_a"] {
		got[id] = true
	}
	want := map[string]bool{"evt_dup": true, "evt_d": true}
	if len(got) != len(want) || !got["evt_dup"] || !got["evt_d"] {
		t.Fatalf("t_a events = %v", got)
	}
	if len(exp.Events["t_b"]) != 0 {
		t.Fatalf("t_b events = %v", exp.Events["t_b"])
	}
	if !exp.ErasedTenants["t_b"] || exp.ErasedTenants["t_a"] {
		t.Fatalf("erased = %v", exp.ErasedTenants)
	}
	if exp.Unparsed != 1 {
		t.Fatalf("unparsed = %d", exp.Unparsed)
	}
}

func clean() store.Audit { return store.Audit{StateMatches: true, IndexMatches: true} }

func TestCompare(t *testing.T) {
	exp := check.Expectation{
		Events:        map[string]map[string]bool{"t1": {"e1": true, "e2": true}, "t2": {}},
		ErasedTenants: map[string]bool{"t3": true},
	}
	good := store.Audit{HotIDs: []string{"e1"}, ColdIDs: []string{"e2"}, StateMatches: true, IndexMatches: true}
	kinds := func(audits map[string]store.Audit, e check.Expectation) []string {
		var k []string
		for _, p := range check.Compare(e, audits) {
			if strings.Contains(p.Detail, "cus_") {
				t.Fatalf("detail leaks customer: %q", p.Detail)
			}
			k = append(k, p.Kind)
		}
		return k
	}
	one := func(name string, a store.Audit, want string) {
		t.Helper()
		got := kinds(map[string]store.Audit{"t1": a}, exp)
		if len(got) != 1 || got[0] != want {
			t.Errorf("%s: got %v want [%s]", name, got, want)
		}
	}
	if k := kinds(map[string]store.Audit{"t1": good, "t2": clean(), "t3": {Erased: true, StateMatches: true, IndexMatches: true}}, exp); len(k) != 0 {
		t.Fatalf("clean: %v", k)
	}
	one("lost", store.Audit{HotIDs: []string{"e1"}, StateMatches: true, IndexMatches: true}, "lost")
	one("unexpected", store.Audit{HotIDs: []string{"e1", "e9"}, ColdIDs: []string{"e2"}, StateMatches: true, IndexMatches: true}, "unexpected")
	one("duplicate", store.Audit{HotIDs: []string{"e1", "e2"}, ColdIDs: []string{"e2"}, StateMatches: true, IndexMatches: true}, "duplicate")
	one("bad", store.Audit{HotIDs: []string{"e1"}, ColdIDs: []string{"e2"}, BadPointers: []string{"t1/x"}, StateMatches: true, IndexMatches: true}, "bad_pointer")
	one("unref", store.Audit{HotIDs: []string{"e1"}, ColdIDs: []string{"e2"}, Unreferenced: []string{"t1/y"}, StateMatches: true, IndexMatches: true}, "unreferenced")
	one("garbage", store.Audit{HotIDs: []string{"e1"}, ColdIDs: []string{"e2"}, GarbageRows: 2, StateMatches: true, IndexMatches: true}, "garbage")
	one("dirty", store.Audit{HotIDs: []string{"e1"}, ColdIDs: []string{"e2"}, Dirty: true, StateMatches: true, IndexMatches: true}, "dirty")
	one("state", store.Audit{HotIDs: []string{"e1"}, ColdIDs: []string{"e2"}, IndexMatches: true}, "state_mismatch")
	one("index", store.Audit{HotIDs: []string{"e1"}, ColdIDs: []string{"e2"}, StateMatches: true}, "index_mismatch")
	one("tier", store.Audit{HotIDs: []string{"e1"}, ColdIDs: []string{"e2"}, StateMatches: true, IndexMatches: true,
		TierViolations: []string{"x"}}, "tier_invariant")
	// non-empty store for an erased tenant
	got := check.Compare(exp, map[string]store.Audit{"t3": {Erased: true, StateMatches: true, IndexMatches: true, ColdIDs: []string{"z"}}})
	if len(got) != 1 || got[0].Kind != "unexpected" {
		t.Errorf("erased non-empty: %v", got)
	}
	// unparsed
	e2 := exp
	e2.Unparsed = 3
	got = check.Compare(e2, map[string]store.Audit{"t1": good})
	if len(got) != 1 || got[0].Kind != "unparsed" || got[0].Tenant != "-" || got[0].Detail != "3" {
		t.Errorf("unparsed: %v", got)
	}
}

func TestUnsettled(t *testing.T) {
	exp := check.Expectation{Events: map[string]map[string]bool{"t1": {"e1": true}}}
	a := store.Audit{HotIDs: []string{"e1"}, Dirty: true} // StateMatches and IndexMatches false
	if got := check.Compare(exp, map[string]store.Audit{"t1": a}); len(got) != 3 {
		t.Fatalf("settled view: %v", got)
	}
	problems := check.Compare(exp, check.Unsettled(map[string]store.Audit{"t1": a}))
	if len(problems) != 1 || problems[0].Kind != "dirty" || check.Fatal(problems[0], true) || !check.Fatal(problems[0], false) {
		t.Fatalf("unsettled view: %v", problems)
	}
	for _, kind := range []string{"unreferenced", "garbage"} {
		if check.Fatal(check.Problem{Kind: kind}, true) {
			t.Errorf("%s must not fail unsettled", kind)
		}
	}
	for _, kind := range []string{"lost", "unexpected", "duplicate", "bad_pointer", "state_mismatch", "index_mismatch", "tier_invariant", "unparsed"} {
		if !check.Fatal(check.Problem{Kind: kind}, true) {
			t.Errorf("%s must fail unsettled", kind)
		}
	}
	// a clean tenant is not adjusted
	b := store.Audit{HotIDs: []string{"e1"}}
	if got := check.Compare(exp, check.Unsettled(map[string]store.Audit{"t1": b})); len(got) != 2 {
		t.Fatalf("clean tenant not adjusted: %v", got)
	}
}
