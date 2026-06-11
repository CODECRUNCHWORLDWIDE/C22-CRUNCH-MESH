# Week 3 — CRDTs, Eventual Consistency, and Conflict Resolution

Week 1 told you that under partition you must choose CP or AP, and that the AP choice leaves you with divergent replicas to reconcile. Week 2 gave you the CP machinery (Raft) and the tool to *detect* concurrency (vector clocks). This week closes the loop on the AP side: **CRDTs** — Conflict-free Replicated Data Types — the data structures that converge *automatically* under concurrent updates, so you never have to hand-pick a winner with last-writer-wins and silently lose data again.

By Friday you will have implemented the core CRDTs from scratch — G-counter, PN-counter, OR-set, LWW-register — proven their convergence property, measured their metadata cost, and built an OR-set shopping cart that survives a 3-way partition heal with *both* concurrent additions preserved. You will be able to look at a piece of mutable distributed state and say, with precision, whether a CRDT is the right answer, which CRDT, and what the metadata will cost you.

The one sentence to internalize before you read another line: **a CRDT is a data type whose merge operation is commutative, associative, and idempotent — which is exactly the algebraic condition that guarantees all replicas converge to the same value regardless of the order or duplication of updates, with no coordination and no consensus.** That algebra (a *join-semilattice*) is the whole trick. Last-writer-wins is a footgun because it discards concurrent writes; a CRDT *merges* them, and the merge is mathematically guaranteed to converge. Once you can spot the semilattice structure, you can design state that is safe under partition by construction — the holy grail of the AP corner.

This week is where eventual consistency stops being "hope the replicas agree" and becomes "the replicas *provably* agree."

## Learning objectives

By the end of this week, you will be able to:

- **Explain** what "eventually" should mean rigorously — *strong eventual consistency* (SEC): replicas that have received the same updates have the same state, with no conflict resolution needed.
- **Distinguish** **state-based (CvRDT)** from **operation-based (CmRDT)** CRDTs — the merge-the-whole-state model vs the broadcast-each-operation model — and state the delivery guarantees each requires.
- **Prove** that a CRDT converges by showing its merge forms a **join-semilattice**: commutative, associative, idempotent, with a partial order and a least upper bound.
- **Implement** the canonical CRDTs from scratch — **G-counter**, **PN-counter**, **OR-set**, **LWW-register** — and explain the design choice each one encodes (especially OR-set's add-wins tag mechanism).
- **Measure** and reason about **metadata growth**: why a naive OR-set's tombstones grow without bound, and how delta-CRDTs and tombstone reclamation bound it.
- **Decide** when a CRDT is the right answer and when it is not — and recognize specifically when **LWW is a footgun** (silent data loss on concurrent writes) versus a legitimate choice.
- **Build** an OR-set CRDT shopping cart that survives a simulated 3-way partition heal with all concurrent additions preserved, and measure its convergence and metadata cost.

## Prerequisites

This week assumes you completed **Weeks 1–2** (CAP/PACELC/FLP; logical clocks and consensus) and the course entry bar. Specifically:

- **Python 3.12+** for the CRDT lab (`python3 --version`). The G-counter, PN-counter, OR-set, and LWW-register are pure-Python, standard library only.
- **Go 1.22+** for one exercise (the CRDT property test) — helpful but the core CRDT work is in Python.
- A firm grip on **Week 2's vector clocks** — CRDTs carry vector-clock-style metadata (version vectors, dots) to detect concurrency, and you will not understand OR-set tags without it.
- The **AP scenario from Week 1** (replicas diverge under partition and must reconcile) — CRDTs are the *principled* reconcile that LWW only approximates.

You do **not** need prior CRDT or abstract-algebra experience. We build the semilattice property from first principles and implement each CRDT step by step. If you can write a Python class and reason about set union, you have enough.

## Topics covered

- **What "eventually" should mean.** Eventual consistency vs **strong eventual consistency (SEC)**: the guarantee that replicas with the same update set are *byte-for-byte identical*, with convergence *by construction* rather than by conflict resolution. The Shapiro et al. definition.
- **State-based vs operation-based CRDTs.** CvRDT (each replica holds a state; replicas periodically merge whole states via a join) vs CmRDT (each replica broadcasts operations; operations commute). The delivery guarantees each needs (CvRDT: eventual gossip; CmRDT: reliable causal broadcast). When to pick which.
- **The convergence proof.** A state-based CRDT converges iff its states form a **join-semilattice** under merge: merge is **commutative**, **associative**, and **idempotent**, the states have a partial order, and merge is the **least upper bound**. Why those three algebraic laws are exactly "order and duplication of updates don't matter."
- **The canonical CRDTs.** **G-counter** (grow-only, per-replica counters, merge = element-wise max). **PN-counter** (two G-counters, increments and decrements). **G-set / 2P-set** (grow-only and two-phase sets). **OR-set** (observed-remove set: unique tags per add, add-wins, the standard production set CRDT). **LWW-register** (last-writer-wins by timestamp — and why it's a footgun). **MV-register** (multi-value, keeps concurrent writes as siblings).
- **Metadata growth.** Why tombstones and tags accumulate; the OR-set's metadata cost; **delta-state CRDTs** (ship only the change, not the whole state); causal stability and tombstone reclamation; dotted version vectors.
- **CRDTs in production.** Riak data types (the Bet365 case study), Redis CRDTs (Active-Active / CRDB), AntidoteDB, Automerge/Yjs for collaborative editing. What each chose and why.
- **When CRDTs are right — and when they're not.** CRDTs shine for commutative, AP-friendly state (counters, sets, collaborative text). They are the *wrong* answer when you need a global invariant (uniqueness, non-negative balance, "exactly N seats") that no local merge can enforce — that needs coordination (Week 2's consensus). Naming this boundary is the senior skill.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                       | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|-------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Eventual vs strong eventual consistency; the semilattice    |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | State vs op-based; G-counter, PN-counter, the convergence proof |  1h   |    2.5h   |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | OR-set, LWW-register, MV-register; the add-wins mechanism   |    2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | Metadata growth; delta-CRDTs; CRDTs in production           |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Friday    | The OR-set cart; 3-way partition heal; measuring metadata   |    0h    |    0h     |     1h     |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work                                      |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, review, writeup polish                                |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                             | **6h**   | **7h**    | **4h**     | **3.5h**  | **5h**   | **12h**      | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | Shapiro et al. on CRDTs, the Bayou paper, Riak/Redis/Antidote docs, and the talks worth your time |
| [lecture-notes/01-eventual-consistency-and-the-semilattice.md](./lecture-notes/01-eventual-consistency-and-the-semilattice.md) | SEC, state vs op-based, and the semilattice convergence proof |
| [lecture-notes/02-the-crdt-zoo-metadata-and-production.md](./lecture-notes/02-the-crdt-zoo-metadata-and-production.md) | G-counter, PN-counter, OR-set, LWW/MV-register, metadata growth, and CRDTs in production |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-classify-crdts.md](./exercises/exercise-01-classify-crdts.md) | For each of six data-modeling problems, pick the right CRDT (or say "this needs consensus") and justify it |
| [exercises/exercise-02-crdt-zoo.py](./exercises/exercise-02-crdt-zoo.py) | Implement G-counter, PN-counter, OR-set, and LWW-register; prove convergence after a reordered, duplicated merge |
| [exercises/exercise-03-semilattice-properties.go](./exercises/exercise-03-semilattice-properties.go) | Property-test that a CRDT merge is commutative, associative, and idempotent |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-lww-data-loss.md](./challenges/challenge-01-lww-data-loss.md) | Demonstrate LWW silently losing a concurrent write, then fix it with the right CRDT and prove no loss |
| [quiz.md](./quiz.md) | 14 questions with a hidden answer key |
| [homework.md](./homework.md) | Six problems including the "is a CRDT the right answer?" decision memo |
| [mini-project/README.md](./mini-project/README.md) | The OR-set shopping cart that survives a 3-way partition heal, with metadata measurement |

## The "it converged" promise

C22's recurring marker this week is a single claim you must be able to demonstrate by Friday:

```
Three replicas each took DIFFERENT concurrent updates during a partition.
After the partition heals and they all merge (in ANY order, with DUPLICATES):
  replica_A.value() == replica_B.value() == replica_C.value()
and that converged value PRESERVES every concurrent update (no last-writer-wins
data loss). The convergence holds because merge is commutative + associative +
idempotent — a join-semilattice — so order and duplication of merges don't matter.
```

If you cannot exhibit three replicas converging to an identical value that *kept all* the concurrent updates, you have not finished the week. The point is to replace "I picked a winner and lost data" with "I merged and lost nothing."

## Stretch goals

If you finish early:

- Read the **Shapiro et al. tech report** ("A comprehensive study of Convergent and Commutative Replicated Data Types") and reproduce the OR-set's correctness argument — why a concurrent add and remove resolves *add-wins* via unique tags.
- Implement a **delta-state G-counter** that ships only the changed component, and measure the bandwidth saving versus shipping the whole state on every merge.
- Implement a tiny **collaborative text CRDT** (a sequence CRDT like RGA or a simplified Logoot) and watch two replicas converge on the same string after concurrent inserts — the technology behind Google Docs-style editors, Automerge, and Yjs.
- Take your OR-set and add **tombstone reclamation** using a version vector to detect causal stability, then measure how much metadata you reclaim.

## Up next

This is the last week of Phase 1's theory block. Week 4 turns to microservice fundamentals — bounded contexts, Conway's law, decomposition — and you start *building* services with the conceptual scaffolding these three weeks gave you. Your CRDT cart returns in Phase 4 (Week 20), promoted to active-active across two regions. Push your mini-project before you start Week 4.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
