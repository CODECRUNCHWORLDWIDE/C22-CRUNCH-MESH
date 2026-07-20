# Week 20 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 21. Answer key is at the bottom — don't peek.

---

**Q1.** What does "convergence" guarantee, and what does it crucially *not* guarantee?

- A) It guarantees the agreed value is correct.
- B) It guarantees all replicas reach the *same* state (agreement) — but says *nothing* about whether that agreed value is the one users intended (correctness). A LWW field converges and can silently lose data.
- C) It guarantees no data is ever lost.
- D) It guarantees the writes happened in timestamp order.

---

**Q2.** What is strong eventual consistency (SEC)?

- A) Replicas are always identical at all times.
- B) Any two replicas that have delivered the *same set* of updates are in the *same state*, regardless of the *order* the updates arrived — which is why no coordination on ordering is needed.
- C) The strongest consistency, equivalent to linearizability.
- D) Eventually one replica becomes the source of truth.

---

**Q3.** Why is an OR-set the right type for a cart's items, and LWW the footgun?

- A) OR-sets are faster.
- B) An OR-set is add-wins / observed-remove: a concurrent add in another region survives a merge, so every customer's added items are preserved. An LWW-register over the whole cart keeps only the latest-timestamp cart and silently discards the other region's concurrent adds.
- C) LWW can't store sets.
- D) They're equivalent; either works.

---

**Q4.** What are Automerge, Yjs, and Redis Active-Active each for?

- A) They're three names for the same library.
- B) Automerge = a rich JSON-document CRDT (in-app state); Yjs = a high-performance shared-text/structured-data CRDT (collaborative editors); Redis Active-Active = primitive CRDT data types (counter/set/register) at the data tier. Documents vs primitives.
- C) All three are databases.
- D) Automerge is for text, Yjs for counters, Redis for documents.

---

**Q5.** When is LWW actually the *correct* choice?

- A) Never — LWW is always wrong.
- B) When concurrent writes are genuinely interchangeable and you want the newest — e.g., a last-seen/presence timestamp, where discarding the older write is the *intended* behavior. LWW is a footgun only when the discarded concurrent write is real data you needed.
- C) Always — LWW is the simplest, so prefer it.
- D) Only for counters.

---

**Q6.** Concurrent "+2 apples" in region A and "+3 apples" in region B. What does a PN-counter converge to, and what would LWW give?

- A) PN-counter: 3; LWW: 5.
- B) PN-counter: 5 (both increments count); LWW: 2 or 3 (only the latest-timestamp write survives, the other is lost).
- C) Both give 5.
- D) Both give 2.

---

**Q7.** Two writes have vector clocks {A:2, B:1} and {A:1, B:2}. What's their relationship and what should the system do?

- A) The first dominates; keep it.
- B) Neither dominates the other → they are *concurrent* (a conflict) → keep both as *siblings* for application-layer resolution, rather than silently picking one.
- C) They're identical; keep either.
- D) The second is newer; keep it.

---

**Q8.** When is surfacing a conflict as siblings (rather than auto-merging) the *correct* behavior?

- A) Never; always auto-merge.
- B) When the field has no safe automatic merge (e.g. a shipping address whose fields are interdependent) — surfacing both siblings for the user/app to reconcile is honest, whereas silently LWW-picking one is data loss disguised as success.
- C) Only when the CRDT library crashes.
- D) Always; never auto-merge anything.

---

**Q9.** What is an OR-set tombstone, and why is it a metadata-cost concern?

- A) A backup of the set.
- B) A marker that a particular add was removed — kept so a stale replica's old add can't *resurrect* the element on re-sync. If never garbage-collected, tombstones accumulate without bound, so the set's *physical* size grows even as its *logical* size stays tiny.
- C) An error log entry.
- D) A tombstone is the same as a snapshot.

---

**Q10.** What safety condition must hold before you garbage-collect a tombstone (or compact op history)?

- A) None; GC anytime.
- B) **Causal stability** — every replica must have *seen* the removal, so none can re-introduce the removed element. Reclaiming a tombstone a replica hasn't observed would let that replica resurrect the deleted item.
- C) The set must be empty.
- D) A leader must approve it.

---

**Q11.** Why is inventory stock that must never oversell *not* a CRDT field?

- A) It's too large for a CRDT.
- B) A CRDT would *converge* concurrent "sell the last unit" writes from two regions into "both sold" (overselling) — converging to a *wrong* value. The correct behavior under concurrency is *coordination* (a single writer per SKU with a lease, or a transaction), not convergence.
- C) Inventory doesn't change.
- D) CRDTs don't support numbers.

---

**Q12.** "Are we eventually consistent or strongly consistent?" — at what granularity is this question answered?

- A) System-wide; pick one for the whole service.
- B) *Per field.* The same cart service has CRDT fields (items, quantities), sibling-resolved fields (address), and strong-consistency dependencies (the inventory check). A senior design labels each field's consistency model; a blanket answer quietly mis-applies a policy.
- C) Per region.
- D) Per request.

---

**Q13.** An active-active cart "converged" after a partition heal — replicas agree, no errors — but customers report missing items. What happened?

- A) The CRDT library has a bug.
- B) The cart was modeled with a type whose convergence is *correct-by-construction but wrong for the field* — almost certainly LWW over a set, which converges (replicas agree) while silently discarding one region's concurrent adds. The convergence succeeded; the type choice was the bug. Fix: change the type to an OR-set.
- C) The regions never actually partitioned.
- D) The monitoring is broken.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — Convergence = agreement, not correctness. The whole week's thesis. (Lecture 1 §2.2.)
2. **B** — Same updates → same state, order-independent; hence no coordination needed. (Lecture 1 §2.1.)
3. **B** — OR-set is add-wins/observed-remove (concurrent adds survive); LWW-whole-cart discards a region's adds. (Lecture 1 §3; Exercise 1; Challenge.)
4. **B** — Automerge (documents), Yjs (shared text/structured), Redis Active-Active (primitive data-tier CRDTs). (Lecture 1 §1.)
5. **B** — LWW is correct when the older concurrent write is *meant* to be discarded (a presence timestamp). (Lecture 1 §3.)
6. **B** — PN-counter sums (5); LWW keeps one (2 or 3). (Lecture 1 §3; Exercise 2.)
7. **B** — Neither dominates → concurrent → keep both as siblings. (Lecture 2 §1.2; Exercise 3.)
8. **B** — When no safe auto-merge exists; surfacing beats silent LWW data loss. (Lecture 2 §1.3.)
9. **B** — A removed-add marker preventing resurrection; unbounded if not GC'd. (Lecture 2 §2.1.)
10. **B** — Causal stability: all replicas have seen the remove before you reclaim. (Lecture 2 §2.2.)
11. **B** — A CRDT converges to an oversold count; coordination (single writer/lease) is correct. (Lecture 2 §3.1.)
12. **B** — Per field; the cart has CRDT, sibling, and strong-consistency fields. (Lecture 2 §3.3.)
13. **B** — Convergent-but-wrong: LWW over a set converged while losing adds; fix the type. (Challenge; Lecture 1 §2.2.)

</details>

---

If you scored under 9, re-read the lecture sections cited in the answers you missed. If you scored 11 or higher, you're ready for the [homework](./homework.md).
