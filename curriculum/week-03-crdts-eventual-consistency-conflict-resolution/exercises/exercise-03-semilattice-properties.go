// Exercise 3 — Semilattice properties (property-test the three laws)
//
// Goal: A CRDT converges IFF its merge forms a join-semilattice: commutative,
//       associative, and idempotent (Lecture 1 section 3). Those three laws are
//       SUFFICIENT for convergence, so a CRDT that passes randomized property tests
//       for all three is very likely correct. This exercise property-tests a
//       G-counter's merge against all three laws over thousands of random states.
//
// This is the algebraic counterpart to Exercise 2's empirical convergence run:
// there you SAW three replicas converge; here you PROVE (by fuzzing) that the merge
// obeys the laws that GUARANTEE convergence for any inputs.
//
// HOW TO RUN
//
//   go test -v ./...
//   # or, as a single file:
//   go test -v -run Properties exercise-03-semilattice-properties.go
//
// The tests generate random G-counter states and assert:
//   commutativity:  merge(a, b) == merge(b, a)
//   associativity:  merge(merge(a, b), c) == merge(a, merge(b, c))
//   idempotence:    merge(a, a) == a
// If all pass over many random cases, the merge is a join-semilattice and converges.
//
// ACCEPTANCE CRITERIA
//
//   [ ] TestProperties_Commutativity passes over >= 1000 random state pairs.
//   [ ] TestProperties_Associativity passes over >= 1000 random state triples.
//   [ ] TestProperties_Idempotence passes over >= 1000 random states.
//   [ ] You can explain why these three laws together GUARANTEE convergence under
//       any reordering/duplication of merges.
//
// Expected: `go test` reports PASS for all three. (Try breaking merge -- e.g.,
// replace max with min, or with a+b -- and watch a law fail, proving the test bites.)

package crdt

import (
	"math/rand"
	"testing"
)

// GCounter is a grow-only counter: per-replica counts, value = sum, merge =
// element-wise max. Its merge is the join (least upper bound) of the lattice.
type GCounter struct {
	counts []uint64
}

func newGCounter(n int) GCounter {
	return GCounter{counts: make([]uint64, n)}
}

// merge returns a NEW G-counter that is the element-wise max of a and b.
// (Returning a new value keeps the property tests clean -- no aliasing.)
func merge(a, b GCounter) GCounter {
	n := len(a.counts)
	out := newGCounter(n)
	for i := 0; i < n; i++ {
		if a.counts[i] >= b.counts[i] {
			out.counts[i] = a.counts[i]
		} else {
			out.counts[i] = b.counts[i]
		}
	}
	return out
}

// equal reports whether two G-counter states are identical.
func equal(a, b GCounter) bool {
	if len(a.counts) != len(b.counts) {
		return false
	}
	for i := range a.counts {
		if a.counts[i] != b.counts[i] {
			return false
		}
	}
	return true
}

// randState builds a random G-counter of width n with small random counts.
func randState(r *rand.Rand, n int) GCounter {
	g := newGCounter(n)
	for i := 0; i < n; i++ {
		g.counts[i] = uint64(r.Intn(1000))
	}
	return g
}

const (
	cases = 2000 // random cases per property
	width = 5    // number of replicas in each counter
)

// Commutativity: merge(a, b) == merge(b, a). The order of two merges doesn't
// matter -- which is exactly why a gossip network can deliver state in any order.
func TestProperties_Commutativity(t *testing.T) {
	r := rand.New(rand.NewSource(1))
	for i := 0; i < cases; i++ {
		a := randState(r, width)
		b := randState(r, width)
		if !equal(merge(a, b), merge(b, a)) {
			t.Fatalf("commutativity FAILED on case %d: a=%v b=%v", i, a.counts, b.counts)
		}
	}
}

// Associativity: merge(merge(a,b),c) == merge(a,merge(b,c)). The grouping of merges
// doesn't matter -- which is why batching/regrouping gossip messages is safe.
func TestProperties_Associativity(t *testing.T) {
	r := rand.New(rand.NewSource(2))
	for i := 0; i < cases; i++ {
		a := randState(r, width)
		b := randState(r, width)
		c := randState(r, width)
		left := merge(merge(a, b), c)
		right := merge(a, merge(b, c))
		if !equal(left, right) {
			t.Fatalf("associativity FAILED on case %d", i)
		}
	}
}

// Idempotence: merge(a, a) == a. Re-merging a duplicate changes nothing -- which is
// why an at-least-once (duplicating) gossip network is safe.
func TestProperties_Idempotence(t *testing.T) {
	r := rand.New(rand.NewSource(3))
	for i := 0; i < cases; i++ {
		a := randState(r, width)
		if !equal(merge(a, a), a) {
			t.Fatalf("idempotence FAILED on case %d: a=%v", i, a.counts)
		}
	}
}

// TestProperties_Convergence ties it together: given any number of replicas with
// random states, merging them ALL into each other (in a random order, with
// duplicates) makes every replica reach the SAME state. This is the convergence
// the three laws guarantee, demonstrated end-to-end.
func TestProperties_Convergence(t *testing.T) {
	r := rand.New(rand.NewSource(4))
	for trial := 0; trial < 200; trial++ {
		k := 3 + r.Intn(4) // 3..6 replicas
		replicas := make([]GCounter, k)
		for i := range replicas {
			replicas[i] = randState(r, width)
		}
		// Snapshot the originals; merge every snapshot into every replica twice,
		// in a shuffled order (commutativity + associativity + idempotence at once).
		snaps := make([]GCounter, k)
		copy(snaps, replicas)

		order := r.Perm(k * k)
		for round := 0; round < 2; round++ {
			for _, idx := range order {
				i, j := idx/k, idx%k
				if i != j {
					replicas[i] = merge(replicas[i], snaps[j])
				}
			}
		}
		// One final full round to reach the fixpoint.
		final := make([]GCounter, k)
		copy(final, replicas)
		for i := 0; i < k; i++ {
			for j := 0; j < k; j++ {
				if i != j {
					replicas[i] = merge(replicas[i], final[j])
				}
			}
		}
		// All replicas must now be identical.
		for i := 1; i < k; i++ {
			if !equal(replicas[0], replicas[i]) {
				t.Fatalf("convergence FAILED on trial %d: replica 0 != replica %d", trial, i)
			}
		}
	}
}

// ----------------------------------------------------------------------------
// Expected result
// ----------------------------------------------------------------------------
//
//   $ go test -v -run Properties exercise-03-semilattice-properties.go
//   === RUN   TestProperties_Commutativity
//   --- PASS: TestProperties_Commutativity
//   === RUN   TestProperties_Associativity
//   --- PASS: TestProperties_Associativity
//   === RUN   TestProperties_Idempotence
//   --- PASS: TestProperties_Idempotence
//   === RUN   TestProperties_Convergence
//   --- PASS: TestProperties_Convergence
//   PASS
//
// To prove the tests BITE, break merge: replace `>=` with `<` (making it element-wise
// MIN). Idempotence still passes (min(a,a)=a), but it is no longer a monotonic join
// for a grow-only counter -- and the convergence test still passes for min too,
// because min is ALSO a semilattice! The real lesson: try `out.counts[i] = a+b`
// (sum), and idempotence FAILS immediately (a+a != a), correctly flagging that
// "sum" is not a valid CRDT merge. That is the property test catching a real bug.
