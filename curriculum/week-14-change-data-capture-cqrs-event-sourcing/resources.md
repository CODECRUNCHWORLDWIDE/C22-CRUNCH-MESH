# Week 14 — Resources

Every resource here is **free** and pinned to **Debezium 2.x** and **Postgres 16** wherever the docs are versioned. The Debezium documentation is open and excellent — read the Postgres connector page in full, not a blog summary of it. The CQRS and event-sourcing literature linked below is the canonical, freely-published source material (Fowler, Young, Vernon's talks). No paywalled books are required.

When a link is versioned, the current stable URL is given. Debezium's connector options move between minor versions; if a property name has changed, the connector's own docs are authoritative.

## Required reading (work it into your week)

- **Debezium — Postgres connector** — the canonical reference. Read it Monday, then again Tuesday while you configure it:
  <https://debezium.io/documentation/reference/stable/connectors/postgresql.html>
- **Debezium — event structure** — `before`/`after`/`op`/`source`, the envelope, schema vs payload:
  <https://debezium.io/documentation/reference/stable/connectors/postgresql.html#postgresql-events>
- **Martin Fowler — CQRS** — the canonical short essay; read it twice:
  <https://martinfowler.com/bliki/CQRS.html>
- **Martin Fowler — Event Sourcing** — the canonical description, costs included:
  <https://martinfowler.com/eaaDev/EventSourcing.html>
- **Microservices.io — Transactional Outbox** — the pattern, the problem it solves, the variants:
  <https://microservices.io/patterns/data/transactional-outbox.html>
- **Microservices.io — CQRS** — the pattern in the microservices context, with the eventual-consistency caveats:
  <https://microservices.io/patterns/data/cqrs.html>

## The deeper references (skim now, return when you need them)

- **Debezium — outbox event router** — the SMT that turns an `outbox` table into clean domain events:
  <https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html>
- **Debezium — snapshots** — initial vs incremental snapshots, and why the first connector start reads the whole table:
  <https://debezium.io/documentation/reference/stable/connectors/postgresql.html#postgresql-snapshots>
- **Kafka Connect — concepts** — connectors, tasks, converters, the Connect runtime Debezium ships on:
  <https://kafka.apache.org/documentation/#connect>
- **Greg Young — CQRS Documents** — the long-form from the person who coined much of the vocabulary:
  <https://cqrs.files.wordpress.com/2010/11/cqrs_documents.pdf>
- **Confluent — "Turning the database inside out"** (Kleppmann) — the essay that frames CDC + streams + materialized views as one idea:
  <https://www.confluent.io/blog/turning-the-database-inside-out-with-apache-samza/>

## API & config references (the ones you'll have open all week)

- **`pgoutput` logical decoding** — the Postgres plugin Debezium uses by default on PG 16:
  <https://www.postgresql.org/docs/16/protocol-logical-replication.html>
- **`REPLICA IDENTITY`** — `DEFAULT` vs `FULL` vs `USING INDEX`, and what each makes available in `before`:
  <https://www.postgresql.org/docs/16/sql-altertable.html#SQL-ALTERTABLE-REPLICA-IDENTITY>
- **Debezium connector REST API** — register/update/delete a connector on Kafka Connect:
  <https://debezium.io/documentation/reference/stable/operations/debezium-server.html>
- **`confluent-kafka` Python client** — the consumer you'll use for the projector:
  <https://docs.confluent.io/platform/current/clients/confluent-kafka-python/html/index.html>
- **`segmentio/kafka-go`** — the Go Kafka client for the event-store consumer:
  <https://github.com/segmentio/kafka-go>

## Event sourcing — the honest stuff

- **EventStoreDB documentation** — the purpose-built event store; read it even if you implement your own:
  <https://developers.eventstore.com/>
- **"Event Sourcing: the good, the bad, and the ugly"** — community write-ups on the costs (GDPR, schema migration, replay); search the conference archives for the skeptical talks, which are more useful than the evangelical ones.
- **Versioning in an Event Sourced System (Young)** — the definitive treatment of evolving stored events:
  <https://leanpub.com/esversioning/read> (the read-online edition is free)

## Tools you'll use this week

- **Debezium on Kafka Connect** — `debezium/connect` image, or Strimzi `KafkaConnect` + `KafkaConnector` CRDs.
- **`kcat`** (formerly kafkacat) — the swiss-army knife for inspecting Kafka topics: `kcat -b localhost:9092 -t orders.public.orders -C -o beginning`.
- **`rpk`** (if on Redpanda) — `rpk topic consume orders.public.orders`.
- **`psql`** — to make the changes Debezium captures, and to read the `REPLICA IDENTITY` of a table (`\d+ orders`).
- **`jq`** — Debezium events are JSON; `jq '.payload.op'` to project the op out of an event.
- **`psycopg` v3 / `kafka-go`** — the consumers in the exercises.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **CDC** | Change Data Capture — turning a database's changes into a stream of events, log-based or query-based. |
| **Log-based CDC** | Reading the database's commit log (Postgres WAL) to derive change events. Low-overhead, faithful, ordered. |
| **Dual write** | Writing to the DB and publishing an event in two separate steps. Not atomic; the root problem CDC solves. |
| **Transactional outbox** | Writing the change and an outbox row in one local transaction, then relaying the outbox. The app-level fix for dual writes. |
| **Debezium** | The open-source log-based CDC platform; runs as Kafka Connect connectors. |
| **Change event** | A Debezium record with `before`, `after`, `op` (c/u/d/r), and `source` metadata. |
| **`REPLICA IDENTITY`** | What Postgres puts in the `before` image; `FULL` includes the whole old row (needed for some CDC and updates). |
| **CQRS** | Command Query Responsibility Segregation — separate the write model from one or more read models. |
| **Read model / projection** | A denormalized, query-shaped view maintained by consuming the change stream. Eventually consistent. |
| **Event sourcing** | Making an append-only log of events the system of record; state is a fold over the events. |
| **Aggregate** | The consistency boundary in event sourcing/DDD; commands produce events that mutate its state. |
| **Snapshot** | A cached materialized state of an aggregate at a version, so replay doesn't start from event zero. |
| **Idempotent consumer** | A consumer that processes a duplicate message with no additional effect. The key to exactly-once *processing*. |
| **Event-driven** | Services react to events and keep their own state. Not the same as event-sourced. |

---

*If a link 404s, please open an issue so we can replace it.*
