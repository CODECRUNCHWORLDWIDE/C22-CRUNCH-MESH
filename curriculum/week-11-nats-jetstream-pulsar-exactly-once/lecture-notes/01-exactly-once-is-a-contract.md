# Lecture 1 — Exactly-Once Is a Contract, Not a Primitive: NATS JetStream and Pulsar

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can state precisely why exactly-once delivery is impossible and why exactly-once effect is achievable, configure NATS JetStream streams/consumers/dedup, explain Pulsar's broker/bookie architecture and its four subscription modes, and place each broker's "exactly-once" feature on the map of what it actually covers.

If you remember one sentence from this entire week, remember this one:

> **Exactly-once *delivery* is impossible over an unreliable network — it follows directly from FLP and the two-generals problem you met in Week 1 — but exactly-once *effect* is very achievable, and it is achieved not by the broker but by making the consumer idempotent and the write atomic.**

Every vendor that sells you "exactly-once" is selling you a *piece* of this, valid inside a boundary they control, and the boundary always ends at your database and your external API calls. Kafka's EOS holds inside Kafka. JetStream's dedup holds inside its window. Pulsar's transactions hold inside Pulsar. The moment your consumer charges a credit card, none of them can help — and that is exactly where this week's work lives. This lecture builds the conceptual map; Lecture 2 builds the machinery (outbox + idempotent consumer) that carries the guarantee across the boundary.

---

## 1. Why exactly-once delivery is impossible (and why that's fine)

Picture a producer P sending a message to a consumer C over a network that can drop packets and delay them arbitrarily. P sends the message and waits for an acknowledgement.

- If P **does not retry** on a missing ack, and the ack was lost (but the message arrived), C processed it but P thinks it failed — and if P's caller retries the whole operation, you get a duplicate anyway, one level up. If the *message* was lost, C never got it. So no-retry is **at-most-once**: you never duplicate, but you can lose.
- If P **does retry** until it gets an ack, then a lost ack causes a resend, and C may receive the message twice. So retry is **at-least-once**: you never lose, but you can duplicate.

There is no third option, because P cannot distinguish "the message was lost" from "the ack was lost" — both look identical to P (no ack arrived). To deliver exactly once, P would need to *know* whether C received it, which requires C to tell P, which requires an ack, which can itself be lost — the regress never bottoms out. This is the two-generals problem, and it is not an engineering limitation to be overcome by a cleverer broker; it is a theorem.

So we stop trying to make *delivery* exactly-once and instead make the *effect* exactly-once. We accept at-least-once delivery (never lose) and we make C **idempotent**: processing the same message twice produces the same result as processing it once. A duplicate delivery then has no duplicate effect. The card is charged once even though the "charge this order" message arrives three times, because C recognizes the order id it already charged and does nothing the second and third time.

> **The reframe that makes the whole week solvable:** stop guarding *delivery* (impossible) and start guarding *effect* (achievable). At-least-once delivery + idempotent processing = the effect happens exactly once. Everything else this week — JetStream dedup, the outbox, dedup tables, Pulsar transactions — is a specific technique for achieving idempotent effect.

The three semantics, summarized so you can place any consumer instantly:

| Semantic | How you get it | Loses? | Duplicates? | Right for |
|---|---|---|---|---|
| **At-most-once** | Commit/ack the offset *before* processing | Yes | No | Pure telemetry where a dropped sample is harmless |
| **At-least-once** | Process *first*, then commit/ack | No | Yes | Almost everything — paired with an idempotent effect |
| **Exactly-once (effect)** | At-least-once + idempotent consumer + atomic write | No | No (in effect) | Orders, payments, anything where a double-effect is a bug |

Notice the third row is not a *delivery* mode — it is a *composition*: at-least-once delivery plus the two pillars below. There is no broker setting labeled "exactly-once effect" because it is not the broker's to give; it is built from at-least-once (which the broker provides) and idempotency + atomicity (which you provide). The rest of this lecture and all of Lecture 2 is how you provide your half.

---

## 2. The two mechanisms: idempotency and atomicity

Effectively-exactly-once rests on two pillars. You will use both, often together.

### 2.1 Idempotency — recognize and drop the duplicate

An operation is **idempotent** if applying it N times equals applying it once. `SET x = 5` is idempotent; `x = x + 5` is not. Most business effects are not naturally idempotent — "charge $42," "decrement stock by 1," "send the shipping email" all double up if run twice. You make them idempotent by attaching a **stable idempotency key** and checking it:

- **Charge a card** *by* an idempotency key (Stripe and every serious payment API accept one): the second charge with the same key is a no-op that returns the first charge's result.
- **Decrement stock** by recording the event id that caused the decrement; if you've seen that event id, skip.
- **Upsert into a read model** keyed by the entity id: re-applying the same event overwrites with the same value, so it's naturally idempotent.

The key must be **stable across retries** — derived from the business event (`order_id`, the event's UUID), not generated fresh on each attempt. A key that changes per retry defeats the entire purpose. This is the single most common idempotency bug: generating the key inside the retry loop instead of carrying it from the event.

The contrast in code, because it is so easy to get wrong:

```python
# WRONG: the key is generated fresh on every attempt, so a retry never matches.
def charge(order):
    key = str(uuid.uuid4())               # <-- new key each call! dedup can never fire
    stripe.PaymentIntent.create(amount=order["total_cents"], idempotency_key=key)

# RIGHT: the key is derived from the event, identical across retries.
def charge(order):
    key = f"charge-{order['order_id']}"   # <-- stable: the 2nd delivery dedups server-side
    stripe.PaymentIntent.create(amount=order["total_cents"], idempotency_key=key)
```

The `WRONG` version *looks* idempotent — there's an `idempotency_key`! — but it double-charges, because each retry presents a different key and the payment provider treats it as a new charge. This bug ships constantly because it reads correctly and passes any happy-path test; only a real retry exposes it. The fix is one line, and the discipline is: **the idempotency key is part of the event, not part of the attempt.** Carry it; never mint it.

### 2.2 Atomicity — never let the event and the state disagree

The second pillar guards the *producer* side. If your service does two things — change its database and publish an event — and those are two separate operations, a crash between them leaves them disagreeing: the order is marked placed in Postgres but `order.placed` was never published, or vice versa. This is the **dual-write problem**, and it is Lecture 2's main subject. The fix is **atomicity**: make the state change and the "intent to publish" commit together, in one transaction, via the **transactional outbox**. The event can then never disagree with the committed state, because they were written in the same transaction.

Hold these two pillars in mind for the rest of the week: **idempotency** protects the consumer from duplicate delivery; **atomicity** (the outbox) protects the producer from the dual-write. Together they give you effectively-exactly-once end to end. No single broker feature gives you both.

---

## 3. NATS: core vs JetStream

NATS is a high-performance messaging system with two layers that you must not confuse, because they have opposite durability guarantees.

### 3.1 NATS core — fire-and-forget

NATS **core** is in-memory, at-most-once pub/sub. A publisher publishes to a **subject** (a dot-delimited name like `order.placed.us-east`); subscribers interested in that subject receive it *if they are connected at that moment*. There is no persistence, no replay, no ack. If no subscriber is listening, the message is gone. If a subscriber is slow and its buffer overflows, NATS drops messages to protect the system. Core NATS is blazing fast and perfect for ephemeral, latency-critical signaling (service discovery, request-reply RPC, live telemetry where a dropped sample is harmless) — and completely wrong for an order event you must not lose.

Subjects support **wildcards**, which is NATS's most elegant feature:

- `order.*` matches exactly one token: `order.placed`, `order.cancelled`, but not `order.placed.us-east`.
- `order.>` matches one or more tokens: `order.placed`, `order.placed.us-east`, `order.cancelled.eu`, everything under `order`.

A consumer can subscribe to `order.>` and receive every order-related event, or `*.placed.us-east` to receive every "placed in us-east" event regardless of entity type. This subject-hierarchy addressing is more expressive than Kafka's flat topic names, and it is one of the genuine reasons teams choose NATS.

Two core-NATS patterns you should recognize, because they shape how teams use NATS even when they later add JetStream:

- **Request-reply.** A client publishes a request to a subject with a unique *reply* subject, and a responder publishes its answer back to that reply subject. This turns the pub/sub bus into a low-latency RPC mechanism — it is how a lot of NATS-based microservice meshes do synchronous calls, with the subject hierarchy providing the routing. Because it's core NATS, it's at-most-once: a lost request or reply just times out and the client retries, which (per §1) means the *caller* must be idempotent.
- **Queue groups.** Multiple subscribers can join a named **queue group** on a subject; NATS then delivers each message to *exactly one* member of the group (load-balanced), rather than to all of them. This is the core-NATS work-queue primitive — analogous to a Kafka consumer group or Pulsar's shared subscription, but without persistence. It's how you scale out at-most-once processing across workers.

These matter because a team often starts on core NATS for its speed and simplicity, uses request-reply and queue groups heavily, and then adopts JetStream *only* for the subjects that need durability — keeping the fast at-most-once path for everything that doesn't. Knowing both layers lets you make that split deliberately instead of putting everything on the durable (and slower) path.

### 3.2 NATS JetStream — durable, replicated, replayable

**JetStream** is the persistence layer NATS adds on top of core. It gives you what Kafka gives you, in NATS's idiom:

- A **stream** captures messages published to a set of subjects and persists them (to disk, replicated via Raft across the cluster — the same Raft from Week 2). A stream has a retention policy (limits, interest, or work-queue), a replica count, and an optional **dedup window**.
- A **consumer** is a stateful view over a stream that tracks delivery and acks. Consumers are **push** (JetStream delivers to you) or **pull** (you fetch batches — the scalable choice, analogous to Kafka's poll). They are **durable** (the server remembers your position across restarts, like a Kafka consumer group) or **ephemeral** (position forgotten when you disconnect). And they have an **ack policy**: `none` (fire-and-forget), `all` (acking message N acks all ≤ N), or `explicit` (ack each message individually — the at-least-once choice).

With a durable pull consumer and `explicit` ack policy, JetStream gives you exactly the at-least-once semantics you built on Kafka in Week 10: process the message, then ack; crash before ack, and JetStream redelivers. Same contract, different broker.

Two JetStream details that differ from Kafka and that you must set deliberately:

- **Retention policy is a stream property with three modes.** `limits` (keep up to a max age/size/count, like Kafka time/size retention — the default for an event stream); `interest` (keep a message only while some consumer still needs it, then drop it — like a smart queue); and `workqueue` (a message is removed once *any* consumer acks it — a true distributed work queue where each message is processed exactly once across consumers, with no replay). Choosing `workqueue` vs `limits` is the JetStream analog of "is this a queue or a log" — `workqueue` for job dispatch, `limits` for an event log you might replay.
- **`AckWait` and `MaxDeliver` govern redelivery.** A consumer has an **ack-wait** timeout: if it pulls a message and doesn't ack within `AckWait`, JetStream assumes the consumer died and **redelivers** the message. `MaxDeliver` caps how many times a message is redelivered before JetStream gives up and (optionally) routes it to a configured dead-letter via an advisory. This is JetStream's built-in poison-message handling — Kafka makes you build the DLT yourself; JetStream gives you `MaxDeliver` + advisories out of the box. Set `AckWait` longer than your worst-case processing time, or a slow consumer will get the same message redelivered while it's still working on it — a self-inflicted duplicate.

The mental mapping for someone coming from Kafka: a JetStream **stream** ≈ a Kafka topic's log; a JetStream **durable consumer** ≈ a Kafka consumer group's offset; `explicit` ack ≈ manual offset commit; `AckWait`/`MaxDeliver` ≈ the redelivery and DLT machinery you hand-rolled. The contract is the same; JetStream just packages more of the consumer-side ceremony into the broker.

A minimal JetStream producer + durable pull consumer in Go, so the idiom is concrete:

```go
import (
	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
)

// Connect and get the JetStream context.
nc, _ := nats.Connect("nats://localhost:4222")
js, _ := jetstream.New(nc)

// Create (or update) a stream capturing order.* with a dedup window.
js.CreateOrUpdateStream(ctx, jetstream.StreamConfig{
	Name:       "ORDERS",
	Subjects:   []string{"order.>"},
	Retention:  jetstream.LimitsPolicy,
	Storage:    jetstream.FileStorage,
	Replicas:   3,
	Duplicates: 2 * time.Minute, // the dedup window
})

// Publish WITH a Nats-Msg-Id so producer retries are deduped within the window.
js.Publish(ctx, "order.placed",
	[]byte(`{"order_id":"A","total_cents":4200}`),
	jetstream.WithMsgID("evt-A-001"))

// A durable pull consumer with explicit ack = at-least-once.
cons, _ := js.CreateOrUpdateConsumer(ctx, "ORDERS", jetstream.ConsumerConfig{
	Durable:   "fulfillment",
	AckPolicy: jetstream.AckExplicitPolicy,
	AckWait:   30 * time.Second, // longer than worst-case processing
	MaxDeliver: 5,               // give up after 5 redeliveries
})

msgs, _ := cons.Fetch(10)
for msg := range msgs.Messages() {
	if err := process(msg.Data()); err != nil {
		msg.Nak() // negative-ack => redeliver after AckWait
		continue
	}
	msg.Ack() // ack only after the work is durably done
}
```

The shape is identical to the Kafka producer/consumer from Week 10 — publish with a dedup key, pull a batch, process, ack-after-work — which is exactly the point: the *contract* is portable even though the *API* differs.

### 3.3 The JetStream dedup window

JetStream adds one thing Kafka's broker does not: a **publish-side dedup window**. If you set a stream's `duplicate window` to, say, 2 minutes, and you publish messages stamped with a `Nats-Msg-Id` header, JetStream will **drop** any message whose `Nats-Msg-Id` it has already seen *within the window*. This deduplicates *producer* retries at the broker — if your producer resends because an ack was lost, JetStream recognizes the `Nats-Msg-Id` and doesn't store the duplicate.

This is genuinely useful and worth knowing precisely, including its limit:

> **The dedup window is bounded in time, not forever.** A duplicate that arrives *after* the window expires is *not* deduplicated — it is accepted as a new message. So the dedup window protects against fast retries (network blips, immediate resends) but **not** against a duplicate that arrives hours later (a consumer replaying old data, a delayed redelivery). It is a *weaker* guarantee than an idempotent consumer with a permanent dedup table. Use the window as a cheap first line of defense; never rely on it as your *only* defense. The outbox + idempotent consumer (Lecture 2) is the durable guarantee; the dedup window is an optimization on top.

---

## 4. Apache Pulsar: the storage/serving split

Pulsar is the third broker in this week's comparison, and its defining architectural choice is different from both Kafka and NATS: **it separates serving from storage.**

### 4.1 Brokers and bookies

- **Brokers** are *stateless*. They handle producer and consumer connections, routing, and subscriptions, but they **do not store the messages**. Because they hold no data, a broker can be added, removed, or restarted instantly, and topics rebalance across brokers in milliseconds — there is no multi-gigabyte log to copy, because the broker never had it.
- **Bookies** (Apache BookKeeper nodes) are the *stateful* storage layer. They hold the actual message log, organized as **ledgers** (append-only segments) of **entries** (records). Replication and durability are BookKeeper's job, at the ledger level.

The payoff of this split: **storage and serving scale independently.** Out of broker CPU but not disk? Add brokers. Out of disk but not CPU? Add bookies. And because brokers are stateless, a broker failure does not trigger a log migration — another broker picks up the topic's serving instantly while the data sits safely on the bookies. Kafka couples these (a broker owns both the serving and the log for its partitions), which is simpler to reason about but means a broker loss is a data-movement event. Pulsar's split is more moving parts (two systems to operate, plus ZooKeeper/etcd for metadata historically) in exchange for elastic, fast rebalancing. Whether that trade is worth it is, as always, a per-workload question.

### 4.2 Tiered storage

Because the storage layer is explicit, Pulsar bakes in **tiered storage**: old ledgers are offloaded to object storage (S3, GCS) while staying transparently readable through the same consumer API. You keep infinite history at object-storage prices and only the recent hot data on the bookies' fast disks. Kafka gained this later (KIP-405); in Pulsar it has been core for years and is a frequently-cited reason to choose it for long-retention workloads.

The BookKeeper durability model, one level deeper, because it's structurally different from Kafka's ISR and worth contrasting:

- A topic's data is a sequence of **ledgers**; each ledger is a sequence of **entries** (records). A ledger has an **ensemble** (the set of bookies it's striped across), a **write quorum** (how many bookies each entry is written to), and an **ack quorum** (how many must ack before the write is considered durable). So durability is per-ledger and tunable: `ensemble=3, write=3, ack=2` means each entry is striped to 3 bookies, written to 3, and acked once 2 confirm — survives one bookie loss, analogous to Kafka's `RF=3, acks=all, min.insync=2` but expressed at the storage layer.
- Because the *broker* doesn't own the data, a broker can fail and another broker immediately serves the topic by reading the same ledgers from the same bookies — **no log migration**, which is the elastic-rebalancing payoff. Contrast Kafka, where a partition's leader owns its log, so leadership moving means a replica must already have the data (the ISR) and a *new* replica means copying gigabytes.
- The cost is operational surface: you run brokers *and* bookies *and* a metadata store, and you reason about two quorum settings (write and ack) plus the ensemble. That's the trade for the elasticity and the storage/serving independence — more parts, more flexibility.

For an exactly-once discussion this matters because Pulsar's transaction durability rides on BookKeeper's: an acked transactional write is durable per the ack quorum, the same way a Kafka transactional write is durable per the ISR. Different mechanism, same guarantee shape — and, as §5 will hammer, the same boundary: it ends at the bookie, not at your database.

### 4.3 The four subscription modes

Pulsar's subscriptions are more flexible than Kafka's consumer groups, and you must know all four because they map directly to delivery and ordering semantics:

| Mode | Behavior | Ordering | Use for |
|---|---|---|---|
| **Exclusive** | One consumer; a second attempt to subscribe fails. | Total order on the topic. | A single-writer-per-stream invariant. |
| **Failover** | One active consumer; standbys take over if it dies. | Total order, preserved across failover. | Ordered processing with HA. |
| **Shared** | Messages round-robined across all consumers; each message to one consumer. | **No ordering guarantee.** | Throughput / work-queue, order-independent. |
| **Key-shared** | Messages with the same key always go to the same consumer. | **Per-key ordering** (like Kafka's keyed partitions). | Ordered-per-entity parallel processing. |

**Key-shared** is the one to anchor on, because it gives you Kafka's per-key-ordering-with-parallelism model without committing to a fixed partition count up front — Pulsar assigns keys to consumers dynamically. **Shared** gives you a classic work queue (no ordering, maximum parallelism, any consumer can take any message), which Kafka cannot do natively (a Kafka partition is owned by one consumer). This flexibility — pick the ordering/parallelism trade-off per subscription, not per topic — is Pulsar's signature.

A Pulsar producer + key-shared consumer in Python, so the idiom is concrete:

```python
import pulsar
from pulsar import ConsumerType

client = pulsar.Client("pulsar://localhost:6650")

# Producer — key the message so key-shared routes it deterministically.
producer = client.create_producer("persistent://public/default/orders")
producer.send(
    b'{"order_id":"A","total_cents":4200}',
    partition_key="order-A",   # same key => same key-shared consumer => per-key order
)

# Consumer — key-shared: same key always reaches the same consumer instance.
consumer = client.subscribe(
    "persistent://public/default/orders",
    subscription_name="checkout-sub",
    consumer_type=ConsumerType.KeyShared,   # Shared / Exclusive / Failover are the others
)

while True:
    msg = consumer.receive()
    try:
        process(msg.data())
        consumer.acknowledge(msg)            # ack AFTER processing (at-least-once)
    except Exception:
        consumer.negative_acknowledge(msg)   # nack => redeliver
```

Swap `ConsumerType.KeyShared` for `ConsumerType.Shared` and the *same code* becomes an unordered work queue across instances — the per-subscription flexibility is one enum away. That is the contrast with Kafka, where the ordering/parallelism choice is baked into the topic's partition layout, not chosen per consumer.

### 4.4 Pulsar transactions

Pulsar supports **transactions** spanning multiple producers and consumers: you can atomically produce to several topics and acknowledge consumed messages, all-or-nothing, similar in spirit to Kafka's transactions. As with Kafka EOS, this holds *inside Pulsar* — it makes a consume-transform-produce pipeline atomic within the broker. And as with Kafka, it stops at your database and external APIs. Same boundary, same need for an outbox + idempotency past it.

---

## 5. Placing the three brokers on the exactly-once map

Here is the table that orients you for Lecture 2 — what each broker's "exactly-once" feature actually covers, and where it stops.

| Broker | The EOS-ish feature | What it covers | Where it STOPS |
|---|---|---|---|
| **Kafka / Redpanda** | Idempotent producer + transactions (`read_committed`) | Dedups producer retries; atomic consume-transform-produce **within Kafka** | At your DB / external API. Charging a card is outside the transaction. |
| **NATS JetStream** | Dedup window (`Nats-Msg-Id`) + explicit ack | Dedups producer retries **within the time window**; at-least-once redelivery | Outside the window, and at your DB / external API. |
| **Pulsar** | Transactions across topics + subscription acks | Atomic produce+ack **within Pulsar** | At your DB / external API. |

Read the rightmost column. Every one says the same thing: **the broker's guarantee ends at the edge of the broker.** The instant your processing touches Postgres or Stripe, you are on your own, and "on your own" means the outbox (for the write) and the idempotency key (for the effect). That is the entire subject of Lecture 2, and it is the single most important operational skill in event-driven systems: knowing exactly where the broker's promise ends and yours begins, and building the contract that spans the gap.

It helps to see how the three brokers achieve their *internal* durability, since you studied all the underlying primitives in earlier weeks:

| Broker | Internal replication mechanism | Primitive you already know |
|---|---|---|
| Kafka | Leader + followers + ISR; `acks=all`, `min.insync.replicas` | The ISR protocol (Week 10) |
| Redpanda | Raft per partition | Raft (Week 2) |
| NATS JetStream | Raft per stream (replica count) | Raft (Week 2) |
| Pulsar | BookKeeper ledgers with write/ack quorum | Quorum replication (Weeks 1–2) |

Three of the four are literally Raft or quorum replication — the consensus machinery from Phase 1 — and Kafka's ISR is a close cousin. This is reassuring rather than coincidental: durable replication is a solved problem with a small number of correct shapes, and every serious broker picks one of them. What distinguishes the brokers is *not* the replication correctness (they're all sound) but the operational model, the API ergonomics, the routing expressiveness, and — the theme of this week — exactly which slice of exactly-once they package versus leave to you. And on that last point, as the table above shows, they are unanimous: they package the part inside themselves and leave the part that touches your world to you.

---

## 6. A worked example on the marketplace

Concretely, on the services you've been building. The order service consumes `order.placed.v1` (at-least-once, from Week 10) and must: reserve inventory, charge payment, and emit `order.confirmed.v1`. Today, if it crashes after charging but before emitting, a redelivery charges again — the exact bug exercise-3 part D exposed last week.

The fix, previewed (built in Lecture 2 and the exercises):

1. **Idempotent charge.** The payment step uses `order_id` as the idempotency key. The second delivery's charge is a no-op returning the first charge's result. No double-charge, regardless of how many times the event is delivered.
2. **Outbox for the emit.** Instead of "charge, then publish `order.confirmed`" as two steps, the order service writes the confirmation row *and* an `outbox` row in one Postgres transaction. A relay publishes the outbox to the broker. Now the emit can never disagree with the committed state — if the transaction committed, the event will be published (at-least-once, by the relay); if it rolled back, neither happened.
3. **Dedup table as a belt-and-suspenders.** The consumer records each processed `event_id` in a dedup table inside the same transaction as its effect; a duplicate `event_id` is an insert that hits the unique constraint and is skipped.

What you bought: the order service can crash at *any* point — before charging, between charging and emitting, during the emit — and on restart, redelivery produces zero double-charges and zero lost confirmations. That is effectively-exactly-once, built from at-least-once delivery + idempotency + atomicity, with no reliance on any broker's EOS feature past its boundary. You will build and *chaos-test* exactly this in the exercises and prove `double-charges: 0`.

Trace the crash windows explicitly, because seeing that *every* one is safe is the moment the pattern clicks:

```
crash BEFORE charging:
  -> redelivery re-runs from the event; charges once (idempotency key fresh, fine).

crash AFTER charging, BEFORE recording "charged" in the dedup table:
  -> the dedup insert and the charge are in ONE transaction, so this window
     DOESN'T EXIST — either both committed or neither did. (Lecture 2 §2.1)

crash AFTER the charge+dedup commit, BEFORE committing the Kafka offset:
  -> redelivery happens; the dedup table says "already charged"; charge is skipped.
     The offset advances on the redelivery. Net effect: charged exactly once.

crash DURING the emit of order.confirmed.v1:
  -> the confirmation row + outbox row were one transaction; the relay publishes
     the outbox at-least-once; a duplicate emit is absorbed by the NEXT consumer's
     idempotency. The emit can't be lost (it's in the committed outbox).
```

Every window is either impossible (collapsed into one transaction) or safe (absorbed by idempotency). That exhaustiveness — "name every place it can crash and show each is fine" — is exactly how you *defend* an exactly-once design in a review, and exactly what the chaos test mechanizes.

---

## 7. Recap

You should now be able to:

- State why exactly-once *delivery* is impossible (two-generals / FLP) and why exactly-once *effect* is achievable, and name the two pillars: idempotency (consumer side) and atomicity (producer side).
- Distinguish NATS core (in-memory, at-most-once, fire-and-forget, wildcard subjects) from JetStream (durable, Raft-replicated, replayable streams with consumers, ack policies, and a bounded dedup window).
- Explain Pulsar's broker/bookie split, why stateless brokers give instant rebalancing, tiered storage, and the four subscription modes — especially key-shared (per-key order) and shared (work queue).
- Place Kafka EOS, JetStream dedup, and Pulsar transactions on the map of what each covers and exactly where each stops (the DB / external-API boundary).
- Write a stable, event-derived idempotency key (and recognize the per-attempt-key bug on sight), and trace every crash window in a checkout flow to show each is safe.
- Recognize that three of the four brokers replicate via Raft/quorum — the Phase-1 consensus you already know — so the differentiator is operations and API, not replication correctness.

Next: the machinery that carries the guarantee across that boundary — the dual-write problem, the transactional outbox, idempotency keys and dedup tables, and a precise side-by-side of the three brokers' EOS features. Continue to [Lecture 2 — The Outbox and Idempotent Consumers](./02-the-outbox-and-idempotent-consumers.md).

---

## References

- *Pattern: Transactional outbox* — microservices.io: <https://microservices.io/patterns/data/transactional-outbox.html>
- *NATS JetStream concepts*: <https://docs.nats.io/nats-concepts/jetstream>
- *NATS JetStream model deep dive (dedup window)*: <https://docs.nats.io/using-nats/developer/develop_jetstream/model_deep_dive>
- *Apache Pulsar — concepts and architecture*: <https://pulsar.apache.org/docs/concepts-architecture-overview/>
- *Apache Pulsar — subscriptions*: <https://pulsar.apache.org/docs/concepts-messaging/#subscriptions>
- *Apache Pulsar — transactions*: <https://pulsar.apache.org/docs/transactions/>
- *Why dual writes are a bad idea* — Kleppmann/Confluent: <https://www.confluent.io/blog/using-logs-to-build-a-solid-data-infrastructure-or-why-dual-writes-are-a-bad-idea/>
