// Exercise 3 — The distributed-monolith smell detector (Go)
//
// Goal: Detect the distributed-monolith anti-pattern (Lecture 2 §2.1) and the
//       chatty mesh from a call-graph spec. The distributed monolith has two
//       mechanical fingerprints we can find without running anything:
//         1. Deploy lockstep: services that must ship together because of a
//            version-pinned synchronous dependency cycle.
//         2. Synchronous request fan-out depth: a single user action that fans
//            through a long chain of synchronous hops, multiplying latency and
//            failure.
//
// Estimated time: 45 minutes. Runnable.
//
// HOW TO USE THIS FILE
//
//	go run exercise-03-distributed-monolith-smell.go
//
//	It analyzes a deliberately-flawed topology (a sync dependency CYCLE and a
//	deep sync chain), prints the findings, and EXITS NON-ZERO. Then it analyzes a
//	corrected topology (cycle broken with an async event, chain shortened) and
//	exits 0. Read both reports.
//
// ACCEPTANCE CRITERIA
//
//	[ ] The flawed run reports a synchronous dependency CYCLE (cart -> order ->
//	    cart) and a deep synchronous chain, and exits non-zero.
//	[ ] The fixed run reports no cycle, an acceptable chain depth, and exits 0.
//	[ ] You can explain why a sync cycle forces lockstep deploys (each service's
//	    release is pinned to the other's, so neither deploys independently).
//
// Standard library only. No modules, no network. Expected output at the bottom.
package main

import (
	"fmt"
	"os"
	"sort"
)

// Edge is one dependency from a service to another, per single user action.
type Edge struct {
	To    string
	Kind  string // "sync" or "async"
	Count int    // calls per action; >1 is a loop
}

// Service in the topology. VersionPinnedOn lists services this one's release is
// hard-pinned to (cannot deploy without a matching version) — the real signature
// of a distributed monolith.
type Service struct {
	Name            string
	Edges           []Edge
	VersionPinnedOn []string
}

// Topology is the whole proposed split.
type Topology struct {
	Name     string
	Services []Service
}

func (t Topology) byName() map[string]Service {
	m := make(map[string]Service, len(t.Services))
	for _, s := range t.Services {
		m[s.Name] = s
	}
	return m
}

// Finding is one detected smell.
type Finding struct {
	Severity string // "ERROR" or "WARN"
	Rule     string
	Message  string
}

// detectSyncCycles finds cycles in the SYNCHRONOUS call graph. A sync cycle means
// two (or more) services call each other synchronously and so cannot be deployed
// or reasoned about independently — the core distributed-monolith fingerprint.
// (Async edges do NOT count: an event loop is decoupled in time and is fine.)
func detectSyncCycles(t Topology) []Finding {
	graph := map[string][]string{}
	for _, s := range t.Services {
		for _, e := range s.Edges {
			if e.Kind == "sync" {
				graph[s.Name] = append(graph[s.Name], e.To)
			}
		}
	}

	var findings []Finding
	const (
		white = 0 // unvisited
		gray  = 1 // on the current DFS stack
		black = 2 // fully explored
	)
	color := map[string]int{}
	var stack []string
	seen := map[string]bool{} // dedupe reported cycles by their member set key

	var dfs func(node string)
	dfs = func(node string) {
		color[node] = gray
		stack = append(stack, node)
		for _, next := range graph[node] {
			switch color[next] {
			case white:
				dfs(next)
			case gray:
				// Found a back-edge -> cycle. Extract it from the stack.
				cycle := extractCycle(stack, next)
				key := cycleKey(cycle)
				if !seen[key] {
					seen[key] = true
					findings = append(findings, Finding{
						Severity: "ERROR",
						Rule:     "sync-cycle",
						Message: fmt.Sprintf(
							"synchronous dependency cycle: %s. These services call "+
								"each other synchronously and cannot deploy "+
								"independently — a distributed monolith. Break the "+
								"cycle with an asynchronous event in one direction.",
							formatCycle(cycle)),
					})
				}
			}
		}
		stack = stack[:len(stack)-1]
		color[node] = black
	}

	// Visit in a stable order so output is deterministic.
	names := make([]string, 0, len(t.Services))
	for _, s := range t.Services {
		names = append(names, s.Name)
	}
	sort.Strings(names)
	for _, n := range names {
		if color[n] == white {
			dfs(n)
		}
	}
	return findings
}

func extractCycle(stack []string, start string) []string {
	for i, n := range stack {
		if n == start {
			cyc := append([]string{}, stack[i:]...)
			return cyc
		}
	}
	return append([]string{}, stack...)
}

func cycleKey(cycle []string) string {
	s := append([]string{}, cycle...)
	sort.Strings(s)
	key := ""
	for _, n := range s {
		key += n + "|"
	}
	return key
}

func formatCycle(cycle []string) string {
	out := ""
	for _, n := range cycle {
		out += n + " -> "
	}
	if len(cycle) > 0 {
		out += cycle[0] // close the loop
	}
	return out
}

// detectVersionLockstep flags any service hard-pinned to another's version. If
// cart only works with order vX and order only works with cart vX, they ship as
// a unit — the distributed monolith's deploy signature, independent of the call
// graph.
func detectVersionLockstep(t Topology) []Finding {
	var findings []Finding
	byName := t.byName()
	reported := map[string]bool{}
	for _, s := range t.Services {
		for _, dep := range s.VersionPinnedOn {
			other, ok := byName[dep]
			if !ok {
				continue
			}
			mutual := false
			for _, back := range other.VersionPinnedOn {
				if back == s.Name {
					mutual = true
				}
			}
			pair := pairKey(s.Name, dep)
			if mutual && !reported[pair] {
				reported[pair] = true
				findings = append(findings, Finding{
					Severity: "ERROR",
					Rule:     "deploy-lockstep",
					Message: fmt.Sprintf(
						"'%s' and '%s' are version-pinned to each other; neither can "+
							"deploy independently. Use a backward-compatible contract "+
							"so vN talks to vN-1.", s.Name, dep),
				})
			}
		}
	}
	return findings
}

func pairKey(a, b string) string {
	if a > b {
		a, b = b, a
	}
	return a + "::" + b
}

// detectDeepChain measures the longest SYNCHRONOUS chain from each entry service
// and warns when it exceeds maxDepth. Deep sync chains multiply latency and
// failure (Lecture 2 §2.3). Only meaningful when there is no cycle.
func detectDeepChain(t Topology, maxDepth int) []Finding {
	graph := map[string][]string{}
	for _, s := range t.Services {
		for _, e := range s.Edges {
			if e.Kind == "sync" {
				graph[s.Name] = append(graph[s.Name], e.To)
			}
		}
	}

	// Longest path via memoized DFS; guard against cycles with a visiting set.
	memo := map[string]int{}
	visiting := map[string]bool{}
	var longest func(node string) int
	longest = func(node string) int {
		if d, ok := memo[node]; ok {
			return d
		}
		if visiting[node] {
			return 0 // a cycle; depth handled by detectSyncCycles
		}
		visiting[node] = true
		best := 0
		for _, next := range graph[node] {
			if d := longest(next) + 1; d > best {
				best = d
			}
		}
		visiting[node] = false
		memo[node] = best
		return best
	}

	var findings []Finding
	names := make([]string, 0, len(t.Services))
	for _, s := range t.Services {
		names = append(names, s.Name)
	}
	sort.Strings(names)
	for _, n := range names {
		if d := longest(n); d > maxDepth {
			findings = append(findings, Finding{
				Severity: "WARN",
				Rule:     "deep-sync-chain",
				Message: fmt.Sprintf(
					"action entering '%s' fans through %d synchronous hops "+
						"(max recommended %d); latency and failure compound. "+
						"Shorten with async events or coarser boundaries.",
					n, d, maxDepth),
			})
		}
	}
	return findings
}

func analyze(t Topology) (int, []Finding) {
	var findings []Finding
	findings = append(findings, detectVersionLockstep(t)...)
	cycles := detectSyncCycles(t)
	findings = append(findings, cycles...)
	// Only run the depth check if there is no cycle (a cycle is infinite depth).
	if len(cycles) == 0 {
		findings = append(findings, detectDeepChain(t, 3)...)
	}
	code := 0
	for _, f := range findings {
		if f.Severity == "ERROR" {
			code = 1
		}
	}
	return code, findings
}

func report(t Topology) int {
	fmt.Printf("\n%s\n", repeat("=", 70))
	fmt.Printf("TOPOLOGY: %s  (%d services)\n", t.Name, len(t.Services))
	fmt.Println(repeat("=", 70))
	for _, s := range t.Services {
		sync, async := 0, 0
		for _, e := range s.Edges {
			if e.Kind == "sync" {
				sync += e.Count
			} else {
				async += e.Count
			}
		}
		fmt.Printf("  %-10s sync=%d async=%d pinned_on=%v\n",
			s.Name, sync, async, s.VersionPinnedOn)
	}
	code, findings := analyze(t)
	fmt.Println(repeat("-", 70))
	if len(findings) == 0 {
		fmt.Println("FINDINGS: none. No distributed-monolith fingerprint.")
	}
	nErr, nWarn := 0, 0
	for _, f := range findings {
		fmt.Printf("  [%-5s] %-16s %s\n", f.Severity, f.Rule, f.Message)
		if f.Severity == "ERROR" {
			nErr++
		} else {
			nWarn++
		}
	}
	fmt.Println(repeat("-", 70))
	verdict := "PASS (exit 0)"
	if code != 0 {
		verdict = "FAIL (exit 1)"
	}
	fmt.Printf("score: %d ERROR, %d WARN  ->  %s\n", nErr, nWarn, verdict)
	return code
}

func repeat(s string, n int) string {
	out := ""
	for i := 0; i < n; i++ {
		out += s
	}
	return out
}

func main() {
	// FLAWED: cart and order call each other synchronously (a cycle) AND are
	// version-pinned to each other; a deep sync chain runs through checkout.
	flawed := Topology{
		Name: "FLAWED (cart<->order sync cycle, deep chain)",
		Services: []Service{
			{
				Name:            "cart",
				Edges:           []Edge{{To: "order", Kind: "sync", Count: 1}, {To: "catalog", Kind: "sync", Count: 1}},
				VersionPinnedOn: []string{"order"},
			},
			{
				Name:            "order",
				Edges:           []Edge{{To: "cart", Kind: "sync", Count: 1}, {To: "payment", Kind: "sync", Count: 1}},
				VersionPinnedOn: []string{"cart"},
			},
			{Name: "catalog", Edges: []Edge{{To: "pricing", Kind: "sync", Count: 1}}},
			{Name: "pricing", Edges: []Edge{{To: "tax", Kind: "sync", Count: 1}}},
			{Name: "tax", Edges: []Edge{{To: "geo", Kind: "sync", Count: 1}}},
			{Name: "geo", Edges: nil},
			{Name: "payment", Edges: nil},
		},
	}

	// FIXED: order reacts to a cart event (async) — cycle broken; the catalog
	// chain is shortened by folding tax/geo into pricing.
	fixed := Topology{
		Name: "FIXED (event-driven order, shallow chains)",
		Services: []Service{
			{
				Name:  "cart",
				Edges: []Edge{{To: "order", Kind: "async", Count: 1}, {To: "catalog", Kind: "sync", Count: 1}},
			},
			{
				Name:  "order",
				Edges: []Edge{{To: "payment", Kind: "async", Count: 1}},
			},
			{Name: "catalog", Edges: []Edge{{To: "pricing", Kind: "sync", Count: 1}}},
			{Name: "pricing", Edges: nil}, // tax+geo folded in; owns its own tables
			{Name: "payment", Edges: nil},
		},
	}

	flawedCode := report(flawed)
	fixedCode := report(fixed)

	fmt.Printf("\n%s\n", repeat("=", 70))
	fmt.Println("SUMMARY")
	fmt.Println(repeat("=", 70))
	fmt.Printf("  flawed topology exit code: %d  (expected 1)\n", flawedCode)
	fmt.Printf("  fixed  topology exit code: %d  (expected 0)\n", fixedCode)

	if flawedCode == 1 && fixedCode == 0 {
		fmt.Println("  tool behaves correctly: FAILS the distributed monolith, PASSES the fix.")
		os.Exit(0)
	}
	fmt.Println("  UNEXPECTED: detector did not behave as designed; re-check your edits.")
	os.Exit(2)
}

// -----------------------------------------------------------------------------
// Expected output (abridged)
// -----------------------------------------------------------------------------
//
// ======================================================================
// TOPOLOGY: FLAWED (cart<->order sync cycle, deep chain)  (7 services)
// ======================================================================
//   cart       sync=2 async=0 pinned_on=[order]
//   order      sync=2 async=0 pinned_on=[cart]
//   ...
// ----------------------------------------------------------------------
//   [ERROR] deploy-lockstep   'cart' and 'order' are version-pinned to each other; ...
//   [ERROR] sync-cycle        synchronous dependency cycle: cart -> order -> cart. ...
// ----------------------------------------------------------------------
// score: 2 ERROR, 0 WARN  ->  FAIL (exit 1)
//
// ======================================================================
// TOPOLOGY: FIXED (event-driven order, shallow chains)  (5 services)
// ======================================================================
//   ...
// ----------------------------------------------------------------------
// FINDINGS: none. No distributed-monolith fingerprint.
// ----------------------------------------------------------------------
// score: 0 ERROR, 0 WARN  ->  PASS (exit 0)
//
// The lesson: making ONE edge asynchronous (cart -> order) breaks the cycle and
// dissolves the distributed monolith. That single change is the difference
// between two services that deploy together forever and two that are independent.
// -----------------------------------------------------------------------------
