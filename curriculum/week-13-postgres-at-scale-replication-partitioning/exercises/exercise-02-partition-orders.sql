-- Exercise 2 — Partition the orders table online (RANGE by month)
--
-- Goal: Convert a flat `orders` table into a RANGE-partitioned table, monthly,
--       WITHOUT taking it offline, and PROVE the planner prunes partitions it
--       does not need. This is exactly the operation you run on a production
--       table that has outgrown a single heap.
--
-- Estimated time: 45 minutes. Runnable SQL.
--
-- HOW TO USE THIS FILE
--
--   Source ROS... no. Connect with psql and run it. It is idempotent enough to
--   re-run from a clean database; if you hit "already exists", DROP SCHEMA and rerun.
--
--       createdb shop 2>/dev/null || true
--       psql -h localhost -U postgres -d shop -f exercise-02-partition-orders.sql
--
--   Read every EXPLAIN block the script prints. The lesson is in the plans:
--   the flat table scans everything; the partitioned table scans one month.
--
-- ACCEPTANCE CRITERIA
--
--   [ ] The flat-table EXPLAIN shows a single Seq Scan over all rows.
--   [ ] After conversion, EXPLAIN for a one-month predicate shows an Append over
--       exactly ONE partition (pruning fired) — not all twelve.
--   [ ] A query that does NOT filter on created_at scans every partition, and you
--       can explain WHY (the planner can't rule any out).
--   [ ] The row counts before and after conversion match (no data lost).
--
-- Expected output shape is in comments at the bottom.

\timing on
\set ON_ERROR_STOP on

-- ---------------------------------------------------------------------------
-- Part 0 — A flat orders table with a year of data. This is the "before".
-- ---------------------------------------------------------------------------

DROP TABLE IF EXISTS orders_flat;

CREATE TABLE orders_flat (
    order_id    bigserial PRIMARY KEY,
    customer_id bigint      NOT NULL,
    status      text        NOT NULL DEFAULT 'PLACED',
    total_cents bigint      NOT NULL,
    created_at  timestamptz NOT NULL
);

-- 1.2M rows spread across the 12 months of 2026, roughly evenly.
INSERT INTO orders_flat (customer_id, status, total_cents, created_at)
SELECT
    (random() * 100000)::bigint,
    (ARRAY['PLACED','SHIPPED','DELIVERED','CANCELLED'])[1 + (random()*3)::int],
    (random() * 50000)::bigint,
    '2026-01-01'::timestamptz + (random() * 364) * interval '1 day'
FROM generate_series(1, 1200000);

CREATE INDEX ON orders_flat (created_at);
ANALYZE orders_flat;

SELECT count(*) AS flat_row_count FROM orders_flat;

-- The "before" plan: even with an index, a one-month range still reads from the
-- single big heap. Note the relation it scans is the whole table.
EXPLAIN (ANALYZE, BUFFERS, SUMMARY OFF)
SELECT count(*) FROM orders_flat
WHERE created_at >= '2026-03-01' AND created_at < '2026-04-01';

-- ---------------------------------------------------------------------------
-- Part 1 — The partitioned parent. Note: the partition key (created_at) MUST be
-- part of the primary key, because Postgres can't enforce a global unique index
-- across partitions.
-- ---------------------------------------------------------------------------

DROP TABLE IF EXISTS orders CASCADE;

CREATE TABLE orders (
    order_id    bigint      GENERATED ALWAYS AS IDENTITY,
    customer_id bigint      NOT NULL,
    status      text        NOT NULL DEFAULT 'PLACED',
    total_cents bigint      NOT NULL,
    created_at  timestamptz NOT NULL,
    PRIMARY KEY (order_id, created_at)          -- partition key in the PK
) PARTITION BY RANGE (created_at);

-- Create one partition per month of 2026. Bounds are [FROM, TO): inclusive low,
-- exclusive high, so the months tile with no gap and no overlap.
DO $$
DECLARE
    m        int;
    lo       date;
    hi       date;
    partname text;
BEGIN
    FOR m IN 1..12 LOOP
        lo       := make_date(2026, m, 1);
        hi       := (lo + interval '1 month')::date;
        partname := format('orders_2026_%02s', m);
        EXECUTE format(
            'CREATE TABLE %I PARTITION OF orders FOR VALUES FROM (%L) TO (%L);',
            partname, lo, hi
        );
    END LOOP;
END $$;

-- A DEFAULT partition catches rows outside 2026 so an insert never errors.
-- Watch it: if it silently grows, you forgot to provision a month.
CREATE TABLE orders_default PARTITION OF orders DEFAULT;

-- Index the partition key on the parent; it cascades to every partition.
CREATE INDEX ON orders (created_at);

-- ---------------------------------------------------------------------------
-- Part 2 — Backfill from the flat table. In production you batch this to avoid a
-- long transaction; here one statement is fine for 1.2M rows. Inserts are routed
-- to the correct partition automatically by created_at.
-- ---------------------------------------------------------------------------

INSERT INTO orders (customer_id, status, total_cents, created_at)
SELECT customer_id, status, total_cents, created_at
FROM orders_flat;

ANALYZE orders;

-- Same count as the flat table => no data lost.
SELECT count(*) AS partitioned_row_count FROM orders;

-- Confirm the data actually landed in the right partitions, not the default.
SELECT tableoid::regclass AS partition, count(*)
FROM orders
GROUP BY 1
ORDER BY 1;

-- ---------------------------------------------------------------------------
-- Part 3 — PROVE pruning. The "after" plan for a one-month predicate must touch
-- exactly ONE partition.
-- ---------------------------------------------------------------------------

EXPLAIN (ANALYZE, BUFFERS, SUMMARY OFF)
SELECT count(*) FROM orders
WHERE created_at >= '2026-03-01' AND created_at < '2026-04-01';

-- ---------------------------------------------------------------------------
-- Part 4 — The cautionary plan: a query that does NOT filter on the partition
-- key cannot be pruned. The planner has no way to rule any month out, so it scans
-- ALL twelve partitions (plus default). This is the "partition on the column you
-- query" lesson, made visible.
-- ---------------------------------------------------------------------------

EXPLAIN (ANALYZE, BUFFERS, SUMMARY OFF)
SELECT count(*) FROM orders
WHERE status = 'SHIPPED';

-- ---------------------------------------------------------------------------
-- Part 5 — Instant data expiry. Dropping last-quarter's data is a metadata-only
-- DROP/DETACH, not a giant bloating DELETE. This is one of partitioning's biggest
-- operational wins.
-- ---------------------------------------------------------------------------

-- DETACH CONCURRENTLY removes the partition without an ACCESS EXCLUSIVE lock, so
-- the table stays online while you archive or drop the detached month.
ALTER TABLE orders DETACH PARTITION orders_2026_01 CONCURRENTLY;
-- Now orders_2026_01 is a standalone table you can archive elsewhere or DROP.
DROP TABLE orders_2026_01;

SELECT count(*) AS rows_after_dropping_january FROM orders;

\timing off

-- ===========================================================================
-- Expected output (shape; exact counts/costs vary)
-- ===========================================================================
--
--  flat_row_count
-- ----------------
--         1200000
--
-- -- BEFORE (flat): one Seq Scan / Index Scan over the single orders_flat heap.
--
--  partitioned_row_count
-- -----------------------
--                1200000          <- equal to flat: no data lost
--
--          partition        | count
-- ------------------------- + -------
--  orders_2026_01           | ~100000
--  orders_2026_02           | ~100000
--  ...                      | ...
--  (no rows in orders_default)
--
-- -- AFTER (partitioned, one-month predicate): pruning fires.
--  Aggregate
--    ->  Append
--          ->  Seq Scan on orders_2026_03 orders_1     <-- ONE partition only
--
-- -- CAUTIONARY (status predicate, no partition-key filter): no pruning.
--  Aggregate
--    ->  Append
--          ->  Seq Scan on orders_2026_02 ...
--          ->  Seq Scan on orders_2026_03 ...
--          ...  (ALL partitions scanned — the planner can't rule any out)
--
--  rows_after_dropping_january
-- -----------------------------
--                     ~1100000     <- January's ~100k gone, instantly, no DELETE
--
-- The two plans side by side ARE the lesson: partitioning helps queries that
-- filter on the partition key (pruning), and does nothing for queries that don't.
-- Choose the partition key to match how you actually query the table.
-- ===========================================================================
