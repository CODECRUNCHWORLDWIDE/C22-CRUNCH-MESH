# Week 3 Homework

Six problems that drive CRDT reasoning and implementation into your fingers. The full set should take about **5 hours**. Work in your Week 3 Git repository (the same workspace as the exercises and the `orset-cart` mini-project) so every problem produces at least one commit you can point to at the midterm architecture review.

The headline deliverable is **Problem 4 — the "is a CRDT the right answer?" decision memo**. Treat it as the artifact a reviewer reads, not a journal entry.

Each problem includes a short **problem statement**, **acceptance criteria**, a **hint**, and an **estimated time**.

---

## Problem 1 — Prove the three laws by hand for a G-set

**Problem statement.** For a grow-only set (merge = union), prove the three semilattice laws by hand in `notes/week-03/gset-laws.md`, using concrete sets `x = {a}`, `y = {b}`, `z = {a, c}`: show commutativity, associativity, and idempotence with the actual unions written out. Then state the partial order (`x ≤ y` iff `merge(x,y) = y`) and identify the bottom and top of the lattice over `{a, b, c}`.

**Acceptance criteria.**
- All three laws shown with explicit unions for the given sets.
- The partial order defined and the empty set identified as bottom.
- A one-sentence statement of why these three laws guarantee convergence.
- Committed.

**Hint.** Set union is the easiest semilattice to verify — every law is a one-line set computation. The point is to *do* it explicitly so the algebra stops being abstract (Lecture 1 §4d).

**Estimated time.** 30 minutes.

---

## Problem 2 — Trace an OR-set add-wins by hand

**Problem statement.** By hand in `notes/week-03/orset-trace.md`, trace two replicas through: both add `x` (tags differ), replica A removes `x` (observing its tag), replica B concurrently re-adds `x` (new tag), then merge. Show the add-set and remove-set at each step and compute whether `x` is present after merge. Then run the same trace through Exercise 2's OR-set and confirm.

**Acceptance criteria.**
- The add-set and remove-set are shown at every step.
- The final presence of `x` is computed correctly (present, by add-wins).
- The code result matches your hand trace.
- One sentence on why add-wins is the right default for a shopping cart.
- Committed.

**Hint.** The trick is that a remove only tombstones the tags it has *observed*. A concurrent add creates a tag the remover never saw, so it survives. Work through Lecture 2 §2.2b's table on your own example.

**Estimated time.** 45 minutes.

---

## Problem 3 — Build and property-test a custom CRDT

**Problem statement.** Implement one CRDT *not* covered in the exercises — a **G-set**, a **2P-set**, or an **enable-once flag** (a boolean that can be set to true but never back to false, merge = OR) — in `notes/week-03/custom-crdt/`. Property-test its merge for commutativity, associativity, and idempotence (the Exercise 3 pattern, in your language of choice). Document which CRDT you built and what semantics it encodes.

**Acceptance criteria.**
- A working CRDT with `update`, `value`, and `merge`.
- Property tests for all three laws, passing over many random cases.
- A note on the CRDT's semantics and one realistic use for it.
- For a 2P-set: explicitly note the "remove is forever" limitation.
- Committed.

**Hint.** The enable-once flag is the simplest (merge = boolean OR; once true, always true). The 2P-set teaches the "remove is forever" trap. Pick based on what you want to understand. All three are easy to property-test.

**Estimated time.** 1 hour.

---

## Problem 4 — The "is a CRDT the right answer?" memo (headline deliverable)

**Problem statement.** Pick **three** pieces of mutable distributed state — one that's clearly a CRDT fit, one that clearly needs coordination, and one genuinely ambiguous. For each, write a section in `notes/week-03/crdt-decision-memo.md` that:

1. Describes the data and how it's updated (and whether concurrent updates are possible).
2. Runs the Lecture 2 §5c decision procedure: (a) is there real concurrency? (b) can a merge violate an invariant? (c) is losing a concurrent write acceptable?
3. Reaches a verdict: a specific CRDT, LWW (justified), or "coordination/consensus."
4. For the CRDT cases, states the metadata cost you're accepting; for the consensus case, states why no CRDT can hold the invariant.

**Acceptance criteria.**
- `notes/week-03/crdt-decision-memo.md` covers three pieces of state with the four points each.
- The coordination case correctly identifies a *reject-the-conflict invariant* (uniqueness, non-negativity, fixed capacity) that no merge can enforce.
- The ambiguous case is genuinely argued (not obvious), with the deciding factor named.
- Each verdict follows from the decision procedure, not from vibes.
- Committed.

**Hint.** The strongest memos use real state from a system you know. The ambiguous case is the most valuable — e.g., "inventory count" can be a CRDT *if* you accept eventual oversell-then-reconcile, or needs coordination *if* you can never oversell. The deciding factor (your tolerance for transient invalidity) is the whole memo.

**Estimated time.** 1 hour 15 minutes.

---

## Problem 5 — Measure metadata growth and propose a fix

**Problem statement.** Using the mini-project's OR-set cart (or Exercise 2's OR-set), run an escalating operation count (10 → 100 → 1,000 → 10,000 add/remove ops on a small item set) and record the live-item count vs add-set/remove-set sizes in `notes/week-03/metadata-growth.md`. Then propose, in two paragraphs, which mitigation (delta-CRDT, tombstone reclamation, or both) you'd apply and why.

**Acceptance criteria.**
- A table showing operation count vs metadata size, demonstrating linear metadata growth with near-constant live items.
- A clear statement of the problem (metadata dwarfs data over time).
- A specific mitigation proposal with reasoning (delta-CRDT cuts bandwidth; reclamation cuts stored state).
- Committed.

**Hint.** The shape to expect is in Lecture 2 §4.5: live items stay in the tens, metadata grows with total ops. The two mitigations attack different costs (wire bandwidth vs stored bytes) — a real system applies both.

**Estimated time.** 50 minutes.

---

## Problem 6 — Find an LWW-where-it-hurts in the wild

**Problem statement.** Find a real system, library, or codebase that uses last-writer-wins for a field where concurrent writes can occur and matter. In `notes/week-03/lww-in-the-wild.md`, document: where the LWW is, what concurrent-write scenario would lose data, and what CRDT (or coordination) would fix it. If you can't find one in code you have access to, analyze Cassandra's default LWW cell resolution or a Redis/DynamoDB last-write pattern.

**Acceptance criteria.**
- `notes/week-03/lww-in-the-wild.md` names a real LWW usage (cite the docs/code).
- A concrete concurrent-write scenario that loses data.
- The CRDT or coordination fix, with one sentence on the tradeoff.
- Committed.

**Hint.** Cassandra's default conflict resolution is LWW by cell timestamp — the canonical example (and the source of real "our writes disappear" incidents, Week 2 Lecture 1's case study). Analyze how a concurrent write to the same cell can lose data and what a Cassandra CRDT (or a counter type, or app-level merge) would do instead.

**Estimated time.** 40 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 — Prove the three laws (G-set) | 30 min |
| 2 — Trace OR-set add-wins | 45 min |
| 3 — Build + property-test a custom CRDT | 1 h 0 min |
| 4 — CRDT decision memo (headline) | 1 h 15 min |
| 5 — Measure metadata growth | 50 min |
| 6 — LWW in the wild | 40 min |
| **Total** | **~5 h 0 min** |

When you've finished all six, push your repo and make sure the `orset-cart` [mini-project](./mini-project/README.md) is in the same workspace — Phase 4 (Week 20) promotes it to active-active across regions. Then take the [quiz](./quiz.md) with your notes closed.
