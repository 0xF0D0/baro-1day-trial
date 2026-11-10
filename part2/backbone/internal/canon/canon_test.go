package canon

import (
	"bytes"
	"encoding/json"
	"errors"
	"os"
	"reflect"
	"strings"
	"testing"
)

func decodeNum(t *testing.T, b []byte) any {
	t.Helper()
	d := json.NewDecoder(bytes.NewReader(b))
	d.UseNumber()
	var v any
	if err := d.Decode(&v); err != nil {
		t.Fatalf("decode %s: %v", b, err)
	}
	return v
}

func jsonEqual(t *testing.T, got, want []byte) {
	t.Helper()
	if !reflect.DeepEqual(decodeNum(t, got), decodeNum(t, want)) {
		t.Fatalf("json mismatch\n got: %s\nwant: %s", got, want)
	}
}

func TestNormalizationExamples(t *testing.T) {
	b, err := os.ReadFile("testdata/normalization_examples.json")
	if err != nil {
		t.Fatal(err)
	}
	var examples []struct {
		Vendor    string                     `json:"vendor"`
		Body      json.RawMessage            `json:"body"`
		Canonical map[string]json.RawMessage `json:"canonical"`
	}
	if err := json.Unmarshal(b, &examples); err != nil {
		t.Fatal(err)
	}
	if len(examples) != 7 {
		t.Fatalf("want 7 examples, got %d", len(examples))
	}
	for _, ex := range examples {
		var tenant string
		if err := json.Unmarshal(ex.Canonical["tenant_id"], &tenant); err != nil {
			t.Fatal(err)
		}
		var ev Event
		if ex.Vendor == "a" {
			ev, err = FromVendorA(ex.Body, tenant)
		} else {
			ev, err = FromVendorB(ex.Body, tenant)
		}
		if err != nil {
			t.Fatalf("%s: %v", ex.Body, err)
		}
		got, err := json.Marshal(ev)
		if err != nil {
			t.Fatal(err)
		}
		want, _ := json.Marshal(ex.Canonical)
		jsonEqual(t, got, want)
	}
}

func TestVendorAUnknownType(t *testing.T) {
	raw := []byte(`{"id":"evt_9","type":"payout.paid","created":1782950400123,"account":"acct_a","livemode":true,"data":{"object":{"customer_id":"cus_1","amount":5}}}`)
	ev, err := FromVendorA(raw, "t_1")
	if err != nil {
		t.Fatal(err)
	}
	if ev.Type != "payout.paid" || ev.CustomerID == nil || *ev.CustomerID != "cus_1" {
		t.Fatalf("bad event %+v", ev)
	}
	jsonEqual(t, ev.Data, []byte(`{"customer_id":"cus_1","amount":5}`))
}

func TestUnknownTypeWithoutCustomer(t *testing.T) {
	raw := []byte(`{"event_uuid":"u1","event":"shop.note","shop_domain":"x.shops.example","timestamp":"2026-07-01T12:00:00.123Z","api_version":"1","payload":{"text":"x"}}`)
	ev, err := FromVendorB(raw, "t_1")
	if err != nil {
		t.Fatal(err)
	}
	if ev.CustomerID != nil {
		t.Fatalf("want nil customer, got %v", *ev.CustomerID)
	}
	out, _ := json.Marshal(ev)
	if !strings.Contains(string(out), `"customer_id":null`) {
		t.Fatalf("customer_id not null: %s", out)
	}
}

func TestEmptyLinesEncodeAsArray(t *testing.T) {
	raw := []byte(`{"id":"e1","type":"order.created","created":1,"account":"a","livemode":true,"data":{"object":{"order_id":"o1","customer":{"id":"c1","email":"e","name":"n"},"line_items":[]}}}`)
	ev, err := FromVendorA(raw, "t_1")
	if err != nil {
		t.Fatal(err)
	}
	out, _ := json.Marshal(ev)
	if !strings.Contains(string(out), `"lines":[]`) {
		t.Fatalf("lines not []: %s", out)
	}
}

func TestVendorBTimestamp(t *testing.T) {
	raw := []byte(`{"event_uuid":"u1","event":"shop.note","shop_domain":"x","timestamp":"2026-07-01T12:00:00.123Z","api_version":"1","payload":{}}`)
	ev, err := FromVendorB(raw, "t_1")
	if err != nil {
		t.Fatal(err)
	}
	if ev.OccurredAtMs != 1782907200123 {
		t.Fatalf("got %d", ev.OccurredAtMs)
	}
}

func TestMalformed(t *testing.T) {
	order := func(qty string) string {
		return `{"id":"e1","type":"order.created","created":1,"account":"a","livemode":true,"data":{"object":{"order_id":"o1","customer":{"id":"c1","email":"e","name":"n"},"line_items":[{"sku":"s","quantity":` + qty + `,"unit_amount":1}]}}}`
	}
	cases := map[string]func() error{
		"A created 1.5": func() error {
			_, err := FromVendorA([]byte(`{"id":"e","type":"ads.metric","created":1.5,"account":"a","data":{"object":{}}}`), "t")
			return err
		},
		"A order without line_items": func() error {
			_, err := FromVendorA([]byte(`{"id":"e1","type":"order.created","created":1,"account":"a","data":{"object":{"order_id":"o1","customer":{"id":"c1","email":"e","name":"n"}}}}`), "t")
			return err
		},
		"B bad timestamp": func() error {
			_, err := FromVendorB([]byte(`{"event_uuid":"u","event":"x","shop_domain":"s","timestamp":"2026-07-01 12:00","payload":{}}`), "t")
			return err
		},
		"B non-Z timestamp": func() error {
			_, err := FromVendorB([]byte(`{"event_uuid":"u","event":"x","shop_domain":"s","timestamp":"2026-07-01T12:00:00.123+00:00","payload":{}}`), "t")
			return err
		},
		"A qty 2.5":    func() error { _, err := FromVendorA([]byte(order("2.5")), "t"); return err },
		"A qty string": func() error { _, err := FromVendorA([]byte(order(`"2"`)), "t"); return err },
		"not json":     func() error { _, err := FromVendorA([]byte(`nope`), "t"); return err },
	}
	for name, f := range cases {
		if err := f(); !errors.Is(err, ErrMalformed) {
			t.Errorf("%s: want ErrMalformed, got %v", name, err)
		}
	}
}

func TestLessIsBytewise(t *testing.T) {
	ev := func(ms int64, id string) Event { return Event{EventID: id, OccurredAtMs: ms} }
	if !Less(ev(5, "0f0e8a6c-aaaa"), ev(5, "evt_a")) {
		t.Error("uuid should sort before evt_")
	}
	if !Less(ev(5, "evt_a-1"), ev(5, "evt_a_1")) {
		t.Error("'-' should sort before '_'")
	}
	if !Less(ev(4, "zzz"), ev(5, "aaa")) {
		t.Error("smaller time first")
	}
	evs := []Event{ev(5, "evt_a_1"), ev(5, "evt_a-1"), ev(1, "z")}
	Sort(evs)
	if evs[0].EventID != "z" || evs[1].EventID != "evt_a-1" {
		t.Errorf("bad sort %+v", evs)
	}
}

func TestNullStringIsMalformed(t *testing.T) {
	raw := []byte(`{"event_uuid":null,"event":"x","shop_domain":"s","timestamp":"2026-07-01T12:00:00.123Z","payload":{}}`)
	if _, err := FromVendorB(raw, "t"); !errors.Is(err, ErrMalformed) {
		t.Fatalf("got %v", err)
	}
}

func TestUnknownTypeNullCustomer(t *testing.T) {
	raw := []byte(`{"event_uuid":"u1","event":"shop.note","shop_domain":"x","timestamp":"2026-07-01T12:00:00.123Z","api_version":"1","payload":{"customer_id":null,"text":"x"}}`)
	ev, err := FromVendorB(raw, "t_1")
	if err != nil {
		t.Fatal(err)
	}
	if ev.CustomerID != nil {
		t.Fatalf("want nil customer, got %q", *ev.CustomerID)
	}
	out, _ := json.Marshal(ev)
	if !strings.Contains(string(out), `"customer_id":null`) {
		t.Fatalf("customer_id not null: %s", out)
	}
}

func TestMalformedErrorsCarryNoInput(t *testing.T) {
	const leak = "LEAK_7f3a"
	a := []string{
		`{"id":"evt_1","type":"x","created":"` + leak + `","data":{"object":{}}}`,
		`{"id":"evt_1","type":"x","created":12` + leak + `,"data":{"object":{}}}`,
		`{"id":{"x":"` + leak + `"},"type":"x","created":1,"data":{"object":{}}}`,
		`{"id":"evt_1","type":` + leak + `}`,
		`{"id":"evt_1","type":"ads.metric","created":1,"data":{"object":{"campaign_id":"c","spend":"` + leak + `","impressions":1,"clicks":1}}}`,
		`{"id":"evt_1","type":"ads.metric","created":1,"data":{"object":{"campaign_id":{"x":"` + leak + `"},"spend":1,"impressions":1,"clicks":1}}}`,
	}
	b := []string{
		`{"event_uuid":"u1","event":"x","timestamp":"` + leak + `","payload":{}}`,
		`{"event_uuid":"u1","event":"x","timestamp":"2026-07-01T00:00:00.000+09:00` + leak + `","payload":{}}`,
		`{"event_uuid":"u1","event":"x","timestamp":"2026-07-01T00:00:00.000` + leak + `Z","payload":{}}`,
		`{"event_uuid":"u1","event":"x","timestamp":"2026-07-01T00:00:00.000+09:00","payload":{}}`,
		`{"event_uuid":"u1","event":"x","timestamp":"2026-07-01T00:00:00Z","payload":` + leak + `}`,
	}
	check := func(name, body string, f func([]byte, string) (Event, error)) {
		_, err := f([]byte(body), "t1")
		if !errors.Is(err, ErrMalformed) {
			t.Errorf("%s %s: want ErrMalformed, got %v", name, body, err)
			return
		}
		if strings.Contains(err.Error(), leak) {
			t.Errorf("%s %s: error carries input: %v", name, body, err)
		}
	}
	for _, s := range a {
		check("A", s, FromVendorA)
	}
	for _, s := range b {
		check("B", s, FromVendorB)
	}
}

func TestNulInEventIDRejected(t *testing.T) {
	_, err := FromVendorA([]byte(`{"id":"evt_\u0000x","type":"x","created":1,"data":{"object":{}}}`), "t1")
	if !errors.Is(err, ErrMalformed) {
		t.Errorf("vendor A: want ErrMalformed, got %v", err)
	}
	_, err = FromVendorB([]byte(`{"event_uuid":"evt_\u0000x","event":"x","timestamp":"2026-07-01T00:00:00Z","payload":{}}`), "t1")
	if !errors.Is(err, ErrMalformed) {
		t.Errorf("vendor B: want ErrMalformed, got %v", err)
	}
}
