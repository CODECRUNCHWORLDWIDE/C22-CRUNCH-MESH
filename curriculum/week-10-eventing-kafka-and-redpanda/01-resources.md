# Week 10 — Resources

Every resource here is **free** and pinned to a current version (Kafka 3.9 / 4.0 era, Redpanda 24.x, 2026) wherever the docs are versioned. The Apache Kafka docs are open. The Redpanda docs are public. The KIPs live on the Apache wiki. No paywalled books are linked, though two classic books are named for those who want the deep dive.

When a link is versioned, the current URL is given. The log-abstraction concepts are stable across versions; only the config-reference URLs and a few default values move.

## Required reading (work it into your week)

- **"The Log: What every software engineer should know about real-time data's unifying abstraction"** — Jay Kreps's foundational 2013 essay. This is the Monday read. It is long; read it anyway. Everything this week is a footnote to it:
  <https://engineering.linkedin.com/distributed-systems/log-what-every-software-engineer-should-know-about-real-time-datas-unifying-abstraction>
- **Apache Kafka — Design** (the "log," "replication," "delivery semantics" sections — the canonical word on what the broker guarantees):
  <https://kafka.apache.org/documentation/#design>
- **Apache Kafka — Producer and Consumer configuration** (the config reference you will keep open all week; read the `acks`, `enable.idempotence`, `enable.auto.commit`, `isolation.level` entries closely):
  <https://kafka.apache.org/documentation/#producerconfigs>
  <https://kafka.apache.org/documentation/#consumerconfigs>
- **Redpanda — Introduction to Redpanda** (the architecture overview: thread-per-core, Raft, no ZooKeeper, Kafka API compatibility):
  <https://docs.redpanda.com/current/get-started/intro-to-events/>
- **Confluent — "Exactly-Once Semantics Are Possible: Here's How Kafka Does It"** (the EOS explainer; read it Thursday before delivery semantics):
  <https://www.confluent.io/blog/exactly-once-semantics-are-possible-heres-how-apache-kafka-does-it/>

## The KIPs (skim, don't memorize)

You will not read these cover to cover. But the first time a colleague says "that's a KIP-98 thing," you want to know what they mean.

- **KIP-98 — Exactly Once Delivery and Transactional Messaging** (the idempotent producer and transactions; the producer epoch and sequence numbers live here):
  <https://cwiki.apache.org/confluence/display/KAFKA/KIP-98+-+Exactly+Once+Delivery+and+Transactional+Messaging>
- **KIP-447 — Producer scalability for exactly-once semantics** (why `sendOffsetsToTransaction` exists and how consume-transform-produce gets EOS):
  <https://cwiki.apache.org/confluence/display/KAFKA/KIP-447%3A+Producer+scalability+for+exactly+once+semantics>
- **KIP-500 / KIP-833 — KRaft (the ZooKeeper replacement)** — why Kafka removed ZooKeeper and what the controller quorum is:
  <https://cwiki.apache.org/confluence/display/KAFKA/KIP-500%3A+Replace+ZooKeeper+with+a+Self-Managed+Metadata+Quorum>
- **KIP-429 — Incremental Cooperative Rebalancing** (why `cooperative-sticky` stopped the stop-the-world rebalance):
  <https://cwiki.apache.org/confluence/display/KAFKA/KIP-429%3A+Kafka+Consumer+Incremental+Rebalance+Protocol>

## API references (the ones you'll have open all week)

- **`confluent-kafka-go`** — the librdkafka-backed Go client we use for the producer (idempotence, delivery reports):
  <https://pkg.go.dev/github.com/confluentinc/confluent-kafka-go/v2/kafka>
- **`confluent-kafka-python`** — the librdkafka-backed Python client for the consumer (manual commit, rebalance callbacks):
  <https://docs.confluent.io/platform/current/clients/confluent-kafka-python/html/index.html>
- **`rpk`** — the Redpanda CLI (`rpk topic`, `rpk group describe`, `rpk redpanda admin`):
  <https://docs.redpanda.com/current/reference/rpk/>
- **Strimzi `KafkaTopic` / `Kafka` CRD reference** — the YAML you write to run Kafka on Kubernetes:
  <https://strimzi.io/docs/operators/latest/configuring.html>

## Operating docs (the practical ones)

- **Strimzi — Deploying and Upgrading** (the operator, the `Kafka` CR, KRaft mode, the Kind quickstart):
  <https://strimzi.io/docs/operators/latest/deploying.html>
- **Strimzi — Quickstart on Kind/minikube**:
  <https://strimzi.io/quickstarts/>
- **Redpanda — Deploy on Kubernetes with the Redpanda Operator / Helm**:
  <https://docs.redpanda.com/current/deploy/deployment-option/self-hosted/kubernetes/>
- **Kafka — `kafka-consumer-groups.sh` and the CLI tools** (lag, offset reset, describe):
  <https://kafka.apache.org/documentation/#basic_ops>

## Kafka in real stacks (read the source of code that gets it right)

- **Debezium** — the CDC connector that turns a Postgres WAL into a Kafka topic; you'll use it in Week 11 and 14. Read how it keys its change events:
  <https://debezium.io/documentation/reference/stable/>
- **Kafka Streams — the `KTable` and changelog topics** — the canonical use of log compaction as a materialized-view backing store:
  <https://kafka.apache.org/documentation/streams/>
- **Apache Flink — Kafka source/sink with exactly-once** — how a stream processor commits offsets in a checkpoint to get EOS across the processing boundary:
  <https://nightlies.apache.org/flink/flink-docs-stable/docs/connectors/datastream/kafka/>

## Talks and deep dives worth your time (free, no signup)

- **"Kafka Internals" — Confluent Developer course** (free; the partition/replication/ISR animations are the clearest on the internet):
  <https://developer.confluent.io/courses/architecture/get-started/>
- **Redpanda engineering blog — "Thread-per-core programming" and "Raft in Redpanda"**:
  <https://www.redpanda.com/blog>
- **Jay Kreps / Martin Kleppmann — "Turning the database inside out"** (the conceptual bridge from a log to event sourcing and CQRS, which you'll build in Weeks 11 and 14):
  <https://www.confluent.io/blog/turning-the-database-inside-out-with-apache-samza/>

## Books (optional, not required, not paywalled-linked)

- **Martin Kleppmann, *Designing Data-Intensive Applications*** — Chapter 11 ("Stream Processing") is the single best treatment of logs, ordering, and delivery semantics in print. You met it in Weeks 1–3; reread Ch. 11 this week.
- **Gwen Shapira et al., *Kafka: The Definitive Guide* (2nd ed.)** — O'Reilly publishes early-release chapters free via Confluent; the replication and reliability chapters are the operating manual.

## Tools you'll use this week

- **`kafka-topics.sh`** — create/alter/describe topics; inspect partition and replica placement.
- **`kafka-consumer-groups.sh --describe`** — your primary diagnostic. Prints current offset, log-end offset, and lag per partition.
- **`kafka-console-producer.sh` / `kafka-console-consumer.sh`** — quick smoke tests without writing code.
- **`kafka-dump-log.sh`** — inspect segment files; prove that compaction kept only the latest value per key.
- **`rpk`** — Redpanda's all-in-one CLI: `rpk topic create/describe`, `rpk group describe`, `rpk redpanda admin brokers list`.
- **`kcat`** (formerly `kafkacat`) — vendor-neutral producer/consumer/metadata tool; works against Kafka and Redpanda identically.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **Topic** | A named, append-only log. Split into partitions. |
| **Partition** | The unit of ordering and parallelism. A totally ordered sequence of records. |
| **Offset** | A monotonic integer position within a partition. The consumer owns it. |
| **Segment** | The on-disk file a partition is stored in; partitions roll over to new segments. |
| **Consumer group** | A set of consumers that share the partitions of a topic; each partition goes to exactly one member. |
| **Rebalance** | Reassigning partitions to group members when membership changes. Cooperative-sticky avoids stop-the-world. |
| **Replication factor** | How many brokers hold a copy of each partition. |
| **Leader / follower** | The replica that handles reads/writes vs the ones that replicate from it. |
| **ISR** | In-Sync Replicas — the set of replicas caught up enough to be eligible for leadership. |
| **`acks`** | How many acknowledgements a producer waits for: `0` (none), `1` (leader), `all` (full ISR). |
| **`min.insync.replicas`** | The smallest ISR size that still accepts an `acks=all` write. |
| **High-water mark** | The highest offset that has been replicated to the full ISR; the highest a consumer can read. |
| **Log compaction** | Retention that keeps only the latest record per key (a changelog), instead of by time. |
| **Tombstone** | A record with a null value; in a compacted topic it marks a key for deletion. |
| **Idempotent producer** | A producer that uses a PID + sequence number so the broker dedupes retries. |
| **Consumer lag** | `LOG-END-OFFSET - CURRENT-OFFSET`: how far behind a group is. |
| **KRaft** | Kafka Raft — the controller quorum that replaced ZooKeeper for metadata. |
| **Redpanda** | A C++, thread-per-core, Raft-per-partition broker speaking the Kafka API; no JVM, no ZooKeeper. |

---

*If a link 404s, please open an issue so we can replace it.*
