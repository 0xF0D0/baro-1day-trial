// Package canon turns vendor webhook bodies into canonical events and orders them.
package canon

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strconv"
)

// ErrMalformed marks a body that cannot be mapped to a canonical event.
var ErrMalformed = errors.New("malformed event")

func malformed(format string, args ...any) error {
	return fmt.Errorf("%w: %s", ErrMalformed, fmt.Sprintf(format, args...))
}

// Event is the canonical event.
type Event struct {
	EventID      string          `json:"event_id"`
	TenantID     string          `json:"tenant_id"`
	Type         string          `json:"type"`
	OccurredAtMs int64           `json:"occurred_at_ms"`
	CustomerID   *string         `json:"customer_id"`
	Data         json.RawMessage `json:"data"`
}

// Less orders by (OccurredAtMs, EventID) with byte-wise EventID comparison.
func Less(a, b Event) bool {
	if a.OccurredAtMs != b.OccurredAtMs {
		return a.OccurredAtMs < b.OccurredAtMs
	}
	return a.EventID < b.EventID
}

// Sort sorts events in canonical order.
func Sort(events []Event) {
	sort.Slice(events, func(i, j int) bool { return Less(events[i], events[j]) })
}

// reqInt is a required integral JSON number.
type reqInt struct {
	v  int64
	ok bool
}

func (r *reqInt) UnmarshalJSON(b []byte) error {
	v, err := strconv.ParseInt(string(b), 10, 64)
	if err != nil {
		return malformed("not an integer: %s", b)
	}
	r.v, r.ok = v, true
	return nil
}

// reqStr is a required JSON string.
type reqStr struct {
	v  string
	ok bool
}

func (r *reqStr) UnmarshalJSON(b []byte) error {
	if len(b) > 0 && b[0] != '"' {
		return malformed("not a string: %s", b)
	}
	if err := json.Unmarshal(b, &r.v); err != nil {
		return malformed("not a string: %s", b)
	}
	r.ok = true
	return nil
}

// decode parses raw into v, mapping every failure to ErrMalformed.
func decode(raw []byte, v any) error {
	d := json.NewDecoder(bytes.NewReader(raw))
	d.UseNumber()
	if err := d.Decode(v); err != nil {
		if errors.Is(err, ErrMalformed) {
			return err
		}
		return malformed("%v", err)
	}
	if d.More() {
		return malformed("trailing data")
	}
	return nil
}

// isObject reports whether raw is a JSON object.
func isObject(raw json.RawMessage) bool {
	t := bytes.TrimSpace(raw)
	return len(t) > 0 && t[0] == '{'
}

// customerIDOf returns the string customer_id of an object, or nil.
func customerIDOf(obj json.RawMessage) *string {
	var m struct {
		C json.RawMessage `json:"customer_id"`
	}
	if json.Unmarshal(obj, &m) != nil {
		return nil
	}
	var s string
	if json.Unmarshal(m.C, &s) != nil {
		return nil
	}
	return &s
}

func marshalData(v any) (json.RawMessage, error) {
	b, err := json.Marshal(v)
	if err != nil {
		return nil, malformed("%v", err)
	}
	return b, nil
}
