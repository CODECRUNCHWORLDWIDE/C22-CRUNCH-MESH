# Lecture 1 — Row vs Column, the OLTP/OLAP Boundary, and the Iceberg Table Format

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can explain why analytics wants columns and transactions want rows, draw the OLTP/OLAP boundary and place a query on it, and describe the Apache Iceberg table format — its metadata tree, snapshots, hidden partitioning, and how it gives you ACID and time-travel over object-store files.

If you remember one sentence from this entire week, remember this one:

> **The lakehouse is a contract — an open table format over open columnar files on object storage — and the contract, not any one query engine, is what you actually own. Trino queries it today; another engine queries it in five years; the data never moved.**

For most of this course, "the database" has meant Postgres: a row-oriented, transaction-optimized OLTP engine that is exactly right for the hot path. This week is about the *other* half of the data world — the analytical half — and why trying to serve it from your OLTP primary is a mistake you pay for in lock contention, cache pollution, and 3 a.m. pages. By the end you'll know where the boundary falls and how to build the analytical side on open foundations.

---

## 1. Row-store vs column-store

The single most important physical fact in this week: **how data is laid out on disk determines which workloads are cheap.**

Consider a table:

```
order_id | customer_id | status    | total_cents | created_at
1        | 42          | SHIPPED   | 1999        | 2026-03-01
2        | 7           | PLACED    | 500         | 2026-03-01
3        | 42          | DELIVERED | 8200        | 2026-03-02
...50 million rows...
```

A **row-store** (Postgres, most OLTP databases) writes all of one row's columns contiguously, then the next row:

```
[1,42,SHIPPED,1999,2026-03-01][2,7,PLACED,500,2026-03-01][3,42,DELIVERED,8200,2026-03-02]...
```

A **column-store** (Parquet, the lakehouse) writes all of one *column's* values contiguously, then the next column:

```
order_id:    [1,2,3,...]
customer_id: [42,7,42,...]
status:      [SHIPPED,PLACED,DELIVERED,...]
total_cents: [1999,500,8200,...]
created_at:  [2026-03-01,2026-03-01,2026-03-02,...]
```

Now the consequences. Two queries:

**Query A (OLTP):** "Give me order 3." A row-store seeks to row 3 and reads it — one contiguous chunk, all columns, done. A column-store must visit *five different places* (one per column) to reassemble the row. **Row-store wins.**

**Query B (OLAP):** "What's the total revenue?" — `SELECT sum(total_cents) FROM orders`. The column-store reads *only the `total_cents` column* — one contiguous run of 50M integers — and ignores the other four columns entirely. The row-store must read *all 50M rows in full* (every column of every row) just to extract the one column it needs, reading perhaps 100× more bytes off disk. **Column-store wins, enormously.**

That is the whole story in miniature. **Analytics reads few columns across many rows; transactions read many columns of few rows.** The column layout reads only the columns a query touches, which is why an aggregation over one column in a column-store reads a tiny fraction of the data a row-store would. On top of that, storing a column together means storing *like values together*, which compresses far better (run-length encoding a column of mostly-`SHIPPED` statuses, dictionary-encoding a low-cardinality column) — often 5–10× smaller on disk, which is 5–10× less I/O again. The wins compound.

And the corollary: a column-store is *terrible* at OLTP. Inserting one row means touching every column's storage; updating one field means rewriting in a columnar structure that was built to be read, not mutated. This is why you don't run your transactions on a column-store and don't run your analytics on a row-store. Different layouts, different jobs.

---

## 2. The OLTP/OLAP boundary

This physical difference maps to two workload families you must be able to tell apart on sight.

| | OLTP (Postgres) | OLAP (lakehouse) |
|---|---|---|
| Query shape | Point reads, single-row writes, small joins | Large scans, aggregations, wide joins |
| Rows touched | Few (1 – thousands) | Many (millions – billions) |
| Columns touched | Many (the whole row) | Few (the aggregated ones) |
| Latency target | Milliseconds | Seconds to minutes is fine |
| Consistency | Strong, current state, transactional | Eventual freshness is acceptable |
| Concurrency | Thousands of concurrent small txns | Few concurrent big queries |
| Write pattern | Constant small writes | Bulk append / periodic load |
| Example | "Place this order," "load my cart" | "Revenue by region by month," "cohort retention" |

The trap that pages you at 3 a.m.: **running OLAP queries on your OLTP primary.** A finance dashboard that does `SELECT region, sum(total_cents) FROM orders GROUP BY region` over 50M rows on your *production primary* will:

- **Pollute the buffer cache.** Your working set of hot order rows gets evicted by the analytical scan's cold pages, and suddenly your point reads — the queries that matter for latency — are hitting disk.
- **Hold locks and burn I/O** that your transactional workload needs.
- **Lag your replica** if you run it there (the long read query blocks WAL replay — recall Week 13 `max_standby_streaming_delay`).

The answer is *not* "buy a bigger primary." The answer is to put analytics where they belong: a column-store, fed by the change stream you built in Week 14, queried by an engine built for big scans. That's the lakehouse.

### 2.1 Where the line actually falls

It is not always obvious. The honest framework (developed fully in Lecture 2 §5):

- **Point lookups and transactional writes → always Postgres.** No lakehouse for "give me this order."
- **Small, frequent aggregations on fresh data that a dashboard polls → often Postgres** (a partitioned, indexed rollup table, maybe a materialized view), *if* it stays cheap. Don't build a lakehouse for a query that an index fixes.
- **Large scans, historical analytics, cross-domain joins, anything that would pollute the OLTP cache → lakehouse.**
- **The decider is query shape × data volume × freshness tolerance.** A monthly rollup over two years of orders with a few-minutes freshness tolerance is a lakehouse query. A "count of open orders right now" is a Postgres query.

You will make this call repeatedly. Getting it right is the week's headline skill, and the homework memo is exactly this judgment.

---

## 3. Parquet: the columnar substrate

Before Iceberg, the file. **Apache Parquet** is the open columnar file format every lakehouse table format sits on. A Parquet file is organized as:

- **Row groups** — horizontal slices of the table (e.g., a million rows). A query can skip whole row groups.
- **Column chunks** — within a row group, each column's data stored together (the columnar part).
- **Pages** — within a column chunk, the unit of encoding and compression.
- **Encodings** — dictionary encoding (store distinct values once, reference by index), run-length encoding (store "SHIPPED × 4,000" not 4,000 copies), bit-packing. These are why columnar compresses so well.
- **Statistics** — each column chunk stores min/max/null-count. This enables **predicate pushdown**: a query `WHERE total_cents > 100000` can skip any row group whose `total_cents` max is below 100000, *without reading the data*. The metadata answers the question.

That last point matters: a well-laid-out Parquet dataset lets a query read only the row groups and columns it needs, guided by statistics, often touching a tiny fraction of the bytes. Parquet alone, though, is just files. It has no concept of "a table," no schema evolution, no atomic commit, no time-travel. That's what a table format adds.

---

### 3a. Warehouse, data lake, lakehouse — the three eras

The word "lakehouse" is a deliberate portmanteau, and the history explains why it's the right pattern. There were two prior eras, each solving the other's problem and creating a new one.

- **The data warehouse era.** A proprietary, columnar, OLAP database (Teradata, then Redshift, Snowflake, BigQuery). You ETL'd data into it, queried it in its dialect, and got fast analytics with real table semantics — schema, transactions, governance. The cost: your data lived *inside* the vendor's system. Leaving meant a migration; the warehouse owned your tables and your bill.
- **The data lake era.** "Just dump everything as files (Parquet, JSON) on cheap object storage (S3/HDFS) and query it with whatever engine." This fixed the lock-in — the data was open files you owned — but threw away the table semantics. A pile of Parquet files has no atomic commits, no schema evolution, no time-travel, no "what is the current state of this table?" Concurrent writers clobbered each other; a half-finished job left readers seeing inconsistent data. Data lakes became "data swamps."

- **The lakehouse era (the synthesis).** Keep the data lake's openness — columnar files on object storage you own — but add a **table format** (Iceberg) that layers warehouse semantics on top: atomic commits, schema evolution, time-travel, ACID, governance. You get the warehouse's table guarantees *and* the lake's open, vendor-neutral storage. The "lake" is the open files; the "house" is the table semantics over them. Hence *lakehouse*.

This is why Iceberg matters historically, not just technically: it's the component that turns a data lake (open but ungoverned) into something with warehouse-grade semantics (governed) *without* re-introducing warehouse lock-in (proprietary). Each era fixed the prior one's flaw; the lakehouse is the first to fix both at once. When you build on Iceberg + Trino, you are choosing the synthesis deliberately — open storage, real semantics, swappable compute — over both the locked-in warehouse and the ungoverned swamp.

## 4. Apache Iceberg: the table format

Parquet files in a bucket are not a table — they're a pile of files. **Apache Iceberg** is a *specification* for what makes that pile a table: a schema, a partition scheme, a sequence of immutable snapshots, and a tree of metadata that points at the data files. Critically, Iceberg is a **spec, not an engine** — Trino, Spark, Flink, DuckDB, and PyIceberg all implement it, so any of them can read and write the same table. That portability is the entire thesis.

### 4.1 The metadata tree

This is the structure to be able to draw from memory. Top to bottom:

```
catalog                 ── an atomic pointer: "the current metadata file for table X"
   │
   ▼
table metadata file     ── schema, partition spec, snapshot LIST, current snapshot id
   │   (one per commit; a new one is written on every change)
   ▼
manifest list           ── one per snapshot; lists the manifest files in that snapshot
   │
   ▼
manifest files          ── each lists data files + per-file column stats (min/max/counts)
   │
   ▼
data files (Parquet)    ── the actual columnar data on object storage
```

Read it bottom-up: the **data files** are Parquet on S3/MinIO. A **manifest** lists a set of data files with their stats. A **manifest list** groups the manifests that make up one **snapshot**. The **table metadata file** records the schema, the partition spec, and the full list of snapshots, naming the current one. The **catalog** holds a single atomic pointer to the current metadata file.

### 4.2 How this gives you ACID and time-travel

Here's the elegant part. Every change to the table — append, delete, schema change — produces a **new metadata file** describing a **new snapshot**, and commits by **atomically swapping the catalog's pointer** from the old metadata file to the new one. Because the swap is a single atomic operation (a compare-and-swap in the catalog), you get **ACID semantics over object storage that doesn't itself support transactions**:

- A reader that started before the swap keeps reading the old snapshot — consistent, no half-written state.
- Two concurrent writers each try to swap the pointer; the catalog's atomic CAS lets exactly one win (the other retries against the new base — optimistic concurrency, the same pattern as the Week 14 event store).
- Old snapshots aren't deleted on commit; they're still referenced in the snapshot log. So you can query the table **as of any past snapshot** — **time travel** — until you expire old snapshots to reclaim space.

```sql
-- Time travel: the table as it was at an earlier snapshot.
SELECT count(*) FROM iceberg.shop.orders FOR VERSION AS OF 8473625847362;
SELECT count(*) FROM iceberg.shop.orders FOR TIMESTAMP AS OF TIMESTAMP '2026-03-01 00:00:00 UTC';
```

This is something no pile-of-Parquet and no traditional warehouse easily gives you: a consistent, queryable history of the table, for free, as a consequence of the snapshot-and-swap design.

### 4.3 Hidden partitioning — the feature that fixes the oldest data-lake bug

In old Hive-style data lakes, partitioning leaked into your queries. You partitioned by `day`, and you had to write `WHERE day = '2026-03-01'` *and* `WHERE created_at >= ...` — and if you forgot the `day` predicate, you scanned everything. Worse, you stored a redundant `day` column derived from `created_at`, and they could disagree.

Iceberg's **hidden partitioning** fixes this. You declare a partition *transform* on a real column:

```sql
CREATE TABLE iceberg.shop.orders (
    order_id bigint, customer_id bigint, status varchar,
    total_cents bigint, created_at timestamp
) WITH (
    partitioning = ARRAY['month(created_at)']   -- partition by a TRANSFORM of created_at
);
```

Now you partition by `month(created_at)` — but you query with a normal predicate on `created_at`, and Iceberg figures out which partitions to prune *itself*. No leaked `month` column, no redundant predicate, no chance of disagreement:

```sql
-- You write the natural predicate; Iceberg prunes the right month-partitions.
SELECT count(*) FROM iceberg.shop.orders
WHERE created_at >= TIMESTAMP '2026-03-01' AND created_at < TIMESTAMP '2026-04-01';
```

Available transforms include `year`, `month`, `day`, `hour`, `bucket(N, col)` (hash into N buckets), and `truncate`. This is strictly better than the Postgres declarative partitioning from Week 13 in one respect: the partitioning doesn't constrain your query syntax, and you can **evolve the partition spec** later without rewriting existing data.

### 4.3a Why Iceberg's metadata makes scans fast: stats all the way down

It's worth seeing *why* the metadata tree (§4.1) isn't just bookkeeping but a performance feature, because it's the same predicate-pushdown idea as Parquet (§3), one level up.

Recall that each **manifest** lists data files *with their per-file column statistics* (min/max/null-count). So before a query reads a single Parquet file, Iceberg can consult the manifests and answer "which data files could possibly contain rows matching `WHERE total_cents > 100000`?" — skipping every file whose `total_cents` max is below 100000 without opening it. Then *within* each surviving file, Parquet's own row-group statistics skip non-matching row groups. You get two layers of skipping — file-level from Iceberg's manifests, row-group-level from Parquet — before any actual data is read.

Combine that with **partition pruning** (skip whole partitions the predicate can't match) and **column projection** (read only the columns the query selects), and a well-laid-out Iceberg table can answer a selective query by reading a tiny fraction of its total bytes. A `SELECT sum(total_cents) FROM orders_events WHERE created_at >= '2026-03-01' AND created_at < '2026-04-01' AND total_cents > 100000` touches: one month-partition (pruning), within it only files whose `total_cents` max clears 100000 (manifest stats), within those only the `total_cents` and `created_at` columns (projection), within those only matching row groups (Parquet stats). Four layers of "don't read what you don't need."

This is the column-store advantage from §1 compounded by the table format's metadata. It's also why the small-file problem (§5b) hurts so much: stats only help if there are few enough files that consulting the manifests is cheaper than scanning — thousands of tiny files means thousands of manifest entries to check and thousands of files to open, drowning the benefit. The metadata makes big files fast and small files slow, which is the whole reason compaction is a query-performance concern, not just tidiness.

### 4.4 Schema and partition evolution

Because the schema lives in metadata referencing data files by *field ID* (not column position), Iceberg evolves the schema without rewriting data:

- **Add a column** — new metadata, old data files just return null for it. Cheap.
- **Drop / rename a column** — a metadata change; old files are read through the field-ID mapping. No rewrite.
- **Change the partition spec** — new data is written under the new spec; old data keeps its old spec; queries read both correctly.

Contrast Week 14's lesson that adding a field to a ROS2 message or coordinating a logical-replication DDL is a redeploy-everything event. Iceberg schema evolution is the opposite — a cheap metadata operation — *because* the data is described by metadata rather than by position. That's a direct payoff of the table-format design.

---

## 5. A worked example: the orders events as an Iceberg table

Tie it to the stream you've been building. Your Week 14 CDC pipeline emits every `orders` change. The lakehouse lands those changes in an Iceberg table partitioned by `month(created_at)`:

```sql
-- In Trino, against the Iceberg catalog:
CREATE TABLE iceberg.shop.orders_events (
    order_id    bigint,
    customer_id bigint,
    status      varchar,
    total_cents bigint,
    op          varchar,          -- c/u/d/r from the change event
    lsn         bigint,           -- the WAL position; ordering + dedup key
    created_at  timestamp
) WITH (partitioning = ARRAY['month(created_at)']);
```

A consumer (Exercise 3) reads the change stream and appends each event. Then analytics that would have hammered your OLTP primary run here instead:

```sql
-- The daily revenue rollup — an OLAP query, on the lakehouse, not the primary.
SELECT date_trunc('day', created_at) AS day,
       count(*) AS orders,
       sum(total_cents) / 100.0 AS revenue_dollars
FROM iceberg.shop.orders_events
WHERE op IN ('c', 'r')                       -- count creations/snapshot rows
GROUP BY 1 ORDER BY 1;
```

This scan reads only the columns it touches (`created_at`, `op`, `total_cents`), prunes to the relevant month-partitions automatically, and runs on a query engine built for it — without evicting a single hot order row from your Postgres cache. And because it's Iceberg, you can ask it "what did revenue look like as of last Tuesday's snapshot?" with time-travel. Exercise 1 stands up the stack; Exercise 2 writes these queries; Exercise 3 lands the stream.

---

## 5a. Iceberg versus the alternatives, and why the format matters

You will hear "Iceberg vs Delta Lake vs Hudi" — the three open table formats — and a reviewer may ask why this course teaches Iceberg. The honest answer has two parts.

First, **all three solve the same core problem**: they add table semantics (schema, snapshots, ACID, partition evolution, time-travel) on top of Parquet files in object storage. Delta Lake (originally tied to Spark/Databricks) and Apache Hudi (originally LinkedIn/Uber, strong on upserts and incremental pulls) are real, capable formats. This is not a case where two are toys.

Second, **Iceberg won the openness argument**, which is why it's the 2026 default for vendor-neutral lakehouses. Its specification is engine-first rather than engine-derived: the spec defines the table, and Trino, Spark, Flink, DuckDB, Snowflake, BigQuery, and others implement readers and writers against *the spec*. The REST catalog standardizes the one remaining coordination point. The practical consequence is that an Iceberg table is the least likely of the three to lock you to a particular engine or vendor — which is the entire reason a lakehouse exists. Delta and Hudi have narrowed the gap and added cross-engine support, but the *design center* of Iceberg is engine-neutrality, and for a course about owning your data on open foundations, that's the one to teach.

The deeper point, which outlives any format war: **the table format is a contract, and contracts are where lock-in lives or dies.** A proprietary warehouse's "table" is defined by the warehouse's code — leave the warehouse and the table is gone. An Iceberg table is defined by a published spec and a pile of open files — leave any one engine and the table is exactly where you left it, readable by the next engine. When you choose a table format you are choosing how replaceable your compute is. That is a more important decision than which engine is fastest this quarter, because engines come and go and your data outlives all of them.

## 5b. The small-file problem and compaction

One operational fact about lakehouse tables that bites every team: **too many small files destroys query performance**, and a naive streaming ingest creates them by the thousand. Each time you append to an Iceberg table you write at least one new data file; if your CDC lander commits one row (or one tiny batch) per snapshot, you accumulate thousands of tiny Parquet files, each with its own metadata overhead, and a query that should read a few large files instead opens thousands of small ones — a metadata and I/O storm that can make the lakehouse *slower* than the database it replaced.

The two defenses:

- **Batch your writes.** A streaming consumer should buffer changes and append them in reasonable batches (say, every few thousand rows or every minute), not one row at a time. This is why the Exercise 3 lander batches, and why the mini-project explicitly forbids one-row snapshots.
- **Compact periodically.** Iceberg provides a `rewrite_data_files` maintenance action that rewrites many small files into fewer large ones, and `expire_snapshots` to drop old snapshots and their now-unreferenced files. You schedule these as background maintenance — the lakehouse equivalent of `VACUUM`/`pg_repack` from Week 13. A table that's never compacted degrades the same way a table that's never vacuumed does.

The throughline from Week 13: every storage system has a "garbage accumulates, reclaim it" maintenance loop. Postgres has autovacuum and `pg_repack`; Iceberg has snapshot expiry and file compaction. Knowing that the loop exists — and scheduling it — is the difference between a lakehouse that stays fast and one that quietly rots into a small-file swamp.

## 6. The placement decision tree

When a query lands on your desk, decide where it runs:

```
A new query needs to run. OLTP or OLAP?
│
├─ Is it a point read / single-row write / transactional?
│   └─ Yes → Postgres (OLTP). Done. No lakehouse.
│
├─ Is it a small, frequent aggregation on FRESH data that an index/rollup fixes cheaply?
│   └─ Yes → Postgres, with an index or a materialized rollup table. Don't over-build.
│
├─ Is it a large scan / historical / cross-domain aggregation, OR would it pollute the
│  OLTP cache / lag the replica?
│   └─ Yes → lakehouse (Iceberg + Trino). Feed it from the change stream.
│
└─ Does it need a CONSISTENT historical view ("as of date X")?
    └─ Yes → lakehouse, time-travel. Postgres doesn't give you this.
```

Tape this next to the federation/dbt guidance from Lecture 2. Between them you can place any analytical query and justify it.

---

## 6a. The freshness gap, and why it's acceptable for analytics

One axis of the OLTP/OLAP boundary deserves its own treatment because it surprises people: **the lakehouse is always a little behind the source database, and for analytics that's fine.**

Your `orders_events` Iceberg table is fed by the change stream, which has CDC lag (Week 14) — the time between a change committing in Postgres and that change landing in Iceberg. Plus, you batch writes into Iceberg to avoid the small-file problem (§5b), which adds more delay. So a row inserted in Postgres might not be queryable in the lakehouse for seconds to minutes. The lakehouse is *eventually* consistent with the OLTP source.

For OLTP, that gap would be a correctness bug — "place an order, immediately read it back, it's missing." For OLAP, it's almost always a non-issue, because analytical questions are about *aggregates over history*, not the exact current value of one row. "What was revenue last month?" does not change because the last thirty seconds of orders haven't landed yet. "Cohort retention over the past year" is unaffected by a one-minute lag. The freshness an analytical query needs is measured in minutes-to-hours, and the lakehouse comfortably meets it.

The discipline is to **make the freshness gap explicit and bounded**, not to pretend it's zero:

- **Measure it.** End-to-end freshness (commit in Postgres → queryable in Iceberg) is a number you can monitor, the same way you monitor replication lag and read-model lag. It's the same metric, a third time.
- **Set an SLO on it.** If the finance dashboard needs data no more than an hour stale, that's an SLO (Week 18) on the freshness gap. If your pipeline can't meet it, you tune the batch interval or the CDC lag — you don't pretend.
- **Route freshness-critical reads elsewhere.** The rare analytical query that genuinely needs the absolute-current value (a real-time fraud aggregate, say) reads Postgres or federates to it, not the lakehouse. Most don't.

The pattern across all of Phase 3 is now visible: Postgres replicas have replication lag, CQRS read models have projection lag, the lakehouse has CDC-plus-batch lag. Every derived copy of your data trails its source by *some* bounded amount, and the engineering is always the same — measure the lag, bound it with an SLO, and route the reads that can't tolerate it back to the source. Internalize that pattern and every "is this stale?" question answers itself.

## 7. Recap

You should now be able to:

- Explain why row-stores win OLTP and column-stores win OLAP, with the I/O and compression math.
- Reason about the lakehouse's freshness gap, why it's acceptable for analytics, and how to bound it with measurement and an SLO.
- Place a query on the OLTP/OLAP boundary and name the failure modes of running analytics on the OLTP primary.
- Describe Parquet's columnar layout and how column statistics enable predicate pushdown.
- Draw the Iceberg metadata tree (catalog → metadata → manifest list → manifests → data files) and explain how the atomic pointer swap gives ACID and time-travel over object storage.
- Use hidden partitioning (partition by a transform, query with a natural predicate) and explain why Iceberg schema evolution is a cheap metadata operation.
- Place the lakehouse in the warehouse → data-lake → lakehouse history, and reason about the freshness gap.

The mental model to carry out of this lecture: **the lakehouse decouples three things a warehouse fused together — the data (open columnar files you own), the table semantics (an open spec, Iceberg), and the compute (any engine).** A warehouse owned all three, which is what made it both convenient and a cage. By splitting them, the lakehouse lets you keep warehouse-grade table behavior — ACID, time-travel, schema evolution — on storage and a format that no vendor controls, queried by compute you can swap or scale at will. When you create that first Iceberg table in the exercise and then read it from a second engine, you are watching that decoupling in action: the table didn't move, didn't change, and didn't care which engine asked. That indifference is the whole point, and it's why the lecture title insists on Iceberg's *spec* over any product's *marketing*.

Next up: the engine that queries all this (Trino), the catalog that anchors it, federation across sources, and dbt for the transformation layer — plus the full placement framework. Continue to [Lecture 2 — Catalogs, Trino, Federation, and dbt](./02-trino-catalogs-federation-and-dbt.md).

---

## 8. A note on what you are *not* doing

It's as important to know what the lakehouse is *not* for as what it is. You are not replacing Postgres — the OLTP primary remains the transactional source of truth, and the lakehouse is downstream of it, fed by the change stream. You are not moving your hot path; point reads, transactional writes, and freshness-critical reads stay where they belong. You are not adopting a vendor; the whole architecture is open files, an open format, and swappable engines, precisely so you *don't* trade one lock-in for another.

What you *are* doing is giving analytics a home that is built for it — columnar, scan-optimized, history-retaining, time-travelable — so that the questions analysts and finance and growth ask stop competing with the transactions that keep the business running. The cleanest way to state the week's contribution: **the lakehouse is where you put the queries that would otherwise hurt your database.** Everything else — Iceberg's metadata, Trino's federation, dbt's transforms — is machinery in service of that one move: getting the big, historical, scan-heavy analytical workload off the OLTP primary and onto open foundations built to serve it.

## References

- *Apache Iceberg — table spec*: <https://iceberg.apache.org/spec/>
- *Apache Iceberg — docs (partitioning, evolution, time travel)*: <https://iceberg.apache.org/docs/latest/>
- *Parquet — file format*: <https://parquet.apache.org/docs/file-format/>
- *Trino — Iceberg connector*: <https://trino.io/docs/current/connector/iceberg.html>
- *The lakehouse paper (CIDR 2021)*: <https://www.cidrdb.org/cidr2021/papers/cidr2021_paper17.pdf>
