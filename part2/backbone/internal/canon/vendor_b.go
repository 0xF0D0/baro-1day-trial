package canon

import (
	"encoding/json"
	"strings"
	"time"
)

type vendorBEnvelope struct {
	UUID      reqStr          `json:"event_uuid"`
	Event     reqStr          `json:"event"`
	Timestamp reqStr          `json:"timestamp"`
	Payload   json.RawMessage `json:"payload"`
}

// FromVendorB maps a vendor B webhook body to a canonical event.
func FromVendorB(raw []byte, tenantID string) (Event, error) {
	var env vendorBEnvelope
	if err := decode(raw, &env); err != nil {
		return Event{}, err
	}
	if !env.UUID.ok || !env.Event.ok || !env.Timestamp.ok || !isObject(env.Payload) {
		return Event{}, malformed("vendor B envelope incomplete")
	}
	if strings.Contains(env.UUID.v, "\x00") {
		return Event{}, malformed("event_uuid contains NUL")
	}
	if !strings.HasSuffix(env.Timestamp.v, "Z") {
		return Event{}, malformed("timestamp is not UTC")
	}
	ts, err := time.Parse(time.RFC3339Nano, env.Timestamp.v)
	if err != nil {
		return Event{}, malformed("timestamp is not RFC 3339")
	}
	ev := Event{EventID: env.UUID.v, TenantID: tenantID, Type: env.Event.v, OccurredAtMs: ts.UnixMilli()}
	p := env.Payload

	var data any
	switch env.Event.v {
	case "shipment.updated":
		var o struct {
			OrderID    reqStr `json:"order_id"`
			CustomerID reqStr `json:"customer_id"`
			Status     reqStr `json:"status"`
			Carrier    reqStr `json:"carrier"`
			Tracking   reqStr `json:"tracking"`
		}
		if err := decode(p, &o); err != nil {
			return Event{}, err
		}
		if !o.OrderID.ok || !o.CustomerID.ok || !o.Status.ok || !o.Carrier.ok || !o.Tracking.ok {
			return Event{}, malformed("shipment.updated incomplete")
		}
		id := o.CustomerID.v
		ev.CustomerID = &id
		data = ShipmentUpdated{OrderID: o.OrderID.v, Status: o.Status.v, Carrier: o.Carrier.v, Tracking: o.Tracking.v}
	case "inventory.adjusted":
		var o struct {
			SKU    reqStr `json:"sku"`
			Delta  reqInt `json:"delta"`
			Reason reqStr `json:"reason"`
		}
		if err := decode(p, &o); err != nil {
			return Event{}, err
		}
		if !o.SKU.ok || !o.Delta.ok || !o.Reason.ok {
			return Event{}, malformed("inventory.adjusted incomplete")
		}
		data = InventoryAdjusted{SKU: o.SKU.v, Delta: o.Delta.v, Reason: o.Reason.v}
	case "message.received":
		var o struct {
			CustomerID reqStr `json:"customer_id"`
			Email      reqStr `json:"customer_email"`
			Channel    reqStr `json:"channel"`
			Body       reqStr `json:"body"`
		}
		if err := decode(p, &o); err != nil {
			return Event{}, err
		}
		if !o.CustomerID.ok || !o.Email.ok || !o.Channel.ok || !o.Body.ok {
			return Event{}, malformed("message.received incomplete")
		}
		id := o.CustomerID.v
		ev.CustomerID = &id
		data = MessageReceived{Channel: o.Channel.v, Email: o.Email.v, Body: o.Body.v}
	default:
		ev.CustomerID = customerIDOf(p)
		ev.Data = append(json.RawMessage(nil), p...)
		return ev, nil
	}
	d, err := marshalData(data)
	if err != nil {
		return Event{}, err
	}
	ev.Data = d
	return ev, nil
}
