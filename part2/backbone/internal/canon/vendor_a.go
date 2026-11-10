package canon

import (
	"encoding/json"
	"strings"
)

type vendorAEnvelope struct {
	ID      reqStr `json:"id"`
	Type    reqStr `json:"type"`
	Created reqInt `json:"created"`
	Data    struct {
		Object json.RawMessage `json:"object"`
	} `json:"data"`
}

// FromVendorA maps a vendor A webhook body to a canonical event.
func FromVendorA(raw []byte, tenantID string) (Event, error) {
	var env vendorAEnvelope
	if err := decode(raw, &env); err != nil {
		return Event{}, err
	}
	if !env.ID.ok || !env.Type.ok || !env.Created.ok || !isObject(env.Data.Object) {
		return Event{}, malformed("vendor A envelope incomplete")
	}
	if strings.Contains(env.ID.v, "\x00") {
		return Event{}, malformed("id contains NUL")
	}
	ev := Event{EventID: env.ID.v, TenantID: tenantID, Type: env.Type.v, OccurredAtMs: env.Created.v}
	obj := env.Data.Object

	var data any
	switch env.Type.v {
	case "order.created":
		var o struct {
			OrderID  reqStr `json:"order_id"`
			Customer struct {
				ID    reqStr `json:"id"`
				Email reqStr `json:"email"`
				Name  reqStr `json:"name"`
			} `json:"customer"`
			LineItems *[]struct {
				SKU      reqStr `json:"sku"`
				Quantity reqInt `json:"quantity"`
				Unit     reqInt `json:"unit_amount"`
			} `json:"line_items"`
		}
		if err := decode(obj, &o); err != nil {
			return Event{}, err
		}
		c := o.Customer
		if !o.OrderID.ok || !c.ID.ok || !c.Email.ok || !c.Name.ok || o.LineItems == nil {
			return Event{}, malformed("order.created incomplete")
		}
		lines := make([]Line, 0, len(*o.LineItems))
		for _, li := range *o.LineItems {
			if !li.SKU.ok || !li.Quantity.ok || !li.Unit.ok {
				return Event{}, malformed("order.created line incomplete")
			}
			lines = append(lines, Line{SKU: li.SKU.v, Qty: li.Quantity.v, UnitCents: li.Unit.v})
		}
		id := c.ID.v
		ev.CustomerID = &id
		data = OrderCreated{OrderID: o.OrderID.v, Lines: lines, Email: c.Email.v, Name: c.Name.v}
		ev.Type = "order.created"
	case "charge.refunded":
		var o struct {
			OrderID    reqStr `json:"order_id"`
			CustomerID reqStr `json:"customer_id"`
			Amount     reqInt `json:"amount_refunded"`
		}
		if err := decode(obj, &o); err != nil {
			return Event{}, err
		}
		if !o.OrderID.ok || !o.CustomerID.ok || !o.Amount.ok {
			return Event{}, malformed("charge.refunded incomplete")
		}
		id := o.CustomerID.v
		ev.CustomerID = &id
		data = OrderRefunded{OrderID: o.OrderID.v, AmountCents: o.Amount.v}
		ev.Type = "order.refunded"
	case "ads.metric":
		var o struct {
			CampaignID  reqStr `json:"campaign_id"`
			Spend       reqInt `json:"spend"`
			Impressions reqInt `json:"impressions"`
			Clicks      reqInt `json:"clicks"`
		}
		if err := decode(obj, &o); err != nil {
			return Event{}, err
		}
		if !o.CampaignID.ok || !o.Spend.ok || !o.Impressions.ok || !o.Clicks.ok {
			return Event{}, malformed("ads.metric incomplete")
		}
		data = AdMetric{CampaignID: o.CampaignID.v, SpendCents: o.Spend.v, Impressions: o.Impressions.v, Clicks: o.Clicks.v}
		ev.Type = "ad.metric"
	default:
		ev.CustomerID = customerIDOf(obj)
		ev.Data = append(json.RawMessage(nil), obj...)
		return ev, nil
	}
	d, err := marshalData(data)
	if err != nil {
		return Event{}, err
	}
	ev.Data = d
	return ev, nil
}
