# Week 13 — Exercises

Three focused drills on a running Postgres 16 instance. Each takes 40–60 minutes. Do them in order — exercise 3 reuses the bloat and statistics intuitions you build while doing 1 and 2. Run everything against a Postgres 16 you control (a `postgres:16` container is the simplest; a Kind StatefulSet or RDS works too).

## Index

1. **[Exercise 1 — Build a streaming replica and measure lag](./exercise-01-streaming-replica.md)** — bring up a primary and a physical streaming replica with `pg_basebackup` and a replication slot, prove the lag is bounded under load, then promote the replica. (~50 min, guided)
2. **[Exercise 2 — Partition the `orders` table online](./exercise-02-partition-orders.sql)** — convert a flat `orders` table to monthly `RANGE` partitions without taking it offline, and prove the planner prunes. (~45 min, runnable SQL)
3. **[Exercise 3 — Bloat and the statements that cost you](./exercise-03-bloat-and-statements.py)** — generate bloat with an update storm, watch autovacuum clean it, and rank queries by total time in `pg_stat_statements`. (~45 min, runnable Python)

## How to work the exercises

- Have a Postgres 16 you can `psql` into with superuser before you start. For the replica exercise you need **two** Postgres data directories (two containers is easiest).
- Set `\timing on` in every `psql` session. Half of all "is this slow?" questions are answered by reading the timing you already have.
- **Read `EXPLAIN (ANALYZE, BUFFERS)` before and after every change.** The plan is your ground truth. Train the habit of diffing the before/after plan by eye.
- When a replica or a query "isn't working," walk the relevant decision tree (Lecture 1 §5 for replication, Lecture 2 §5 for storage) before you touch config. Connection first, slot second, lag third.
- Each runnable exercise ends with an **expected output** block. If your output doesn't match the *shape* (exact numbers vary by hardware), you're not done.

## Running the SQL and Python exercises

The SQL file runs straight in `psql`:

```bash
psql -h localhost -U postgres -d shop -f exercise-02-partition-orders.sql
```

The Python file needs `psycopg` (the modern Postgres driver, v3):

```bash
python3 -m pip install "psycopg[binary]>=3.1"
python3 exercise-03-bloat-and-statements.py --dsn "host=localhost user=postgres dbname=shop"
```

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c22-week-13` to compare.
