package fold

import (
	"encoding/json"
	"sort"
	"testing"

	"backbone/internal/canon"
)

func sortedCopy(events []canon.Event) []canon.Event {
	s := append([]canon.Event(nil), events...)
	canon.Sort(s)
	return s
}

func TestDayFloors(t *testing.T) {
	for in, want := range map[int64]int64{0: 0, 86_399_999: 0, 86_400_000: 1, -1: -1, -86_400_000: -1, -86_400_001: -2} {
		if got := Day(in); got != want {
			t.Errorf("Day(%d) = %d, want %d", in, got, want)
		}
	}
}

func TestSnapshotRestoreRoundTrip(t *testing.T) {
	for _, f := range loadFixtures(t) {
		t.Run(f.name, func(t *testing.T) {
			sorted := sortedCopy(f.events)
			n := len(sorted)
			want, err := Fold(f.tid, f.events, identity)
			if err != nil {
				t.Fatal(err)
			}
			wb, _ := json.Marshal(want)
			for _, k := range []int{0, n / 2, n} {
				s := New(f.tid, identity)
				for _, e := range sorted[:k] {
					s.Apply(e)
				}
				b, err := json.Marshal(s.Snapshot())
				if err != nil {
					t.Fatal(err)
				}
				var snap Snapshot
				if err := json.Unmarshal(b, &snap); err != nil {
					t.Fatal(err)
				}
				r := Restore(f.tid, identity, snap)
				for _, e := range sorted[k:] {
					r.Apply(e)
				}
				jsonEqual(t, r.Result(), wb)
			}
		})
	}
}

func TestSnapshotDoesNotMutateAndHasNoNilMaps(t *testing.T) {
	snap := New("t", identity).Snapshot()
	b, _ := json.Marshal(snap)
	want := `{"event_count":0,"customers":[],"orders":{},"inventory":{},"oversold":{},"messages_by_channel":{},"last_message_by_day":{},"campaigns":{},"orphan_refunds":0,"orphan_shipments":0}`
	if string(b) != want {
		t.Fatalf("got %s", b)
	}
}

func groupMoves(events []canon.Event) map[string][]Move {
	s := New("t", identity)
	out := map[string][]Move{}
	for _, e := range events {
		for _, m := range s.ApplyMoves(e) {
			out[m.SKU] = append(out[m.SKU], m)
		}
	}
	return out
}

func TestApplyMovesMatchesRefold(t *testing.T) {
	for _, f := range loadFixtures(t) {
		t.Run(f.name, func(t *testing.T) {
			sorted := sortedCopy(f.events)
			s := New(f.tid, identity)
			by := map[string][]Move{}
			for _, e := range sorted {
				for _, m := range s.ApplyMoves(e) {
					by[m.SKU] = append(by[m.SKU], m)
				}
			}
			res, snap := s.Result(), s.Snapshot()
			if len(by) != len(res.Inventory) {
				t.Fatalf("moved SKUs %d, inventory SKUs %d", len(by), len(res.Inventory))
			}
			for sku, ms := range by {
				stock, over := RefoldSKU(ms)
				if stock != res.Inventory[sku] || over != snap.Oversold[sku] {
					t.Errorf("%s: refold (%d,%d), state (%d,%d)", sku, stock, over, res.Inventory[sku], snap.Oversold[sku])
				}
			}
		})
	}
}

func TestRemoveCustomerMatchesFoldWithoutThem(t *testing.T) {
	for _, f := range loadFixtures(t) {
		if f.name != "t_0016" && f.name != "t_0018" {
			continue
		}
		sorted := sortedCopy(f.events)
		count := map[string]int{}
		for _, e := range sorted {
			if e.CustomerID != nil {
				count[*e.CustomerID]++
			}
		}
		var ids []string
		for id := range count {
			ids = append(ids, id)
		}
		sort.Slice(ids, func(i, j int) bool {
			if count[ids[i]] != count[ids[j]] {
				return count[ids[i]] > count[ids[j]]
			}
			return ids[i] < ids[j]
		})
		if len(ids) > 5 {
			ids = ids[:5]
		}
		if len(ids) == 0 {
			t.Fatalf("%s: no customers", f.name)
		}
		full := New(f.tid, identity)
		for _, e := range sorted {
			full.Apply(e)
		}
		snap := full.Snapshot()
		for _, id := range ids {
			t.Run(f.name+"/"+id, func(t *testing.T) {
				var removed, rest []canon.Event
				for _, e := range sorted {
					if e.CustomerID != nil && *e.CustomerID == id {
						removed = append(removed, e)
					} else {
						rest = append(rest, e)
					}
				}
				all := groupMoves(rest)
				moves := map[string][]Move{}
				for _, sku := range AffectedSKUs(removed) {
					moves[sku] = all[sku]
				}
				dayMax := map[int64]*int64{}
				for _, d := range AffectedDays(removed) {
					dayMax[d] = nil
				}
				for _, e := range rest {
					if e.Type != "message.received" {
						continue
					}
					var d struct {
						Channel *string `json:"channel"`
					}
					if json.Unmarshal(e.Data, &d) != nil || d.Channel == nil {
						continue
					}
					day := Day(e.OccurredAtMs)
					if cur, ok := dayMax[day]; ok && (cur == nil || e.OccurredAtMs > *cur) {
						v := e.OccurredAtMs
						dayMax[day] = &v
					}
				}
				got := Restore(f.tid, identity, RemoveCustomer(snap, id, removed, moves, dayMax)).Result()
				want, err := Fold(f.tid, rest, identity)
				if err != nil {
					t.Fatal(err)
				}
				wb, _ := json.Marshal(want)
				jsonEqual(t, got, wb)
			})
		}
	}
}
