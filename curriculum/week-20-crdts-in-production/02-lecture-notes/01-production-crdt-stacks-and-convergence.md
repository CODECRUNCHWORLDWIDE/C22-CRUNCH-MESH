# Lecture 1 — Production CRDT Stacks, Convergence, and Choosing the Type Per Field

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can describe the production CRDT stacks (Automerge, Yjs, Redis Active-Active) and what each is for; state the convergence guarantee precisely and what it does *not* promise; and choose the right CRDT type for the cart's items, an inventory quantity, and a counter — articulating, per field, why the converged value of that type is the *intended* one.

If you remember one sentence from this lecture, remember this one:

> **A CRDT guarantees the replicas agree; it does not guarantee they agree on something correct — so the engineering is not "make it converge" (the type does that) but "pick the type whose converged value is the one your users wanted."**

In Week 3 you proved a hand-rolled OR-set converges after a partition heal. That was the *theory*: convergence exists, it's a mathematical property of the merge function, and you exhibited it. This week is the *practice*: real stacks teams run, the harder question of *which* type for *which* field, and the honest limits — metadata cost, when automatic merge is wrong, and when a CRDT is the wrong tool entirely. The skill that makes you dangerous with CRDTs is not knowing they converge; everyone knows that. It's knowing *which* CRDT makes the convergence land on the value the business wanted, and recognizing the fields where no CRDT does and you need strong consistency instead.

---

## 0. From Week 3 theory to 2026 production

A bridge before the stacks. In Week 3 you hand-rolled an OR-set in Rust and watched it converge after a simulated partition — the *theory*, exhibited. That was the right way to *learn* a CRDT (build the merge, see the semilattice), but it is *not* how you run one in production, for three reasons this week makes you internalize:

1. **Hand-rolled merges have bugs.** A CRDT's convergence rests on the merge being commutative, associative, and idempotent. Get one of those subtly wrong (a non-idempotent merge that double-counts on a resend) and you break convergence in a way that only shows up under specific message interleavings — the worst kind of bug to find in production. Mature libraries (Automerge, Yjs, Redis CRDB) have *proven* merges and battle-tested transports. You stop hand-rolling.

2. **The transport is half the problem.** A CRDT type is useless without a way to ship updates between replicas reliably (op-based) or efficiently (delta-state). Automerge's binary sync protocol, Yjs's update encoding, and Redis's cross-region replication are real engineering you don't want to redo. The library gives you the type *and* the sync.

3. **Metadata management is the production hard part.** Tombstones, op history, version vectors — these grow, and bounding them (Lecture 2) is what separates a CRDT that works in the demo from one that works in month three. The libraries give you compaction/GC primitives; you still have to *use* them, which is why this week makes you measure and bound metadata.

So this week is the *graduation* from Week 3: same convergence guarantee, now realized with production stacks, with the harder questions (which type per field, when not to, how to bound the cost) front and center. The reason CRDTs are *now* (2026) a standard tool and not a research curiosity is exactly that these stacks matured — Automerge 2.x's Rust core, Yjs's performance, Redis Active-Active as managed infrastructure — so the engineering moved from "implement a CRDT" to "choose and operate one." That's the shift this week trains.

---

## 1. The production stacks

### 1.1 Automerge — the JSON-document CRDT

**Automerge** is an op-based CRDT that gives you a **JSON-like document** that merges. You read and write it like a normal object (maps, lists, text, counters, nested structures), and Automerge records every change as an operation with a causal context. Two replicas that diverge can each `merge` the other's changes and reach the same document — automatically, with no central server.

- **What it's for:** rich application state that's naturally a document — a cart, a config, a collaborative form, a local-first app's whole data model. When your data is a structured object and you want the *whole object* to merge sensibly, Automerge is the tool.
- **The 2026 shape:** Automerge 2.x has a Rust core compiled to WASM, so it's fast and runs the same in the browser, Node, and native. You use it from JavaScript/TypeScript (and other bindings), and it handles the op log, the merge, and the binary sync protocol for you.
- **The merge semantics matter:** Automerge's containers have *defined* concurrent-merge rules — concurrent inserts into a list both survive (in a deterministic order); a map key set concurrently by two actors resolves by a deterministic rule; it has an explicit `Counter` type for the increment case. You're not getting "last write wins" by default — you're getting type-appropriate merge, which is the entire point.

A taste of the API, so the model is concrete:

```js
import * as Automerge from "@automerge/automerge";

let doc = Automerge.from({ items: {} });             // a JSON-like document
doc = Automerge.change(doc, (d) => {                 // a local change
  d.items["sku-APPLE"] = { qty: new Automerge.Counter(0) };
  d.items["sku-APPLE"].qty.increment(2);             // Counter = a PN-counter
});

// another replica makes a CONCURRENT change, then they merge:
const merged = Automerge.merge(doc, otherReplicaDoc); // converges, type-appropriately
```

The `Counter` increment is a PN-counter under the hood, so two replicas concurrently incrementing the same counter *sum* — not last-write-wins. That defined, type-appropriate merge is what makes Automerge a *correct* cart and not just a converging blob.

### 1.2 Yjs — the high-performance shared-data CRDT

**Yjs** is a CRDT optimized for **shared text and structured data at interactive speed** — it's the engine under a large fraction of real-time collaborative editors. Its `Y.Text`, `Y.Array`, `Y.Map` types merge concurrent edits with the kind of performance a live multi-cursor editor needs.

- **What it's for:** collaborative editing and high-frequency shared state where merge performance and small update sizes are critical (every keystroke is an op). Where Automerge optimizes for a clean document model and history, Yjs optimizes for throughput and compact updates.
- **The takeaway for this course:** you won't build a text editor, but Yjs is the name to know when someone says "real-time collaboration" — and the design lesson (sequence CRDTs for ordered data, with carefully engineered metadata) transfers.

### 1.3 Redis Active-Active (CRDB) — CRDTs at the data tier

The other family is **primitive distributed data types at scale**. **Redis Active-Active** (geo-distributed CRDB) makes Redis's data structures into CRDTs: a counter is a PN-counter, a set is an OR-set, a register is an LWW (or a defined-merge) register — replicated across regions, each accepting writes, converging automatically.

- **What it's for:** the data *tier*, not the application document. When you want "a counter that's correct under concurrent increments from three regions" or "a set that converges," and you want it as infrastructure rather than in-app state, this is the tool. Counters, presence sets, rate-limit buckets, feature-flag registers.
- **The honest framing:** Redis gives you the *primitives* (counter, set, register) as CRDTs and *defines* the conflict-resolution rule per type. Your job is to know which primitive maps to your field and what its merge rule does — which is exactly §3.

In Redis Active-Active, the *same commands* you already know become CRDT operations across regions:

```
# region A and region B are both writable members of the same Active-Active DB.
# A regular INCR is a PN-counter increment that converges across regions:
A> INCR cart:user42:apple:qty      # +1 in region A
B> INCR cart:user42:apple:qty      # +1 in region B, concurrently
# after sync: the counter is +2 on BOTH regions (both increments counted)

# A regular SADD is an OR-set add (add-wins on concurrent add/remove):
A> SADD cart:user42:items "sku-KIWI"
B> SADD cart:user42:items "sku-PEAR"
# after sync: the set has BOTH on both regions
```

You didn't write CRDT code — you wrote ordinary Redis commands, and the Active-Active database made them converge. The catch (and the reason §3 matters): you must *know* that `INCR` is a PN-counter and a `SET` (string) is an LWW-register, so you don't accidentally model a *set* of items as a single `SET` string (the LWW footgun) when you meant a converging `SADD` set. The primitive's merge rule is fixed; choosing the right primitive is the engineering.

### 1.4 The split: documents vs primitives

The mental model: **Automerge/Yjs give you rich mergeable documents (in-app state); Redis Active-Active gives you primitive mergeable data types (at the data tier).** A cart could be modeled either way — as an Automerge document (the whole cart merges) or as a Redis OR-set of items plus PN-counters for quantities (each field is a primitive CRDT). Both are valid; the choice is where you want the convergence to live (in the app or in the database) and how rich the merge needs to be. This week's lab does the document version (Automerge) because it makes the per-field reasoning vivid, and the data-tier version (OR-set/counter modeling) because that's how the cart's data would live in the capstone's Redis.

The tradeoff between the two placements, made explicit:

- **Convergence in the app (Automerge/Yjs):** the merge logic lives in your service, the document syncs between replicas, and the *database* can be anything (it just stores opaque CRDT blobs). *Pro:* rich, type-appropriate merge of complex nested state; works offline / local-first. *Con:* every service that touches the state needs the CRDT library and must handle sync; the document (with its history) is the thing you store and grow.
- **Convergence in the database (Redis Active-Active):** the merge lives in the data tier, and your services use ordinary commands. *Pro:* services stay simple (just `INCR`/`SADD`); convergence is operational infrastructure. *Con:* you're limited to the primitive types the database offers, and you run a geo-distributed database (operational cost).

For the capstone cart, the lab teaches the app-side (Automerge) reasoning because it makes "this field is an OR-set, that one is a Counter" vivid, but the production deployment could push the cart's data into Redis Active-Active CRDTs — same per-field type choices, different placement. The skill (choosing the type per field) transfers regardless of where the convergence lives.

---

### 1.5 Choosing a stack — the decision

When do you reach for which stack? The decision, made operational:

- **Reach for Automerge** when your state is a *document* — a structured object you want to merge as a whole, with history, used from JS/TS, in a local-first or collaborative-but-not-hyper-high-frequency app. The cart, a form, a config, a kanban board. You get rich merge and a clean change model; you pay in document/history growth (bounded by compaction).
- **Reach for Yjs** when you need *interactive-speed* shared editing — a collaborative text editor, a whiteboard, anything where every keystroke is an op and update size + merge throughput are critical. You get blistering performance and tiny updates; you pay in a more specialized API.
- **Reach for Redis Active-Active (CRDB)** when you want *primitive* CRDT data types as *infrastructure* — a geo-distributed counter, set, or register at the data tier, not in-app state. A cross-region rate-limit bucket, a presence set, a feature-flag register. You get convergence as a database feature; you pay in the operational cost of running a geo-distributed Redis and in being limited to the primitive types it offers.

The mistake to avoid: forcing one stack everywhere. A system can use Automerge for its in-app document state *and* Redis Active-Active for a cross-region counter *and* never touch Yjs — each where it fits. And for the cart specifically, you could model it either as an Automerge document (the whole cart merges) or as Redis OR-set + PN-counter at the data tier; the lab does the Automerge version for vividness and notes the Redis version for the capstone. The choice is *where the convergence lives* (in the app or in the database) and *how rich the merge must be* — not a one-size answer.

---

## 2. The convergence guarantee, stated precisely

Everyone says "CRDTs converge." Here is what that *actually* means, stated carefully enough that you can reason about its edges.

### 2.1 Strong eventual consistency

The guarantee is **strong eventual consistency (SEC)**:

> **Any two replicas that have delivered the same set of updates are in the same state — regardless of the *order* in which those updates were delivered.**

Two things to extract:

- **"The same set of updates."** Convergence is conditional on the replicas having *seen the same updates*. A replica that's missing an update isn't diverged-forever; it's just *behind* — once it gets the update, it converges. (This is why "converged" requires that updates actually propagate; a partition that never heals means replicas that never converge, not because the CRDT failed but because they haven't seen each other's updates yet.)
- **"Regardless of order."** This is the magic property. Normal data structures care about order (apply A-then-B vs B-then-A and you might get different results). A CRDT's merge is **commutative, associative, and idempotent** — apply the updates in any order, any grouping, even some twice, and you land in the same place. That's the *join-semilattice* structure from Week 3, and it's *why* you don't need coordination: order doesn't matter, so you don't have to agree on an order.

### 2.2 What convergence does NOT promise

This is the heart of the week, so it gets its own statement:

> **Convergence is *agreement*, not *correctness*. The CRDT guarantees all replicas reach the *same* value. It says *nothing* about whether that value is the one your users intended.**

A LWW-register converges perfectly: every replica ends up with the write that has the latest timestamp. But "the latest timestamp wins" *discards* every concurrent write — two users edited the field, both edits were real and acknowledged, and LWW keeps one and throws the other away, forever, with no error and no log. The replicas *agree* (converged ✔) on a value that *lost data* (correct ✘). The convergence didn't fail; the *type choice* was wrong for a field with concurrent writers.

So the discipline is: **convergence is table stakes; the question is always "does this type's merge rule produce the value the business wanted for this field?"** That question is answered per field, in §3.

### 2.3 What it requires of you

For the guarantee to hold in practice:

- **Op-based types need causal delivery.** Automerge and other op-based CRDTs require operations to be delivered respecting happens-before (you can't apply "remove X" before the "add X" it refers to). The library handles this via the causal context it ships with each change — but it means the transport must deliver a replica's full causal history, which is part of why op-based metadata grows (§ Lecture 2).
- **State-based types need a correct join.** A state-based (CvRDT) merge must be the least-upper-bound of a semilattice — commutative, associative, idempotent. If you hand-roll one and get the merge wrong (non-idempotent, say), you *break* convergence. (This is why you use a library, not a hand-rolled type, in production — Week 3 was the hand-rolled learning exercise; this week you stop hand-rolling.)

### 2.4 State-based vs op-based, and why it matters in production

The Week 3 distinction between state-based (CvRDT) and op-based (CmRDT) becomes an *operational* choice in production, so it's worth restating with its consequences:

- **State-based (CvRDT):** replicas periodically exchange their *full state* and *merge* it (join/least-upper-bound). *Pros:* simple transport (you can lose, duplicate, or reorder messages and still converge, because the merge is idempotent and order-independent — just resend the whole state). Robust to flaky networks. *Cons:* sending full state is expensive if the state is large (you ship the whole cart, not just the change). Mitigated by *delta-state* CRDTs, which ship only the changed part.
- **Op-based (CmRDT):** replicas exchange *operations* (the individual add/remove). *Pros:* small messages (just the op). *Cons:* the ops must be delivered *reliably and in causal order* — you can't drop or reorder them, because applying "remove X" before "add X" is undefined. This pushes complexity into the transport (it must guarantee causal delivery) and is why op-based metadata includes the causal context. Automerge is op-based (with an efficient binary sync protocol that handles the causal delivery for you).

The practical upshot: **the library you pick has already made this choice and built the transport for it** — Automerge handles op-based causal sync, Redis Active-Active handles state/delta sync between regions. Your job is to understand the *consequence*: op-based gives small updates but needs ordered delivery (which the binary sync provides), and the causal history it carries is part of the metadata you must compact (Lecture 2). You don't implement the transport; you reason about its cost.

### 2.5 A worked SEC example: order independence

To make "regardless of order" concrete, trace a G-counter (the simplest CRDT) across three replicas with messages arriving in different orders:

```
   three replicas, each increments locally, then they gossip state.
   A: +1   B: +1   C: +1     (each a per-actor tally)

   state = { A:1, B:1, C:1 } eventually on ALL replicas, because:
     merge takes the MAX per actor (idempotent, commutative, associative)
     A receives C then B  -> {A:1,C:1} then {A:1,B:1,C:1}
     B receives A then C  -> {A:1,B:1} then {A:1,B:1,C:1}
     C receives B then A  -> {B:1,C:1} then {A:1,B:1,C:1}   <- SAME final state
   value = sum = 3 on all three, no matter the message order.
```

Each replica saw the *same set* of updates ({A's, B's, C's increments}) and reached the *same state* — even though each saw them in a *different order* and could have seen duplicates. That's strong eventual consistency in one trace: the per-actor max is order-independent, so no coordination on ordering is needed. Every CRDT generalizes this — the merge is structured so order doesn't matter, which is *why* you can run it active-active with no consensus. The exercise has you confirm the same order-independence on the OR-set cart by re-running the merges in different orders and getting identical results.

---

## 3. Choosing the CRDT per field — the actual engineering

Here is the table that is the whole week. For each field of the cart system, the right CRDT type and *why its converged value is the intended one*.

| Field | Wrong (footgun) | Right type | Why the converged value is correct |
|---|---|---|---|
| Cart **items** (which SKUs are in the cart) | LWW-register on the whole cart | **OR-set** | Two regions concurrently add different items; add-wins OR-set keeps *both* adds. LWW would keep only one region's cart, discarding the other's adds. |
| Cart item **quantity** (a number that goes up and down) | LWW-register | **PN-counter** (with a floor) | Concurrent "+2" and "+3" both count → 5, not "whichever wrote last." Caveat: model *removal* as observed-remove (OR-set membership), not a decrement, or the counter can go negative. |
| A **like/view counter** | LWW-register | **PN-counter** (or G-counter if monotonic) | Increments from many regions all count; LWW would keep one region's increment and lose the rest. |
| A **last-seen / presence** timestamp | OR-set | **LWW-register** | Here LWW is *correct*: you genuinely want the most-recent value and concurrent writes are interchangeable (you want the newest timestamp). LWW is the right tool *when discarding the older write is the intended behavior*. |
| A **shipping address** edited by two devices | auto-merged anything | **siblings (app-layer resolution)** | Two concurrent address edits must NOT silently merge into a Frankenstein address. Surface both as siblings; the user picks (Lecture 2). |
| **Inventory stock count** (must never oversell) | *any* CRDT | **strong consistency** (single-writer-per-SKU + lease) | This field *cannot* tolerate divergent concurrent writes — two regions both selling the last unit is overselling. A CRDT would converge to a *wrong* (oversold) count. Use a single writer, not a CRDT (Lecture 2 §4). |

The three lessons baked into that table:

1. **LWW is sometimes right and sometimes a footgun** — it's *right* when concurrent writes are genuinely interchangeable and you want the newest (a presence timestamp); it's a *footgun* when concurrent writes are both real data you must keep (a cart's items, a counter). The whole skill is telling those apart.
2. **The "shape" of the field picks the type:** a *set* of things → OR-set; a *number that goes both ways* → PN-counter; a *single value where newest wins* → LWW-register; *structured data that merges* → an Automerge document; *concurrent edits that must not auto-merge* → siblings.
3. **Some fields are not CRDT fields at all.** Inventory that must never oversell is a *strong-consistency* field — convergence to an agreed value is exactly wrong when that agreed value can be "we sold 11 of 10 units." Knowing which fields are CRDT fields and which are strong-consistency fields is the senior judgment (Lecture 2 §4).

### 3.1 The cart, worked

The capstone cart is the canonical example, so let's model it fully:

- **Items present:** an **OR-set** of SKUs. Add an item → add to the set (add-wins, so a concurrent add in another region survives). Remove an item → observed-remove (removes only the adds this replica has *seen*, so a concurrent re-add survives the remove). Two regions, partition, both add items → heal → the cart has *all* the items. This is the lossless behavior the OR-set buys.
- **Quantity per item:** a **PN-counter** per SKU (or, more safely, model the cart as a multiset where quantity is the count of OR-set adds for that SKU). Concurrent "add 2 apples" in A and "add 3 apples" in B → 5 apples after heal, not 2 or 3. The intent (both customers' adds count) is preserved.
- **The removal subtlety:** if you model "remove all apples" as a PN-counter decrement, and another region concurrently "add 1 apple," arithmetic can produce a negative or surprising count. The robust model uses OR-set membership for *presence* and reserves the counter (or counts adds) for *quantity*, so a remove is "remove the observed adds," not "subtract a number." This is exactly the PN-counter footgun the homework and stretch make you hit and fix.

> **The senior move:** model the cart so that the *converged* state after any partition is the *union of both customers' intentions* — every item they added is there, every quantity counts, and a removal only undoes what it actually saw. That's an OR-set/multiset model, and it's why "the cart converges *correctly*" (not just converges) is the achievable, demonstrable goal of this week.

### 3.2 The OR-set mechanism, in detail

Because the OR-set is the workhorse of this week, it's worth seeing *exactly* how it achieves add-wins, so the convergence isn't magic. An OR-set represents each element not as "present/absent" but as a *set of unique add-tags*:

- **add(x):** attach a fresh, globally-unique tag to `x` (e.g. `regionA:42`). The element is "present" if it has at least one *live* tag.
- **remove(x):** record a *tombstone* for every tag of `x` that *this replica has currently observed*. Crucially, it tombstones only the tags it has *seen* — not future tags it doesn't know about.
- **merge:** union the add-tags and union the tombstones. An element is present iff it has an add-tag that is *not* in the tombstone set.

Now the add-wins property falls out. Suppose region A removes `x` (tombstoning the tags it saw), while region B *concurrently* adds `x` with a *new* tag B didn't know about. On merge:

- A's tombstones cover the old tags,
- but B's new add-tag is *not* tombstoned (A never saw it to tombstone it),
- so `x` has a live tag → `x` is present.

The concurrent add *won* over the remove, because the remove could only act on what it had observed. This is precisely the behavior a cart wants: "I removed this, but you concurrently re-added it" resolves to "it's in the cart" (the re-add is a real, recent intention). And the merge is commutative/associative/idempotent (it's set union on tags and tombstones), so it converges regardless of order — the join-semilattice property from Week 3, realized concretely.

The cost of this magic — and the thing Lecture 2 §2 dwells on — is the **tombstones**: every remove leaves a tombstone the set must remember forever (or until causally-stable GC), or else a stale replica's old add could resurrect a removed element. The convergence is paid for in tombstone metadata, and bounding that is the production discipline.

### 3.3 The PN-counter, and its footgun

The PN-counter (the type for two-way quantities) is two G-counters: one tracking total increments, one tracking total decrements, per actor. The value is `sum(increments) - sum(decrements)`. Concurrent increments from different regions all count (each actor tracks its own tally, and merge takes the max per actor), so "add 2 in A" and "add 3 in B" converge to +5 — both customers' adds preserved. That's correct for a *quantity*.

The footgun is modeling **removal** as a decrement. Consider: region A "removes all 2 apples" (decrement by 2), region B *concurrently* "adds 1 apple" (increment by 1), starting from 2. The PN-counter converges to `2 + 1 - 2 = 1`... or, if A's view of "all" was 2 but B had already made it 3, you can get arithmetic that doesn't match either customer's intent, and in some interleavings a *negative* count. The arithmetic is *convergent* but *semantically wrong*, because "remove what's there" is not the same as "subtract a fixed number" under concurrency. The fix (the senior move from §3.1): use **OR-set membership** for presence (a remove is observed-remove, not arithmetic) and reserve the counter for genuine monotonic-ish quantity, so a remove undoes *the specific adds it saw*, not *a number*. The homework makes you reproduce the negative-counter bug and fix it with the OR-set model — the per-field type choice, made painful and then correct.

---

## 4. When eventual consistency is the *right* consistency

The lecture's title question, answered directly. Eventual consistency (a CRDT) is the right choice when **all three** of these hold:

1. **The data can tolerate temporary divergence.** During a partition, region A and region B will have *different* cart states, and that's *fine* — the user in A sees their cart, the user in B sees theirs, and they reconcile on heal. If temporary divergence is unacceptable (a bank balance you must never show wrong), eventual consistency is wrong.
2. **Concurrent writes have a *correct merge*.** There's a type whose merge produces the intended value (OR-set for a cart, PN-counter for a counter). If there's *no* correct automatic merge (two address edits, an oversell-sensitive stock count), eventual consistency via a CRDT is wrong — you need siblings (Lecture 2) or strong consistency.
3. **You want availability and local latency over coordination.** The reason to pay the CRDT's metadata cost is to get *writes that never block on coordination* — every region writes locally, no quorum, no single-writer bottleneck, partition-tolerant. If you don't need that (the data lives fine in one region — Week 19's read-local/write-primary), you don't need a CRDT.

The cart hits all three: a cart tolerates temporary divergence (✔), has a correct merge (OR-set, ✔), and genuinely benefits from local writes in every region with no failover-RTO (✔). So the cart is a CRDT field. Inventory hits *none* of them (it can't tolerate divergence — that's overselling), so inventory is *not* a CRDT field. Same system, opposite answers, because the per-field reasoning is different. That per-field discrimination — not a blanket "we use CRDTs" — is the entire competence this week certifies.

---

## 4a. The CRDT type zoo, for reference

A compact reference of the common CRDT types and what each is for — keep it open when you're choosing a field's type:

| Type | What it is | Use it for | Watch out for |
|---|---|---|---|
| **G-counter** | increment-only counter (per-actor tallies) | a monotonic count (total views, total events) | can't go down |
| **PN-counter** | inc + dec (two G-counters) | a two-way quantity (cart qty, score) | modeling *removal* as decrement → can go wrong/negative |
| **G-set** | grow-only set | a set you only ever add to (audit log) | can't remove |
| **2P-set** | add + remove, but remove is permanent | a set where removed = gone forever | re-adding a removed element is impossible |
| **OR-set** | observed-remove set (add-wins) | a cart's items, tags, members | tombstone metadata growth |
| **LWW-register** | single value, newest timestamp wins | a presence timestamp, a "last editor" | DISCARDS concurrent writes — footgun for real data |
| **MV-register** | multi-value register (keeps siblings) | a value where conflicts must be surfaced | the app must resolve the siblings |
| **Sequence/RGA** | ordered list with concurrent inserts | collaborative text, ordered lists | the most metadata-heavy; Yjs/Automerge engineer this |
| **Map / document** | nested structure of the above | a whole cart/document (Automerge) | history/document growth |

The single most important row to internalize is the contrast between **OR-set** and **LWW-register**: both can represent "what's in the cart," but the OR-set merges concurrent adds (correct) and the LWW discards them (the footgun). Choosing between rows of this table *is* the per-field engineering. There is no "default CRDT"; there's the right type for each field's semantics.

Two rows people misuse most often, worth flagging:

- **2P-set is a trap for carts.** It looks like an OR-set ("add and remove"), but its removes are *permanent* — once you remove an item, you can *never* add it back. A cart needs re-adding (the user removed milk, then changed their mind); a 2P-set silently makes that impossible. Use OR-set, not 2P-set, for anything re-addable.
- **MV-register vs LWW-register.** Both are "single value," but the MV-register *keeps* concurrent writes as siblings (for the app to resolve) while the LWW *discards* all but the newest. If concurrent writes to the field are real data, you want MV-register (siblings), not LWW. LWW is only correct when discarding the older write is *intended*.

### 4a-bis. The five questions to ask of any field

When a colleague proposes "let's make this a CRDT," run the field through these five questions before agreeing:

1. **What *shape* is this field?** A set, a number, a single value, structured text? The shape narrows the type (table in §4a).
2. **Can two regions write it concurrently?** If no (single-writer), you may not need a CRDT at all — a normal value with one writer is simpler.
3. **If they do write concurrently, is there a *correct* merge?** Both adds survive (OR-set)? Both increments count (PN-counter)? If yes, name the type. If no, go to 4.
4. **If there's no correct auto-merge, can a human/app reconcile?** Then it's a sibling field (Lecture 2). If even that's unsafe, go to 5.
5. **Must the concurrent writes *not both succeed*?** (Overselling, double-charge.) Then it's *not* a CRDT field — it's strong consistency (Lecture 2 §3).

Answering these five, out loud, for each field is the discipline. It's quick, it catches the LWW footgun (a *set* answered at question 1 must not become an LWW at question 3), and it catches the strong-consistency field (question 5) that a blanket "we use CRDTs" would have silently corrupted. The competence isn't knowing CRDTs converge; it's running these five questions reflexively, per field.

A worked pass for the cart's fields, to show the questions in action:

- *items*: set (Q1) → concurrent yes (Q2) → correct merge: add-wins OR-set (Q3) → **OR-set**.
- *quantity*: two-way number (Q1) → concurrent yes (Q2) → correct merge: sum (Q3) → **PN-counter** (presence via the OR-set, not decrement).
- *last-modified*: single value (Q1) → concurrent yes (Q2) → correct merge: newest wins, discarding older is *intended* (Q3) → **LWW-register**.
- *shipping address*: single coherent value (Q1) → concurrent yes (Q2) → *no* correct auto-merge (Q3) → human can reconcile (Q4) → **siblings**.
- *inventory availability* (read dependency): a count that must-not-oversell (Q1) → concurrent writes must *not both succeed* (Q5) → **strong consistency, NOT a CRDT**.

One cart, five fields, five different answers — produced mechanically by the five questions. That is the per-field consistency map the mini-project asks you to build, and it's the artifact that proves you understand CRDTs are a per-field tool.

### 4b. The convergence-vs-correctness cheat sheet

```
CONVERGENCE  = all replicas reach the SAME value   (the type gives you this free)
CORRECTNESS  = that value is the INTENDED one        (YOU get this by picking the right type)

  converged + correct   ✔✔   OR-set cart: both adds kept
  converged + WRONG      ✔✘   LWW cart: converged, silently dropped a region's adds
  not converged          (just behind; will converge once updates propagate)

THE QUESTION (per field): does THIS type's merge produce the value users wanted?
  set of things      -> OR-set
  two-way number     -> PN-counter (presence via OR-set, not decrement)
  newest-wins value  -> LWW-register (ONLY when discarding older is intended)
  re-addable set     -> OR-set (NOT 2P-set: 2P removes are permanent)
  conflict-surfacing -> MV-register / siblings (app/user resolves)  [Lecture 2]
  no safe auto-merge -> siblings (app/user resolves)  [Lecture 2]
  must-not-diverge   -> NOT a CRDT; strong consistency [Lecture 2]
```

The mantra to repeat until it's automatic: **converged is not correct.** A green "the replicas agree" dashboard tells you the type's *math* worked; it tells you *nothing* about whether the agreed value is the one your users wanted. That second question — answered by the type you chose, per field — is the whole job. Every time you reach for a CRDT, you are really choosing which *flavor* of agreement you want, and the wrong flavor (LWW on a set) agrees beautifully on the wrong answer.

---

## 5. Recap

You should now be able to:

- Name the production CRDT stacks and what each is for: Automerge (rich JSON documents), Yjs (high-performance shared text/structured data), Redis Active-Active (primitive CRDT data types at the data tier) — and the documents-vs-primitives split.
- State strong eventual consistency precisely (same updates → same state, regardless of order) and what it requires (commutative/associative/idempotent merge; causal delivery for op-based).
- State, repeatedly and correctly, that **convergence is agreement, not correctness** — a LWW field converges *and* silently loses concurrent data.
- Choose the right CRDT per field (OR-set for cart items, PN-counter for counters, LWW only when discarding the older write is *intended*, siblings when auto-merge is wrong, strong consistency when divergence is unacceptable) and justify why the converged value is the intended one.
- Answer "when is eventual consistency the right consistency" with the three-part test (tolerates divergence + has a correct merge + wants local writes over coordination), and apply it to show the cart is a CRDT field and inventory is not.
- Explain the OR-set mechanism (unique add-tags + tombstones → add-wins), the PN-counter and its removal-as-decrement footgun, and the state-based vs op-based transport tradeoff.
- Read the CRDT type-zoo table and pick a type for a field by its *shape* (set → OR-set, two-way number → PN-counter, newest-wins → LWW, no-safe-merge → siblings, must-not-diverge → strong consistency).

The single sentence to leave with: **convergence is free and correctness is not — the type's merge gives you agreement, and your per-field type choice is what makes the agreed value the one users wanted.** Carry that into every CRDT decision: don't ask "will it converge" (it will); ask "will it converge to what we meant."

Next up: what to do when the CRDT's automatic merge is *not* the right policy — vector-clock-driven siblings and application-layer resolution — the metadata cost of convergence and how to bound it, and the fields where a CRDT is the *wrong* tool. Continue to [Lecture 2 — Conflict Resolution, Vector Clocks, Metadata, and Limits](./02-conflict-resolution-vector-clocks-metadata-and-limits.md).

---

## References

- *Shapiro et al. — Conflict-free Replicated Data Types (2011)*: <https://inria.hal.science/inria-00609399/document>
- *Automerge — documentation*: <https://automerge.org/docs/>
- *Yjs — documentation*: <https://docs.yjs.dev/>
- *Redis — Active-Active (CRDT) databases*: <https://redis.io/docs/latest/operate/rs/databases/active-active/>
- *Designing Data-Intensive Applications — Ch. 5 (Replication)*, Martin Kleppmann.
