# Week 15 — The Modern Lakehouse: Iceberg, Trino, and OLAP

Welcome to the week where the change stream you've been building for two weeks finally meets the question it was always headed toward: *where do analytical queries belong?* By Friday you will be able to look at a query — a daily revenue rollup, a year-over-year cohort analysis, an ad-hoc "how many orders shipped late last quarter" — and state, with reasons, whether it should run against your Postgres OLTP database or be pushed down to a lakehouse, and you'll be able to stand up that lakehouse — object storage, an Apache Iceberg table, a Trino query engine, a catalog — from scratch and query the very `orders` events you've been streaming since Week 13.

We assume you finished Week 14 and have the CDC pipeline: Debezium streaming `orders` changes to Kafka, with consumers that fan those changes into a read model and an event store. We also assume you have Docker (or Kind) and enough disk for an object store and a query engine. If your Week 14 pipeline is broken, the exercises provide a standalone event generator so you can still build the lakehouse — but the whole point is to land *your* change stream in Iceberg.

The one thing to internalize before you read another line: **the lakehouse is a contract, not a product, and the contract is a table format you can read with any engine — not a vendor you're married to.** For a decade the industry's answer to "where do analytics go?" was a proprietary data warehouse: you copied data into it, queried it in its dialect, and paid its bill. The lakehouse inverts that. Your data sits in open columnar files (Parquet) on commodity object storage (S3/MinIO), described by an open table format (Apache Iceberg) whose specification — not any one engine — defines what a table *is*: its schema, its snapshots, its partitions, its file manifests. Trino queries it today; Spark queries it tomorrow; DuckDB queries it on your laptop; a future engine queries it in five years. You own the data and the format; the engine is swappable. That decoupling is the whole week, and it is why "Iceberg's spec over Delta's marketing" is the lecture title.

This is where you stop copying analytics into a vendor and start querying them in place.

## Learning objectives

By the end of this week, you will be able to:

- **Distinguish** row-store from column-store at the storage level, and explain why OLTP wants rows and OLAP wants columns — with the I/O math that makes it concrete.
- **Draw** the OLTP/OLAP boundary: which queries belong in Postgres (point reads, transactional writes, low-latency single-row) and which belong in the lakehouse (large scans, aggregations, historical analytics) — and justify a given query's placement.
- **Explain** the Apache Iceberg table format: the metadata hierarchy (catalog → table metadata → manifest list → manifests → data files), snapshots, hidden partitioning, schema evolution, and how Iceberg gives you ACID and time-travel over object-store files.
- **Stand up** a working lakehouse: MinIO as S3-compatible storage, an Iceberg catalog (REST catalog or Nessie), and Trino as the query engine — and create, write, and query an Iceberg table end to end.
- **Write** analytical SQL in Trino against Iceberg: aggregations, window functions, time-travel (`FOR VERSION AS OF` / `FOR TIMESTAMP AS OF`), and federated queries that join Iceberg data to Postgres in a single statement.
- **Use** Trino as a federated engine: query Postgres, Iceberg, and Kafka through one engine, and reason about when federation is the right tool versus when you should land the data first.
- **Reason** about dbt's role — transformations as version-controlled, tested SQL models that build derived tables in the lakehouse — and build a daily-revenue rollup model that turns raw `orders` events into a clean analytics table.

## Prerequisites

This week assumes you have completed **C22 weeks 1–14**, or have equivalent backend and data fluency. Specifically:

- **Docker** (or Kind) and ~10 GB free disk — you'll run MinIO, a catalog, and Trino as containers.
- The **Week 14 CDC pipeline** (Debezium → Kafka → consumers) ideally running, so you can land *your* `orders` change stream in Iceberg. A standalone generator is provided as a fallback.
- You can write **analytical SQL** from memory: `GROUP BY`, `HAVING`, window functions (`OVER`, `PARTITION BY`), CTEs, and date functions. This week is heavy on SQL.
- You understand the **OLTP `orders` schema** from Week 13 and the **change-event shape** from Week 14 — the lakehouse consumes those.
- You're comfortable reading a `docker compose` file, mapping ports, and following a multi-container stack's logs when something doesn't connect.

You do **not** need prior data-engineering, Spark, or warehouse experience. We start at row-vs-column and build up to a federated query. If you've only ever thought of "the database" as one Postgres instance, this is the week you learn where the analytical half of the world lives.

## Topics covered

- **Row-store vs column-store.** How rows are laid out on disk vs how columns are, why an aggregation over one column reads 100× less data in a column-store, compression wins from columnar encoding, and why each layout is wrong for the other's workload.
- **OLTP vs OLAP, the boundary.** Transactional (many small reads/writes, low latency, strong consistency, current state) vs analytical (few huge scans, high throughput, eventual freshness, historical state); the failure modes of running analytics on your OLTP primary (lock contention, cache pollution, replica lag); and where the line actually falls.
- **The Parquet file format.** Columnar layout, row groups, column chunks, dictionary and run-length encoding, predicate pushdown via column statistics, and why Parquet is the substrate every lakehouse table format sits on.
- **Apache Iceberg.** The table format as a *spec*: the metadata tree (catalog pointer → metadata file → manifest list → manifest files → Parquet data files), snapshots and the snapshot log, **hidden partitioning** (partition transforms that don't leak into queries), schema and partition evolution without rewriting data, ACID via atomic metadata swaps, and time-travel.
- **Catalogs.** Why a table format needs a catalog (the atomic pointer to "the current table metadata"); the Iceberg REST catalog; **Project Nessie** (a git-like catalog with branches and tags for data); and the Hive Metastore as the legacy option.
- **Trino.** Architecture (coordinator, workers, connectors), the Iceberg connector, the Postgres connector, the Kafka connector; **federated queries** joining across connectors in one SQL statement; pushdown; and when federation beats ETL.
- **dbt and the transformation layer.** Transformations as version-controlled, tested SQL models; staging vs marts; materializations (view, table, incremental); the daily/hourly rollup pattern; and where dbt fits relative to the raw CDC landing zone.
- **The decision: push compute to the lakehouse or stay in Postgres.** The honest framework — query shape, data volume, freshness tolerance, and operational cost — for deciding where a given analytical query lives.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                       | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|-------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Row vs column; OLTP/OLAP boundary; Parquet                  |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Iceberg metadata, snapshots, hidden partitioning; catalogs  |    1h    |    2.5h   |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | Stand up MinIO + catalog + Trino; create & query Iceberg    |    2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | Trino federation; time-travel; dbt rollup model             |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Friday    | The orders-events lakehouse; the placement decision         |    0h    |    0h     |     1h     |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work                                       |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, review, placement memo polish                         |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                             | **6h**   | **7h**    | **4h**     | **3.5h**  | **5h**   | **12h**      | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./00-overview.md) | This overview (you are here) |
| [resources.md](./01-resources.md) | The Iceberg spec, Trino docs, dbt docs, Parquet/columnar references, and the talks worth your time |
| [lecture-notes/01-row-vs-column-oltp-olap-and-iceberg.md](./02-lecture-notes/01-row-vs-column-oltp-olap-and-iceberg.md) | Row vs column, the OLTP/OLAP boundary, Parquet, and the Iceberg table format in depth |
| [lecture-notes/02-trino-catalogs-federation-and-dbt.md](./02-lecture-notes/02-trino-catalogs-federation-and-dbt.md) | Catalogs, Trino architecture and federation, time-travel, dbt, and the placement decision |
| [exercises/README.md](./03-exercises/00-overview.md) | Index of the three exercises |
| [exercises/exercise-01-stand-up-the-lakehouse.md](./03-exercises/exercise-01-stand-up-the-lakehouse.md) | Bring up MinIO + REST catalog + Trino and create/query your first Iceberg table |
| [exercises/exercise-02-analytical-queries.sql](./03-exercises/exercise-02-analytical-queries.sql) | Trino analytical SQL against Iceberg: aggregations, windows, time-travel, federation |
| [exercises/exercise-03-land-the-stream.py](./03-exercises/exercise-03-land-the-stream.py) | Consume the `orders` change stream and append it into an Iceberg table |
| [challenges/README.md](./04-challenges/00-overview.md) | Index of the weekly challenge |
| [challenges/challenge-01-place-six-queries.md](./04-challenges/challenge-01-place-six-queries.md) | Place six queries on the OLTP/OLAP boundary with evidence and defend each call |
| [quiz.md](./05-quiz.md) | 13 questions with a hidden answer key |
| [homework.md](./06-homework.md) | Six problems including the headline OLTP/OLAP placement memo |
| [mini-project/README.md](./07-mini-project/00-overview.md) | The `orders-lakehouse`: CDC → Iceberg, a dbt revenue rollup, and a placement report |

## The "time-travel and the engine is swappable" promise

C22 uses a recurring marker for every exercise that ends in the lakehouse doing what only a lakehouse can. The marker is a **time-travel query** that reads the table *as it was* at an earlier snapshot:

```
trino> SELECT count(*) FROM iceberg.shop.orders FOR VERSION AS OF 8473625847362;
 _col0
-------
 41023        -- the row count at that snapshot, not now

trino> SELECT count(*) FROM iceberg.shop.orders;
 _col0
-------
 52910        -- the current row count
```

And the deeper marker — querying the *same* Iceberg table from a *different* engine (Trino, then DuckDB or Spark) and getting the same answer, proving the table is the contract, not the engine. If your time-travel query can't read an old snapshot, or a second engine can't read your table, you haven't built a lakehouse — you've built a pile of Parquet. The point of Week 15 is to make those two queries ordinary.

## Stretch goals

If you finish the regular work early and want to push further:

- Read the **Iceberg table spec** (the metadata section) until you can draw the catalog → metadata → manifest-list → manifest → data-file tree from memory: <https://iceberg.apache.org/spec/>. Then inspect the actual JSON metadata files MinIO holds for your table and find the snapshot you time-traveled to.
- Query your Iceberg table from **DuckDB** (`INSTALL iceberg; SELECT * FROM iceberg_scan('s3://...')`) and confirm you get the same result as Trino. That single experiment is the lakehouse thesis, proven on your laptop.
- Use **Nessie** instead of the REST catalog and create a **branch** of your `orders` table, write experimental rollups to the branch, validate them, and merge — git-for-data. Document the workflow.
- Add an **Iceberg `MERGE INTO`** that upserts the latest state of each order from the change stream (a CDC-to-Iceberg merge), and compare it to the append-only landing approach. Note the file-compaction implications.

## Up next

Week 16 turns from analytics back to the hot path with **caching** (Redis, Memcached, Dragonfly) — the other half of "where does a read go." The OLTP/OLAP placement instinct you build this week is the same instinct, pointed at a third tier. You close Phase 3's data arc here: Postgres (Week 13), the change stream (Week 14), the lakehouse (Week 15). Push your mini-project before you start it.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
