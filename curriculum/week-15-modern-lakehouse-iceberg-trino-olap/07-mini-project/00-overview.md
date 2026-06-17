# Mini-Project — `orders-lakehouse`: CDC → Iceberg, a dbt Rollup, and a Placement Report

> Build the full lakehouse half of the syllabus lab: stand up MinIO + an Iceberg catalog + Trino, land your Week 14 `orders` change stream into an Iceberg table, transform it into a clean daily/hourly revenue rollup with dbt, demonstrate time-travel and engine-portability, and write a **placement report** that justifies — with measurements — which analytical queries you moved off Postgres and why.

This is the artifact that proves you can close the OLTP/OLAP loop: take the change stream you've built over two weeks, land it in an open lakehouse, transform it with tested SQL, and *defend the architecture* with evidence rather than enthusiasm. After this week, "we have a lakehouse" is not a slide — it's a running stack with a rollup a dashboard could query, a time-travel demo, and a report that shows the OLTP primary is faster *because* the analytics moved.

**Estimated time:** ~12 hours, split across Thursday, Friday, and Saturday in the suggested schedule.

**Builds on and closes:** This consumes the Week 14 `orders-cdc` change stream directly — the lakehouse is its third consumer, alongside the read model and the event store. It closes Phase 3's data arc: Postgres at scale (13), the change stream (14), the lakehouse (15). The placement report is the same judgment the capstone's `analytics-service` needs.

---

## What you will build

A repository `orders-lakehouse` with five deliverables:

1. **`infra/`** — a `compose.yml` bringing up MinIO, an Iceberg catalog (REST catalog or Nessie), and Trino, with the Trino Iceberg and Postgres connectors configured.
2. **`landing/`** — a consumer (PyIceberg, from Exercise 3) that lands the `orders` change stream into an Iceberg table `shop.orders_events`, partitioned by `month(created_at)`.
3. **`transform/`** — a dbt project (using `dbt-trino`) with a `staging` model that cleans/dedups the raw change events and a `marts` model that produces a daily (and hourly) revenue rollup, with at least two dbt tests gating the build.
4. **`demos/`** — scripts proving the two lakehouse-only powers: a **time-travel** query showing the table at an earlier snapshot, and an **engine-portability** check reading the same table from a second engine (DuckDB or Spark) and matching Trino's answer.
5. **`REPORT.md`** — the placement report: the architecture diagram, the rollup, the demos' output, and a measured justification for each analytical query you moved off Postgres.

By the end you have a public repo of ~500–700 lines (infra + Python + SQL + dbt) demonstrating a complete, open, defensible lakehouse — a strong portfolio piece.

---

## Why a placement report and not just "we built a lakehouse"

You could stand up the stack, land the data, build a rollup, and call it done. Don't. A lakehouse with no justification for *what moved to it and why* is cargo-culting — and a reviewer will ask. A real report:

- **Shows the primary got faster.** The point of moving analytics off Postgres is that the hot path stops competing with big scans. Measure a point read's latency (or the buffer-cache hit ratio) with the analytical query running on Postgres vs running in the lakehouse. The improvement is the justification.
- **Justifies each move with the framework.** For each query you moved, state shape × volume × freshness × operational cost. "We moved the monthly rollup because it scans 50M rows, tolerates a day of staleness, and was evicting hot order rows from the OLTP cache" is a defensible sentence. "We moved it to the lakehouse because lakehouses are good" is not.
- **Names what stayed.** A strong report also lists queries you *kept* in Postgres and why (Q2-style indexed counts), proving you placed by reasoning, not by reflex.
- **Proves the contract.** The time-travel and second-engine demos prove you built an Iceberg *table* (the open contract), not just a Trino-specific pile of Parquet.

This is the senior-shop convention in 2026: a data-platform change ships with a placement report and a measured before/after, not a "we adopted Iceberg" announcement.

---

## Repository layout

```
orders-lakehouse/
├── README.md
├── infra/
│   ├── compose.yml                 # minio + iceberg catalog + trino
│   └── trino/catalog/
│       ├── iceberg.properties
│       └── postgres.properties     # for federation + before/after measurement
├── landing/
│   └── land_stream.py              # CDC -> Iceberg (PyIceberg)
├── transform/                      # the dbt project (dbt-trino)
│   ├── dbt_project.yml
│   ├── profiles.yml
│   └── models/
│       ├── staging/stg_orders.sql  # dedup/clean the raw change events
│       ├── marts/daily_revenue.sql # the incremental rollup
│       └── marts/schema.yml        # dbt tests (not_null, unique, accepted_values)
├── demos/
│   ├── time_travel.sql             # query an earlier snapshot
│   └── portability_check.py        # read the table from DuckDB, compare to Trino
└── REPORT.md
```

---

## Deliverable 1 — the lakehouse infrastructure

Reuse the Exercise 1 compose (MinIO + Iceberg REST catalog + Trino). Add a **Postgres connector** to Trino (`postgres.properties`) pointing at your Week 13/14 Postgres, so you can (a) federate and (b) measure the OLTP primary before/after. A `make up` must bring the whole stack up and confirm Trino can reach both Iceberg and Postgres (`SHOW CATALOGS`, `SHOW SCHEMAS FROM postgres`).

---

## Deliverable 2 — the landing consumer

The PyIceberg consumer from Exercise 3, productionized:

- Creates `iceberg.shop.orders_events` partitioned by `month(created_at)` if absent.
- Consumes the `orders` change stream and appends events as rows (batched into reasonable snapshots — not one snapshot per row, which creates small-file bloat).
- Is a **separate consumer group** from the Week 14 read model and event store, proving one stream feeds N consumers.
- Handles deletes (`op=d`) and tombstones without crashing.
- Is resumable: restarting resumes from its committed offset.

> **Small-file warning:** appending one row per snapshot creates thousands of tiny Parquet files and tanks query performance. Batch appends, and document (or implement) Iceberg's `rewrite_data_files` compaction as the maintenance story. A reviewer *will* check your file count.

---

## Deliverable 3 — the dbt transformation

A `dbt-trino` project with two layers:

- **`stg_orders`** (staging) — reads `iceberg.shop.orders_events`, deduplicates by the change LSN (so a re-landed event counts once), casts types, and filters to the relevant `op`s. Materialized as a view or incremental table.
- **`daily_revenue`** (mart) — an **incremental** model that produces `day, order_count, gross_dollars, fulfilled_dollars`, processing only new events since the last run (not rescanning all history every build). Materialized as an Iceberg table.

At least **two dbt tests** in `schema.yml`: e.g., `not_null` on `day`, `unique` on `day`, and `accepted_values` on a status field in staging. `dbt build` must fail if the data violates them — demonstrating the "tested transformation" property.

```sql
-- models/marts/daily_revenue.sql (sketch)
{{ config(materialized='incremental', unique_key='day') }}
SELECT
    date_trunc('day', created_at)                                  AS day,
    count(*)                                                       AS order_count,
    sum(total_cents) / 100.0                                       AS gross_dollars,
    sum(CASE WHEN status IN ('SHIPPED','DELIVERED') THEN total_cents ELSE 0 END) / 100.0
                                                                   AS fulfilled_dollars
FROM {{ ref('stg_orders') }}
{% if is_incremental() %}
  WHERE created_at > (SELECT coalesce(max(day), DATE '1970-01-01') FROM {{ this }})
{% endif %}
GROUP BY 1
```

---

## Deliverable 4 — the demos

Two scripts that prove the lakehouse is real:

- **`time_travel.sql`** — captures a snapshot ID, lands more data, then queries `FOR VERSION AS OF` the earlier snapshot and shows a *different* (earlier) result than current. Prove the snapshot history is queryable.
- **`portability_check.py`** — reads `shop.orders_events` (or `daily_revenue`) from a **second engine** — DuckDB's Iceberg extension is the easiest — and asserts the result matches Trino's. This is the thesis: the table is the contract, the engine is swappable.

---

## Deliverable 5 — the placement report

`REPORT.md` must contain:

- An **architecture diagram**: Postgres → Debezium → Kafka → {read model, event store, **Iceberg landing**} → dbt rollup → Trino/dashboards.
- The **rollup output**: a sample of `daily_revenue`, and the `dbt build` output showing tests passing.
- The **time-travel** and **portability** demo outputs.
- The **measured before/after**: a point-read latency (or buffer-cache hit ratio) on the OLTP primary with the monthly rollup running *on Postgres* vs running *in the lakehouse*. The improvement is your justification.
- A **placement table**: for at least four representative analytical queries, where each runs (Postgres / lakehouse / federate / dbt rollup) and the four-axis reason — including at least one query you deliberately **kept** in Postgres and why.
- One **honest limitation**: e.g., "the rollup is fresh only to within the CDC lag; for a true-real-time count we still hit Postgres."

---

## Rules

- **You may** reuse the Exercise 1 compose, the Exercise 3 lander, and the Exercise 2 queries as starting points.
- **You must** land data in **batches** (no one-row snapshots) and address small-file compaction at least in the report.
- **You must** include the **engine-portability** demo (a second engine reading the same table) — it's the load-bearing proof that you built a lakehouse, not a Trino silo.
- **You must** measure the OLTP before/after, not assert it.
- Iceberg + Trino + dbt-trino + MinIO, all open-source. PyIceberg for landing. Python 3.12.
- The whole thing comes up and the demos run from **documented commands** (ideally `make up && make demo`).

---

## Acceptance criteria

- [ ] A public GitHub repo named `c22-week-15-orders-lakehouse-<yourhandle>`.
- [ ] `make up` (or documented) brings up MinIO + catalog + Trino; `SHOW CATALOGS` shows both `iceberg` and `postgres`.
- [ ] The lander populates `iceberg.shop.orders_events` (partitioned by month), in batches, as a separate consumer group; deletes/tombstones handled.
- [ ] `dbt build` produces `stg_orders` and an **incremental** `daily_revenue`, and at least two dbt **tests pass** (and demonstrably fail when the data is bad).
- [ ] The **time-travel** demo shows an earlier snapshot's result; the **portability** demo reads the same table from a second engine and matches Trino.
- [ ] `REPORT.md` has the diagram, rollup, demos, the **measured OLTP before/after**, the placement table (with at least one query kept in Postgres), and one honest limitation.
- [ ] Committed and pushed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Lakehouse stand-up** | 15 | MinIO + catalog + Trino + both connectors up from one command; Iceberg table partitioned by month. |
| **Landing the stream** | 15 | Batched appends (no small-file explosion); separate consumer group; deletes/tombstones handled; resumable. |
| **dbt transformation** | 20 | Staging dedup; **incremental** rollup that doesn't rescan history; ≥2 tests that pass and demonstrably gate the build. |
| **The two demos** | 20 | Time-travel returns an earlier state; engine-portability reads the same table from a second engine and matches. |
| **The placement report** | 25 | Diagram; measured OLTP before/after; placement table with four-axis reasoning **and** a query kept in Postgres; one honest limitation. |
| **Docs & hygiene** | 5 | One-command bring-up; small-file/compaction addressed; sensible commits. |

**90+** is portfolio-grade and closes Phase 3's data arc cleanly. **70–89** works but the report asserts rather than measures, or the portability demo is missing. **Below 70** means you built a Trino-and-Parquet pile, not a defensible lakehouse — no second-engine proof, or no justification for what moved. Fix that first; the whole point is the *contract* and the *reasoning*, not the stack.

---

## Stretch goals

- **Nessie branching.** Swap the REST catalog for Nessie, branch the `orders_events` table, build an experimental rollup on the branch, validate, and merge — git-for-data, documented as a workflow.
- **CDC-to-Iceberg MERGE.** Instead of append-only landing, use Iceberg `MERGE INTO` to keep only the latest state of each order (upsert from the change stream). Compare query performance and file count to the append approach, and discuss the compaction tradeoff.
- **Federated serving.** Build the "customer lifetime value + current loyalty tier" federated query (Iceberg history + Postgres live) and put it behind a tiny API, with a note on why this one federates rather than lands.
- **Lag SLO.** Instrument end-to-end freshness (commit in Postgres → row queryable in Iceberg) and set an SLO; the report fails if median freshness exceeds your target.

---

## How this connects to the rest of C22

- **Weeks 13–14** produce the partitioned `orders` table and the change stream this lakehouse consumes; the lander is the third consumer of that stream.
- **Week 16 (caching)** is the next "where does a read go" decision — the same placement instinct, pointed at a cache tier.
- **The capstone** has an `analytics-service` (Iceberg-on-Trino daily/hourly rollups); this mini-project *is* that service, built four weeks early. Keep the repo and fold it in.

## What "defensible" means when you present this

When you walk a reviewer through this project, the difference between a pass and a portfolio piece is whether you can answer three questions without hesitating:

- **"Why did this query move off Postgres?"** Your answer is the measured before/after — a point-read latency or cache-hit ratio that improved when the analytical scan left the primary — plus the four-axis reason (shape, volume, freshness, operational cost). Not "lakehouses are good." A number and a framework.
- **"Prove it's a real Iceberg table and not a Trino silo."** Your answer is the engine-portability demo: the same table read from a second engine, same result, no copy. This is the one demo that proves you understood the week's thesis rather than just wiring up Trino.
- **"What happens when the stream re-delivers, or a column is added, or the table fills with small files?"** Your answer is: the lander dedups by LSN; Iceberg schema evolution is a cheap metadata change; and you've scheduled `rewrite_data_files` compaction. These are the operational realities that separate a demo from a system someone could run.

If you can answer those three, you have built a lakehouse you understand, not one you copied. That understanding — *where data should live and why, with evidence* — is the single most valuable thing Phase 3 teaches, and this mini-project is where you prove you have it.

Keep the repo. The capstone's `analytics-service` is this project, hardened: the same Iceberg landing, the same dbt rollups, the same placement reasoning, defended in front of two external reviewers. Everything you build here, you build once and reuse.

When you've finished, push the repo and take the [quiz](../05-quiz.md).
