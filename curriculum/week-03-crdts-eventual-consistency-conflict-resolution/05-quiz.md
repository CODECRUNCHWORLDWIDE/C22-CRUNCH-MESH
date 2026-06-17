# Week 3 — Quiz

Fourteen questions. Take it with your lecture notes closed. Aim for 11/14 before moving to Week 4. Answer key is at the bottom — don't peek.

---

**Q1.** What is the difference between eventual consistency and *strong* eventual consistency (SEC)?

- A) They are identical.
- B) SEC adds: any two replicas that have applied the *same set of updates* are in the *same state*, by construction, with no conflict-resolution step.
- C) SEC is weaker — it allows more divergence.
- D) SEC requires consensus.

---

**Q2.** A state-based CRDT (CvRDT) converges if and only if its merge forms a:

- A) total order.
- B) join-semilattice — commutative, associative, idempotent, with a least upper bound.
- C) consensus quorum.
- D) hash table.

---

**Q3.** Why do the three laws (commutative, associative, idempotent) guarantee convergence over an unreliable network?

- A) They make the network reliable.
- B) They make merge immune to exactly what the network does: reorder (commutativity), regroup/batch (associativity), and duplicate (idempotence) messages.
- C) They speed up the network.
- D) They require exactly-once delivery.

---

**Q4.** What delivery guarantee does a *state-based* CRDT need from the network?

- A) Reliable, exactly-once, causal-order delivery.
- B) Only eventual, unordered, at-least-once delivery (gossip) — because merge is idempotent and commutative.
- C) Synchronous, totally-ordered broadcast.
- D) No network at all.

---

**Q5.** A G-counter's merge is element-wise max over per-replica counts. Why element-wise max?

- A) Max is faster than sum.
- B) Each replica only increments its own slot, so the true value of a slot is the maximum any replica has seen — and max is a join-semilattice.
- C) Max prevents the counter from growing.
- D) Sum would also work identically.

---

**Q6.** Why can't you build a counter that supports decrements as a single G-counter, and what do you use instead?

- A) You can; just allow negative increments.
- B) Decrement isn't monotonic, so max breaks; use a PN-counter (two G-counters, P and N, value = sum(P) − sum(N)).
- C) Use an OR-set.
- D) Decrements require consensus.

---

**Q7.** What does the OR-set do that a 2P-set cannot?

- A) Converge.
- B) Allow an element to be re-added after it was removed (each add gets a fresh unique tag), instead of "remove is forever."
- C) Use less metadata.
- D) Enforce uniqueness.

---

**Q8.** In an OR-set, replica A removes `x` (observing tag t1) while replica B concurrently re-adds `x` (creating tag t2). After merge, is `x` present?

- A) No — the remove wins.
- B) Yes — add-wins: t2 is in the add-set and not in the remove-set (A never observed t2), so `x` is present.
- C) It's undefined.
- D) Only if A's timestamp is higher.

---

**Q9.** Why is an LWW-register described as a "footgun"?

- A) It doesn't converge.
- B) It silently discards concurrent writes (keeps only the higher timestamp), and with wall-clock timestamps the loss is nondeterministic.
- C) It uses too much metadata.
- D) It requires consensus.

---

**Q10.** When concurrent writes to a single-slot field both matter, which register should you use?

- A) LWW-register.
- B) MV-register — it keeps concurrent writes as siblings (detected via version vectors) for the application to resolve.
- C) G-counter.
- D) A consensus protocol always.

---

**Q11.** What is the central operational cost of CRDTs, and what bounds it?

- A) CPU; faster cores bound it.
- B) Metadata growth (tags, tombstones); delta-CRDTs (small messages), causal-stability reclamation (bounded tombstones), and dotted version vectors (precise per-write identity) bound it.
- C) Network bandwidth only; nothing bounds it.
- D) There is no cost.

---

**Q12.** A delta-state CRDT improves on a naive state-based CRDT by:

- A) shipping only the *delta* (the change) instead of the whole state on each merge.
- B) using consensus.
- C) removing tombstones immediately.
- D) switching to LWW.

---

**Q13.** For which of these is a CRDT the WRONG answer (you need coordination instead)?

- A) A shopping cart's set of items.
- B) A like/unlike counter.
- C) "This username must be globally unique" — a reject-the-conflict invariant a merge cannot enforce.
- D) A collaborative document's text.

---

**Q14.** Which production system pairs each correctly with its CRDT role?

- A) Riak: first-class CRDT data types (counters/sets/maps), state-based, used in the Bet365 high-availability case study.
- B) Automerge: a consensus protocol with no CRDTs.
- C) Redis Active-Active: a single-leader CP store.
- D) AntidoteDB: an LWW-only store.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — SEC = eventual delivery + strong convergence (same updates ⟹ same state, by construction, no resolution step). (Lecture 1 §1.2.)
2. **B** — Convergence ⟺ join-semilattice: commutative/associative/idempotent merge that is the least upper bound. (Lecture 1 §3.)
3. **B** — The three laws make merge immune to reorder/regroup/duplicate — exactly the anomalies an unreliable network introduces. (Lecture 1 §3.1.)
4. **B** — State-based needs only eventual, unordered, at-least-once delivery (gossip), because idempotence/commutativity absorb anomalies. (Lecture 1 §2.1.)
5. **B** — Each replica owns its slot; the true value is the max seen; max is a semilattice. (Lecture 1 §4.)
6. **B** — Decrement isn't monotonic; use a PN-counter (two G-counters). (Lecture 2 §1.2.)
7. **B** — The OR-set's per-add unique tags allow re-add after remove, fixing the 2P-set's "remove is forever." (Lecture 2 §2.1–2.2.)
8. **B** — Add-wins: the concurrent (unobserved) re-add tag survives the remove. (Lecture 2 §2.2 / §2.2b.)
9. **B** — LWW silently discards concurrent writes; wall-clock timestamps make the loss nondeterministic. (Lecture 2 §3.1.)
10. **B** — MV-register keeps concurrent writes as siblings for the app to resolve. (Lecture 2 §3.2.)
11. **B** — Metadata growth; bounded by delta-CRDTs, causal-stability reclamation, and dotted version vectors. (Lecture 2 §4.)
12. **A** — Delta-CRDTs ship only the change, not the whole state. (Lecture 2 §4.2.)
13. **C** — Uniqueness is a reject-the-conflict invariant; a merge keeps both registrations, violating it — needs coordination. (Lecture 1 §5.)
14. **A** — Riak: first-class state-based CRDT data types; the Bet365 case study. (Lecture 2 §5.1.)

</details>

---

If you scored under 10, re-read the lecture sections cited in the answers you missed. If you scored 12 or higher, you're ready for the [homework](./06-homework.md).
