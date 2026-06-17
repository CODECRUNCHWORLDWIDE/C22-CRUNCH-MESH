# Lecture 2 — Conflict Resolution, Vector Clocks, Metadata Cost, and the Limits

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can resolve conflicts at the application layer with vector-clock-detected siblings when automatic merge is wrong; quantify the metadata cost of CRDTs (tombstones, history, document growth) and apply compaction to bound it; and decide, for a given field, when a CRDT is the *wrong* tool and strong consistency is required.

Lecture 1 gave you the stacks and the per-field type choice. This lecture is the three things that separate a CRDT *demo* from a CRDT *deployment*: (1) what to do when the automatic merge is the wrong policy, (2) the metadata cost that quietly kills naive deployments, and (3) the fields where a CRDT is simply the wrong answer.

The sentence to carry through:

> **The CRDT's automatic merge is a *policy*; sometimes it's the right one, sometimes you must override it with application logic, and sometimes the data shouldn't be a CRDT at all — and a senior engineer is the one who knows which case they're in.**

---

## Part 1 — When automatic merge is wrong: vector clocks and siblings

### 1.1 The case the OR-set doesn't cover

An OR-set merges a *set* correctly: concurrent adds all survive, removes are observed-remove. But some fields aren't sets, and their concurrent writes have *no* correct automatic merge. The canonical example: a **shipping address** edited concurrently on two devices.

- Device A changes the street to "123 Oak St."
- Device B (concurrently, during a partition) changes the city to "Portland."

What's the merged address? A field-by-field auto-merge gives you "123 Oak St., Portland" — which might be a real address neither user intended (the Oak St. is in a *different* city). Or LWW gives you one device's entire edit and silently drops the other's. **Neither is safe**, because the address is a *coherent unit* whose fields are interdependent, and the system has no way to know which combination is correct. This is the case where the honest answer is: **the system can't decide; surface the conflict.**

The general principle behind "the OR-set doesn't cover this": a CRDT's automatic merge is correct only when the field's correctness is *compositional* — the merged value is correct *because* each part was independently correct. A set of cart items is compositional (each item is independently valid, so the union is valid). An address is *not* compositional (a valid street and a valid city can compose into an invalid address). When correctness is *not* compositional — when the parts have cross-constraints — there's no safe field-by-field merge, and you need either a whole-value LWW (which loses data) or siblings (which surface the conflict). The same applies to a "shipping method + address" pair (some methods don't ship to some places), a "start date + end date" range (start must precede end), or a "discount code + cart total" (the code might not apply to the new total). Spotting non-compositionality is how you spot a sibling field before you ship an auto-merge that produces nonsense.

### 1.2 The Dynamo/Riak model: vector clocks → siblings

The classic mechanism for "surface the conflict" comes from Amazon's Dynamo and its open-source descendant Riak: **vector clocks detect concurrency, and concurrent writes are kept as *siblings* — multiple values the application (or user) must reconcile.**

Recall the Week 2 mechanism: a **vector clock** is a per-actor version vector. Given two writes, their vector clocks tell you their relationship:

- One clock **dominates** the other (every component ≥, at least one >) → the writes are **causally ordered**; the later one supersedes the earlier. No conflict — keep the later.
- Neither dominates (each has a component the other doesn't) → the writes are **concurrent** → they *conflict*. The system keeps **both as siblings**.

```
   write X: clock {A:2, B:1}      write Y: clock {A:1, B:2}
   neither dominates the other  ->  CONCURRENT  ->  keep both as siblings
   the app (or user) must reconcile X and Y into one value
```

When the application next reads the field, it gets *both* siblings and must resolve them — with business logic ("merge the line items, sum the quantities") or by asking the user ("you changed this address on two devices; which one?"). The system's contribution is *detecting* the concurrency (vector clocks) and *not silently picking a loser* (keeping siblings); the *resolution* is the application's responsibility, because only the application knows what's correct.

### 1.2a A worked vector-clock trace

To make domination-vs-concurrency concrete, trace two writes to a `profile` field across two replicas:

```
   start: profile = "v0", clock = {A:0, B:0} on both

   CASE 1 — causal (B read A's write, then wrote):
     A writes "Alice"   -> clock {A:1, B:0}
     B receives it, THEN writes "Alice Smith" -> clock {A:1, B:1}
     compare {A:1,B:1} vs {A:1,B:0}:  every component >=, one strictly >  -> DOMINATES
     => {A:1,B:1} happened-after; keep "Alice Smith". NO conflict.

   CASE 2 — concurrent (both wrote without seeing each other):
     A writes "Alice"     -> clock {A:1, B:0}
     B writes "Bob"       -> clock {A:0, B:1}   (B never saw A's write)
     compare {A:1,B:0} vs {A:0,B:1}:  A has a component B lacks AND vice versa
     => NEITHER dominates -> CONCURRENT -> keep BOTH as siblings {"Alice","Bob"}
```

The rule, stated mechanically: **A dominates B iff A ≥ B in every component and A ≠ B; if neither dominates, they're concurrent.** Domination means "happened-after" (safe to supersede); concurrency means "happened without knowledge of each other" (a genuine conflict). The exercise has you implement exactly this `dominates`/`concurrent` test — it's a dozen lines, and it's the entire detection mechanism. Everything else (siblings, resolution) builds on this binary distinction.

### 1.2b Why CRDTs and vector-clock siblings are two answers to one question

It's worth seeing how the OR-set (Lecture 1) and the vector-clock-sibling model relate, because they're solving the *same* problem two ways:

- **The CRDT bakes the resolution into the type.** An OR-set *decides in advance* that concurrent add/remove resolves add-wins. There's no sibling, no app callback — the merge function already encodes the resolution policy. This works *when a single, universal resolution policy is correct for the field* (a cart's items: always keep both adds).
- **Vector-clock siblings defer the resolution to the app.** When *no* single universal policy is correct (a shipping address — sometimes the user wants A, sometimes B, and the system can't know), you can't bake it into a merge function. So you detect the conflict (vector clocks) and hand both values to the app/user.

So the choice between "use a CRDT" and "use siblings" is really: **is there one correct resolution policy I can bake into a merge, or must the resolution be decided case-by-case at read time?** Cart items have a universal policy (add-wins) → CRDT. Shipping addresses don't → siblings. Same underlying machinery (detect concurrency, don't lose data); different place the resolution decision lives.

### 1.3 Why this is sometimes the *right* answer

It's tempting to see "the user has to resolve it" as a failure. It isn't. For a field where there's genuinely no correct automatic merge, **surfacing the conflict is the honest, correct behavior** — the alternative (silently picking one with LWW) is *data loss disguised as success*. A calendar app that detects you double-booked and asks you to choose is *better* than one that silently keeps one event and drops the other. The senior framing: **a CRDT's auto-merge and "surface a sibling" are both valid conflict-resolution policies; you pick per field based on whether a correct automatic merge exists.** Cart items: auto-merge (OR-set), correct merge exists. Shipping address: siblings, no correct auto-merge. Exercise 3 makes you build exactly this — vector-clock detection plus application-layer sibling resolution — so the mechanism is in your fingers.

### 1.4 The hybrid: CRDT for the easy fields, siblings for the hard ones

Real systems combine both. The cart's *items* are an OR-set (auto-merge); the cart's *shipping address* is a sibling-resolved field; the cart's *last-modified timestamp* is an LWW-register. **One object, three different conflict-resolution policies, chosen per field.** This is the mature pattern: not "the cart is a CRDT" but "each field of the cart has a conflict policy appropriate to that field's semantics." The per-field consistency *map* — which field uses which policy and why — is a real design artifact, and producing it for the cart is the mini-project's central deliverable.

### 1.5 Designing the resolution function for a mergeable sibling field

When a sibling field *does* have a business merge (the cart's line items, where the right answer is "union the items, sum the quantities"), you write a **resolution function** the app applies on read. The design considerations:

- **It must be deterministic and order-independent.** If two replicas independently resolve the same siblings, they must reach the same result — otherwise you've reintroduced divergence at the resolution layer. "Union and sum" is order-independent (set union and addition both are); "pick the longer one" might not be (ties).
- **It should be idempotent under re-resolution.** Resolving an already-resolved value should be a no-op, so re-reads don't keep transforming the data.
- **It should preserve every sibling's intent where possible.** The point of siblings (vs LWW) is *not losing data*, so a good resolution merges both rather than picking one — unless the field's semantics genuinely require a single choice (then ask the user).

Notice that a *good* sibling-resolution function is essentially *reinventing a CRDT merge at the application layer* — which is the hint that, if you find yourself writing a deterministic, order-independent, idempotent merge for a field, you might as well model it as a proper CRDT and let the library handle it. Siblings earn their place specifically when the resolution is *not* a clean function — when it needs human judgment or context the system doesn't have. The art is telling those apart: a mergeable sibling field is often a CRDT in disguise; a truly-non-mergeable one is where siblings (and a user prompt) are irreplaceable.

---

## Part 2 — The metadata cost, and how to bound it

### 2.1 Convergence isn't free — it's paid in metadata

The thing CRDT demos never show you: **the convergence guarantee is paid for in metadata**, and naive deployments drown in it. Three sources:

**Tombstones (OR-sets).** An OR-set removes an element by recording a **tombstone** — a marker that "this add was removed" — because it must remember the removal to prevent the element *resurrecting* when a stale replica re-syncs an old add. If you never garbage-collect tombstones, a cart that's had 10,000 add/remove cycles carries 10,000 tombstones forever, even if it currently holds one item. The set's *logical* size is small; its *physical* size grows without bound. This is the single most common CRDT production surprise.

**Operation history (op-based types).** Op-based CRDTs (Automerge) keep the *history* of operations and their causal context, because that's how they merge and how a late replica catches up. The document's *content* might be tiny, but its *change history* grows with every edit. An Automerge document edited continuously for a year can be far larger than the data it represents.

**Per-actor state (counters, version vectors).** A vector clock has one entry per actor that's ever written. In a system with many short-lived actors (every browser tab is an actor), the version vector itself can bloat. PN-counters keep per-actor increment/decrement tallies.

A concrete way the metadata bites: imagine a popular product whose "likes" counter and "who has it in their cart" set are CRDTs. Over a year, millions of users add and remove it. The *current* state is "42 likes, 7 carts" — a handful of bytes. But the *un-GC'd* representation carries a tombstone for every removed cart-add (millions), an op for every like/unlike (millions), and a version-vector entry for every actor that ever touched it. The object is now megabytes representing a few bytes of live state — and every sync ships that bloat, and every read deserializes it. Latency climbs, memory climbs, bandwidth climbs, all for state that's logically tiny. *This* is what "CRDTs fall over in month three" means concretely, and it's why the metadata budget is not optional polish — it's the difference between a CRDT that scales and one that quietly degrades until someone notices the carts take 800ms to load.

The mitigations map to the sources:

- **tombstones** → causal-stability GC (reclaim once all replicas saw the remove),
- **op history** → snapshot/compaction (collapse to current-state + recent tail),
- **version vectors** → keep the actor set bounded (fixed regions, not per-tab actors; or use a scheme that prunes dead actors).

```
   logical size:   { "sku-APPLE": 2 }            <- 1 item, tiny
   physical size:  10,000 tombstones +
                   8,000 ops of history +
                   3,000 actor entries            <- the convergence tax
```

### 2.2 Bounding it: causal stability and compaction

The fix is **garbage collection**, gated on a safety condition so you never GC something a replica still needs:

- **Causal stability.** An operation (or tombstone) is **causally stable** once *every* replica has seen it. After that point, no replica can ever re-introduce the removed element (they've all observed the remove), so the tombstone is safe to delete. Bounding tombstones means tracking "have all replicas seen this remove?" and reclaiming once yes. This requires knowing your replica set and their progress — which is why unbounded-actor systems (every tab) are harder to GC than fixed-replica ones (a known set of regions).
- **Snapshotting / compaction.** Op-based types periodically **compact** the history: collapse the op log into a snapshot of current state plus a short recent-op tail, discarding the old ops once they're causally stable. Automerge supports saving a compacted document; Yjs has its own compaction. The discipline: compact on a schedule (or a size threshold), gated on causal stability, so the document size tracks the *data* size, not the *edit count*.

### 2.2a Compaction in practice (Automerge)

To make compaction concrete, here's the shape with Automerge. The library lets you *save* a document to a compact binary form and *load* it back — and the saved form is a snapshot, not the full op log:

```js
// after lots of edits, the in-memory doc carries a long history.
const compactBinary = Automerge.save(doc);    // a compacted snapshot (+ recent tail)
// store/ship compactBinary; it's much smaller than the full history.
const reloaded = Automerge.load(compactBinary); // resumes from the snapshot
```

The discipline: on a schedule (say nightly) or when a document crosses a size threshold, save-and-reload it, so its on-disk and over-the-wire size tracks the *data*, not the *lifetime edit count*. The safety nuance: compaction discards old ops, so it's only safe once those ops are *causally stable* (all replicas have them) — otherwise a replica that's behind couldn't catch up from the compacted snapshot. For a known set of regions, you compact once everyone's confirmed caught up; the snapshot then contains everything the laggard needs. This is the op-history analogue of tombstone GC, with the same causal-stability gate.

### 2.3 The operational rule

> **A CRDT field's metadata is a resource you must budget and reclaim, exactly like memory.** "It converges" is true forever; "it stays small" is true only if you GC the tombstones and compact the history. A CRDT deployment without a metadata budget and a compaction strategy works in the demo and falls over in month three when the documents are 100× the data.

This is why the mini-project requires a **metadata-cost budget**: measure the tombstone/history growth under realistic add/remove churn, and demonstrate a compaction that bounds it. Measuring it is what turns "CRDTs have a metadata cost" from a warning into a number you manage. The stretch goal makes you drive thousands of cycles and watch the tombstones grow, then GC them on causal stability — the cost made visible and then controlled.

### 2.4 The tombstone resurrection bug — why GC is dangerous

Garbage-collecting tombstones is *necessary* (or they grow forever) but *dangerous* if done wrong, and the failure mode has a memorable name: **resurrection**. Here's how it happens:

```
   region A removes "milk" (tombstones its add-tag), then GCs the tombstone
     thinking it's safe — but region C was partitioned and never saw the remove.
   region C, still holding the OLD add of "milk", re-syncs.
   region A no longer has the tombstone (it GC'd it), so A sees C's add as NEW.
   => "milk" RESURRECTS — an item the user deleted comes BACK.
```

The bug is GC'ing a tombstone *before causal stability* — before *every* replica has seen the remove. The tombstone exists precisely to suppress C's stale add; remove it too early and the stale add wins. This is why the safety condition is **causal stability** (all replicas have observed the remove), not "it's been a while" or "the set looks settled." A time-based or size-based GC that ignores causal stability is a resurrection bug waiting for a partition. The homework's planted-fault includes exactly this — an item that comes back from the dead after a sync — and the two-signal diagnosis is "it was definitely removed" plus "it's present after sync."

The practical consequence: **GC requires knowing your replica set and tracking each replica's progress** (a version vector of "what has everyone seen"). This is tractable for a *fixed, known* replica set (your two or three regions) and hard for an *unbounded, ephemeral* one (every browser tab is a replica that might never come back to confirm it saw a remove). Which is why local-first apps with millions of clients use cleverer schemes (and why "CRDTs: The Hard Parts" is a talk and not a footnote). For the cart across a *known* set of regions, causal-stability GC is achievable, and the mini-project asks for it.

### 2.5 A rough budget you can reason about

To make the metadata cost something you can *plan*, a back-of-envelope model for an OR-set cart across R regions:

- **Tombstones** without GC ≈ the total number of *removes* ever performed. A cart with heavy churn (add, remove, re-add repeatedly) accumulates a tombstone per remove. With causal-stability GC, this drops to ≈ the removes *not yet seen by all R regions* — typically a small, bounded number (recent removes in flight).
- **Op history** (op-based) without compaction ≈ the total number of *operations* ever. With periodic snapshot-compaction, it drops to ≈ the recent op tail since the last snapshot.
- **Version vectors** ≈ R entries (one per region) for a fixed region set — small and bounded. (Unbounded actors are the problem case.)

So the *bounded* steady-state metadata for a fixed-region cart is roughly: the data + a snapshot + a small tail of recent ops + R version-vector entries + a handful of not-yet-stable tombstones. That's *proportional to the data*, not the edit count — which is the whole goal. The mini-project's budget is to *show* this: drive churn, measure the unbounded growth, apply GC/compaction, and demonstrate the steady-state is bounded and proportional to the live data. "Without GC the document grew to 50× the data after 10k cycles; with causal-stability GC it stayed at ~1.2× the data" is the sentence that proves you can run a CRDT past the demo.

---

## Part 3 — When NOT to use a CRDT

### 3.1 The fields where convergence is the wrong goal

A CRDT's promise is "all replicas agree." For some data, *agreeing on a value reached by merging concurrent writes is exactly the wrong thing*, because the correct behavior is to *prevent* the concurrent writes from both succeeding in the first place. Two canonical cases:

**Inventory that must never oversell.** You have 10 units. Region A sells the last unit; region B, concurrently (during a partition), also sells the last unit. A CRDT would *converge* — to a count of -1, or to "both sales succeeded," i.e. **you sold 11 of 10 units**. The convergence is real and the result is a business catastrophe (you can't ship a unit you don't have). The correct tool is **strong consistency**: a single writer per SKU with a lease (Week 19's inventory model, Week 2's leases/fencing), or a transaction, so that *only one* region can sell the last unit and the other is told "out of stock." Here, *refusing* the concurrent write is the feature; merging it is the bug.

**A financial balance / a charge.** A payment must be neither lost nor double-counted. A CRDT counter would happily converge a balance under concurrent debits — but "converged to a wrong balance" is fraud or loss. Payments use strong consistency (a single source of truth, idempotency keys, transactions — Week 11's exactly-once, Week 12's Temporal), *not* a CRDT, precisely because the correct behavior under concurrency is coordination, not convergence.

**A uniqueness constraint.** "This username/email/slug must be unique" cannot be a CRDT. Two regions concurrently registering the same username would both *converge* to "registered" — and now two users own the same identity. Uniqueness is an *invariant across the whole dataset*, and CRDTs guarantee per-key convergence, not global invariants. Uniqueness needs coordination (a single authority for the namespace, or a consensus-backed allocation).

The deeper principle behind all three: **CRDTs preserve *local* invariants (a counter sums correctly, a set merges) but cannot enforce *global* invariants (stock ≥ 0 across all regions, a balance is exact, a name is unique).** Any constraint that spans the concurrent writers — "the total must not exceed X," "this must be unique," "these must sum to zero" — cannot be a CRDT, because enforcing it requires the writers to coordinate, which is exactly what CRDTs avoid. When you see a *global invariant*, you see a strong-consistency field. That's the sharpest single test for "is this a CRDT field": **does correctness depend on a constraint that spans concurrent writers?** If yes, it's not a CRDT.

### 3.1a The "reservation" pattern: making inventory tolerable

Inventory is the canonical not-a-CRDT field, but it's worth seeing how real systems make it *work* across regions without overselling, because "just use strong consistency" is a non-answer if it kills your multi-region latency. The dominant pattern is **per-region reservations against a coordinated pool**:

- A single authority (or a consensus group) owns the *total* stock for a SKU.
- It *allocates* a chunk of that stock to each region as a *reservation* (region A gets 4 units, region B gets 4, 2 held back).
- Within its reservation, each region sells *locally and fast* (no cross-region coordination) — it's selling from *its own* allocated units, so there's no conflict.
- When a region's reservation runs low, it asks the authority for more (a coordinated, but infrequent, operation).

This gives you *most* of the multi-region win (local, fast sells) while *preserving the global invariant* (you can't sell more than the authority allocated). It's not a CRDT — the authority coordinates the allocation — but it pushes the coordination to the *rare* path (refilling reservations) and keeps the *common* path (selling) local. The lesson: **"not a CRDT" doesn't mean "single region, slow."** It means the *coordination* (allocation) is strongly consistent while the *common operations* (sells within a reservation) are local. The capstone's `inventory-service` ("single-writer-per-SKU with leases") is exactly this — the lease *is* the reservation. So the cart is active-active via CRDT, and inventory is reservation-based strong consistency, and both are correct multi-region designs for their respective invariants.

### 3.2 The test, restated as a question

For any field, ask: **"If two regions write this concurrently and the system merges them, is the merged value acceptable?"**

- **Yes** (cart items: both adds survive; a counter: both increments count; a presence timestamp: newest wins) → CRDT is fine, pick the type whose merge is correct (Lecture 1 §3).
- **No, but a human/app could reconcile** (a shipping address) → siblings + application-layer resolution (Part 1).
- **No, and there's no acceptable merge — the concurrent writes must not *both* succeed** (overselling inventory, a balance) → **strong consistency**: prevent the concurrent write with a single writer, a lease, or a transaction. A CRDT here is a convergent-but-wrong footgun.

### 3.3 The senior posture: per-field, not per-system

The recurring discipline, stated for the last time: **"are we eventually consistent or strongly consistent" is not a system-wide question; it's a per-field question.** The same cart service has CRDT fields (items, quantities), sibling-resolved fields (address), and — if it touches inventory — strong-consistency dependencies (the stock check). A senior design *labels each field with its consistency model* and defends each label. The junior mistake is a blanket answer ("we're eventually consistent, we use CRDTs") that quietly applies a convergent-but-wrong policy to a field that needed strong consistency, and oversells the inventory in production. The competence this week certifies is the *discrimination*: knowing, field by field, which consistency model is correct and why.

This is also why the cart in your capstone is active-active via CRDT *while* inventory stays single-writer-per-SKU: it's not inconsistency, it's *correct* per-field design. The cart tolerates divergence and has a correct merge; inventory tolerates neither. Same system, opposite models, both right.

One more framing that helps in design reviews: **a CRDT is a *tool*, not an *architecture*.** Saying "we're a CRDT system" is as meaningless as saying "we're an `if`-statement system" — CRDTs are a tool you apply to specific fields where their properties (coordination-free convergence) are exactly what that field needs. A mature distributed system uses CRDTs for the handful of fields that benefit, strong consistency for the fields with global invariants, siblings for the genuinely-ambiguous fields, and plain single-writer values for everything else. The architecture is the *system*; CRDTs are one tool in it. When someone proposes "let's build it on CRDTs," the right response is "for which fields, and why those?" — pushing the conversation from a religion back to per-field engineering. That reframe is, more than any single CRDT type, what this week is trying to install.

### 3.3a A production-readiness checklist for a CRDT field

Before a CRDT field ships, run it past this list — it catches the failures this lecture has named:

- [ ] **The type matches the field's semantics.** A set is an OR-set (not LWW); a two-way number is a counter (not LWW); a non-compositional value is siblings (not auto-merge).
- [ ] **Correctness, not just convergence, is monitored.** A check asserts "every acknowledged write survives," not merely "the replicas are equal." (The convergence-only monitor misses the LWW footgun.)
- [ ] **The merge is from a library, not hand-rolled.** Proven commutative/associative/idempotent merge + a battle-tested sync transport.
- [ ] **Metadata is bounded.** Tombstones GC'd on causal stability; op history compacted; version vectors bounded (fixed actor set). A measured before/after on size under churn.
- [ ] **No premature GC.** GC is gated on causal stability (all replicas saw the remove), not time/size — or you get resurrection.
- [ ] **The field is genuinely a CRDT field.** It tolerates divergence, has a correct merge, and benefits from coordination-free writes — and does *not* carry a global invariant (which would make it strong-consistency).
- [ ] **Sibling fields have a deterministic resolution** (order-independent, idempotent) or a user-prompt path — not a silent LWW.

A CRDT field that passes all seven is production-ready; one that skips the metadata or the correctness-monitoring lines works in the demo and degrades (or loses data) in production. The mini-project is essentially this checklist, made into a graded deliverable.

### 3.4 A decision flowchart for any field

Pulling Parts 1–3 together into one procedure you can run on any field:

```
FOR EACH FIELD:

  Does correctness depend on a constraint SPANNING the concurrent writers?
  (stock >= 0, balance exact, name unique, total bounded)
      |
      YES -> STRONG CONSISTENCY (not a CRDT).
      |       single writer / lease / transaction / reservation pattern.
      NO
      |
  Can two regions write it concurrently at all?
      |
      NO  -> a plain value, single writer. (no CRDT needed.)
      YES
      |
  Is there ONE universal, correct merge for concurrent writes?
      |
      YES -> CRDT. pick the type whose merge IS that policy:
      |        set -> OR-set ; two-way number -> PN-counter ;
      |        newest-wins -> LWW ; structured -> Automerge doc.
      NO
      |
  Can a human/app reconcile concurrent values case-by-case?
      |
      YES -> SIBLINGS (vector-clock detect + app/user resolution).
      NO  -> reconsider: it's probably a strong-consistency field after all.
```

Run this on every field of a feature and you produce the per-field consistency map — the mini-project's central artifact and the thing that distinguishes a senior CRDT design from "we sprinkled CRDTs on it." The flowchart is mechanical, which is the point: per-field consistency reasoning should be a *checklist you run*, not a vibe you have.

### 3.4a Five red flags in a CRDT design review

When reviewing a colleague's "we'll use a CRDT" proposal, these five red flags catch the common mistakes:

1. **A *set* field modeled as a single LWW value** — it'll converge and silently eat concurrent adds (the Challenge).
2. **A *quantity* modeled as an LWW value instead of a counter** — concurrent changes stomp each other instead of summing.
3. **No metadata/GC story** — works in the demo, drowns in tombstones in month three.
4. **A field with a global invariant treated as a CRDT** — overselling, double-charge, duplicate username waiting to happen.
5. **"It converges" offered as the correctness argument** — convergence is agreement, not correctness; ask "to *what* value, and is that what users wanted?"

Spotting any one of these in review saves a production incident. They're the five ways "we use CRDTs" goes wrong, and naming them is the reviewer's job.

### 3.5 The week's cheat sheet

```
CONVERGENCE != CORRECTNESS
  the type's merge gives AGREEMENT; YOUR type choice gives the INTENDED value.

CONFLICT POLICIES (choose per field)
  CRDT auto-merge   one universal correct merge exists (cart items: add-wins)
  siblings          no universal merge; app/user reconciles (shipping address)
  strong consistency a global invariant spans writers (inventory, balance, uniqueness)

VECTOR CLOCKS
  A dominates B  -> A happened-after -> supersede (no conflict)
  neither dominates -> CONCURRENT -> siblings

METADATA = the price of convergence
  tombstones (OR-set) + op history (op-based) + version vectors
  bound with CAUSAL-STABILITY GC + compaction
  premature GC (before all replicas saw the remove) -> RESURRECTION bug

NOT A CRDT when:
  correctness needs a constraint spanning concurrent writers.
  -> use single-writer / lease / reservation / transaction.
```

The one line to leave with: **eventual consistency is the *right* consistency exactly when the field tolerates divergence, has a correct merge, and benefits from coordination-free local writes — and a senior engineer decides that field by field, never system-wide.**

---

## 4. Recap

You should now be able to:

- Resolve conflicts at the application layer when automatic merge is wrong: use **vector clocks** to detect concurrency, keep concurrent writes as **siblings**, and reconcile them with business logic or by asking the user — and recognize that "surface the conflict" is the *correct*, honest behavior when no correct auto-merge exists.
- Combine policies per field: OR-set auto-merge for cart items, siblings for a shipping address, LWW for a timestamp — one object, multiple conflict policies, chosen per field.
- Quantify the **metadata cost** (tombstones, op history, per-actor state) and bound it with **causal-stability-gated GC** and **compaction/snapshotting** — and treat CRDT metadata as a budgeted, reclaimed resource.
- Decide when a CRDT is the *wrong* tool: inventory that must not oversell, a financial balance — fields where the correct behavior under concurrency is *coordination* (strong consistency, single writer, lease, transaction), not convergence.
- Apply the per-field test ("is the merged concurrent value acceptable?") and defend a **per-field consistency map**, not a blanket system-wide answer.
- Trace a vector-clock comparison (dominates vs concurrent) and explain why CRDT-merge and vector-clock-siblings are two answers to one question (one universal merge policy vs case-by-case resolution).
- Explain the **resurrection bug** (premature tombstone GC before causal stability) and why it's the reason GC needs a known replica set.
- Recognize a **global invariant** (stock ≥ 0, uniqueness, an exact balance) as the sharpest signal of a *not-a-CRDT* field, and know the **reservation pattern** that makes inventory tolerable multi-region without overselling.

The single most important takeaway of the entire week, restated once more because it's the thing people get wrong: **a CRDT guarantees the replicas agree; it does not guarantee they agree on something correct.** Convergence is the easy, free, monitored half. Correctness — the agreed value being the one users wanted — comes only from choosing the right type/policy per field. Monitor *correctness* (every acknowledged add survives), not just convergence (the replicas are equal), or you'll ship a cart that agrees beautifully while eating your customers' items.

When you build the `cart-crdt` mini-project, every claim in this lecture becomes a thing you *demonstrate*: convergence AND losslessness AND intent (not just convergence), a bounded metadata budget (not unbounded growth), and a per-field consistency map (not "we use CRDTs"). That demonstrated, correct, bounded CRDT cart — not a converging blob — is the deliverable, and it's the capstone's `cart-service`.

And the connection forward: this CRDT cart sits on the Week-19 two-region base (now genuinely active-active, not just failover) and under the Week-21 zero-trust layer (every cross-region sync hop mutually authenticated and authorized). The convergence-across-a-partition demo you build here is one of the capstone's required deliverables, and Week 22's gameday will partition the regions for real while a load generator writes to both — and grade whether your cart converges losslessly. So the correctness you prove this week (not just "it converged" but "every acknowledged add survived") is exactly what the gameday tests. Build it so the proof is real, because in two weeks it gets exercised under adversarial conditions, not friendly ones.

Next: the exercises put an OR-set cart, an active-active Automerge cart, and vector-clock sibling resolution in your hands. Continue to [the exercises](../03-exercises/00-overview.md).

---

## References

- *Amazon Dynamo (DeCandia et al., 2007) — §4.4 Data Versioning (vector clocks, siblings)*: <https://www.allthingsdistributed.com/files/amazon-dynamo-sosp2007.pdf>
- *Riak — conflict resolution / siblings*: <https://docs.riak.com/riak/kv/latest/developing/usage/conflict-resolution/index.html>
- *Martin Kleppmann — "CRDTs: The Hard Parts" (metadata, tombstones)*: <https://www.youtube.com/watch?v=x7drE24geUw>
- *Automerge — under the hood (history, compaction)*: <https://automerge.org/docs/under-the-hood/>
- *Designing Data-Intensive Applications — Ch. 7 (Transactions), Ch. 9 (Consistency and Consensus)*, Martin Kleppmann.
