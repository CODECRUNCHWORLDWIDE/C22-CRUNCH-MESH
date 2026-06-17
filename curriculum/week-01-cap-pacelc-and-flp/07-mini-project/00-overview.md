# Mini-Project — The Three-Regime Register: Exhibiting CAP Experimentally

> Build an instrumented, three-node replicated register in Go that you can drive into a network partition on command, and **experimentally exhibit** all three CAP regimes: **CP** (the minority refuses, consistency preserved), **AP** (everyone answers, replicas diverge), and the **impossibility of CA** (a proof, in your own test harness, that you cannot be both available and linearizable across the cut). The deliverable is not a toy — it is a small, tested, runnable lab that turns Gilbert–Lynch from a theorem you read into a result you produced.

This is the artifact that makes the week's theory yours. Anyone can recite "pick CP or AP." After this project you will have *built* both, *measured* the difference, and *demonstrated* — with a checker, not a hand-wave — that the third option does not exist.

**Estimated time:** ~12 hours, split across Thursday, Friday, and Saturday in the suggested schedule.

**Compounds forward:** This register is the skeleton you will graft Raft onto in **Week 2**. The replication, the partition simulator, and the linearizability checker you build here are reused when you replace "synchronous replicate to peer" with "append to a Raft log and wait for a quorum." Build the seams cleanly now; you will thank yourself next week.

---

## What you will build

A Go module `regime-register` with three deliverables:

1. **`register/` package** — a three-node replicated register with a controllable partition simulator and a pluggable consistency *mode* (CP or AP). Majority quorum (2 of 3) is the unit of "consistency."
2. **`checker/` package** — a linearizability checker (the Exercise 3 algorithm, generalized to record live histories) plus an "availability" recorder, so each experiment produces a verdict, not just a log.
3. **An experiment harness** (`cmd/experiments/`) — three runnable scenarios (`cp`, `ap`, `ca-impossible`) that drive the register through a partition and print, for each, a labeled trace and a machine-checked PASS/FAIL.

By the end you have ~300–450 lines of tested Go that any future Crunch Mesh week can read to recall "what does a partition actually do," and a `RESULTS.md` that records the measured difference between CP and AP.

---

## Why three nodes, not two

Exercise 2 used two nodes, which is enough to *show* the tradeoff but too coarse to *measure* it: with two nodes, "majority" is ambiguous. Three nodes give you a real majority quorum (2 of 3), which is the actual mechanism every CP system uses:

- A partition that isolates **one** node leaves a **2-node majority** that can still make progress in CP mode (it has quorum) — and a 1-node minority that cannot.
- A partition that isolates **two** nodes from one leaves **no** majority anywhere; in CP mode the *whole system* stops accepting writes. That is the etcd/ZooKeeper behavior, and seeing it in your own code is the point.

This three-node structure is also exactly the smallest Raft cluster, which is why it is the right skeleton for Week 2.

---

## Package layout

```
regime-register/
├── go.mod
├── README.md                      # how to run, the regime table, your RESULTS summary
├── register/
│   ├── register.go                # the 3-node register, modes, partition simulator
│   └── register_test.go           # unit tests: CP refusal, AP divergence, quorum logic
├── checker/
│   ├── linearizable.go            # the history checker (generalized from Exercise 3)
│   ├── linearizable_test.go       # the four reference histories + your recorded ones
│   └── availability.go            # an availability recorder (counts non-error responses)
├── cmd/experiments/
│   └── main.go                    # the cp / ap / ca-impossible scenarios
└── RESULTS.md                     # measured: write-success rate per regime per partition
```

---

## Deliverable 1 — `register/` (the heart)

The register holds three replicas and a partition simulator. Model the network as a symmetric reachability matrix: `reachable[i][j]` is true iff node i can send to node j. A partition is a set of cut edges. A node has **quorum** iff it can reach a majority of nodes (including itself).

Required behavior:

- **`Write(node, value)`**:
  - **CP mode**: succeeds only if `node` currently has quorum (can reach ≥ 2 of 3). The write replicates synchronously to every reachable peer and is acknowledged only after a quorum has it. If `node` lacks quorum, return `ErrUnavailable`. *No divergence is ever possible.*
  - **AP mode**: always succeeds locally and replicates to whatever peers are reachable. Nodes on opposite sides of a cut diverge. Each write carries a version (a per-node Lamport counter — `(counter, nodeID)`) so reconciliation is deterministic.
- **`Read(node, consistency)`**:
  - A **linearizable** read (CP) requires quorum; otherwise `ErrUnavailable`.
  - An **eventual** read (AP) always returns the local replica's value, possibly stale.
- **`Partition(groups ...[]int)`** — cut the network into the named groups; nodes within a group reach each other, across groups they don't.
- **`Heal()`** — restore full reachability and, in AP mode, run a deterministic reconcile (start with LWW by `(version, nodeID)`; the stretch goal upgrades it).

The version type is the seed of Week 2's logical clocks:

```go
// Version is a Lamport-style logical timestamp: a per-node counter plus the node
// id as a deterministic tiebreaker. Compare lexicographically. This is exactly the
// ordering you will generalize into vector clocks next week.
type Version struct {
    Counter uint64
    NodeID  int
}

func (v Version) Less(o Version) bool {
    if v.Counter != o.Counter {
        return v.Counter < o.Counter
    }
    return v.NodeID < o.NodeID
}
```

A sketch of the quorum check (fill in the rest yourself):

```go
// hasQuorum reports whether `node` can currently reach a strict majority of the
// cluster (itself included). With N=3 the majority is 2.
func (c *Cluster) hasQuorum(node int) bool {
    reachable := 1 // itself
    for peer := 0; peer < c.n; peer++ {
        if peer != node && c.reachable[node][peer] {
            reachable++
        }
    }
    return reachable*2 > c.n
}
```

---

## Deliverable 2 — `checker/` (verdicts, not vibes)

- **`linearizable.go`** — the Exercise 3 backtracking checker, generalized to accept a recorded `[]Op` history where invoke/return times come from the *actual* experiment (use a monotonic counter or `time.Now()` ticks). It must return a verdict and a witness order.
- **`availability.go`** — an `AvailabilityRecorder` that, given a stream of operation results, computes the fraction that returned a non-error response. CP partitions drive this *down* on the minority; AP keeps it at 1.0 everywhere. This number is your *measured* CAP tradeoff.

The whole point is that each experiment ends in two numbers you can defend: **availability** (fraction of requests answered) and **linearizable?** (yes/no on the recorded history). CP trades the first for the second; AP trades the second for the first.

---

## Deliverable 3 — the experiment harness

`cmd/experiments/main.go` takes a scenario name and runs it end to end, recording a history and printing a verdict.

### Scenario `cp`

1. Healthy: write `v1`, confirm all three replicas hold it.
2. Partition `{0,1} | {2}` — node 2 is the 1-node minority.
3. In CP mode: a write at node 0 (majority) **succeeds**; a write at node 2 (minority) is **refused**; a linearizable read at node 2 is **refused**.
4. Record availability (it drops because node 2's requests error) and check the recorded history is **linearizable** (it is — no stale read ever returned).
5. Heal; confirm convergence with no reconciliation needed (nothing diverged).
6. Print: `CP: availability=0.67 linearizable=true -> PASS`.

### Scenario `ap`

1. Healthy: write `v1`.
2. Partition `{0,1} | {2}`.
3. In AP mode: writes at node 0 **and** node 2 both **succeed**; the sides **diverge**.
4. Record availability (=1.0 — everyone answered) and check the recorded history is **NOT linearizable** (a read on one side missed a completed write on the other).
5. Heal; the reconcile converges the replicas; confirm all three agree afterward.
6. Print: `AP: availability=1.00 linearizable=false -> PASS`.

### Scenario `ca-impossible`

This is the proof. Drive a partition and attempt to be **both** available **and** linearizable, and demonstrate — via the checker — that no mode achieves it:

1. Partition `{0,1} | {2}`.
2. Force *full availability* (every node must answer — i.e., run AP semantics so no request errors). Record the history.
3. Run the linearizability checker on the recorded history. It returns **false** whenever a write on one side completed before a read on the other side returned the old value across the cut.
4. Conversely, force *linearizability* (CP semantics). Record availability — it is **< 1.0** because the minority refused.
5. Print a table proving you can get `available=true, linearizable=false` (AP) or `available=false, linearizable=true` (CP), but the cell `available=true AND linearizable=true` is **unreachable** under partition.
6. Print: `CA-IMPOSSIBLE: no run achieved available=true && linearizable=true -> PASS (Gilbert-Lynch confirmed)`.

This scenario is the mini-project's reason to exist. You are not asserting CA is impossible; you are *demonstrating* it with your own checker on your own recorded histories.

---

## Rules

- **You may** read the lectures, the Gilbert–Lynch paper, and the Go standard-library docs.
- **You must not** use any third-party module. The standard library (`sync`, `time`, `sort`, `testing`) is sufficient. No Raft library — that's next week, and using one now defeats the purpose.
- Go 1.22+. `go vet ./...` must be clean. `go test ./...` must pass, including `go test -race ./...` (the partition simulator touches shared state — prove it's safe).
- Every experiment's verdict must be **machine-checked** (a returned bool the harness asserts), not eyeballed from a log line.

## Acceptance criteria

- [ ] A public GitHub repo named `c22-week-01-regime-register-<yourhandle>`.
- [ ] `go build ./...` and `go vet ./...` succeed with no warnings.
- [ ] `go test -race ./...` passes, with at least:
  - `register_test.go`: CP minority write refused; CP majority write succeeds; AP both-sides diverge; `hasQuorum` correct for the no-majority partition `{0}|{1}|{2}`.
  - `linearizable_test.go`: the four reference histories (H1–H4 from Exercise 3) plus at least one history *recorded from a live AP partition run* that the checker correctly flags non-linearizable.
- [ ] `go run ./cmd/experiments cp` prints `linearizable=true` and availability `< 1.0`, verdict PASS.
- [ ] `go run ./cmd/experiments ap` prints `linearizable=false` and availability `= 1.0`, verdict PASS.
- [ ] `go run ./cmd/experiments ca-impossible` prints the proof table and PASS.
- [ ] `RESULTS.md` records the measured availability numbers for each regime and a paragraph naming the tradeoff in the week-README template.
- [ ] Committed and pushed.

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Quorum & partition correctness** | 25 | `hasQuorum` is right for every partition shape; the no-majority case stops *all* CP writes; the partition simulator is symmetric and race-free. |
| **CP/AP mode behavior** | 20 | CP never diverges and refuses the minority; AP always answers and diverges; the seam between them is a clean mode switch, not duplicated logic. |
| **Checker correctness** | 25 | The linearizability checker agrees with the four reference histories and correctly flags a live-recorded AP history as non-linearizable; the availability recorder is right. |
| **The CA-impossible demonstration** | 15 | The harness actually *demonstrates* (via the checker) that available+linearizable is unreachable under partition, rather than asserting it. |
| **Tests & hygiene** | 10 | `go test -race` green; tests cover both modes and the no-majority partition; no `build/`/`bin/` checked in. |
| **Docs & results** | 5 | `RESULTS.md` reports measured numbers and names the tradeoff precisely. |

**90+** is portfolio-grade and ready to grow into Week 2's Raft log. **70–89** works but has a soft checker or an untested partition shape. **Below 70** means the demonstration isn't actually machine-checked — fix that first; the whole point is verdicts, not logs.

## Stretch goals

- **Replace LWW with a version-vector reconcile.** Track a version *vector* (one counter per node) instead of a single Lamport stamp, and on heal *detect concurrent writes* (incomparable vectors) instead of silently overwriting. Report conflicts rather than discarding a write. This is the bridge to Week 3's CRDTs and proves you understand *why* LWW is a footgun.
- **Measure the availability/staleness curve.** Run a sustained workload through a partition of varying duration and plot AP staleness (how far behind the minority's reads were) against partition length. The curve is the EL/EC tradeoff (PACELC) made visible.
- **Three-way partition.** Add the `{0}|{1}|{2}` total split and show that CP mode grinds to a halt (no quorum anywhere) while AP keeps every node available — the most dramatic illustration of the choice.
- **Wire in the Exercise 3 checker as a CI gate.** A GitHub Actions job that runs all three scenarios and fails the build if any verdict regresses. Now your CAP demonstration can't silently break.

## How this connects to the rest of C22

- **Week 2 (consensus)** replaces the synchronous-replicate step with a Raft append + quorum commit; your three-node skeleton and partition simulator are exactly what you'll drive Raft elections with.
- **Week 3 (CRDTs)** replaces the LWW reconcile with a convergent merge; the version-vector stretch goal here is the first half of that lesson.
- **Phase 4 (multi-region)** is this register, grown up: active-active across two regions is the AP scenario with a CRDT reconcile and a real network.

When you've finished, push the repo and take the [quiz](../05-quiz.md).
