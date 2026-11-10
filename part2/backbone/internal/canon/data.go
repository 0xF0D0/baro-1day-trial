package canon

// Line is one order line.
type Line struct {
	SKU       string `json:"sku"`
	Qty       int64  `json:"qty"`
	UnitCents int64  `json:"unit_cents"`
}

// OrderCreated is the data of an order.created event.
type OrderCreated struct {
	OrderID string `json:"order_id"`
	Lines   []Line `json:"lines"`
	Email   string `json:"email"`
	Name    string `json:"name"`
}

// OrderRefunded is the data of an order.refunded event.
type OrderRefunded struct {
	OrderID     string `json:"order_id"`
	AmountCents int64  `json:"amount_cents"`
}

// AdMetric is the data of an ad.metric event.
type AdMetric struct {
	CampaignID  string `json:"campaign_id"`
	SpendCents  int64  `json:"spend_cents"`
	Impressions int64  `json:"impressions"`
	Clicks      int64  `json:"clicks"`
}

// ShipmentUpdated is the data of a shipment.updated event.
type ShipmentUpdated struct {
	OrderID  string `json:"order_id"`
	Status   string `json:"status"`
	Carrier  string `json:"carrier"`
	Tracking string `json:"tracking"`
}

// InventoryAdjusted is the data of an inventory.adjusted event.
type InventoryAdjusted struct {
	SKU    string `json:"sku"`
	Delta  int64  `json:"delta"`
	Reason string `json:"reason"`
}

// MessageReceived is the data of a message.received event.
type MessageReceived struct {
	Channel string `json:"channel"`
	Email   string `json:"email"`
	Body    string `json:"body"`
}
