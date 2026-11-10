package crashpoint_test

import (
	"testing"

	"backbone/internal/crashpoint"
)

func TestArmValidates(t *testing.T) {
	defer crashpoint.Arm(nil, 0) //nolint:errcheck
	if err := crashpoint.Arm([]string{"nope"}, 1); err == nil {
		t.Fatal("unknown name accepted")
	}
	for _, p := range []float64{0, 1.5, -1} {
		if err := crashpoint.Arm([]string{"flush.after_bucket"}, p); err == nil {
			t.Fatalf("probability %v accepted", p)
		}
	}
	if err := crashpoint.Arm(nil, 0); err != nil {
		t.Fatal(err)
	}
	if err := crashpoint.Arm([]string{"flush.after_bucket", "rebuild.before_commit"}, 0.5); err != nil {
		t.Fatal(err)
	}
}

func TestHitDisarmedNeverExits(t *testing.T) {
	exits := 0
	defer crashpoint.Intercept(func() { exits++ })()
	if err := crashpoint.Arm(nil, 0); err != nil {
		t.Fatal(err)
	}
	for _, n := range crashpoint.Names {
		for i := 0; i < 1000; i++ {
			crashpoint.Hit(n)
		}
	}
	if exits != 0 {
		t.Fatalf("exits: %d", exits)
	}
}

func TestHitArmedFires(t *testing.T) {
	exits := 0
	defer crashpoint.Intercept(func() { exits++ })()
	if err := crashpoint.Arm([]string{"flush.after_bucket"}, 1); err != nil {
		t.Fatal(err)
	}
	defer crashpoint.Arm(nil, 0) //nolint:errcheck
	crashpoint.Hit("flush.after_bucket")
	if exits != 1 {
		t.Fatalf("exits: %d, want 1", exits)
	}
	crashpoint.Hit("rebuild.after_bucket")
	if exits != 1 {
		t.Fatalf("unarmed point fired: %d", exits)
	}
}
