# Week 14 — Change Data Capture, CQRS, and Event Sourcing

Welcome to the week where the storage tier stops being a place data *rests* and becomes a place data *flows from*. By Friday you will be able to take the `orders` table you partitioned last week, capture every change to it as a stream of events with Debezium, fan those events into a denormalized read model on one side and an append-only event store on the other, and — the part most engineers get wrong — articulate precisely the difference between an *event-driven service* and an *event-sourced aggregate*, because conflating them is how teams accidentally sign up for a decade of accidental complexity.

We assume you finished Week 13 and have a Postgres primary with `wal_level = logical` and the `orders` table. We also assume you still have the Kafka cluster from Phase 2 (Week 10) — Strimzi on Kind, Redpanda, or any broker you can produce to and consume from. If you don't, fix that first: every exercise this week moves events between Postgres, Kafka, and downstream consumers.

The one thing to internalize before you read another line: **the dual write is a lie you tell yourself, and change data capture is how you stop telling it.** The moment a service writes to its database *and* publishes an event to Kafka in two separate steps, you have a distributed transaction you didn't design and can't make atomic: the process can crash between the two writes, and now your database and your event stream disagree forever. CDC fixes this at the root — the event stream is *derived* from the database's own commit log (the WAL you learned last week), so there is exactly one source of truth and the events are a faithful, ordered consequence of it. You do not publish events *and* commit; you commit, and the events fall out of the commit. That inversion is the whole week.

This is where you stop dual-writing.

## Learning objectives

By the end of this week, you will be able to:

- **Explain** why dual writes are unsafe, and how the transactional outbox pattern and log-based CDC each solve it — and when you reach for which.
- **Deploy** a Debezium Postgres connector that reads the WAL via logical decoding and emits change events to Kafka, and read the structure of a Debezium change event (`before`, `after`, `op`, `source`, transaction metadata).
- **Distinguish** CDC (capturing changes to a database) from event sourcing (making events the system of record) from event-driven architecture (services reacting to events) — and place a given design correctly in that taxonomy.
- **Design** a CQRS system: a write model (the command side, normalized for correctness) and a separately-optimized read model (denormalized, query-shaped), kept in sync by the change stream — and reason about the read model's *eventual consistency* honestly.
- **Build** a read-model projector that consumes the `orders` change stream and maintains a denormalized search view, and a second consumer that writes the same events into an append-only event log — and make both **idempotent** so duplicate delivery doesn't corrupt them.
- **Implement** a small event-sourced aggregate: append events as the source of truth, rebuild state by replaying them, snapshot for performance, and handle schema evolution of stored events.
- **Reason** about the costs event sourcing imposes — schema migration of historical events, GDPR/right-to-erasure against an append-only log, debugging by replay, the "you can never delete" tax — and decide when those costs are worth paying.

## Prerequisites

This week assumes you have completed **C22 weeks 1–13**, or have equivalent backend and streaming fluency. Specifically:

- **Postgres 16** with `wal_level = logical`, the `orders` table from Week 13, and a replication role. You can `CREATE PUBLICATION` and create a logical replication slot.
- A **Kafka or Redpanda** cluster you can produce to and consume from (Strimzi on Kind from Week 10, or Redpanda locally). You can list topics and read messages with `kafka-console-consumer` / `rpk`.
- You understand **Kafka fundamentals** from Week 10: topics, partitions, offsets, consumer groups, keys, and why partition key choice controls ordering.
- You can write a non-trivial consumer in **Go or Python** (the exercises use both; the read-model projector is Python, the event-store consumer is Go).
- You understand **idempotency and at-least-once delivery** from Week 11 — that consumers must tolerate duplicates, because exactly-once-delivery is a fiction and exactly-once-*processing* is the real, achievable goal.

You do **not** need prior Debezium or event-sourcing experience. We start at the dual-write problem and build up. If you have used CQRS only as a buzzword in a design doc, this is the week it becomes a concrete, debuggable system.

## Topics covered

- **The dual-write problem.** Why "write to the DB, then publish to Kafka" is not atomic, the failure interleavings that corrupt state, and why you cannot fix it with a try/catch.
- **The transactional outbox pattern.** Writing the business change and an outbox row in one local transaction, then relaying the outbox to Kafka — the application-level solution, and how Debezium's outbox event router productionizes it.
- **Log-based CDC with Debezium.** The Debezium architecture (Kafka Connect, connectors, the Postgres connector on `pgoutput`), the anatomy of a change event, snapshots vs streaming, `REPLICA IDENTITY` and why `FULL` is sometimes required, tombstones, and topic-per-table routing.
- **CQRS in earnest.** Command model vs query model; why one normalized write schema and N denormalized read schemas is a feature not a smell; the read model as a *projection* of the change stream; staleness, read-your-writes, and how to communicate eventual consistency to product.
- **Materialized views and read-model projectors.** Building and maintaining a denormalized view (a search index, a cache, a reporting table) by consuming changes; rebuilding a projection from scratch by replaying the log; the projector's checkpoint/offset bookkeeping.
- **Event sourcing.** Events as the system of record; the aggregate, command, and event vocabulary; rebuilding state by folding events; snapshots; optimistic concurrency with an expected-version check; and the append-only event store (a Postgres `events` table, EventStoreDB, or a Kafka-backed log).
- **The taxonomy that prevents disasters.** Event-driven service (reacts to events, keeps its own state) vs CDC (derives events from a DB) vs event-sourced aggregate (events *are* the state). Why most systems want CDC-fed CQRS and *not* full event sourcing, and the honest cost ledger of event sourcing (historical-event schema migration, erasure compliance, replay debugging, the no-delete tax).

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                       | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|-------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Dual-write problem; outbox; Debezium architecture & events  |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Deploy Debezium on `orders`; read the change stream         |    1h    |    2.5h   |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | CQRS; read-model projector; eventual consistency            |    2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | Event sourcing; aggregates, replay, snapshots, the costs    |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Friday    | The end-to-end CDC pipeline; idempotency under chaos         |    0h    |    0h     |     1h     |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work                                       |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, review, taxonomy memo polish                          |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                             | **6h**   | **7h**    | **4h**     | **3.5h**  | **5h**   | **12h**      | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./00-overview.md) | This overview (you are here) |
| [resources.md](./01-resources.md) | The Debezium docs, CQRS/event-sourcing literature, Kafka Connect docs, and the talks worth your time |
| [lecture-notes/01-cdc-debezium-and-the-dual-write-problem.md](./02-lecture-notes/01-cdc-debezium-and-the-dual-write-problem.md) | The dual-write problem, the outbox pattern, Debezium architecture, and the change-event anatomy |
| [lecture-notes/02-cqrs-event-sourcing-and-the-taxonomy.md](./02-lecture-notes/02-cqrs-event-sourcing-and-the-taxonomy.md) | CQRS, read-model projections, event sourcing, and the event-driven/CDC/event-sourced taxonomy |
| [exercises/README.md](./03-exercises/00-overview.md) | Index of the three exercises |
| [exercises/exercise-01-debezium-on-orders.md](./03-exercises/exercise-01-debezium-on-orders.md) | Deploy a Debezium Postgres connector on `orders` and read the change events |
| [exercises/exercise-02-read-model-projector.py](./03-exercises/exercise-02-read-model-projector.py) | An idempotent Python projector that maintains a denormalized read model from the change stream |
| [exercises/exercise-03-event-store.go](./03-exercises/exercise-03-event-store.go) | A Go event store: append-only events, replay-to-rebuild, optimistic-concurrency version check |
| [challenges/README.md](./04-challenges/00-overview.md) | Index of the weekly challenge |
| [challenges/challenge-01-classify-and-fix-four-designs.md](./04-challenges/challenge-01-classify-and-fix-four-designs.md) | Classify four real designs into the taxonomy and fix the one that's secretly dual-writing |
| [quiz.md](./05-quiz.md) | 13 questions with a hidden answer key |
| [homework.md](./06-homework.md) | Six problems including the headline CDC-vs-event-sourcing taxonomy memo |
| [mini-project/README.md](./07-mini-project/00-overview.md) | The `orders-cdc` pipeline: Debezium → Kafka → read model + event store, idempotent under chaos |

## The "exactly-once processing, not delivery" promise

C22 uses a recurring marker for every exercise that ends in a consumer doing the right thing under duplicate delivery. The marker is: kill the consumer mid-batch, restart it, and prove the read model and the event store are **byte-identical** to a clean run — no double-applied change, no duplicate event:

```
$ ./reset-and-run.sh                         # clean run
read_model checksum: 9f2c...   event_count: 41023

$ ./run-with-chaos.sh   # kills the consumer mid-batch, restarts, replays duplicates
read_model checksum: 9f2c...   event_count: 41023      # IDENTICAL
```

If the checksum or the event count *changes* when you inject the chaos, your consumer is not idempotent and you are not done. At-least-once delivery means duplicates *will* arrive; the point of Week 14 is to make the *processing* exactly-once anyway, and to make any double-apply *loud* instead of silent.

## Stretch goals

If you finish the regular work early and want to push further:

- Configure the **Debezium outbox event router** (`io.debezium.transforms.outbox.EventRouter`) against a real `outbox` table, and compare it to raw table-level CDC. Note when the outbox's explicit event shape beats raw row changes (decoupling the event contract from the table schema).
- Add a **second read model** with a *different* shape (a daily revenue rollup table) fed by the same change stream, proving the CQRS claim that one write model feeds N independently-optimized read models.
- Replay your event store **from offset zero** into a fresh read model and confirm it converges to the same state as the live one. This is the event-sourcing superpower — and the test that proves your projection is a pure function of the log.
- Implement **snapshotting** in the event store: after every 100 events for an aggregate, write a snapshot, and rebuild from the latest snapshot + subsequent events. Measure the replay-time difference on an aggregate with 10,000 events.

## Up next

Week 15 takes the change stream you built here and routes it into the **lakehouse**: the same `orders` events you fan into a read model this week also land in Apache Iceberg, queryable by Trino for analytics. The event-store and CQRS literacy from this week is what lets you reason about the OLTP/OLAP boundary next week. Push your mini-project before you start it.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
