# Week 1 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 2. Answer key is at the bottom — don't peek.

---

**Q1.** In the CAP theorem as proved by Gilbert and Lynch, what does "consistency" mean?

- A) The data passes its integrity constraints (ACID's "C").
- B) Linearizability — the system behaves as if there is one copy of the data and every read sees the most recent completed write in real time.
- C) Eventual convergence of all replicas.
- D) Every transaction is serializable.

---

**Q2.** Why is "CA" not a coherent category for a distributed system that spans a network?

- A) Because consistency and availability are the same property.
- B) Because partition tolerance is not an option you choose — networks partition regardless — so "CA" describes a single node, not a networked system.
- C) Because CA systems are simply too slow to be useful.
- D) Because the CAP theorem only has two real categories by definition.

---

**Q3.** A service writes to the Postgres primary, gets an OK, then reads the same row from an asynchronous read replica and gets the *old* value. What consistency model did the replica read actually provide, and what guarantee did the user expect?

- A) Linearizable; the user expected eventual.
- B) Eventual; the user expected read-your-writes (a session guarantee an async replica does not provide).
- C) Causal; the user expected sequential.
- D) Nothing is wrong; Postgres is always strongly consistent.

---

**Q4.** Order these consistency models from strongest to weakest: causal, eventual, linearizable, sequential.

- A) eventual, causal, sequential, linearizable
- B) linearizable, sequential, causal, eventual
- C) sequential, linearizable, eventual, causal
- D) linearizable, causal, sequential, eventual

---

**Q5.** Which is the *strongest* consistency model that a system can provide while remaining available under a network partition?

- A) Linearizable
- B) Sequential
- C) Causal (causal+)
- D) None — all consistency is impossible under partition

---

**Q6.** PACELC adds what to CAP?

- A) A third option besides consistency and availability.
- B) The "else" branch: when there is **no** partition, the system still trades **L**atency against **C**onsistency on every request.
- C) A way to have all three of C, A, and P.
- D) A formal proof that partitions never happen in modern datacenters.

---

**Q7.** Classify DynamoDB (default configuration) and etcd in PACELC.

- A) DynamoDB PA/EL; etcd PC/EC.
- B) DynamoDB PC/EC; etcd PA/EL.
- C) Both PA/EL.
- D) Both PC/EC.

---

**Q8.** The FLP theorem proves that in an asynchronous network with one possible crash, no deterministic consensus protocol can guarantee which property?

- A) Agreement (no two processes decide differently).
- B) Validity (the decided value was proposed).
- C) Termination (every correct process eventually decides).
- D) All three simultaneously, even with no failures.

---

**Q9.** Which escape hatch from FLP do Raft and Paxos actually use?

- A) Randomization (coin flips).
- B) An unreliable failure detector only.
- C) Partial synchrony — timeouts that assume the network is *eventually* timely, trading guaranteed termination for eventual termination.
- D) They don't escape FLP; they violate it.

---

**Q10.** "Two processes never decide different values" and "the protocol eventually decides" are, respectively:

- A) Both safety properties.
- B) Both liveness properties.
- C) A safety property and a liveness property.
- D) A liveness property and a safety property.

---

**Q11.** Why is FLP best understood as a *liveness* impossibility rather than a safety one?

- A) Because consensus protocols can always stay *safe* (never decide two values) even in a fully asynchronous network; what FLP steals is the guarantee of *termination*.
- B) Because safety is impossible but liveness is easy.
- C) Because FLP only applies to read/write registers, not consensus.
- D) Because liveness and safety are the same under partition.

---

**Q12.** In the design heuristic from this week, which property should you almost never sacrifice to buy the other?

- A) Sacrifice safety freely to gain liveness — a stalled system is worse than a wrong one.
- B) Never sacrifice safety to buy liveness — a system that occasionally stalls is annoying, but one that returns wrong/divergent/lost data is broken, often silently.
- C) Always sacrifice both equally.
- D) Liveness must always be preserved at the cost of safety.

---

**Q13.** A vendor's page says the database is "strongly consistent and highly available." Using this week's vocabulary, what is the most likely truth?

- A) The system genuinely provides linearizability and CAP-availability simultaneously under partition.
- B) "Strongly consistent" likely applies only to an opt-in read mode, and "highly available" is likely a PA/EL claim with an unquantified staleness window — the two words describe different configurations, not one.
- C) The system has defeated the CAP theorem.
- D) The system is CA and therefore a single node.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — In CAP, consistency *is* linearizability. It is not ACID's C and not "the data is correct." (Lecture 1 §2.1.)
2. **B** — Partition tolerance is forced by the world; you cannot opt out of packet loss. "CA" therefore describes a single node, not a distributed system. (Lecture 1 §2.5.)
3. **B** — The async replica provides **eventual** consistency (lag is the staleness window); the user expected **read-your-writes**, a session guarantee an async replica doesn't give. The fix is a consistency-model decision, not a retry. (Lecture 1 §5.)
4. **B** — Linearizable > sequential > causal > eventual. Stronger models imply weaker ones. (Lecture 1 §3.)
5. **C** — Causal (causal+) is the strongest model available under partition; linearizable and sequential require coordination that a partition can block. (Lecture 1 §3.3.)
6. **B** — PACELC's contribution is the "else" branch: even with a healthy network you trade latency against consistency on every request — the tradeoff CAP ignores. (Lecture 2 §1.1.)
7. **A** — DynamoDB default is PA/EL (available + fast, eventually consistent); etcd is PC/EC (minority refuses; coordinates through quorum). (Lecture 2 §1.3.)
8. **C** — FLP forbids guaranteed **termination**. Agreement and validity (safety) can always be kept; termination (liveness) cannot be guaranteed in a fully async network with one crash. (Lecture 2 §2.2.)
9. **C** — Partial synchrony: timeouts that assume eventual timeliness. Raft elects a new leader on timeout, trading guaranteed termination for eventual termination, never sacrificing safety. (Lecture 2 §2.4.)
10. **C** — "Never decide differently" is safety (a finite prefix can violate it); "eventually decides" is liveness (only an infinite execution violates it). (Lecture 2 §3.1.)
11. **A** — Consensus protocols stay safe even when fully asynchronous; FLP takes the termination (liveness) guarantee, which is why the escape hatches buy back liveness under extra assumptions rather than repairing safety. (Lecture 2 §3.2.)
12. **B** — Never trade safety for liveness. A stall is recoverable; silent data corruption/divergence/loss usually is not. Raft stalls rather than ever violating log agreement. (Lecture 2 §3.2.)
13. **B** — The two words almost always describe different configurations: an opt-in strong-read mode and a separate PA/EL availability story with an unstated staleness window. Naming that gap is the Challenge-1 audit skill. (Lecture 1 §6, Lecture 2 §1; Challenge 1.)

</details>

---

If you scored under 9, re-read the lecture sections cited in the answers you missed. If you scored 11 or higher, you're ready for the [homework](./homework.md).
