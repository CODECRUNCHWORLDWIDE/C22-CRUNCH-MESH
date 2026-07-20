# Week 10 — Eventing: Kafka and Redpanda

Welcome to the spine of every event-driven system you will ever build. By Friday you will be able to look at a topic on a running Kafka cluster and state, without hand-waving, how many partitions it has and why, what its retention policy is and what that costs, which consumer group owns which partition, and exactly how far behind each consumer is. You will read `kafka-consumer-groups.sh --describe` the way a backend engineer reads an HTTP status code.

We assume you finished Week 9 and have the `cart` and `inventory` services running in a Kind cluster behind Linkerd or Istio. Those services still talk to each other over gRPC, synchronously, in the request path. This week is where they stop. By the end of the week the cart service will *emit* `order.placed.v1` to a log instead of *calling* the order service, and the order service will *consume* it on its own schedule. That inversion — from "call you and wait" to "write a fact to a log and walk away" — is the single most important architectural move in this phase, and it is the move that makes the rest of the capstone possible.

The one thing to internalize before you read another line: **Kafka is not a message queue. It is a distributed, replicated, append-only commit log, and the consumer — not the broker — owns the read position.** A queue deletes a message when it is consumed; the log keeps it until retention expires, and every consumer group reads it independently at its own offset. That single difference is why you can add a new consumer group six months later and replay the entire history of orders to build a brand-new read model, why a slow consumer never blocks a fast one, and why "the message was lost" is almost never the real bug — the real bug is almost always an offset committed too early or a partition key that put everything on one partition.

This week is where you stop being surprised by that.

## Learning objectives

By the end of this week, you will be able to:

- **Explain** the Kafka log abstraction — topics, partitions, offsets, segments, the high-water mark — and why the consumer owning its read position changes everything downstream.
- **Choose** a partition count and a partition key for a topic given only its throughput target, its ordering requirement, and its consumer parallelism — and defend the choice against a 10x growth scenario.
- **Reason** about the replication protocol: leaders and followers, the in-sync replica (ISR) set, `acks`, `min.insync.replicas`, and exactly which combinations of those settings can and cannot lose an acknowledged write.
- **Predict** the delivery semantics — at-most-once, at-least-once, exactly-once-ish — that a given producer and consumer configuration actually delivers, before you ever run it.
- **Build** a correct Kafka producer in Go (with idempotence, keying, and proper error handling) and a correct consumer group in Python (with manual offset commits and graceful rebalance handling) for `order.placed.v1`.
- **Operate** Redpanda as a drop-in Kafka-API-compatible broker, explain the Raft-per-partition and thread-per-core architecture that replaces ZooKeeper/KRaft and the page cache, and benchmark it honestly against Kafka.
- **Diagnose** consumer lag on a live cluster with `kafka-consumer-groups.sh` and Redpanda's `rpk group describe`, distinguish a slow consumer from a stuck one from a rebalance storm, and prescribe the fix.
- **Design** retention and compaction for a topic — knowing when a topic is an event stream (time-retained) versus a changelog (compacted to the latest value per key) — and what each choice costs in disk and in semantics.

## Prerequisites

This week assumes you have completed **C22 weeks 1–9**, or have equivalent distributed-systems fluency. Specifically:

- A working **Kind** cluster (`kind create cluster` succeeds), `kubectl` configured, and Helm 3 installed. You have stood up a multi-pod workload before.
- The **`cart` and `inventory` services** from Weeks 5–9, with their `cart.v1` and `inventory.v1` Protobuf contracts. If your cart service is broken, the standalone producers and consumers each exercise provides are your fallback.
- **Go 1.23+** and **Python 3.12+** installed locally. You can write a Go program with goroutines and channels from memory, and an `async`/`await` Python program with `asyncio`.
- Comfort with the consistency vocabulary from Weeks 1–3 — you can define at-least-once vs at-most-once vs exactly-once and you remember why FLP makes the last one subtle.
- You can read a `docker compose` file and a Kubernetes `StatefulSet`, and you know the difference between a `Service` and a `StatefulSet`'s headless service.

You do **not** need prior Kafka experience. We start at the log abstraction and build up to the replication protocol, delivery semantics, and the Redpanda alternative. If you've used Kafka only through a managed cloud offering without knowing what a partition or an ISR is, this is the week that knowledge becomes load-bearing.

## Topics covered

- **The log abstraction in depth:** the topic as a named log, the partition as the unit of ordering and parallelism, the offset as a monotonic per-partition position, the segment as the on-disk file, the high-water mark, the log-end offset, and why "the consumer owns the offset" is the whole game.
- **Partitions and keys:** how the producer's partitioner maps a key to a partition (murmur2 hash mod partition count), why per-key ordering is the only ordering Kafka gives you, why you can add partitions but the key→partition mapping then shifts, and how to pick a partition count from a throughput and parallelism budget.
- **Consumer groups and rebalancing:** the group coordinator, partition assignment (range, round-robin, sticky, cooperative-sticky), the rebalance protocol and why a naive rebalance stops the world, `max.poll.interval.ms` and the "consumer kicked out of the group" failure, and the dual-consumer-group fan-out pattern.
- **The replication protocol:** leaders and followers, the ISR set, `acks=0/1/all`, `min.insync.replicas`, `unclean.leader.election`, and the exact matrix of which settings lose acknowledged data and which don't. KRaft (the ZooKeeper replacement) at the level you need to operate it.
- **Delivery semantics:** at-most-once, at-least-once, and exactly-once-within-Kafka (idempotent producer + transactions). Why at-least-once + an idempotent consumer is the pragmatic default, and where Kafka's EOS actually holds and where it leaks past the broker boundary (a teaser for Week 11).
- **Retention and compaction:** time/size retention (`retention.ms`, `retention.bytes`), log compaction (`cleanup.policy=compact`, tombstones, the changelog-topic pattern), and the decision rule for stream-vs-changelog.
- **Redpanda:** the C++ rewrite, thread-per-core (seastar), Raft-per-partition instead of ISR, no ZooKeeper and no separate KRaft quorum, no JVM and no page-cache dependence, the Kafka API compatibility surface, `rpk` as the operator CLI, and the honest 2026 comparison against Kafka (Strimzi/KRaft).
- **Operating the cluster:** Strimzi for Kafka-on-Kubernetes, the `KafkaTopic` CRD, consumer-lag diagnosis with `kafka-consumer-groups.sh` and `rpk group describe`, and the offset-reset tooling you use to replay history.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                  | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|--------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | The log abstraction; partitions, offsets, keys         |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Replication, ISR, acks; deploy Strimzi on Kind         |    1h    |    2.5h   |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | Consumer groups, rebalancing; the Go producer          |    2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | Delivery semantics; the Python consumer; retention     |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Friday    | Redpanda; rpk; the benchmark; lag diagnosis            |    0h    |    0h     |     1h     |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work                                 |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, review, postmortem polish                        |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                        | **6h**   | **7h**    | **4h**     | **3.5h**  | **5h**   | **12h**      | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | The Kafka docs, Jay Kreps's "The Log," the KIPs, Redpanda docs, and the talks worth your time |
| [lecture-notes/01-the-log-is-the-truth.md](./lecture-notes/01-the-log-is-the-truth.md) | The log abstraction, partitions/offsets/keys, consumer groups, the replication protocol, and delivery semantics |
| [lecture-notes/02-redpanda-retention-and-operating-the-cluster.md](./lecture-notes/02-redpanda-retention-and-operating-the-cluster.md) | Redpanda's architecture, retention and compaction, Strimzi on Kubernetes, and lag diagnosis |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-strimzi-on-kind.md](./exercises/exercise-01-strimzi-on-kind.md) | Deploy a 3-broker Kafka cluster on Kind via Strimzi, create `order.placed.v1`, and read both endpoints' state |
| [exercises/exercise-02-order-producer.go](./exercises/exercise-02-order-producer.go) | An idempotent, keyed Go producer for `order.placed.v1` with proper delivery-report handling |
| [exercises/exercise-03-order-consumer.py](./exercises/exercise-03-order-consumer.py) | A Python consumer group with manual commits, rebalance callbacks, and the dual-group fan-out demo |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-diagnose-three-lag-faults.md](./challenges/challenge-01-diagnose-three-lag-faults.md) | Detect and prescribe the fix for three different consumer-lag scenarios on a live cluster |
| [quiz.md](./quiz.md) | 13 questions with a hidden answer key |
| [homework.md](./homework.md) | Six problems including the one-page partitioning-and-retention design memo |
| [mini-project/README.md](./mini-project/README.md) | The `order-events` spine: a benchmark harness comparing Kafka and Redpanda on the same producer/consumer code |

## The "the offset advanced" promise

C22 uses a recurring marker for every exercise that ends in a consumer actually making durable progress:

```
$ kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
    --describe --group order-fulfillment
GROUP            TOPIC            PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
order-fulfillment order.placed.v1  0          1042            1042            0
order-fulfillment order.placed.v1  1          1039            1041            2
order-fulfillment order.placed.v1  2          1044            1044            0
```

If `LAG` is climbing without bound when you expected it flat, or `CURRENT-OFFSET` is stuck while `LOG-END-OFFSET` advances, you are not done. A consumer group whose lag grows forever is the canonical "we're falling behind and nobody noticed until the disk filled" failure. The point of Week 10 is to make `LAG: 0` (or a small, bounded, oscillating lag) ordinary — and to make an unbounded lag *loud* instead of silent.

## Stretch goals

If you finish the regular work early and want to push further:

- Read **KIP-98 (idempotent producer and transactions)** and **KIP-447 (producer-per-consumer-group EOS)** until you can explain, without notes, why `enable.idempotence=true` requires `acks=all` and `max.in.flight.requests.per.connection <= 5`: <https://cwiki.apache.org/confluence/display/KAFKA/Kafka+Improvement+Proposals>.
- Run **`kafka-producer-perf-test.sh`** and **`rpk redpanda admin brokers list`** against the same workload and produce a throughput-vs-latency curve. Note where Redpanda's thread-per-core model pulls ahead at the tail (p99.9) and where Kafka's batching wins on raw throughput.
- Reconfigure `order.placed.v1` from 3 partitions to 12 with `kafka-topics.sh --alter` while a producer keyed by `order_id` is running, and *observe* that existing keys now hash to different partitions — proving why you size partitions up front and treat repartitioning as a migration, not a knob.
- Turn a `cart.changelog` topic into a **compacted** topic, write three updates for the same `cart_id`, force a log-cleaner run, and confirm with `kafka-dump-log.sh` that only the latest value per key survives.

## Up next

Week 11 takes the at-least-once-plus-idempotency reflex you built here and makes it rigorous: NATS JetStream, Pulsar's tiered storage, the transactional outbox, and the honest truth about exactly-once across a broker boundary — the place Kafka's EOS stops and your application's idempotency keys have to take over. Push your mini-project before you start it.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
