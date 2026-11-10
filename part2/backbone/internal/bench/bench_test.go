package bench

import (
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestWindows(t *testing.T) {
	const day = int64(86400000)
	d0 := 20000 * day
	in := strings.Join([]string{
		`{"seq":1,"kind":"webhook","at_ms":` + strconv.FormatInt(d0+5000, 10) + `}`,
		`{"seq":2,"kind":"erase_customer","at_ms":` + strconv.FormatInt(d0+2*day+7, 10) + `}`,
		``,
		`{"seq":3,"kind":"webhook","at_ms":` + strconv.FormatInt(d0+day+99, 10) + `}`,
	}, "\n")
	cf, ct, hf, ht, err := Windows(strings.NewReader(in))
	if err != nil {
		t.Fatal(err)
	}
	if cf != d0 || ct != d0+day || hf != d0+2*day || ht != d0+3*day {
		t.Fatalf("got cold [%d,%d) hot [%d,%d)", cf, ct, hf, ht)
	}
	if _, _, _, _, err := Windows(strings.NewReader("")); err == nil {
		t.Fatal("empty input must fail")
	}
}

func TestSummarize(t *testing.T) {
	var s []time.Duration
	for i := 100; i >= 1; i-- {
		s = append(s, time.Duration(i)*time.Millisecond)
	}
	got := Summarize(s)
	ms := time.Millisecond
	want := Summary{Count: 100, P50: 50 * ms, P95: 95 * ms, P99: 99 * ms, Max: 100 * ms}
	if got != want {
		t.Fatalf("got %+v want %+v", got, want)
	}
	if z := Summarize(nil); z != (Summary{}) {
		t.Fatalf("empty: %+v", z)
	}
}
