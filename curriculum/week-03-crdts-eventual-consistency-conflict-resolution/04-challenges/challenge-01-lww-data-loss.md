# Challenge 1 — Catch LWW Losing Data, Then Fix It

**Time estimate:** ~90 minutes.

## Problem statement

You are reviewing a multi-region service that stores each user's profile. The previous engineer used **last-writer-wins** (a value plus a timestamp) for every field, reasoning "it converges, so it's fine." It *does* converge — and it *silently loses* concurrent edits. Your job is to reproduce the data loss, name it precisely, fix it with the right CRDT, and prove with a test that the fix preserves all concurrent writes.

This is the data-loss bug CRDTs exist to prevent, reproduced in your own hands so you never trust LWW carelessly again.

## Part A — Reproduce the LWW data loss

Build a tiny two-replica store where each replica holds an LWW-register for a `tags` field (a set of user-chosen tags, stored — wrongly — as a single LWW value). Use the harness below as a starting point (Python; adapt to your language if you prefer).

```python
#!/usr/bin/env python3
"""LWW data-loss harness. Two replicas concurrently edit the SAME field."""

class LWWRegister:
    def __init__(self, replica_id):
        self.id = replica_id
        self.vt = (None, -1, -1)   # (value, timestamp, replica_id)

    def set(self, value, ts):
        self.vt = (value, ts, self.id)

    def value(self):
        return self.vt[0]

    def merge(self, other):
        if (other.vt[1], other.vt[2]) > (self.vt[1], self.vt[2]):
            self.vt = other.vt


# Scenario: a user has tags {"vip"}. Concurrently:
#   - Replica A (phone)  adds "beta"  -> sets the field to {"vip","beta"} @ ts=100
#   - Replica B (laptop) adds "early" -> sets the field to {"vip","early"} @ ts=101
# Both edits are MEANINGFUL. The user wants BOTH "beta" and "early".

A = LWWRegister("A")
B = LWWRegister("B")
A.set({"vip"}, ts=10); B.merge(A)          # both start at {"vip"}
A.set({"vip", "beta"}, ts=100)             # phone adds "beta"
B.set({"vip", "early"}, ts=101)            # laptop adds "early" (concurrent)

# Heal: merge both ways.
A.merge(B); B.merge(A)
print("converged tags:", A.value())        # what survived?
```

Run it. Record the output in `challenge-01-lww-loss.md`. You will see the converged value is `{"vip", "early"}` — **"beta" is gone.** The phone's edit vanished. Note: had the timestamps come from wall clocks (Week 2), *which* edit survives would depend on clock skew, making the loss nondeterministic.

Document:
1. **What was lost** — the "beta" tag, and why (the whole-field LWW kept only the higher-timestamp snapshot).
2. **Why it's silent** — no error, no warning; the store "converged" and reported success.
3. **The wall-clock amplifier** — one sentence on how clock skew makes this nondeterministic.

## Part B — Fix it with the right CRDT

The `tags` field is a **set of independently-meaningful elements**, so the correct model is an **OR-set**, not an LWW-register over the whole set. Replace the field with an OR-set (use your Exercise 2 implementation) and re-run the *same* scenario:

```python
# Now each replica holds an OR-set for tags. The concurrent adds of "beta" and
# "early" both create fresh tags, so the merge (union) keeps BOTH.
A = ORSet("A"); B = ORSet("B")
A.add("vip"); B.merge(A)
A.add("beta")     # phone
B.add("early")    # laptop (concurrent)
A.merge(B); B.merge(A)
print("converged tags:", A.value())   # {"vip", "beta", "early"} -- nothing lost!
```

Document the new converged value (`{"vip", "beta", "early"}`) and explain why the OR-set preserves both concurrent adds (union of tagged adds — Lecture 2 §2.2).

## Part C — Prove it with a test

Write an automated test (`test_no_loss.py` or equivalent) that:
1. Sets up two replicas with the OR-set `tags` field.
2. Applies the concurrent adds.
3. Merges in **both orders** (A←B and B←A) and asserts both converge to the *same* set.
4. Asserts the converged set **contains both** "beta" and "early" (the no-loss property).
5. For contrast, includes a test showing the **LWW** version *fails* the no-loss assertion (one tag is missing).

The test is the deliverable that turns "I fixed it" into "I proved it stays fixed."

## Acceptance criteria

- [ ] `challenge-01-lww-loss.md` documents the reproduced LWW data loss with the actual output and the three points from Part A.
- [ ] The OR-set fix is implemented and the same scenario now converges to `{"vip", "beta", "early"}`.
- [ ] An automated test asserts: (a) both merge orders converge to the same set, (b) the OR-set keeps both concurrent tags, (c) the LWW version loses one.
- [ ] You correctly explain *why* a single LWW-register over a set is the wrong model and an OR-set is right.
- [ ] Committed to your Week 3 repo under `challenges/challenge-01/`.

## The trap (read after a first attempt)

The subtle wrong fix is to keep the LWW-register but "make the timestamps better" (use a logical clock, use server time, add more precision). **That does not fix it.** No timestamp scheme makes LWW preserve concurrent writes, because LWW *by definition* keeps one and discards the rest — better timestamps only change *which* one you lose, not *whether* you lose one. The fix must change the *data type* (to one whose merge keeps both), not the timestamp source. If your fix still has a single LWW value for the whole set, you've moved the bug, not removed it. The OR-set works because its merge is *union*, which is a join that includes both — the §3 semilattice property doing exactly what it's for.

## Stretch

- Extend the harness to **three** replicas with three concurrent tag adds, and confirm the OR-set keeps all three while LWW keeps only one.
- Add a **concurrent remove**: phone removes "vip" while laptop concurrently re-adds "vip". Show the OR-set's add-wins keeps "vip" (Lecture 2 §2.2b), and discuss whether add-wins is the right policy for *this* field (it is for tags; argue why).
- Identify a field in a real system you've worked on that uses LWW where concurrent writes matter, and write the one-paragraph bug report you'd file. This is the most valuable artifact — a real latent data-loss bug, named.

## Why this matters

In the capstone, the cart-service is a CRDT precisely so it never loses an item across a region partition, and you demo its convergence live. This challenge is that demo's foundation: you cannot appreciate *why* the cart is a CRDT until you've watched LWW silently eat a write. Every multi-master system has fields where someone reached for LWW because it was simple; the engineer who can spot "those writes are concurrent and meaningful, so LWW is losing data here" is the one who prevents the incident instead of debugging it.
