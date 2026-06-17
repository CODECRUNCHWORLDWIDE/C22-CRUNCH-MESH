# Week 13 — Resources

Every resource here is **free** and pinned to **Postgres 16** (the major version we run) wherever the docs are versioned. The Postgres documentation is the gold standard in open-source docs — read it, do not skim a blog summary of it. pgBouncer, Citus, and CockroachDB all publish full docs openly. No paywalled books are linked.

When a link is versioned, the Postgres 16 URL is given. If you are on 17 later, swap `16` for `17` in the path — the replication and partitioning concepts are stable across these versions; only a few config defaults and a handful of features (logical replication of sequences, parallel `pg_basebackup`) move forward.

## Required reading (work it into your week)

- **High Availability, Load Balancing, and Replication** — the canonical Postgres replication chapter. Read it Monday, then again Friday:
  <https://www.postgresql.org/docs/16/high-availability.html>
- **Log-Shipping Standby Servers & Streaming Replication** — `primary_conninfo`, hot standby, replication slots:
  <https://www.postgresql.org/docs/16/warm-standby.html>
- **Logical Replication** — `PUBLICATION`, `SUBSCRIPTION`, restrictions, conflict handling:
  <https://www.postgresql.org/docs/16/logical-replication.html>
- **Table Partitioning** — declarative `RANGE`/`LIST`/`HASH`, pruning, partition-wise joins:
  <https://www.postgresql.org/docs/16/ddl-partitioning.html>
- **Routine Vacuuming** — MVCC, dead tuples, autovacuum, wraparound:
  <https://www.postgresql.org/docs/16/routine-vacuuming.html>
- **pg_stat_statements** — the query-cost extension you will live in:
  <https://www.postgresql.org/docs/16/pgstatstatements.html>

## The deep references (skim now, return when you need them)

You will not read these cover to cover this week. But when a colleague says "that's a WAL-sender-timeout thing" or "the planner pruned at execution time, not plan time," you want to know where to look.

- **Write-Ahead Logging (WAL)** — the chapter that explains the spine everything else consumes:
  <https://www.postgresql.org/docs/16/wal-intro.html>
- **WAL configuration & `wal_level`** — `replica` vs `logical`, and the cost of each:
  <https://www.postgresql.org/docs/16/runtime-config-wal.html>
- **Replication configuration** — every `synchronous_*`, `primary_conninfo`, `max_wal_senders` knob:
  <https://www.postgresql.org/docs/16/runtime-config-replication.html>
- **HOT (heap-only tuples)** — the source-tree README, the clearest explanation that exists:
  <https://github.com/postgres/postgres/blob/REL_16_STABLE/src/backend/access/heap/README.HOT>
- **Partition pruning** — plan-time vs execution-time, and how to read it in `EXPLAIN`:
  <https://www.postgresql.org/docs/16/ddl-partitioning.html#DDL-PARTITION-PRUNING>

## API & config references (the ones you'll have open all week)

- **`pg_stat_replication`** — the primary-side view of every connected standby and its lag:
  <https://www.postgresql.org/docs/16/monitoring-stats.html#MONITORING-PG-STAT-REPLICATION-VIEW>
- **`pg_replication_slots`** — slots, their `restart_lsn`, and the WAL-retention danger they create:
  <https://www.postgresql.org/docs/16/view-pg-replication-slots.html>
- **`pg_stat_user_tables`** — `n_dead_tup`, `n_live_tup`, last-autovacuum — your bloat dashboard:
  <https://www.postgresql.org/docs/16/monitoring-stats.html#MONITORING-PG-STAT-ALL-TABLES-VIEW>
- **`pg_basebackup`** — how you clone a primary to seed a standby:
  <https://www.postgresql.org/docs/16/app-pgbasebackup.html>
- **`EXPLAIN`** — every option, including `BUFFERS` and `SETTINGS`:
  <https://www.postgresql.org/docs/16/sql-explain.html>

## Pooling, automation, and the horizontal options

- **pgBouncer documentation** — pooling modes, `max_client_conn`, `default_pool_size`, the config file:
  <https://www.pgbouncer.org/config.html>
- **pgBouncer features** — exactly what breaks in transaction mode (prepared statements, `SET`, advisory locks):
  <https://www.pgbouncer.org/features.html>
- **PgCat** — the Rust pooler with sharding and load balancing, the 2026 challenger to pgBouncer:
  <https://github.com/postgresml/pgcat>
- **pg_partman** — automated time-series partition management (create-ahead, retention):
  <https://github.com/pgpartman/pg_partman>
- **Citus documentation** — distributed tables, reference tables, the coordinator, colocation:
  <https://docs.citusdata.com/en/stable/>
- **CockroachDB architecture** — Raft ranges, `SERIALIZABLE`, what "Postgres-compatible" does and does not mean:
  <https://www.cockroachlabs.com/docs/stable/architecture/overview>

## Benchmarking & introspection tools

- **`pgbench`** — ships with Postgres; the standard TPC-B-like load generator:
  <https://www.postgresql.org/docs/16/pgbench.html>
- **`pgstattuple`** — measures real bloat (live vs dead vs free space) on a table or index:
  <https://www.postgresql.org/docs/16/pgstattuple.html>
- **`pg_repack`** — rebuilds a bloated table/index online, without the `ACCESS EXCLUSIVE` lock `VACUUM FULL` takes:
  <https://github.com/reorg/pg_repack>
- **`auto_explain`** — logs the plan of slow queries automatically, so you catch the bad plan in prod:
  <https://www.postgresql.org/docs/16/auto-explain.html>

## Talks and long-form worth your time (free, no signup)

- **PGConf / PGCon talk archives** — the replication, partitioning, and vacuum deep-dives are posted free; search the archive:
  <https://www.pgcon.org/>
- **"Postgres at scale" / partitioning sessions** — the community conference talks on partitioning hot tables are the most-rewatched in the operations track:
  <https://www.youtube.com/@PostgresOpen>
- **Citus Data engineering blog** — honest write-ups of where single-node Postgres ends and sharding begins:
  <https://www.citusdata.com/blog/>

## Tools you'll use this week

- **`psql`** — your primary interface. Learn `\d+`, `\watch`, `\timing on`, and `\x`.
- **`pg_basebackup`** — clone a primary to bootstrap a standby.
- **`pgbench -i -s 500`** — initialize a scale-500 dataset (~50M rows in the main table) for the benchmark.
- **`EXPLAIN (ANALYZE, BUFFERS)`** — the only honest way to see what a query actually did.
- **`pg_stat_statements`** — `CREATE EXTENSION pg_stat_statements;` then query it by `total_exec_time DESC`.
- **`pgbouncer`** — `apt install pgbouncer`; one `pgbouncer.ini` and one `userlist.txt`.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **WAL** | Write-Ahead Log — the ordered record of every change, written before the data files. Everything replicates by shipping it. |
| **LSN** | Log Sequence Number — a position in the WAL. Lag is the byte distance between two LSNs. |
| **Streaming / physical replication** | The standby replays the primary's raw WAL block-for-block. Byte-identical copy; same major version. |
| **Logical replication** | The primary *decodes* the WAL into row-level changes and ships those. Selective, cross-version, the basis of CDC. |
| **Replication slot** | A primary-side bookmark that guarantees WAL is retained until a consumer has it. Also the way to run out of disk. |
| **Hot standby** | A streaming replica that also serves read-only queries while replaying. |
| **Synchronous commit** | The primary waits for a standby to confirm WAL before acknowledging the commit. Durability up, write latency up. |
| **Declarative partitioning** | Splitting one logical table into physical partitions by `RANGE`/`LIST`/`HASH`, transparently to queries. |
| **Partition pruning** | The planner (or executor) skipping partitions that can't match the query predicate. |
| **MVCC** | Multi-Version Concurrency Control — updates write a new tuple and mark the old dead; readers never block writers. |
| **HOT update** | Heap-Only Tuple update — an update that doesn't touch indexed columns, so it avoids new index entries. |
| **Bloat** | Dead tuples and free space that `VACUUM` hasn't reclaimed; the table is bigger on disk than its live data. |
| **autovacuum** | The background process that reclaims dead tuples and updates planner statistics. |
| **Connection pooling** | A proxy (pgBouncer) that multiplexes many client connections onto few Postgres backends. |
| **Transaction-mode pooling** | A server connection is assigned per *transaction*, not per *session* — maximum reuse, with prepared-statement caveats. |

---

*If a link 404s, please open an issue so we can replace it.*
