# Lecture 2 — Catalogs, Trino, Federation, and dbt

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can explain why a table format needs a catalog and choose one, describe Trino's architecture and run federated queries across Iceberg + Postgres + Kafka, write time-travel queries, build a dbt rollup model, and apply a defensible framework for deciding whether a given query stays in Postgres or moves to the lakehouse.

Lecture 1 gave you the data layer: columnar files, the Iceberg table format, snapshots and time-travel. This lecture gives you the *query* layer and the *transformation* layer that turn that data into answers. Four parts: (1) catalogs, (2) Trino and federation, (3) dbt, (4) the placement decision in full.

The thesis:

> **Trino is a query engine, not a database — it stores nothing and owns nothing. It reads Iceberg, Postgres, and Kafka through connectors and joins them in one SQL statement. That separation of compute (Trino) from storage (Iceberg on object storage) from the pointer-of-record (the catalog) is what makes the lakehouse swappable at every layer.**

---

## Part 1 — Catalogs: the atomic pointer

Lecture 1 said an Iceberg commit works by atomically swapping the catalog's pointer from the old table-metadata file to the new one. So the **catalog** is the component that holds, for each table, *which metadata file is current* — and provides the atomic compare-and-swap that makes commits ACID. Without a catalog, two writers could both think they have the latest table and clobber each other; the catalog is the referee.

You have three real choices in 2026:

- **The Iceberg REST catalog.** An open API (the REST Catalog spec) that any Iceberg client speaks. A small service (e.g., `tabulario/iceberg-rest`) implements it over a backing store. This is the modern default — engine-agnostic, simple, and what you'll use in the exercises.
- **Project Nessie.** A **git-like** catalog: it gives you *branches* and *tags* over your data. You can branch the `orders` table, write experimental transformations to the branch, validate them, and *merge* — or discard the branch with zero impact on production data. "Git for data" is not a metaphor; it's the actual model. Use it when you want isolated experimentation or auditable, mergeable data changes.
- **Hive Metastore.** The legacy option, inherited from the Hadoop era. Still widely deployed, still works, but it's a heavier service with a relational backend and none of Nessie's branching. You'll meet it in older shops; you won't choose it for greenfield.

The key idea to carry forward: **the catalog is small and swappable, and it's the only stateful coordination point.** The data is just files; the metadata is just files; the catalog is the one thing that says "this is the current truth," atomically. Point Trino, Spark, and PyIceberg at the *same* catalog and they all see the same tables, the same snapshots, the same current state. Point them at different catalogs and they see different worlds. The catalog *is* the namespace.

---

## Part 2 — Trino: the federated query engine

**Trino** (formerly PrestoSQL) is a distributed SQL engine designed to query data *where it lives*, across many sources, without first loading it into Trino. It stores nothing itself.

### 2.1 Architecture

- **Coordinator** — parses SQL, plans the query, schedules work, and combines results. One per cluster (clients connect here).
- **Workers** — execute the plan in parallel, each reading a slice of the data from the source.
- **Connectors** — plugins that teach Trino how to read a given source: the Iceberg connector, the Postgres connector, the Kafka connector, and dozens more. Each connector maps a source's tables into Trino's `catalog.schema.table` namespace.

```
                client
                   │ SQL
                   ▼
           ┌──────────────┐
           │ COORDINATOR  │  parse, plan, schedule
           └──────┬───────┘
        ┌─────────┼─────────┐
        ▼         ▼         ▼
     worker    worker    worker          (parallel execution)
        │         │         │
        ▼         ▼         ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐
   │ Iceberg │ │Postgres │ │  Kafka  │   (connectors → sources)
   └─────────┘ └─────────┘ └─────────┘
```

A Trino catalog (confusingly, a different "catalog" than the Iceberg metadata catalog — Trino calls each *connector configuration* a catalog) is a properties file:

```properties
# etc/catalog/iceberg.properties
connector.name=iceberg
iceberg.catalog.type=rest
iceberg.rest-catalog.uri=http://iceberg-rest:8181
fs.native-s3.enabled=true
s3.endpoint=http://minio:9000
s3.path-style-access=true
```

```properties
# etc/catalog/postgres.properties
connector.name=postgresql
connection-url=jdbc:postgresql://primary:5432/shop
connection-user=trino
connection-password=...
```

Now `iceberg.shop.orders_events` and `postgres.public.orders` are both queryable from the same Trino prompt.

### 2.2 Federation: one query, many sources

The superpower: **join across sources in a single SQL statement.** Suppose your *current* orders live in Postgres (OLTP, fresh) and your *historical* order events live in Iceberg (OLAP, cheap to scan), and you want "this customer's lifetime spend (history) alongside their current open-order count (live)":

```sql
SELECT
    h.customer_id,
    h.lifetime_cents / 100.0          AS lifetime_dollars,
    coalesce(o.open_orders, 0)        AS open_orders_now
FROM (
    -- historical aggregate from the LAKEHOUSE (cheap big scan)
    SELECT customer_id, sum(total_cents) AS lifetime_cents
    FROM iceberg.shop.orders_events
    WHERE op IN ('c','r')
    GROUP BY customer_id
) h
LEFT JOIN (
    -- live current state from POSTGRES (fresh, small)
    SELECT customer_id, count(*) AS open_orders
    FROM postgres.public.orders
    WHERE status = 'PLACED'
    GROUP BY customer_id
) o ON h.customer_id = o.customer_id;
```

One query, two engines' worth of data, no ETL to pre-join them. Trino pushes the aggregations down to each source where it can (predicate and aggregate pushdown), reads only what it needs, and joins the results.

### 2.2a The Kafka connector and querying the stream directly

Beyond Iceberg and Postgres, Trino's **Kafka connector** exposes Kafka topics as tables — so you can `SELECT` against the raw change stream itself. This sounds like it should replace the lander (why land into Iceberg if Trino can query Kafka directly?), and understanding why it *doesn't* sharpens the whole architecture.

You *can* point Trino at the `shop.public.orders` topic and query it. But:

- **Kafka is not columnar and not indexed.** Trino reading a Kafka topic reads the messages sequentially; there's no partition pruning, no column statistics, no predicate pushdown into a columnar layout. A big aggregation over a topic re-reads the whole topic every time. Kafka is a *log*, optimized for streaming consumption, not for repeated analytical scans.
- **Retention is bounded.** A topic holds data for its retention window (days, maybe), then it's gone. The lakehouse holds history indefinitely. "Revenue over the last two years" can't query a 7-day-retention topic.
- **No table semantics.** No time-travel, no schema evolution, no snapshots — the topic is a stream, not a table.

So the Kafka connector is genuinely useful for **inspecting the live stream** ("what's flowing right now?", debugging, a real-time peek) and occasionally joining recent stream data to a table. It is *not* the analytics substrate — that's Iceberg. The pattern is: **land the stream into Iceberg for analytics (durable, columnar, time-travelable), and use the Kafka connector to peek at the live edge.** This is the same land-vs-query-live decision as §2.3, applied to the stream itself, and it reinforces why Week 14's lander exists: the stream is for moving data, the lakehouse is for querying history.

### 2.3 When federation is the right tool — and when it isn't

Federation is powerful and it is *seductive*, so know its limits:

- **Use federation** for ad-hoc cross-source analysis, for joining a big historical fact (Iceberg) to a small live dimension (Postgres), and for exploration where building a pipeline isn't worth it.
- **Don't use federation** as your *production* serving path for a query that runs constantly, or one that scans a huge Postgres table on every run (you'll hammer the OLTP source — the exact cache-pollution problem from Lecture 1, now driven by Trino instead of a rogue analyst). For repeated heavy access, **land the data** into Iceberg via the change stream and query it there. Federation reads the source live; landing copies it once.
- **The rule:** federate to *discover* and to join across a boundary occasionally; *land and transform* (Part 3) for anything you run on a schedule. A query you run every five minutes against Postgres through Trino is a pipeline you should have built.

---

## Part 3 — dbt: transformations as tested, version-controlled SQL

You've landed raw `orders` change events in Iceberg. Raw events are not analytics — they're append-only rows with `op` flags and duplicates. Turning them into clean, trustworthy tables (a daily revenue rollup, a per-customer summary) is the **transformation layer**, and the standard tool for it in 2026 is **dbt**.

dbt's core idea: a transformation is a `SELECT` statement in a version-controlled file, and dbt handles turning it into a table or view, in dependency order, with tests. You don't write `CREATE TABLE AS`; you write the `SELECT`, declare how it should be materialized, and dbt builds it.

```sql
-- models/marts/daily_revenue.sql
{{ config(materialized='table') }}

SELECT
    date_trunc('day', created_at)        AS day,
    count(*)                             AS order_count,
    sum(total_cents) / 100.0             AS revenue_dollars
FROM {{ ref('stg_orders') }}             -- references another dbt model
WHERE op IN ('c', 'r')
GROUP BY 1
```

The pieces that make dbt more than "SQL in a file":

- **`ref()` and the DAG.** `{{ ref('stg_orders') }}` declares a dependency on another model. dbt builds the dependency graph and runs models in the right order — staging models first, then the marts built on them.
- **Materializations.** `view` (a saved query, recomputed each read), `table` (fully rebuilt on each run), `incremental` (only process *new* rows since the last run — essential for the rollup pattern so you don't reprocess two years of history every night), and `ephemeral` (inlined as a CTE).
- **Layering.** *Staging* models clean and standardize raw sources (dedup the change events, cast types, filter to the relevant `op`s). *Marts* build business-facing tables (the revenue rollup) on top of staging. This `staging → marts` discipline keeps transformations readable and reusable.
- **Tests.** dbt runs schema tests (`not_null`, `unique`, `accepted_values`) and custom data tests as a gate: a model that produces a null `day` or a duplicate key fails the build, before the bad table reaches a dashboard. This is the part that turns "some SQL someone ran once" into a *trustworthy* pipeline.

The incremental rollup is the canonical pattern: each night (or hour), dbt processes only the change events since the last run and merges them into the rollup, so the daily-revenue table stays fresh without rescanning history. Run via the `dbt-trino` adapter against your Iceberg lakehouse, the rollup *is* an Iceberg table, queryable by Trino, time-travelable, engine-portable.

> **Where dbt fits:** the raw CDC landing zone (Iceberg tables fed by the change stream) is the *source*; dbt's staging-and-marts models are the *transformation*; the marts are what dashboards and the finance team actually query. dbt does not move data between systems (that's the change stream's job) — it transforms data *within* the lakehouse, as tested, versioned, dependency-ordered SQL.

---

## Part 3b — The compute/storage separation, and why it changes the cost model

There's an economic point underneath the lakehouse architecture that's worth making explicit, because it changes how you reason about cost and scale.

In a traditional warehouse, **compute and storage are coupled**: the warehouse stores your data *and* runs your queries, often on the same nodes, and you pay for them together. Scaling query capacity meant scaling the whole system; idle compute still cost you because it was tied to the storage that had to stay up.

The lakehouse **separates them**. Storage is object storage (MinIO/S3) — cheap, durable, and *always there* whether or not anyone is querying. Compute is Trino — a stateless cluster you can scale up for a heavy batch job, scale down (or off) when idle, or run *multiple independent clusters* against the *same* data. The catalog and the data files don't care how many engines point at them.

The consequences reshape your cost and scaling decisions:

- **Idle storage is cheap.** Two years of order history sitting in Iceberg costs object-storage rates whether or not anyone queries it. You don't pay to keep cold data queryable, unlike a warehouse where the cluster must stay running.
- **Compute scales independently and elastically.** The finance team's month-end heavy run can spin up a big Trino cluster for an hour and tear it down; the merchandising dashboards run on a small always-on cluster. Same data, two right-sized compute footprints.
- **No compute, no compute cost.** Object storage with no queries running costs only storage. A warehouse you're not querying still bills you for the cluster.
- **Multiple engines, one copy.** Trino for interactive SQL, Spark for heavy batch, a future engine for whatever's next — all against the same Iceberg tables, no data duplication. The compute is a detail; the data is the asset.

This separation is *why* the "the engine is swappable" thesis has teeth: because compute is decoupled from storage, swapping or scaling the engine is a compute decision that doesn't touch your data. It's also why a lakehouse can be dramatically cheaper than a warehouse for workloads with lots of cold data and bursty query patterns — you stop paying for coupled capacity you're not using. When you justify a lakehouse to a finance-minded reviewer, this is the argument: you've decoupled the cost of *keeping* data from the cost of *querying* it, and you pay for each only when you use it.

## Part 4 — The placement decision, in full

You now have every piece to answer the week's headline question precisely. Given an analytical need, where does it run? The framework has four axes:

1. **Query shape.** Point lookup or single-row write → Postgres, always. Large scan / aggregation / wide historical join → lakehouse.
2. **Data volume.** Kilobytes-to-megabytes of hot current data → Postgres handles it. Gigabytes-to-terabytes, especially historical → lakehouse.
3. **Freshness tolerance.** Needs the absolute current value, transactionally → Postgres. Tolerates seconds-to-minutes of staleness (most analytics) → lakehouse (fed by the change stream, which has CDC lag).
4. **Operational cost.** Would this query pollute the OLTP cache, lag the replica, or hold locks the hot path needs? If yes, get it off Postgres regardless of the other axes.

Applied:

| Query | Shape | Volume | Freshness | → Placement |
|---|---|---|---|---|
| "Give me order 1001" | point read | tiny | current | **Postgres** |
| "Open orders count right now" | small agg | small | current | **Postgres** (indexed) |
| "Revenue by region by month, last 2 years" | big agg | large/historical | minutes OK | **Lakehouse** |
| "Cohort retention curve" | wide historical | large | hours OK | **Lakehouse** |
| "Customer lifetime spend + open orders" | cross-domain | mixed | mixed | **Federate** (Iceberg history + Postgres live) |
| "Daily revenue for the exec dashboard" | scheduled agg | large | daily | **Lakehouse + dbt** (incremental rollup) |

The senior judgment the homework tests: **don't reflexively lakehouse everything (a query an index fixes belongs in Postgres) and don't reflexively keep everything in Postgres (a 50M-row historical scan does not belong on your primary).** The decision is per-query, evidence-based — and the strongest answer often includes "this one federates" or "this one becomes a dbt rollup," not just "Postgres" or "lakehouse."

---

## Part 4a — How the change stream becomes a clean analytics table

It's worth tracing the full path from a raw `orders` change event to a trustworthy `daily_revenue` row, because every layer this week earns its place in that path.

1. **Land (raw).** The CDC lander (Week 14 / Exercise 3) appends every change event into `iceberg.shop.orders_events` — append-only, with `op`, `lsn`, and the row payload. This is the *raw* zone: faithful to the stream, including duplicates, deletes, and out-of-order arrivals. You never query this directly for business numbers; it's the source of truth for the transformation, not for the dashboard.

2. **Stage (clean).** A dbt staging model `stg_orders` reads the raw events and turns them into a clean current-state-or-event-level table: deduplicate by `lsn` so a re-landed event counts once, cast types, filter to the `op`s that matter (`c`, `r`, and the latest `u` per order), drop the operational columns the business doesn't care about. Staging is where the stream's messiness is absorbed so that everything downstream can trust the data.

```sql
-- models/staging/stg_orders.sql
{{ config(materialized='view') }}
WITH ranked AS (
    SELECT *, row_number() OVER (PARTITION BY order_id ORDER BY lsn DESC) AS rn
    FROM {{ source('raw', 'orders_events') }}
    WHERE op IN ('c', 'r', 'u')
)
SELECT order_id, customer_id, status, total_cents, created_at
FROM ranked
WHERE rn = 1                       -- the latest state of each order, deduped by lsn
```

3. **Mart (aggregate).** A dbt mart `daily_revenue` builds the business table on top of staging — the rollup the finance team actually queries. Because it `ref()`s `stg_orders`, dbt knows to build staging first. Because it's `incremental`, it only processes new data each run.

4. **Test (gate).** dbt tests on staging and the mart (`not_null` on `day`, `unique` on `day`, `accepted_values` on `status`) run as part of `dbt build`. A model that produces a duplicate day or a null key fails the build *before* the bad table reaches a dashboard. This is the step that makes the pipeline *trustworthy* rather than merely functional.

5. **Serve.** Dashboards, the finance team, and the federated queries read the *mart* — never the raw zone. The raw → staging → mart layering means the dashboard sees clean, tested, business-shaped data, and the messiness of the change stream is contained in the staging layer where it belongs.

This raw → staging → mart → test → serve flow is the standard analytics-engineering shape in 2026, and every piece of it is open: Iceberg tables, dbt models in version control, Trino as the engine, tests as the gate. There is no proprietary warehouse anywhere in the path — and yet you have warehouse-grade semantics. That is the lakehouse delivering on its promise.

## Part 5 — The federation-and-transformation decision tree

```
You have an analytical query. Where does it run, and how?
│
├─ Point read / transactional write?
│   └─ Postgres. Stop.
│
├─ Cheap with an index / small materialized rollup on fresh data?
│   └─ Postgres. Don't over-build a lakehouse for it.
│
├─ Runs on a SCHEDULE, large, historical?
│   └─ Land it in Iceberg (change stream) + transform with dbt (incremental). Query in Trino.
│
├─ Ad-hoc, joins a big historical fact to a small live dimension, runs occasionally?
│   └─ Federate in Trino (Iceberg + Postgres in one query). Don't build a pipeline.
│
└─ Runs constantly AND scans a big Postgres table live through Trino?
    └─ STOP — you're hammering the OLTP source. Land the data; query Iceberg instead.
```

Tape this next to the OLTP/OLAP placement tree from Lecture 1. Together they answer "where does this query run, and by what path."

---

## Part 3a — dbt is not a pipeline mover, and other boundaries

dbt is powerful and it is *specific*, and confusing what it does for what other tools do is a common architecture mistake. Three boundaries to keep straight.

**dbt transforms within a warehouse/lakehouse; it does not move data between systems.** dbt does not extract from Postgres, does not stream from Kafka, does not land files in S3. It assumes the data is *already* in the place it queries (your Iceberg lakehouse) and builds derived tables there with SQL. Getting the data *into* the lakehouse is the change stream's job (Weeks 14–15). The mental model: the **EL** (extract-load) is CDC/Debezium/the lander; the **T** (transform) is dbt. dbt is the T in "ELT," not the EL. A team that asks "how do I use dbt to get data out of Postgres?" has the boundary wrong — that's CDC's job.

**dbt models are SQL, not arbitrary code.** dbt is declarative: a model is a `SELECT` and dbt materializes it. It is not a place for imperative logic, calling APIs, or complex procedural transforms — those belong in the application or a stream processor. dbt's sweet spot is exactly the analytics transformation: clean, join, aggregate, test, in SQL, version-controlled. Trying to make dbt do non-SQL work fights the tool.

**dbt's tests gate the build; they are not monitoring.** dbt tests run at *build time* — a model with bad data fails `dbt build` and the bad table never ships. That's a gate. It is not continuous monitoring of a live system (that's Prometheus/Grafana territory, Week 17). The two are complementary: dbt tests catch bad *transformations* before they reach a dashboard; observability catches bad *behavior* in production. Don't expect dbt tests to page you about a live incident, and don't expect a Grafana alert to stop a bad model from building.

The reason these boundaries matter: a modern data platform has a clear division of labor — CDC moves and lands data, dbt transforms and tests it within the lakehouse, Trino queries it, observability watches it run. Each tool is excellent at its job and poor at the others'. The architect's skill is putting each concern in the right tool, which is the same OLTP/OLAP placement discipline (Part 4) applied to the transformation toolchain itself.

## Part 5a — Reading a Trino query plan, and the costs that bite

Trino makes a big-scan query *possible*; making it *fast* and *cheap* is its own skill, and the entry point is reading the plan. `EXPLAIN (TYPE DISTRIBUTED)` shows how Trino will split the work across workers and — critically — what it pushes down to each connector.

The three things you look for:

- **Partition pruning fired.** For an Iceberg table partitioned by `month(created_at)`, a query with a `created_at` range predicate should show Trino reading only the relevant partitions, not the whole table. If the plan scans every partition, your predicate isn't pruning (maybe it's on the wrong column, maybe a function wrapped `created_at` and defeated the transform) — the same lesson as Week 13's Postgres pruning, in a new engine.
- **Predicate and aggregate pushdown.** When you query the Postgres connector, Trino can push the `WHERE` and even aggregations *down to Postgres* so Postgres does the filtering and returns less data. The plan shows this as filter/aggregate nodes adjacent to the source scan. Pushdown is the difference between "Postgres returns 100 rows" and "Trino drags 50M rows across the network and filters them itself" — the latter being the federation anti-pattern from §2.3, now visible in the plan.
- **The join strategy.** Trino chooses broadcast joins (ship the small side to every worker) or partitioned joins (repartition both sides). A federated join of a big Iceberg fact to a small Postgres dimension should broadcast the small dimension. If it's repartitioning a huge table, your query will be slow and you may want to restructure it.

The costs that actually bite an analyst:

- **Scanning too many columns.** `SELECT *` defeats the column-store's entire advantage — you read every column when you needed three. Select only the columns you use; it's not style, it's the I/O difference Lecture 1 §1 was about.
- **Small files (again).** A table fragmented into thousands of tiny Parquet files makes Trino open thousands of files for one query. Compaction (Lecture 1 §5b) is a *query-performance* fix, not just a tidiness one.
- **No partitioning, or the wrong partitioning.** An unpartitioned 50M-row Iceberg table forces a full scan for every query. The partition transform must match how you query, exactly as in Postgres.
- **Federating a hot path.** Bears repeating: a query you run every few minutes against a live Postgres table through Trino hammers your OLTP source. Land it.

> **The senior habit:** before you complain that "Trino is slow," run `EXPLAIN (TYPE DISTRIBUTED)` and check that pruning fired, pushdown happened, and you're not reading columns or files you don't need. Nine times in ten the fix is in the query or the table layout, not the cluster size. This is the same discipline as reading `EXPLAIN (ANALYZE, BUFFERS)` in Postgres (Week 13) — the engine changed, the discipline didn't.

## Part 6 — Recap

You should now be able to:

- Explain why Iceberg needs a catalog (the atomic current-metadata pointer) and choose between the REST catalog, Nessie (git-for-data), and the Hive Metastore.
- Read a Trino distributed query plan for partition pruning, pushdown, and join strategy, and name the costs (wide scans, small files, bad partitioning, hot-path federation) that make queries slow.
- Describe Trino's coordinator/worker/connector architecture and configure Iceberg and Postgres connectors.
- Write a federated query that joins Iceberg historical data to live Postgres in one statement, and state when to federate vs when to land the data.
- Build a dbt model with `ref()`-driven dependencies, choose a materialization, layer staging into marts, and gate it with tests — and place dbt correctly relative to the CDC landing zone.
- Apply the four-axis placement framework (shape, volume, freshness, operational cost) to put any analytical query in the right tier, including "federate" and "dbt rollup" as answers.
- Read a Trino plan for pruning, pushdown, and join strategy, and reason about the compute/storage separation's cost model.

The judgment to carry out of this lecture: **a data platform is a set of placement decisions, and the architect's value is making each one by shape × volume × freshness × cost rather than by which tool is newest.** Trino can query anything, dbt can transform anything, the lakehouse can hold anything — and that flexibility is a trap if you reach for it reflexively. The point query stays in Postgres. The historical rollup lands in Iceberg and gets a dbt model. The occasional cross-source join federates. The constant heavy scan against the OLTP primary is the bug you catch. None of these is decided by enthusiasm; each is decided by the framework, backed by a measurement. Be the person who places queries by reasoning and you keep the hot path fast and the analysts unblocked at the same time — which is the entire job of Phase 3's data tier.

Next: the exercises stand up the whole lakehouse, write analytical SQL against it, and land your own change stream in Iceberg. Continue to [the exercises](../exercises/README.md).

---

## Part 7 — The shape of a 2026 open data platform

Stepping back, the pieces from this week and the two before assemble into a coherent, fully open data platform — worth seeing whole, because it's the architecture you'll defend at the capstone.

- **OLTP truth:** Postgres, partitioned and pooled (Week 13), serving the transactional hot path.
- **The spine:** the change stream — Debezium CDC reading the WAL (Week 14) — carrying every committed change exactly once it's processed idempotently.
- **The serving derivatives:** CQRS read models and caches (Weeks 14, 16) for low-latency, query-shaped reads.
- **The analytical home:** the lakehouse — Iceberg tables on object storage, fed by the stream, queried by Trino, transformed by dbt (Week 15) — for the big, historical, scan-heavy questions.
- **The glue:** an Iceberg catalog as the atomic pointer, and Trino federating across the lakehouse and the live OLTP source when a query genuinely spans both.

Not one proprietary product in that list. Postgres, Debezium, Kafka, Iceberg, Trino, dbt, MinIO — every layer open-source, every interface a published spec, every component swappable. That is the deliberate thesis of the whole Crunch Mesh data arc: you can build a platform with warehouse-grade analytics, transactional integrity, and reliable event flow, on foundations that no vendor owns and that outlive any single tool in the stack. When a reviewer asks "why these technologies?", the answer is not "they're popular" — it's "each one is the open, spec-defined, swappable choice for its layer, and together they keep us out of every lock-in trap a less deliberate platform falls into." Hold that whole picture; it's the data half of the architecture you defend at the end of the course.

And notice the recurring shape across all three Phase 3 data weeks: every tier has a *source of truth* and one or more *derived, eventually-consistent copies*, each tier has a *maintenance loop* that reclaims its garbage (Postgres autovacuum, Kafka retention/compaction, Iceberg snapshot-expiry and file-compaction), and every cross-tier decision is a *placement decision* made on shape, volume, freshness, and cost. Learn those three patterns — derived copies trail their source by a bounded amount, every store needs a reclaim loop, and data goes where the four axes send it — and the specific technologies become interchangeable details. That transferable judgment, not the particular stack, is what Phase 3 is really teaching.

## References

- *Trino — overview & concepts*: <https://trino.io/docs/current/overview/concepts.html>
- *Trino — Iceberg connector*: <https://trino.io/docs/current/connector/iceberg.html>
- *Trino — Postgres connector* (federation): <https://trino.io/docs/current/connector/postgresql.html>
- *Iceberg REST catalog spec*: <https://github.com/apache/iceberg/blob/main/open-api/rest-catalog-open-api.yaml>
- *Project Nessie*: <https://projectnessie.org/>
- *dbt — materializations*: <https://docs.getdbt.com/docs/build/materializations>
- *dbt-trino adapter*: <https://github.com/starburstdata/dbt-trino>
- *Trino — Kafka connector*: <https://trino.io/docs/current/connector/kafka.html>
- *Trino — Iceberg time travel & metadata tables*: <https://trino.io/docs/current/connector/iceberg.html#metadata-tables>
- *dbt — incremental models*: <https://docs.getdbt.com/docs/build/incremental-models>
- *dbt — data tests*: <https://docs.getdbt.com/docs/build/data-tests>
- *Iceberg — partitioning & hidden partitioning*: <https://iceberg.apache.org/docs/latest/partitioning/>
- *Trino — Postgres connector* (federation): <https://trino.io/docs/current/connector/postgresql.html>
