# Exercise 1 — The OR-Set Cart: Partition, Heal, Converge

**Goal:** Model the cart's *items* as an **OR-set** (observed-remove set), run two replicas through a partition where each accepts concurrent writes, heal them, and *prove* convergence **with every concurrent add preserved**. Then model the *same* scenario with an **LWW-register** and show it converges too — but silently discards one region's entire cart. By the end you can state, with a worked example, why the OR-set is the right type for cart items and LWW is the footgun.

**Estimated time:** 75 minutes. Guided.

---

## Setup

This exercise is *modeling* — you can do it by hand on paper, in a REPL, or in a few dozen lines of any language. The point is the *reasoning*, not a library. If you want to code it, a minimal OR-set is:

```python
# A minimal OR-set: each element carries a set of unique "add tags".
# add(x)    -> attach a fresh unique tag to x
# remove(x) -> tombstone every tag of x THIS replica has currently observed
# merge(a,b)-> union the add-tags, union the tombstones; x is present iff it has
#              an add-tag that is NOT tombstoned.
class ORSet:
    def __init__(self):
        self.adds = {}        # element -> set of unique tags
        self.tombs = set()    # tombstoned tags (removed adds)
    def add(self, x, tag):    # tag must be globally unique (e.g. f"{replica}:{counter}")
        self.adds.setdefault(x, set()).add(tag)
    def remove(self, x):      # observed-remove: tombstone only the tags we've seen
        for tag in self.adds.get(x, set()):
            self.tombs.add(tag)
    def merge(self, other):   # commutative, associative, idempotent
        for x, tags in other.adds.items():
            self.adds.setdefault(x, set()).update(tags)
        self.tombs |= other.tombs
    def value(self):          # present = has a live (non-tombstoned) add-tag
        return {x for x, tags in self.adds.items() if tags - self.tombs}
```

That's the whole OR-set. The magic is in `value()`: an element is present iff it has at least one add-tag that hasn't been tombstoned. A concurrent add (a *new* tag) survives a remove (which only tombstones the tags it *saw*) — that's the "observed-remove, add-wins" property.

---

## Step 1 — The scenario

Two regions, both serving the same user's cart, partitioned (can't talk to each other). The user is shopping from two devices, one routed to each region.

```
   Start (before partition): cart = { } on both replicas (synced, empty)

   PARTITION begins. The replicas can't communicate.

   region-A actions:           region-B actions:
     add "APPLE"                  add "APPLE"        (concurrent add, same item)
     add "PEAR"                   add "KIWI"
     remove "PEAR"                (nothing about PEAR)

   PARTITION heals. Replicas exchange state and merge.
```

Predict, before computing: what *should* the converged cart contain? The user added APPLE (twice, from two devices — still one item, but both adds are real), PEAR (then removed it in A), and KIWI. The *intended* converged cart is **{ APPLE, KIWI }** — PEAR was removed, everything else the user added is present.

---

## Step 2 — Run it as an OR-set

Use unique tags per add (replica:counter):

```
region-A:  add APPLE -> tag a1;  add PEAR -> tag a2;  remove PEAR -> tombstone {a2}
           A.adds = {APPLE:{a1}, PEAR:{a2}}   A.tombs = {a2}
           A.value() = {APPLE}                 (PEAR's only tag is tombstoned)

region-B:  add APPLE -> tag b1;  add KIWI -> tag b2
           B.adds = {APPLE:{b1}, KIWI:{b2}}   B.tombs = {}
           B.value() = {APPLE, KIWI}

HEAL: merge A and B (both directions):
   adds  = {APPLE:{a1,b1}, PEAR:{a2}, KIWI:{b2}}
   tombs = {a2}
   value = {APPLE, KIWI}        <-- A and B now IDENTICAL
```

**Convergence:** A and B reach the same value ✔. **Correctness:** the value is `{APPLE, KIWI}` — exactly the intent ✔. PEAR is gone (its tag `a2` is tombstoned), and crucially APPLE survived even though it was added concurrently in *both* regions (it has two live tags `a1`, `b1` — either keeps it present). No add was lost; the remove only undid what it observed.

> **The key insight:** the OR-set kept APPLE present through the merge *because* a concurrent add creates a *new* tag that the other region's remove never saw and so never tombstoned. Add-wins is exactly "a concurrent add beats a remove that didn't observe it" — which is the behavior a cart wants.

---

## Step 3 — Now run it as an LWW-register (the footgun)

Model the *whole cart* as a single LWW-register: the value is "the entire item list," and the write with the latest timestamp wins.

```
region-A final write (whole cart): {APPLE}        at timestamp t=105
region-B final write (whole cart): {APPLE, KIWI}  at timestamp t=103

HEAL: LWW keeps the latest timestamp -> t=105 wins -> {APPLE}
   A and B both converge to {APPLE}
```

**Convergence:** A and B reach the same value ✔. **Correctness:** the value is `{APPLE}` — **KIWI is gone** ✘. The user added KIWI in region B, got a confirmation, and it *vanished* on heal — not because of an error, but because region A's whole-cart write had a later timestamp and LWW discarded everything else. **It converged. It lost data. Both true.**

This is the footgun in one example: the LWW *converged perfectly* and *silently ate a real item*. The replicas agree on a wrong answer. The bug isn't the convergence; it's modeling a *set* as a *single last-write-wins value*.

---

## Step 4 — Prove the OR-set's algebra (why it's safe in any order)

Confirm the convergence is *order-independent* (the join-semilattice property). Re-run the merge with the operations applied in a *different* order, or merge B-into-A vs A-into-B, or merge twice. The result is identical every time:

```
merge(A, B) == merge(B, A)                    (commutative)
merge(merge(A,B), C) == merge(A, merge(B,C))  (associative)
merge(A, A) == A                              (idempotent)
```

This is *why* you don't need coordination: order doesn't matter, so the two regions never have to agree on an order. Apply your add/remove/merge in any sequence and you land in the same place — which is the formal content of "strong eventual consistency."

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] You ran the partition-heal scenario as an OR-set and got the converged cart `{APPLE, KIWI}` on *both* replicas — convergence AND the intended value.
- [ ] You can explain *why* APPLE survived a concurrent add-in-both-regions (the two live tags) and PEAR did not (its tag was tombstoned by the observed-remove).
- [ ] You ran the *same* scenario as an LWW-register and showed it converges to `{APPLE}` — silently losing KIWI — and can state "it converged AND it lost data."
- [ ] You demonstrated (by re-ordering the merges) that the OR-set merge is commutative, associative, and idempotent.
- [ ] You can state, in one sentence, why the OR-set is the right type for cart items and LWW is the footgun.

---

## Stretch

- Add **quantity**: model "2 APPLEs in A, 3 APPLEs in B" and show that an OR-set of *(item, add-tag)* pairs (a multiset) converges to 5 APPLEs (both adds count), while an LWW quantity would keep only one. This is the PN-counter/multiset reasoning for quantity.
- Reproduce the **PN-counter-goes-negative footgun**: model "remove APPLE" as a quantity decrement, run a concurrent "add APPLE," and show the count can go negative or wrong — then fix it by using OR-set membership for presence and reserving arithmetic for genuine quantity. The per-field type choice made concrete.
- Drive **1000 add/remove cycles** and count the tombstones. Watch the OR-set's *physical* size grow while its *logical* size stays tiny — the metadata cost (Lecture 2 §2) you'll bound in the mini-project.

---

When this feels comfortable, move to [Exercise 2 — The Automerge active-active cart](exercise-02-automerge-active-active-cart.mjs).
