# Lecture 1 — CAP and the Consistency Lattice: What "Consistency" Actually Means

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can state the CAP theorem the way Gilbert and Lynch proved it, explain why "CA" is not a coherent category for a networked system, and place a real database on the lattice of consistency models — linearizable, sequential, causal, eventual — without conflating any two of them.

If you remember one sentence from this entire lecture, remember this one:

> **CAP is not a menu where you "pick two of three." It is a statement about one specific moment — the instant a network partition occurs — at which a system spanning that partition must choose between answering requests with possibly-stale data (availability) or refusing them to avoid being wrong (consistency). The rest of the time, CAP says nothing at all.**

Every misuse of CAP traces back to ignoring those two facts: that it is conditioned on a partition, and that "CA" — consistent and available but not partition-tolerant — describes a system that simply does not tolerate the network failing, which on any real network means a single machine. The moment your state lives on two machines connected by a fallible link, your menu is exactly two items: CP or AP. This lecture makes that precise and then gives you the vocabulary — the consistency lattice — to say something far more useful than a two-letter label.

---

## 1. The history, briefly, because the history is the misunderstanding

In 2000, Eric Brewer gave a keynote at the PODC conference (Principles of Distributed Computing) in which he conjectured that a distributed system can provide at most two of three properties: **C**onsistency, **A**vailability, and **P**artition tolerance. He drew a triangle. The triangle was a teaching device. It was never meant to be read as "all three corners are symmetric options and you freely pick two."

In 2002, Seth Gilbert and Nancy Lynch (the same Lynch of FLP, which we meet in Lecture 2) **proved** a precise version of the conjecture. Their proof is what made CAP a theorem. And their proof is also what shows the triangle is the wrong shape: partition tolerance is not a property you *choose* — it is a property of the *world*. Networks partition. You do not get to opt out of packet loss. So the real content of CAP is conditional: **given that partitions happen, when one happens, choose C or A.** "CA" is the corner you reach only by assuming partitions never occur, which is the same as assuming a single node.

In 2012 Brewer himself wrote "CAP Twelve Years Later," whose entire thesis is "the 2-of-3 framing is misleading; here is what I actually meant." When the author of a model spends a paper walking back the popular reading of it, you should take the hint. Read Gilbert–Lynch for the proof, read Brewer's retrospective for the intent, and never draw the triangle again.

---

## 2. The CAP theorem, stated precisely

Gilbert and Lynch give each word a formal meaning. You must use *these* meanings, because the everyday meanings of "consistency" and "availability" are far looser and the looseness is where the errors live.

### 2.1 Consistency = linearizability

In CAP, **consistency means linearizability** (also called atomic consistency). Informally: the system behaves as if there is a single copy of the data, and every operation appears to take effect instantaneously at some point between its invocation and its response, in an order consistent with real time. If a write completes at 12:00:00.000 and a read begins at 12:00:00.001, that read must see the write (or something newer). There is no "I read a slightly old value because my replica hadn't caught up" — that is precisely what linearizability forbids.

This is a **strong** notion of consistency. It is *not* the "C" of ACID (which is about preserving invariants within a transaction); it is *not* "the data isn't corrupted." It is a statement about the *ordering* of reads and writes as observed by clients.

### 2.2 Availability = every request to a live node gets a non-error answer

In CAP, **availability means** that every request received by a **non-failing** node must result in a response — not an error, not a timeout-forever, but an actual answer. Crucially, the definition says nothing about *latency*: a system that takes a year to answer is "available" by this definition. (PACELC will fix that omission.) And the answer is allowed to be *stale* — availability does not require correctness, only liveness of the response.

### 2.3 Partition tolerance = the network may drop arbitrarily many messages

**Partition tolerance** means the system continues to function even when the network arbitrarily drops or delays messages between groups of nodes. A partition splits the nodes into groups that cannot communicate. Note: a partition need not be a clean "cable cut." A slow link that delays every message past every timeout is, operationally, a partition. A garbage-collection pause that freezes a node for ten seconds looks, to everyone else, exactly like that node being partitioned away.

### 2.4 The theorem and its one-line proof sketch

> **Theorem (Gilbert–Lynch).** It is impossible in an asynchronous network to implement a read/write register that is both **available** and **linearizable** (consistent) in all executions in which messages may be lost (i.e., under partition tolerance).

The proof is short enough to hold in your head. Picture two nodes, **G₁** and **G₂**, each holding a replica of a single value, initially `v0`. The network partitions: no messages get through between them.

1. A client writes `v1` to **G₁**. To stay **available**, G₁ must accept and acknowledge the write — it cannot wait for G₂, because no message reaches G₂.
2. A client reads from **G₂**. To stay **available**, G₂ must answer. But G₂ never heard about `v1` (the partition ate the message), so it answers `v0`.
3. The read returned `v0` after a write of `v1` completed. That violates **linearizability** — a linearizable read after the write must return `v1` or newer.

So if the system is available on both sides of the partition, it cannot be linearizable. To be linearizable, at least one side must refuse to answer (sacrificing availability). **You cannot have both during the partition.** That is the entire theorem. Four sentences.

Here is the same proof as a diagram. Draw it yourself once and it is yours forever:

```
   Client A                 Client B
      │                         │
   write(v1)                 read()
      │                         │
      ▼                         ▼
  ┌────────┐    X (partition)  ┌────────┐
  │  G₁    │  ╳╳╳╳╳╳╳╳╳╳╳╳╳╳  │  G₂    │
  │ v0→v1  │   message dropped │  v0    │   ← never heard about v1
  └────────┘                   └────────┘
      │                            │
   ack v1  ◄── must answer to     answer v0  ◄── must answer to
   (available)   stay available    (available)    stay available
                                       │
                                       ▼
                          read returned v0 AFTER write(v1) completed
                          → NOT linearizable. Contradiction.

   To be linearizable, G₂ must instead REFUSE to answer (wait for G₁),
   which sacrifices AVAILABILITY. You cannot have both. ∎
```

The act of drawing two boxes, a dropped arrow, and the two operations is the single fastest way to make CAP permanent in your mind. Exercise 1 and the lab make you reproduce it in code.

A reading checklist to apply whenever a system claims "consistent and available":

1. **Which consistency model?** (Linearizable? Or a weaker model the word is hiding?)
2. **Available in the CAP sense, or just good uptime?** (Does every live node answer *during a partition*, or does the minority error out?)
3. **What is the partition behavior, explicitly?** (CP: minority refuses. AP: everyone answers, may diverge.)
4. **Where do I read from?** (Leader = strong; async replica = eventual. The *read target* often sets the model.)
5. **Per-request or per-system?** (Is consistency a fixed property or a knob like `ConsistentRead`/consistency level?)

Five questions, asked in order, dismantle almost any over-broad consistency claim. The rest of this lecture equips you to answer each one.

### 2.5 Why "CA" is a category error

Given the proof, the three CAP "categories" really mean:

- **CP** — under partition, sacrifice **A**vailability. The minority (or one side) stops answering to avoid returning stale or divergent data. *Examples:* etcd, ZooKeeper, HBase, a single-leader Postgres with synchronous replication that blocks on the follower.
- **AP** — under partition, sacrifice **C**onsistency. Both sides keep answering; they may diverge and must reconcile later. *Examples:* Cassandra, DynamoDB (in its default mode), Riak.
- **CA** — sacrifice **P**artition tolerance. This is only possible if partitions never happen, i.e., a **single node** (or a system that simply gives up — crashes or becomes unavailable — the instant the network misbehaves, which is just CP with a worse failure mode).

"CA" is therefore not a design point you reach by clever engineering on a distributed system. It is what a single-machine database is. The instant you replicate across a network, partition tolerance is forced on you by physics, and your only real axis is CP↔AP. Anyone selling you "CA at scale" is selling you a single point of failure with a marketing budget.

---

## 3. The word "consistency" is overloaded — here is the lattice

CAP's "C" is *one specific* consistency model (linearizability). In the wild, "consistency" is used for at least four genuinely different guarantees, and conflating them is the single most common reasoning error in system design. Here is the lattice, from strongest to weakest. Stronger models *imply* weaker ones: a linearizable system is also causal and eventual; the converse fails.

### 3.1 Linearizable (strongest, single-object)

There is a single, **real-time-respecting** total order of operations on the object. Every read returns the result of the most recent completed write in real time. This is CAP's "C." It is what `etcd` gives you for a key, what a single-leader database gives you for reads served by the leader, and what you implicitly assume whenever you write `x = 1; assert read(x) == 1` and expect it to hold across machines.

Linearizability is a **per-object** (per-register) property in its classic form. Composing linearizable objects does not automatically give you a linearizable *multi-object* system; that requires more (transactions, or strict serializability).

### 3.2 Sequential

There is a single total order that all clients agree on, **but it need not respect real time.** If client A's write finishes (in wall-clock time) before client B's write starts, a *linearizable* system guarantees everyone sees A before B; a merely *sequential* system may legally order B before A, as long as *everyone* sees the same order and each client's own operations appear in program order. Lamport defined this for shared-memory multiprocessors. Practically, sequential consistency is rarer as an explicit guarantee in databases, but it is the right name for "single agreed order, no real-time promise."

### 3.3 Causal (the sweet spot for many systems)

Operations that are **causally related** (one *could have* influenced the other — A wrote, B read A's write and then wrote again) are seen in that order **everywhere**. Operations that are **concurrent** (neither could have seen the other) may be seen in different orders by different replicas. Causal consistency is the strongest model you can have while remaining **available under partition** — this is a deep result (the CAC theorem / Mahajan et al.), and it is why causal+ consistency is the target for many AP systems that still want to avoid the chaos of pure eventual consistency. The "happens-before" relation that defines causality is the heart of next week's logical clocks.

A concrete payoff: causal consistency gives you **read-your-writes** ("after I post a comment, I see my comment"), **monotonic reads** ("I never see time go backwards"), and **writes-follow-reads** ("if I reply to a message, nobody sees my reply before the message"). Those three session guarantees are what users actually *feel*; full linearizability is often more than the UX needs.

### 3.4 Eventual (weakest useful guarantee)

**If writes stop, all replicas eventually converge** to the same value. That is the *entire* promise. It says nothing about what you read *while* writes are ongoing — you may read stale data, you may read values out of order, you may read your own write and then not read it on the next request (a violation of read-your-writes that eventual consistency permits). Eventual consistency is the AP baseline. CRDTs (Week 3) are the discipline that makes eventual consistency *predictable* by guaranteeing convergence to a *well-defined* merged value rather than an arbitrary last-writer-wins coin flip.

### 3.5 The lattice as a picture

```
        STRONGER (more coordination, less available under partition)
            │
   Linearizable        ── real-time total order; CAP's "C"; CP systems
            │
   Sequential          ── single agreed total order, no real-time promise
            │
   Causal (causal+)    ── causal order preserved; concurrent ops may differ;
            │              the strongest model available under partition
   Eventual             ── replicas converge if writes stop; says nothing during writes
            │
        WEAKER (less coordination, fully available under partition)
```

The session guarantees — read-your-writes, monotonic reads, monotonic writes, writes-follow-reads — live *between* causal and eventual; they are useful named points you can promise a client without paying for full causality across the whole system.

> **The discipline this lecture demands:** when someone says "the system is consistent," your reflex must be *"which model?"* Linearizable and eventual are not two flavors of the same thing; they are at opposite ends of a lattice and differ by enormous amounts of coordination cost and availability. Naming the model is the difference between an engineer and someone reciting a buzzword.

---

## 4. Reading a real system onto the lattice

Let us place systems you have used. This is the muscle Exercise 1 drills.

| System | Default consistency for a single key | Notes |
|---|---|---|
| **etcd / ZooKeeper** | Linearizable (writes; reads linearizable if you ask) | Built on Raft/Zab. CP: minority stops serving under partition. |
| **Single-leader Postgres** (reads from leader) | Linearizable on the leader | Reads from async replicas are only *eventual*. The replica is where people get fooled. |
| **Spanner** | Externally consistent (≈ linearizable, globally) | Uses TrueTime to bound clock skew and wait it out; effectively PC/EC. |
| **DynamoDB** (default eventually-consistent reads) | Eventual | Offers an opt-in *strongly consistent read* per request — read the API, not the brand. |
| **Cassandra** | Tunable | `QUORUM` reads+writes can give strong-ish guarantees; `ONE` is eventual. The *configuration* picks the model. |
| **Riak** | Eventual (with CRDTs for convergence) | AP by design; the Week 3 case study. |
| **Redis (single instance)** | Linearizable-ish (single-threaded) | But Redis *replication* is async — failover can lose acknowledged writes. The cluster story is weaker than the single-node story. |

Two lessons jump out of that table:

1. **The brand name is not the consistency model.** DynamoDB and Cassandra both let you pick per-request. "Postgres is strongly consistent" is true for the leader and false for an async replica. You must read the *configuration and the specific API call*, not the logo.
2. **Where you read from changes the model.** The most common production consistency bug is reading from an asynchronous replica and assuming you got linearizable data. You got *eventual* data. The replica lag is the staleness window, and under load that window grows exactly when you least want it to.

---

## 5. A worked example: the read-from-replica trap

Here is a bug that has shipped at every company you have heard of. A service writes a user's new email to the Postgres primary, gets an OK, then immediately issues a "confirm your settings" read — but the read is load-balanced to an **asynchronous read replica** that has not yet received the write. The read returns the *old* email. The user sees their change "didn't take," refreshes (hitting a different replica, or the same one after it caught up), and now it's there. Intermittent, unreproducible, maddening.

Name the failure with this week's vocabulary:

- The system was advertised internally as "consistent" (everyone trusts Postgres).
- The *primary* is linearizable. The *replica* is **eventual** — it converges, but the read happened inside the convergence window.
- The user expected **read-your-writes**, a session guarantee that an async replica does not provide.

The fix is a consistency-model decision, not a code patch: either route reads-after-writes to the primary (pay latency for linearizability — the "EL vs EC" PACELC choice in Lecture 2), or make the replica session-consistent by tracking the write's log position and only serving the read from a replica that has caught up to it (read-your-writes without paying full linearizability everywhere). Both are defensible. "Add a retry and hope" is not — it is reciting that you don't understand the model.

```go
// The trap, in pseudo-Go. The bug is the load balancer's choice of read target,
// not anything visible in this function.
func UpdateEmail(ctx context.Context, db *Cluster, userID, newEmail string) error {
    if err := db.Primary().Exec(ctx,
        "UPDATE users SET email=$1 WHERE id=$2", newEmail, userID); err != nil {
        return err
    }
    // DANGER: db.AnyReplica() may route to a replica behind the write above.
    // That read is EVENTUAL, not linearizable. Read-your-writes is NOT guaranteed.
    got, _ := db.AnyReplica().QueryRow(ctx,
        "SELECT email FROM users WHERE id=$1", userID)
    // got may still be the OLD email. This is not a Postgres bug; it is a
    // consistency-model mismatch between what we assumed and what we configured.
    _ = got
    return nil
}
```

The corrected version names its choice explicitly:

```go
// Option A — pay latency for linearizability: read your own write from the primary.
got, _ := db.Primary().QueryRow(ctx,
    "SELECT email FROM users WHERE id=$1", userID)

// Option B — read-your-writes without full linearizability: remember the write's
// log position (LSN) and only accept a replica that has replayed at least that far.
lsn := db.Primary().LastWriteLSN()
replica := db.ReplicaCaughtUpTo(lsn) // blocks/falls back to primary if none caught up
got, _ = replica.QueryRow(ctx, "SELECT email FROM users WHERE id=$1", userID)
```

Both are correct. The point is that you *chose*, and you can say which consistency model each option provides.

---

## 6. Availability is not uptime, and consistency is not correctness

Two vocabulary traps that catch experienced engineers:

- **CAP "availability" ≠ your SLA uptime.** Your dashboard's "99.95% available" is an operational uptime metric. CAP availability is a formal "every request to a live node returns a non-error answer, no matter how slow." A CP system (etcd) can have wonderful operational uptime and still be "not available" in the CAP sense during a partition, because the minority deliberately returns errors. These are different words that happen to share spelling.
- **CAP "consistency" ≠ ACID "C" ≠ "the data is correct."** ACID's C is "transactions preserve declared invariants." CAP's C is linearizability of a register. "Correct data" is a third thing entirely (often integrity constraints + application logic). When a vendor says "strongly consistent," ask *which* consistency, because the word is doing at least three jobs.

Keep these straight and half of all distributed-systems arguments dissolve, because most of them are two people using the same word for different things.

---

## 6b. Quorums: the mechanism that buys consistency back

How does a system *implement* the CP side — staying linearizable across replicas — without a single point of failure? The answer is **quorums**, and understanding them now makes the consensus material in Week 2 land softly instead of cold.

A **quorum** is a subset of replicas whose agreement is required to commit (for a write quorum) or to be consulted (for a read quorum). With `N` replicas, a write quorum of size `W` and a read quorum of size `R`, the magic inequality is:

```
W + R > N      (every read quorum overlaps every write quorum)
W > N/2        (write quorums overlap each other -> no two conflicting writes commit)
```

The first inequality is the one that buys you read-your-writes: if every read consults `R` replicas and every write touches `W`, and `W + R > N`, then any read quorum and any write quorum share *at least one* replica — so a read is guaranteed to see at least one replica that has the latest write. The classic choice is `N = 3, W = 2, R = 2`: `2 + 2 = 4 > 3`. A majority write quorum (`W = 2 > 3/2`) also guarantees two writes cannot both commit on disjoint sets, which is what prevents split-brain divergence.

Now connect this to CAP. Under a partition that isolates one of three nodes, the 2-node majority side can still form a write quorum of 2 (`W = 2`) — it makes progress, **linearizably**. The 1-node minority cannot reach `W = 2` — it has no quorum, so in CP mode it *refuses*. That refusal is the sacrifice of availability, and the quorum inequality is *why* it is safe to refuse: the minority knows it might be missing a write that committed on the majority side, so answering would risk a stale read.

This is the deep reason "CA" is incoherent and CP is achievable: a quorum system *embraces* partition tolerance (it expects some replicas to be unreachable) and chooses consistency by refusing to act without a quorum. It does not pretend partitions don't happen; it plans for them. Your mini-project this week implements exactly this 2-of-3 quorum, and Week 2's Raft is a quorum protocol with a leader bolted on to make the ordering efficient.

One subtlety worth internalizing: **plain `W + R > N` quorums are not fully linearizable by themselves.** Concurrent writes, partial writes that reach some but not all of `W`, and read-repair timing can all produce edge cases (Kleppmann's DDIA §9 walks through them). Real linearizable systems add a *total order* on top — a leader, or a consensus round per operation — which is why etcd uses Raft rather than bare Dynamo-style quorums. Quorums give you the overlap guarantee; consensus gives you the ordering guarantee; linearizability needs both.

## 6c. Strict serializability: linearizability for transactions

Linearizability is a *single-object* property. The moment you have **transactions** over multiple objects, you need its multi-object cousin: **strict serializability** = serializability (transactions appear to execute in *some* serial order) + linearizability (that order respects real time). Spanner's "external consistency" is exactly strict serializability at global scale.

Why does this matter for reading systems? Because a database can be *serializable* (a strong isolation level) without being *linearizable* across real time, and the gap shows up as "stale snapshot" reads. Snapshot isolation, for instance, reads from a consistent point-in-time snapshot — serializable-ish for many workloads — but a long-running read transaction can return data that was already overwritten in real time. That is not a bug; it is the isolation level doing what it promises. When you audit a system (this week's challenge), you must say *both* its single-object consistency model *and* its multi-object isolation level, because "consistent" without both numbers is half an answer. The Bailis "Highly Available Transactions" paper is the map of which isolation levels survive a partition and which force you off the AP corner.

## 7. What CAP does *not* tell you

CAP is a real result, but it is narrow. Be precise about its limits so you don't over-apply it:

- **CAP only speaks during a partition.** Most of the time there is no partition, and CAP is silent. The steady-state tradeoff — latency vs consistency when the network is healthy — is invisible to CAP. That is exactly the gap PACELC fills, and it is the more *frequently relevant* tradeoff, because partitions are rare and every-request latency is constant. (Lecture 2.)
- **CAP is about a single register.** Real systems have transactions across many objects, where strict serializability, snapshot isolation, and a zoo of weaker isolation levels live. CAP does not directly characterize those; the Bailis "Highly Available Transactions" paper maps which isolation levels survive a partition.
- **The labels are coarse.** Kleppmann's "please stop calling databases CP or AP" argues — correctly — that "CP" and "AP" hide enormous variation, and that you should name the *consistency model* and the *failure behavior* instead. Use CAP to *start* the conversation; use the lattice to *finish* it.

---

## 7b. The five misconceptions that survive a CS degree

These are the CAP errors that show up in design reviews from otherwise-strong engineers. Name them so you can catch them — in others and in yourself.

**Misconception 1: "Pick any two of CAP."** No. Partition tolerance is not optional on a network, so you are picking one of {C, A} *conditional on a partition*. The free choice among three is the single most damaging sentence in the field. Whenever you hear it, mentally rewrite it to "under partition, C or A."

**Misconception 2: "We chose AP, so we're always available and that's a pure win."** AP buys availability *under partition* at the cost of consistency *under partition* — and that inconsistency does not vanish when the partition heals. It becomes a **reconciliation problem**: divergent replicas that must be merged, with the ever-present risk that last-writer-wins silently discards a real write (you saw this in Exercise 2 and will fix it with CRDTs in Week 3). "We're AP" is not "we're free"; it is "we have signed up to handle conflicts correctly, forever."

**Misconception 3: "Strong consistency means my data is safe."** Linearizability is about *ordering*, not *durability*. A linearizable system can still lose your data if it acknowledges a write before it is durably replicated and then the leader crashes. Consistency (ordering) and durability (survival) are orthogonal axes; a system can have either without the other. Always ask both questions.

**Misconception 4: "Adding more replicas makes us more consistent."** More replicas make you more *durable* and can improve read throughput, but they make linearizability *harder* and *slower* (more nodes to coordinate, larger quorums, more chances for one to be partitioned). Consistency cost rises with replica count; it does not fall. The instinct "more copies = safer = more consistent" conflates three different properties.

**Misconception 5: "Partitions are so rare we can ignore CAP."** Partitions are rarer than people fear but far more common than people hope — and crucially, a partition is *anything that looks like one*: a GC pause, an overloaded NIC, a misconfigured security group, a slow disk that backs up the network buffers, a Kubernetes node going `NotReady`. You do not get to ignore CAP because "the network is reliable"; you get to *choose your behavior* for the moment it isn't, and that moment will come. PACELC's reminder that the EL/EC tradeoff is paid *constantly* is the deeper reason you can't ignore any of this.

## 7c. One sentence you can take into any review

Compress the whole lecture into a single sentence you can deploy when a design review goes vague:

> *"Name the consistency model for this data, name where we read it from, and name what happens to it during a partition — and if any of those three is 'I'm not sure,' that's the risk we're actually reviewing."*

Everything above is in service of being able to say that sentence and then *answer your own three questions* for the system on the whiteboard. Linearizable vs eventual; leader vs replica; CP vs AP. Three nouns, and you have replaced a marketing adjective with an engineering specification.

## 8. Recap

You should now be able to:

- State the CAP theorem as Gilbert and Lynch proved it: under partition, a distributed register cannot be both available and linearizable, and reproduce the two-node, one-dropped-message proof from memory.
- Explain why **CA** is a category error for a networked system — partition tolerance is forced by the world, leaving CP↔AP as the only real axis.
- Name and order the four consistency models — **linearizable**, **sequential**, **causal**, **eventual** — and the session guarantees that sit between causal and eventual.
- Recognize the read-from-async-replica trap as a consistency-model mismatch (eventual where you assumed linearizable) and prescribe a model-aware fix.
- Keep CAP-availability, SLA-uptime, CAP-consistency, ACID-consistency, and "correct data" as five distinct ideas, not one overloaded word.

## 9. Field guide: the four session guarantees, because they are what users feel

Between causal and eventual sit four named **session guarantees** (Terry et al., the Bayou paper — which returns as a Week 3 reading). They are cheaper than full causal consistency and far more meaningful to a user than "eventual." A senior engineer reaches for these constantly, because they let you promise a *specific* user-visible property without paying for global ordering.

- **Read-your-writes (RYW).** After you write a value, your own subsequent reads see that value (or newer). The canonical violation: you change your profile photo, the next page load shows the old one because it hit a lagging replica. The fix is per-session, not global: route your reads to a replica that has your write, or pin you to the primary for a short window after a write.
- **Monotonic reads.** Once you have read a value, you never read an *older* value afterward — time does not go backwards for you. Violation: you refresh a comment thread and a comment that was there *disappears* because the second read hit a more-stale replica. Fix: pin a session to a single replica (or to replicas at least as fresh as your last read).
- **Monotonic writes.** Your writes are applied in the order you issued them. Violation: you set `x=1` then `x=2`, but a replica applies them out of order and settles on `x=1`. Fix: order a session's writes (a per-session sequence number).
- **Writes-follow-reads (WFR).** If you read a value and then write, your write is ordered *after* the write you read. Violation: you read a question, post an answer, and someone sees your answer before the question. Fix: carry the read's version into the write's causal context.

Why this is the practical payoff of the whole lecture: **most products do not need linearizability; they need these four guarantees for a session.** Linearizability is global, expensive, and availability-hostile under partition. The session guarantees are local, cheap, and *available* — and they cover the overwhelming majority of "the UI feels broken" consistency complaints. When a product manager says "users say their changes don't stick," the precise diagnosis is almost always "we are not providing read-your-writes," and the fix is a session-routing decision, not a database migration. Naming the exact guarantee turns a vague complaint into a one-line architectural change.

A compact map of where everything sits, strongest to weakest, with the cost axis made explicit:

| Model | Promise | Coordination cost | Available under partition? |
|---|---|---|---|
| Linearizable | One real-time total order | High (quorum/leader per op) | No (CP) |
| Sequential | One agreed total order, no real-time | High | No |
| Causal+ | Causal order preserved everywhere | Medium (track causality) | **Yes** — the strongest that is |
| Read-your-writes + monotonic reads/writes + WFR | Per-session sanity | Low (session routing) | Yes |
| Eventual | Converges if writes stop | Lowest | Yes |

That table is the lecture in one picture: as you move down, you pay less coordination and gain partition-availability, and you cross the linearizable→causal line exactly where CAP forces the AP choice. Pick the *weakest* model that still satisfies the product, and name it. That is the whole discipline.

Next up: PACELC fills CAP's steady-state blind spot, FLP draws the hard floor under what consensus can promise, and the safety/liveness distinction tells you which kind of guarantee each result is really about. Continue to [Lecture 2 — PACELC, FLP, and Safety vs Liveness](./02-pacelc-flp-safety-liveness.md).

---

## References

- *Brewer's Conjecture and the Feasibility of Consistent, Available, Partition-Tolerant Web Services* — Gilbert & Lynch (2002): <https://groups.csail.mit.edu/tds/papers/Gilbert/Brewer2.pdf>
- *CAP Twelve Years Later: How the "Rules" Have Changed* — Brewer (2012): <https://www.infoq.com/articles/cap-twelve-years-later-how-the-rules-have-changed/>
- *Linearizability: A Correctness Condition for Concurrent Objects* — Herlihy & Wing (1990): <https://cs.brown.edu/~mph/HerlihyW90/p463-herlihy.pdf>
- *Please stop calling databases CP or AP* — Kleppmann (2015): <https://martin.kleppmann.com/2015/05/11/please-stop-calling-databases-cp-or-ap.html>
- *Designing Data-Intensive Applications*, Ch. 9 — Kleppmann (2017).
- *Consistency Models* — Jepsen interactive lattice: <https://jepsen.io/consistency>
