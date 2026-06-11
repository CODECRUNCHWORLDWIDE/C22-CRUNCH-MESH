# Week 2 — Time, Order, and Consensus

Last week told you the floor (CAP, FLP) and the tax (PACELC, safety vs liveness). This week you build the machinery that lives inside the escape hatches. The two questions that organize it: **how do you order events without a global clock?** (logical clocks — Lamport and vector clocks) and **how do you reach agreement despite FLP?** (consensus — Raft deeply, Paxos in overview). By Friday you will have implemented vector clocks from scratch, traced a Raft election by hand, and operated a real 3-node etcd cluster through a node failure.

The one sentence to internalize before you read another line: **the wall clock is a lie you cannot use to order events in a distributed system, because clocks on different machines drift, NTP corrections make time jump backward, and there is no instant that two machines agree is "now."** Lamport's 1978 insight — that you can build a *logical* notion of order from message causality alone, with no clock at all — is the foundation everything else stands on. Once you can order events by *happens-before* instead of by timestamp, leader election, replicated logs, and conflict detection all become tractable. Skip this and you will write the bug that every junior distributed-systems engineer writes: trusting `System.currentTimeMillis()` to decide which of two events came first, and watching it silently corrupt data when one machine's clock is 200 ms ahead.

This week is where you stop trusting wall clocks and start reasoning about order.

## Learning objectives

By the end of this week, you will be able to:

- **Explain** why physical clocks (wall-clock time, NTP, even PTP) cannot be trusted to order events across machines, and what clock *drift*, *skew*, and *backward jumps* do to naive timestamp-ordering code.
- **Define** the **happens-before** relation (Lamport's `→`) precisely, and use it to say whether two events are causally ordered or genuinely concurrent.
- **Implement** **Lamport timestamps** and **vector clocks** from scratch, and state exactly what each can and cannot tell you (Lamport: a consistent total order; vector clocks: the ability to *detect concurrency*).
- **Trace** the **Raft** consensus protocol by hand through leader election, log replication, and a leader failure — naming terms, the commit rule, and why the election restriction guarantees safety.
- **Contrast** Raft with **Paxos** (single-decree and Multi-Paxos) at the level of "what each is optimizing for and why Raft is easier to implement correctly."
- **Use** **leases** and **fencing tokens** to make a lock safe against the slow-vs-dead problem from Week 1, and recognize a fencing-token bug in a lock API on sight.
- **Operate** a real Raft-backed coordination service — a 3-node **etcd** cluster on Kind — exercising leader election by killing nodes and observing the cluster heal.

## Prerequisites

This week assumes you completed **Week 1** (CAP/PACELC/FLP, the partitioned register, safety vs liveness) and the course entry bar. Specifically:

- **Python 3.12+** for the logical-clock lab (`python3 --version`). The vector-clock and Lamport-log code is pure-Python, standard library only.
- **Go 1.22+** is helpful (the Raft skeleton you graft onto last week's `regime-register` is in Go), but the core Raft work this week is *tracing and operating*, not a from-scratch implementation.
- **Kind** (Kubernetes in Docker) and **kubectl** installed, plus **Docker/Podman**. The etcd lab runs a 3-node cluster on a local Kind cluster.
- A firm grip on **Week 1's FLP and safety/liveness** material — Raft's election timeout *is* the partial-synchrony escape hatch, and you will not understand why it exists without that grounding.

You do **not** need prior consensus experience. We build from happens-before up to Raft, and operate etcd hands-on. If you can write a Python class and read a Go struct, you have enough.

## Topics covered

- **Physical vs logical clocks.** Why wall-clock time is unsafe for ordering: drift, skew, NTP step adjustments (time going *backward*), the absence of a shared "now." When physical time is still useful (TrueTime-style bounded uncertainty, lease *durations*) and when it is a footgun.
- **The happens-before relation.** Lamport's `→`: same-process order, message send→receive, transitivity. Concurrency as the *absence* of happens-before. Why this is the only honest notion of "order" you have.
- **Lamport timestamps.** The single-counter algorithm (`L(e)`), the update-on-receive rule, the tiebreak by process ID for a total order. What they guarantee (`a → b ⟹ L(a) < L(b)`) and the converse they *cannot* give you (`L(a) < L(b)` does **not** imply `a → b`).
- **Vector clocks.** One counter per process; the increment-and-merge rules; the partial order on vectors. The thing Lamport clocks can't do: **detect concurrency** (`V(a) ∥ V(b)` iff neither dominates). The metadata cost (O(N) per event) and why it matters.
- **Raft, deeply.** Terms, leader/follower/candidate roles, the election timeout (the FLP escape hatch), RequestVote and AppendEntries RPCs, the log-matching property, the commit rule (majority replication), the leader-completeness/election-restriction safety argument, and log compaction via snapshots.
- **Paxos, in overview.** Single-decree Paxos (proposers, acceptors, learners; prepare/promise, accept/accepted; the majority-quorum overlap that makes it safe), why Multi-Paxos exists, and an honest comparison to Raft on understandability and implementability.
- **Leases and fencing tokens.** A lease as a time-bounded lock; why a lease alone is not safe under a GC pause; the **fencing token** (a monotonically increasing number the storage layer checks) that closes the gap. ZooKeeper, etcd, and Consul as Raft consumers that hand you these primitives.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                   | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|---------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Physical vs logical clocks; happens-before; Lamport     |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Vector clocks; concurrency detection                    |    1h    |    2.5h   |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | Raft deeply: election, replication, safety              |    2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | Paxos overview; leases and fencing tokens               |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Friday    | The etcd cluster; leader election by killing nodes      |    0h    |    0h     |     1h     |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work                                  |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, review, writeup polish                            |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                         | **6h**   | **7h**    | **4h**     | **3.5h**  | **5h**   | **12h**      | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | Lamport 1978, the Raft paper and visualization, Paxos Made Simple, and the DDIA chapters |
| [lecture-notes/01-time-clocks-and-logical-order.md](./lecture-notes/01-time-clocks-and-logical-order.md) | Why wall clocks lie, happens-before, Lamport timestamps, and vector clocks |
| [lecture-notes/02-consensus-raft-paxos-leases.md](./lecture-notes/02-consensus-raft-paxos-leases.md) | Raft deeply, Paxos in overview, and leases + fencing tokens |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-trace-a-raft-election.md](./exercises/exercise-01-trace-a-raft-election.md) | Trace a Raft election and a log-replication round by hand, then verify against the visualization |
| [exercises/exercise-02-vector-clocks.py](./exercises/exercise-02-vector-clocks.py) | Implement Lamport and vector clocks; detect concurrency on a recorded message trace |
| [exercises/exercise-03-fencing-tokens.py](./exercises/exercise-03-fencing-tokens.py) | Reproduce the lease-without-fencing bug, then fix it with a fencing token the storage checks |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-operate-an-etcd-cluster.md](./challenges/challenge-01-operate-an-etcd-cluster.md) | Stand up 3-node etcd on Kind, force elections by killing the leader, and document the failover |
| [quiz.md](./quiz.md) | 14 questions with a hidden answer key |
| [homework.md](./homework.md) | Six problems including the fencing-token postmortem |
| [mini-project/README.md](./mini-project/README.md) | Graft a Raft replicated log onto last week's register and pass a small linearizability test |

## The "order without a clock" promise

C22's recurring marker this week is a single claim you must be able to defend by Friday:

```
Given two events a and b on different machines, I can decide their relationship
WITHOUT any wall clock:
  - a → b      (a happens-before b)        if V(a) < V(b)   (vector a dominated by b)
  - b → a      (b happens-before a)        if V(b) < V(a)
  - a ∥ b      (a and b are CONCURRENT)     if neither dominates
And I know that a Lamport timestamp gives me a usable TOTAL order but CANNOT tell
me whether a ∥ b — only a vector clock can.
```

If you cannot state that distinction — Lamport gives total order, vector clocks detect concurrency — you have not finished the week. The whole point is to replace "which timestamp is bigger" with "what does causality actually say."

## Stretch goals

If you finish early:

- Read the **Raft paper §5.4 (safety)** until you can explain the *election restriction* — why a candidate must have an up-to-date log to win — from memory, and why without it a committed entry could be overwritten.
- Implement **matrix clocks** (vector clocks of vector clocks) and explain what extra question they answer (what every process knows that every other process knows) and why their O(N²) cost is rarely worth it.
- Run **`etcdctl` with `--write-out=json`** against your cluster and watch the **Raft term** and **leader** change as you kill nodes. Correlate the term bumps with the elections you triggered.
- Read **Paxos Made Live** (the Google paper on what it took to ship Paxos in Chubby) and list three things the original Paxos paper omits that production forced them to solve.

## Up next

Week 3 takes the conflict-detection skill from vector clocks and turns it into conflict *resolution*: CRDTs, the data structures that converge automatically under concurrent updates, so you never have to hand-pick a winner with last-writer-wins again. The vector clocks you build this week are the metadata CRDTs use. Push your mini-project before you start it.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
