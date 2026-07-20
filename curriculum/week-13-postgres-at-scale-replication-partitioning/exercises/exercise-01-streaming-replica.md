# Exercise 1 — Build a Streaming Replica and Measure Lag

**Goal:** Bring up a Postgres 16 primary and a physical streaming replica, connect them with a replication slot, *prove* the replication lag is bounded under write load by reading `pg_stat_replication`, and then promote the replica to a standalone primary. You will train the single most important diagnostic habit for replication: reading the two LSNs and knowing whether the distance between them is healthy.

**Estimated time:** 50 minutes. Guided.

---

## Setup

You need two Postgres 16 data directories that can reach each other. The cleanest local setup is two containers on one Docker network. Save this as `compose.yml`:

```yaml
services:
  primary:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: shop
    command:
      - "postgres"
      - "-c"
      - "wal_level=logical"
      - "-c"
      - "max_wal_senders=10"
      - "-c"
      - "max_replication_slots=10"
      - "-c"
      - "max_slot_wal_keep_size=2GB"
    ports: ["5432:5432"]
    networks: [pg]

  # The replica container starts empty; we clone the primary into it by hand below.
  replica:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: postgres
    entrypoint: ["sleep", "infinity"]      # we control startup manually
    ports: ["5433:5432"]
    networks: [pg]

networks:
  pg: {}
```

```bash
docker compose up -d
```

---

## Step 1 — Prepare the primary

Create the replication role and allow the replication connection.

```bash
docker compose exec primary psql -U postgres -d shop -c \
  "CREATE ROLE replicator WITH REPLICATION LOGIN PASSWORD 'replicator';"
```

Append an `hba` rule so the replica's subnet may make a `replication` connection, then reload:

```bash
docker compose exec primary bash -c \
  "echo 'host replication replicator all scram-sha-256' >> \$PGDATA/pg_hba.conf"
docker compose exec primary psql -U postgres -c "SELECT pg_reload_conf();"
```

Create the `orders` table you'll write to:

```bash
docker compose exec primary psql -U postgres -d shop -c "
CREATE TABLE orders (
    order_id    bigserial PRIMARY KEY,
    customer_id bigint NOT NULL,
    total_cents bigint NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);"
```

---

## Step 2 — Clone the primary into the replica with `pg_basebackup`

Wipe the empty replica data directory and stream a base backup from the primary, creating a replication slot in the same step:

```bash
docker compose exec replica bash -c '
  rm -rf "$PGDATA"/* &&
  PGPASSWORD=replicator pg_basebackup \
    --host=primary --port=5432 --username=replicator \
    --pgdata="$PGDATA" \
    --wal-method=stream --create-slot --slot=replica1 \
    --write-recovery-conf --progress &&
  chmod 700 "$PGDATA"
'
```

The `--write-recovery-conf` flag wrote `primary_conninfo` and `primary_slot_name` into `postgresql.auto.conf`, and created a `standby.signal` file. Confirm:

```bash
docker compose exec replica bash -c 'cat "$PGDATA"/postgresql.auto.conf; ls "$PGDATA"/standby.signal'
```

You should see a `primary_conninfo = '...application_name=...'` line and the `standby.signal` file. That file is what tells Postgres "boot as a read-only standby and replay forever."

---

## Step 3 — Start the replica and confirm it streams

Start Postgres inside the replica container as the `postgres` user:

```bash
docker compose exec -u postgres replica bash -c 'pg_ctl -D "$PGDATA" -l /tmp/pg.log start'
sleep 2
docker compose exec -u postgres replica tail -5 /tmp/pg.log
```

You want to see `started streaming WAL from primary` and `database system is ready to accept read-only connections` in the log. Now confirm from the **primary** that the standby is connected:

```bash
docker compose exec primary psql -U postgres -x -c "SELECT * FROM pg_stat_replication;"
```

A row with `state = streaming` and `application_name = ...replica1` means the connection formed. **This is the connection-formed promise for replication.** If you get zero rows, the standby isn't connected — walk the Lecture 1 §5 tree (check the log, `primary_conninfo`, the `hba` rule, the role).

---

## Step 4 — Prove the replica is a live read-only copy

Insert on the primary; read on the replica.

```bash
docker compose exec primary psql -U postgres -d shop -c \
  "INSERT INTO orders (customer_id, total_cents) VALUES (42, 1999) RETURNING order_id;"

# Within milliseconds, on the replica:
docker compose exec replica psql -U postgres -d shop -c \
  "SELECT order_id, customer_id, total_cents FROM orders WHERE customer_id = 42;"
```

The row is there. Now prove the replica is **read-only** — writes must be rejected:

```bash
docker compose exec replica psql -U postgres -d shop -c \
  "INSERT INTO orders (customer_id, total_cents) VALUES (1, 1);"
# ERROR:  cannot execute INSERT in a read-only transaction
```

That error is correct and expected: a hot standby serves reads, never writes.

---

## Step 5 — Measure lag under load and prove it's bounded

Generate write load on the primary and watch the lag rise and fall but stay bounded. In one terminal, start a write loop:

```bash
docker compose exec primary psql -U postgres -d shop -c "
INSERT INTO orders (customer_id, total_cents)
SELECT (random()*1000)::bigint, (random()*10000)::bigint
FROM generate_series(1, 2000000);"
```

In another terminal, watch the lag on the primary:

```bash
docker compose exec primary psql -U postgres -c "
SELECT application_name, state,
       pg_wal_lsn_diff(sent_lsn, replay_lsn) AS replay_bytes
FROM pg_stat_replication;" 
# Re-run a few times during the insert (or use \watch 1 inside an interactive psql).
```

You'll see `replay_bytes` climb during the burst (the replica is a little behind) and fall back toward a small number when the burst ends. **Bounded, oscillating, returning toward zero = healthy.** A number that only ever climbs = the replica can't keep up. Read it on the standby side too, in seconds:

```bash
docker compose exec replica psql -U postgres -d shop -c \
  "SELECT now() - pg_last_xact_replay_timestamp() AS replication_delay;"
```

---

## Step 6 — Promote the replica

Simulate a failover: promote the standby to a full primary.

```bash
docker compose exec replica psql -U postgres -d shop -c "SELECT pg_promote();"
# returns: t
```

After promotion the former replica accepts writes. Confirm:

```bash
docker compose exec replica psql -U postgres -d shop -c \
  "INSERT INTO orders (customer_id, total_cents) VALUES (999, 500) RETURNING order_id;"
# Now succeeds — it's a primary.
```

It is no longer in recovery:

```bash
docker compose exec replica psql -U postgres -c "SELECT pg_is_in_recovery();"
# f
```

> A real failover does more: it fences the old primary (so you don't get split-brain with two writable nodes), repoints other standbys, and redirects app traffic. Patroni automates all of it. `pg_promote()` is the one piece you just did by hand so you know what Patroni is doing for you.

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] `pg_stat_replication` on the primary shows one row with `state = streaming` for `replica1`.
- [ ] A row inserted on the primary is readable on the replica within seconds, and a write **attempt** on the replica is rejected with `cannot execute INSERT in a read-only transaction`.
- [ ] Under a 2M-row insert burst, `replay_bytes` rises and then returns toward a small number — you can state in one sentence why a *monotonically climbing* number would mean the replica can't keep up.
- [ ] `SELECT pg_promote();` returns `t`, after which the former replica accepts writes and `pg_is_in_recovery()` returns `f`.

---

## Stretch

- Turn on **synchronous replication**: set `synchronous_standby_names = 'ANY 1 (replica1)'` on the primary, reload, and time an insert before and after. The added milliseconds are the durability tax. Then stop the replica and watch a commit **block** — now you understand why `ANY N` of several standbys (not one) is the production form.
- Kill the replica container *without* removing the slot, generate WAL on the primary, and watch `pg_replication_slots` show the slot `active = f` while `pg_wal` grows. This is the disk-fill timer from Lecture 1 §2.2. Then confirm `max_slot_wal_keep_size` caps it.
- Set up a **cascading replica**: a second standby that streams from `replica1` instead of the primary. Confirm changes flow primary → replica1 → replica2.

---

When this feels comfortable, move to [Exercise 2 — Partition the `orders` table online](exercise-02-partition-orders.sql).
