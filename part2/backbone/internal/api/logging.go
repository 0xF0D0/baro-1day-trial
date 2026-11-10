package api

import (
	"log/slog"
	"net/http"
	"time"
)

type statusWriter struct {
	http.ResponseWriter
	status int
}

func (w *statusWriter) WriteHeader(code int) {
	w.status = code
	w.ResponseWriter.WriteHeader(code)
}

// logRequests writes one line per request: route template, status, duration.
// It never logs the path, query, headers, body or error text.
func logRequests(log *slog.Logger, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		sw := &statusWriter{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(sw, r)
		route := r.Pattern // set by the mux on this request
		if route == "" {
			route = "unmatched"
		}
		log.Info("request", "route", route, "status", sw.status, "duration_ms", time.Since(start).Milliseconds())
	})
}
