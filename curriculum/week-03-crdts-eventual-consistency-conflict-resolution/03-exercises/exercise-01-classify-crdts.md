# Exercise 1 — Classify the CRDTs

**Goal:** For each of six data-modeling problems, decide the right tool: a specific CRDT, or "this needs consensus / a single writer — a CRDT will converge to an invalid state." This is the load-bearing reasoning skill of the week: the Lecture 1 §5 boundary (merge-includes-both vs reject-the-conflict) applied to real problems.

**Estimated time:** 60 minutes. Written.

---

## Setup

Create `notes/week-03/classification.md`. For each problem, fill in a table row and a one-sentence justification. The decision procedure (Lecture 2 §5c):

1. Can two replicas concurrently update this, both meaningfully? (No → single writer.)
2. Can merging both updates violate an invariant? (Yes → consensus, not a CRDT.)
3. Is losing a concurrent write acceptable? (Yes → LWW; No → a lossless CRDT.)

The candidate answers are: **G-counter, PN-counter, OR-set, LWW-register, MV-register, CRDT-map**, or **"consensus / single writer."**

---

## The six problems

| # | Problem | Right tool | Justification (one sentence) |
|---|---|---|---|
| 1 | A live "viewers watching this stream right now" count, updated from many regions, only ever increasing over the stream's life | | |
| 2 | A shopping cart's set of items, edited concurrently from a phone and a laptop offline, must never lose an added item | | |
| 3 | A user's display-name field, edited rarely, where a concurrent edit conflict should be *shown* to the user to resolve | | |
| 4 | The number of available seats on a flight (must never go below zero or oversell) | | |
| 5 | A document's like/unlike counter (goes up and down) across regions | | |
| 6 | A globally-unique handle/username registration ("@alice" can be taken by only one person) | | |

## Follow-up questions

Answer each in 2–4 sentences in the same file.

1. **The trap question.** Two of these problems (which?) are the ones where a CRDT would *converge to an invalid state*. Explain what specifically goes wrong if you naively use a CRDT (say, a counter or a set) for each.

2. **LWW vs MV.** Problem 3 could use either an LWW-register or an MV-register. Explain the user-visible difference: what does each do when two edits to the display name happen concurrently, and why is MV the better choice *here* specifically?

3. **The cart's add-wins.** Problem 2's OR-set has "add-wins" semantics. Describe a concrete sequence (remove on phone, concurrent re-add on laptop) and state what the merged cart contains, and why that's the right answer for a shopping cart.

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] All six rows are filled with a specific tool and a justification.
- [ ] Problems 4 and 6 are correctly identified as **consensus / single writer**, not a CRDT.
- [ ] Problem 1 is a **G-counter** (monotonic) and Problem 5 is a **PN-counter** (up and down) — and you can say why 5 isn't a G-counter.
- [ ] All three follow-up questions are answered.
- [ ] Committed.

---

## Answer sketch (read only after you've attempted it)

1. **G-counter** — only increases over the stream's life; want the total across regions; monotonic, so element-wise max is perfect.
2. **OR-set** — concurrent adds must all survive; add-wins handles concurrent remove/re-add; the canonical cart CRDT.
3. **MV-register** — a single-slot field where concurrent edits matter; MV surfaces both as siblings for the user to resolve, rather than LWW silently dropping one.
4. **Consensus / single writer** — "never oversell" is a reject-the-conflict invariant; a CRDT counter would let two regions each sell the last seat and merge to a negative/oversold state. Needs coordination (Week 2 leases per seat block).
5. **PN-counter** — goes up and down (like/unlike), so a G-counter won't do; PN-counter (two G-counters) handles decrements.
6. **Consensus / single writer** — uniqueness is the archetypal reject-the-conflict invariant; two regions could each register "@alice" and a set-CRDT merge would keep both, violating uniqueness. Needs coordination.

**Follow-ups:**
1. Problems 4 and 6. For 4, a PN-counter converges to whatever the increments/decrements sum to, ignoring the floor — two regions both sell the 100th seat, merge says "−1 seats," oversold. For 6, an OR-set keeps both "@alice" registrations, so two users both "own" the handle. In both, the CRDT *converges* but to a *semantically invalid* state, which is worse than a visible failure.
2. LWW keeps the higher-timestamp edit and silently discards the other (nondeterministic if wall-clock based); MV keeps both as siblings and lets the user pick. For a display name a user cares about, silently losing their edit is bad UX; surfacing "you have two versions, choose one" is honest.
3. Phone removes "milk" (observes tag t1); laptop concurrently re-adds "milk" (new tag t2). Merge: removes={t1}, adds={t1,t2}; t2 is live → milk is **present**. Right for a cart: the concurrent re-add means the user wanted it, so add-wins keeps it.

---

## Stretch

- Add three data items from a system you operate and classify each. The most instructive are the ones currently using LWW where the writes actually matter — those are latent data-loss bugs.
- For Problem 4 (seats), sketch how an **escrow/reservation** scheme could let you use a CRDT-ish approach *with* a coordinated reservation step — the hybrid that real ticketing systems use. (Hint: pre-allocate blocks of seats to regions via consensus, then each region sells its block CRDT-style.)

When this feels comfortable, move to [Exercise 2 — The CRDT zoo](./exercise-02-crdt-zoo.py).
