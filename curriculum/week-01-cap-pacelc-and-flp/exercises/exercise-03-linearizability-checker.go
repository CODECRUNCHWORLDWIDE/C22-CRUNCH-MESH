// Exercise 3 — The linearizability checker (turn the definition into a yes/no)
//
// Goal: Take a recorded HISTORY of operations on a single read/write register and
//       decide whether it is LINEARIZABLE: does there exist a single total order
//       of the operations that (a) respects real-time precedence (if op A returned
//       before op B was invoked, A is before B in the order) and (b) is a legal
//       sequential execution of a register (every read returns the value of the
//       most recent preceding write)?
//
// This makes Lecture 1's abstract definition operational. The checker uses the
// classic Wing-Gong / Lowe backtracking search: repeatedly try to "linearize" an
// operation whose invocation has already happened, apply it to a model register,
// recurse, and backtrack if no completion is possible. For single-register
// histories this is efficient enough to check by hand-sized inputs.
//
// HOW TO RUN
//
//   go run exercise-03-linearizability-checker.go
//
// It runs four built-in histories — two linearizable, two not — and prints the
// verdict and (for the linearizable ones) a witnessing linear order.
//
// ACCEPTANCE CRITERIA
//
//   [ ] History H1 (sequential, obviously legal) -> LINEARIZABLE.
//   [ ] History H2 (concurrent but reorderable into a legal order) -> LINEARIZABLE,
//       and the printed witness order is a legal register execution.
//   [ ] History H3 (a read returns a value no write ever produced) -> NOT
//       linearizable.
//   [ ] History H4 (real-time violation: a read after a completed write returns the
//       old value, with no concurrency to excuse it) -> NOT linearizable.
//   [ ] You can explain, for H4, exactly which real-time edge the search could not
//       satisfy.
//
// Expected output (shape) is at the bottom of this file.

package main

import (
	"fmt"
	"sort"
)

// OpKind is read or write.
type OpKind int

const (
	Write OpKind = iota
	Read
)

func (k OpKind) String() string {
	if k == Write {
		return "W"
	}
	return "R"
}

// Op is one operation on the register, with a real-time interval [Invoke, Return].
// For a write, Value is the value written. For a read, Value is the value the read
// observed (its response). Times are abstract logical ticks; only their ORDER
// matters. Two ops are concurrent if their intervals overlap.
type Op struct {
	ID     int
	Kind   OpKind
	Value  string
	Invoke int
	Return int
}

func (o Op) String() string {
	return fmt.Sprintf("%s(%s)#%d[%d,%d]", o.Kind, o.Value, o.ID, o.Invoke, o.Return)
}

// precedes reports whether op a happens-before op b in real time: a returned
// strictly before b was invoked. If neither precedes the other, they are
// concurrent and may be linearized in either order.
func precedes(a, b Op) bool {
	return a.Return < b.Invoke
}

// linearizable decides whether `ops` has a valid linearization, and if so returns
// one witnessing order. The register starts at initial value `init`.
//
// Algorithm (backtracking over linearization points):
//   - We maintain the set of ops not yet placed in the linear order.
//   - At each step, an op is ELIGIBLE to be placed next iff no other unplaced op
//     must precede it in real time (i.e., no unplaced op p with precedes(p, op)).
//     Placing a non-eligible op would violate real-time order.
//   - For a write, placing it just updates the model register value.
//   - For a read, placing it is legal only if the read's observed Value equals the
//     model register's current value (a register read must return the latest write).
//   - Recurse; if the recursion fails, backtrack and try a different eligible op.
//   - Success when all ops are placed.
func linearizable(ops []Op, init string) (bool, []Op) {
	remaining := make([]Op, len(ops))
	copy(remaining, ops)
	var order []Op
	ok := search(remaining, init, &order)
	return ok, order
}

func search(remaining []Op, regValue string, order *[]Op) bool {
	if len(remaining) == 0 {
		return true
	}
	for i := range remaining {
		cand := remaining[i]
		if !eligible(cand, remaining) {
			continue // some other unplaced op must come before cand
		}

		// Compute the model state after applying cand, and whether cand is legal.
		newValue := regValue
		legal := true
		if cand.Kind == Write {
			newValue = cand.Value
		} else { // Read must observe the current register value.
			legal = cand.Value == regValue
		}
		if !legal {
			continue // this read cannot be placed here; try another candidate
		}

		// Tentatively place cand and recurse on the rest.
		rest := removeIndex(remaining, i)
		*order = append(*order, cand)
		if search(rest, newValue, order) {
			return true
		}
		// Backtrack.
		*order = (*order)[:len(*order)-1]
	}
	return false
}

// eligible reports whether `cand` can be placed next: no OTHER op still in
// `remaining` is required by real time to precede it.
func eligible(cand Op, remaining []Op) bool {
	for _, p := range remaining {
		if p.ID == cand.ID {
			continue
		}
		if precedes(p, cand) {
			return false
		}
	}
	return true
}

func removeIndex(s []Op, i int) []Op {
	out := make([]Op, 0, len(s)-1)
	out = append(out, s[:i]...)
	out = append(out, s[i+1:]...)
	return out
}

// ----------------------------------------------------------------------------
// Built-in histories
// ----------------------------------------------------------------------------

func report(name, desc string, ops []Op, init string, wantLinearizable bool) bool {
	// Print the history sorted by invoke time for readability.
	sorted := make([]Op, len(ops))
	copy(sorted, ops)
	sort.Slice(sorted, func(i, j int) bool { return sorted[i].Invoke < sorted[j].Invoke })

	fmt.Printf("---- %s ----\n%s\n", name, desc)
	fmt.Print("history: ")
	for _, o := range sorted {
		fmt.Printf("%s ", o)
	}
	fmt.Println()

	ok, order := linearizable(ops, init)
	verdict := "NOT LINEARIZABLE"
	if ok {
		verdict = "LINEARIZABLE"
	}
	fmt.Printf("verdict: %s\n", verdict)
	if ok {
		fmt.Print("witness: ")
		for _, o := range order {
			fmt.Printf("%s ", o)
		}
		fmt.Println()
	}

	pass := ok == wantLinearizable
	if pass {
		fmt.Println("self-check: PASS")
	} else {
		fmt.Printf("self-check: FAIL (wanted linearizable=%v)\n", wantLinearizable)
	}
	fmt.Println()
	return pass
}

func main() {
	allPass := true

	// H1 — strictly sequential and legal: write x, then read x.
	// Real-time: W returns at 2, R invoked at 3. Obviously linearizable.
	h1 := []Op{
		{ID: 1, Kind: Write, Value: "x", Invoke: 1, Return: 2},
		{ID: 2, Kind: Read, Value: "x", Invoke: 3, Return: 4},
	}
	allPass = report("H1", "sequential: W(x) then R->x. Trivially legal.", h1, "v0", true) && allPass

	// H2 — concurrent writes and reads that DO admit a legal order.
	// Two writers overlap; a reader observes "b". A valid linearization is:
	//   W(a) , W(b) , R(b)   -- real time allows W(a) and W(b) in either order
	// because their intervals overlap, and R(b) after both is legal.
	h2 := []Op{
		{ID: 1, Kind: Write, Value: "a", Invoke: 1, Return: 4},
		{ID: 2, Kind: Write, Value: "b", Invoke: 2, Return: 5},
		{ID: 3, Kind: Read, Value: "b", Invoke: 6, Return: 7},
	}
	allPass = report("H2", "concurrent W(a)||W(b), then R->b. Reorderable into a legal order.", h2, "v0", true) && allPass

	// H3 — a read returns a value NEVER written. No order can make a register
	// read return "z" when only "a" was ever written. NOT linearizable.
	h3 := []Op{
		{ID: 1, Kind: Write, Value: "a", Invoke: 1, Return: 2},
		{ID: 2, Kind: Read, Value: "z", Invoke: 3, Return: 4},
	}
	allPass = report("H3", "R observes 'z' but only 'a' was ever written. Impossible.", h3, "v0", false) && allPass

	// H4 — a real-time violation with NO concurrency to excuse it:
	//   W(a) completes (returns at 2), THEN a read invoked at 3 returns "v0".
	// Because W(a) precedes R in real time, any linearization must place W(a)
	// before R, so R must observe "a", not the initial "v0". NOT linearizable.
	h4 := []Op{
		{ID: 1, Kind: Write, Value: "a", Invoke: 1, Return: 2},
		{ID: 2, Kind: Read, Value: "v0", Invoke: 3, Return: 4},
	}
	allPass = report("H4", "W(a) completes before R is invoked, yet R returns the OLD value. Real-time violated.", h4, "v0", false) && allPass

	fmt.Println("===================== SUMMARY =====================")
	if allPass {
		fmt.Println("ALL SELF-CHECKS PASS")
	} else {
		fmt.Println("SOME SELF-CHECKS FAILED")
	}
}

// ----------------------------------------------------------------------------
// Expected output (shape)
// ----------------------------------------------------------------------------
//
// ---- H1 ----
// sequential: W(x) then R->x. Trivially legal.
// history: W(x)#1[1,2] R(x)#2[3,4]
// verdict: LINEARIZABLE
// witness: W(x)#1[1,2] R(x)#2[3,4]
// self-check: PASS
//
// ---- H2 ----
// verdict: LINEARIZABLE   (witness: W(a) W(b) R(b)  -- concurrent writes reordered)
// self-check: PASS
//
// ---- H3 ----
// verdict: NOT LINEARIZABLE   (R observed a value never written)
// self-check: PASS
//
// ---- H4 ----
// verdict: NOT LINEARIZABLE
// self-check: PASS
//
// ===================== SUMMARY =====================
// ALL SELF-CHECKS PASS
//
// Why H4 fails, precisely: the search tries to place the only eligible-first op.
// W(a) returns at t=2 and R is invoked at t=3, so precedes(W,R) is true: W is the
// ONLY op eligible to go first. After placing W the register holds "a", but R
// claims to have observed "v0" -> illegal read -> no completion -> NOT linearizable.
// That single unsatisfiable real-time edge is the whole violation.
