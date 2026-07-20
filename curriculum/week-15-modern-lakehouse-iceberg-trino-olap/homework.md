# Week 15 Homework

Six problems that revisit the week's topics and force the lakehouse and OLTP/OLAP-placement literacy into your fingers. The full set should take about **5 hours**. Work in your Week 15 Git repository (the same workspace as the exercises and the `orders-lakehouse` mini-project) so every problem produces at least one commit you can point to at the Phase 3 architecture review.

The headline deliverable is **Problem 4 — the OLTP/OLAP placement memo**. Treat it as the artifact a staff engineer reads to approve a data-tier topology, not a journal entry.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

Run everything against the Exercise 1 lakehouse stack (MinIO + Iceberg catalog + Trino), plus your Week 13/14 Postgres for the placement and federation problems.

---

## Problem 1 — The Iceberg metadata tour

**Problem statement.** Create an Iceberg table, insert two batches of rows (two separate `INSERT`s so you get two snapshots), then *map the metadata tree on disk*. Using `mc ls -r` against MinIO and the Iceberg metadata tables (`$snapshots`, `$manifests`, `$files`, `$partitions`), produce an annotated diagram of the actual files for your table: the metadata JSONs, the manifest lists, the manifests, and the partitioned Parquet data files. Match each file to its place in the Lecture 1 §4.1 tree.

**Acceptance criteria.**

- `notes/week-15/metadata-tour.md` contains the real `mc ls -r` output and the metadata-table output, annotated to the catalog → metadata → manifest-list → manifest → data-file hierarchy.
- You identify which metadata file corresponds to which snapshot, and show the two snapshots in `$snapshots`.
- You state, in one sentence, why "this pile of files plus that metadata IS the table" — and what makes it engine-portable.
- Committed.

**Hint.** `SELECT * FROM iceberg.shop."orders$files";` lists the data files with their stats; `"orders$manifests"` lists manifests. The `metadata/*.json` files in MinIO are the table-metadata files (one per commit); the `snap-*.avro` is a manifest list. Reading them side by side is the whole point.

**Estimated time.** 40 minutes.

---

## Problem 2 — Time-travel and snapshot expiry

**Problem statement.** Demonstrate time-travel and its cost. Build an Iceberg table with several snapshots (insert, update via `MERGE` or re-insert, insert again). Capture a snapshot ID and timestamp. Run `FOR VERSION AS OF` and `FOR TIMESTAMP AS OF` queries showing the table's earlier state. Then run `expire_snapshots` to remove old snapshots and show that the time-travel query to an expired snapshot now *fails* — proving time-travel is bounded by retention, not free forever.

**Acceptance criteria.**

- `notes/week-15/time-travel.md` shows: the snapshot list, a `FOR VERSION AS OF` and a `FOR TIMESTAMP AS OF` query each returning an earlier state, and the post-expiry failure.
- You correctly state that snapshots (and their unreferenced data files) consume storage, and expiry is the cost/retention knob.
- Committed.

**Hint.** Trino exposes snapshot expiry via `ALTER TABLE ... EXECUTE expire_snapshots(retention_threshold => '7d')` (syntax varies by version — check the connector docs). After expiry, time-traveling to an expired snapshot errors; that error is the lesson, not a bug.

**Estimated time.** 45 minutes.

---

## Problem 3 — A dbt rollup with tests that gate

**Problem statement.** Build a small `dbt-trino` project against your Iceberg lakehouse with a `stg_orders` staging model (dedup the change events by LSN, cast types) and a `daily_revenue` incremental mart. Add at least two dbt tests (`not_null` on `day`, `unique` on `day`, or `accepted_values` on status). Then *deliberately break the data* (inject a duplicate `day` or a null) and show `dbt build` **fails** the test — proving the test is a real gate, not decoration.

**Acceptance criteria.**

- `notes/week-15/dbt/` contains the dbt project (models + `schema.yml` tests).
- `dbt build` succeeds on clean data and produces an Iceberg `daily_revenue` table.
- You show `dbt build` **failing** on injected-bad data, with the test-failure output.
- You correctly explain why the mart is `incremental` (it processes only new events, not all history each run).
- Committed.

**Hint.** `dbt-trino`'s profile points at your Trino coordinator with the `iceberg` catalog. The incremental `WHERE created_at > (SELECT max(day) FROM {{ this }})` clause is what avoids the full rescan. To break a test, land an event that produces a duplicate `day` key or a null `created_at` and re-run `dbt build`.

**Estimated time.** 1 hour.

---

## Problem 4 — The OLTP/OLAP placement memo (headline deliverable)

**Problem statement.** This is the staff-review artifact. You run the marketplace's data tier: a Postgres OLTP primary (50M-row `orders`) and an Iceberg+Trino lakehouse fed by the change stream. Five analytical needs arrive: (1) the exec daily-revenue dashboard; (2) the ops "open orders right now" widget; (3) the growth team's quarterly cohort-retention analysis; (4) a support tool showing a customer's lifetime spend next to their live loyalty tier; (5) the merchandising homepage's "top products this week," refreshed every 5 minutes. Write a memo at `notes/week-15/placement-memo.md` placing each on the right tier (Postgres / lakehouse / federate / dbt rollup) with a four-axis justification and a measurement.

For each need, your memo must state:

1. **Placement** — exactly one tier, named.
2. **Four-axis justification** — shape × volume × freshness × operational cost, one line each.
3. **The measurement** that confirms it (an `EXPLAIN`, a `pg_stat_statements` entry, a cache-hit ratio, a Trino time, a CDC-lag reading).
4. **The query you'd be tempted to misplace** — for at least one need, note the reflex answer and why it's wrong.

**Acceptance criteria.**

- `notes/week-15/placement-memo.md` exists, fits one-to-two pages, and places all five needs with parts 1–4.
- Your placements are defensible: dashboard → lakehouse/dbt rollup; "open orders now" → Postgres (indexed); cohort → lakehouse; lifetime-spend-plus-tier → federate; top-products-every-5-min → dbt rollup in the lakehouse (NOT a live Postgres scan).
- Each placement names a concrete measurement, not just an assertion.
- You explicitly flag at least one reflex-trap (the "open orders now" looks like analytics but is Postgres; the "top products this week" looks small but is an OLAP load at that frequency).
- It reads like a memo to a staff engineer, not a tutorial.
- Committed.

**Hint.** Reuse your mini-project's measured OLTP before/after as evidence. The strongest memos place by *shape × volume × freshness × frequency*, not by shape alone — and explicitly keep at least one query in Postgres to prove you're not lakehouse-everything. State, for one need, "what would change this placement."

**Estimated time.** 1 hour.

---

## Problem 5 — Federation done right (and wrong)

**Problem statement.** Configure the Trino Postgres connector and write the "customer lifetime spend (Iceberg history) + current loyalty tier (live Postgres)" federated query. Run it and `EXPLAIN (TYPE DISTRIBUTED)` it to see where Trino pushes work down to each source. Then demonstrate the *anti-pattern*: write a federated query that scans a large Postgres table live on every run (e.g., a full `order_items` aggregation through Trino), observe the load it puts on the OLTP primary, and explain why this one should be *landed* in Iceberg instead.

**Acceptance criteria.**

- `notes/week-15/federation.md` shows the good federated query, its result, and the distributed `EXPLAIN` (with the pushdown).
- It shows the anti-pattern query and evidence of OLTP-primary load (a `pg_stat_statements` entry, or a concurrent point-read latency degradation while it runs).
- You state the rule: federate to join a small live dimension occasionally; land-and-query for anything heavy or repeated against the OLTP source.
- Committed.

**Hint.** In the distributed `EXPLAIN`, look for the aggregation being pushed to the Postgres connector (`Aggregate` nodes near the `TableScan` for the postgres catalog) — that's pushdown working. The anti-pattern's harm is most visible if you run it in a loop while timing a `WHERE order_id = ?` point read against the same Postgres.

**Estimated time.** 50 minutes.

---

## Problem 6 — Prove the engine is swappable

**Problem statement.** This is the lakehouse thesis, made concrete. Take an Iceberg table you built with Trino and read it from a **completely different engine** — DuckDB's Iceberg extension is the simplest. Run the *same* aggregation in both Trino and DuckDB and assert the results are identical. Then write one paragraph on why this property (the table is the contract, the engine is swappable) is the central value proposition of the lakehouse versus a proprietary warehouse.

**Acceptance criteria.**

- `notes/week-15/portability.md` shows the same aggregation run in Trino and in DuckDB (or Spark), with matching results.
- The DuckDB read points at the *same* Iceberg metadata/data in MinIO — no re-export, no copy.
- Your paragraph correctly frames why engine-portability is the lakehouse's core advantage over a vendor warehouse (you own the data and the open format; the compute is replaceable).
- Committed.

**Hint.** `INSTALL iceberg; LOAD iceberg;` in DuckDB, then `SELECT * FROM iceberg_scan('s3://warehouse/shop/orders_events', ...)` with the MinIO S3 credentials configured. If DuckDB's Iceberg support is limited for your table, Spark with the Iceberg runtime is the fallback — the point is "a second engine, same table, same answer."

**Estimated time.** 45 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 — Iceberg metadata tour | 40 min |
| 2 — Time-travel & expiry | 45 min |
| 3 — dbt rollup with gating tests | 1 h 0 min |
| 4 — Placement memo (headline) | 1 h 0 min |
| 5 — Federation right and wrong | 50 min |
| 6 — Engine portability | 45 min |
| **Total** | **~5 h 0 min** |

When you've finished all six, push your repo and make sure the `orders-lakehouse` [mini-project](./mini-project/README.md) is in the same workspace. This closes Phase 3's data arc — Postgres at scale (13), the change stream (14), the lakehouse (15). Then take the [quiz](./quiz.md) with your notes closed.

---

## Grading rubric (for the headline memo, Problem 4)

| Criterion | Weight | What earns full marks |
|---|---:|---|
| **Correct placements** | 25% | All five needs placed defensibly across Postgres / lakehouse / federate / dbt rollup. |
| **Four-axis reasoning** | 25% | Each placement justified by shape × volume × freshness × operational cost — not shape alone. |
| **Evidence, not opinion** | 25% | Every placement names a specific measurement; numbers from your own stack where possible. |
| **Calibration / trap-catching** | 15% | At least one reflex-trap flagged (Postgres query that looks like OLAP, or a "small" query that's an OLAP load at frequency); at least one query kept in Postgres. |
| **Memo quality** | 10% | Reads like a staff-review memo; includes a "what would change this placement" for at least one need. |

A memo that places everything in the lakehouse, or that decides by query shape alone without volume/freshness/frequency, caps at 60%. The whole skill is placing by the full framework, with evidence, and catching the traps.
