# Lecture 1 — Eventual Consistency and the Semilattice: Why CRDTs Converge

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can state strong eventual consistency precisely, distinguish state-based from operation-based CRDTs, and *prove* that a CRDT converges by showing its merge forms a join-semilattice — commutative, associative, idempotent.

If you remember one sentence from this entire lecture, remember this one:

> **A CRDT converges because its merge operation is commutative, associative, and idempotent — the exact algebraic conditions under which the order in which updates arrive, and whether they arrive more than once, cannot change the final result. That structure is a join-semilattice, and it is the whole reason eventual consistency can be made *strong* and *coordination-free*.**

Week 1 left the AP corner with a problem: replicas diverge under partition, and the naive fix — last-writer-wins by timestamp — silently discards concurrent writes. Week 2 gave you vector clocks to *detect* that divergence. This lecture gives you the principled *resolution*: data types that merge divergent states correctly, by construction, with a mathematical guarantee of convergence. No consensus, no coordination, no lost data.

---

## 1. From eventual to *strong eventual* consistency

### 1.1 Eventual consistency is a weak promise

Recall Week 1's definition: **eventual consistency** says "if writes stop, all replicas eventually converge." That is a real but *weak* promise. It says nothing about:

- *How* they converge (they might converge to an arbitrary value — last-writer-wins picks one and discards the rest).
- *Whether data is lost* in the process (LWW loses concurrent writes).
- *What you read* before convergence (anything, in any order).

A system can be eventually consistent and still lose your shopping-cart items, because "converge" doesn't require "converge to a value that preserves everyone's updates." Eventual consistency is the floor; it is not enough.

### 1.2 Strong eventual consistency (SEC) is the strong promise

Shapiro et al. define the stronger guarantee that CRDTs provide. **Strong eventual consistency** has two parts:

1. **Eventual delivery:** an update applied at one correct replica is eventually applied at all correct replicas.
2. **Strong convergence:** any two correct replicas that have applied **the same set of updates** are in **the same state** — byte for byte, immediately, with *no conflict-resolution step.*

The crucial upgrade over plain eventual consistency is "the same set of updates ⟹ the same state, by construction." There is no moment where replicas have seen the same updates but still disagree and must run a reconciliation protocol. Convergence is not *achieved* by resolving conflicts; it is *guaranteed* because the data type's merge cannot produce a conflict in the first place. That is what "conflict-free" in CRDT means: not "conflicts are resolved" but "conflicts are *impossible* by design."

> **The payoff:** SEC is **available under partition** (no coordination needed — it's a pure AP technique) yet gives a *predictable* converged value that *preserves all updates*. It is the strongest practical thing you can have on the AP side of CAP. This is why CRDTs are the backbone of multi-region active-active systems (the C22 capstone's cart) and of local-first collaborative apps (Automerge, Yjs).

---

### 1.3 The problem CRDTs solve, restated from Week 1

To anchor the motivation, replay the AP scenario from Week 1's partitioned register. Two replicas of a shopping cart accept writes during a partition:

```
Replica A:  cart = {milk}        (added during partition)
Replica B:  cart = {eggs}        (added during partition)
partition heals -> the replicas must reconcile A's {milk} and B's {eggs}
```

Week 1's register used **last-writer-wins** to reconcile: pick one by timestamp, discard the other. Result: the cart is `{milk}` *or* `{eggs}`, and a customer's item silently vanished. Week 2 gave you vector clocks, which can *detect* that these two writes were concurrent (incomparable vectors) — but detection alone doesn't tell you what to *do*.

A CRDT is the answer to "what to do": model the cart as a **set CRDT** whose merge is *union*, and the reconcile is `{milk} ⊔ {eggs} = {milk, eggs}` — both items preserved, no coordination, guaranteed convergence. The customer keeps both items. That single example — LWW loses an item, a set CRDT keeps both — is the whole motivation for the week. Everything below is the machinery that makes "the merge is union and it always converges" rigorous and general.

## 2. Two flavors: state-based and operation-based

There are two ways to build a CRDT, and they require different things from the network.

The names are worth pinning down because they're easy to swap: **CvRDT = Convergent = state-based** (you converge by merging *states*); **CmRDT = Commutative = op-based** (you converge because *operations* commute). The "v" is for conVergent, the "m" is for coMmutative. Keep them straight and the literature stops being confusing.

### 2.1 State-based (CvRDT — Convergent)

Each replica holds a **state**. Replicas periodically send their *entire state* to each other and **merge** the received state into their own via a `merge` function. The value is read from the local state.

- **The network only needs eventual, at-least-once, unordered delivery** (gossip). Messages can be lost, reordered, and duplicated — *because* merge is idempotent and commutative, none of that matters. This is the great robustness advantage: state-based CRDTs work over the flakiest possible network.
- **The cost is bandwidth:** shipping the whole state on every merge is expensive for large states. (Delta-CRDTs, Lecture 2, fix this by shipping only the change.)

```python
# The shape of every state-based CRDT.
class CvRDT:
    def update(self, ...):       # apply a local update to self.state
        ...
    def merge(self, other):      # join: self.state = LUB(self.state, other.state)
        ...                      # MUST be commutative, associative, idempotent
    def value(self):             # read the current value from self.state
        ...
```

### 2.2 Operation-based (CmRDT — Commutative)

Each replica **broadcasts each operation** (not the whole state). Every replica applies received operations to its local state. The value is read from the local state.

- **The operations must commute** — applying them in any order yields the same state. But because operations are not idempotent in general, **the network must deliver each operation exactly once, in causal order** (reliable causal broadcast). This is a *stronger* delivery requirement than state-based.
- **The benefit is small messages:** you ship the operation ("add X"), not the whole set. Cheaper bandwidth, stronger delivery requirement.

### 2.3 Which to pick

| Dimension | State-based (CvRDT) | Operation-based (CmRDT) |
|---|---|---|
| What's shipped | The whole state (or a delta) | Each operation |
| Network requirement | Eventual, unordered, at-least-once (gossip) | Reliable, exactly-once, causal-order delivery |
| Robustness | Very high — tolerates loss/dup/reorder | Lower — needs a reliable causal broadcast layer |
| Bandwidth | High (whole state), unless delta-based | Low (just the op) |
| Typical use | Geo-replication over flaky links (Riak) | In-cluster with a reliable broadcast (some collab editors) |

The two are theoretically equivalent in power (you can emulate one with the other), but the *operational* tradeoff is real: state-based is robust-but-fat, op-based is lean-but-demanding. Riak and Redis CRDTs are state-based (delta-optimized) because geo-replication networks are flaky; many in-process collaborative editors are op-based because they have a reliable channel. **This lecture and the labs focus on state-based**, because the convergence proof (the semilattice) is cleanest there and the robustness is the bigger win for the AP geo-replication use case C22 targets.

---

## 3. The convergence proof: a join-semilattice

Here is the mathematical heart. A state-based CRDT converges **if and only if** its states form a **join-semilattice** under merge. Let's build that up.

### 3.1 The three algebraic laws

The merge function must satisfy three laws, for all states `x`, `y`, `z`:

1. **Commutativity:** `merge(x, y) = merge(y, x)`. *The order in which two states are merged doesn't matter.*
2. **Associativity:** `merge(merge(x, y), z) = merge(x, merge(y, z))`. *The grouping of merges doesn't matter.*
3. **Idempotence:** `merge(x, x) = x`. *Merging a state with itself (or re-merging a duplicate) changes nothing.*

These three laws are *exactly* the conditions under which **the order and multiplicity of updates cannot affect the result.** Think about what the network does to your messages: it reorders them (commutativity handles that), it batches/regroups them (associativity), and it duplicates them (idempotence). A merge that obeys all three is *immune* to everything an unreliable network can do to your gossip messages. That immunity is precisely why state-based CRDTs need only eventual, unordered, at-least-once delivery.

### 3.2 The partial order and the least upper bound

These three laws are equivalent to saying the states form a **join-semilattice**:

- Define a **partial order** `x ≤ y` to mean `merge(x, y) = y` (i.e., `y` already "contains" `x`).
- Then `merge` is the **least upper bound (join, ⊔)** of two states: the smallest state that is `≥` both. `merge(x, y) = x ⊔ y`.
- The semilattice is **monotonic**: every update only moves a replica *up* the lattice (`x ≤ update(x)`), and merge only moves *up* (`x ≤ x ⊔ y` and `y ≤ x ⊔ y`).

```
A G-set (grow-only set) semilattice over {a, b}:

            {a, b}              <- top (least upper bound of {a} and {b})
           /      \
        {a}        {b}
           \      /
             {}                 <- bottom (empty set)

merge = set union = least upper bound. Adding only moves UP. Two replicas, one with
{a} and one with {b}, both merge to {a,b} -- the join -- regardless of order. That
is convergence, and it is just "take the LUB in the lattice."
```

Because every replica only climbs the lattice (updates and merges are monotonic, never descending), and because any two states have a unique least upper bound, **all replicas that have seen the same set of updates compute the same join and land on the same lattice point.** That is strong convergence, proven. There is no possible reordering or duplication that lands two replicas on different points, because the LUB is unique.

### 3.3 Why "conflict-free" is the right name

A conflict, in a divergent-replica system, is "two replicas disagree and we must pick." In a semilattice there is *no picking*: there is always a unique LUB that is `≥` both states, and that LUB *is* the merged state. The lattice structure means a "conflict" (two incomparable states) always has a well-defined resolution (their join) that *includes both*. A G-set with `{a}` and `{b}` doesn't have to choose between `a` and `b` — the join is `{a, b}`, which keeps both. That is the antidote to last-writer-wins: instead of choosing a winner and discarding a loser, you take the join and keep everything. The data type's *structure* makes conflicts impossible, which is why it's "conflict-free."

---

## 4. A worked convergence: the G-counter

Make it concrete with the simplest non-trivial CRDT, the **grow-only counter (G-counter)**, which you implement in Exercise 2.

The state is a **map from replica-id to a per-replica count.** Each replica only increments *its own* entry. The value is the sum of all entries. The merge is element-wise max.

```python
class GCounter:
    def __init__(self, replica_id, num_replicas):
        self.id = replica_id
        self.counts = [0] * num_replicas

    def increment(self, by=1):
        self.counts[self.id] += by          # only touch MY entry -> no conflict

    def value(self):
        return sum(self.counts)             # value = total across replicas

    def merge(self, other):
        # element-wise MAX -- the join. Each replica's true count is the max seen.
        self.counts = [max(a, b) for a, b in zip(self.counts, other.counts)]
```

Why does element-wise max converge? Because each replica's *own* entry only ever grows (monotonic), so the *true* value of replica `i`'s entry is the maximum any replica has seen for it. Taking the element-wise max is taking the join: the result is `≥` both inputs in every component, and it's the *least* such state. Verify the three laws:

- **Commutative:** `max(a, b) = max(b, a)` componentwise. ✓
- **Associative:** `max(max(a, b), c) = max(a, max(b, c))`. ✓
- **Idempotent:** `max(a, a) = a`. ✓

So three replicas that each incremented their own entry during a partition will, after merging in *any order* with *any duplicates*, all hold the same element-wise-max vector and thus the same sum. Three replicas increment to `[5,0,0]`, `[0,3,0]`, `[0,0,2]`; all merges yield `[5,3,2]`, value `10`. No increment is lost — unlike LWW, which would keep only one. That is the entire promise of the week, demonstrated on the simplest CRDT.

---

## 4b. A worked partition-and-heal trace

Watch three replicas of a G-counter survive a partition. Each is a click-counter on a 3-region active-active deployment; during a partition each region keeps counting locally.

| Step | R1 state | R2 state | R3 state | values |
|---|---|---|---|---|
| start (synced) | `[0,0,0]` | `[0,0,0]` | `[0,0,0]` | 0,0,0 |
| partition; each counts | `[5,0,0]` | `[0,3,0]` | `[0,0,2]` | 5,3,2 |
| heal: R1 ⊔ R2 | `[5,3,0]` | `[5,3,0]` | `[0,0,2]` | 8,8,2 |
| R2 ⊔ R3 | `[5,3,0]` | `[5,3,2]` | `[5,3,2]` | 8,10,10 |
| R1 ⊔ R3 | `[5,3,2]` | `[5,3,2]` | `[5,3,2]` | **10,10,10** |

After the dust settles every replica holds `[5,3,2]`, value **10** — the *true total* of all clicks across all regions, with not a single increment lost. Now do the merges in a *different* order, or merge some twice: the answer is *still* `[5,3,2]`. That invariance under reordering and duplication is the semilattice property, and it is why this works over a gossip network that loses, reorders, and duplicates messages. Contrast with LWW, which would have kept only *one* region's count (say 5) and silently discarded the other 5 clicks. The G-counter keeps all 10. **That difference — 10 vs 5 — is the entire value proposition of CRDTs over LWW, in one number.**

## 4c. The PN-counter: composing two G-counters

A G-counter only grows. What if you need *decrements* (a cart item-count that can go down, a like that can be un-liked)? You cannot just allow decrements on a G-counter — `max` would break (a decrement isn't monotonic). The elegant fix is a **PN-counter**: hold **two** G-counters, `P` (increments) and `N` (decrements), and define the value as `sum(P) - sum(N)`.

```python
class PNCounter:
    def __init__(self, replica_id, n):
        self.P = GCounter(replica_id, n)   # increments
        self.N = GCounter(replica_id, n)   # decrements

    def increment(self, by=1): self.P.increment(by)
    def decrement(self, by=1): self.N.increment(by)   # a decrement is a +1 to N
    def value(self):          return self.P.value() - self.N.value()
    def merge(self, other):
        self.P.merge(other.P)              # merge each component G-counter
        self.N.merge(other.N)
```

This is the **composition principle** that runs through the whole CRDT zoo: build complex CRDTs by combining simpler ones whose semilattice properties you've already proven. The PN-counter converges because each component is a G-counter (which converges), and the difference of two converged values is itself well-defined. Lecture 2's OR-set and CRDT *maps* are the same idea taken further — compose proven CRDTs and the composite inherits convergence. You rarely prove a CRDT from scratch; you compose it from semilattices you trust.

## 4d. Verifying the three laws, explicitly, on a G-set

Do not take "merge is commutative/associative/idempotent" on faith — verify it the way Exercise 3 will, on the grow-only set whose merge is union. Let `x = {a}`, `y = {b}`, `z = {a, c}`.

- **Commutativity:** `x ∪ y = {a,b}` and `y ∪ x = {a,b}`. Equal. ✓ (Set union is commutative for any sets.)
- **Associativity:** `(x ∪ y) ∪ z = {a,b} ∪ {a,c} = {a,b,c}`; `x ∪ (y ∪ z) = {a} ∪ {a,b,c} = {a,b,c}`. Equal. ✓
- **Idempotence:** `x ∪ x = {a} = x`. ✓

Three small checks, and you have *proven* the G-set converges — no matter how a gossip network reorders, batches, or duplicates the merges. This is the entire verification burden for a state-based CRDT, and it is why CRDTs are *trustworthy*: convergence isn't an empirical hope you test with fuzzing, it's an algebraic fact you check with three equations. (You still property-test it, in Exercise 3, to catch *implementation* bugs — but the *design* is provably correct.)

The 2P-set (two-phase set) shows the subtlety that motivates the OR-set next lecture: a 2P-set allows removes by keeping a second G-set of tombstones, with value = `added − removed`. It converges (two G-sets, both semilattices) — but it has a nasty semantic: **once you remove an element, you can never re-add it** (the tombstone is permanent and `added − removed` stays empty). That "remove is forever" footgun is exactly what the OR-set fixes with per-add unique tags, and it's why production set CRDTs are OR-sets, not 2P-sets. Convergence is necessary but not sufficient; the *semantics* of the merge must also match what users expect, and "I removed an item and now can't ever re-add it" is a semantics nobody wants.

## 4e. A checklist for designing your own CRDT

When you need a CRDT that isn't in the catalog, this is the senior-engineer procedure:

1. **Identify the state and the read.** What does each replica store, and how do you compute the value from it?
2. **Make updates monotonic.** Every local update must move *up* the lattice (add, never remove-in-place; increment a per-replica counter, never overwrite). If an update isn't naturally monotonic (a decrement), *encode* it monotonically (PN-counter's separate N counter).
3. **Define merge as the least upper bound.** Element-wise max for counters, union for sets, etc.
4. **Verify the three laws** (commutative, associative, idempotent) — by algebra, then by property test.
5. **Check the semantics, not just convergence.** Does the converged value mean what users expect? (The 2P-set converges but has the "remove is forever" trap.)
6. **Check the boundary (§5).** Does your data need a global invariant a merge can't enforce? If so, a CRDT is the wrong tool — you need coordination.

Run that checklist and you can build a correct CRDT for novel state. Skip step 5 or 6 and you ship something that converges to a value that's either surprising or invalid.

## 5. The limit: what a semilattice cannot do

CRDTs are not magic, and the semilattice structure tells you *exactly* their limit. A join only ever moves *up* the lattice and *includes more*. That means CRDTs are great at "monotonic" facts — a set that grows, a counter that accumulates, a flag that gets set — but they **cannot enforce a global invariant that requires saying "no" to a local update.**

Consider "this username must be globally unique" or "this account balance must never go negative" or "exactly 100 seats can be sold." No local merge can enforce these, because two replicas can *each* locally accept a conflicting update (both register "alice"; both sell the 100th seat) and the merge — being a join that *includes both* — will happily keep both, violating the invariant. The semilattice's superpower (never lose an update by including both) is exactly its limitation (it cannot reject a conflicting update to preserve a global constraint).

> **The boundary, stated precisely:** CRDTs work for state whose correctness is preserved under *merge-includes-both*. They fail for invariants that require *coordination to reject* conflicting updates — and those require consensus (Week 2's Raft) or a single writer. **Knowing which side of this line your data is on is the senior design skill of the week.** A cart's contents? CRDT (merging items is fine). Unique seat assignment? Consensus (you must reject the second sale). Getting this wrong — using a CRDT where you needed coordination — produces a system that converges happily to an *invalid* state, which is worse than not converging.

A decision table for the line, with examples you'll meet in the capstone:

| Data / operation | Merge-includes-both OK? | Verdict |
|---|---|---|
| Shopping cart contents (add items) | Yes — a cart with both items is fine | **CRDT** (OR-set) |
| Like / view counter | Yes — sum all increments | **CRDT** (G/PN-counter) |
| Collaborative document text | Yes — interleave both edits | **CRDT** (sequence CRDT) |
| User presence / online set | Yes — union of who's online | **CRDT** (OR-set) |
| Unique username registration | No — must reject the second | **Consensus** (single writer) |
| Account balance ≥ 0 invariant | No — must reject overdraft | **Consensus** (or escrow/reservation) |
| "Exactly 100 seats" inventory | No — must reject the 101st | **Consensus** (Week 2 leases per SKU) |
| Bank-transfer atomicity | No — needs a transaction | **Consensus** / saga |

The pattern: if two replicas can *both* locally accept updates that, when merged, *violate a constraint*, you need coordination. If merging just *accumulates* and any accumulation is valid, you can use a CRDT and stay available under partition. The capstone splits exactly this way: `cart-service` is a CRDT (AP, active-active), `inventory-service` uses leases (CP, single-writer-per-SKU) precisely because "don't oversell" is a reject-the-conflict invariant a CRDT cannot enforce.

---

## 5b. Where SEC sits on Week 1's consistency lattice

Connect this back to the Week 1 lattice (linearizable → sequential → causal → eventual). Strong eventual consistency is a *refinement of eventual consistency*, sitting just above plain eventual:

| Model | Promise | Coordination | Loses concurrent writes? |
|---|---|---|---|
| Linearizable | One real-time order | High (CP) | N/A (one order, no concurrency) |
| Causal+ | Causal order preserved | Medium | Depends on resolution |
| **Strong eventual (CRDT)** | Same updates ⟹ same state, preserving all | **None (AP)** | **No** — merge keeps all |
| Eventual (LWW) | Eventually converges | None (AP) | **Yes** — LWW discards |

The key column is the last one. Plain eventual consistency *with LWW* converges but loses concurrent writes. **Strong eventual consistency with a CRDT converges AND preserves every update.** Both are AP (no coordination), so they sit at the same place on the *availability* axis — but they are worlds apart on *correctness*. CRDTs are how you get the availability of eventual consistency without the data loss. That is why "we're eventually consistent" should always prompt the follow-up "with LWW or with CRDTs?" — the two have identical availability and opposite data-loss behavior.

## 5c. Three misconceptions to kill

- **"Eventually consistent means I'll lose some writes; that's the tradeoff."** False for CRDTs. Plain LWW loses concurrent writes; a CRDT *preserves* them. The data loss is a property of the *resolution strategy* (LWW), not of eventual consistency itself. Choosing a CRDT removes the loss while keeping the availability.
- **"CRDTs need a special database."** No — a CRDT is a *data type*, a discipline you can implement in your application over any store that can hold its state. Riak/Redis/Antidote provide them built-in, but you can (and in the lab, will) implement a correct CRDT in plain Python over any key-value store. The semilattice is in the *merge function*, not the database.
- **"If it converges, it's correct."** Dangerous. A CRDT converges to a *well-defined* value, but if you chose the wrong CRDT for your semantics (e.g., a CRDT where you needed coordination), it can converge to a value that *violates your invariant* — two users both got the unique username, and the merge kept both. Convergence is necessary, not sufficient; the converged value must also be *semantically valid*, which is the §5 boundary.

## 5d. The op-based vs state-based proof obligation

A subtle but important distinction for when you build your own: the *proof obligation* differs between the two flavors.

- **State-based:** you must prove `merge` is **commutative, associative, idempotent** (a join-semilattice). Delivery can be arbitrary.
- **Op-based:** you must prove operations **commute** (for concurrent ops), and you must *assume* the delivery layer provides **exactly-once, causal-order** broadcast. Idempotence is *not* required of the op itself — instead the delivery layer guarantees no duplicates.

This is why state-based CRDTs are often preferred in hostile networks: the proof obligation (three algebraic laws on merge) buys you immunity to *any* delivery anomaly, so you do not have to build and trust a reliable causal-broadcast layer. Op-based pushes some of the burden onto the network. When you design a CRDT, decide this first — it determines what you must prove and what you must demand of the transport. The lab uses state-based precisely so the only thing you must verify is the three laws (Exercise 3 property-tests exactly those).

## 6. Recap

You should now be able to:

- State **strong eventual consistency**: eventual delivery + strong convergence (same updates ⟹ same state, by construction, no conflict resolution).
- Distinguish **state-based (CvRDT)** — ship whole state, needs only eventual unordered delivery — from **operation-based (CmRDT)** — ship operations, needs reliable causal delivery.
- Prove convergence by showing merge is **commutative, associative, idempotent** — a **join-semilattice** where merge is the least upper bound and updates/merges are monotonic.
- Explain why those three laws make a CRDT immune to network reordering, batching, and duplication, and why "conflict-free" means conflicts are *impossible by construction*, not *resolved*.
- Name the **limit**: CRDTs cannot enforce global invariants that require rejecting a conflicting update (uniqueness, non-negativity, fixed capacity) — those need coordination.

One last frame to carry into the zoo: a CRDT is best understood as **"a data structure that made its merge function a join."** Everything else — the tags, the tombstones, the version vectors — is bookkeeping in service of making `merge` commutative, associative, and idempotent. When you read a new CRDT next lecture, find its `merge` first and ask "is this a least upper bound?" If yes, it converges, and the rest is details about *what value* the lattice point represents. The semilattice is the lens; the zoo is what you see through it.

## 6b. The one-sentence test for your design reviews

When a teammate proposes "let's make this eventually consistent" or "let's just use last-writer-wins," deploy this:

> *"Can two replicas concurrently make updates that both matter? If yes, last-writer-wins will silently lose one of them — so either prove only one update can ever happen concurrently, or use a CRDT whose merge keeps both. And if the two updates can together violate an invariant, neither works — you need coordination."*

That sentence forces the three decisions of this week into the open: (1) is there real concurrency? (2) does LWW lose data here? (3) is there an invariant that even a CRDT can't hold? Most "eventually consistent" proposals that ship bugs skipped one of those questions. Asking them out loud is the entire senior contribution.

## 6c. A note on testing CRDTs

Because convergence is an *algebraic* property, CRDTs are unusually testable, and you should exploit that. **Property-based testing** (Exercise 3) is the right tool: generate random sequences of updates and merges, in random orders with random duplicates, and assert that all replicas converge to the same value. The three laws translate directly into three properties:

- `merge(a, b) == merge(b, a)` (commutativity)
- `merge(merge(a, b), c) == merge(a, merge(b, c))` (associativity)
- `merge(a, a) == a` (idempotence)

A CRDT that passes thousands of randomized property-test cases for all three is *very* likely correct, because those three laws are *sufficient* for convergence — there's no fourth thing that can go wrong at the merge level. (Implementation bugs — a typo in the merge — are exactly what the property test catches.) This is a rare luxury in distributed systems: a correctness property you can both *prove* by algebra and *check* by fuzzing. Use both.

Next: the CRDT zoo in full — G-counter, PN-counter, OR-set, LWW/MV-register — the metadata-growth problem, and how Riak, Redis, and AntidoteDB run CRDTs in production. Continue to [Lecture 2 — The CRDT Zoo, Metadata, and Production](./02-the-crdt-zoo-metadata-and-production.md).

---

## References

- *Conflict-free Replicated Data Types* — Shapiro, Preguiça, Baquero & Zawirski (2011): <https://inria.hal.science/inria-00609399/document>
- *A comprehensive study of CRDTs* (tech report) — Shapiro et al. (2011): <https://inria.hal.science/inria-00555588/document>
- *Designing Data-Intensive Applications*, Ch. 5 — Kleppmann (2017).
- *Managing Update Conflicts in Bayou* — Terry et al. (SOSP 1995).
- *crdt.tech* — Marc Shapiro's CRDT portal (catalog, papers, talks): <https://crdt.tech/>
- *Why Logical Clocks are Easy* — Baquero & Preguiça (ACM Queue, 2016): <https://queue.acm.org/detail.cfm?id=2917756>
- *Delta State Replicated Data Types* — Almeida, Shoker & Baquero (2016): <https://arxiv.org/abs/1603.01529>
- *Dotted Version Vectors* — Preguiça et al.: <https://arxiv.org/abs/1011.5808>
