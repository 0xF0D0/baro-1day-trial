package fold

import (
	"sort"

	"backbone/internal/canon"
)

const msPerDay = 86_400_000

// Day returns the UTC day number of a millisecond timestamp, rounding down.
func Day(ms int64) int64 {
	d := ms / msPerDay
	if ms%msPerDay < 0 {
		d--
	}
	return d
}

// OrderState is one order in a Snapshot.
type OrderState struct {
	Gross    int64  `json:"gross"`
	Refunded int64  `json:"refunded"`
	Status   string `json:"status"`
}

// Snapshot is the serializable state of a fold. Its maps are never nil.
type Snapshot struct {
	EventCount       int64                 `json:"event_count"`
	Customers        []string              `json:"customers"`
	Orders           map[string]OrderState `json:"orders"`
	Inventory        map[string]int64      `json:"inventory"`
	Oversold         map[string]int64      `json:"oversold"`
	Messages         map[string]int64      `json:"messages_by_channel"`
	LastMessageByDay map[int64]int64       `json:"last_message_by_day"`
	Campaigns        map[string]Campaign   `json:"campaigns"`
	OrphanRefunds    int64                 `json:"orphan_refunds"`
	OrphanShipments  int64                 `json:"orphan_shipments"`
}

// Move is one inventory movement. Kind "adjust" is an inventory.adjusted delta
// (LineNo 0); "order" is one line of a winning order.created (Amount is the
// qty, LineNo the line index).
type Move struct {
	SKU    string
	Kind   string
	Amount int64
	LineNo int
}

func copyMap[K comparable, V any](m map[K]V) map[K]V {
	out := make(map[K]V, len(m))
	for k, v := range m {
		out[k] = v
	}
	return out
}

// Snapshot captures the state. It does not mutate s.
func (s *State) Snapshot() Snapshot {
	snap := Snapshot{
		EventCount:       s.eventCount,
		Customers:        make([]string, 0, len(s.customers)),
		Orders:           make(map[string]OrderState, len(s.orders)),
		Inventory:        copyMap(s.inventory),
		Oversold:         copyMap(s.oversold),
		Messages:         copyMap(s.messages),
		LastMessageByDay: copyMap(s.dayMax),
		Campaigns:        copyMap(s.campaigns),
		OrphanRefunds:    s.orphanRefunds,
		OrphanShipments:  s.orphanShipments,
	}
	for c := range s.customers {
		snap.Customers = append(snap.Customers, c)
	}
	sort.Strings(snap.Customers)
	for id, o := range s.orders {
		snap.Orders[id] = OrderState{Gross: o.gross, Refunded: o.refunded, Status: o.status}
	}
	return snap
}

// Restore rebuilds a State from a snapshot (nil maps in snap are tolerated).
func Restore(tenantID string, customerKey func(string) string, snap Snapshot) *State {
	s := New(tenantID, customerKey)
	s.eventCount = snap.EventCount
	for _, c := range snap.Customers {
		s.customers[c] = struct{}{}
	}
	for id, o := range snap.Orders {
		s.orders[id] = &order{gross: o.Gross, refunded: o.Refunded, status: o.Status}
	}
	for k, v := range snap.Inventory {
		s.inventory[k] = v
	}
	for k, v := range snap.Oversold {
		s.oversold[k] = v
	}
	for k, v := range snap.Messages {
		s.messages[k] = v
	}
	for k, v := range snap.LastMessageByDay {
		s.dayMax[k] = v
	}
	for k, v := range snap.Campaigns {
		s.campaigns[k] = v
	}
	s.orphanRefunds = snap.OrphanRefunds
	s.orphanShipments = snap.OrphanShipments
	return s
}

// RefoldSKU replays one SKU's movements from zero with the reducer's clamp
// rules and returns the resulting stock and oversold units.
func RefoldSKU(moves []Move) (stock, oversold int64) {
	for _, m := range moves {
		if m.Kind == "adjust" {
			stock = max(0, stock+m.Amount)
			continue
		}
		take := min(stock, m.Amount)
		stock -= take
		oversold += m.Amount - take
	}
	return stock, oversold
}

// foldRemoved folds the removed events alone (sorted copy) into a fresh state
// and returns it with the movements it applied.
func foldRemoved(removed []canon.Event) (*State, []Move) {
	sorted := append([]canon.Event(nil), removed...)
	canon.Sort(sorted)
	x := New("", func(c string) string { return c })
	var moves []Move
	for _, e := range sorted {
		moves = append(moves, x.ApplyMoves(e)...)
	}
	return x, moves
}

// AffectedSKUs returns the sorted SKUs that the removed events move.
func AffectedSKUs(removed []canon.Event) []string {
	_, moves := foldRemoved(removed)
	set := map[string]struct{}{}
	for _, m := range moves {
		set[m.SKU] = struct{}{}
	}
	out := make([]string, 0, len(set))
	for k := range set {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

// AffectedDays returns the sorted UTC days of the removed message.received
// events that count in the fold.
func AffectedDays(removed []canon.Event) []int64 {
	x, _ := foldRemoved(removed)
	out := make([]int64, 0, len(x.dayMax))
	for d := range x.dayMax {
		out = append(out, d)
	}
	sort.Slice(out, func(i, j int) bool { return out[i] < out[j] })
	return out
}

// RemoveCustomer returns snap minus the events of one customer. removed is
// every snapshotted event of that customer; skuMoves holds the remaining
// movements (in key order) of every SKU in AffectedSKUs(removed); dayMax holds
// the latest remaining message.received time of every day in
// AffectedDays(removed), nil when none is left. Campaign keys are kept even
// when their sums reach zero: canonical ad.metric events carry no customer, so
// a customer shows up in a campaign only through a cross-vendor event, and
// whether such a key would survive the removal is not tracked.
func RemoveCustomer(snap Snapshot, customerKey string, removed []canon.Event,
	skuMoves map[string][]Move, dayMax map[int64]*int64) Snapshot {
	x, _ := foldRemoved(removed)
	out := Snapshot{
		EventCount:       snap.EventCount - x.eventCount,
		Customers:        make([]string, 0, len(snap.Customers)),
		Orders:           copyMap(snap.Orders),
		Inventory:        copyMap(snap.Inventory),
		Oversold:         copyMap(snap.Oversold),
		Messages:         copyMap(snap.Messages),
		LastMessageByDay: copyMap(snap.LastMessageByDay),
		Campaigns:        copyMap(snap.Campaigns),
		OrphanRefunds:    snap.OrphanRefunds - x.orphanRefunds,
		OrphanShipments:  snap.OrphanShipments - x.orphanShipments,
	}
	for _, c := range snap.Customers {
		if c != customerKey {
			out.Customers = append(out.Customers, c)
		}
	}
	for id := range x.orders {
		delete(out.Orders, id)
	}
	for ch, n := range x.messages {
		out.Messages[ch] -= n
		if out.Messages[ch] <= 0 {
			delete(out.Messages, ch)
		}
	}
	for id, c := range x.campaigns {
		cur := out.Campaigns[id]
		cur.SpendCents -= c.SpendCents
		cur.Impressions -= c.Impressions
		cur.Clicks -= c.Clicks
		out.Campaigns[id] = cur
	}
	for day, v := range dayMax {
		if v == nil {
			delete(out.LastMessageByDay, day)
		} else {
			out.LastMessageByDay[day] = *v
		}
	}
	for _, sku := range AffectedSKUs(removed) {
		ms := skuMoves[sku]
		if len(ms) == 0 {
			delete(out.Inventory, sku)
			delete(out.Oversold, sku)
			continue
		}
		stock, over := RefoldSKU(ms)
		out.Inventory[sku] = stock
		if over != 0 {
			out.Oversold[sku] = over
		} else {
			delete(out.Oversold, sku)
		}
	}
	return out
}
