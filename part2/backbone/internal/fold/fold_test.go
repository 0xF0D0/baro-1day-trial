package fold

import (
	"bufio"
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"testing"

	"backbone/internal/canon"
)

func identity(s string) string { return s }

type fixture struct {
	name   string
	events []canon.Event
	exp    []byte
	tid    string
}

func loadFixtures(t *testing.T) []fixture {
	t.Helper()
	files, err := filepath.Glob("testdata/*.events.jsonl")
	if err != nil || len(files) == 0 {
		t.Fatalf("no fixtures: %v", err)
	}
	var out []fixture
	for _, f := range files {
		name := strings.TrimSuffix(filepath.Base(f), ".events.jsonl")
		fh, err := os.Open(f)
		if err != nil {
			t.Fatal(err)
		}
		var events []canon.Event
		sc := bufio.NewScanner(fh)
		sc.Buffer(make([]byte, 1<<20), 1<<20)
		for sc.Scan() {
			var e canon.Event
			if err := json.Unmarshal(sc.Bytes(), &e); err != nil {
				t.Fatalf("%s: %v", f, err)
			}
			events = append(events, e)
		}
		fh.Close()
		if err := sc.Err(); err != nil {
			t.Fatal(err)
		}
		exp, err := os.ReadFile("testdata/" + name + ".expected.json")
		if err != nil {
			t.Fatal(err)
		}
		var head struct {
			TenantID string `json:"tenant_id"`
		}
		if err := json.Unmarshal(exp, &head); err != nil {
			t.Fatal(err)
		}
		out = append(out, fixture{name, events, exp, head.TenantID})
	}
	return out
}

func decodeAny(t *testing.T, b []byte) any {
	t.Helper()
	d := json.NewDecoder(bytes.NewReader(b))
	d.UseNumber()
	var v any
	if err := d.Decode(&v); err != nil {
		t.Fatalf("decode %s: %v", b, err)
	}
	return v
}

func jsonEqual(t *testing.T, got any, want []byte) {
	t.Helper()
	g, err := json.Marshal(got)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(decodeAny(t, g), decodeAny(t, want)) {
		t.Fatalf("mismatch\n got: %s\nwant: %s", g, want)
	}
}

func TestFoldMatchesReducer(t *testing.T) {
	for _, f := range loadFixtures(t) {
		t.Run(f.name, func(t *testing.T) {
			got, err := Fold(f.tid, f.events, identity)
			if err != nil {
				t.Fatal(err)
			}
			jsonEqual(t, got, f.exp)
		})
	}
}

func TestApplyContinuesFromAnyPoint(t *testing.T) {
	for _, f := range loadFixtures(t) {
		t.Run(f.name, func(t *testing.T) {
			sorted := append([]canon.Event(nil), f.events...)
			canon.Sort(sorted)
			n := len(sorted)
			ks := map[int]bool{}
			for _, k := range []int{0, 1, n / 3, n / 2, n - 1, n} {
				if k >= 0 && k <= n {
					ks[k] = true
				}
			}
			var points []int
			for k := range ks {
				points = append(points, k)
			}
			sort.Ints(points)
			want, err := Fold(f.tid, f.events, identity)
			if err != nil {
				t.Fatal(err)
			}
			for _, k := range points {
				s := New(f.tid, identity)
				for _, e := range sorted[:k] {
					if err := s.Apply(e); err != nil {
						t.Fatal(err)
					}
				}
				_ = s.Result()
				_ = s.Result()
				for _, e := range sorted[k:] {
					if err := s.Apply(e); err != nil {
						t.Fatal(err)
					}
				}
				wb, _ := json.Marshal(want)
				jsonEqual(t, s.Result(), wb)
			}
		})
	}
}

func TestEmptyResultShape(t *testing.T) {
	r, err := Fold("t_edge", nil, identity)
	if err != nil {
		t.Fatal(err)
	}
	b, _ := json.Marshal(r)
	s := string(b)
	for _, want := range []string{`"inventory":{}`, `"campaigns":{}`, `"shipment_status_counts":{}`,
		`"messages_by_channel":{}`, `"last_contact_ms":null`} {
		if !strings.Contains(s, want) {
			t.Errorf("missing %s in %s", want, s)
		}
	}
	if n := strings.Count(s, "null"); n != 1 {
		t.Errorf("want exactly one null, got %d in %s", n, s)
	}
}

func TestUnreadableKnownTypeCountsAsUnknown(t *testing.T) {
	cases := []struct{ name, typ, data string }{
		{"order without lines", "order.created", `{"order_id":"o1"}`},
		{"order lines object", "order.created", `{"order_id":"o1","lines":{"sku":"a"}}`},
		{"order line missing qty", "order.created", `{"order_id":"o1","lines":[{"sku":"a","unit_cents":5}]}`},
		{"refund without order_id", "order.refunded", `{"amount_cents":5}`},
		{"shipment without order_id", "shipment.updated", `{"status":"shipped"}`},
		{"inventory delta string", "inventory.adjusted", `{"sku":"a","delta":"3"}`},
		{"message without channel", "message.received", `{"from":"x"}`},
		{"ad without clicks", "ad.metric", `{"campaign_id":"c","spend_cents":1,"impressions":2}`},
	}
	want, err := Fold("t_x", nil, identity)
	if err != nil {
		t.Fatal(err)
	}
	want.EventCount, want.CustomerCount = 1, 1
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			cus := "cus_1"
			e := canon.Event{EventID: "e1", Type: c.typ, CustomerID: &cus, Data: json.RawMessage(c.data)}
			got, err := Fold("t_x", []canon.Event{e}, identity)
			if err != nil {
				t.Fatal(err)
			}
			if !reflect.DeepEqual(got, want) {
				t.Fatalf("got %+v, want %+v", got, want)
			}
		})
	}
}

func TestRefundAndShipmentWithExistingOrderAndMissingField(t *testing.T) {
	events := []canon.Event{
		{EventID: "e1", OccurredAtMs: 1, Type: "order.created",
			Data: json.RawMessage(`{"order_id":"o1","lines":[{"sku":"A","qty":1,"unit_cents":100}]}`)},
		{EventID: "e2", OccurredAtMs: 2, Type: "order.refunded", Data: json.RawMessage(`{"order_id":"o1"}`)},
		{EventID: "e3", OccurredAtMs: 3, Type: "shipment.updated", Data: json.RawMessage(`{"order_id":"o1"}`)},
	}
	got, err := Fold("t_x", events, identity)
	if err != nil {
		t.Fatal(err)
	}
	if got.EventCount != 3 || got.RefundedCents != 0 || got.OrphanRefunds != 0 || got.OrphanShipments != 0 {
		t.Fatalf("got %+v", got)
	}
	if !reflect.DeepEqual(got.ShipmentStatusCounts, map[string]int64{"unfulfilled": 1}) {
		t.Fatalf("shipment_status_counts = %v", got.ShipmentStatusCounts)
	}
}

func TestWellFormedCrossVendorEventApplies(t *testing.T) {
	events := []canon.Event{
		{EventID: "e1", OccurredAtMs: 1, Type: "order.created", Data: json.RawMessage(`{"order_id":"o1","lines":[]}`)},
		{EventID: "e2", OccurredAtMs: 2, Type: "shipment.updated",
			Data: json.RawMessage(`{"order_id":"o1","status":"shipped","carrier":"x","note":"y"}`)},
	}
	got, err := Fold("t_x", events, identity)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(got.ShipmentStatusCounts, map[string]int64{"shipped": 1}) {
		t.Fatalf("shipment_status_counts = %v", got.ShipmentStatusCounts)
	}
}
