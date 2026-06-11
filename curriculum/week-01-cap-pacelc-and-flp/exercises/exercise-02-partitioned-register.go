// Exercise 2 — The partitioned register (watch CAP happen in your terminal)
//
// Goal: Build a two-node replicated register with a CONTROLLABLE network
//       partition, then run it in two modes and watch the CAP tradeoff:
//
//   CP mode: under partition, the minority side REFUSES writes (and stale reads)
//            to preserve linearizability. Availability is sacrificed. No divergence.
//   AP mode: under partition, BOTH sides keep accepting writes. Availability is
//            preserved. The replicas DIVERGE and must be reconciled on heal.
//
// This is the Gilbert-Lynch proof, executable: a write to one side, a read from
// the other across a dropped link, and the impossibility of being both available
// and consistent at that moment.
//
// HOW TO RUN
//
//   go run exercise-02-partitioned-register.go
//   go run -race exercise-02-partitioned-register.go   # prove no data races
//
// The program runs two scenarios (CP then AP) and prints a labeled trace plus a
// PASS/FAIL self-check for each. Read the trace alongside Lecture 1 sections 2.4
// and 2.5.
//
// ACCEPTANCE CRITERIA
//
//   [ ] CP scenario: during the partition, the minority node's write/read is
//       REJECTED (returns ErrUnavailable). The majority stays linearizable. After
//       heal, both nodes agree. Self-check prints "CP PASS".
//   [ ] AP scenario: during the partition, BOTH writes are ACCEPTED, the two nodes
//       hold DIFFERENT values (divergence), and after heal a reconciliation step
//       converges them to one value. Self-check prints "AP PASS".
//   [ ] You can fill in the "name the tradeoff" template from the week README for
//       each mode without hesitation.
//
// Expected output (shape) is at the bottom of this file.

package main

import (
	"errors"
	"fmt"
	"sync"
	"time"
)

// ErrUnavailable is what a CP node returns when it cannot safely serve a request
// because it is on the minority side of a partition. This is CAP's "sacrifice
// availability": a correct refusal rather than a wrong answer.
var ErrUnavailable = errors.New("unavailable: cannot guarantee consistency on the minority side of a partition")

// Mode selects the system's behavior under partition.
type Mode int

const (
	CP Mode = iota // Consistent under partition: minority refuses.
	AP             // Available under partition: both sides answer, may diverge.
)

func (m Mode) String() string {
	if m == CP {
		return "CP"
	}
	return "AP"
}

// versioned is a value tagged with a monotonically increasing version and the id
// of the node that last wrote it. The version is a Lamport-style logical clock
// (Week 2 makes this rigorous); here it is enough to order writes for reconcile.
type versioned struct {
	value   string
	version uint64
	writer  int
}

// Cluster is a tiny two-node replicated register. node[0] and node[1] each hold a
// replica. A boolean `connected` simulates the network link between them: when
// false, the nodes are partitioned and cannot replicate to each other.
type Cluster struct {
	mu        sync.Mutex
	mode      Mode
	connected bool
	node      [2]versioned
	clock     uint64 // shared logical-clock source for write versions
}

func NewCluster(mode Mode) *Cluster {
	return &Cluster{
		mode:      mode,
		connected: true,
		node:      [2]versioned{{value: "v0"}, {value: "v0"}},
	}
}

// nextVersion returns a fresh, strictly increasing version. Caller holds mu.
func (c *Cluster) nextVersion() uint64 {
	c.clock++
	return c.clock
}

// Partition cuts the link between the two nodes. After this, writes do not
// replicate across nodes until Heal is called.
func (c *Cluster) Partition() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.connected = false
}

// quorumSide reports whether `node` is on the majority side of the partition.
// With two nodes we designate node 0 as the majority side when partitioned (a
// stand-in for "the side that retained quorum"; with 3+ nodes this would be a
// real majority count). The minority side (node 1) is what loses availability.
func (c *Cluster) quorumSide(node int) bool {
	if c.connected {
		return true // no partition: everyone has quorum
	}
	return node == 0 // partitioned: node 0 is the majority side
}

// Write applies a write at `node`. Behavior depends on mode and connectivity.
func (c *Cluster) Write(node int, value string) (uint64, error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.mode == CP && !c.quorumSide(node) {
		// CP: the minority side cannot safely accept a write — it might conflict
		// with a write on the majority side that it cannot see. Refuse. This is
		// the sacrifice of AVAILABILITY to preserve LINEARIZABILITY.
		return 0, ErrUnavailable
	}

	ver := c.nextVersion()
	c.node[node] = versioned{value: value, version: ver, writer: node}

	if c.connected {
		// Healthy network: replicate synchronously to the peer so both replicas
		// stay linearizable.
		other := 1 - node
		c.node[other] = c.node[node]
	}
	// If partitioned in AP mode, we intentionally do NOT replicate; the nodes
	// diverge. That divergence is the cost of staying available.
	return ver, nil
}

// Read returns the value at `node`. In CP mode a minority read is refused (a stale
// read would violate linearizability). In AP mode every read is served, possibly
// stale or divergent.
func (c *Cluster) Read(node int) (string, error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.mode == CP && !c.quorumSide(node) {
		return "", ErrUnavailable
	}
	return c.node[node].value, nil
}

// Heal restores the link and, for AP mode, reconciles divergent replicas using a
// deterministic rule: highest version wins, ties broken by writer id. This is a
// last-writer-wins (LWW) merge — simple, total, and a footgun in production
// because it silently discards a concurrent write (Week 3 replaces it with CRDTs).
func (c *Cluster) Heal() (string, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.connected = true

	a, b := c.node[0], c.node[1]
	if a.version == b.version && a.value == b.value {
		return a.value, nil // already in agreement
	}

	// LWW reconcile: higher version wins; tie -> higher writer id wins.
	winner := a
	if b.version > a.version || (b.version == a.version && b.writer > a.writer) {
		winner = b
	}
	c.node[0] = winner
	c.node[1] = winner
	return winner.value, nil
}

// snapshot returns the current value at each node, for tracing.
func (c *Cluster) snapshot() (string, string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.node[0].value, c.node[1].value
}

// ----------------------------------------------------------------------------
// Scenarios
// ----------------------------------------------------------------------------

func runCP() bool {
	fmt.Println("===================== CP MODE =====================")
	c := NewCluster(CP)

	fmt.Println("[healthy] write v1 at node 0")
	if _, err := c.Write(0, "v1"); err != nil {
		fmt.Println("  unexpected error:", err)
		return false
	}
	n0, n1 := c.snapshot()
	fmt.Printf("  state: node0=%q node1=%q (replicated, linearizable)\n", n0, n1)

	fmt.Println("[partition] cut the link between node 0 (majority) and node 1 (minority)")
	c.Partition()

	fmt.Println("[partitioned] write v2 at node 0 (majority side)")
	if _, err := c.Write(0, "v2"); err != nil {
		fmt.Println("  unexpected error:", err)
		return false
	}

	fmt.Println("[partitioned] write v3 at node 1 (minority side) -- expect REFUSAL")
	_, err := c.Write(1, "v3")
	if !errors.Is(err, ErrUnavailable) {
		fmt.Println("  FAIL: minority write should have been refused, got:", err)
		return false
	}
	fmt.Println("  refused as expected:", err)

	fmt.Println("[partitioned] read at node 1 (minority) -- expect REFUSAL (no stale reads)")
	_, rerr := c.Read(1)
	if !errors.Is(rerr, ErrUnavailable) {
		fmt.Println("  FAIL: minority read should have been refused, got:", rerr)
		return false
	}
	fmt.Println("  refused as expected:", rerr)

	got, _ := c.Read(0)
	fmt.Printf("[partitioned] read at node 0 (majority) -> %q (still linearizable)\n", got)

	fmt.Println("[heal] restore the link")
	final, _ := c.Heal()
	n0, n1 = c.snapshot()
	fmt.Printf("  reconciled value: %q  (node0=%q node1=%q)\n", final, n0, n1)

	ok := final == "v2" && n0 == n1
	if ok {
		fmt.Println("CP PASS: minority sacrificed availability; no divergence; reads were never stale.\n")
	} else {
		fmt.Println("CP FAIL\n")
	}
	return ok
}

func runAP() bool {
	fmt.Println("===================== AP MODE =====================")
	c := NewCluster(AP)

	fmt.Println("[healthy] write v1 at node 0")
	if _, err := c.Write(0, "v1"); err != nil {
		fmt.Println("  unexpected error:", err)
		return false
	}

	fmt.Println("[partition] cut the link")
	c.Partition()

	fmt.Println("[partitioned] write v2 at node 0 -- ACCEPTED (stay available)")
	if _, err := c.Write(0, "v2"); err != nil {
		fmt.Println("  FAIL: AP should accept the write, got:", err)
		return false
	}
	fmt.Println("[partitioned] write v3 at node 1 -- ACCEPTED (stay available)")
	if _, err := c.Write(1, "v3"); err != nil {
		fmt.Println("  FAIL: AP should accept the write, got:", err)
		return false
	}

	n0, n1 := c.snapshot()
	fmt.Printf("[partitioned] DIVERGENCE: node0=%q node1=%q (both available, inconsistent)\n", n0, n1)
	diverged := n0 != n1
	if !diverged {
		fmt.Println("  FAIL: expected divergence under AP partition")
		return false
	}

	fmt.Println("[heal] restore link and reconcile (last-writer-wins)")
	final, _ := c.Heal()
	n0, n1 = c.snapshot()
	fmt.Printf("  converged value: %q  (node0=%q node1=%q)\n", final, n0, n1)

	ok := diverged && n0 == n1
	if ok {
		fmt.Println("AP PASS: both sides stayed available; replicas diverged; reconcile converged them.")
		fmt.Println("NOTE: LWW silently discarded the losing concurrent write (v2 or v3). That data loss")
		fmt.Println("      is the AP footgun CRDTs fix in Week 3.\n")
	} else {
		fmt.Println("AP FAIL\n")
	}
	return ok
}

func main() {
	start := time.Now()
	cpOK := runCP()
	apOK := runAP()

	fmt.Println("===================== SUMMARY =====================")
	fmt.Printf("CP scenario: %s\n", passFail(cpOK))
	fmt.Printf("AP scenario: %s\n", passFail(apOK))
	fmt.Printf("(elapsed %s)\n", time.Since(start).Round(time.Millisecond))
	fmt.Println()
	fmt.Println("Name the tradeoff (fill these in for yourself):")
	fmt.Println("  CP: during a partition it refused WRITES+READS on the minority to preserve LINEARIZABILITY;")
	fmt.Println("      it gave up AVAILABILITY on that side.")
	fmt.Println("  AP: during a partition it accepted writes on BOTH sides to preserve AVAILABILITY;")
	fmt.Println("      it gave up CONSISTENCY (divergence) and paid with a reconcile + possible data loss.")
}

func passFail(ok bool) string {
	if ok {
		return "PASS"
	}
	return "FAIL"
}

// ----------------------------------------------------------------------------
// Expected output (shape; exact wording stable, ordering deterministic)
// ----------------------------------------------------------------------------
//
// ===================== CP MODE =====================
// [healthy] write v1 at node 0
//   state: node0="v1" node1="v1" (replicated, linearizable)
// [partition] cut the link between node 0 (majority) and node 1 (minority)
// [partitioned] write v2 at node 0 (majority side)
// [partitioned] write v3 at node 1 (minority side) -- expect REFUSAL
//   refused as expected: unavailable: cannot guarantee consistency ...
// [partitioned] read at node 1 (minority) -- expect REFUSAL (no stale reads)
//   refused as expected: unavailable: cannot guarantee consistency ...
// [partitioned] read at node 0 (majority) -> "v2" (still linearizable)
// [heal] restore the link
//   reconciled value: "v2"  (node0="v2" node1="v2")
// CP PASS: minority sacrificed availability; no divergence; reads were never stale.
//
// ===================== AP MODE =====================
// ... both writes accepted, divergence node0="v2" node1="v3",
//     converged value "v3" (higher writer id breaks the version tie), AP PASS ...
//
// ===================== SUMMARY =====================
// CP scenario: PASS
// AP scenario: PASS
//
// The lesson: at the instant of partition you CHOSE. CP refused to stay correct;
// AP answered and diverged. There is no third option that is both available and
// linearizable across the cut — that is Gilbert-Lynch, run in your terminal.
