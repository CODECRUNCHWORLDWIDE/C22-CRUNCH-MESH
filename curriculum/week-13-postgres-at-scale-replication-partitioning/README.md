# Week 13 — Postgres at Scale: Replication and Partitioning

Welcome to Phase 3, where the services you spent twelve weeks decomposing finally have to *store* something, and the storage tier becomes the thing that wakes you up at 3 a.m. By Friday you will be able to look at a single Postgres instance under load and state, with evidence, whether it should be replicated, whether it should be partitioned, whether its connection pool is configured for the workload, and — the hardest call — whether it should be sharded across nodes at all or left exactly where it is.

We assume you finished Phase 2 and have the `order-service` writing `order.placed.v1` to Kafka. We also assume you have a Postgres instance somewhere — a container, a Kind pod, RDS, it doesn't matter — that you can connect to with `psql` and that you have superuser on. If you don't, fix that first: every exercise this week runs against a Postgres 16 you control.

The one thing to internalize before you read another line: **"just add a read replica" and "just shard it" are the two most expensive sentences a backend engineer can say without evidence, and most teams say both about a year too early.** A single Postgres instance on modern hardware will comfortably serve tens of thousands of transactions per second and hold tables in the billions of rows if — and it is a real *if* — you have partitioned the hot tables, killed the bloat, pooled the connections, and stopped doing `SELECT *` across an unindexed predicate. The instinct from the distributed-systems half of this course is to reach for horizontal scale. Phase 3 deliberately resists that instinct. You shard when you have *measured* a wall, not when you have *imagined* one. This week is where you learn to measure the wall.

This is where you stop guessing about your storage tier.

## Learning objectives

By the end of this week, you will be able to:

- **Distinguish** physical (streaming) replication from logical replication — what each ships on the wire, what each can and cannot do, and which one you reach for to build a read replica versus a cross-version upgrade versus a CDC feed.
- **Stand up** a Postgres primary with a streaming physical replica and a logical replica, promote a replica to primary, and measure replication lag with `pg_stat_replication` and `pg_replication_slots`.
- **Choose** a partitioning strategy — declarative `RANGE`, `LIST`, or `HASH` — for a given table given its access pattern, and write the DDL that creates the partitioned parent and attaches partitions without locking the table out of service.
- **Explain** HOT (heap-only tuple) updates, why MVCC produces bloat, and how `autovacuum`, `pg_stat_user_tables`, and `pgstattuple` let you see and control it.
- **Read** `pg_stat_statements` like a backend engineer reads an HTTP access log — finding the query that costs you the most total time, not just the slowest single call.
- **Tune** pgBouncer in transaction-pooling versus session-pooling mode, state which one a given workload requires, and explain the prepared-statement and `SET`-leakage footguns that transaction pooling introduces.
- **Reason** about when Postgres genuinely runs out of vertical and partition-level headroom, and compare Citus (distributed Postgres) and CockroachDB (Postgres-wire-compatible NewSQL) as the horizontal escape hatches — with their costs stated honestly.
- **Build** a benchmark harness that loads 50 million synthetic `orders` rows, measures query latency before and after partitioning, and produces a defensible before/after report.

## Prerequisites

This week assumes you have completed **C22 weeks 1–12**, or have equivalent distributed-systems and backend fluency. Specifically:

- **Postgres 16** running somewhere you have superuser access — Docker (`postgres:16`), a Kind StatefulSet, or a managed instance you can reconfigure. `psql --version` reports 16.x; you can `CREATE ROLE` and edit `postgresql.conf` / `pg_hba.conf`.
- You can write non-trivial SQL from memory: joins, `GROUP BY`, window functions, CTEs, and an `EXPLAIN (ANALYZE, BUFFERS)` you can actually read.
- You understand **MVCC at the conceptual level** from any prior database course — that a row update writes a new tuple and marks the old one dead, and that *something* has to clean the dead tuples up.
- You are comfortable in a Linux shell, with `docker` or `kubectl`, and can edit a config file, restart a service, and tail a log.
- The **`order-service`** from Phase 2 exists and emits `order.placed.v1`. This week's `orders` table is the same domain; next week's Debezium feed reads its WAL.

You do **not** need prior replication or partitioning experience. We start at the WAL and build up. If you have used a read replica only as a checkbox in a cloud console without knowing what streams across the wire, this is the week that knowledge becomes load-bearing.

## Topics covered

- **The WAL as the spine of everything.** The write-ahead log, `wal_level` (`replica` vs `logical`), checkpoints, and why every replication feature in Postgres — physical replicas, logical replicas, CDC, point-in-time recovery — is a different consumer of the *same* log.
- **Physical (streaming) replication.** `primary_conninfo`, `pg_basebackup`, replication slots, hot standby, synchronous vs asynchronous commit (`synchronous_commit`, `synchronous_standby_names`), cascading replicas, and the failover-and-promotion path (`pg_promote()`).
- **Logical replication.** `PUBLICATION` / `SUBSCRIPTION`, the logical decoding plugin (`pgoutput`), row vs column filters, what logical replication *cannot* do (DDL, sequences, large objects out of the box), and why it is the foundation for both selective replicas and next week's Debezium CDC.
- **Declarative partitioning.** `PARTITION BY RANGE / LIST / HASH`, creating partitions, `ATTACH` / `DETACH PARTITION`, partition pruning at plan time and execution time, partition-wise joins and aggregates, default partitions, and the `pg_partman` automation pattern for rolling time-series partitions.
- **MVCC, HOT, and bloat.** Heap-only-tuple updates and when they apply, dead tuples, the `autovacuum` machinery and its tunables, `VACUUM` vs `VACUUM FULL` vs `pg_repack`, transaction-ID wraparound, and reading bloat with `pg_stat_user_tables` and `pgstattuple`.
- **Query observability.** `pg_stat_statements` (total time vs mean time vs calls), `auto_explain`, `EXPLAIN (ANALYZE, BUFFERS)`, and the discipline of optimizing the query that costs the most *aggregate* time rather than the one that feels slowest.
- **Connection pooling.** pgBouncer in `session`, `transaction`, and `statement` modes; the C10k-of-connections problem and why Postgres processes are not cheap; the transaction-mode footguns (server-side prepared statements, session `SET`s, advisory locks, `LISTEN/NOTIFY`); and where PgCat and the built-in connection-pooling roadmap fit in 2026.
- **The horizontal escape hatches.** Citus (sharding Postgres by distribution column, reference vs distributed tables, the coordinator), CockroachDB (Raft-replicated ranges, `SERIALIZABLE` by default, Postgres wire compatibility but *not* Postgres internals), and the honest decision: when "vertical + partitioning + pooling" has actually run out and sharding is the lesser evil.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                  | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|--------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | WAL, physical streaming replication, slots, failover   |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Logical replication; partitioning strategy & DDL       |    1h    |    2.5h   |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | MVCC, HOT, bloat, autovacuum; `pg_stat_statements`     |    2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | pgBouncer pooling modes; Citus & CockroachDB           |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Friday    | The 50M-row benchmark; before/after partitioning report|    0h    |    0h     |     1h     |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work                                 |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, review, report polish                            |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                        | **6h**   | **7h**    | **4h**     | **3.5h**  | **5h**   | **12h**      | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | The Postgres docs, replication and partitioning chapters, pgBouncer and Citus docs, and the talks worth your time |
| [lecture-notes/01-replication-physical-and-logical.md](./lecture-notes/01-replication-physical-and-logical.md) | The WAL, streaming physical replication, slots, failover, and logical replication |
| [lecture-notes/02-partitioning-bloat-pooling-and-sharding.md](./lecture-notes/02-partitioning-bloat-pooling-and-sharding.md) | Declarative partitioning, MVCC/HOT/bloat, `pg_stat_statements`, pgBouncer, and the Citus/Cockroach decision |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-streaming-replica.md](./exercises/exercise-01-streaming-replica.md) | Build a primary + streaming physical replica, measure lag, and promote the replica |
| [exercises/exercise-02-partition-orders.sql](./exercises/exercise-02-partition-orders.sql) | Convert a flat `orders` table to monthly `RANGE` partitions online, with pruning proof |
| [exercises/exercise-03-bloat-and-statements.py](./exercises/exercise-03-bloat-and-statements.py) | Generate bloat, watch autovacuum, and rank queries by total time via `pg_stat_statements` |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-diagnose-a-slow-storage-tier.md](./challenges/challenge-01-diagnose-a-slow-storage-tier.md) | Diagnose three planted storage-tier faults on a live instance and prescribe the fix |
| [quiz.md](./quiz.md) | 13 questions with a hidden answer key |
| [homework.md](./homework.md) | Six problems including the headline replication-and-partitioning decision memo |
| [mini-project/README.md](./mini-project/README.md) | The `orders-at-scale` benchmark harness: 50M rows, before/after partitioning, defensible report |

## The "lag is bounded and pruning fires" promise

C22 uses a recurring marker for every exercise that ends in the storage tier behaving. For replication it is bounded, observable lag:

```
$ psql -h primary -c "SELECT application_name, state, \
    pg_wal_lsn_diff(sent_lsn, replay_lsn) AS replay_bytes FROM pg_stat_replication;"
 application_name |   state   | replay_bytes
------------------+-----------+--------------
 replica1         | streaming |         8192
```

For partitioning it is the planner *pruning* partitions it doesn't need:

```
$ EXPLAIN SELECT * FROM orders WHERE created_at >= '2026-03-01' AND created_at < '2026-04-01';
 Append  (cost=...)
   ->  Seq Scan on orders_2026_03 orders_1   (one partition, not twelve)
```

If `replay_bytes` is climbing without bound, or your `EXPLAIN` scans every partition when the predicate names one month, you are not done. A replica that exists but lags forever is the canonical silent storage failure; a partitioned table the planner can't prune is partitioning that bought you nothing. The point of Week 13 is to make both of those lines ordinary — and to make the bad case *loud*.

## Stretch goals

If you finish the regular work early and want to push further:

- Stand up **synchronous replication** with `synchronous_standby_names = 'ANY 1 (replica1, replica2)'` and measure the commit-latency tax versus async. Note exactly where the latency shows up and why a single synchronous standby is a single point of *write* failure.
- Configure **`pg_partman`** to auto-create next month's `orders` partition and auto-detach partitions older than 12 months. Confirm the background worker runs and the partition set rolls forward without a human.
- Run **`pgbench`** at increasing client counts directly against Postgres and then through pgBouncer in transaction mode. Find the connection count where direct-to-Postgres throughput collapses and pooled throughput holds. That collapse point is the number you quote when someone asks "why pgBouncer."
- Read the **Citus "distributed tables" docs** and convert your partitioned `orders` table into a Citus distributed table sharded by `customer_id`. Run the same benchmark and compare. Document one query that got faster and one that got *slower* (cross-shard joins are not free).

## Up next

Week 14 takes the logical-replication and WAL literacy you built here and turns it into a **change-data-capture pipeline**: Debezium reading the very same `orders` WAL you set up this week, fanning changes into a CQRS read model and an event store. The `orders` table you partition this week is the table Debezium streams next week. Push your mini-project before you start it.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
