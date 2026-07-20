# Week 2 Homework

Six problems that drive logical clocks and consensus into your fingers. The full set should take about **5 hours**. Work in your Week 2 Git repository (the same workspace as the exercises and the `raft-register` mini-project) so every problem produces at least one commit you can point to at the midterm architecture review.

The headline deliverable is **Problem 4 — the fencing-token postmortem**. Treat it as the artifact a reviewer reads, not a journal entry.

Each problem includes a short **problem statement**, **acceptance criteria**, a **hint**, and an **estimated time**.

---

## Problem 1 — Hand-compute Lamport and vector clocks

**Problem statement.** Given a four-process message trace (write your own, with at least two messages and one *known* concurrent pair), compute by hand the Lamport timestamp and vector clock of every event. Record them in `notes/week-02/clocks-by-hand.md`. Then run the same trace through Exercise 2's code and confirm your hand-computed values match.

**Acceptance criteria.**
- `notes/week-02/clocks-by-hand.md` shows every event's Lamport and vector value, computed by hand.
- At least one pair is identified as concurrent, justified by incomparable vectors.
- The Exercise 2 code reproduces your values (or you found and explain your hand-error).
- Committed.

**Hint.** The `max + 1` rule on receive is where hand-computations go wrong: the receiver takes the element-wise max with the message's vector, *then* bumps its own slot. Do the merge before the bump.

**Estimated time.** 40 minutes.

---

## Problem 2 — Prove a Lamport timestamp can't detect concurrency

**Problem statement.** Construct a concrete pair of events `a` and `b` that are genuinely **concurrent** (`a ∥ b`) but have `L(a) < L(b)` under Lamport timestamps. Show that an engineer who concluded "`a` happened before `b`" from the Lamport order would be *wrong*. Then show the vector clock correctly flags them concurrent. Write it up in `notes/week-02/lamport-limit.md`.

**Acceptance criteria.**
- A concrete trace with two concurrent events where the Lamport order is misleading.
- The vector clock for both, demonstrated incomparable.
- One sentence on the real-world consequence (e.g., a last-writer-wins reconcile silently discarding a concurrent write).
- Committed.

**Hint.** Two first-events on different processes both get `L = 1`, but any *later* concurrent pair works too — e.g., a local event on P1 after it has advanced its clock, concurrent with a local event on P2. The point is `L(a) < L(b)` with no causal path between them.

**Estimated time.** 40 minutes.

---

## Problem 3 — Trace the Raft commit rule (Figure 8)

**Problem statement.** Reproduce the Raft paper's Figure 8 scenario on paper in `notes/week-02/raft-figure-8.md`: a previous-term entry that is replicated on a majority but is **not yet committed**, and gets **overwritten** by a new leader — demonstrating *why* the commit rule requires a current-term entry. Explain, step by step, what would go wrong if Raft committed the previous-term entry just because it was on a majority.

**Acceptance criteria.**
- A step-by-step trace (terms, logs per node) showing a majority-replicated previous-term entry getting overwritten.
- An explanation of the safety violation that would occur without the current-term rule.
- You correctly state the full commit rule: majority **and** a current-term entry on top.
- Committed.

**Hint.** This is the single hardest subtlety in Raft. Use the Raft paper §5.4.2 and the visualization. The key insight: a majority-replicated entry from an *old* term is not safe to commit because a future leader (with a different log) could still legally win and overwrite it — until a *current-term* entry is committed above it, anchoring it.

**Estimated time.** 1 hour.

---

## Problem 4 — The fencing-token postmortem (headline deliverable)

**Problem statement.** Take Exercise 3 (or engineer a fresh scenario) and write a one-page postmortem at `notes/week-02/fencing-postmortem.md` for the lease-without-fencing data-corruption bug, against this template:

1. **Summary** — one sentence: what corrupted and the user-visible symptom (e.g., "two workers processed the same job; a payment was charged twice").
2. **Timeline** — t=0 acquire, the GC pause, the lease expiry + reassignment, the new holder's write, the stale holder's write, in order.
3. **Root cause** — the slow-vs-dead problem: the lock service correctly reassigned the expired lease, but the paused client could not tell it had been fenced out. State that a lease alone cannot solve this.
4. **Why it was the storage's job** — explain why the fix must be enforced at storage (the monotonic fencing token), not at the client, since the client's belief is exactly what's unreliable.
5. **Fix** — the fencing-token mechanism, with the before/after (unsafe storage accepts; fenced storage rejects token < highest).
6. **Prevention** — one concrete process change (e.g., "every lock acquisition returns a fencing token; every write to shared storage carries it; storage rejects stale tokens; this is a code-review checklist item").

**Acceptance criteria.**
- `notes/week-02/fencing-postmortem.md` exists, fits roughly one page (350–550 words), and hits all six headings.
- The root cause is stated as the **slow-vs-dead** problem, tied to Week 1's FLP.
- The fix is the **monotonic token checked at storage**, not a client-side change.
- The prevention is concrete and actionable.
- Committed.

**Hint.** The strongest version connects this back to Week 1's safety/liveness: the corruption is a *safety* violation (two holders wrote), and the lease-only design traded safety for the *liveness* of "always make progress." Fencing restores safety without sacrificing liveness.

**Estimated time.** 1 hour.

---

## Problem 5 — Operate etcd and capture an election

**Problem statement.** Using the Challenge's etcd cluster (or a fresh one), capture the Raft **term incrementing** during a leader kill. In `notes/week-02/etcd-election.md`, paste the `etcdctl endpoint status --write-out=table` output *before* and *after* killing the leader, highlighting the leader change and the new term. Then explain in two sentences why the term is a logical clock.

**Acceptance criteria.**
- Before/after `endpoint status` tables with a different leader and a higher term.
- A two-sentence explanation that the term is a cluster-wide Lamport-style logical clock for leadership epochs.
- Confirmation the cluster stayed available (a successful write after failover, with 2 of 3 nodes).
- Committed.

**Hint.** If you can't run etcd, the Raft visualization (raft.github.io) shows the term incrementing on each election — capture that instead and say so. The concept is the deliverable, not the specific tool.

**Estimated time.** 45 minutes.

---

## Problem 6 — Spot the fencing bug in a lock API

**Problem statement.** Find a real distributed-locking library or pattern (Redlock/Redis, a ZooKeeper recipe, a homegrown DB-based lock at your company) and evaluate it for the fencing-token property in `notes/week-02/lock-api-audit.md`. Answer: does acquiring the lock return a monotonic token? Does the documentation tell you to carry it through to storage? If not, construct the GC-pause scenario that would corrupt data, and state the precise fix.

**Acceptance criteria.**
- `notes/week-02/lock-api-audit.md` names a real lock library/pattern and cites its docs.
- A clear yes/no on whether it provides a fencing token usable against storage.
- If no, the specific GC-pause corruption scenario and the fix.
- Committed.

**Hint.** Kleppmann's "How to do distributed locking" essay critiques Redlock on exactly this point — read it and apply the same lens to whatever lock you pick. The tell is whether the lock hands you a *number* you're meant to check at the storage layer; most simple locks don't, which makes them unsafe under pauses.

**Estimated time.** 35 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 — Hand-compute clocks | 40 min |
| 2 — Lamport can't detect concurrency | 40 min |
| 3 — Raft commit rule (Figure 8) | 1 h 0 min |
| 4 — Fencing-token postmortem (headline) | 1 h 0 min |
| 5 — Operate etcd, capture an election | 45 min |
| 6 — Audit a lock API for fencing | 35 min |
| **Total** | **~5 h 0 min** |

When you've finished all six, push your repo and make sure the `raft-register` [mini-project](./mini-project/README.md) is in the same workspace — Week 3 pairs its CP path against the AP path of CRDTs. Then take the [quiz](./quiz.md) with your notes closed.
