// Package bench holds the pure parts of the benchmark command: the read
// windows and the latency summary.
package bench

import (
	"bufio"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"sort"
	"time"
)

const dayMs = int64(86400000)

// Windows picks the read windows from the deliveries file: cold is the first
// UTC day of delivery times, hot is the last UTC day. Each window is
// [From, To) in epoch milliseconds.
func Windows(deliveries io.Reader) (coldFrom, coldTo, hotFrom, hotTo int64, err error) {
	sc := bufio.NewScanner(deliveries)
	sc.Buffer(make([]byte, 0, 1<<20), 64<<20)
	minAt, maxAt := int64(math.MaxInt64), int64(math.MinInt64)
	n := 0
	for sc.Scan() {
		line := sc.Bytes()
		if len(line) == 0 {
			continue
		}
		var row struct {
			AtMs *int64 `json:"at_ms"`
		}
		if err := json.Unmarshal(line, &row); err != nil {
			return 0, 0, 0, 0, fmt.Errorf("bad delivery row: %w", err)
		}
		if row.AtMs == nil {
			return 0, 0, 0, 0, errors.New("delivery row without at_ms")
		}
		minAt, maxAt = min(minAt, *row.AtMs), max(maxAt, *row.AtMs)
		n++
	}
	if err := sc.Err(); err != nil {
		return 0, 0, 0, 0, err
	}
	if n == 0 {
		return 0, 0, 0, 0, errors.New("no delivery rows")
	}
	coldFrom = floorDay(minAt)
	hotFrom = floorDay(maxAt)
	return coldFrom, coldFrom + dayMs, hotFrom, hotFrom + dayMs, nil
}

func floorDay(ms int64) int64 {
	d := ms / dayMs
	if ms%dayMs < 0 {
		d--
	}
	return d * dayMs
}

// Summary is the latency summary of one request class.
type Summary struct {
	Count              int
	P50, P95, P99, Max time.Duration
}

// Summarize sorts the samples and takes nearest-rank percentiles.
func Summarize(samples []time.Duration) Summary {
	if len(samples) == 0 {
		return Summary{}
	}
	s := append([]time.Duration(nil), samples...)
	sort.Slice(s, func(i, j int) bool { return s[i] < s[j] })
	rank := func(p float64) time.Duration {
		r := int(math.Ceil(p / 100 * float64(len(s))))
		return s[min(max(r, 1), len(s))-1]
	}
	return Summary{Count: len(s), P50: rank(50), P95: rank(95), P99: rank(99), Max: s[len(s)-1]}
}
