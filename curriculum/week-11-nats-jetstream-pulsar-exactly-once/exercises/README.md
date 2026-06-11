# Week 11 — Exercises

Three focused drills on real brokers and a real Postgres. Each takes 45–75 minutes. Do them in order — exercise 3 consumes what exercise 2's outbox relay produces, and both build on the broker you stand up in exercise 1. Run everything against local Docker containers (NATS, Pulsar, Kafka/Redpanda from Week 10, and Postgres) — each exercise gives the `docker run` / `docker compose` invocation.

## Index

1. **[Exercise 1 — JetStream and Pulsar up close](exercise-01-jetstream-and-pulsar.md)** — stand up NATS JetStream and Pulsar in Docker, create durable streams/topics, observe the JetStream **dedup window** dropping a repeated `Nats-Msg-Id`, and watch Pulsar's **key-shared vs shared** subscription modes change ordering and parallelism. (~75 min, guided)
2. **[Exercise 2 — The transactional outbox relay](exercise-02-outbox-relay.go)** — a Go program that writes a business row + an `outbox` row in **one Postgres transaction**, then a relay that reads the outbox with `FOR UPDATE SKIP LOCKED` and publishes to the broker, marking rows sent. Prove the event can never disagree with the committed state. (~60 min, runnable)
3. **[Exercise 3 — The idempotent consumer + chaos test](exercise-03-idempotent-consumer.py)** — a Python consumer with a **dedup table** that records each processed `event_id` in the same transaction as its effect. Kill it mid-batch, restart, and verify **zero double-charges** under at-least-once redelivery. (~60 min, runnable)

## How to work the exercises

- Have **Postgres** and your **broker** running before you start exercise 2 or 3. Each exercise's header has the exact `docker` command and the schema.
- **Inspect the tables before and after every change.** `psql -c "SELECT * FROM outbox"` and `SELECT * FROM processed_events` are your ground truth, exactly as the lag table was in Week 10. Train the habit of reading the tables, not guessing.
- When something "double-charges," run the Lecture 2 reasoning before you touch code: is the dedup insert in the *same transaction* as the effect? Is the idempotency key *stable* across retries? Those two questions catch 90% of idempotency bugs.
- Each runnable exercise (`.go`, `.py`) ends with an **expected output** block. If your output doesn't match — especially if `double-charges` is anything but `0` — you're not done.

## Running the Go outbox relay

The relay uses `pgx/v5` (Postgres) and `confluent-kafka-go/v2` (broker). From a fresh module directory:

```bash
go mod init outbox-relay
go get github.com/jackc/pgx/v5
go get github.com/confluentinc/confluent-kafka-go/v2/kafka
go run exercise-02-outbox-relay.go -dsn "postgres://crunch:crunch@localhost:5432/crunch" -bootstrap localhost:9092
```

## Running the Python idempotent consumer

The consumer uses `psycopg` (Postgres) and `confluent-kafka` (broker):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install "psycopg[binary]" confluent-kafka
python3 exercise-03-idempotent-consumer.py --dsn "postgres://crunch:crunch@localhost:5432/crunch" \
    --bootstrap localhost:9092 --group order-fulfillment
```

To run the chaos test: start the consumer, let it process a few hundred events, `kill -9` it, restart it, and compare `unique orders charged` against `double-charges` (must be `0`).

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c22-week-11` to compare.
