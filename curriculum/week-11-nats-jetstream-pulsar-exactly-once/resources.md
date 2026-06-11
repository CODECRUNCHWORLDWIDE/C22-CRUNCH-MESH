# Week 11 — Resources

Every resource here is **free** and pinned to a current version (NATS 2.10+, Pulsar 3.x/4.x, 2026) wherever the docs are versioned. The NATS docs are open. The Apache Pulsar docs are public. The outbox-pattern canon (microservices.io, Debezium) is open. No paywalled books are linked, though two classics are named for the deep dive.

When a link is versioned, the current URL is given. The delivery-semantics concepts are stable across versions; only the config-reference URLs and a few defaults move.

## Required reading (work it into your week)

- **"Pattern: Transactional outbox"** — Chris Richardson's microservices.io page. This is the Monday/Thursday read; it is the canonical statement of the pattern you build this week:
  <https://microservices.io/patterns/data/transactional-outbox.html>
- **"Pattern: Idempotent consumer"** — the companion pattern; the other half of effectively-exactly-once:
  <https://microservices.io/patterns/communication-style/idempotent-consumer.html>
- **NATS — JetStream concepts** (streams, consumers, ack policies, the dedup window via `Nats-Msg-Id`):
  <https://docs.nats.io/nats-concepts/jetstream>
- **Apache Pulsar — Concepts and Architecture** (broker/bookie split, subscriptions, the four subscription modes):
  <https://pulsar.apache.org/docs/concepts-architecture-overview/>
  <https://pulsar.apache.org/docs/concepts-messaging/#subscriptions>
- **Confluent — "Exactly-Once Semantics Are Possible"** (reread from Week 10; this week you'll cross its boundary deliberately):
  <https://www.confluent.io/blog/exactly-once-semantics-are-possible-heres-how-apache-kafka-does-it/>

## The deeper writeups (skim, don't memorize)

- **Debezium — Outbox Event Router** (the CDC-based outbox relay you'll prefer at scale; previews Week 14):
  <https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html>
- **Martin Kleppmann — "Using logs to build a solid data infrastructure (or: why dual writes are a bad idea)"** (the definitive statement of the dual-write problem):
  <https://www.confluent.io/blog/using-logs-to-build-a-solid-data-infrastructure-or-why-dual-writes-are-a-bad-idea/>
- **NATS — JetStream and exactly-once** (the dedup window and its precise guarantee and limits):
  <https://docs.nats.io/using-nats/developer/develop_jetstream/model_deep_dive>
- **Pulsar — Transactions** (the producer/consumer transaction API and what it covers):
  <https://pulsar.apache.org/docs/transactions/>

## API references (the ones you'll have open all week)

- **`nats.go`** — the Go NATS/JetStream client (`jetstream` package: streams, consumers, `Publish` with `MsgId`):
  <https://pkg.go.dev/github.com/nats-io/nats.go>
- **`nats.py`** — the asyncio NATS/JetStream Python client:
  <https://nats-io.github.io/nats.py/>
- **`pulsar-client` (Python)** — producer/consumer, subscription modes, transactions:
  <https://pulsar.apache.org/docs/client-libraries-python/>
- **`pgx` (Go Postgres driver)** — transactions and the outbox writer:
  <https://pkg.go.dev/github.com/jackc/pgx/v5>
- **`confluent-kafka-python`** — reused for the idempotent Kafka consumer:
  <https://docs.confluent.io/platform/current/clients/confluent-kafka-python/html/index.html>

## Operating docs (the practical ones)

- **NATS — Running a JetStream cluster** (the `nats-server` config, `-js`, replicas, `nats` CLI):
  <https://docs.nats.io/running-a-nats-service/configuration/clustering/jetstream_clustering>
- **`nats` CLI reference** (`nats stream add`, `nats consumer add`, `nats stream report`):
  <https://github.com/nats-io/natscli>
- **Apache Pulsar — Run Pulsar in Docker / standalone**:
  <https://pulsar.apache.org/docs/getting-started-docker/>
- **`pulsar-admin` CLI** (topics, subscriptions, namespaces, transactions):
  <https://pulsar.apache.org/docs/admin-api-overview/>

## The patterns in real stacks (read the source of code that gets it right)

- **Debezium outbox examples** — a runnable outbox + CDC relay on Postgres → Kafka:
  <https://github.com/debezium/debezium-examples/tree/main/outbox>
- **NATS by Example** — JetStream dedup, pull consumers, key-value, all runnable:
  <https://natsbyexample.com/>
- **Pulsar examples** — subscription modes and transactions, runnable:
  <https://github.com/apache/pulsar/tree/master/examples>

## Talks and deep dives worth your time (free, no signup)

- **"Exactly-once delivery is impossible; here's what to do instead"** — search the conference archives (QCon, GOTO, Strange Loop) for the idempotency-and-outbox talks; the canonical framing of delivery-vs-effect:
  <https://www.youtube.com/results?search_query=exactly+once+delivery+idempotent+consumer>
- **NATS — "JetStream deep dive"** (Synadia/NATS maintainers; streams, consumers, dedup):
  <https://www.youtube.com/@SynadiaCommunications>
- **Apache Pulsar — "Pulsar architecture and BookKeeper"** (StreamNative; the broker/bookie split explained):
  <https://www.youtube.com/@streamnative>

## Books (optional, not required, not paywalled-linked)

- **Martin Kleppmann, *Designing Data-Intensive Applications*** — Chapter 9 ("Consistency and Consensus") for why exactly-once delivery is impossible, Chapter 11 for stream processing and effectively-once. The single best treatment in print.
- **Sam Newman, *Building Microservices* (2nd ed.)** — the saga and outbox chapters frame why dual writes are dangerous and orchestration-vs-choreography (which sets up Week 12).

## Tools you'll use this week

- **`nats` CLI** — `nats stream add/report`, `nats consumer add`, `nats pub`/`sub` (with `--count`), `nats stream view`. Your JetStream diagnostic.
- **`pulsar-admin`** — `topics create-partitioned-topic`, `topics stats`, `topics subscriptions`. Your Pulsar diagnostic.
- **`psql`** — inspect the `outbox` and dedup tables, run the transactions by hand to understand them.
- **`kafka-consumer-groups.sh` / `rpk group describe`** — reused from Week 10 for the Kafka idempotent consumer.
- **A `chaos-test.sh`** — the script that kills the consumer mid-batch and verifies zero double-charges; you write it in the mini-project.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **At-most-once** | Deliver 0 or 1 times; never duplicates, may lose. Commit-before-process. |
| **At-least-once** | Deliver 1 or more times; never loses, may duplicate. Process-before-commit. |
| **Exactly-once (delivery)** | Deliver exactly 1 time. **Impossible** over an unreliable network. |
| **Exactly-once (effect / processing)** | The *effect* happens once, even if delivery happens many times. Achievable via idempotency + atomicity. |
| **Idempotency key** | A stable id (event id, order id, request id) the consumer uses to recognize and drop a duplicate. |
| **Dedup table** | A table of seen idempotency keys; a duplicate is an insert that hits the unique constraint. |
| **Dual-write problem** | Writing to the DB and the broker as two separate steps; a crash between them leaves state and event disagreeing. |
| **Transactional outbox** | Write the business row and an `outbox` row in one DB transaction; a relay publishes the outbox. Removes the dual write. |
| **Outbox relay** | The process that reads unpublished outbox rows and produces them to the broker (polling, or CDC-based). |
| **NATS core** | In-memory, at-most-once, fire-and-forget pub/sub with subject addressing. No persistence. |
| **JetStream** | NATS's durable, replicated (Raft), replayable layer: streams + consumers + dedup. |
| **Subject / wildcard** | NATS addressing: `order.placed`, `order.*` (one token), `order.>` (one-or-more tokens). |
| **Dedup window** | A JetStream stream's time window in which a repeated `Nats-Msg-Id` is dropped. |
| **Ack policy** | A JetStream consumer's ack mode: none, all, or explicit (per-message). |
| **Bookie / BookKeeper** | Pulsar's storage layer; the stateful nodes that hold the log (ledgers/entries). |
| **Subscription mode** | Pulsar consumer mode: exclusive, failover, shared, or key-shared. |
| **Key-shared** | Pulsar mode: messages with the same key always go to the same consumer (ordered per key, like Kafka). |
| **Tiered storage** | Offloading old segments/ledgers to object storage (S3/GCS) while keeping them readable. |

---

*If a link 404s, please open an issue so we can replace it.*
