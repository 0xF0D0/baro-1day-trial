package api

import (
	"errors"
	"io"
	"net/http"

	"backbone/internal/canon"
	"backbone/internal/store"
	"backbone/internal/tenants"
	"backbone/internal/webhook"
)

const maxBody = 1 << 20

func (s *server) webhookA(w http.ResponseWriter, r *http.Request) {
	s.webhook(w, r, webhook.HeaderA, webhook.PeekAccount,
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
	s.webhook(w, r, webhook.HeaderB, webhook.PeekShopDomain,
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
	w http.ResponseWriter, r *http.Request, header string,
	peek func([]byte) (string, error),
	lookup func([]byte) (*tenants.Tenant, bool),
	secret func(*tenants.Tenant) string,
	verify func(secret, header string, raw []byte) error,
	normalize func(raw []byte, tenantID string) (canon.Event, error),
) {
	raw, err := io.ReadAll(http.MaxBytesReader(w, r.Body, maxBody))
	if err != nil {
		status(w, http.StatusBadRequest)
		return
	}
	if _, err := peek(raw); err != nil {
		status(w, http.StatusBadRequest)
		return
	}
	t, ok := lookup(raw)
	if !ok {
		status(w, http.StatusNotFound)
		return
	}
	if err := verify(secret(t), r.Header.Get(header), raw); err != nil {
		status(w, http.StatusUnauthorized)
		return
	}
	ev, err := normalize(raw, t.ID)
	if err != nil {
		if errors.Is(err, canon.ErrMalformed) {
			status(w, http.StatusBadRequest)
		} else {
			status(w, http.StatusInternalServerError)
		}
		return
	}
	sc, err := s.st.Scope(r.Context(), t.ID)
	if err != nil {
		if errors.Is(err, store.ErrTenantErased) {
			status(w, http.StatusGone)
		} else {
			status(w, http.StatusInternalServerError)
		}
		return
	}
	res, err := s.st.Ingest(r.Context(), sc, ev)
	switch {
	case err != nil:
		status(w, http.StatusInternalServerError)
	case res == store.TenantErased:
		status(w, http.StatusGone)
	default:
		status(w, http.StatusOK)
	}
}
