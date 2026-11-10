package metrics_test

import (
	"context"
	"errors"
	"fmt"
	"net/http/httptest"
	"strings"
	"testing"

	"backbone/internal/cold"
	"backbone/internal/metrics"

	"github.com/jackc/pgx/v5/pgconn"
)

func TestErrorClass(t *testing.T) {
	cases := []struct {
		err  error
		want string
	}{
		{&pgconn.PgError{Code: "40P01"}, "postgres_40P01"},
		{fmt.Errorf("wrap: %w", &pgconn.PgError{Code: "23505"}), "postgres_23505"},
		{fmt.Errorf("wrap: %w", cold.ErrNotFound), "object_not_found"},
		{context.Canceled, "canceled"},
		{fmt.Errorf("x: %w", context.DeadlineExceeded), "canceled"},
		{errors.New("x"), "other"},
	}
	for _, c := range cases {
		if got := metrics.ErrorClass(c.err); got != c.want {
			t.Errorf("%v: got %q want %q", c.err, got, c.want)
		}
	}
}

func TestHandlerServesProcessMetrics(t *testing.T) {
	rec := httptest.NewRecorder()
	metrics.Handler().ServeHTTP(rec, httptest.NewRequest("GET", "/metrics", nil))
	body := rec.Body.String()
	for _, want := range []string{"go_goroutines", "# HELP backbone_ingest_total"} {
		if !strings.Contains(body, want) {
			t.Errorf("body lacks %q", want)
		}
	}
}
