# Exercise 1 — Debezium on the `orders` Table

**Goal:** Deploy a Debezium Postgres connector that captures every change to the `orders` table into a Kafka topic, then read and decode the change events well enough to build consumers against them. You will train the diagnostic habit of the week: reading a change event's `op`, `before`, `after`, and LSN and knowing exactly what happened to the row — and you'll see firsthand how `REPLICA IDENTITY` controls the `before` image.

**Estimated time:** 55 minutes. Guided.

---

## Setup

You need Postgres 16 with `wal_level = logical`, a Kafka broker, and Kafka Connect with the Debezium Postgres connector. The compose below stands up all three. Save as `compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: shop
    command: ["postgres", "-c", "wal_level=logical", "-c", "max_replication_slots=10", "-c", "max_wal_senders=10"]
    ports: ["5432:5432"]

  kafka:
    image: apache/kafka:3.7.0      # KRaft mode, no ZooKeeper
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:9093
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT,CONTROLLER:PLAINTEXT
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS: 0
    ports: ["9092:9092"]

  connect:
    image: debezium/connect:2.7
    depends_on: [kafka, postgres]
    environment:
      BOOTSTRAP_SERVERS: kafka:9092
      GROUP_ID: connect-cluster
      CONFIG_STORAGE_TOPIC: connect_configs
      OFFSET_STORAGE_TOPIC: connect_offsets
      STATUS_STORAGE_TOPIC: connect_statuses
    ports: ["8083:8083"]
```

```bash
docker compose up -d
# Wait for Connect to come up:
until curl -sf localhost:8083/ >/dev/null; do echo "waiting for connect..."; sleep 2; done
```

---

## Step 1 — Prepare Postgres

Create the table (if you don't already have it from Week 13), a Debezium role, and grant what the snapshot needs.

```bash
docker compose exec postgres psql -U postgres -d shop -c "
CREATE TABLE IF NOT EXISTS orders (
    order_id    bigserial PRIMARY KEY,
    customer_id bigint NOT NULL,
    status      text NOT NULL DEFAULT 'PLACED',
    total_cents bigint NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE ROLE debezium WITH REPLICATION LOGIN PASSWORD 'dbz';
GRANT SELECT ON ALL TABLES IN SCHEMA public TO debezium;
GRANT USAGE ON SCHEMA public TO debezium;
ALTER ROLE debezium WITH LOGIN;
"
```

Seed a couple of rows so the initial snapshot has something to emit:

```bash
docker compose exec postgres psql -U postgres -d shop -c "
INSERT INTO orders (customer_id, total_cents) VALUES (42, 1999), (7, 500);"
```

---

## Step 2 — Register the Debezium connector

POST the connector config to Kafka Connect:

```bash
curl -s -X POST localhost:8083/connectors -H "Content-Type: application/json" -d '{
  "name": "orders-connector",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": "postgres",
    "database.port": "5432",
    "database.user": "debezium",
    "database.password": "dbz",
    "database.dbname": "shop",
    "topic.prefix": "shop",
    "plugin.name": "pgoutput",
    "slot.name": "debezium_orders",
    "publication.autocreate.mode": "filtered",
    "table.include.list": "public.orders",
    "snapshot.mode": "initial",
    "tombstones.on.delete": "true"
  }
}' | jq .
```

Confirm it's running — **this is the connection-formed promise for CDC**:

```bash
curl -s localhost:8083/connectors/orders-connector/status | jq '.connector.state, .tasks[].state'
# "RUNNING"
# "RUNNING"
```

If you see `FAILED`, read the trace: `curl -s localhost:8083/connectors/orders-connector/status | jq '.tasks[].trace'`. The usual culprits are `wal_level` not `logical`, the role lacking `REPLICATION`, or no `SELECT` grant for the snapshot. Walk the Lecture 1 §6 tree.

---

## Step 3 — Read the snapshot events

The connector snapshotted the two seeded rows as `op: "r"` (read) events. Consume them from the topic:

```bash
docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server kafka:9092 --topic shop.public.orders \
  --from-beginning --max-messages 2 \
  | jq '.payload | {op, after}'
```

```
{"op":"r","after":{"order_id":1,"customer_id":42,"status":"PLACED","total_cents":1999, ...}}
{"op":"r","after":{"order_id":2,"customer_id":7, "status":"PLACED","total_cents":500,  ...}}
```

`op: "r"` means "this came from the initial snapshot, not a live change." A new consumer uses these to build complete current state before the live changes arrive.

---

## Step 4 — Watch a live INSERT, UPDATE, and DELETE

Leave a consumer tailing the topic in one terminal:

```bash
docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server kafka:9092 --topic shop.public.orders --offset end --partition 0 \
  | jq '.payload | {op, before: .before.status, after: .after.status, lsn: .source.lsn}'
```

In another terminal, make changes:

```bash
docker compose exec postgres psql -U postgres -d shop -c \
  "INSERT INTO orders (customer_id, total_cents) VALUES (99, 12345);"
docker compose exec postgres psql -U postgres -d shop -c \
  "UPDATE orders SET status='SHIPPED' WHERE order_id=1;"
docker compose exec postgres psql -U postgres -d shop -c \
  "DELETE FROM orders WHERE order_id=2;"
```

You should see (in the consumer):

```
{"op":"c","before":null,"after":"PLACED","lsn":...}        # the INSERT
{"op":"u","before":null,"after":"SHIPPED","lsn":...}       # the UPDATE — note before is null!
{"op":"d","before":"PLACED","after":null,"lsn":...}        # the DELETE
(then a tombstone: a message with this key and a null value)
```

Notice the **`before` is `null` on the UPDATE**. That's `REPLICA IDENTITY DEFAULT` — Postgres only logged the primary key, not the old `status`. Fix it next.

---

## Step 5 — Set `REPLICA IDENTITY FULL` and see the prior image

```bash
docker compose exec postgres psql -U postgres -d shop -c \
  "ALTER TABLE orders REPLICA IDENTITY FULL;"
docker compose exec postgres psql -U postgres -d shop -c \
  "UPDATE orders SET status='DELIVERED' WHERE order_id=1;"
```

Now the consumer shows the **full prior image**:

```
{"op":"u","before":"SHIPPED","after":"DELIVERED","lsn":...}    # before is now populated!
```

That before/after pair is what a read model uses to compute a diff and what an audit log needs. You paid for it in WAL volume (the whole old row is now logged on every update) — a deliberate tradeoff (Lecture 1 §4.3).

---

## Step 6 — Confirm the slot and lag

Debezium streams via a logical replication slot — the same Week 13 slots. Confirm it exists and is active (an inactive one fills your disk):

```bash
docker compose exec postgres psql -U postgres -c \
  "SELECT slot_name, active, plugin FROM pg_replication_slots;"
# debezium_orders | t | pgoutput
```

Check CDC lag — the gap between when a change committed and when Debezium emitted it — by comparing `source.ts_ms` to the top-level `ts_ms` on a fresh event. Under no load this is single-digit milliseconds.

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] `curl .../orders-connector/status` shows `connector` and task `state` both `RUNNING`.
- [ ] You read two `op: "r"` snapshot events and can explain what `r` means.
- [ ] A live INSERT shows `op: "c"` with `before: null`; a DELETE shows `op: "d"` with `after: null` followed by a tombstone.
- [ ] With `REPLICA IDENTITY DEFAULT`, an UPDATE's `before` is null; after `REPLICA IDENTITY FULL`, the `before` carries the full prior row — and you can state the WAL-cost tradeoff.
- [ ] `pg_replication_slots` shows the `debezium_orders` slot `active = t`.

---

## Stretch

- Configure the **outbox event router**: create an `outbox` table, add `"transforms": "outbox"` with `io.debezium.transforms.outbox.EventRouter`, write to the outbox in the same transaction as an order change, and confirm clean domain events on a per-event-type topic. Compare to raw table CDC.
- Kill the `connect` container mid-stream, make several changes to `orders`, then restart Connect. Confirm Debezium **resumes from the slot** and you lose no events — the slot is what makes CDC durable across connector restarts.
- Add `order_items` to `table.include.list` and observe that Debezium produces to a **second topic** (`shop.public.order_items`) — topic-per-table. Reason about how a consumer joins the two streams (it doesn't, easily — that's why the read model denormalizes).

---

When this feels comfortable, move to [Exercise 2 — The read-model projector](./exercise-02-read-model-projector.py).
