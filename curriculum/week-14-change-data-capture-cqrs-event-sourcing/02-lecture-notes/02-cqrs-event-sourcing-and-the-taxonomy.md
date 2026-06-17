# Lecture 2 — CQRS, Event Sourcing, and the Taxonomy That Prevents Disasters

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can design a CQRS system with a write model and one or more projected read models, build an idempotent projector, implement a small event-sourced aggregate with replay and snapshots, and — most importantly — correctly classify any design as event-driven, CDC-fed, or event-sourced, and refuse to adopt event sourcing where CDC-fed CQRS is the right, cheaper answer.

Lecture 1 gave you a faithful stream of changes. This lecture is about what you build *with* it, and the conceptual discipline that keeps you from building the wrong thing. Three parts: (1) CQRS and read-model projections, (2) event sourcing done honestly, (3) the taxonomy that distinguishes three things people constantly conflate.

The thesis:

> **Most teams that "do event sourcing" actually wanted CDC-fed CQRS, and the confusion costs them years. CQRS — one write model, many projected read models — solves the "my queries and my writes want different schemas" problem cheaply. Event sourcing — events as the system of record — solves a different and rarer problem, at a much higher price. Know which problem you have before you pick the tool.**

---

## Part 1 — CQRS: separate the write model from the read models

**CQRS** (Command Query Responsibility Segregation) is a small, powerful idea: the schema that is correct for *writing* data is often wrong for *reading* it, so use different models for each.

The write side (the **command model**) is normalized for correctness: third-normal-form tables, foreign keys, constraints — optimized so that a write is valid and consistent. The read side (the **query model**, or **read model**) is denormalized for the queries you actually run: a flat search document, a pre-joined reporting table, a cache. You keep the read model in sync with the write model by consuming the change stream from Lecture 1.

```
            writes                         reads
              │                              │
              ▼                              ▼
      ┌──────────────┐   CDC / events   ┌──────────────┐
      │ WRITE MODEL  │ ───────────────► │  READ MODEL  │
      │ (normalized  │   (the stream)   │ (denormalized│
      │  orders, FK, │                  │  search doc, │
      │  constraints)│                  │  rollup, …)  │
      └──────────────┘                  └──────────────┘
       command side                       query side
```

The key reframing: **one write model can feed N read models, each optimized for a different access pattern.** The same `orders` change stream can maintain:

- an **Elasticsearch search index** (denormalized order-with-customer-and-items, optimized for full-text and faceted search),
- a **daily revenue rollup** table (aggregated, optimized for the finance dashboard),
- a **per-customer order history** cache (optimized for the account page),
- and an **Iceberg table** for the lakehouse (Week 15).

Each read model is a **projection** — a pure function of the change stream. You never write to a read model directly; you *project* the stream into it. This is what makes read models disposable: if a projection is wrong or its schema changes, you delete it and **rebuild it by replaying the stream**. That replay-to-rebuild property is the operational superpower of CQRS, and it's why the projector's only job is to be a correct, idempotent fold over events.

### 1.1 Eventual consistency, stated honestly to product

The read model lags the write model — by milliseconds usually, by seconds under load, occasionally by minutes during a backfill. This is **eventual consistency**, and you must communicate it honestly rather than pretend it away:

- **Read-your-writes is not free.** A user who places an order and immediately loads "my orders" may not see it if "my orders" reads the eventually-consistent read model. The fixes are: read the *write* model for read-your-writes paths, or carry the write's version forward and have the UI wait for the read model to catch up, or show an optimistic UI. Decide this per screen; don't let it surprise you in production.
- **Staleness is a number, not a vibe.** The CDC lag (Lecture 1 §4.2, the `ts_ms` gap) is your read-model staleness. Monitor it. An SLO on read-model lag (Week 18) is how you keep "eventually" bounded.
- **Some reads must hit the write model.** A balance check before a withdrawal, an inventory check before a reservation — anything where stale data is a correctness bug, not a UX annoyance — reads the authoritative write model, not a projection. CQRS does not mean "all reads go to the read model"; it means "reads that *tolerate* staleness can."

> **The senior position:** CQRS is the right default whenever your read and write access patterns genuinely diverge — which is most non-trivial systems. It is *not* the right default for a simple CRUD service whose reads and writes want the same shape; there, one table is correct and CQRS is overhead. Don't add a read model you don't need.

---

## Part 2 — The idempotent projector

A projector consumes the change stream and updates a read model. Because delivery is at-least-once (Lecture 1, Week 11), the *same* change event will sometimes arrive twice — after a consumer restart, a rebalance, a redelivery. If your projector is not idempotent, a duplicate `OrderPlaced` double-counts revenue, a re-applied `+1` inventory drifts, a re-inserted row violates a constraint or duplicates a search result. **Idempotency is not optional; it is the contract.**

There are three robust ways to make a projection idempotent:

1. **Upsert by primary key.** If the read model is keyed and the event carries the full `after` state, an `INSERT ... ON CONFLICT DO UPDATE` is naturally idempotent: applying the same `after` twice yields the same row. This is the simplest and most common pattern, and it's why CDC events carrying full `after` images are so convenient.

```sql
INSERT INTO order_search (order_id, customer_id, status, total_cents, updated_lsn)
VALUES (%(order_id)s, %(customer_id)s, %(status)s, %(total_cents)s, %(lsn)s)
ON CONFLICT (order_id) DO UPDATE
SET status = EXCLUDED.status,
    total_cents = EXCLUDED.total_cents,
    updated_lsn = EXCLUDED.updated_lsn
WHERE order_search.updated_lsn < EXCLUDED.updated_lsn;   -- ignore stale/duplicate
```

2. **Track the last-applied position.** Store the highest LSN (or Kafka offset) you've applied per key or globally, and skip any event whose position you've already passed. The `WHERE updated_lsn < EXCLUDED.updated_lsn` clause above does exactly this inline — it makes the upsert *monotonic*, so an out-of-order or duplicate older event is ignored.

3. **Dedup table.** For non-upsertable effects (incrementing a counter, sending a notification), record processed event IDs in a `processed_events` table inside the *same transaction* as the effect, and check it first. Same idea: the effect and the "I did this" marker commit together.

The discipline: **apply the effect and record that you applied it in one atomic step**, and make re-application a no-op. Do that and at-least-once delivery becomes exactly-once *processing* — the "exactly-once processing, not delivery" promise from the week README. Exercise 2 builds this projector; the chaos test in the mini-project proves it by killing the consumer mid-batch and checking the read model is byte-identical to a clean run.

---

### 2a. The three idempotency patterns, side by side

§2 listed three ways to make a projection idempotent. They're worth contrasting directly, because choosing the right one per effect is the difference between a correct projector and a subtly broken one.

| Pattern | Use when the effect is… | How it works | Failure if you skip it |
|---|---|---|---|
| **Upsert by key** | A row replacement (the read model is keyed) | `INSERT ... ON CONFLICT DO UPDATE`; same `after` applied twice = same row | A duplicate insert violates the PK or creates a dupe |
| **Monotonic by position** | A row replacement where ordering matters | Upsert guarded by `WHERE existing.lsn < new.lsn` | An out-of-order *older* event overwrites newer state |
| **Dedup table** | A non-replaceable effect (counter, notification, external call) | Record processed event IDs in the same txn as the effect; check first | A duplicate increments the counter / sends the email twice |

The instructive case is the difference between the first two. A plain upsert is idempotent against *duplicates* — applying the same event twice is harmless. But it is **not** safe against *reordering*: if event v2 arrives, gets applied, and then a delayed duplicate of v1 arrives, a plain upsert happily overwrites the v2 state with stale v1 data. The `WHERE existing.lsn < new.lsn` guard fixes exactly this — it makes the upsert *monotonic*, so an older event can never clobber a newer one. Under the per-partition ordering Kafka gives you (Lecture 1's key-by-PK), strict reordering of the same key is rare, but rebalances, retries, and multi-partition fan-in make it possible enough that the guard is cheap insurance you should always include.

The dedup table is for the effects you *cannot* express as an upsert: incrementing a running total, sending a confirmation email, calling a payment API. For these, "apply twice" is not naturally harmless, so you make it harmless by recording "I processed event X" in the *same transaction* as the effect and checking that record first. The atomicity is the whole point — if the effect and the marker could commit separately, you'd have reinvented the dual-write problem inside your consumer.

The rule to carry: **match the idempotency pattern to the effect.** Replaceable keyed state → monotonic upsert. Non-replaceable effect → dedup table in the same transaction. Never assume "at-least-once is fine" without naming which pattern absorbs the duplicate; "it'll probably be fine" is how double-charged customers happen.

## Part 3 — Event sourcing, done honestly

CQRS keeps a *current-state* write model and projects read models from its changes. **Event sourcing** is more radical: it makes the **append-only sequence of events the system of record**. There is no current-state table you `UPDATE`; there is a log of facts — `OrderPlaced`, `OrderShipped`, `OrderCancelled` — and current state is *computed* by replaying them.

### 3.1 The vocabulary

- **Event** — an immutable fact that happened: `OrderShipped{order_id, shipped_at, carrier}`. Past tense, never deleted, never mutated.
- **Aggregate** — the consistency boundary (from DDD): the `Order`. Commands target an aggregate; events belong to it.
- **Command** — a request to change state: `ShipOrder{order_id, carrier}`. A command is *validated against current state* and, if valid, **produces one or more events**. Commands can be rejected; events cannot (they already happened).
- **Apply / fold** — current state is a left-fold over the aggregate's events: `state = events.reduce(apply, empty)`. `apply(state, OrderShipped) → state with status=SHIPPED`.

```
command  ShipOrder(1001)
   │
   ▼  load current state by replaying events for order 1001
state = fold([OrderPlaced, OrderPaid])           → {status: PAID}
   │  validate: can a PAID order ship? yes.
   ▼  produce new event
emit OrderShipped(1001)                            → append to the log
   │
   ▼  new state (for the next command) = fold([..., OrderShipped]) → {status: SHIPPED}
```

### 3.2 The event store

The store is an append-only table (or EventStoreDB, or a Kafka-backed log). A minimal Postgres event store:

```sql
CREATE TABLE events (
    global_seq   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    aggregate_id text   NOT NULL,
    version      int    NOT NULL,         -- per-aggregate sequence, 1,2,3,...
    event_type   text   NOT NULL,
    payload      jsonb  NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (aggregate_id, version)        -- the optimistic-concurrency guard
);
```

The `UNIQUE (aggregate_id, version)` constraint is the load-bearing line. When you handle a command, you load the aggregate at version N, decide to append event N+1, and `INSERT` it with `version = N+1`. If a *concurrent* command also loaded version N and tries to insert its own version N+1, the unique constraint **rejects the second one** — that's **optimistic concurrency control**. The loser retries: reload (now at N+1), re-validate, re-append as N+2. No locks, no lost updates. This is how event sourcing handles concurrency without `SELECT FOR UPDATE`.

### 3.3 Snapshots

Replaying 50,000 events to handle one command is slow. **Snapshots** cache the folded state at a version: store `{aggregate_id, version, state}` periodically (every 100 events, say). To load, fetch the latest snapshot and replay only the events *after* it. Snapshots are an optimization, never the source of truth — you can always delete every snapshot and rebuild from events. (If you ever feel tempted to update state *only* in the snapshot and not append an event, stop: you've abandoned event sourcing and reinvented a mutable table.)

### 3.3a Event versioning and upcasting, concretely

§3.4 names "schema evolution of historical events" as the biggest ongoing cost. Here is what it actually looks like, because it's abstract until you've hit it.

Suppose your 2024 `OrderPlaced` event was `{order_id, customer_id, total}`. In 2025 you split `total` into `subtotal` and `tax`. You cannot rewrite the millions of 2024 events sitting in your log — they're immutable facts. So when you replay the log to rebuild an aggregate, your `apply` function encounters *both* shapes: old events with `total`, new events with `subtotal`+`tax`. Two strategies handle this:

- **Tolerant readers.** Your `apply` function checks which fields are present and copes: "if the event has `total` but not `subtotal`, treat `subtotal = total` and `tax = 0`." This works but accretes conditionals forever — every old shape leaves a permanent `if` in your code.
- **Upcasting.** A dedicated *upcaster* layer transforms old event versions into the current version *as they're read*, before `apply` ever sees them. The 2024 `OrderPlaced{total}` is upcast to `OrderPlaced{subtotal: total, tax: 0}` on the way out of the store. Now `apply` only ever handles the current shape, and all the version-bridging logic lives in one explicit, testable place. This is the disciplined answer and the one Greg Young's *Versioning in an Event Sourced System* advocates.

```python
# An upcaster: old shape in, current shape out. Registered per (event_type, version).
def upcast_order_placed_v1_to_v2(old: dict) -> dict:
    return {
        "subtotal": old["total"],     # the v1 'total' becomes v2 'subtotal'
        "tax": 0,                     # v1 had no tax; default it
        "order_id": old["order_id"],
        "customer_id": old["customer_id"],
        "_version": 2,
    }
```

Either way, the cost is real and *permanent*: every event shape you have ever emitted must be handled forever, because you can never delete or rewrite the history. A system that's been event-sourced for five years carries five years of upcasters. This is the tax, and it's why event sourcing is the wrong default — you pay it only when the history is worth it. In a CDC-fed CQRS system, by contrast, the change stream carries the *current* table shape and you don't keep ancient event versions around to fold; the cost simply doesn't arise. That asymmetry is a big part of why "default to CQRS, reach for event sourcing only when history is the asset" is the right rule.

### 3.4 The costs — the part the evangelists skip

Event sourcing is powerful and it is *expensive*. A senior engineer can recite the costs:

- **Schema evolution of historical events.** Your `OrderPlaced` event from 2024 has a different shape than your 2026 one. But you can never re-write old events — they're immutable facts. So your `apply` function must handle *every version of every event you have ever emitted*, forever, or you must run an explicit event-upcasting layer. This is the single biggest ongoing tax. (Greg Young wrote a whole book on just this problem.)
- **The right to erasure (GDPR).** "Delete my personal data" against an **append-only, never-deleted log** is a genuine conflict. The pragmatic answers — crypto-shredding (encrypt PII per-subject, throw away the key to "delete"), or storing PII outside the event store and referencing it — are real engineering you must design up front, not bolt on.
- **Debugging and onboarding cost.** "What is the current state?" is a replay, not a `SELECT`. New engineers find it disorienting. Tooling (a state-inspector that folds events on demand) is mandatory, not optional.
- **The no-delete tax.** Storage only grows. Every mistake is permanent in the log (you correct with a *compensating event*, never a delete). This is philosophically clean and operationally heavy.

> **When event sourcing is worth it:** domains where the *history of how state changed* is itself the valuable asset and is legally or functionally required — ledgers and accounting (every transaction is a fact you must keep), audit-critical workflows, systems where "show me exactly how this got to its current state" is a first-class requirement, and domains with rich temporal queries ("what did this look like as of last Tuesday?"). For a shopping cart, a search index, or a typical CRUD service, it is over-engineering. Use CDC-fed CQRS instead.

---

## Part 4 — The taxonomy that prevents disasters

Here is the distinction that, once internalized, prevents the most expensive architecture mistake in this whole course. Three things people call "event-driven," precisely separated:

| | What is the source of truth? | Where do events come from? | Current state? |
|---|---|---|---|
| **Event-driven service** | A normal current-state DB (per service) | The service *publishes* events when things happen (via outbox/CDC) | A normal mutable table you `UPDATE` |
| **CDC-fed CQRS** | A normal current-state write DB | *Derived* from the write DB's change log (Debezium) | Write model is normal tables; read models are projections |
| **Event-sourced aggregate** | The **event log itself** | Events *are* the writes; there's no separate "publish" | **Computed** by folding events; no canonical state table |

The traps this table defuses:

- **"We're event-driven, so we're event-sourced."** No. An event-driven service that publishes `OrderShipped` from a normal `orders` table is *not* event-sourced — its source of truth is the table, and the event is a notification. Calling it event-sourced leads people to delete the table and discover they can't reconstruct state. Most "event-driven" systems are the first row, and that is *fine* and *correct*.
- **"CQRS means event sourcing."** No. CQRS is about separating read and write *models*; the write model can be (and usually is) a normal current-state database, fed to read models by CDC. You can do CQRS with zero event sourcing. Greg Young, who popularized both terms, has spent years saying they are independent.
- **"Event sourcing is just CDC with extra steps."** No. CDC *derives* events from a database whose source of truth is current-state tables. Event sourcing has *no* current-state source of truth — the events are primary. They look similar on the Kafka topic; they are opposite in where truth lives.

The practical guidance for 2026: **default to a normal write model fed to projected read models by Debezium CDC (rows 1–2 of the table). Reach for full event sourcing (row 3) only when the event history is the asset and you've accepted the schema-migration and erasure costs.** When someone proposes "let's event-source the whole platform," your job is to ask which problem it solves that CDC-fed CQRS doesn't — and most of the time the honest answer is "none, and it costs us a decade of upcasting."

---

## Part 4a — The same feature, three ways: a worked comparison

Abstractions land harder when you see the *same* requirement built three ways. Take one feature — "track an order through its lifecycle and let other services react" — and build it as an event-driven service, as CDC-fed CQRS, and as an event-sourced aggregate. Watch where the truth lives in each.

**As an event-driven service (the common, correct default).** The `orders` service owns a normal `orders` table with a `status` column. Handling "ship order 1001" is an `UPDATE orders SET status='SHIPPED'`, and the service announces it by writing an outbox row in the same transaction (so no dual write). Other services consume `OrderShipped` and react.

```sql
BEGIN;
  UPDATE orders SET status = 'SHIPPED' WHERE order_id = 1001;
  INSERT INTO outbox (event_type, aggregate_id, payload)
  VALUES ('OrderShipped', '1001', '{"order_id":1001}');
COMMIT;
```

Truth lives in the `orders` row. The event is a *notification* of a fact the table already recorded. To answer "what status is order 1001?" you `SELECT status` — instant. This is right for the vast majority of services.

**As CDC-fed CQRS (when reads and writes want different shapes).** Same normalized `orders` write model, same `UPDATE`. But now you don't write an outbox row — Debezium captures the `orders` change stream, and a projector maintains a denormalized read model (the search index, the per-customer history, the rollup). The write side answers "is this order valid?"; the read models answer "show me all of this customer's shipped orders, full-text searchable" without a join the write schema would make expensive.

```sql
-- write side: same UPDATE as above. Debezium captures it. The projector then:
INSERT INTO order_search (order_id, status, customer_id, updated_lsn)
VALUES (1001, 'SHIPPED', 42, :lsn)
ON CONFLICT (order_id) DO UPDATE SET status = EXCLUDED.status, updated_lsn = EXCLUDED.updated_lsn
WHERE order_search.updated_lsn < EXCLUDED.updated_lsn;
```

Truth still lives in the `orders` row; the read models are *derived projections*, rebuildable from the stream. "What status?" reads the write model for correctness or a read model for staleness-tolerant queries. This is right when your read access patterns genuinely diverge from your write schema.

**As an event-sourced aggregate (when history is the asset).** Now there is *no* `orders.status` column. There is an append-only log: `OrderPlaced`, `OrderPaid`, `OrderShipped`. "Ship order 1001" loads the order's events, folds them to current state, validates the transition, and appends `OrderShipped` with an expected version.

```sql
-- there is no status column to UPDATE. There is only:
INSERT INTO events (aggregate_id, version, event_type, payload)
VALUES ('1001', 3, 'OrderShipped', '{"carrier":"crunch-logistics"}');
-- (rejected by UNIQUE(aggregate_id,version) if someone else already wrote version 3)
```

Truth *is* the event log. "What status?" is a replay (`fold(events)`), not a `SELECT` — so you snapshot for performance. But now you can answer questions the other two cannot: "what was order 1001's exact lifecycle, with timestamps?", "what did it look like before it shipped?", "replay every cancellation to find the pattern." This is right *only* when those questions are the point.

The comparison makes the cost visible: the event-driven version answers "current status" with one indexed read; the event-sourced version answers it with a replay-and-fold. You pay that cost for a *reason* — the history — and if you don't need the history, you've paid it for nothing. Lay the three side by side whenever a team proposes event sourcing, and ask: which column of this comparison is your actual requirement?

## Part 5 — The design-classification decision tree

When you read or propose an event-using design, classify it before you build it:

```
A design uses events. Which kind is it (and is it right)?
│
├─ Is the EVENT LOG the source of truth (no canonical state table)?
│   ├─ Yes → EVENT SOURCING. Ask: is history the asset? Have we accepted
│   │        upcasting + erasure + replay-debugging costs? If not → reconsider.
│   └─ No ↓
│
├─ Are read schemas SEPARATE from the write schema, kept in sync by the change log?
│   ├─ Yes → CQRS (almost always CDC-fed). Good default. Confirm read models
│   │        are projections (rebuildable) and consumers are idempotent.
│   └─ No ↓
│
├─ Does the service publish events about its own current-state DB?
│   ├─ Yes, via outbox/CDC → EVENT-DRIVEN, correctly. Confirm no DUAL WRITE.
│   └─ Yes, via "write DB then publish to Kafka" → STOP. That's a dual write.
│                                                  Fix with outbox or CDC. (Lecture 1)
│
└─ (And always) Are consumers idempotent against at-least-once delivery? If not → fix.
```

Tape this next to the CDC failure-mode tree from Lecture 1. The two together cover "is this design sound, and why isn't the pipeline flowing" — the two questions you'll be asked at the Phase 3 review.

---

## Part 4b — Where the change stream meets sagas (a Phase 2 callback)

Week 11 and 12 introduced **sagas** — multi-step business transactions across services, with compensation on failure — and the choreography-vs-orchestration choice. The change stream you've built this week is one of the two substrates a saga runs on, so it's worth connecting explicitly.

A **choreographed saga** is event-driven: each step reacts to the previous step's event and emits its own. "Reserve inventory" reacts to `OrderPlaced`, succeeds, emits `InventoryReserved`; "charge payment" reacts to that, succeeds, emits `PaymentCharged`; and so on. The events that drive a choreographed saga are *exactly* the kind of domain events this week produces — and they have the *exact* dual-write hazard this week warns about. If the inventory service updates its database and then publishes `InventoryReserved` as two steps, a crash between them strands the saga: inventory is reserved but nothing knows to charge payment. So a choreographed saga **must** publish its events via outbox or CDC, never a dual write. The saga's correctness depends on the atomicity guarantee this week is about.

An **orchestrated saga** (Temporal, Week 12) centralizes the steps in a workflow that calls each service and handles compensation. It depends less on the event stream for *driving* the saga — the orchestrator drives it — but the services it calls still often *emit* events (for read models, analytics, notifications) that must be published atomically.

The throughline: **the dual-write discipline is not an isolated lesson about CDC; it's load-bearing for every event-driven pattern in the course.** A choreographed saga, a CQRS read model, an event-driven notification, an event-sourced aggregate — all of them produce events, and all of them are corrupted by a dual write. The outbox/CDC guarantee from Lecture 1 is the foundation the entire event-driven half of Phase 2 and Phase 3 stands on. When you reach the capstone and wire `order-service` to drive a checkout saga while emitting `order.placed.v1`, the reason it doesn't lose events under failure traces directly back to this week.

## Part 5a — Rebuilding a read model: the operational superpower you'll actually use

The most practically valuable property of CQRS read models — the one that pays for the whole pattern in operations — is that **a read model is disposable and rebuildable**, because it's a pure projection of the change stream. This shows up constantly in production:

- **The projection logic had a bug.** You computed a denormalized field wrong for three weeks. With a normal mutable table you'd have to write a careful correction migration. With a projection: fix the projector, **drop the read model, replay the stream from the beginning**, and it rebuilds correct. The stream is the truth; the read model is a cache of a computation over it.
- **The read model's schema must change.** A new field, a different denormalization, a switch from Elasticsearch to a new search engine. You don't migrate the old read model in place — you build the *new* one by replaying the stream into it, run both in parallel until the new one is caught up, then cut over. Zero-downtime read-model schema change, for free.
- **The read model got corrupted.** A bad deploy, a disk failure, a partial write. You don't debug the corruption — you rebuild from the stream. The read model has no independent truth to recover; the stream has all of it.

This is why the projector's only job is to be a **correct, idempotent, deterministic fold** over the change stream. If it's all three, the read model is always reconstructable, and "rebuild it" is your answer to a whole class of problems that would otherwise be painful migrations.

The one prerequisite: the **stream must be retained long enough to replay**. With CDC, that means the source database (and any compacted Kafka topic) must hold enough history — or you re-snapshot from the source (Debezium's snapshot, Lecture 1 §4.4). With a full event store, the log is permanent by definition, so replay is always available. Either way, "can I rebuild this read model from scratch?" is a question you should be able to answer "yes" to for every projection you run; if the answer is "no," you've built a read model with hidden independent state, which is the thing CQRS exists to avoid.

## Part 6 — Recap

You should now be able to:

- Design CQRS: a normalized write model feeding N denormalized read-model projections via the change stream, and reason about eventual consistency and read-your-writes honestly.
- Rebuild a read model from scratch by replaying the stream, and use that property for bug fixes, schema changes, and corruption recovery.
- Build an idempotent projector — upsert-by-key, monotonic-by-LSN, or dedup-table — so at-least-once delivery yields exactly-once processing.
- Implement an event-sourced aggregate: append events as truth, fold to current state, guard concurrency with a `UNIQUE(aggregate_id, version)` optimistic check, and snapshot for performance.
- Recite event sourcing's real costs — historical-event schema migration, GDPR erasure against an append-only log, replay debugging, the no-delete tax — and decide when they're worth paying.
- Classify any design as event-driven, CDC-fed CQRS, or event-sourced, and refuse event sourcing where CDC-fed CQRS is the cheaper correct answer.
- Match the right idempotency pattern (monotonic upsert vs dedup table) to each kind of effect.

The judgment to carry out of this week: **the taxonomy is not pedantry — it is the difference between a system that works and one that quietly corrupts itself or buries a team in accidental complexity.** Call an event-driven service "event-sourced" and someone eventually deletes the source-of-truth table believing they can rebuild it. Call CQRS "event sourcing" and you sign up for upcasting you never needed. Skip the dual-write check and your stream silently disagrees with your database. Each of these is a real incident that traces back to a fuzzy mental model, and each is prevented by the same discipline: name what kind of event system you're building, locate the source of truth, verify there's no dual write, and confirm consumers are idempotent. Do that on every design that crosses your desk and you will be the engineer whose event platform doesn't surprise anyone.

Next: the exercises put this on the real `orders` stream — deploy Debezium, build an idempotent projector, and implement an event store with optimistic concurrency. Continue to [the exercises](../03-exercises/00-overview.md).

---

## Part 7 — A closing word on "eventual"

The word that recurs through this week — *eventual* consistency — deserves a precise final framing, because it's where engineers either make peace with distributed data or fight it forever.

Every derived view of your data in this course is *eventually* consistent with its source: the read replica (Week 13) trails the primary, the CQRS read model trails the write model, the lakehouse (Week 15) trails the change stream. "Eventually" is not a weasel word and it is not a failure — it is a *bounded* property you measure and manage. The lag has a distribution; you put an SLO on it; you route the reads that can't tolerate it back to the source. That is the entire discipline.

The mistake is treating "eventual" as either invisible (pretend the read model is always current — and ship the read-your-writes bug) or unacceptable (demand every read be strongly consistent — and lose the scalability that derived views buy you). The senior stance is the middle: **name the staleness window, bound it, and place each read according to whether it tolerates that window.** A product-browse read tolerates seconds; a balance-before-withdrawal read tolerates nothing. Same system, different placement, and the difference is a *decision you made on purpose*, not an accident you discovered in production.

Carry that into Week 15 (where the lakehouse's freshness gap is the same idea, one tier further out) and into the capstone (where every read path in the marketplace is one of these decisions). Eventual consistency, understood and bounded, is the price of scale — and it's a price worth paying, as long as you pay it knowingly.

The one-line summary of the whole week, then: **derive your events from commits (never dual-write), project them into purpose-shaped read models (CQRS), reach for event sourcing only when the history itself is the asset, make every consumer idempotent, and treat the staleness of every derived view as a number you bound rather than a surprise you discover.** Hold those five and you can build event-driven data systems that scale without quietly corrupting themselves — which is exactly what Phase 3 set out to teach.

## References

- *Martin Fowler — CQRS*: <https://martinfowler.com/bliki/CQRS.html>
- *Martin Fowler — Event Sourcing*: <https://martinfowler.com/eaaDev/EventSourcing.html>
- *Microservices.io — CQRS*: <https://microservices.io/patterns/data/cqrs.html>
- *Greg Young — CQRS Documents*: <https://cqrs.files.wordpress.com/2010/11/cqrs_documents.pdf>
- *Greg Young — Versioning in an Event Sourced System*: <https://leanpub.com/esversioning/read>
- *Kleppmann — Turning the database inside out*: <https://www.confluent.io/blog/turning-the-database-inside-out-with-apache-samza/>
- *EventStoreDB docs*: <https://developers.eventstore.com/>
- *Microservices.io — Transactional Outbox*: <https://microservices.io/patterns/data/transactional-outbox.html>
- *Microservices.io — Saga pattern* (choreography vs orchestration): <https://microservices.io/patterns/data/saga.html>
- *Microservices.io — Database per Service*: <https://microservices.io/patterns/data/database-per-service.html>
