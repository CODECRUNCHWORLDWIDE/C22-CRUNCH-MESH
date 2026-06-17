# Week 14 — Exercises

Three focused drills that move events between Postgres, Kafka, and downstream consumers. Each takes 45–60 minutes. Do them in order — exercise 3's idempotency mindset builds on the projector you write in exercise 2, which consumes the stream you stand up in exercise 1. Run everything against the Postgres 16 (with `wal_level = logical`) and Kafka/Redpanda you have from Weeks 13 and 10.

## Index

1. **[Exercise 1 — Debezium on `orders`](./exercise-01-debezium-on-orders.md)** — deploy a Debezium Postgres connector that captures the `orders` table to Kafka, then read and decode the change events (`op`, `before`, `after`, LSN). Toggle `REPLICA IDENTITY` and watch `before` change. (~55 min, guided)
2. **[Exercise 2 — The read-model projector](./exercise-02-read-model-projector.py)** — an idempotent Python consumer that projects the `orders` change stream into a denormalized read-model table, and survives duplicate delivery without corrupting it. (~50 min, runnable)
3. **[Exercise 3 — The event store](./exercise-03-event-store.go)** — a Go append-only event store with replay-to-rebuild and an optimistic-concurrency version check that rejects concurrent conflicting commands. (~50 min, runnable)

## How to work the exercises

- Have Postgres 16 (`wal_level = logical`, the `orders` table, a replication-capable role) and a Kafka/Redpanda broker running before you start.
- For Debezium you need Kafka Connect with the Debezium Postgres connector. The `debezium/connect` image is the simplest; Strimzi `KafkaConnect`+`KafkaConnector` CRDs work on Kind.
- **Read the change event before you build against it.** `kcat ... | jq '.payload'` once, by hand, so you know the shape your consumer parses.
- When the stream "isn't flowing," walk the CDC decision tree (Lecture 1 §6) before touching the connector. Connector status first, slot second, snapshot third.
- Each runnable exercise ends with an **expected output** block. If your output doesn't match the *shape*, you're not done.

## Running the Python and Go exercises

The Python projector needs `psycopg` v3 and a Kafka client:

```bash
python3 -m pip install "psycopg[binary]>=3.1" "confluent-kafka>=2.3"
python3 exercise-02-read-model-projector.py \
    --bootstrap localhost:9092 --topic shop.public.orders \
    --dsn "host=localhost user=postgres dbname=shop"
```

The Go event store is a standalone module — it talks to Postgres directly (no Kafka needed for the store itself):

```bash
cd exercise-03 && go mod init eventstore && go mod tidy
go run exercise-03-event-store.go -dsn "postgres://postgres:postgres@localhost:5432/shop"
```

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c22-week-14` to compare.
