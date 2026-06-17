# Week 20 Homework

Six problems that revisit the week's topics and force the CRDT-design literacy into your fingers. The full set should take about **5 hours**. Work in your Week 20 Git repository (the same workspace as the exercises and the `cart-crdt` mini-project) so every problem produces at least one commit you can point to at the Phase 4 review and the capstone demo.

The headline deliverable is **Problem 4 — the per-field CRDT-selection memo**, the artifact a reviewer reads to see you understand CRDTs are a per-field tool, not a system-wide religion. Treat it as a design document, not a journal entry.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

Have **Node.js** (for Automerge) and **Python** ready, and the exercises working. Problems 1, 2, 3, 5, and 6 are runnable; problem 4 is the memo.

---

## Problem 1 — Convergence is not correctness (demonstrate the gap)

**Problem statement.** Take the *same* partition-heal scenario and run it two ways: as an OR-set cart and as an LWW-whole-cart. For each, report (a) did it converge (replicas equal)? and (b) is it correct (every acknowledged add present)? Show that both *converge* but only the OR-set is *correct*.

**Acceptance criteria.**

- `notes/week-20/convergence-vs-correctness.md` shows both models converging (A == B) and the OR-set preserving all adds while the LWW silently loses one region's adds.
- You state, in one sentence, why "the convergence metric is green" did not catch the LWW data loss.
- Committed.

**Hint.** Use Exercise 1's OR-set and the Challenge's LWW cart on the same scenario (concurrent adds in both regions). The OR-set keeps both; the LWW keeps one. Both are "converged."

**Estimated time.** 40 minutes.

---

## Problem 2 — The Automerge active-active cart, with intent checks

**Problem statement.** Extend Exercise 2: run the Automerge cart through a partition with concurrent adds, a remove, *and* concurrent quantity changes to the same SKU, then heal. Assert CONVERGED, LOSSLESS, and INTENT (quantity = sum of concurrent adds). Then break one field's type (model a quantity as a non-counter overwrite) and show INTENT fails while CONVERGED still passes.

**Acceptance criteria.**

- `notes/week-20/automerge-intent.md` (or the extended `.mjs`) shows all three checks passing on the correct model.
- You demonstrate that swapping the quantity to an overwrite makes INTENT fail (the sum is wrong) while CONVERGED still passes — convergence didn't catch it.
- Committed.

**Hint.** Automerge's `Counter` is a PN-counter — concurrent increments both count. Replace it with a plain number you overwrite, and concurrent writes stomp each other: the quantity becomes one region's value, not the sum. CONVERGED stays green; INTENT goes red.

**Estimated time.** 50 minutes.

---

## Problem 3 — Vector-clock siblings, end to end

**Problem statement.** Using Exercise 3, build a small "field with concurrent writes" pipeline: feed it two writes, have it detect (via vector clocks) whether they're causal or concurrent, and resolve them — auto-merge for a mergeable field, surface-siblings for a non-mergeable one. Cover all three cases: causal (one winner), concurrent-mergeable (business merge), concurrent-non-mergeable (siblings surfaced).

**Acceptance criteria.**

- `notes/week-20/siblings.md` records the three cases with the vector clocks, the concurrency verdict, and the resolution for each.
- For the non-mergeable case, you show both siblings surfaced (not silently LWW'd) and state why that's correct.
- You map the three cases onto cart fields (items = mergeable, address = non-mergeable, last-modified = causal/LWW).
- Committed.

**Hint.** Domination = "every component ≥ and at least one >." Concurrent = neither dominates. The non-mergeable resolution doesn't *compute* an answer — it *returns both* for a human/app to choose. That restraint is the point.

**Estimated time.** 45 minutes.

---

## Problem 4 — The per-field CRDT-selection memo (headline deliverable)

**Problem statement.** This is the syllabus skill ("picking the right CRDT for the right field; per-field consistency models"). Write a one-to-two-page memo at `notes/week-20/per-field-memo.md` that takes a real feature and assigns a consistency model to *every* field, with justification. Pick **one** feature and map all its fields:

- **Feature A — the shopping cart:** items, per-item quantity, applied coupon code, shipping address, last-modified timestamp, and the inventory availability it reads.
- **Feature B — a collaborative document:** the text body, the title, the list of collaborators, a "last editor" field, the document's share-permissions, and a server-side view counter.

Your memo must hit these headings:

1. **The field table** — every field, its chosen CRDT type or policy (OR-set / PN-counter / LWW-register / Automerge document / siblings / strong-consistency-not-a-CRDT), and one line of justification each.
2. **Why each converged value is the intended one** — for each CRDT field, why its merge rule produces what users want.
3. **The LWW footguns** — which fields would silently lose data if modeled as LWW, and what they'd lose.
4. **The non-CRDT fields** — which field(s) need *strong consistency* (not convergence) and why a CRDT there would be a convergent-but-wrong footgun.
5. **The sibling fields** — which field(s) have no safe auto-merge and must surface conflicts, and why that's correct rather than a failure.
6. **The metadata note** — which field(s) carry the most metadata cost (tombstone/history growth) and how you'd bound it.

**Acceptance criteria.**

- `notes/week-20/per-field-memo.md` exists, fits roughly one-to-two pages (600–1000 words), and hits all six headings.
- *Every* field gets a labeled consistency model with a justification — none left as "TBD" or "eventually consistent" without a type.
- At least one field is correctly identified as **strong-consistency-not-a-CRDT** with the overselling/double-count reasoning.
- At least one field is correctly identified as a **sibling / app-resolution** field.
- Committed.

**Hint.** The strongest memos resist the urge to make *everything* a CRDT. The discriminating moves are: spotting the field that needs strong consistency (inventory availability / share-permissions — a CRDT would converge to a *wrong* answer), and spotting the field where siblings beat auto-merge (the shipping address / the title two people renamed). A memo that labels every field "OR-set" has missed the entire point — the skill is the *discrimination*, field by field.

**Estimated time.** 1 hour.

---

## Problem 5 — Bound the metadata

**Problem statement.** Drive realistic churn on an OR-set cart (thousands of add/remove cycles) and measure the tombstone / history growth. Then implement (or describe and simulate) a causal-stability GC that reclaims tombstones once all replicas have seen the remove, and show the growth is bounded.

**Acceptance criteria.**

- `notes/week-20/metadata.md` shows the metadata (tombstone count / document size) growing under churn without GC.
- It shows the bounded size with the causal-stability GC applied (before/after).
- You state the safety condition (only reclaim what *all* replicas have observed) and why violating it would resurrect deleted items.
- Committed.

**Hint.** Without GC, every remove leaves a tombstone forever; after 5000 add/remove cycles you have ~5000 tombstones for a possibly-empty cart. The GC condition is causal stability: a tombstone is safe to drop once every replica's vector clock shows it has seen the remove. Track that and reclaim.

**Estimated time.** 40 minutes.

---

## Problem 6 — Diagnose a planted CRDT fault

**Problem statement.** Have a partner (or your future self) introduce ONE of these faults, then diagnose it from the outside: (a) a *set* field modeled as an LWW-register (silent add loss on heal), (b) a *quantity* field modeled as an overwrite instead of a counter (silent quantity loss), or (c) tombstones GC'd *before* causal stability (a deleted item resurrects). For whichever fault, produce a diagnosis: symptom, evidence, root cause, fix.

**Acceptance criteria.**

- `notes/week-20/planted-fault.md` records which fault, the diagnostic steps, the evidence (the converged-but-wrong value, or the resurrected item), the root cause, and the fix.
- You reach the diagnosis with at least two signals (e.g., the replicas are equal *and* an acknowledged write is missing → convergent-but-wrong; or an item reappears after being removed → premature GC).
- Committed.

**Hint.** The scariest is (c), premature-GC resurrection: an item the user *removed* comes *back* after a sync, because a tombstone was reclaimed before a replica that still held the old add had seen the remove. The two-signal tell: the item was definitely removed (in the history) AND it's present after sync (it resurrected). Faults (a) and (b) are the convergent-but-wrong family from the Challenge.

**Estimated time.** 35 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 — Convergence ≠ correctness | 40 min |
| 2 — Automerge with intent checks | 50 min |
| 3 — Vector-clock siblings | 45 min |
| 4 — Per-field CRDT memo (headline) | 1 h 0 min |
| 5 — Bound the metadata | 40 min |
| 6 — Diagnose a planted fault | 35 min |
| **Total** | **~5 h 0 min** |

When you've finished all six, push your repo and make sure the `cart-crdt` [mini-project](./07-mini-project/00-overview.md) is in the same workspace — it *is* the capstone's cart-service, and Week 22's gameday runs a convergence-across-a-partition demo on it. Then take the [quiz](./05-quiz.md) with your notes closed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Convergence ≠ correctness (P1)** | 15 | Both models converge; only the OR-set is lossless; the "green metric missed it" point made. |
| **Automerge intent checks (P2)** | 15 | CONVERGED+LOSSLESS+INTENT asserted; breaking a type fails INTENT while CONVERGED passes. |
| **Vector-clock siblings (P3)** | 15 | All three cases; non-mergeable surfaces siblings rather than LWW; mapped onto cart fields. |
| **Per-field memo (P4)** | 25 | Every field labeled + justified; a strong-consistency field and a sibling field correctly identified. |
| **Bounded metadata (P5)** | 20 | Growth measured; causal-stability GC bounds it; safety condition stated. |
| **Planted fault (P6)** | 10 | Two-signal diagnosis; correct root cause and fix. |

**90+** is portfolio-grade. **70–89** is solid but the memo likely makes everything a CRDT or misses the strong-consistency field. **Below 70** usually means Problem 1 or 4 was treated as a formality — they're the two that prove you understand that *converged is not correct* and that consistency is a *per-field* choice, which is the whole difference between using a CRDT and engineering with one.
