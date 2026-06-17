# Week 11 — NATS JetStream, Pulsar, and Exactly-Once Semantics

Welcome to the week where "exactly-once" stops being a marketing word and becomes an engineering contract you can actually write down, defend, and test. By Friday you will be able to look at any event-driven flow and state, without hand-waving, whether it is at-most-once, at-least-once, or effectively-exactly-once — and exactly *which* mechanism (an idempotency key, a transactional outbox, a JetStream dedup window, a Pulsar transaction) is carrying that guarantee at each hop. You will read a duplicate delivery the way a backend engineer reads a retry: not as a bug, but as the expected event your system was built to absorb.

We assume you finished Week 10 and have the `order-events` spine running — a keyed, idempotent-producer Kafka (or Redpanda) topic with an at-least-once consumer group. You also saw, in exercise-3 part D, that crashing before commit redelivers records, and that your consumer's `_process()` was *not* idempotent — it double-printed. This week we fix that, properly, and then we widen the lens to two other brokers (NATS JetStream and Pulsar) that model durability and exactly-once differently, so you can choose between them with evidence instead of habit.

The one thing to internalize before you read another line: **exactly-once delivery is impossible across an unreliable network (this is a direct consequence of the FLP and two-generals results you met in Week 1), but exactly-once *processing* — the effect happening once — is very achievable, and it is achieved not by the broker but by making the consumer idempotent and the write atomic.** Kafka's EOS, NATS JetStream's dedup, and Pulsar's transactions each give you a *piece* of this, but every one of them stops at the boundary of your database and your external API calls. The moment you charge a card, you are outside every broker's transaction, and the guarantee becomes yours to build — with an idempotency key and a transactional outbox. This week is where you build it.

This week is where you stop being afraid of duplicate delivery.

## Learning objectives

By the end of this week, you will be able to:

- **State** precisely why exactly-once *delivery* is impossible over an unreliable network, and why exactly-once *processing* (the effect once) is nonetheless achievable, and name the two mechanisms that achieve it: idempotency and atomic writes.
- **Compare** NATS core (fire-and-forget pub/sub) against NATS JetStream (durable, replicated, replayable streams), explain subject hierarchies and wildcards, and configure stream retention, replicas, and the dedup window.
- **Explain** Pulsar's architecture — the broker/bookie split, BookKeeper as the storage layer, tiered storage offload, and subscription modes (exclusive, shared, failover, key-shared) — and how it differs from Kafka's partition-owned-log model.
- **Implement** the **transactional outbox pattern** in Postgres: write the business row and the outbox row in one transaction, then relay the outbox to the broker, so a published event can never disagree with the committed state.
- **Build** a genuinely **idempotent consumer** that survives duplicate delivery — using an idempotency key, a dedup table, or an upsert — and prove with a chaos test (kill mid-batch, restart, re-process) that it produces zero double-effects.
- **Distinguish** Kafka EOS, NATS JetStream dedup, and Pulsar transactions: what each guarantees, what it costs, and exactly where each one's guarantee ends and your application's must begin.
- **Reason** about the dual-write problem — why writing to the database and the broker in two separate steps is unsafe — and articulate the outbox (and its cousin, change-data-capture, previewing Week 14) as the correct fix.
- **Choose** between Kafka, NATS JetStream, and Pulsar for a given workload based on throughput, retention, multi-tenancy, operational footprint, and the delivery semantics each makes easy.

## Prerequisites

This week assumes you have completed **C22 weeks 1–10**, or have equivalent fluency. Specifically:

- The **`order-events` spine** from Week 10: a keyed Kafka/Redpanda topic with an at-least-once consumer group, and the muscle memory of reading the lag table. If it's broken, the standalone producers/consumers each exercise provides are your fallback.
- A working **Postgres** (Docker is fine) — you'll build the outbox here. You can write a transaction, a unique constraint, and an upsert in SQL from memory.
- **Go 1.23+** and **Python 3.12+**. The outbox relay and idempotent consumer are written in both; you'll read and run both.
- The **FLP / two-generals** intuition from Week 1 — you can explain why no protocol guarantees agreement over an unreliable channel in bounded time. This week makes that abstract result concrete and operational.
- Comfort with the at-least-once vs at-most-once vs exactly-once vocabulary from Week 10 §5. This week deepens it; it does not re-teach it.

You do **not** need prior NATS or Pulsar experience. We start from NATS core pub/sub and Pulsar's architecture and build up. If you've used JetStream only through a managed offering without knowing what a dedup window or a consumer's ack policy is, this is the week that knowledge becomes load-bearing.

## Topics covered

- **The impossibility, stated honestly:** why exactly-once *delivery* cannot exist over an unreliable network (FLP, two-generals), and the reframe that makes the problem solvable — move the guarantee from *delivery* to *effect*, via idempotency and atomicity.
- **NATS core vs JetStream:** NATS core as in-memory, at-most-once, fire-and-forget pub/sub with subject-based addressing and wildcards (`order.*`, `order.>`); JetStream as the durable, replicated (Raft), replayable layer on top — streams, consumers (push vs pull, durable vs ephemeral), ack policies (none/all/explicit), and the **dedup window** (`Nats-Msg-Id`).
- **Pulsar architecture:** the stateless broker layer over the stateful BookKeeper bookies, the ledger/entry model, why the storage/serving split enables independent scaling and instant rebalancing, tiered storage offload to object storage, and the four subscription modes — exclusive, failover, shared, key-shared — and which delivery semantics each enables.
- **The dual-write problem:** why "write to Postgres, then publish to Kafka" in two steps can leave the event and the state disagreeing (crash between the two), and why this is the single most common correctness bug in event-driven systems.
- **The transactional outbox pattern:** write the business change and an `outbox` row in one DB transaction; a relay reads the outbox and publishes to the broker, marking rows sent (or letting CDC do it). At-least-once from the outbox + idempotent consumer = effectively-exactly-once end-to-end.
- **Idempotency keys and dedup tables:** carrying a stable id (the event id, the order id, a request id) so the consumer can recognize and drop a duplicate; the `INSERT ... ON CONFLICT DO NOTHING` and the dedup-table patterns; idempotent upserts into a read model.
- **Kafka EOS vs JetStream dedup vs Pulsar transactions:** a side-by-side of what each broker's "exactly-once" actually covers, what configuration turns it on, and the precise boundary where each stops and your idempotency must take over.
- **Choosing a broker:** the honest 2026 comparison of Kafka/Redpanda, NATS JetStream, and Pulsar across throughput, retention, multi-tenancy, operational footprint, and which delivery semantics each makes easy or hard.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                     | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|-----------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | The impossibility; idempotency & atomicity; NATS core     |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | NATS JetStream: streams, consumers, dedup window          |    1h    |    2.5h   |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | Pulsar architecture; subscriptions; the dual-write bug    |    2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | The outbox pattern; idempotent consumer; the chaos test   |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Friday    | EOS vs dedup vs transactions; choosing a broker           |    0h    |    0h     |     1h     |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work                                     |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, review, postmortem polish                           |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                           | **6h**   | **7h**    | **4h**     | **3.5h**  | **5h**   | **12h**      | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./00-overview.md) | This overview (you are here) |
| [resources.md](./01-resources.md) | The NATS/JetStream docs, Pulsar docs, the outbox-pattern canon, and the talks worth your time |
| [lecture-notes/01-exactly-once-is-a-contract.md](./02-lecture-notes/01-exactly-once-is-a-contract.md) | The impossibility, idempotency and atomicity, NATS core vs JetStream, and Pulsar's architecture |
| [lecture-notes/02-the-outbox-and-idempotent-consumers.md](./02-lecture-notes/02-the-outbox-and-idempotent-consumers.md) | The dual-write problem, the transactional outbox, idempotency keys, and Kafka EOS vs JetStream dedup vs Pulsar transactions |
| [exercises/README.md](./03-exercises/00-overview.md) | Index of the three exercises |
| [exercises/exercise-01-jetstream-and-pulsar.md](./03-exercises/exercise-01-jetstream-and-pulsar.md) | Stand up NATS JetStream and Pulsar, create durable streams, and observe dedup and subscription modes |
| [exercises/exercise-02-outbox-relay.go](./03-exercises/exercise-02-outbox-relay.go) | A Postgres transactional-outbox writer and relay in Go that publishes to the broker exactly as the outbox dictates |
| [exercises/exercise-03-idempotent-consumer.py](./03-exercises/exercise-03-idempotent-consumer.py) | An idempotent consumer with a dedup table that survives a kill-mid-batch chaos test with zero double-charges |
| [challenges/README.md](./04-challenges/00-overview.md) | Index of the weekly challenge |
| [challenges/challenge-01-diagnose-three-delivery-faults.md](./04-challenges/challenge-01-diagnose-three-delivery-faults.md) | Detect and prescribe the fix for three different delivery-semantics faults on a live system |
| [quiz.md](./05-quiz.md) | 13 questions with a hidden answer key |
| [homework.md](./06-homework.md) | Six problems including the one-page exactly-once-boundary design memo |
| [mini-project/README.md](./07-mini-project/00-overview.md) | The `idempotent-checkout` pipeline: outbox + idempotent consumer proven correct under chaos, on two brokers |

## The "zero double-charges" promise

C22 uses a recurring marker for every exercise that ends in a duplicate delivery being correctly absorbed:

```
$ ./chaos-test.sh
producing 1000 order.placed events...
killing consumer mid-batch at record ~437...
restarting consumer (it will redeliver from the last committed offset)...
verifying ledger:
  events delivered (incl. duplicates): 1063
  unique orders charged:               1000
  double-charges:                      0      <-- the line that matters
PASS: at-least-once delivery, exactly-once effect.
```

If `double-charges` is anything but `0`, you are not done. A consumer that double-charges on redelivery is the canonical "exactly-once was a wish, not a contract" failure. The point of Week 11 is to make `double-charges: 0` ordinary even under deliberate chaos — and to make a nonzero count *loud* instead of discovered in a customer complaint.

## Stretch goals

If you finish the regular work early and want to push further:

- Read the canonical **transactional outbox** and **dual-write** write-ups (microservices.io and the Debezium outbox guide) until you can explain, without notes, why CDC-based outbox relay (Week 14) is strictly better than a polling relay for high throughput.
- Configure a **JetStream stream with a 2-minute dedup window** and prove that re-publishing the same `Nats-Msg-Id` within the window is silently dropped, but the same id *after* the window is accepted — and reason about why a dedup window is a weaker guarantee than an outbox.
- Stand up **Pulsar with tiered storage** to MinIO and offload an old ledger to object storage, then read it back transparently — proving the storage/serving split lets you keep infinite history cheaply.
- Implement the **same idempotent consumer three ways** — dedup table, `ON CONFLICT DO NOTHING`, and an idempotent upsert into a read model — and write a paragraph on when each is the right tool.

## Up next

Week 12 takes the saga-by-events you have been hand-wiring with topics and outboxes and replaces it with **Temporal** — a workflow engine that makes the orchestration explicit, durable, and replayable, and that turns "compensate on failure" from scattered consumer logic into a single readable workflow. You'll be able to say exactly when orchestration beats the choreography you built this week. Push your mini-project before you start it.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
