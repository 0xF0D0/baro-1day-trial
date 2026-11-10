package api

import (
	"errors"
	"io"
	"net/http"
	"time"

	"backbone/internal/canon"
	"backbone/internal/metrics"
	"backbone/internal/store"
	"backbone/internal/tenants"
	"backbone/internal/webhook"
)

const maxBody = 1 << 20

func (s *server) webhookA(w http.ResponseWriter, r *http.Request) {
	s.webhook(w, r, "a", webhook.HeaderA, webhook.PeekAccount,
		func(raw []byte) (*tenants.Tenant, bool) {
			acct, err := webhook.PeekAccount(raw)
			if err != nil || acct == "" {
				return nil, false
			}
			return s.reg.ByAccount(acct)
		},
		func(t *tenants.Tenant) string { return t.VendorA.SigningSecret },
		webhook.VerifyA, canon.FromVendorA)
}

func (s *server) webhookB(w http.ResponseWriter, r *http.Request) {
	s.webhook(w, r, "b", webhook.HeaderB, webhook.PeekShopDomain,
		func(raw []byte) (*tenants.Tenant, bool) {
			dom, err := webhook.PeekShopDomain(raw)
			if err != nil || dom == "" {
				return nil, false
			}
			return s.reg.ByShopDomain(dom)
		},
		func(t *tenants.Tenant) string { return t.VendorB.SigningSecret },
		webhook.VerifyB, canon.FromVendorB)
}

func (s *server) webhook(
	w http.ResponseWriter, r *http.Request, vendor, header string,
	peek func([]byte) (string, error),
	lookup func([]byte) (*tenants.Tenant, bool),
	secret func(*tenants.Tenant) string,
	verify func(secret, header string, raw []byte) error,
	normalize func(raw []byte, tenantID string) (canon.Event, error),
) {
	start := time.Now()
	// reply answers with code and counts the outcome; 200s also time the ack.
	reply := func(code int, outcome string) {
		status(w, code)
		metrics.IngestTotal.WithLabelValues(vendor, outcome).Inc()
		if code == http.StatusOK {
			metrics.AckSeconds.WithLabelValues(vendor).Observe(time.Since(start).Seconds())
		}
	}
	raw, err := io.ReadAll(http.MaxBytesReader(w, r.Body, maxBody))
	if err != nil {
		reply(http.StatusBadRequest, "bad_request")
		return
	}
	if _, err := peek(raw); err != nil {
		reply(http.StatusBadRequest, "bad_request")
		return
	}
	t, ok := lookup(raw)
	if !ok {
		reply(http.StatusNotFound, "unknown_tenant")
		return
	}
	if err := verify(secret(t), r.Header.Get(header), raw); err != nil {
		reply(http.StatusUnauthorized, "bad_signature")
		return
	}
	ev, err := normalize(raw, t.ID)
	if err != nil {
		if errors.Is(err, canon.ErrMalformed) {
			reply(http.StatusBadRequest, "bad_request")
		} else {
			reply(http.StatusInternalServerError, "error")
		}
		return
	}
	sc, err := s.st.Scope(r.Context(), t.ID)
	if err != nil {
		if errors.Is(err, store.ErrTenantErased) {
			reply(http.StatusGone, "tenant_erased")
		} else {
			reply(http.StatusInternalServerError, "error")
		}
		return
	}
	res, err := s.st.Ingest(r.Context(), sc, ev)
	switch {
	case err != nil:
		reply(http.StatusInternalServerError, "error")
	case res == store.TenantErased:
		reply(http.StatusGone, "tenant_erased")
	case res == store.Duplicate:
		reply(http.StatusOK, "duplicate")
	case res == store.CustomerErased:
		reply(http.StatusOK, "customer_erased")
	default:
		reply(http.StatusOK, "stored")
	}
}
