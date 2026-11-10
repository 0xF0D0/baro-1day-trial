// Package crashpoint provides named, test-only points where the process can be
// made to die as a kill -9 would. Disarmed, a hit does nothing.
package crashpoint

import (
	"fmt"
	"math/rand/v2"
	"os"
	"slices"
	"sync/atomic"
)

// Names lists every crash point, in the order of the Global Constraints.
var Names = []string{
	"flush.after_bucket",
	"flush.after_snapshot",
	"flush.before_commit",
	"rebuild.after_bucket",
	"rebuild.after_snapshot",
	"rebuild.before_commit",
}

type armed struct {
	points      []string
	probability float64
}

var (
	state atomic.Pointer[armed]
	exit  atomic.Pointer[func()]
)

// Arm enables points with the given probability per hit. An empty list disarms; otherwise every
// name must be in Names and probability must be in (0, 1].
func Arm(points []string, probability float64) error {
	if len(points) == 0 {
		state.Store(nil)
		return nil
	}
	for _, p := range points {
		if !slices.Contains(Names, p) {
			return fmt.Errorf("crashpoint: unknown point %q", p)
		}
	}
	if !(probability > 0 && probability <= 1) {
		return fmt.Errorf("crashpoint: probability %v must be in (0, 1]", probability)
	}
	state.Store(&armed{points: slices.Clone(points), probability: probability})
	return nil
}

// Hit fires the point when it is armed and the draw succeeds. It is safe for concurrent use.
func Hit(name string) {
	a := state.Load()
	if a == nil || !slices.Contains(a.points, name) {
		return
	}
	if a.probability < 1 && rand.Float64() >= a.probability {
		return
	}
	// One line, no deferred calls: a real kill -9 runs none either.
	fmt.Fprintf(os.Stderr, "{\"level\":\"WARN\",\"msg\":\"crash point\",\"point\":%q}\n", name)
	if f := exit.Load(); f != nil {
		(*f)()
		return
	}
	os.Exit(137)
}

// Intercept replaces the exit for tests and returns a function that restores it.
func Intercept(exit_ func()) (restore func()) {
	prev := exit.Load()
	exit.Store(&exit_)
	return func() { exit.Store(prev) }
}
