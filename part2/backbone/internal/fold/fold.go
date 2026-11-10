// Package fold is a port of the reference reducer: it folds a tenant's canonical
// events, applied in canon.Less order, into the public state.
package fold

import (
	"encoding/json"
	"fmt"

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

func decode(e canon.Event, v any) error {
	if err := json.Unmarshal(e.Data, v); err != nil {
		return fmt.Errorf("fold: event %s (%s): %w", e.EventID, e.Type, err)
	}
	return nil
}

// Apply folds one event. It fails only when a known type's data cannot be decoded.
func (s *State) Apply(e canon.Event) error {
	switch e.Type {
	case "order.created":
		var d canon.OrderCreated
		if err := decode(e, &d); err != nil {
			return err
		}
		s.begin(e)
		if _, ok := s.orders[d.OrderID]; ok {
			return nil
		}
		var gross int64
		for _, l := range d.Lines {
			gross += l.Qty * l.UnitCents
			have := s.inventory[l.SKU]
			take := min(have, l.Qty)
			s.inventory[l.SKU] = have - take
			s.oversold += l.Qty - take
		}
		s.orders[d.OrderID] = &order{gross: gross, status: "unfulfilled"}
	case "order.refunded":
		var d canon.OrderRefunded
		if err := decode(e, &d); err != nil {
			return err
		}
		s.begin(e)
		if o, ok := s.orders[d.OrderID]; ok {
			o.refunded = min(o.gross, o.refunded+d.AmountCents)
		} else {
			s.orphanRefunds++
		}
	case "shipment.updated":
		var d canon.ShipmentUpdated
		if err := decode(e, &d); err != nil {
			return err
		}
		s.begin(e)
		if o, ok := s.orders[d.OrderID]; ok {
			o.status = d.Status
		} else {
			s.orphanShipments++
		}
	case "inventory.adjusted":
		var d canon.InventoryAdjusted
		if err := decode(e, &d); err != nil {
			return err
		}
		s.begin(e)
		s.inventory[d.SKU] = max(0, s.inventory[d.SKU]+d.Delta)
	case "message.received":
		var d canon.MessageReceived
		if err := decode(e, &d); err != nil {
			return err
		}
		s.begin(e)
		s.messages[d.Channel]++
		if s.lastContact == nil || e.OccurredAtMs > *s.lastContact {
			t := e.OccurredAtMs
			s.lastContact = &t
		}
	case "ad.metric":
		var d canon.AdMetric
		if err := decode(e, &d); err != nil {
			return err
		}
		s.begin(e)
		c := s.campaigns[d.CampaignID]
		c.SpendCents += d.SpendCents
		c.Impressions += d.Impressions
		c.Clicks += d.Clicks
		s.campaigns[d.CampaignID] = c
	default:
		s.begin(e)
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
