# Week 2 — Quiz

Fourteen questions. Take it with your lecture notes closed. Aim for 11/14 before moving to Week 3. Answer key is at the bottom — don't peek.

---

**Q1.** Why can't you use wall-clock timestamps to order events across two machines?

- A) Wall clocks are always perfectly synchronized, so it's redundant.
- B) Clocks drift, NTP can step them backward, and skew between machines can exceed the interval you're trying to resolve — so a bigger timestamp doesn't reliably mean "later."
- C) Wall clocks are too slow to read.
- D) You can, as long as both machines run NTP.

---

**Q2.** Define the happens-before relation `a → b`. Which is NOT one of its rules?

- A) If a and b are in the same process and a is first, then a → b.
- B) If a is the send of a message and b is its receipt, then a → b.
- C) If a → b and b → c, then a → c.
- D) If a and b have the same wall-clock timestamp, then a → b.

---

**Q3.** A Lamport timestamp guarantees `a → b ⟹ L(a) < L(b)`. What does it NOT guarantee?

- A) That the converse holds: `L(a) < L(b)` does **not** imply `a → b` — a smaller timestamp might just be a concurrent event.
- B) That timestamps increase within a process.
- C) That a receive's timestamp exceeds the matching send's.
- D) Nothing — it guarantees a full bidirectional ordering.

---

**Q4.** Two events have vector clocks `[2,0,1]` and `[1,1,1]`. What is their relationship?

- A) The first happens-before the second.
- B) The second happens-before the first.
- C) Concurrent — the vectors are incomparable (2>1 in slot 0, but 0<1 in slot 1).
- D) Equal.

---

**Q5.** What can vector clocks do that Lamport timestamps cannot?

- A) Use less metadata.
- B) Detect concurrency — incomparable vectors reveal that two events are causally unrelated, which a single Lamport counter collapses away.
- C) Provide a total order.
- D) Work without per-process state.

---

**Q6.** In Raft, what is a "term"?

- A) A fixed-length time window measured in seconds.
- B) A monotonically increasing integer (a cluster-wide logical clock) that increments each election, with at most one leader per term.
- C) The number of log entries.
- D) The election timeout duration.

---

**Q7.** A Raft follower's election timeout fires. What does it do?

- A) Immediately becomes leader.
- B) Increments its term, becomes a candidate, votes for itself, and sends RequestVote RPCs to gather a majority.
- C) Shuts down.
- D) Waits for the old leader to return.

---

**Q8.** Why does Raft use a *randomized* election timeout?

- A) To make the code harder to test.
- B) To reduce the chance that two followers campaign simultaneously and split the vote — so elections resolve quickly under partial synchrony (the practical defeat of FLP's split-vote stall).
- C) Because deterministic timeouts are illegal.
- D) To save battery.

---

**Q9.** In Raft, an entry is committed when it is replicated on a majority AND:

- A) the client acknowledges it.
- B) all followers have it.
- C) the leader has also replicated at least one entry from its **current term** (the Figure-8 safety rule).
- D) the term increments.

---

**Q10.** The Raft election restriction (a candidate needs an up-to-date log to win) guarantees what?

- A) That elections are fast.
- B) Leader Completeness: every leader contains all committed entries, so forcing followers to match the leader never deletes a committed entry — proven by quorum overlap.
- C) That the leader has the smallest log.
- D) That no elections ever happen.

---

**Q11.** Compared to Paxos, Raft is generally considered:

- A) More powerful — it solves problems Paxos cannot.
- B) Equivalent in power but easier to implement correctly, because it makes the leader and the log first-class.
- C) Strictly weaker and unsafe.
- D) Identical in every respect including the paper.

---

**Q12.** A client acquires a 10-second lease, suffers a 12-second GC pause, and wakes up to write — but a new holder already acquired the lease and wrote. Without fencing, what happens?

- A) Nothing; the lease service prevents it.
- B) The paused client's write corrupts the new holder's data — two clients wrote believing they held the lock. This is the slow-vs-dead problem.
- C) The paused client's process is automatically killed.
- D) The write is queued until the new holder finishes.

---

**Q13.** How does a fencing token fix the lease-pause bug?

- A) It makes the lease longer.
- B) The lock service issues a monotonically increasing token with each grant; the **storage** layer rejects any write carrying a token lower than the highest it has seen — fencing off the stale holder.
- C) It speeds up garbage collection.
- D) It synchronizes the clients' clocks.

---

**Q14.** You run a 5-node etcd cluster and kill 3 nodes. What happens to writes, and why?

- A) Writes continue — etcd is AP.
- B) Writes fail/stall — with only 2 of 5 nodes there is no majority (need 3), so etcd cannot commit; it sacrifices availability to preserve consistency (the CP choice).
- C) The cluster automatically promotes the 2 survivors to a full cluster.
- D) Reads fail but writes succeed.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — Drift, NTP backward steps, and skew larger than the interval make wall-clock ordering unsafe across machines. (Lecture 1 §1.)
2. **D** — Same wall-clock timestamp says nothing about causality; that's the whole reason logical clocks exist. The other three are exactly Lamport's rules. (Lecture 1 §2.)
3. **A** — The converse fails: `L(a) < L(b)` does not imply `a → b`; it might be concurrent. This is Lamport's fatal blind spot. (Lecture 1 §3.2.)
4. **C** — `[2,0,1]` and `[1,1,1]` are incomparable (2>1 in slot 0, 0<1 in slot 1) → concurrent. (Lecture 1 §4.2.)
5. **B** — Detect concurrency via incomparable vectors. The cost is O(N) metadata per event. (Lecture 1 §4.)
6. **B** — A term is a cluster-wide logical clock, one leader per term, incremented each election. (Lecture 2 §1.1.)
7. **B** — Increment term, become candidate, self-vote, send RequestVote for a majority. (Lecture 2 §1.2.)
8. **B** — Randomization breaks split votes so elections resolve fast under partial synchrony — the practical answer to FLP's stall. (Lecture 2 §1.2.)
9. **C** — Majority replication **plus** a current-term entry on top (the Figure-8 rule). Skipping this is the classic home-grown-Raft data-loss bug. (Lecture 2 §1.4.)
10. **B** — Leader Completeness via quorum overlap: a winner's log is at least as up-to-date as a majority, and a committed entry is on a majority, so the winner has it. (Lecture 2 §1.5.)
11. **B** — Equivalent power, easier to implement correctly; leader and log are first-class in Raft. (Lecture 2 §2.2.)
12. **B** — The paused client wakes stale and corrupts the new holder's data — the slow-vs-dead problem from Week 1. The lease service did nothing wrong. (Lecture 2 §3.2.)
13. **B** — A monotonic fencing token checked at **storage** rejects the stale holder's write. The fix lives in storage, not the client. (Lecture 2 §3.3.)
14. **B** — 2 of 5 is not a majority (need 3); no commit possible; etcd refuses writes — the CP choice. (Lecture 2 §Part 3b; Week 1 CAP.)

</details>

---

If you scored under 10, re-read the lecture sections cited in the answers you missed. If you scored 12 or higher, you're ready for the [homework](./06-homework.md).
