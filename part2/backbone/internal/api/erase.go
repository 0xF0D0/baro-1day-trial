package api

import (
	"errors"
	"net/http"

	"backbone/internal/store"
)

// authorizeAdmin checks the admin token and that the path tenant exists.
func (s *server) authorizeAdmin(w http.ResponseWriter, r *http.Request) (string, bool) {
	if !s.reg.IsAdmin(bearer(r)) {
		status(w, http.StatusUnauthorized)
		return "", false
	}
	id := r.PathValue("id")
	if _, ok := s.reg.ByID(id); !ok {
		status(w, http.StatusNotFound)
		return "", false
	}
	return id, true
}

func (s *server) eraseCustomer(w http.ResponseWriter, r *http.Request) {
	id, ok := s.authorizeAdmin(w, r)
	if !ok {
		return
	}
	sc, err := s.st.Scope(r.Context(), id)
	if err != nil {
		if errors.Is(err, store.ErrTenantErased) {
			status(w, http.StatusNoContent)
		} else {
			status(w, http.StatusInternalServerError)
		}
		return
	}
	if err := s.st.EraseCustomer(r.Context(), sc, r.PathValue("customer_id")); err != nil {
		status(w, http.StatusInternalServerError)
		return
	}
	status(w, http.StatusNoContent)
}

func (s *server) eraseTenant(w http.ResponseWriter, r *http.Request) {
	id, ok := s.authorizeAdmin(w, r)
	if !ok {
		return
	}
	if err := s.st.EraseTenant(r.Context(), id); err != nil {
		status(w, http.StatusInternalServerError)
		return
	}
	status(w, http.StatusNoContent)
}
