# Lecture 2 — The CRDT Zoo, Metadata Growth, and CRDTs in Production

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can implement the canonical CRDTs (G/PN-counter, G/2P/OR-set, LWW/MV-register), explain the OR-set's add-wins tag mechanism, reason about metadata growth and how delta-CRDTs bound it, and name what Riak, Redis, and AntidoteDB chose and why.

Lecture 1 proved *why* CRDTs converge (the semilattice). This lecture is the *catalog* — the specific data types you reach for, the design choice each encodes, the metadata cost that is the CRDT world's central tax, and how production systems pay it. If you remember one sentence:

> **The OR-set is the production set CRDT because it tags every add with a globally-unique identifier so that a concurrent add-and-remove resolves *add-wins* — and the price of that correctness is metadata (tags and tombstones) that grows, which delta-CRDTs and causal-stability reclamation exist to bound.**

---

## Part 1 — The counters

### 1.1 G-counter (recap from Lecture 1)

Grow-only. State: per-replica counts. Increment your own entry; value = sum; merge = element-wise max. Converges because max is a join-semilattice. Use it for monotonic counts: page views, total likes-ever, anything that only goes up.

The reason it splits per replica (rather than a single shared integer) is essential: a single shared integer is *not* a CRDT — two replicas that both increment a shared `5` to `6` would merge to `6`, losing one increment. By giving each replica its own slot that only *it* writes, increments never collide, and merge (element-wise max) recovers the true per-replica maximum. The per-replica decomposition is what converts a non-mergeable counter into a mergeable one. This decomposition trick — "give each writer its own slot" — recurs throughout the zoo.

> **When G-counter is right:** any quantity that only ever increases and where you want the *total* across all replicas. Page-view counts, total-bytes-served, lifetime-likes. If it can decrease, you need a PN-counter; if "decrease" must respect a floor, you need coordination.

### 1.2 PN-counter

Increments *and* decrements, built from two G-counters: `P` (increments) and `N` (decrements). Value = `sum(P) − sum(N)`. Merge each component independently. Use it for counts that go up and down: a cart's quantity of an item, net votes, active-connection counts.

```python
class PNCounter:
    def __init__(self, replica_id, n):
        self.P = GCounter(replica_id, n)
        self.N = GCounter(replica_id, n)

    def increment(self, by=1): self.P.increment(by)
    def decrement(self, by=1): self.N.increment(by)   # decrement = increment N
    def value(self):          return self.P.value() - self.N.value()

    def merge(self, other):
        self.P.merge(other.P)
        self.N.merge(other.N)
```

> **The gotcha:** a PN-counter can go *negative* even if you "never decrement below zero" locally, because two replicas can each decrement concurrently and the merge sums both decrements. If "balance ≥ 0" is an invariant, a PN-counter **cannot enforce it** (Lecture 1 §5 boundary) — you need coordination or an escrow/reservation scheme. The PN-counter converges; it does not respect a floor.

---

## Part 2 — The sets (and the heart of the week)

### 2.1 G-set and 2P-set

- **G-set (grow-only set):** add only; merge = union. Converges trivially. But you can't remove.
- **2P-set (two-phase set):** add to one G-set `A`, remove by adding to a tombstone G-set `R`; element is present iff in `A` and not in `R`. Converges (two G-sets). **But:** once removed, an element can *never* be re-added (its tombstone is permanent). That "remove is forever" semantic is unacceptable for most uses (you can't re-add `milk` to a cart after removing it once). The 2P-set is a teaching step, not a production set.

### 2.2 OR-set — the production set CRDT

The **observed-remove set** fixes the re-add problem with one idea: **tag every add with a globally-unique identifier.**

- **Add(e):** generate a unique tag `t` (e.g., `(replica_id, counter)` or a UUID), and store `(e, t)` in the add-set.
- **Remove(e):** record the tags of `e` that this replica has *observed*, and put them in the remove-set (tombstones). You remove the *specific instances* you've seen, not the element abstractly.
- **Value:** `e` is present iff there exists at least one tag `(e, t)` in the add-set whose `t` is *not* in the remove-set.
- **Merge:** union the add-sets, union the remove-sets (both G-sets → converges).

The magic is **add-wins under concurrency.** Suppose replica A removes `milk` (observing tag `t1`) while, concurrently, replica B adds `milk` again (creating a *new* tag `t2`). On merge: the remove-set contains `t1`, the add-set contains `t1` and `t2`. Is `milk` present? Yes — because `t2` is in the add-set and *not* in the remove-set (A never observed `t2`; it didn't exist when A removed). The concurrent add *wins*, which is the intuitive and safe default: a remove only cancels the adds it actually saw, so a concurrent (unseen) add survives. And re-adding works fine, because each add is a fresh tag.

```python
class ORSet:
    def __init__(self, replica_id):
        self.id = replica_id
        self.counter = 0
        self.adds = set()      # set of (element, tag)
        self.removes = set()   # set of tags (tombstones)

    def _fresh_tag(self):
        self.counter += 1
        return (self.id, self.counter)   # globally unique: (replica, local seq)

    def add(self, e):
        self.adds.add((e, self._fresh_tag()))

    def remove(self, e):
        # Remove only the tags of e we have OBSERVED (add-wins on concurrency).
        observed = {tag for (elem, tag) in self.adds if elem == e}
        self.removes |= observed

    def value(self):
        live_tags = {tag for (e, tag) in self.adds} - self.removes
        return {e for (e, tag) in self.adds if tag in live_tags}

    def merge(self, other):
        self.adds |= other.adds          # union of add-sets (G-set)
        self.removes |= other.removes    # union of tombstones (G-set)
```

This is the CRDT you implement in the mini-project (the shopping cart). The add-wins semantic is exactly right for a cart: if you and a concurrent device both add an item, you keep it; if you remove an item but a concurrent device re-added it, the re-add wins (the customer wanted it). Internalize the tag mechanism — it is the single most important CRDT design pattern, and it generalizes (CRDT maps tag every key's value the same way).

### 2.2b A worked OR-set trace: concurrent add-and-remove

Walk the add-wins resolution step by step. Two replicas, A and B, both start with `milk` present (tag `(A,1)`).

| Step | Replica A adds/removes | Replica B adds/removes | A.adds | A.removes | B.adds | B.removes |
|---|---|---|---|---|---|---|
| 0 | start: milk present | start: milk present | {(milk,(A,1))} | {} | {(milk,(A,1))} | {} |
| 1 | A removes milk (observes (A,1)) | — | {(milk,(A,1))} | {(A,1)} | {(milk,(A,1))} | {} |
| 2 | — | B re-adds milk (new tag (B,1)) | {(milk,(A,1))} | {(A,1)} | {(milk,(A,1)),(milk,(B,1))} | {} |
| 3 | merge A ⊔ B | merge A ⊔ B | {(milk,(A,1)),(milk,(B,1))} | {(A,1)} | same | {(A,1)} |

After merge, both replicas hold adds `{(milk,(A,1)),(milk,(B,1))}` and removes `{(A,1)}`. Is `milk` present? The live tags are `{(A,1),(B,1)} − {(A,1)} = {(B,1)}`, which is non-empty — so **yes, milk is present.** The concurrent re-add `(B,1)` survived A's remove, because A only removed the tag it had *observed* (`(A,1)`), not the tag B created concurrently. That is **add-wins**, and it is exactly the behavior a user expects: "I removed it on my phone, but I'd just re-added it on my laptop — keep it." Trace this until it's reflexive; it is the single trickiest CRDT mechanic and the mini-project depends on it.

Contrast with a 2P-set: there, removing `milk` tombstones the *element* permanently, so B's re-add would be cancelled and `milk` would be **gone** — the wrong answer. The per-add unique tag is precisely what lets the OR-set distinguish "the milk I removed" from "the milk you concurrently re-added."

### 2.3 The metadata cost of the OR-set

Here is the tax. The OR-set's add-set and remove-set **only grow** — every add is a new tag forever, and every remove adds a tombstone forever. A cart that has had 10,000 add/remove operations carries 10,000 tags even if it currently holds 3 items. Left unbounded, the metadata dwarfs the data. This is the central operational problem of CRDTs, and §4 is how production bounds it.

---

## Part 3 — The registers

### 3.1 LWW-register (and why it's a footgun)

A **last-writer-wins register** holds a single value plus a timestamp. Merge keeps the value with the higher timestamp (ties broken by replica id). It converges (max on timestamps is a semilattice). But:

> **LWW silently discards concurrent writes.** Two replicas concurrently set the register to different values; merge keeps *one* (the higher timestamp) and *throws away the other*. The discarded write is gone with no signal. If the two writes were both meaningful (two users edited the same field), you lost one — and worse, if the timestamps come from wall clocks (Week 2!), *which* one you keep depends on clock skew, so the data loss is nondeterministic.

LWW is a *legitimate* choice when the field genuinely has "only the latest matters" semantics and concurrent writes to it are either impossible or acceptable to lose (a "last seen at" timestamp, a cache of a derived value). It is a **footgun** when concurrent writes carry information you cannot afford to lose. The skill is telling those cases apart — and the default assumption should be "LWW loses data; justify it," not "LWW is fine."

A concrete LWW data-loss demo (Challenge 1 makes you reproduce this):

```
Replica A:  set(profile_bio, "Loves hiking")    @ timestamp 100
Replica B:  set(profile_bio, "PhD candidate")    @ timestamp 101  (concurrent edit)
merge (LWW): keep timestamp 101 -> "PhD candidate"
RESULT: "Loves hiking" is GONE. The user who wrote it sees their edit vanish.
```

If those timestamps came from wall clocks on two machines (Week 2), then *which* edit survives depends on clock skew — slow down replica A's clock and "Loves hiking" wins instead. The data loss is real *and* nondeterministic. An MV-register would instead keep both as siblings and let the app say "you have two versions of your bio; which do you want?" — surfacing the conflict honestly instead of silently coin-flipping it away.

### 3.2 MV-register (multi-value)

When you *can't* afford to lose concurrent writes but the field is a single slot, use a **multi-value register**: on concurrent writes (detected by version vectors — Week 2!), it keeps *all* of them as **siblings**, and hands the application the set of concurrent values to resolve (show the user "you have two conflicting versions; pick one"). This is what Riak does with its default conflict model. The MV-register doesn't *solve* the conflict — it *surfaces* it honestly instead of silently picking, which is strictly better than LWW when the writes matter.

```python
class MVRegister:
    """Keeps concurrent writes as siblings using version vectors (Week 2)."""
    def __init__(self, replica_id, n):
        self.id = replica_id
        self.n = n
        # Each value carries the version vector at which it was written.
        self.values = []   # list of (value, version_vector)

    def write(self, value, current_vv):
        # A new write supersedes all values it causally dominates.
        survivors = [(v, vv) for (v, vv) in self.values
                     if not self._dominates(current_vv, vv)]
        self.values = survivors + [(value, current_vv)]

    def get(self):
        return [v for (v, vv) in self.values]   # one value, or several siblings

    @staticmethod
    def _dominates(a, b):
        return all(x >= y for x, y in zip(a, b)) and a != b
```

The LWW-vs-MV choice is the practical face of Lecture 1's "merge keeps both": LWW keeps one (lossy), MV keeps all (honest). The C22 capstone's cart uses an OR-set (not a register) precisely so it never faces this choice — sets merge by union, no LWW required.

---

## Part 3b — The CRDT catalog at a glance

Keep this table taped to your monitor; it is the "which CRDT" lookup you'll use for years.

| CRDT | State | Merge | Value | Use for | Watch out for |
|---|---|---|---|---|---|
| **G-counter** | per-replica counts | element-wise max | sum | views, total likes-ever | can't decrement |
| **PN-counter** | two G-counters (P, N) | merge each | sum(P)−sum(N) | net votes, item quantity | can go negative; no floor invariant |
| **G-set** | a set | union | the set | append-only logs, tags | can't remove |
| **2P-set** | add-set + remove-set | union both | adds − removes | teaching only | remove is **forever** |
| **OR-set** | tagged adds + tag tombstones | union both | live-tagged elements | carts, presence, the real set | metadata growth (tags/tombstones) |
| **LWW-register** | value + timestamp | higher timestamp wins | the value | "last seen", derived caches | **silently drops concurrent writes** |
| **MV-register** | values + version vectors | keep concurrent | one value or siblings | fields where conflicts must surface | app must resolve siblings |
| **CRDT map** | keys → nested CRDTs | merge per key | the map | documents, profiles | inherits children's metadata cost |

The decision flow: counts → counter (PN if it decrements); membership → OR-set; single-slot value where only the latest matters → LWW (justify it!); single-slot value where conflicts matter → MV-register; structured object → CRDT map composing the above. And always, *always* check the Lecture 1 §5 boundary first — if there's a reject-the-conflict invariant, no CRDT will do.

## Part 3c — Three CRDT misconceptions to kill

- **"OR-set tombstones don't matter; sets are small."** A cart's *current* contents may be three items, but its OR-set carries a tag for every add ever and a tombstone for every remove ever. Over a long-lived cart that is unbounded growth. Metadata is the CRDT tax; budget for it (delta-CRDTs + reclamation) or it will surprise you in production.
- **"LWW is simpler, so prefer it."** LWW is simpler *and lossy*. It silently discards concurrent writes, and with wall-clock timestamps (Week 2) the loss is nondeterministic. Prefer the CRDT whose merge keeps what matters; reach for LWW only when you can articulate why losing a concurrent write to this specific field is acceptable.
- **"A CRDT map is just a hash map."** No — every value in a CRDT map is itself a CRDT (a counter, an OR-set, a register), and the map merges per key by merging the nested CRDTs. The convergence and the metadata are inherited from the children. Treating it like a plain map and overwriting values reintroduces LWW data loss inside each key.

## Part 4 — Metadata growth and how to bound it

CRDTs trade coordination for metadata. The metadata is the price; here is how production keeps it from eating you alive.

### 4.1 The problem, named

- **Tombstones** (removed-element markers) accumulate in OR-sets, 2P-sets, and sequence CRDTs.
- **Tags** accumulate (one per add).
- **State size** in state-based CRDTs is the *whole* state shipped on every merge — expensive even before tombstones.

### 4.2 Delta-state CRDTs

Instead of shipping the *whole* state on every merge, **delta-CRDTs** ship only the *delta* — the part that changed since the last sync — and merge the delta into the remote state. The delta is itself a small CRDT, so all the convergence guarantees hold; you've just made the *messages* small. This is the single most important production optimization for state-based CRDTs: it turns "ship a 10 MB cart state to gossip one added item" into "ship the one added item." Riak and Redis CRDTs are delta-optimized for exactly this reason.

### 4.3 Tombstone reclamation via causal stability

You cannot delete a tombstone the moment you remove an element — a replica that hasn't seen the remove yet could re-introduce the element. But once *every* replica has observed a remove (the remove is **causally stable** — no replica can ever again send a message concurrent with it), the tombstone is safe to garbage-collect. Detecting causal stability requires tracking what every replica has seen (a matrix of version vectors), which is itself metadata — so reclamation is a tradeoff, not free. Production systems run reclamation periodically, accepting bounded tombstone growth between sweeps.

### 4.4 Dotted version vectors

A plain version vector can't distinguish multiple *concurrent* writes from the *same* replica (a server accepting two concurrent client requests). **Dotted version vectors** add a "dot" (a single extra event) to the vector so each write is identified precisely, which is what lets a server-side OR-set or MV-register track concurrent client writes without conflating or over-growing. You don't need to implement them this week, but recognize the name: it's the metadata refinement that makes server-coordinated CRDTs (Riak's model) tractable.

---

### 4.5 Measuring the growth (what the mini-project does)

You will *measure* OR-set metadata growth in the mini-project. The shape to expect:

```
ops performed   live items   add-set size   remove-set size   bytes (approx)
       10              4            7               3            ~ 0.5 KB
      100             12           70              58            ~ 5 KB
    1,000             15          640             625            ~ 50 KB
   10,000             18        6,400           6,382          ~ 500 KB
```

Notice: **live items stays small (~tens) while metadata grows linearly with total operations.** A cart you actively use for a year could carry hundreds of KB of tags to represent a handful of items. That is the curve you must respect. The two levers:

1. **Delta-CRDTs** cut the *per-merge bandwidth* (ship the delta, not the 500 KB), but do **not** shrink the stored state.
2. **Causal-stability reclamation** cuts the *stored state* by GC-ing tombstones everyone has seen, but costs metadata to track who's seen what.

A production cart applies both: delta-sync on the wire, periodic reclamation on disk. The mini-project's stretch goal implements reclamation so you can *watch the curve bend back down* after a GC sweep — the most satisfying graph in the week.

### 4.6 The op-based escape from metadata

One reason op-based CRDTs (CmRDT) are sometimes chosen despite their stricter delivery requirement: they can have **less metadata**, because they don't need to keep the whole history of tags for the merge to work — the reliable causal-broadcast layer guarantees each op is delivered once, so you don't need idempotence-via-tags. The tradeoff reappears: op-based pushes the cost from *metadata* (state-based) onto the *delivery layer* (causal broadcast). There is no free lunch; you move the cost, you don't remove it. Choosing between them is choosing *where* you'd rather pay.

## Part 5 — CRDTs in production

A quick orientation before the specifics — these systems sit on a spectrum from "CRDTs bolted onto a KV store" to "CRDTs as the whole design philosophy":

| System | What it is | CRDT role | Delivery model |
|---|---|---|---|
| **Riak** | AP key-value store | First-class data types (counter/set/map/register/flag) | State-based, gossip |
| **Redis Active-Active** | Geo-distributed Redis | CRDT semantics on standard types | State-based, region sync |
| **AntidoteDB** | Research transactional store | CRDTs + highly-available transactions | Op-based with causal delivery |
| **Automerge / Yjs** | Client-side CRDT libraries | The entire data model is a CRDT | Op-based, peer sync |

With that map, the details:

### 5.1 Riak (the Bet365 case study)

Riak ships production CRDTs (counters, sets, maps, registers, flags) as first-class "data types." The famous case study is **Bet365**, a betting platform that moved high-availability state onto Riak CRDTs to stay available under partition during peak load — when being down costs real money every second. The lesson from their experience: CRDTs delivered the availability, but the team had to *think hard about the metadata* and about which state was CRDT-appropriate versus which needed coordination. CRDTs are a power tool, not a free lunch — they remove the coordination cost and replace it with a metadata-management cost.

### 5.2 Redis Active-Active (CRDB)

Redis Enterprise's **Active-Active** (formerly CRDB) databases are geo-distributed and use CRDTs under the hood so that the same key can be written in multiple regions and converge. Counters, sets, hashes, and strings get CRDT semantics. The selling point is exactly the AP-with-convergence story: write locally in every region, never coordinate cross-region on the write path, converge by merge.

### 5.3 AntidoteDB

A research-grade database that combines **CRDTs with highly-available transactions** (transactional causal consistency) — proving you can have *some* transactional grouping over CRDTs without giving up availability. The frontier of "how much consistency can you keep while staying AP."

### 5.3b When production teams reach for CRDTs — and when they don't

The honest 2026 field guidance, distilled from the case studies:

**Reach for CRDTs when:**
- You need **multi-region active-active** writes (write locally everywhere, converge by merge) — the cart-service capstone case.
- You're building **local-first / offline-capable** apps where each device edits independently and syncs later (collaborative editors, mobile apps with offline mode).
- The state is naturally **commutative** (counters, sets, presence) and any merged accumulation is valid.

**Do NOT reach for CRDTs when:**
- You have a **reject-the-conflict invariant** (uniqueness, non-negative balance, fixed inventory). Use consensus or a single writer (Lecture 1 §5). A CRDT will converge to an *invalid* state.
- A **single-leader** design is acceptable and simpler. If you don't need multi-master writes, don't pay the CRDT metadata tax — a Raft-backed single leader (Week 2) is simpler and gives you linearizability.
- The **metadata cost** would dominate (huge state, high churn, no reclamation budget). Sometimes the right answer is "coordinate; it's cheaper than the metadata."

The senior framing: **CRDTs are a specialized tool for the AP-multi-master corner, not a default.** Most services are fine with a single-leader CP store (Postgres, etcd). You reach for CRDTs when the *availability* requirement genuinely forbids coordination on the write path — and then you accept the metadata cost as the price of that availability. Reaching for CRDTs because they're interesting, when a single leader would do, is over-engineering that you'll pay for in metadata and debugging.

### 5.4 Automerge and Yjs (collaborative editing)

The local-first / collaborative-editing world runs on CRDTs: **Automerge** (a JSON CRDT) and **Yjs** (a fast CRDT for editors) power real-time collaborative documents, where two users typing concurrently must converge to the same text. This is the hardest CRDT problem (sequence CRDTs with interleaving and garbage collection — Kleppmann's "CRDTs: The Hard Parts"), and it's where most CRDT research energy now goes. Your cart is the easy case; collaborative text is the PhD case.

---

## 6. Recap

You should now be able to:

- Implement **G-counter**, **PN-counter**, **G/2P/OR-set**, **LWW-register**, and **MV-register**, and state the semantics each encodes.
- Explain the **OR-set's add-wins tag mechanism**: unique tags per add, remove only observed tags, so a concurrent add survives a concurrent remove — and why it fixes the 2P-set's "remove is forever" trap.
- Identify **LWW as a footgun** (silent loss of concurrent writes, nondeterministic with wall-clock timestamps) and reach for an **MV-register** or a set CRDT when concurrent writes matter.
- Reason about **metadata growth** (tombstones, tags) and the three mitigations: **delta-CRDTs** (small messages), **causal-stability reclamation** (bounded tombstones), and **dotted version vectors** (precise per-write identity).
- Name what **Riak, Redis Active-Active, AntidoteDB, and Automerge/Yjs** chose and why, and that CRDTs trade coordination cost for metadata cost.

The single most important takeaway to carry forward: **a CRDT removes the coordination cost of staying available under partition and replaces it with a metadata cost — and the OR-set's add-wins tag mechanism is the canonical example of paying that metadata to get correct, lossless concurrent semantics.** When you build the cart in the mini-project, you are paying tags and tombstones to never lose a customer's item, and the metadata you measure is the receipt for that guarantee. That trade — coordination for metadata — is the defining characteristic of the CRDT approach, and recognizing it lets you decide, for any AP data flow, whether the metadata price is worth the availability it buys.

## 5b. How this closes Phase 1's theory arc

Step back and see the three weeks as one argument:

- **Week 1 (CAP/PACELC/FLP):** under partition you choose CP or AP; the AP choice leaves divergent replicas; and consensus (the CP machinery) pays a liveness tax to FLP.
- **Week 2 (clocks + consensus):** the CP path, built — logical clocks to order without a wall clock, Raft to agree despite FLP, vector clocks to *detect* concurrency.
- **Week 3 (CRDTs):** the AP path, completed — convergent data types that *resolve* the concurrency vector clocks detected, with no coordination and no data loss.

You now hold **both** paths. For any piece of distributed state, you can ask the PACELC question (Week 1), and if the answer is "AP, available under partition," you can choose between *LWW* (lossy, simple) and a *CRDT* (lossless, metadata-heavy) — and if the answer is "CP, must reject conflicts," you reach for *consensus* (Week 2). That decision — CP-consensus vs AP-CRDT vs AP-LWW, made per data flow with a named justification — is the synthesis of the entire theory phase, and it is exactly what the capstone's service-by-service consistency choices demand. The cart is an AP-CRDT; inventory is CP-consensus; the two coexist in one system because you reasoned about each data flow separately. That is the whole skill.

## 5c. The one question that picks the path

For any mutable distributed state, ask in order:

1. **Can two replicas concurrently update this, both meaningfully?** No → single writer / CP is simplest. Yes → continue.
2. **Can merging both updates ever violate an invariant?** Yes → you need **coordination** (consensus); a CRDT will converge to an invalid state. No → continue.
3. **Is losing a concurrent write to this field acceptable?** Yes → **LWW** is fine (cheap). No → **CRDT** (lossless, pay the metadata).

Three questions, and you've placed any piece of state correctly: single-writer-CP, consensus, LWW, or CRDT. Most production bugs in this space come from skipping question 2 (using a CRDT where coordination was needed) or answering question 3 wrong (using LWW where the writes mattered). Asking them explicitly, in order, is the senior contribution this week trains.

Next: the exercises put this in your hands — classify six problems by the right CRDT, implement the zoo and prove convergence, and property-test the semilattice laws. Continue to [the exercises](../exercises/README.md).

---

## References

- *Conflict-free Replicated Data Types* — Shapiro et al. (2011): <https://inria.hal.science/inria-00609399/document>
- *A comprehensive study of CRDTs* (the OR-set, the catalog) — Shapiro et al. (2011): <https://inria.hal.science/inria-00555588/document>
- *Delta State Replicated Data Types* — Almeida, Shoker & Baquero (2016): <https://arxiv.org/abs/1603.01529>
- *Dotted Version Vectors* — Preguiça et al.: <https://arxiv.org/abs/1011.5808>
- *Riak data types*: <https://docs.riak.com/riak/kv/latest/developing/data-types/>
- *Redis Active-Active*: <https://redis.io/docs/latest/operate/rs/databases/active-active/>
- *CRDTs: The Hard Parts* — Kleppmann (2020 talk).
- *Automerge* — JSON CRDT for local-first apps: <https://automerge.org/>
- *Yjs* — the CRDT behind many collaborative editors: <https://yjs.dev/>
