-- Exercise 2 — Analytical SQL against Iceberg (in Trino)
--
-- Goal: Write the kind of OLAP SQL the lakehouse exists for — aggregations, window
--       functions, time-travel, and a FEDERATED join across Iceberg and Postgres —
--       and see why each belongs on the analytical side of the OLTP/OLAP boundary.
--
-- Estimated time: 45 minutes. Runnable in the Trino CLI.
--
-- HOW TO USE THIS FILE
--
--   Requires Exercise 1's lakehouse up, with iceberg.shop.orders populated. For
--   the federation section (Part 5) you also need a Postgres connector configured
--   in Trino (etc/trino/catalog/postgres.properties) pointing at your Week 13/14
--   Postgres. If you don't have that, Part 5 is clearly marked optional.
--
--       docker compose exec -T trino trino --catalog iceberg --schema shop \
--           < exercise-02-analytical-queries.sql
--
--   Read each result. The point is to feel how a column-store engine answers a
--   big-scan aggregation, and to use the two lakehouse-only powers: time-travel
--   and federation.
--
-- ACCEPTANCE CRITERIA
--
--   [ ] The aggregation and window queries return sensible results.
--   [ ] A FOR VERSION AS OF time-travel query returns an EARLIER table state.
--   [ ] (If Postgres connector configured) the federated join returns rows
--       combining Iceberg historical data with live Postgres current state.
--   [ ] You can state, for each query, why it belongs on the OLAP side.
--
-- Expected output shape is in comments at the bottom.

-- First, seed a bit more data so the analytics have something to chew on. (Skip
-- if you already loaded a real dataset via Exercise 3.)
INSERT INTO iceberg.shop.orders VALUES
    (10, 100, 'SHIPPED',   2500, TIMESTAMP '2026-01-05 09:00:00'),
    (11, 100, 'DELIVERED', 4200, TIMESTAMP '2026-01-20 12:00:00'),
    (12, 200, 'PLACED',     900, TIMESTAMP '2026-02-03 08:30:00'),
    (13, 200, 'CANCELLED',  900, TIMESTAMP '2026-02-04 08:30:00'),
    (14, 100, 'DELIVERED', 7700, TIMESTAMP '2026-03-11 15:45:00'),
    (15, 300, 'SHIPPED',   1500, TIMESTAMP '2026-03-12 16:00:00'),
    (16, 300, 'DELIVERED', 6000, TIMESTAMP '2026-04-01 10:10:00');

-- ===========================================================================
-- Part 1 — The daily/monthly revenue rollup (the canonical OLAP aggregation).
-- This scan reads only created_at, status, total_cents — not the whole row —
-- and prunes by month-partition. This is exactly the query you do NOT want
-- running on your OLTP primary.
-- ===========================================================================

SELECT
    date_trunc('month', created_at)              AS month,
    count(*)                                     AS orders,
    sum(total_cents) / 100.0                     AS gross_dollars,
    sum(CASE WHEN status = 'CANCELLED' THEN total_cents ELSE 0 END) / 100.0
                                                 AS cancelled_dollars,
    sum(CASE WHEN status IN ('SHIPPED','DELIVERED') THEN total_cents ELSE 0 END) / 100.0
                                                 AS fulfilled_dollars
FROM iceberg.shop.orders
GROUP BY 1
ORDER BY 1;

-- ===========================================================================
-- Part 2 — Window functions: each customer's running lifetime spend, and their
-- rank by spend. Window functions over millions of rows are an OLAP staple.
-- ===========================================================================

SELECT
    customer_id,
    order_id,
    created_at,
    total_cents / 100.0 AS dollars,
    sum(total_cents) OVER (
        PARTITION BY customer_id ORDER BY created_at
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) / 100.0 AS running_lifetime_dollars
FROM iceberg.shop.orders
WHERE status <> 'CANCELLED'
ORDER BY customer_id, created_at;

-- ===========================================================================
-- Part 3 — Top customers by fulfilled revenue (a HAVING + ORDER BY + LIMIT shape).
-- ===========================================================================

SELECT
    customer_id,
    count(*)                  AS fulfilled_orders,
    sum(total_cents) / 100.0  AS fulfilled_dollars
FROM iceberg.shop.orders
WHERE status IN ('SHIPPED', 'DELIVERED')
GROUP BY customer_id
HAVING sum(total_cents) > 5000
ORDER BY fulfilled_dollars DESC
LIMIT 10;

-- ===========================================================================
-- Part 4 — Time-travel: the table as it was at an earlier snapshot. First list
-- snapshots, then query AS OF one. (Replace <snapshot_id> with a real id from
-- the first result.) This is a power Postgres does not give you.
-- ===========================================================================

SELECT snapshot_id, committed_at, operation
FROM iceberg.shop."orders$snapshots"
ORDER BY committed_at;

-- The current count vs the count at an earlier snapshot:
SELECT count(*) AS current_count FROM iceberg.shop.orders;
-- SELECT count(*) AS earlier_count FROM iceberg.shop.orders
--   FOR VERSION AS OF <snapshot_id>;        -- uncomment with a real id

-- You can also time-travel by timestamp:
-- SELECT count(*) FROM iceberg.shop.orders
--   FOR TIMESTAMP AS OF TIMESTAMP '2026-01-01 00:00:00 UTC';

-- ===========================================================================
-- Part 5 — FEDERATION (optional; requires a Postgres connector in Trino).
-- Join the LAKEHOUSE historical aggregate to LIVE Postgres current state in one
-- query. Iceberg supplies the cheap big-scan history; Postgres supplies the
-- fresh current open-order counts. Neither system pollutes the other.
-- ===========================================================================

-- Uncomment when postgres.properties is configured:
--
-- SELECT
--     h.customer_id,
--     h.lifetime_dollars,
--     coalesce(o.open_orders, 0) AS open_orders_now
-- FROM (
--     SELECT customer_id, sum(total_cents) / 100.0 AS lifetime_dollars
--     FROM iceberg.shop.orders
--     WHERE status <> 'CANCELLED'
--     GROUP BY customer_id
-- ) h
-- LEFT JOIN (
--     SELECT customer_id, count(*) AS open_orders
--     FROM postgres.public.orders
--     WHERE status = 'PLACED'
--     GROUP BY customer_id
-- ) o ON h.customer_id = o.customer_id
-- ORDER BY h.lifetime_dollars DESC;

-- ===========================================================================
-- Expected output (shape; exact rows depend on your seed data)
-- ===========================================================================
--
-- Part 1 (monthly rollup):
--    month    | orders | gross_dollars | cancelled_dollars | fulfilled_dollars
-- ------------+--------+---------------+-------------------+-------------------
--  2026-01-01 |   2    |    67.00      |       0.00        |      67.00
--  2026-02-01 |   2    |    18.00      |       9.00        |       0.00
--  2026-03-01 |   3    |   119.00      |       0.00        |     119.00
--  2026-04-01 |   2    |   ...         |       ...         |      ...
--
-- Part 2 (running lifetime): customer 100's running_lifetime_dollars climbs
--   25.00 -> 67.00 -> 144.00 across their three non-cancelled orders.
--
-- Part 4 (time-travel): current_count is the full row count; AS OF an earlier
--   snapshot returns a SMALLER number — the table as it was then.
--
-- Part 5 (federation, if enabled): one row per customer with BOTH their
--   lakehouse-computed lifetime_dollars AND their live Postgres open_orders_now.
--
-- The lesson: every query here reads few columns over many rows (OLAP), uses a
-- power the lakehouse provides (column scan, time-travel, federation), and would
-- be a poor fit for — or actively harmful to — your OLTP Postgres primary.
-- ===========================================================================
