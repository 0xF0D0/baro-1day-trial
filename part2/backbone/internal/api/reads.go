package api

import (
	"errors"
	"net/http"
	"strconv"

	"backbone/internal/canon"
	"backbone/internal/fold"
	"backbone/internal/store"
)

const maxLimit = 1000

// parseLimit returns the page size: default and cap are maxLimit.
func parseLimit(s string) (int, error) {
	if s == "" {
		return maxLimit, nil
	}
	n, err := strconv.Atoi(s)
	if err != nil || n < 1 {
		return 0, errors.New("bad limit")
	}
	return min(n, maxLimit), nil
}

// authorizeRead checks the bearer token against the path tenant and returns a
// scope. It writes the error response itself and reports ok=false.
func (s *server) authorizeRead(w http.ResponseWriter, r *http.Request) (store.Scope, bool) {
	t, ok := s.reg.ByToken(bearer(r))
	if !ok {
		status(w, http.StatusUnauthorized)
		return store.Scope{}, false
	}
	if t.ID != r.PathValue("id") {
		status(w, http.StatusNotFound)
		return store.Scope{}, false
	}
	sc, err := s.st.Scope(r.Context(), t.ID)
	if err != nil {
		readErr(w, err)
		return store.Scope{}, false
	}
	return sc, true
}

func readErr(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, store.ErrTenantErased):
		status(w, http.StatusGone)
	case errors.Is(err, store.ErrUnknownTenant):
		status(w, http.StatusNotFound)
	default:
		status(w, http.StatusInternalServerError)
	}
}

func (s *server) state(w http.ResponseWriter, r *http.Request) {
	sc, ok := s.authorizeRead(w, r)
	if !ok {
		return
	}
	var events []canon.Event
	err := s.st.ScanAll(r.Context(), sc, func(ev canon.Event) error {
		events = append(events, ev)
		return nil
	})
	if err != nil {
		readErr(w, err)
		return
	}
	res, err := fold.Fold(sc.TenantID(), events, sc.Keys().CustomerKeyHex)
	if err != nil {
		status(w, http.StatusInternalServerError)
		return
	}
	writeJSON(w, res)
}

type eventsResponse struct {
	Events     []canon.Event `json:"events"`
	NextCursor *string       `json:"next_cursor"`
}

func (s *server) events(w http.ResponseWriter, r *http.Request) {
	sc, ok := s.authorizeRead(w, r)
	if !ok {
		return
	}
	q := r.URL.Query()
	from, err1 := strconv.ParseInt(q.Get("from_ms"), 10, 64)
	to, err2 := strconv.ParseInt(q.Get("to_ms"), 10, 64)
	limit, err3 := parseLimit(q.Get("limit"))
	if err1 != nil || err2 != nil || err3 != nil {
		status(w, http.StatusBadRequest)
		return
	}
	var after *store.Key
	if c := q.Get("cursor"); c != "" {
		k, err := decodeCursor(sc.Keys(), c, from, to)
		if err != nil {
			status(w, http.StatusBadRequest)
			return
		}
		after = &k
	}
	rows, err := s.st.Range(r.Context(), sc, from, to, after, limit+1)
	if err != nil {
		readErr(w, err)
		return
	}
	resp := eventsResponse{Events: []canon.Event{}}
	if len(rows) > limit {
		rows = rows[:limit]
		last := rows[limit-1]
		c := encodeCursor(sc.Keys(), from, to, store.Key{OccurredAtMs: last.OccurredAtMs, EventID: last.EventID})
		resp.NextCursor = &c
	}
	resp.Events = append(resp.Events, rows...)
	writeJSON(w, resp)
}
