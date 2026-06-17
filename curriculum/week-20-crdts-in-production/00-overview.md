# Week 20 — CRDTs in Production and Conflict Resolution

Welcome to the week eventual consistency stops being a slogan and becomes a guarantee you can prove. Last week you put the system in two regions and chose, deliberately, to keep a *single* write path — read-local/write-primary — precisely so you would never have to answer the question active-active forces: when both regions accept a write to the same data, who wins? You dodged that question by having one primary. This week you stop dodging it. You promote the cart to genuinely **active-active**, both regions accepting writes, partition them, heal them — and the cart **converges with no lost updates**, something a single primary with failover can never give you, because a single primary that's gone *is* lost updates (the RPO from last week).

The tool that makes this possible is the **CRDT** — the Conflict-free Replicated Data Type. You met the theory in Week 3: state-based vs operation-based, G-counters, PN-counters, OR-sets, LWW-registers, the *convergent* guarantee. That week was a Rust shopping-cart toy proving convergence after a simulated partition heal. This week is the same idea, **in production**, with the stacks teams actually run in 2026 — **Automerge** and **Yjs** for rich collaborative state, **Redis with CRDT (Active-Active) databases** for counters and sets at the data tier — and the harder, more honest question the syllabus puts at the center: **not "can a CRDT converge" (yes) but "is the value it converges to the one your users wanted."**

The one sentence to internalize before you read another line: **a CRDT guarantees the replicas agree; it does not guarantee they agree on something correct.** Last-write-wins (LWW) converges beautifully and silently eats data — two users edited the same field, both edits were real, and LWW keeps one and discards the other, *forever*, with no error. A PN-counter converges and *keeps every increment* — but if you model "remove item from cart" as "decrement quantity" on a counter that another replica already removed, you can drive the count negative. The convergence is free; **choosing the right CRDT for the right field so that the converged value is the *intended* one is the entire engineering of this week.** "When eventual consistency is the right consistency" is a per-field decision, and this week makes you the engineer who makes it deliberately.

This week is where "it'll converge eventually" stops being a hope and becomes a property you select, test, and defend — field by field.

## Learning objectives

By the end of this week, you will be able to:

- **Bring** the Week 3 CRDT theory into production: deploy and operate a real CRDT stack (Automerge/Yjs for documents, Redis Active-Active for counters/sets) rather than a hand-rolled toy, and explain what each one gives you and costs you.
- **Choose** the right CRDT for the right field: LWW-register vs OR-set vs PN-counter vs a merge-semantics document type, for the cart, the inventory, and the counters — and articulate, per field, *why* the converged value of that type is the intended one (and where LWW is a footgun).
- **Reason about** the convergence guarantee precisely: that all replicas that have seen the same set of updates reach the same state regardless of order (strong eventual consistency), what "seen the same updates" requires (causal delivery), and what convergence does *not* promise (a correct value, or any particular value).
- **Promote** the cart service to **active-active** across two regions using a CRDT, so both regions accept writes to the same cart simultaneously without a single-writer bottleneck.
- **Partition** the two regions, write to both during the partition, **heal**, and **prove convergence** — both regions reach byte-identical cart state with every real update preserved — and measure the metadata cost of doing so.
- **Resolve conflicts at the application layer** when the CRDT's automatic merge isn't enough: vector-clock-driven sibling resolution (the Riak/Dynamo model), where you get *multiple concurrent values* and must merge them with business logic, and why sometimes surfacing the conflict to the user is the correct answer.
- **Quantify** the metadata cost of CRDTs — tombstones in OR-sets, the per-actor history in op-based types, the document growth in Automerge — and apply the compaction/GC strategies that keep that cost bounded (the thing that bites CRDT deployments in production).
- **Decide** when a CRDT is the right answer and when it is *not*: where strong consistency (a single writer, a lease, a transaction) is the correct tool because the data genuinely cannot tolerate concurrent divergent writes (inventory that must never oversell, a financial balance).

## Prerequisites

This week assumes you have completed **C22 weeks 1–19**, or have equivalent fluency. Specifically:

- The **Week 3 CRDT theory**: you can define a G-counter, PN-counter, OR-set, and LWW-register, and you understand state-based vs op-based and the convergence (join-semilattice) guarantee. We build *on* that; we don't re-derive it.
- The **Week 2 vector-clock / happens-before** literacy: you can read a vector clock and tell whether two events are concurrent or causally ordered — because vector clocks are how application-layer conflict resolution detects "these two writes were concurrent."
- The **Week 19 two-region topology**: two Kind clusters, a partition you can induce and heal, and the read-local/write-primary baseline you'll now upgrade to active-active.
- The **`cart`/`inventory` services** from Phase 1, deployable as gRPC servers — the cart is the thing you'll make CRDT-backed and active-active.
- **Node.js** (for the Automerge/Yjs exercises) and **Python** (for the Redis CRDT exercise), plus a **Redis** you can run (Redis 7+ for the local OR-set modeling; the Active-Active/CRDB semantics are explained for where you'd run them).
- Comfort with **JSON and basic data modeling** — choosing a CRDT is, at bottom, choosing how to model a field as a mergeable type.

You do **not** need a managed CRDT cloud product. The convergence *property* is identical whether you run Automerge on a laptop or Redis Active-Active across continents; the lab makes the partition-and-heal explicit and local.

## Topics covered

- **Production CRDT stacks**: **Automerge** (an op-based JSON-document CRDT with rich merge, used for local-first / collaborative apps), **Yjs** (a high-performance CRDT for shared text/structured data, the backbone of many collaborative editors), and **Redis Active-Active (CRDB)** (geo-distributed Redis where counters, sets, and registers are CRDTs at the data tier). What each is for: documents and rich structure (Automerge/Yjs) vs primitive distributed data types at scale (Redis).
- **Choosing the CRDT per field**: LWW-register (last-write-wins by timestamp — converges, but *discards* concurrent writes, the footgun); OR-set (observed-remove set — add/remove with add-wins semantics, the right type for a cart's *items*); PN-counter (increment/decrement, the right type for a *quantity* that goes both ways, with the caveat about driving it negative); and document/sequence CRDTs (Automerge/Yjs) for structured or text fields.
- **The convergence guarantee, precisely**: **strong eventual consistency** — replicas that have delivered the same set of updates are in the same state, independent of delivery *order* — and what it requires (commutativity/associativity/idempotence of merge, i.e. a join-semilattice; causal delivery for op-based types) and what it does *not* give you (a *correct* value — convergence is about *agreement*, not *intent*).
- **Active-active with a CRDT**: making both regions accept writes to the same cart, so there is no single-writer bottleneck and no failover-RTO on the write path — the thing read-local/write-primary (Week 19) couldn't do — with the partition-tolerance that a CRDT's merge provides.
- **Partition, heal, converge**: writing to both regions during a partition, healing, and proving both replicas reach identical state with every real update preserved (the lab's central demonstration) — and measuring the divergence-then-reconvergence.
- **Application-layer conflict resolution and vector clocks**: when the CRDT's automatic merge is *not* the right policy and you instead want **sibling values** (the Riak/Dynamo model) — concurrent writes detected by vector clocks are surfaced as multiple values, and *you* merge them with business logic (or ask the user) — and why "the system can't decide; surface it" is sometimes the correct, honest answer.
- **Metadata cost and compaction**: the price of convergence — OR-set **tombstones** (removed elements you must remember to prevent resurrection), op-based **history** growth, Automerge **document** growth — and the GC/compaction strategies (causal stability, snapshotting) that keep it bounded. This is the thing that quietly kills naive CRDT deployments.
- **When NOT to use a CRDT**: the data that genuinely cannot tolerate concurrent divergent writes — inventory that must never oversell (Week 19's single-writer-per-SKU with leases), a financial balance (a charge must not be lost *or* double-counted) — where strong consistency (a single writer, a transaction, consensus) is the correct, non-negotiable tool, and a CRDT would be a convergent-but-wrong footgun.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                  | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|--------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Production CRDT stacks; convergence precisely; per-field |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Automerge/Yjs: documents that merge; partition + heal    |    1h    |    2.5h   |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | OR-set carts; PN-counters; Redis Active-Active           |    2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | App-layer conflict resolution; vector clocks; siblings   |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Friday    | Metadata cost, compaction; when NOT to use a CRDT        |    0h    |    0h     |     1h     |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work                                  |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, review, convergence-proof polish                 |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                        | **6h**   | **7h**    | **4h**     | **3.5h**  | **5h**   | **12h**      | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./00-overview.md) | This overview (you are here) |
| [resources.md](./01-resources.md) | The Automerge/Yjs/Redis-CRDT docs, the CRDT papers, the production talks worth your time |
| [lecture-notes/01-production-crdt-stacks-and-convergence.md](./02-lecture-notes/01-production-crdt-stacks-and-convergence.md) | Automerge/Yjs/Redis Active-Active, the convergence guarantee precisely, choosing the CRDT per field |
| [lecture-notes/02-conflict-resolution-vector-clocks-metadata-and-limits.md](./02-lecture-notes/02-conflict-resolution-vector-clocks-metadata-and-limits.md) | App-layer resolution with vector clocks, siblings, metadata cost + compaction, and when NOT to use a CRDT |
| [exercises/README.md](./03-exercises/00-overview.md) | Index of the three exercises |
| [exercises/exercise-01-or-set-cart-partition-heal.md](./03-exercises/exercise-01-or-set-cart-partition-heal.md) | Model the cart as an OR-set, partition two replicas, write to both, heal, prove convergence — and see why LWW would have lost data |
| [exercises/exercise-02-automerge-active-active-cart.mjs](./03-exercises/exercise-02-automerge-active-active-cart.mjs) | A runnable Automerge active-active cart: two replicas diverge during a partition, merge, and converge to a correct, lossless state |
| [exercises/exercise-03-vector-clock-conflict-resolution.py](./03-exercises/exercise-03-vector-clock-conflict-resolution.py) | Detect concurrent writes with vector clocks, produce siblings, and resolve them with application-layer business logic |
| [challenges/README.md](./04-challenges/00-overview.md) | Index of the weekly challenge |
| [challenges/challenge-01-the-lww-that-ate-the-cart.md](./04-challenges/challenge-01-the-lww-that-ate-the-cart.md) | An active-active cart using LWW silently loses items on partition heal — diagnose why "it converged" hid data loss, and fix the type choice |
| [quiz.md](./05-quiz.md) | 13 questions with a hidden answer key |
| [homework.md](./06-homework.md) | Six problems including the per-field CRDT-selection memo |
| [mini-project/README.md](./07-mini-project/00-overview.md) | `cart-crdt`: the cart promoted to active-active across two regions with a CRDT, a proven convergence demo, a metadata-cost budget, and a per-field consistency map |

## The "it converged AND it's correct" promise

C22 uses a recurring marker for every exercise that ends in the system actually doing what you declared. This week's canonical one is a convergence proof that also checks *correctness* — because convergence alone is the easy, misleading half:

```
$ node exercise-02-automerge-active-active-cart.mjs
[partition] region-a adds 'sku-APPLE' (qty 2), removes 'sku-PEAR'
[partition] region-b adds 'sku-APPLE' (qty 3), adds 'sku-KIWI'
[heal]      merging region-a <-> region-b ...
--------------------------------------------------------------------
CONVERGED:  region-a state == region-b state   (byte-identical)  ✔
LOSSLESS:   every concurrent ADD preserved     (APPLE, KIWI)     ✔
INTENT:     APPLE qty = 5 (2+3, both adds kept, NOT overwritten)  ✔
            PEAR removed (the remove won over no concurrent re-add) ✔
--------------------------------------------------------------------
(an LWW register here would have CONVERGED but kept only ONE region's
 cart, silently discarding the other — converged is NOT correct.)
```

If the script reports CONVERGED *and* LOSSLESS *and* INTENT — not just CONVERGED — your CRDT is the right one for the field, not merely a thing that agrees. The point of this week is to make that distinction *ordinary*: you check that it converged to the *intended* value, the way you checked a measured RTO last week, and to make a *convergent-but-wrong* design (an LWW field that silently eats concurrent edits) something you catch in a test, not in a customer complaint.

## Stretch goals

If you finish the regular work early and want to push further:

- Run the Automerge cart **across the two real Kind regions** from Week 19, partition them at the *network* level (not just in-process), write to both, heal, and prove convergence on genuinely separated replicas. This is the mini-project's active-active across real regions.
- Measure and **bound the metadata**: drive thousands of add/remove cycles on an OR-set cart and watch the **tombstone** count grow; implement (or configure) a causal-stability-based GC that reclaims tombstones once all replicas have seen the remove, and graph the before/after document size.
- Model a field where **automatic merge is wrong** and **siblings are right**: a "shipping address" where two concurrent edits must *not* be silently merged — surface both as siblings and require resolution. Contrast with the cart's items, where add-wins merge *is* right.
- Implement the **PN-counter footgun** and its fix: show that modeling "remove from cart" as a counter decrement can go negative under concurrency, then fix it by using an OR-set (where remove is observed-remove, not arithmetic) — the per-field type choice made concrete.

## Up next

Week 21 closes the zero-trust loop on the multi-region, CRDT-backed system you now have: **SPIFFE/SPIRE workload identity and OPA policy.** The cart that's now active-active across two regions needs every cross-region hop mutually authenticated and every access authorized — and the SPIFFE identities you met in Istio (Week 8) get deployed explicitly with SPIRE, with OPA enforcing policy as code. Everything you built this week — a cart that survives a partition with no lost updates — needs to *also* survive an adversary, which is what the security stack next week provides. Push your `cart-crdt` mini-project before you start it.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
