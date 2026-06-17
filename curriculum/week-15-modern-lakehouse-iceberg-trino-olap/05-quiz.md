# Week 15 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 16. Answer key is at the bottom — don't peek.

---

**Q1.** Why does a column-store read far less data than a row-store for `SELECT sum(total_cents) FROM orders`?

- A) Column-stores compress better, that's the only reason.
- B) A column-store reads only the `total_cents` column's contiguous storage; a row-store must read every column of every row to extract the one column it needs.
- C) Column-stores have more indexes.
- D) Row-stores can't compute sums.

---

**Q2.** Which workload belongs on a row-store (OLTP), not a column-store?

- A) Aggregating revenue across 50M rows.
- B) "Give me order 1001" — a point read of all columns of one row.
- C) A two-year cohort retention analysis.
- D) A monthly rollup over historical data.

---

**Q3.** What is the danger of running a large analytical aggregation on your OLTP primary?

- A) Nothing; Postgres handles all workloads equally.
- B) The analytical scan pollutes the buffer cache (evicting hot rows), holds locks/I-O the hot path needs, and can lag a replica — slowing the transactional workload.
- C) It corrupts the data.
- D) It requires a column-store license.

---

**Q4.** What does Parquet's per-column-chunk min/max statistics enable?

- A) Encryption.
- B) Predicate pushdown — a query can skip whole row groups whose stats can't match the predicate, without reading the data.
- C) Row-level locking.
- D) Schema evolution.

---

**Q5.** Apache Iceberg is best described as:

- A) A query engine.
- B) A **table format** (a spec) for schema, snapshots, partitions, and file manifests over columnar files on object storage — readable by any engine that implements it.
- C) A proprietary data warehouse.
- D) A replacement for Postgres.

---

**Q6.** How does an Iceberg commit achieve ACID over object storage that doesn't support transactions?

- A) It locks the entire bucket.
- B) It writes a new metadata file (a new snapshot) and atomically swaps the catalog's pointer from the old metadata to the new — a single atomic compare-and-swap.
- C) It uses two-phase commit across S3.
- D) Object storage is already transactional.

---

**Q7.** With Iceberg **hidden partitioning** (`partitioning = ARRAY['month(created_at)']`), how do you write a query to get pruning?

- A) `WHERE month_col = '2026-03'` using an explicit partition column.
- B) A natural predicate on `created_at` (e.g., `WHERE created_at >= ... AND < ...`); Iceberg prunes by the transform itself — the partition value never appears in your SQL.
- C) You can't prune with hidden partitioning.
- D) You must add a `month` column to the table.

---

**Q8.** Why is adding a column to an Iceberg table cheap (no data rewrite)?

- A) Iceberg stores everything in one file.
- B) Iceberg tracks columns by field ID in metadata; a new column is a metadata change, and old data files just return null for it.
- C) Iceberg rewrites all data files in the background.
- D) Adding columns is not supported.

---

**Q9.** What is the catalog's role in an Iceberg lakehouse?

- A) It stores the actual data.
- B) It holds the atomic pointer to the current table-metadata file and provides the compare-and-swap that makes commits ACID; it's the one stateful coordination point.
- C) It runs the queries.
- D) It compresses the Parquet files.

---

**Q10.** Trino is:

- A) A database that stores your data.
- B) A distributed SQL query engine (coordinator + workers + connectors) that queries data where it lives across many sources, storing nothing itself.
- C) A replacement for Iceberg.
- D) A row-store.

---

**Q11.** When is Trino federation the *wrong* tool?

- A) For ad-hoc cross-source exploration.
- B) For a production query that runs constantly and scans a huge Postgres table live every run — you'd hammer the OLTP source; land the data into Iceberg and query it there instead.
- C) For joining a big Iceberg fact to a small live Postgres dimension occasionally.
- D) Federation is never the wrong tool.

---

**Q12.** What does dbt's **incremental** materialization give you for a daily rollup?

- A) It rebuilds the entire table from all history every run.
- B) It processes only new rows since the last run and merges them, so you don't rescan years of data nightly.
- C) It stores the rollup in Postgres.
- D) It disables tests.

---

**Q13.** A query is a `count(*) WHERE status='PLACED'` polled every 10 seconds for an ops dashboard, needing the current value. Where does it belong?

- A) The lakehouse, because it's an aggregation.
- B) Postgres — it's small, needs the *current* value, and is fixed by an index/partial index; the lakehouse would lose freshness (CDC lag) and gain nothing.
- C) A dbt rollup.
- D) Federated across both.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — Columnar layout lets a query read only the columns it touches; the row-store must read full rows. Compression is a second, additional win. (Lecture 1 §1.)
2. **B** — A point read of a whole row is the row-store's home turf; aggregations belong on the column-store. (Lecture 1 §1–2.)
3. **B** — Cache pollution, lock/I-O contention, and replica lag — analytics on the OLTP primary harm the transactional workload. (Lecture 1 §2.)
4. **B** — Column statistics enable predicate pushdown: skip row groups that can't match, without reading them. (Lecture 1 §3.)
5. **B** — Iceberg is a table-format *spec*, engine-agnostic, over columnar files on object storage. (Lecture 1 §4.)
6. **B** — A new metadata file plus an atomic catalog-pointer swap gives ACID and time-travel over non-transactional object storage. (Lecture 1 §4.2.)
7. **B** — You write a natural predicate on the source column; Iceberg prunes by the transform; the partition value never leaks into your SQL. (Lecture 1 §4.3.)
8. **B** — Field-ID-based metadata makes adding/dropping/renaming columns a cheap metadata operation, no data rewrite. (Lecture 1 §4.4.)
9. **B** — The catalog is the atomic current-metadata pointer and the only stateful coordination point. (Lecture 2 §1.)
10. **B** — Trino is a federated query engine that stores nothing and reads sources via connectors. (Lecture 2 §2.)
11. **B** — Don't federate a constant, heavy live scan of a Postgres table; land it in Iceberg and query that. (Lecture 2 §2.3.)
12. **B** — Incremental models process only new rows and merge, avoiding a full historical rescan each run. (Lecture 2 §3.)
13. **B** — Small, current, indexable → Postgres. The lakehouse would add CDC-lag staleness for no benefit. (Lecture 2 §4; the Q2 trap.)

</details>

---

If you scored under 9, re-read the lecture sections cited in the answers you missed. If you scored 11 or higher, you're ready for the [homework](./06-homework.md).
