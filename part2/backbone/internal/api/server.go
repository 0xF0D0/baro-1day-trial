// Package api is the HTTP layer: webhooks, reads, erasure and health.
package api

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"backbone/internal/metrics"
	"backbone/internal/store"
	"backbone/internal/tenants"
)

type server struct {
	reg *tenants.Registry
	st  *store.Store
	log *slog.Logger
}

// NewServer builds the HTTP handler.
func NewServer(reg *tenants.Registry, st *store.Store, log *slog.Logger) http.Handler {
	s := &server{reg: reg, st: st, log: log}
	mux := http.NewServeMux()
	mux.HandleFunc("POST /webhooks/vendor-a", s.webhookA)
	mux.HandleFunc("POST /webhooks/vendor-b", s.webhookB)
	mux.HandleFunc("GET /tenants/{id}/state", s.state)
	mux.HandleFunc("GET /tenants/{id}/events", s.events)
	mux.HandleFunc("DELETE /tenants/{id}/customers/{customer_id}", s.eraseCustomer)
	mux.HandleFunc("DELETE /tenants/{id}", s.eraseTenant)
	mux.HandleFunc("GET /healthz", s.healthz)
	mux.Handle("GET /metrics", metrics.Handler())
	return logRequests(log, mux)
}

func (s *server) healthz(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()
	if err := s.st.Ping(ctx); err != nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		return
	}
	w.WriteHeader(http.StatusOK)
}

// status writes an empty-bodied response; error bodies never echo input.
func status(w http.ResponseWriter, code int) { w.WriteHeader(code) }

func writeJSON(w http.ResponseWriter, v any) {
	b, err := json.Marshal(v)
	if err != nil {
		status(w, http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(b)
}

func bearer(r *http.Request) string {
	tok, ok := strings.CutPrefix(r.Header.Get("Authorization"), "Bearer ")
	if !ok {
		return ""
	}
	return tok
}
