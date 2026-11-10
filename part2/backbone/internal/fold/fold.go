// Package fold is a port of the reference reducer: it folds a tenant's canonical
// events, applied in canon.Less order, into the public state.
package fold

import (
	"encoding/json"

	"backbone/internal/canon"
)

// Campaign is the running total of one ad campaign.
type Campaign struct {
	SpendCents  int64 `json:"spend_cents"`
	Impressions int64 `json:"impressions"`
	Clicks      int64 `json:"clicks"`
}

// Result is the tenant state, with the reducer's 16 keys. Its maps are never nil.
type Result struct {
	TenantID             string              `json:"tenant_id"`
	EventCount           int64               `json:"event_count"`
	OrderCount           int64               `json:"order_count"`
	GrossCents           int64               `json:"gross_cents"`
	RefundedCents        int64               `json:"refunded_cents"`
	NetCents             int64               `json:"net_cents"`
	OpenOrders           int64               `json:"open_orders"`
	ShipmentStatusCounts map[string]int64    `json:"shipment_status_counts"`
	Inventory            map[string]int64    `json:"inventory"`
	OversoldUnits        int64               `json:"oversold_units"`
	CustomerCount        int64               `json:"customer_count"`
	MessagesByChannel    map[string]int64    `json:"messages_by_channel"`
	LastContactMs        *int64              `json:"last_contact_ms"`
	Campaigns            map[string]Campaign `json:"campaigns"`
	OrphanRefunds        int64               `json:"orphan_refunds"`
	OrphanShipments      int64               `json:"orphan_shipments"`
}

type order struct {
	gross, refunded int64
	status          string
}

// State is an in-progress fold. Events must be applied in canon.Less order.
type State struct {
	tenantID        string
	customerKey     func(string) string
	eventCount      int64
	orders          map[string]*order
	inventory       map[string]int64
	oversold        int64
	customers       map[string]struct{}
	messages        map[string]int64
	lastContact     *int64
	campaigns       map[string]Campaign
	orphanRefunds   int64
	orphanShipments int64
}

// New starts an empty fold. customerKey maps a customer ID to the key used to
// count distinct customers.
func New(tenantID string, customerKey func(customerID string) string) *State {
	return &State{
		tenantID:    tenantID,
		customerKey: customerKey,
		orders:      map[string]*order{},
		inventory:   map[string]int64{},
		customers:   map[string]struct{}{},
		messages:    map[string]int64{},
		campaigns:   map[string]Campaign{},
	}
}

// The req* types decode only the fields the reference reducer reads. Pointer
// fields make a missing or null field distinguishable from a zero value.
type reqLine struct {
	SKU       *string `json:"sku"`
	Qty       *int64  `json:"qty"`
	UnitCents *int64  `json:"unit_cents"`
}

type reqOrderCreated struct {
	OrderID *string    `json:"order_id"`
	Lines   *[]reqLine `json:"lines"`
}

// AmountCents and Status stay raw: the reducer reads them only once the order
// exists, so a bad value must not hide a good order_id.
type reqOrderRefunded struct {
	OrderID     *string         `json:"order_id"`
	AmountCents json.RawMessage `json:"amount_cents"`
}

type reqShipmentUpdated struct {
	OrderID *string         `json:"order_id"`
	Status  json.RawMessage `json:"status"`
}

type reqInventoryAdjusted struct {
	SKU   *string `json:"sku"`
	Delta *int64  `json:"delta"`
}

type reqMessageReceived struct {
	Channel *string `json:"channel"`
}

type reqAdMetric struct {
	CampaignID  *string `json:"campaign_id"`
	SpendCents  *int64  `json:"spend_cents"`
	Impressions *int64  `json:"impressions"`
	Clicks      *int64  `json:"clicks"`
}

// Apply folds one event and always returns nil. Fields are checked in the
// order the reducer reads them, and a field the reducer never reaches is not
// required. A known type whose data lacks a field the reducer reads, or has it
// with the wrong JSON type, is treated like an unknown type: it is counted
// (with its customer) and changes nothing else. For order.refunded and
// shipment.updated, order_id is read first: a missing order is an orphan
// whatever the other fields hold, and for an existing order a missing or
// malformed amount_cents / status changes nothing.
func (s *State) Apply(e canon.Event) error {
	s.begin(e)
	switch e.Type {
	case "order.created":
		var d reqOrderCreated
		if json.Unmarshal(e.Data, &d) != nil || d.OrderID == nil || d.Lines == nil {
			return nil
		}
		for _, l := range *d.Lines {
			if l.SKU == nil || l.Qty == nil || l.UnitCents == nil {
				return nil
			}
		}
		if _, ok := s.orders[*d.OrderID]; ok {
			return nil
		}
		var gross int64
		for _, l := range *d.Lines {
			gross += *l.Qty * *l.UnitCents
			have := s.inventory[*l.SKU]
			take := min(have, *l.Qty)
			s.inventory[*l.SKU] = have - take
			s.oversold += *l.Qty - take
		}
		s.orders[*d.OrderID] = &order{gross: gross, status: "unfulfilled"}
	case "order.refunded":
		var d reqOrderRefunded
		if json.Unmarshal(e.Data, &d) != nil || d.OrderID == nil {
			return nil
		}
		o, ok := s.orders[*d.OrderID]
		if !ok {
			s.orphanRefunds++
			return nil
		}
		var amount *int64
		if json.Unmarshal(d.AmountCents, &amount) != nil || amount == nil {
			return nil
		}
		o.refunded = min(o.gross, o.refunded+*amount)
	case "shipment.updated":
		var d reqShipmentUpdated
		if json.Unmarshal(e.Data, &d) != nil || d.OrderID == nil {
			return nil
		}
		o, ok := s.orders[*d.OrderID]
		if !ok {
			s.orphanShipments++
			return nil
		}
		var status *string
		if json.Unmarshal(d.Status, &status) != nil || status == nil {
			return nil
		}
		o.status = *status
	case "inventory.adjusted":
		var d reqInventoryAdjusted
		if json.Unmarshal(e.Data, &d) != nil || d.SKU == nil || d.Delta == nil {
			return nil
		}
		s.inventory[*d.SKU] = max(0, s.inventory[*d.SKU]+*d.Delta)
	case "message.received":
		var d reqMessageReceived
		if json.Unmarshal(e.Data, &d) != nil || d.Channel == nil {
			return nil
		}
		s.messages[*d.Channel]++
		if s.lastContact == nil || e.OccurredAtMs > *s.lastContact {
			t := e.OccurredAtMs
			s.lastContact = &t
		}
	case "ad.metric":
		var d reqAdMetric
		if json.Unmarshal(e.Data, &d) != nil || d.CampaignID == nil || d.SpendCents == nil ||
			d.Impressions == nil || d.Clicks == nil {
			return nil
		}
		c := s.campaigns[*d.CampaignID]
		c.SpendCents += *d.SpendCents
		c.Impressions += *d.Impressions
		c.Clicks += *d.Clicks
		s.campaigns[*d.CampaignID] = c
	}
	return nil
}

// begin counts the event and its customer, before the type branch.
func (s *State) begin(e canon.Event) {
	s.eventCount++
	if e.CustomerID != nil {
		s.customers[s.customerKey(*e.CustomerID)] = struct{}{}
	}
}

// Result derives the public state. It does not mutate s.
func (s *State) Result() Result {
	r := Result{
		TenantID:             s.tenantID,
		EventCount:           s.eventCount,
		OrderCount:           int64(len(s.orders)),
		ShipmentStatusCounts: map[string]int64{},
		Inventory:            make(map[string]int64, len(s.inventory)),
		OversoldUnits:        s.oversold,
		CustomerCount:        int64(len(s.customers)),
		MessagesByChannel:    make(map[string]int64, len(s.messages)),
		Campaigns:            make(map[string]Campaign, len(s.campaigns)),
		OrphanRefunds:        s.orphanRefunds,
		OrphanShipments:      s.orphanShipments,
	}
	for k, v := range s.inventory {
		r.Inventory[k] = v
	}
	for k, v := range s.messages {
		r.MessagesByChannel[k] = v
	}
	for k, v := range s.campaigns {
		r.Campaigns[k] = v
	}
	if s.lastContact != nil {
		t := *s.lastContact
		r.LastContactMs = &t
	}
	for _, o := range s.orders {
		r.ShipmentStatusCounts[o.status]++
		r.GrossCents += o.gross
		r.RefundedCents += o.refunded
		if o.status != "delivered" && o.status != "returned" && o.refunded < o.gross {
			r.OpenOrders++
		}
	}
	r.NetCents = r.GrossCents - r.RefundedCents
	return r
}

// Fold sorts a copy of events and applies all of them.
func Fold(tenantID string, events []canon.Event, customerKey func(string) string) (Result, error) {
	sorted := append([]canon.Event(nil), events...)
	canon.Sort(sorted)
	s := New(tenantID, customerKey)
	for _, e := range sorted {
		if err := s.Apply(e); err != nil {
			return Result{}, err
		}
	}
	return s.Result(), nil
}
