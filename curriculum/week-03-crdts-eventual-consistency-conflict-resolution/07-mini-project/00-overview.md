# Mini-Project — The OR-Set Cart: Surviving a 3-Way Partition Heal

> Build an OR-set CRDT shopping cart that three replicas can edit independently during a partition, then prove it **converges** after the partition heals — with *every* concurrent add preserved (add-wins on concurrent remove/re-add), *no* last-writer-wins data loss — and **measure** the metadata cost as the operation count grows. This is the AP counterpart to Week 2's CP Raft register, and the direct ancestor of the capstone's active-active `cart-service`.

This is the project where the week's theory becomes a running, tested artifact. You will *demonstrate* the "it converged" promise: three replicas, different concurrent updates, merge in any order, identical result, nothing lost. And you will *measure* the metadata curve that is the CRDT world's central tax — and (stretch) bend it back down with tombstone reclamation.

**Estimated time:** ~12 hours, split across Thursday, Friday, and Saturday in the suggested schedule.

**Compounds forward:** This cart is the seed of the capstone's `cart-service` (Rust in the capstone; Python here is fine — the CRDT logic is identical). In Phase 4 (Week 20), you promote this exact design to active-active across two Kind regions, partition them for five minutes, heal, and verify convergence. The OR-set you build now is the data structure that makes that demo work.

---

## What you will build

A Python package `orset-cart` with three deliverables:

1. **`cart/` package** — an OR-set-backed shopping cart supporting `add(item)`, `remove(item)`, `quantity(item, n)` (using a PN-counter per item), `value()` (the current cart), and `merge(other)`. The merge must be commutative, associative, and idempotent (you'll property-test it).
2. **A partition simulator + 3-way heal harness** — three replicas, a controllable partition, and a heal that merges them in a *shuffled, duplicated* order, asserting convergence with all concurrent updates preserved.
3. **A metadata measurement** — run N operations and record the live-item count vs the add-set/remove-set sizes (and approximate bytes), producing the growth curve from Lecture 2 §4.5.

By the end you have ~300–400 lines of tested Python that any future Crunch Mesh week can read to recall "what an AP-safe cart looks like," plus a `RESULTS.md` with the convergence proof and the metadata curve.

---

## Why a cart, and why an OR-set

A shopping cart is the canonical CRDT use case because:

- It is **AP-friendly**: a customer must be able to add items even if their region is partitioned from the others (you don't want "can't add to cart, try later" — that's lost revenue).
- Concurrent adds **must all survive**: if a customer adds an item on their phone and another on their laptop offline, both must be in the cart after sync. LWW would lose one.
- The **add-wins** remove semantic is exactly right: if you remove an item but concurrently re-added it on another device, keeping it (add-wins) matches user intent.

An OR-set provides all three. A naive set with LWW would lose concurrent adds; a 2P-set would make "remove is forever" (you couldn't re-add a removed item). The OR-set's per-add unique tags are precisely what the cart needs.

---

## Package layout

```
orset-cart/
├── README.md                   # how to run + your RESULTS summary
├── cart/
│   ├── __init__.py
│   ├── orset.py                # the OR-set CRDT (reuse/extend Exercise 2)
│   ├── pncounter.py            # PN-counter for per-item quantities
│   └── cart.py                 # the Cart: composes OR-set (items) + PN-counter (qty)
├── harness/
│   ├── partition_heal.py       # 3-replica partition + shuffled/duplicated heal
│   └── metadata.py             # operation-count vs metadata-size measurement
├── tests/
│   ├── test_convergence.py     # 3 replicas converge; add-wins; no data lost
│   ├── test_semilattice.py     # property tests: commutative/associative/idempotent
│   └── test_quantity.py        # PN-counter quantities converge
└── RESULTS.md                  # convergence proof + metadata growth curve
```

---

## Deliverable 1 — the cart CRDT

The cart composes two CRDTs (Lecture 1 §4c composition principle):

- **An OR-set** for *which items* are in the cart (add/remove with add-wins).
- **A PN-counter per item** for the *quantity* of each item (increment/decrement, converges).

```python
class Cart:
    """A CRDT shopping cart: OR-set of items + a PN-counter per item for quantity."""

    def __init__(self, replica_id, num_replicas):
        self.id = replica_id
        self.n = num_replicas
        self.items = ORSet(replica_id)                 # which items are present
        self.qty = {}                                  # item -> PNCounter

    def add(self, item, n=1):
        self.items.add(item)
        self.qty.setdefault(item, PNCounter(self.id, self.n)).increment(n)

    def remove(self, item):
        self.items.remove(item)
        # Note: quantity counter stays (CRDTs don't delete); value() ignores
        # quantities of items not currently in the OR-set.

    def set_quantity_delta(self, item, delta):
        c = self.qty.setdefault(item, PNCounter(self.id, self.n))
        c.increment(delta) if delta >= 0 else c.decrement(-delta)

    def value(self):
        """Return {item: quantity} for items currently in the OR-set."""
        present = self.items.value()
        return {item: max(0, self.qty[item].value()) for item in present
                if item in self.qty}

    def merge(self, other):
        self.items.merge(other.items)
        for item, counter in other.qty.items():
            self.qty.setdefault(item, PNCounter(self.id, self.n)).merge(counter)
```

The merge must satisfy the three semilattice laws — your `test_semilattice.py` verifies this by property testing (the Exercise 3 pattern, in Python with `random`).

---

## Deliverable 2 — the 3-way partition heal harness

This is the headline demonstration. Three replicas (regions) edit the cart independently during a partition, then heal:

```python
def three_way_partition_heal():
    A, B, C = (Cart(i, 3) for i in range(3))

    # All start synced with one item.
    A.add("milk"); B.merge(A); C.merge(A)

    # PARTITION: each region edits independently, concurrently.
    A.add("eggs")                  # region A adds eggs
    B.add("bread", n=2)            # region B adds 2 bread
    C.add("milk")                  # region C adds more milk (concurrent)
    C.remove("milk")               # ...then C removes milk it observed
    # Meanwhile A still has milk (never saw C's remove) -> add-wins should keep it.

    # HEAL: merge in a SHUFFLED, DUPLICATED order to stress the semilattice laws.
    replicas = [A, B, C]
    snaps = [r_copy(r) for r in replicas]
    schedule = shuffled_duplicated_pairs(len(replicas))
    for (i, j) in schedule:
        replicas[i].merge(snaps[j])
    # ... one more full round to fixpoint ...

    # ASSERT: all three converge to the SAME value, with every concurrent add kept.
    assert A.value() == B.value() == C.value()
    assert set(A.value().keys()) == {"milk", "eggs", "bread"}   # nothing lost
    print("CONVERGED:", A.value())
```

The harness must:
- Merge in a **shuffled, duplicated** order (proving commutativity + associativity + idempotence at once).
- Assert **all three replicas converge** to an identical value.
- Assert **every concurrent add survived** (no LWW-style loss) and **add-wins** resolved the concurrent milk remove/re-add correctly.

---

## Deliverable 3 — the metadata measurement

Run an escalating number of add/remove operations and record the metadata growth:

```python
def measure_metadata():
    cart = Cart(0, 1)
    print(f"{'ops':>8} {'live':>6} {'adds':>7} {'removes':>8} {'approx_bytes':>13}")
    ops = 0
    for target in [10, 100, 1000, 10000]:
        while ops < target:
            item = f"item-{ops % 20}"          # 20 distinct items, churned
            cart.add(item)
            if ops % 3 == 0:
                cart.remove(item)
            ops += 1
        live = len(cart.value())
        adds = len(cart.items.adds)
        removes = len(cart.items.removes)
        approx_bytes = (adds + removes) * 24    # rough per-tag estimate
        print(f"{ops:>8} {live:>6} {adds:>7} {removes:>8} {approx_bytes:>13}")
```

The expected shape (Lecture 2 §4.5): **live items stays small (~tens) while adds/removes grow linearly with total operations.** Record this table in `RESULTS.md` and write one paragraph on what it means for a long-lived cart and which mitigation (delta-CRDTs, reclamation) you'd apply.

---

## Rules

- **You may** read the lectures, the Shapiro CRDT paper, and the Riak/Redis CRDT docs.
- **You must not** use a third-party CRDT library — implement the OR-set and PN-counter yourself. Standard library only (plus `pytest` for tests).
- **You must not** use last-writer-wins anywhere in the cart's item or quantity logic. If `grep -rn "timestamp" cart/` finds LWW-style resolution on items, you've defeated the project's purpose.
- Python 3.12+. `pytest` green.
- The convergence test must merge in a **shuffled, duplicated** order and assert **no concurrent add was lost**.

## Acceptance criteria

- [ ] A public GitHub repo named `c22-week-03-orset-cart-<yourhandle>`.
- [ ] `pytest` passes, including:
  - `test_convergence.py`: 3 replicas converge to an identical value after a shuffled/duplicated heal, with every concurrent add preserved and add-wins resolving the concurrent milk remove/re-add.
  - `test_semilattice.py`: property tests asserting the cart's merge is commutative, associative, and idempotent over random states.
  - `test_quantity.py`: PN-counter quantities converge correctly (including a concurrent increment/decrement).
- [ ] `python3 harness/partition_heal.py` prints the converged cart `{milk, eggs, bread}` and the equality of all three replicas.
- [ ] `python3 harness/metadata.py` prints the growth table; `RESULTS.md` records it with a paragraph on metadata cost.
- [ ] No LWW on items/quantities (`grep` is clean).
- [ ] Committed and pushed.

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **OR-set correctness** | 25 | Unique tags per add; add-wins on concurrent remove/re-add; union merge; re-add after remove works. |
| **Convergence demonstration** | 25 | 3 replicas converge to identical value under shuffled+duplicated merge; every concurrent add preserved. |
| **Semilattice property tests** | 20 | Commutative/associative/idempotent verified by property testing; tests actually bite. |
| **Quantity (PN-counter) composition** | 15 | Per-item PN-counters converge; concurrent inc/dec correct; quantities compose cleanly with the OR-set. |
| **Metadata measurement** | 10 | The growth table is produced and interpreted; the curve matches the lecture's shape. |
| **Hygiene** | 5 | No LWW on items; clear README/RESULTS; no junk checked in. |

**90+** is portfolio-grade and ready to grow into the capstone's `cart-service`. **70–89** works but has a soft add-wins or a convergence test that doesn't shuffle/duplicate. **Below 70** usually means LWW crept into the item logic or the merge isn't a true join — fix that first; it's the whole point.

## Stretch goals

- **Tombstone reclamation.** Track a version vector of what every replica has observed; once a remove is causally stable (seen by all), GC its tombstones. Re-run the metadata measurement and **watch the curve bend back down** after a sweep — the most satisfying graph of the week.
- **Delta-CRDT sync.** Implement delta-state sync (ship only the change since last sync, not the whole state) and measure the bandwidth saving versus full-state gossip on each merge.
- **Two-region active-active preview.** Run two carts in separate processes, sync them over a socket, partition (stop syncing) for a bit, heal, and confirm convergence over a real (if local) network. This is the literal Week 20 capstone demo, built six weeks early.
- **A property-based fuzzer.** Generate random sequences of add/remove/merge across replicas and assert convergence + no-loss after every run. If it ever fails, you found a real bug.

## How this connects to the rest of C22

- **Week 4+ (services)** will wrap this cart logic in an actual service with a gRPC contract — the CRDT is the *state*, the service is the *shell*.
- **Phase 4 (Week 19–20, multi-region)** promotes this exact cart to active-active across two regions, with a real partition-and-heal drill. The OR-set you build now is that drill's data structure.
- **The capstone** ships `cart-service` (Rust) as an OR-set CRDT, active-active across two regions, demoed converging across a simulated partition. This mini-project is that service's brain, prototyped in Python.

When you've finished, push the repo and take the [quiz](../05-quiz.md).
