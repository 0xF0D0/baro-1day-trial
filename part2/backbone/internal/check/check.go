// Package check proves, after a chaos run, that storage holds exactly the
// events the replay had acknowledged.
package check

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"sort"

	"backbone/internal/canon"
	"backbone/internal/store"
	"backbone/internal/tenants"
	"backbone/internal/webhook"
)

// Expectation is what storage must hold after the replay.
type Expectation struct {
	Events        map[string]map[string]bool // tenant -> event IDs that must be stored
	ErasedTenants map[string]bool
	Unparsed      int // acknowledged webhook deliveries whose tenant or event could not be resolved
}

type row struct {
	Seq        int             `json:"seq"`
	Kind       string          `json:"kind"`
	Path       string          `json:"path"`
	Body       json.RawMessage `json:"body"`
	TenantID   string          `json:"tenant_id"`
	CustomerID string          `json:"customer_id"`
}

func acknowledged(responses map[string]*int, seq int) bool {
	s := responses[fmt.Sprint(seq)]
	return s != nil && *s >= 200 && *s <= 299
}

// Expected reads deliveries (JSON lines, already decompressed) and the replay
// responses. The expected set is every acknowledged webhook event, minus the
// events of customers whose erasure was acknowledged, minus every event of
// tenants whose erasure was acknowledged.
func Expected(reg *tenants.Registry, deliveries io.Reader, responses map[string]*int) (Expectation, error) {
	exp := Expectation{Events: map[string]map[string]bool{}, ErasedTenants: map[string]bool{}}
	custOf := map[string]map[string]string{} // tenant -> event ID -> customer ("" if none)
	erasedCust := map[string]map[string]bool{}

	sc := bufio.NewScanner(deliveries)
	sc.Buffer(make([]byte, 1<<20), 16<<20)
	for sc.Scan() {
		line := bytes.TrimSpace(sc.Bytes())
		if len(line) == 0 {
			continue
		}
		var r row
		if err := json.Unmarshal(line, &r); err != nil {
			return exp, fmt.Errorf("check: bad delivery row: %w", err)
		}
		if !acknowledged(responses, r.Seq) {
			continue
		}
		switch r.Kind {
		case "webhook":
			var body []byte
			var s string
			if json.Unmarshal(r.Body, &s) == nil {
				body = []byte(s)
			} else {
				body = r.Body
			}
			tenantID, ev, ok := resolve(reg, r.Path, body)
			if !ok {
				exp.Unparsed++
				continue
			}
			if custOf[tenantID] == nil {
				custOf[tenantID] = map[string]string{}
			}
			c := ""
			if ev.CustomerID != nil {
				c = *ev.CustomerID
			}
			custOf[tenantID][ev.EventID] = c
		case "erase_customer":
			if erasedCust[r.TenantID] == nil {
				erasedCust[r.TenantID] = map[string]bool{}
			}
			erasedCust[r.TenantID][r.CustomerID] = true
		case "erase_tenant":
			exp.ErasedTenants[r.TenantID] = true
		}
	}
	if err := sc.Err(); err != nil {
		return exp, fmt.Errorf("check: read deliveries: %w", err)
	}
	for tenantID, evs := range custOf {
		if exp.ErasedTenants[tenantID] {
			continue
		}
		set := map[string]bool{}
		for id, c := range evs {
			if c != "" && erasedCust[tenantID][c] {
				continue
			}
			set[id] = true
		}
		exp.Events[tenantID] = set
	}
	return exp, nil
}

func resolve(reg *tenants.Registry, path string, raw []byte) (string, canon.Event, bool) {
	var ev canon.Event
	switch path {
	case "/webhooks/vendor-a":
		acct, err := webhook.PeekAccount(raw)
		if err != nil || acct == "" {
			return "", ev, false
		}
		t, ok := reg.ByAccount(acct)
		if !ok {
			return "", ev, false
		}
		ev, err = canon.FromVendorA(raw, t.ID)
		return t.ID, ev, err == nil
	case "/webhooks/vendor-b":
		dom, err := webhook.PeekShopDomain(raw)
		if err != nil || dom == "" {
			return "", ev, false
		}
		t, ok := reg.ByShopDomain(dom)
		if !ok {
			return "", ev, false
		}
		ev, err = canon.FromVendorB(raw, t.ID)
		return t.ID, ev, err == nil
	}
	return "", ev, false
}

// Problem is one inconsistency. Detail is an event ID, an object name or a
// count; never a customer ID.
type Problem struct {
	Tenant string
	Kind   string // lost, unexpected, duplicate, bad_pointer, unreferenced, garbage, dirty, state_mismatch, index_mismatch, tier_invariant, unparsed
	Detail string
}

// Compare checks every audited tenant against the expectation.
func Compare(exp Expectation, audits map[string]store.Audit) []Problem {
	var out []Problem
	if exp.Unparsed > 0 {
		out = append(out, Problem{"-", "unparsed", fmt.Sprint(exp.Unparsed)})
	}
	tenantIDs := make([]string, 0, len(audits))
	for id := range audits {
		tenantIDs = append(tenantIDs, id)
	}
	sort.Strings(tenantIDs)
	for _, id := range tenantIDs {
		a := audits[id]
		add := func(kind, detail string) { out = append(out, Problem{id, kind, detail}) }
		want := exp.Events[id]
		if exp.ErasedTenants[id] {
			want = nil
			if !a.Erased {
				add("unexpected", "tenant not erased")
			}
		}
		count := map[string]int{}
		for _, e := range a.HotIDs {
			count[e]++
		}
		for _, e := range a.ColdIDs {
			count[e]++
		}
		stored := make([]string, 0, len(count))
		for e := range count {
			stored = append(stored, e)
		}
		sort.Strings(stored)
		for _, e := range stored {
			if count[e] > 1 {
				add("duplicate", e)
			}
			if !want[e] {
				add("unexpected", e)
			}
		}
		wanted := make([]string, 0, len(want))
		for e := range want {
			wanted = append(wanted, e)
		}
		sort.Strings(wanted)
		for _, e := range wanted {
			if count[e] == 0 {
				add("lost", e)
			}
		}
		for _, o := range a.BadPointers {
			add("bad_pointer", o)
		}
		for _, o := range a.Unreferenced {
			add("unreferenced", o)
		}
		if a.GarbageRows > 0 {
			add("garbage", fmt.Sprint(a.GarbageRows))
		}
		if a.Dirty {
			add("dirty", "")
		}
		if !a.StateMatches {
			add("state_mismatch", "")
		}
		if !a.IndexMatches {
			add("index_mismatch", "")
		}
		for _, v := range a.TierViolations {
			add("tier_invariant", v)
		}
	}
	return out
}

// Unsettled adjusts audits for a check made before the settle. A dirty tenant
// still has late hot rows, so its state and index comparisons are not
// meaningful and are treated as matching.
func Unsettled(audits map[string]store.Audit) map[string]store.Audit {
	out := make(map[string]store.Audit, len(audits))
	for id, a := range audits {
		if a.Dirty {
			a.StateMatches = true
			a.IndexMatches = true
		}
		out[id] = a
	}
	return out
}

// Fatal reports whether a problem fails the check. Before the settle,
// leftovers that the settle exists to remove (a dirty tenant, unreferenced
// objects, garbage rows) are counted but do not fail it.
func Fatal(p Problem, unsettled bool) bool {
	if unsettled {
		switch p.Kind {
		case "dirty", "unreferenced", "garbage":
			return false
		}
	}
	return true
}
