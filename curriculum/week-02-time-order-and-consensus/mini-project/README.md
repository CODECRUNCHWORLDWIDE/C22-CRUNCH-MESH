# Mini-Project — Graft Raft onto the Register: A Replicated Log That Stays Linearizable

> Take last week's `regime-register` (the 3-node CP/AP register) and replace its hand-rolled "synchronously replicate to peers" step with a real **Raft replicated log**: a leader, an election timeout, `AppendEntries`/`RequestVote` RPCs, majority commit, and the election restriction. Then prove your register is **linearizable** by feeding a recorded history through last week's linearizability checker — and prove it survives a leader failure without losing a committed write.

This is the project where last week's impossibility theory becomes this week's working consensus. You built a register that *chose* CP or AP by hand; now you make the CP path *real* by putting Raft underneath it. The result is a small, tested, in-memory Raft you actually understand, line by line — the single best thing you can have read and written before you operate etcd, Consul, or CockroachDB in anger.

**Estimated time:** ~12 hours, split across Thursday, Friday, and Saturday in the suggested schedule.

**Compounds forward:** This Raft is the seed of every coordination decision later in the course. The capstone's `inventory-service` (single-writer-per-SKU with leases) and Phase 4's multi-region state both lean on exactly this primitive. More immediately, having *implemented* `AppendEntries` makes Friday's etcd operation legible — you'll recognize every term bump and commit you watch.

---

## What you will build

A Go module `raft-register` with three deliverables:

1. **`raft/` package** — a simulated in-memory Raft: 3 nodes, terms, roles (follower/candidate/leader), randomized election timeout, `RequestVote` and `AppendEntries` RPCs over an in-process network with a controllable partition, majority commit with the current-term rule, and the election restriction.
2. **`register/` package** — last week's register, rewritten so a write is a Raft *log append* that returns only after the entry is *committed* (replicated on a majority), and a linearizable read goes through the leader.
3. **A test + experiment harness** — `go test` proving safety (no committed entry is ever lost across an election), plus a `cmd/demo` that drives an election, replicates writes, kills the leader, and re-checks linearizability with last week's checker.

By the end you have ~400–550 lines of tested Go that implement the core of Raft (election + replication + safety; *not* full membership changes or snapshots — those are stretch goals), and a `RESULTS.md` showing a recorded history that the checker confirms is linearizable even across a leader failure.

---

## Why graft, not rewrite

You already have a 3-node register with a partition simulator and a linearizability checker. Reuse them. The *only* thing that changes is the replication mechanism: last week you did "leader writes to a variable and copies it to peers"; this week the write must be *agreed* by a majority via Raft before it counts. Keeping the register and checker means the project is about *consensus*, not plumbing — and it makes the before/after crisp: same register, same checker, but now the CP path is backed by a real protocol with a real safety proof.

---

## Package layout

```
raft-register/
├── go.mod
├── README.md                  # how to run + your RESULTS summary
├── raft/
│   ├── raft.go                # Node: state, terms, roles, election, RPCs, commit
│   ├── network.go             # in-process RPC bus with a controllable partition
│   └── raft_test.go           # election, replication, and SAFETY tests
├── register/
│   ├── register.go            # Write = committed Raft append; linearizable Read via leader
│   └── register_test.go       # register semantics over Raft
├── checker/
│   └── linearizable.go        # reused from Week 1 (copy it in)
├── cmd/demo/
│   └── main.go                # election -> writes -> kill leader -> re-check linearizability
└── RESULTS.md                 # the recorded history + checker verdict
```

---

## Deliverable 1 — `raft/` (the core)

Implement a `Node` with the standard Raft state. The minimum it must do:

- **Persistent-ish state**: `currentTerm`, `votedFor`, `log []Entry` (each entry has `Term`, `Index`, `Command`). In-memory is fine for the lab, but model it as "would be persisted before responding" — note the persist points in comments.
- **Roles & election**: a randomized election timeout; on timeout, increment term, become candidate, vote for self, send `RequestVote`. Win on a majority; on receiving a higher term, step down to follower.
- **The two RPCs**: `RequestVote` (with the up-to-date-log election restriction) and `AppendEntries` (with the `prevLogIndex`/`prevLogTerm` consistency check, conflict truncation, and `leaderCommit` propagation).
- **Commit rule**: advance the commit index when an entry is on a majority **and** it's from the current term (the Figure-8-safe rule).

A sketch of the election-restriction check (fill in the rest):

```go
// atLeastAsUpToDate reports whether a candidate's log (lastTerm, lastIndex) is at
// least as up-to-date as ours -- the election restriction (Raft paper 5.4.1).
// A voter grants its vote only if this holds, which guarantees a winning candidate
// has every COMMITTED entry (because committed = on a majority, and any winning
// majority overlaps that majority in at least one voter).
func (n *Node) atLeastAsUpToDate(lastTerm, lastIndex int) bool {
    myLastTerm := n.lastLogTerm()
    myLastIndex := n.lastLogIndex()
    if lastTerm != myLastTerm {
        return lastTerm > myLastTerm     // higher last-term wins
    }
    return lastIndex >= myLastIndex      // same term -> longer (or equal) log wins
}
```

And the commit-advance core:

```go
// advanceCommit moves commitIndex forward to the highest N such that:
//   (a) N > commitIndex,
//   (b) a MAJORITY of matchIndex[i] >= N, and
//   (c) log[N].Term == currentTerm   <-- the current-term rule (Figure 8 safety)
// Skipping (c) is the single most common way a home-grown Raft loses data.
func (n *Node) advanceCommit() {
    for N := n.lastLogIndex(); N > n.commitIndex; N-- {
        if n.log[N].Term != n.currentTerm {
            continue // never commit a previous-term entry directly
        }
        count := 1 // self
        for i := range n.peers {
            if n.matchIndex[i] >= N {
                count++
            }
        }
        if count*2 > len(n.peers)+1 { // strict majority
            n.commitIndex = N
            return
        }
    }
}
```

---

## Deliverable 2 — `register/` (the register over Raft)

Rewrite the register so:

- **`Write(key, value)`** appends a command to the Raft log via the leader and blocks until that entry is **committed** (replicated on a majority). If the node isn't the leader, it redirects (or, for the lab, returns "not leader"). A write that cannot reach a majority (minority partition) *fails* — the CP choice, now enforced by Raft rather than by hand.
- **`Read(key)`** (linearizable) is served by the leader, which confirms it is still leader (a heartbeat round or a `ReadIndex`-style check) before answering — otherwise a stale leader could return a stale value. (A simpler lab version: read from the leader's committed state; document the staleness window you're accepting.)

The register now inherits Raft's safety: a committed write is never lost, even across an election, because the election restriction guarantees the new leader has it.

---

## Deliverable 3 — the test + demo harness

- **`raft_test.go`** must include a **safety test**: write and commit an entry, then force a leader change (kill the leader, let a new one win), and assert the committed entry is **still present and committed** on the new leader. This is the election-restriction guarantee, tested.
- **`cmd/demo`** runs: elect a leader → write three values (each committed on a majority) → kill the leader → watch a new election → write a fourth value → record the full history → run last week's **linearizability checker** on it → print the verdict.

The headline result: a recorded history of writes spanning a leader failure that the checker confirms is **linearizable**. That is the proof that grafting Raft onto the register gave you a real CP system, not a hopeful one.

---

## Rules

- **You may** read the Raft paper, the lecture notes, and the etcd/hashicorp raft source for reference.
- **You must not** import a third-party Raft library — the whole point is to implement the core yourself. Standard library only (`sync`, `time`, `math/rand`, `testing`).
- Go 1.22+. `go vet ./...` clean; `go test -race ./...` green (the in-process network touches shared state — prove it's safe).
- The safety test must **force a leader change and assert no committed entry is lost** — that's the load-bearing test.

## Acceptance criteria

- [ ] A public GitHub repo named `c22-week-02-raft-register-<yourhandle>`.
- [ ] `go build ./...` and `go vet ./...` succeed with no warnings.
- [ ] `go test -race ./...` passes, including:
  - an **election test** (a leader emerges from a majority vote; the term increments),
  - a **replication test** (a write is committed only after majority replication),
  - a **safety test** (a committed entry survives a forced leader change),
  - a **minority test** (a write on a minority-partitioned node fails — the CP choice).
- [ ] `go run ./cmd/demo` elects a leader, commits writes, kills the leader, re-elects, and the linearizability checker reports the recorded history **LINEARIZABLE**.
- [ ] `RESULTS.md` includes the recorded history and the checker verdict, plus a paragraph mapping what you built to the Week 2 lecture (term = logical clock; majority = quorum; election restriction = safety).
- [ ] Committed and pushed.

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Election correctness** | 20 | Randomized timeout; majority vote; higher-term step-down; no two leaders in one term. |
| **Replication & log matching** | 20 | `prevLogIndex`/`prevLogTerm` check; conflict truncation; followers' logs forced to match the leader. |
| **Commit rule** | 20 | Majority + current-term rule implemented correctly (the Figure-8-safe version); no previous-term direct commit. |
| **Safety test** | 20 | A committed entry provably survives a forced leader change; the test actually forces the change. |
| **Linearizability proof** | 10 | The checker confirms a real recorded history (spanning a failure) is linearizable. |
| **Tests & hygiene** | 10 | `go test -race` green; minority-write test present; no `build/` checked in. |

**90+** is portfolio-grade and a genuine "I implemented Raft" artifact. **70–89** works but has a soft commit rule or a safety test that doesn't really force a leader change. **Below 70** usually means the commit rule skipped the current-term clause — fix that first; it's the difference between safe and silently-lossy.

## Common pitfalls (read before you start)

These are the mistakes that sink home-grown Raft implementations. Forewarned:

- **Committing previous-term entries directly.** The single most common safety bug. An entry from an *old* term, even on a majority, is *not* committed until a *current-term* entry is committed above it (§1.4 / Figure 8). If your `advanceCommit` doesn't check `log[N].Term == currentTerm`, it is silently lossy. Test this explicitly.
- **Forgetting to persist `votedFor` and `currentTerm`.** A node that restarts and forgets it already voted can vote twice in one term, electing two leaders. Even in-memory, model the persist points and reason about a restart.
- **Resetting the election timer at the wrong moments.** A follower must reset its timer on a *valid* `AppendEntries` from the *current* leader and on *granting* a vote — but not on every message. Getting this wrong causes either election storms or a dead cluster that never re-elects.
- **Off-by-one in log indices.** Raft logs are conventionally 1-indexed in the paper; pick a convention and be ruthless about it. Most replication bugs are an index off by one in the `prevLogIndex` check.
- **Aliasing shared state in the in-process network.** If you merge a *live* peer instead of a *snapshot*, the race detector will (rightly) scream. Always pass copies across the simulated network.

Print this list; check each one off when your tests cover it. The grading rubric weights the commit rule and the safety test heavily precisely because these are where real Raft breaks.

## A suggested build order

Don't write all of Raft at once. Build it in testable layers:

1. **Leader election only.** Three nodes, randomized timeouts, `RequestVote`, majority. Test: a leader emerges; the term increments; killing the leader triggers a new election. No log yet.
2. **Log replication on a stable leader.** Add `AppendEntries`, the `prevLogIndex`/`prevLogTerm` check, and conflict truncation. Test: a write replicates to a majority and commits.
3. **The commit rule.** Add the current-term clause to `advanceCommit`. Test: the Figure-8 scenario doesn't lose data.
4. **The election restriction.** Add the up-to-date-log check to `RequestVote`. Test: a stale candidate cannot win, and a committed entry survives a forced leader change (the safety test).
5. **The register + linearizability.** Wire the register's `Write` to a committed append, record a history across a failure, and run the checker.

Each layer is independently testable, which is the only sane way to build something with this many invariants. A big-bang implementation will have a bug you can't localize.

## Stretch goals

- **Snapshots / log compaction.** Add `InstallSnapshot` so a far-behind follower can catch up without replaying the whole log. This is what real etcd does to keep the log bounded.
- **Single-server membership change.** Add nodes one at a time safely (the simplest safe membership-change scheme). This is where real Raft bugs hide; doing it correctly is a strong signal.
- **Lease-based linearizable reads.** Implement a leader lease so the leader can serve linearizable reads without a round trip per read (the etcd optimization). Document the clock assumption it makes and why a lease read is unsafe if the clock can't be trusted.
- **Jepsen-style fault injection.** Drive random partitions and leader kills under a sustained write load and run the linearizability checker on the result. If it ever reports non-linearizable, you found a real bug — fix it.

## How this connects to the rest of C22

- **Week 3 (CRDTs)** is the AP counterpart: where this week's Raft *coordinates* to stay linearizable, CRDTs *avoid* coordination and converge. Having built both the CP (Raft) and AP (CRDT) paths, you can choose per data flow (Week 1's PACELC).
- **Phase 2 (eventing)** uses Kafka, whose per-partition replication is a Raft-adjacent (or, in Redpanda, literally Raft) protocol — you'll recognize the ISR/quorum logic.
- **Phase 4 (multi-region)** runs consensus across regions; this in-memory Raft is the mental model you bring to that, scaled up to a real network.

A final word: implementing Raft correctly is a rite of passage for distributed-systems engineers. It is humbling — the invariants are subtle and the failure modes are quiet — and it is exactly that humbling experience that makes you respect (and operate well) the production consensus systems you'll never write from scratch again. Take your time, build it in layers, and let the tests teach you where your mental model was wrong.

When you've finished, push the repo and take the [quiz](../quiz.md).
