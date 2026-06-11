# Lecture 2 — PACELC, FLP, and Safety vs Liveness

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can apply PACELC to separate the partition-time tradeoff from the every-request tradeoff, state the FLP impossibility result and the three escape hatches real systems use to route around it, and classify any guarantee in a spec as a safety property or a liveness property.

Lecture 1 left CAP with two admitted blind spots: it only speaks *during* a partition, and it says nothing about *latency*. Both blind spots matter more in practice than the partition case, because partitions are rare and latency is paid on every single request. **PACELC** fixes the first two. Then we descend to the hardest floor in the field — **FLP** — which tells you that consensus itself cannot be both always-safe and always-terminating in an asynchronous network, and we examine the three engineering tricks that make Raft and Paxos work anyway. Finally we sharpen the lens that makes all of this legible: the **safety vs liveness** distinction, which is the single most clarifying idea for reading any distributed-systems guarantee.

---

## Part 1 — PACELC: CAP plus the steady state

### 1.1 The reformulation

In 2012, Daniel Abadi published a one-page reformulation that has aged better than CAP itself:

> **PACELC:** **if** there is a **P**artition, then trade **A**vailability against **C**onsistency (this is CAP); **e**lse — in normal operation, with the network healthy — trade **L**atency against **C**onsistency.

Read it as a conditional with two branches. The **PA/PC** branch is just CAP: what does the system do when the network splits? The **EL/EC** branch is the part CAP forgot: what does the system do *the rest of the time*, when there is no partition but you still must decide whether to coordinate (pay latency for consistency) or skip coordination (pay inconsistency for latency)?

Make the "else" branch concrete before we generalize. Imagine a 3-replica system with replicas in Virginia, Oregon, and Frankfurt, and a client in Virginia issuing a read. There is **no partition** — the network is perfectly healthy. The client still faces a choice:

- **Read from the local Virginia replica** (`EL`): ~1 ms, but that replica might be a few milliseconds behind the latest write committed via a quorum that didn't include it. You get speed and accept a small staleness window.
- **Read with a quorum / through the leader** (`EC`): the read must contact a majority — say Virginia + Oregon — costing a cross-country round trip (~60 ms) to *prove* it has the latest value. You get linearizability and pay the latency.

Nothing here involves a partition. The network is fine. The tradeoff is purely "do I coordinate (slow, correct) or not (fast, maybe stale)," and it is paid on *every single read forever*. That is the EL/EC axis, and CAP is completely blind to it because CAP only speaks during partitions. PACELC's whole contribution is putting that 60-ms-vs-1-ms decision on the map.

Why does the "else" branch exist at all? Because **strong consistency costs round trips even with a healthy network.** To serve a linearizable read in a replicated system, you generally must confirm you are still the leader, or contact a quorum, or wait out a clock-uncertainty bound. Each of those is latency you pay on *every* request, partition or no partition. A system can legitimately decide: "in normal operation I will answer from the nearest replica without coordinating (low **L**atency, weaker **C**onsistency) and only pay for consistency when explicitly asked." That decision is invisible to CAP and central to PACELC.

### 1.2 The four corners

Combine the two binary choices and you get a four-way taxonomy. A system is labeled by its partition behavior **and** its steady-state behavior:

| Label | Under partition | Normal operation | Meaning |
|---|---|---|---|
| **PA/EL** | Available (may be inconsistent) | Low latency (may be inconsistent) | "Always answer fast; consistency is best-effort." |
| **PC/EC** | Consistent (may be unavailable) | Consistent (pay latency) | "Always correct, even if it costs availability or latency." |
| **PA/EC** | Available under partition | Consistent in normal operation | "Stay up when split, but coordinate fully when healthy." |
| **PC/EL** | Consistent under partition | Low latency in normal operation | "Refuse rather than diverge when split, but skip coordination when healthy." |

A way to remember which corner is which, by the question each corner answers "yes" to:

- **PA/EL** — "Will you always answer me fast?" → Yes, always; correctness is best-effort. (Dynamo lineage.)
- **PC/EC** — "Will you always be correct?" → Yes, always; I'll pay availability and latency for it. (Raft systems, Spanner.)
- **PA/EC** — "Stay up under partition, but be fully correct when healthy?" → Yes. (Rarer; some configurations of primary-based systems.)
- **PC/EL** — "Refuse rather than diverge under partition, but be fast when healthy?" → Yes. (PNUTS, the classic example.)

### 1.3 Real systems, classified

This is the table you should be able to reproduce and defend (Exercise 1 grades exactly this):

| System | PACELC | Why |
|---|---|---|
| **DynamoDB** (default) / **Cassandra** (`ONE`) / **Riak** | **PA/EL** | Stays available under partition; serves from nearest replica fast in normal operation; consistency is eventual unless you opt in per-request. |
| **etcd / ZooKeeper / HBase** | **PC/EC** | Raft/Zab: the minority refuses to serve under partition (PC); reads/writes coordinate through the leader/quorum in normal operation (EC). |
| **Spanner** | **PC/EC** | Globally consistent via TrueTime; the consistency "wait" is paid as latency even with a healthy network. The canonical PC/EC system that engineered the latency down rather than away. |
| **PNUTS** (Yahoo) | **PC/EL** | The classic PC/EL example from Abadi's paper: consistent under partition for its primary, but optimized for low latency in normal operation. |
| **MongoDB** (default majority writes) | **PC/EC**-leaning | A single primary; writes with `majority` concern coordinate; reads can be tuned toward EL with `readPreference`/`readConcern`. The *configuration* moves it. |

The two takeaways mirror Lecture 1's: **the corner is set by configuration, not the brand**, and **the "E" branch is the one you pay for constantly**. A system that is PC/EC is paying coordination latency on every operation in exchange for never being wrong; a PA/EL system is fast and occasionally wrong and asks you to handle the occasionally. Neither is "better." The job is to name which one you have and confirm it matches what the product needs.

### 1.3b A worked PACELC decision, end to end

Abstract taxonomies are useless until you run one. Suppose you are designing the **read path for a product catalog** at a marketplace (this is, not coincidentally, the kind of decision the C22 capstone makes for real). Walk PACELC:

1. **Is there a partition right now?** Almost never. So the decision that governs 99.99% of requests is the **E** branch: latency vs consistency on a healthy network.
2. **The E choice.** A product's price and description change rarely (minutes-to-hours between edits) and are read constantly. Serving a catalog read from the nearest replica, accepting that it may be a few seconds stale, shaves tens of milliseconds off every request and removes a coordination round trip. The staleness cost is *invisible to users* — nobody notices a price is 3 seconds old. **Choose EL.** Name the staleness budget: "catalog reads may be up to 5 seconds stale." Write it down; it is now a measurable SLO, not a vibe.
3. **The P choice.** During a (rare) partition, do you keep serving catalog reads or refuse them? Refusing to show products because a replica can't reach the primary is catastrophic for revenue; a slightly stale catalog is fine. **Choose PA.**
4. **Result: PA/EL** for the catalog read path, with a written 5-second staleness budget.

Now do the **same exercise for the checkout/payment path** and watch the answer flip:

1. **E branch:** a stale read of "is this item in stock" or "what is the account balance" can double-sell inventory or double-charge a card. The staleness cost is *not* invisible — it is money and trust. **Choose EC**: pay the coordination latency to read the authoritative value.
2. **P branch:** during a partition, would you rather refuse a checkout or risk selling something twice? For payments, refuse. **Choose PC.**
3. **Result: PC/EC** for checkout, even in the *same system* as the PA/EL catalog.

The lesson that separates seniors from juniors: **PACELC is a per-data-flow decision, not a per-system one.** The same marketplace correctly runs its catalog reads PA/EL and its payment ledger PC/EC. A team that picks "we're a Cassandra shop, everything is PA/EL" has applied a system-level brand to a path that needed EC, and they will discover it as a double-charge incident. Walk PACELC per path, name the staleness budget where you chose EL, and you have made the tradeoff *legible and defensible* — which is the entire skill this course is teaching.

### 1.3c Spanner: the PC/EC system that engineered the latency down, not away

The most instructive PACELC data point is Google **Spanner**, because it refuses the usual escape. Most systems that want low latency choose EL and accept staleness. Spanner is **PC/EC** — globally consistent (externally consistent / strict-serializable) — and it pays the consistency cost as *latency on every commit*. The interesting engineering is *how it makes that latency tolerable rather than pretending it isn't there.*

The mechanism is **TrueTime**: an API that returns not a timestamp but a *bounded interval* `[earliest, latest]` within which the true time provably lies, backed by GPS receivers and atomic clocks in every datacenter. Spanner assigns each transaction a commit timestamp and then **waits out the uncertainty** — it deliberately delays the commit until it is certain the chosen timestamp is in the past everywhere (`commit_wait`). That wait is typically a handful of milliseconds, because the clock-uncertainty bound is small. By *bounding* clock skew instead of *denying* it, Spanner converts "we cannot agree on time" (the problem that makes global linearizability seem impossible) into "we can agree on time to within ε, so we wait ε." The EC latency is real, named, and minimized — not hidden.

Why this matters for your PACELC literacy: Spanner proves the EC corner is not a death sentence for latency *if* you are willing to spend (a lot of) engineering on the constant factor. It also proves the opposite of the lazy reading of CAP — "globally consistent and available is impossible." Spanner is globally consistent and *highly available in practice* because Google's network partitions rarely and its quorums are well-placed; CAP still applies (during a true partition the minority is unavailable), but the **frequency** of that case is engineered down to near-zero while the EC latency is engineered down to milliseconds. Spanner is the existence proof that the PACELC corner you land in is a *design choice with a cost you can pay down*, not a fixed property of the universe. When someone says "you can't have strong consistency at global scale," the one-word answer is "Spanner," followed by "and here is what it cost them."

### 1.4 Why PACELC is the more useful day-to-day tool

Partitions are rare — a well-run datacenter network partitions a handful of times a year. The **EL/EC** decision is exercised on **every request, forever.** So while CAP is the dramatic result you cite in interviews, PACELC's "else" branch is the one that actually governs your p99 latency and your staleness budget in production. When you choose to read from a local replica to shave 40 ms off the tail, you are making an EL choice and accepting a staleness window. Name it. Budget it. That is senior-level reasoning; "we use Cassandra because it's fast" is not.

---

## Part 2 — FLP: the impossibility under the impossibility

### 2.1 What consensus is

**Consensus** is the problem of getting a set of processes to agree on a single value, subject to three properties:

- **Agreement:** no two correct processes decide different values.
- **Validity:** the decided value was proposed by some process (you can't decide a value nobody suggested).
- **Termination:** every correct process eventually decides.

Consensus is the beating heart of every coordination system. Everything below reduces to it:

- **Leader election** — agree on *which* node is the leader.
- **Atomic commit** — agree on commit-or-abort across participants.
- **Replicated log ordering** (Raft, Paxos) — agree on the order of entries in the log.
- **Distributed locks / leases** — agree on who holds the lock.
- **Membership / configuration changes** — agree on the current set of nodes.

If you can solve consensus you can build all of those; if you can't, none of them are safe. This is why FLP is not an academic curiosity — it sits underneath *every* coordination primitive you will ever operate.

### 2.2 The FLP result

In 1985, Fischer, Lynch, and Paterson proved:

> **Theorem (FLP).** In an **asynchronous** distributed system, there is no **deterministic** consensus protocol that guarantees **agreement, validity, and termination** if even **one** process may **crash**.

Read the qualifiers carefully, because every word is load-bearing and every word is also an escape hatch:

- **Asynchronous** — there is no bound on message delay or relative process speed. You cannot set a timeout and *know* that a node which hasn't responded is dead rather than slow. This is the crux.
- **Deterministic** — the protocol makes choices as a function of its state and messages, with no coin flips.
- **One crash** — the result needs only a *single* potential failure. It is not about Byzantine adversaries or floods of failures; one possible crash is enough to break termination.

The thing FLP forbids is **guaranteed termination**, not safety. A correct consensus protocol in an asynchronous network can always stay **safe** (it will never let two processes decide different values), but it cannot **guarantee** it will always *decide at all* — there exists an (adversarial, infinitely unlucky) execution in which it runs forever without deciding. FLP is, at its core, a **liveness** impossibility. Hold that thought; Part 3 makes it precise.

### 2.3 Why it's true: the bivalence argument, in plain English

The proof's machinery is the notion of a configuration's **valence**:

- A configuration (the global state) is **bivalent** if, from it, the protocol *could* still decide either 0 or 1 depending on how the schedule unfolds. The outcome is not yet locked in.
- It is **univalent** (0-valent or 1-valent) if the outcome is already determined no matter what happens next.

The proof shows two things. First, **a bivalent initial configuration must exist** — by a continuity/adjacency argument over the possible inputs, you can always find an input assignment where flipping one process's input flips the eventual decision, and somewhere on that boundary sits a bivalent start. Second, and this is the killer: **from any bivalent configuration, the adversary scheduler can always force the system into another bivalent configuration** by carefully choosing which single message to deliver next (delaying the one message that would tip the system into a univalent state). Because the system was asynchronous, the scheduler is *allowed* to delay that pivotal message arbitrarily.

Chain those together: start bivalent, and the scheduler keeps you bivalent forever, delivering messages in an order that never lets the system commit to a decision. The protocol stays safe — it never decides *wrongly* — but it never decides at all. That infinite undecided execution is the violation of termination. **That is FLP.** No determinism plus asynchrony plus one crash possibility equals "an adversarial network can stall consensus forever."

The bivalence argument as a picture:

```
   Some INITIAL configuration is BIVALENT
   (either 0 or 1 is still reachable)
            │
            ▼
   ┌────────────────────────────────────────────┐
   │  Adversary scheduler's move:                │
   │  the configuration is bivalent, so there    │
   │  EXISTS a next message whose delivery keeps  │
   │  it bivalent. The scheduler delays the one   │
   │  message that would make it univalent, and   │
   │  delivers the bivalence-preserving one.      │
   └────────────────────────────────────────────┘
            │
            ▼
   STILL BIVALENT  ──────────► (repeat forever)
            │
            ▼
   The protocol NEVER reaches a decision.
   It stays SAFE (never decides 0 and 1), but it
   never TERMINATES. That infinite run is the
   liveness violation. ∎
```

The asynchrony assumption is what licenses "the scheduler delays the one message" — in a synchronous network the scheduler could not stall a message indefinitely, which is exactly why the partial-synchrony escape works.

### 2.4 The three escape hatches — how real systems live with FLP

FLP does **not** say "consensus is impossible." It says "deterministic consensus cannot *guarantee termination* in a *fully asynchronous* network." Every word is a door:

**Escape 1 — Partial synchrony (timeouts).** Drop the "fully asynchronous" assumption. Dwork, Lynch, and Stockmeyer's *partial synchrony* model says: the network is asynchronous for a while, but **eventually** becomes timely (messages arrive within some bound after some unknown point). Under partial synchrony, consensus *is* solvable. This is what **Raft and Paxos actually do**: they use **timeouts** to *suspect* a crashed leader and elect a new one. The timeout is a bet — "if I haven't heard from the leader in 150 ms, I'll assume it's dead and start an election." FLP guarantees this bet is *sometimes wrong* (the leader was just slow, and now you have a needless election, even a brief dueling-leaders situation), but partial synchrony guarantees that *eventually* the network is calm enough that an election succeeds and the system makes progress. Raft trades **guaranteed** termination for **eventual** termination — exactly the trade FLP says you must make. It never sacrifices safety: even during a chaotic election storm, Raft never commits two different values for the same log slot.

**Escape 2 — Randomization.** Drop "deterministic." If processes can flip coins, randomized consensus protocols (Ben-Or 1983, and modern descendants used in some BFT and blockchain systems) terminate with **probability 1** — meaning the probability of running forever is zero, even though no *finite* bound is guaranteed. The adversary can no longer pin the schedule to keep you bivalent, because it can't predict your coin flips. You give up a hard deadline; you get "terminates almost surely."

**Escape 3 — Failure detectors.** Chandra and Toueg showed that consensus becomes solvable if you assume an (unreliable) **failure detector** with certain properties — most famously **◇S** ("eventually strong"): it may make mistakes for a while but eventually correctly suspects crashed processes and stops suspecting correct ones. A failure detector is really an *abstraction* of the timeout escape hatch — "assume some oracle eventually tells you who's dead" — and the weakest failure detector for consensus, **◇W**, draws the precise line of what assumption you minimally need.

The three escape hatches side by side, so you can recognize which one a system uses:

| Escape | Assumption dropped | What you get | What you give up | Used by |
|---|---|---|---|---|
| **Partial synchrony** | "fully asynchronous" | Termination once the network is eventually timely | A hard deadline (elections may churn while the network is rough) | Raft, Paxos/Multi-Paxos, Zab, Viewstamped Replication — i.e., **every production coordination system** |
| **Randomization** | "deterministic" | Termination with probability 1 | A finite worst-case bound (it terminates *almost surely*, not by a deadline) | Ben-Or, randomized BFT, some blockchain consensus |
| **Failure detectors** | "no oracle about crashes" | Termination given a ◇S/◇W detector | The need to *assume* an (eventually) accurate crash oracle | The theoretical framing of the timeout approach (Chandra–Toueg) |

Notice that partial synchrony and failure detectors are two views of the *same* practical trick — "use timeouts, assume the network eventually behaves." Randomization is the genuinely different door, and it is the one blockchains lean on because they cannot assume a cooperative network or trust a timeout in an adversarial setting. For the systems you will operate in this course (etcd, Consul, the Raft you build next week), the answer is always partial synchrony: a tunable election timeout that bets a silent leader is dead.

> **The senior framing:** FLP is not a wall you crash into; it is a tax you pay. Every consensus system you operate — etcd, ZooKeeper, Consul, CockroachDB's Raft groups — has *chosen* the partial-synchrony escape (timeouts), which is why **leader-election timeouts are a tuning knob** and why a flaky network produces election churn rather than data corruption. The system stays *safe* through the churn; FLP only took its *liveness guarantee*, and the timeout bet buys back liveness whenever the network behaves. Next week you implement exactly this in Raft.

---

### 2.5 FLP in the operations room: what the tax actually feels like

You will operate FLP's consequences long before you prove its theorem. Here is what the liveness tax looks like on a real on-call rotation, so the abstraction connects to a pager.

**Election storms.** An etcd or Consul cluster on a flaky network produces *leader-election churn*: the followers' timeouts fire, they start elections, a leader is elected, the network hiccups again, the timeout fires again. To an operator this looks like "the cluster keeps re-electing and writes pause for a few hundred milliseconds at a time." That pause **is** FLP's liveness tax being paid: the system is choosing to stall (lose liveness briefly) rather than risk two leaders committing different values (lose safety). Tuning the election timeout is tuning *how aggressively the system bets that a silent leader is dead.* Too short, and a momentarily slow leader triggers needless elections (more churn). Too long, and a genuinely dead leader leaves the cluster leaderless and write-unavailable for longer. There is no setting that eliminates the tradeoff — FLP guarantees that — there is only a setting that fits your network's timeliness profile.

**The slow-vs-dead indistinguishability, concretely.** A 12-second stop-the-world garbage-collection pause on a Java-based coordinator (a real and famous failure mode) is, to every other node, *identical* to that coordinator being dead. The peers cannot tell "paused" from "crashed" — that is precisely the asynchrony FLP assumes. They time out, elect a new leader, and resume. Then the paused node wakes up *still believing it is the leader* and tries to act. This is the **fencing problem**, and it is why every correct lock and lease carries a monotonic **fencing token** that the storage layer checks — so the resurrected old leader's writes are rejected. (You implement fencing tokens next week; for now, notice that the *entire need* for fencing flows directly from FLP's slow-vs-dead indistinguishability.)

**Why your consensus system never corrupts data during this chaos.** Through every election storm and GC pause, etcd never commits two different values for the same log index. The churn is annoying (a liveness symptom); the log stays correct (safety intact). That asymmetry — chaotic liveness, pristine safety — is the signature of a system that made the FLP-mandated choice correctly. If you ever operate a "consensus" system that *corrupts* data under network stress, it did not pay the tax honestly; it traded safety for liveness, which is the cardinal sin Part 3 names.

## Part 3 — Safety vs liveness: the lens that organizes everything

### 3.1 The definitions

Lamport (1977) gave the cleanest classification of properties:

- A **safety** property says **"nothing bad ever happens."** Formally: if the property is violated, it is violated by a **finite prefix** of the execution — there is a specific bad moment after which no future can redeem it. *Examples:* "two processes never decide different values" (consensus agreement), "a lock is never held by two holders," "a committed transaction is never lost," "a read never returns a value that was never written."
- A **liveness** property says **"something good eventually happens."** Formally: it can only be violated by an **infinite** execution — at any finite point, the good thing *could still* happen later. *Examples:* "the consensus eventually decides" (termination), "every request eventually gets a response" (CAP availability), "the leader election eventually completes."

A quick test to tell them apart, which you can run in your head: **imagine you froze the system right now and looked at the execution so far.** If you could already point at a moment and say "there — it's ruined, no future can fix it," the property is **safety**. If you can never say that — if at every finite moment the good thing *could* still happen later — it's **liveness**. "Two leaders committed conflicting values" can be ruined at a finite moment (safety). "The election will eventually finish" can never be *proven failed* by a freeze-frame, only by an infinite run that never finishes (liveness). The freeze-frame test is the fastest way to classify a guarantee you've never seen before.

The deep theorem (Alpern & Schneider, 1985) is that **every property is the intersection of a safety property and a liveness property.** So any guarantee you read in a spec decomposes into "what bad thing it forbids" and "what good thing it promises eventually." Training yourself to do that split is the most transferable skill in this entire course.

### 3.2 Why the distinction reorganizes the whole week

Apply the lens and the week's three results snap into focus:

- **FLP is a liveness impossibility.** Consensus protocols keep their **safety** property (agreement — never decide two values) for free, even in a fully asynchronous network. What FLP steals is the **liveness** property (termination — always eventually decide). That is *why* the escape hatches work: they don't repair safety (it was never broken); they buy back liveness under extra assumptions (eventual timeliness, randomness, a failure detector). Understanding FLP as "liveness tax, safety intact" is the difference between fearing it and operating around it.
- **CAP availability is a liveness property** ("every request eventually gets a non-error response"). Linearizability (CAP consistency) is largely a **safety** property ("a read never returns a stale/out-of-order value"). CAP is therefore, at its heart, a statement that under partition you cannot keep this particular safety property *and* this particular liveness property simultaneously. Same structure as FLP, different setting.
- **The design heuristic that falls out:** when you build distributed systems, **never sacrifice safety to buy liveness.** A system that occasionally stalls (a liveness hiccup — an election, a retry, a brief unavailability) is annoying. A system that occasionally returns wrong, divergent, or lost data (a safety violation) is *broken*, and the breakage is often silent and unrecoverable. Raft makes exactly this choice: it will happily stall (no progress during an election storm) rather than ever violate log-agreement. Mature systems are conservative on safety and only relax liveness. When you see a design that relaxes safety to chase availability or latency, that is the moment to ask very hard questions.

### 3.3 The classifier, as a habit

For any guarantee you encounter, ask:

1. **Is it a safety or a liveness property?** (Can a finite prefix violate it → safety. Only an infinite execution → liveness.)
2. **Under what failure model does it hold?** (No failures? One crash? Partition? Byzantine?)
3. **Is it conditional?** (Like CAP's "during a partition" or PACELC's "else.")

Run those three questions on every line of a database's consistency documentation and you will catch the exact place where a vendor's prose slides from a firm safety guarantee ("we never lose an acknowledged write") to a hopeful liveness one ("writes are usually replicated within milliseconds") — and that slide is almost always where the operational surprise lives.

---

### 3.4 A worked safety/liveness catalog

Run the classifier (Part 3) on a dozen real guarantees so the split becomes automatic. For each, ask: *can a finite prefix of the execution violate it?* If yes → safety. If only an infinite execution can → liveness.

| Guarantee | Safety or liveness? | Why |
|---|---|---|
| "No two replicas commit different values for log index `i`" | **Safety** | Violated the instant both commits exist — a finite, identifiable bad moment. |
| "Every submitted write eventually replicates to all replicas" | **Liveness** | At any finite point it *could* still replicate later; only never-replicating violates it. |
| "A committed transaction is never lost" (durability) | **Safety** | One lost commit is a finite witness. |
| "A read never returns a value that was never written" | **Safety** | The bad read is a finite witness. |
| "Leader election eventually completes" | **Liveness** | Can be delayed forever by an adversarial schedule (FLP), but no finite prefix proves failure. |
| "A held lock is never granted to a second holder" (mutual exclusion) | **Safety** | Two simultaneous holders is a finite bad state. |
| "A process waiting for the lock eventually gets it" (no starvation) | **Liveness** | Starvation is only provable over an infinite run. |
| "Acknowledged writes are linearizable" | **Safety** (mostly) | An out-of-order observed read is a finite violation. |
| "Every request to a live node eventually gets a response" (CAP availability) | **Liveness** | A slow-forever response, not a wrong one, is the failure. |
| "The system never deadlocks" | **Safety** | A deadlocked state is a finite, identifiable configuration. |
| "Messages are delivered in causal order" | **Safety** | An out-of-causal-order delivery is a finite witness. |
| "The queue eventually drains" | **Liveness** | Only an infinite never-draining run violates it. |

Two patterns jump out once you've done a dozen. First, **most "correctness" properties are safety; most "progress" properties are liveness** — "never does the wrong thing" vs "eventually does the right thing." Second, **the properties you can guarantee unconditionally are the safety ones**; the liveness ones almost always come with an asterisk ("under partial synchrony," "if the network eventually delivers," "assuming no infinite failures"). That asterisk is FLP's fingerprint. When you read a spec, the liveness guarantees are where the fine print lives, and the fine print is where the 3 a.m. page is born.

### 3.5 The "is it actually wait-free / lock-free?" tangent

A small but career-useful corollary of the safety/liveness lens shows up in concurrent (single-machine) programming, and it is the same idea wearing different clothes. **Lock-freedom** and **wait-freedom** are *liveness* progress guarantees:

- **Wait-free:** every operation completes in a bounded number of steps regardless of other threads (the strongest liveness — no thread can be starved).
- **Lock-free:** *some* thread always makes progress (the system as a whole advances), but an individual thread can be starved.
- **Obstruction-free:** a thread makes progress if it runs in isolation.

These are exactly liveness properties — they constrain *progress*, not *correctness*. The correctness of a concurrent object (linearizability, from Lecture 1, which Herlihy defined in the *same* line of work) is the *safety* half. So a concurrent data structure has a safety story (is it linearizable?) and a liveness story (is it lock-free?), and they are independent — you can have a linearizable structure that is only blocking, or a lock-free structure that is not linearizable. The fact that the same safety/liveness decomposition organizes both distributed consensus *and* single-machine concurrent data structures is not a coincidence; it is why Herlihy and Lynch's names recur across both literatures. Once you see the decomposition, you see it everywhere.

## Part 4 — Putting CAP, PACELC, and FLP together

A single picture connects the week:

```
                         Is the network partitioned right now?
                                       │
                ┌──────────────────────┴──────────────────────┐
               YES (rare)                                     NO (almost always)
                │                                              │
        CAP / PACELC-P branch                         PACELC-E branch
        Choose: Availability  ──or──  Consistency     Choose: Latency ──or── Consistency
        (AP: answer, may diverge)     (CP: refuse)     (EL: don't coordinate)  (EC: coordinate)
                │                                              │
                └───────────────── and underneath BOTH branches ──────────────┘
                                       │
                          To agree on anything (a leader, a commit,
                          a log order), you run CONSENSUS — which by FLP
                          cannot guarantee termination in async networks,
                          so it uses timeouts (partial synchrony) and stays
                          SAFE while only risking its LIVENESS.
```

CAP and PACELC tell you *what tradeoff* your system makes and *when*. FLP tells you that the coordination machinery underneath — the thing that makes "CP" or "EC" even possible — pays a liveness tax to exist at all. Safety-vs-liveness is the vocabulary that lets you say all of it precisely.

---

## 4b. How to read these papers without drowning

This week's readings are three of the most-cited papers in computer science, and they are dense. A senior engineer does not read a theory paper front to back like a novel; they read it in passes, extracting what they need. Here is the protocol:

- **Pass 1 — the theorem statement only.** Find the boxed/italicized theorem and read *just* it, plus the definitions it depends on. For FLP, that is the one-sentence "no deterministic protocol..." For Gilbert–Lynch, it is the impossibility of available + atomic under message loss. You can stop here and already be more literate than 90% of engineers who only know the meme.
- **Pass 2 — the proof's *shape*, not every line.** Read the structure: FLP's bivalence lemma and the "commuting" argument; Gilbert–Lynch's two-node partition. You want to be able to *reconstruct the idea* on a whiteboard, not reproduce every epsilon. Skim the technical lemmas.
- **Pass 3 — the qualifiers.** Go back and underline every assumption: "asynchronous," "deterministic," "one crash," "messages may be lost." Each qualifier is both a limit on the result and an escape hatch for engineering. This pass is where the *practical* payoff lives — it tells you exactly which assumption to break to route around the impossibility.
- **Pass 4 (optional) — the full proof.** Only when you need to extend or apply the result rigorously. Most engineers never need pass 4 for FLP; they need passes 1–3 cold.

Apply this to Abadi's PACELC paper and you'll finish it in twenty minutes (it is short and prose-heavy — read it whole). Apply it to FLP and you'll extract the theorem and the bivalence idea in an hour without getting lost in the formalism. The skill of reading a theory paper *for what you need* is itself a deliverable of this week, and it is what the midterm architecture-review essay will demand of you at scale.

## 4c. The bridge to Week 2

Everything this week was *impossibility and tradeoff*: what you cannot have (CAP, FLP) and what you must trade (PACELC, safety vs liveness). Week 2 is the constructive answer — the machinery that lives *inside* the escape hatches:

- **Logical clocks (Lamport timestamps, vector clocks)** are how you recover *ordering* — the thing linearizability needs — without a global wall-clock, which the asynchrony assumption denies you. The "happens-before" relation that defines causal consistency (Lecture 1 §3.3) is literally what a vector clock measures.
- **Raft and Paxos** are the partial-synchrony escape hatch made concrete: a leader, an election timeout, and a quorum-committed log. You will build the register from this week's mini-project into a Raft replicated log, and the election timeout you tune *is* the FLP liveness bet.
- **Leases and fencing tokens** are the direct answer to the slow-vs-dead indistinguishability of §2.5: a monotonic token that lets storage reject a resurrected old leader's writes, preserving *safety* through the liveness chaos.

So hold the through-line: this week told you the floor (impossibility) and the tax (tradeoff); next week builds the structure that pays the tax and stands on the floor. You cannot understand *why* Raft has an election timeout until you have internalized FLP — which is precisely why C22 teaches the literature before the code. A team that learns Raft without FLP cargo-cults the timeout; a team that learns FLP first understands the timeout is a *bet against an impossibility*, and tunes it like one.

## 5. Recap

You should now be able to:

- State **PACELC** and classify real systems into PA/EL, PC/EC, PA/EC, PC/EL, defending the choice by what they do under partition and what they do on a healthy network.
- Explain why the **EL/EC** branch governs day-to-day latency and staleness far more than the rare partition case does.
- State the **FLP** theorem with all its qualifiers (asynchronous, deterministic, one crash) and explain the **bivalence** argument in plain English.
- Name the **three escape hatches** — partial synchrony/timeouts, randomization, failure detectors — and identify which one Raft and Paxos use.
- Classify any guarantee as **safety** ("nothing bad ever happens," violated by a finite prefix) or **liveness** ("something good eventually happens," violated only by an infinite execution), and explain why FLP is a liveness result and why you never trade safety for liveness.

Next: the exercises put this on real systems and in real code — you classify ten databases, build a two-node register that exhibits CP and AP experimentally, and write a checker that decides whether a recorded history was linearizable. Continue to [the exercises](../exercises/README.md).

---

## References

- *Consistency Tradeoffs in Modern Distributed Database System Design (PACELC)* — Abadi (2012): <https://www.cs.umd.edu/~abadi/papers/abadi-pacelc.pdf>
- *Impossibility of Distributed Consensus with One Faulty Process (FLP)* — Fischer, Lynch & Paterson (1985): <https://groups.csail.mit.edu/tds/papers/Lynch/jacm85.pdf>
- *Consensus in the Presence of Partial Synchrony* — Dwork, Lynch & Stockmeyer (1988).
- *Unreliable Failure Detectors for Reliable Distributed Systems* — Chandra & Toueg (1996).
- *Proving the Correctness of Multiprocess Programs (safety/liveness)* — Lamport (1977).
- *Defining Liveness* — Alpern & Schneider (1985).
- *In Search of an Understandable Consensus Algorithm (Raft)* — Ongaro & Ousterhout (2014) — the escape hatch in practice, and your Week 2 reading.
