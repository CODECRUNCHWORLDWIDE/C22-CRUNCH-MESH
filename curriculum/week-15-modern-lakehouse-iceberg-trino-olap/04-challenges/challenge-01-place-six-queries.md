# Challenge 1 — Place Six Queries on the OLTP/OLAP Boundary

**Time estimate:** ~90 minutes.

## Problem statement

You are the data architect for the marketplace. Six teams each bring you a query and ask "where should this run?" Your job — the real job — is to place each on the correct tier (Postgres OLTP, lakehouse OLAP, federated, or a dbt rollup), back the call with the **four-axis framework** (query shape × data volume × freshness tolerance × operational cost) and at least one **measurement**, and defend each call against a skeptic. Two of the six are *traps* designed to catch reflexive answers — find them.

This mirrors the real skill: you rarely design a data platform on a whiteboard from scratch. You field a stream of "where should this query live?" questions, and a wrong answer to any one of them either slows the hot path or builds infrastructure nobody needed.

## The six queries

You have a Postgres OLTP primary with the `orders` table (~50M rows, partitioned by month, from Week 13) and an Iceberg lakehouse fed by the change stream (from Weeks 14–15).

1. **`Q1` — "Load order 1001 for the order-detail page."**
   `SELECT * FROM orders WHERE order_id = 1001;` — runs thousands of times a minute, must return in single-digit milliseconds.

2. **`Q2` — "Count of open ('PLACED') orders right now, for the ops dashboard."**
   `SELECT count(*) FROM orders WHERE status = 'PLACED';` — polled every 10 seconds, needs the current value.

3. **`Q3` — "Monthly gross revenue by region for the last 24 months, for the board deck."**
   A `GROUP BY region, date_trunc('month', created_at)` over two years of orders, run a few times a week, a day-old number is fine.

4. **`Q4` — "Per-customer lifetime value joined to their current loyalty tier."**
   Lifetime value is a sum over all historical orders; loyalty tier is a live, frequently-updated column in a small Postgres `customers` table. Run on demand by support agents.

5. **`Q5` — "12-month cohort retention curve" — for every signup-month cohort, what fraction placed an order in each subsequent month.**
   A wide, multi-self-join historical analysis over all orders and customers, run weekly by the growth team. Hours-old data is fine.

6. **`Q6` — "Top 100 products by units sold in the last 7 days, refreshed every 5 minutes for the merchandising homepage."**
   An aggregation over the last week of `order_items` (~3M rows/week), refreshed constantly, drives a high-traffic page; a few minutes stale is acceptable.

## Your task

For **each query Q1–Q6**, produce a placement with these parts:

1. **Placement** — exactly one of: *Postgres*, *Lakehouse (Iceberg+Trino)*, *Federate (Trino across both)*, *dbt incremental rollup in the lakehouse*. (A query may be "Postgres with an index" or "lakehouse via a dbt rollup" — be specific.)
2. **Four-axis justification** — shape, volume, freshness, operational cost. One line each.
3. **The measurement** — the specific thing you'd run to confirm the call: an `EXPLAIN` plan, a `pg_stat_statements` total-time entry, a buffer-cache-hit-ratio check, a Trino query time, a CDC-lag reading. Name it.
4. **The skeptic's objection** — state the strongest argument *against* your placement and rebut it in one sentence.

Then, explicitly:

5. **Identify the two traps** and explain why each is a trap.

## Acceptance criteria

- [ ] A file `challenge-01-placements.md` with a section per query containing parts 1–4.
- [ ] Your placements are defensible:
  - **Q1** → **Postgres** (point read; index on PK; the textbook OLTP query).
  - **Q2** → **Postgres** (small, current, fixed by an index/partial index; *the trap that looks like analytics but isn't*).
  - **Q3** → **Lakehouse** (large historical aggregation; would pollute the OLTP cache; freshness-tolerant).
  - **Q4** → **Federate** (historical sum from Iceberg + live tier from Postgres in one Trino query).
  - **Q5** → **Lakehouse** (wide historical multi-join; classic OLAP; never on the primary).
  - **Q6** → **dbt incremental rollup in the lakehouse** (*the trap that looks like a small Postgres query but, refreshed every 5 min over 3M rows on a high-traffic page, will hammer the primary*).
- [ ] Each placement cites a concrete **measurement**, not just an assertion.
- [ ] You correctly name **Q2 and Q6 as the traps** and explain both: Q2 *looks* like an analytical aggregation but is a cheap indexed count that belongs in Postgres; Q6 *looks* like a small recent-window query but its frequency × volume × the fact it drives a hot page makes it an OLAP load that must come off the primary.
- [ ] Committed to your Week 15 repo under `challenges/challenge-01/`.

## The traps (read after a first attempt)

**Trap Q2 — "it's an aggregation, so lakehouse."** No. A `count(*) WHERE status='PLACED'` is small, needs the *current* value, and is fixed dead by a partial index (`CREATE INDEX ON orders (status) WHERE status='PLACED'`) or a maintained counter. Pushing it to the lakehouse buys you nothing and *loses* you freshness (the change stream has CDC lag). The reflex "aggregation → OLAP" is wrong when the aggregation is small, current, and indexable. Measure it: `EXPLAIN` shows an index-only scan in microseconds. Keep it in Postgres.

**Trap Q6 — "it's just the last 7 days, that's small, keep it in Postgres."** No. It's "small" *per run*, but it runs every 5 minutes (288×/day), scans ~3M rows each time, and feeds a high-traffic homepage. On the OLTP primary that's a recurring 3M-row scan polluting the buffer cache and competing with the hot path — the exact failure from Lecture 1 §2. The frequency and the page traffic turn a "small" query into an OLAP load. The right answer is a **dbt incremental rollup** in the lakehouse (or at minimum a maintained Postgres rollup *table*, not the live scan), refreshed on a schedule, with the homepage reading the pre-computed result. Measure it: `pg_stat_statements` will show this query near the top by *total* time despite a modest mean — the Week 13 lesson, reappearing.

The whole challenge is calibration: don't reflexively lakehouse every aggregation (Q2) and don't reflexively keep every "small" query in Postgres (Q6). Shape alone doesn't decide; shape × volume × freshness × frequency does.

## Stretch

- **Prove Q6's harm.** Actually run the Q6 live-scan against your Postgres `order_items` in a loop every 5 seconds while measuring the buffer-cache hit ratio and the latency of a concurrent point read (Q1). Show the point read degrade. Then build the dbt rollup and show the homepage query drop to microseconds with no primary impact.
- **Build the Q3 rollup as a dbt model** and time it in Trino vs the equivalent on the Postgres primary. Quantify the difference and the cache impact.
- **Write the Q4 federated query** for real and `EXPLAIN (TYPE DISTRIBUTED)` it in Trino — show where Trino pushes the aggregation down to each source.

## Why this matters

In the Phase 3 architecture review, the reviewer will draw your data tier and ask "why does *this* query run *there*?" — and for at least one query they'll have picked the trap on purpose to see if you place it by reflex or by reasoning. This challenge *is* that conversation, six times. A data platform is only as good as the placement decisions behind it; the architect who keeps the OLTP primary fast *and* the analysts unblocked is the one who placed every query by shape × volume × freshness × cost, not by which tier was newest and most exciting.
