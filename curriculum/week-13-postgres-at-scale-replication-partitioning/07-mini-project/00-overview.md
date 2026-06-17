# Mini-Project — `orders-at-scale`: A Defensible Before/After Partitioning Benchmark

> Build a repeatable benchmark harness that loads 50 million synthetic `orders` rows into a flat table and into a monthly-partitioned table, runs a fixed query suite against both, and produces a **defensible before/after report** — with `EXPLAIN` plans, latency percentiles, and pgBouncer pooling numbers — that you could put in front of a staff engineer to justify "we partitioned `orders`."

This is the artifact that kills the week's anti-pattern: claiming a storage change "made things faster" with no measurement, no plan, and no honest accounting of where it *didn't* help. After this week, a partitioning decision is a decision made **with evidence** — a benchmark you can re-run, a report a reviewer can challenge, and a clear statement of which queries got faster, which were unchanged, and why.

**Estimated time:** ~12 hours, split across Thursday, Friday, and Saturday in the suggested schedule.

**Compounds forward:** The `orders` schema and the partition lifecycle you build here are the **same table Debezium streams in Week 14** and the same data Trino queries in Week 15. The benchmark harness becomes your reference for "is this query fast enough to stay in Postgres, or does it belong in the lakehouse?" — the exact OLTP/OLAP boundary question of Week 15. Build it well now; you'll lean on it twice more.

---

## What you will build

A small repository `orders-at-scale` with four deliverables:

1. **`schema/`** — the SQL that builds both a flat `orders` table and a `RANGE`-partitioned `orders` table (monthly, with a `pg_partman`-style create-ahead/expire-behind lifecycle), plus the indexes each needs.
2. **`load/loader.py`** — a generator that loads 50M synthetic rows efficiently (via `COPY`, not `INSERT`), spread realistically across ~24 months, into either target.
3. **`bench/run_suite.py`** — a benchmark runner that executes a fixed suite of representative queries against a target, captures latency percentiles (p50/p95/p99) and the `EXPLAIN (ANALYZE, BUFFERS)` plan of each, optionally through pgBouncer, and emits machine-readable results.
4. **`REPORT.md`** — the human deliverable: a before/after comparison with the numbers, the plans, and an honest "what got faster, what didn't, and what I'd do next" section.

By the end you have a public repo of ~400–600 lines (SQL + Python) that any future project can clone to answer "should we partition this table?" with data instead of opinion.

---

## Why a benchmark and not a vibe

You could partition `orders`, run one query, eyeball it, and declare victory. Don't. A real before/after benchmark gives you:

- **A control.** The flat table is the baseline. Without it, "47 ms" means nothing — fast or slow compared to *what*?
- **Percentiles, not averages.** A mean hides the tail. The p99 is what your users feel and what your SLO is written against (Week 18). Report p50/p95/p99 or you've measured the wrong thing.
- **The plan, not just the time.** A query can be fast for the wrong reason (it's all in cache) or slow for a fixable reason (it's not pruning). `EXPLAIN (ANALYZE, BUFFERS)` is the only honest record of *what the database actually did*.
- **An honest negative result.** The status-filter query (no partition-key predicate) will **not** get faster from partitioning — and saying so, with the plan that proves it, is what makes the report defensible rather than marketing.

This is the senior-shop convention in 2026: a storage change ships with a benchmark, a report, and a stated negative result.

---

## Repository layout

```
orders-at-scale/
├── README.md
├── schema/
│   ├── 01_flat.sql            # the baseline flat orders table + indexes
│   ├── 02_partitioned.sql     # the RANGE-partitioned orders + partitions
│   └── 03_partition_mgmt.sql  # create-ahead / detach-old lifecycle (pg_partman or hand-rolled)
├── load/
│   └── loader.py              # COPY-based 50M-row generator, targets either table
├── bench/
│   ├── queries.sql            # the fixed query suite (commented, one per pattern)
│   └── run_suite.py           # runs the suite, captures percentiles + plans
├── results/
│   ├── flat.json              # emitted by run_suite.py
│   └── partitioned.json
└── REPORT.md                  # the human deliverable
```

---

## Deliverable 1 — the schemas

Both tables share columns; only the storage differs.

`schema/01_flat.sql` — the baseline:

```sql
CREATE TABLE orders_flat (
    order_id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint      NOT NULL,
    status      text        NOT NULL,
    total_cents bigint      NOT NULL,
    created_at  timestamptz NOT NULL
);
CREATE INDEX ON orders_flat (created_at);
CREATE INDEX ON orders_flat (customer_id);
```

`schema/02_partitioned.sql` — the partitioned version (partition key in the PK):

```sql
CREATE TABLE orders (
    order_id    bigint      GENERATED ALWAYS AS IDENTITY,
    customer_id bigint      NOT NULL,
    status      text        NOT NULL,
    total_cents bigint      NOT NULL,
    created_at  timestamptz NOT NULL,
    PRIMARY KEY (order_id, created_at)
) PARTITION BY RANGE (created_at);
-- Create 24 monthly partitions (2025-01 .. 2026-12) + a DEFAULT.
-- Index created_at and customer_id on the parent; they cascade.
```

Your `03_partition_mgmt.sql` must implement the lifecycle: either configure `pg_partman` to create next month's partition ahead of time and detach partitions older than your retention window, or hand-roll a function + a scheduled call that does the same. **Document which you chose and why.**

---

## Deliverable 2 — the loader

50M `INSERT` statements would take hours and bloat the WAL. Use `COPY`. The loader streams generated rows into a `COPY ... FROM STDIN` so the server ingests them at disk speed.

Requirements:

- Generates ~50M rows spread across ~24 months (so partition pruning has something to prune), with realistic `customer_id` cardinality (e.g., 1M distinct customers) and a realistic `status` distribution.
- Targets either `orders_flat` or `orders` by a `--target` flag.
- Uses `COPY` via `psycopg`'s `cursor.copy()` — not row-by-row inserts.
- Prints throughput (rows/sec) and total elapsed, so you can compare ingest cost of flat vs partitioned (insert routing has a small cost — measure it).
- Is restartable / idempotent enough that a re-run doesn't silently double-load.

```python
# Sketch of the COPY hot loop (fill in generation + batching):
with conn.cursor() as cur:
    with cur.copy(
        "COPY orders (customer_id, status, total_cents, created_at) FROM STDIN"
    ) as copy:
        for row in generate_rows(n=50_000_000):
            copy.write_row(row)
```

---

## Deliverable 3 — the benchmark runner

`bench/queries.sql` holds the fixed suite — at minimum these patterns, each labeled:

- **Q1 — single-month range** (`created_at >= ... AND < ...`): the query partitioning is *supposed* to help. Expect pruning to one partition.
- **Q2 — recent-customer history** (`customer_id = ? AND created_at >= ?`): pruning + index.
- **Q3 — status filter, no time bound** (`status = 'SHIPPED'`): the query partitioning does *not* help. Expect a scan of every partition. This is your honest negative result.
- **Q4 — monthly revenue rollup** (`GROUP BY date_trunc('month', created_at)`): a partition-wise aggregate candidate.
- **Q5 — point lookup by primary key**: should be equally fast on both (sanity control).

`bench/run_suite.py` must:

1. Take `--target {flat,partitioned}`, `--dsn`, and `--via-pgbouncer` flags.
2. Warm the cache (run each query once, discarded) then time **N=50** runs of each query, recording p50/p95/p99 latency.
3. Capture the `EXPLAIN (ANALYZE, BUFFERS)` plan of each query once.
4. Emit a `results/<target>.json` with, per query: the percentiles, whether pruning fired (parse the plan for the number of partitions scanned), and the plan text.
5. Print a summary table to the terminal.

The pruning check is the load-bearing assertion: for Q1, the partitioned run must scan **one** partition and the flat run scans the whole heap; the report must show that difference.

---

## Deliverable 4 — the report

`REPORT.md` is what a reviewer reads. It must contain:

- A **methodology** paragraph: hardware, Postgres version, row count, N, warm-cache policy, pgBouncer config.
- A **results table**: each query, flat p50/p95/p99 vs partitioned p50/p95/p99, and the delta.
- For Q1, the **two `EXPLAIN` plans side by side** showing the flat full scan vs the single-partition prune.
- The **honest negative result**: Q3 did not improve (or got marginally worse from per-partition overhead), with the plan that proves it, and one sentence on why (no partition-key predicate ⇒ no pruning).
- A **pgBouncer section**: throughput direct-to-Postgres vs through transaction-mode pgBouncer at a high client count, and the connection count where direct collapses.
- A **"what I'd do next"** paragraph: e.g., "Q3 wants a separate index or a different partition key; the monthly rollup (Q4) is a candidate to push to the lakehouse in Week 15."

---

## Rules

- **You may** read the Postgres docs, the lecture notes, `pg_partman` docs, and any open-source benchmark harness for inspiration.
- **You must not** load the 50M rows with row-by-row `INSERT`. Use `COPY`. (A reviewer will ask, and "it took 40 minutes" is the wrong answer.)
- **You must** report percentiles, not just means, and you **must** include at least one honest negative result.
- Python 3.12, `psycopg` v3, Postgres 16. No ORM — raw SQL, because you're measuring the database, not a framework.
- The benchmark must be **re-runnable**: `make bench` (or a documented one-liner) reproduces `results/*.json` from scratch.

---

## Acceptance criteria

- [ ] A public GitHub repo named `c22-week-13-orders-at-scale-<yourhandle>`.
- [ ] `schema/` builds both tables; `02_partitioned.sql` has the partition key in the PK and 24 monthly partitions + default.
- [ ] `03_partition_mgmt.sql` creates a future partition and detaches an old one, with the mechanism documented.
- [ ] `loader.py` loads 50M rows via `COPY` and prints throughput; a re-run does not double-load.
- [ ] `run_suite.py` emits `results/flat.json` and `results/partitioned.json` with p50/p95/p99 and plan text per query, and detects whether pruning fired for Q1.
- [ ] `REPORT.md` contains the methodology, the results table, the side-by-side Q1 plans, the honest Q3 negative result, and the pgBouncer numbers.
- [ ] `grep`-clean of row-by-row inserts in the loader (the `COPY` rule).
- [ ] Committed and pushed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Schema & partition lifecycle** | 20 | Both tables correct; partition key in PK; 24 partitions + default; a working create-ahead/detach-old lifecycle, documented. |
| **Loader efficiency** | 15 | `COPY` not `INSERT`; 50M rows load in a sane time; throughput reported; idempotent re-run. |
| **Benchmark rigor** | 25 | Warm-cache policy; N≥50; p50/p95/p99 captured; plans captured; pruning detection works for Q1. |
| **The report** | 25 | Methodology stated; results table complete; Q1 plans side-by-side; **honest negative result** for Q3 present and explained; pgBouncer collapse point measured. |
| **Reproducibility** | 10 | One command re-runs the whole benchmark from scratch; results are deterministic in shape. |
| **Docs & hygiene** | 5 | Clear README; no `build/`/`results/` junk beyond the emitted JSON; sensible commits. |

**90+** is portfolio-grade and the reference you cite in Weeks 14–15. **70–89** works but is missing the negative result or the percentiles. **Below 70** means the benchmark isn't defensible — it has a mean with no plan, or no control table. Fix that first; a benchmark you can't defend is worse than no benchmark.

---

## Stretch goals

- **Citus comparison.** Stand up a single-node Citus, convert `orders` to a distributed table sharded by `customer_id`, run the same suite, and add a third results column. Document one query that got faster and one (a cross-shard aggregate) that got slower.
- **The cache-cold truth.** Run the suite once cache-cold (`pg_prewarm` off, restart, drop OS cache) and once cache-warm. Report both. The gap is what a cold start or a cache eviction does to your tail latency.
- **pg_repack mid-benchmark.** Bloat the partitioned table, run the suite, `pg_repack` one partition, re-run, and quantify the bloat tax on query latency.
- **CI gate.** A GitHub Actions workflow that spins up Postgres, loads a *small* (1M-row) dataset, runs the suite, and fails if Q1 stops pruning — so a future schema change that breaks partition pruning is caught on a PR.

---

## How this connects to the rest of C22

- **Week 14 (CDC/CQRS)** streams this exact `orders` table via Debezium. Your partition lifecycle is what keeps the source table healthy while the WAL is being decoded.
- **Week 15 (lakehouse)** asks the OLTP/OLAP boundary question directly: your Q4 monthly rollup is the candidate to push to Iceberg+Trino, and this benchmark is how you justify the move.
- **Week 18 (reliability)** writes SLOs against p99 latency — the percentiles you learned to report here are the same ones the SLO is defined on.

When you've finished, push the repo and take the [quiz](../05-quiz.md).
