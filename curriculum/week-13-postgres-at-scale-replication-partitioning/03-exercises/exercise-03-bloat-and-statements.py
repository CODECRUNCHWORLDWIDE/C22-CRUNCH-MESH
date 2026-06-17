#!/usr/bin/env python3
# Exercise 3 — Bloat and the statements that cost you
#
# Goal: Generate MVCC bloat with an UPDATE storm, watch dead tuples accumulate and
#       autovacuum clean them, then rank queries by TOTAL execution time in
#       pg_stat_statements so you optimize the query that actually costs you, not
#       the one that "feels" slow. These are the two storage-tier instincts a
#       senior data-platform engineer reaches for first.
#
# Estimated time: 45 minutes. Runnable.
#
# REQUIREMENTS
#
#   * Postgres 16 you have superuser on.
#   * pg_stat_statements loaded. The simplest way is to start Postgres with:
#         -c shared_preload_libraries=pg_stat_statements
#     (the postgres:16 image: add that to `command:`). Then this script runs
#         CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
#     If shared_preload_libraries is NOT set, CREATE EXTENSION will fail and the
#     script tells you exactly what to do.
#   * psycopg v3:  python3 -m pip install "psycopg[binary]>=3.1"
#
# HOW TO USE THIS FILE
#
#       python3 exercise-03-bloat-and-statements.py \
#           --dsn "host=localhost user=postgres password=postgres dbname=shop"
#
#   The script:
#     1. Builds a small accounts table and seeds it.
#     2. Runs an UPDATE storm on a NON-indexed column (HOT-eligible) and an
#        indexed column, so you can SEE the HOT ratio differ.
#     3. Reports n_dead_tup / dead_pct from pg_stat_user_tables before and after
#        a manual VACUUM, proving VACUUM reclaims the dead tuples.
#     4. Prints the top queries by total_exec_time from pg_stat_statements.
#
# ACCEPTANCE CRITERIA
#
#   [ ] After the UPDATE storm, n_dead_tup is clearly > 0 (bloat appeared).
#   [ ] After VACUUM, dead tuples drop toward 0 (bloat reclaimed).
#   [ ] The HOT-eligible update column shows a HIGHER n_tup_hot_upd ratio than the
#       indexed column — you can explain why (HOT avoids index churn).
#   [ ] The pg_stat_statements report ranks by total time, and you can name the
#       query with the highest TOTAL cost (which is not the highest MEAN cost).
#
# Expected output shape is at the bottom of the file.

from __future__ import annotations

import argparse
import sys
import time

try:
    import psycopg
except ImportError:
    sys.exit("psycopg v3 is required:  python3 -m pip install 'psycopg[binary]>=3.1'")


def dead_tuple_stats(conn: psycopg.Connection, table: str) -> dict:
    """Read live/dead tuple counts and the HOT-update ratio for one table."""
    row = conn.execute(
        """
        SELECT n_live_tup, n_dead_tup, n_tup_upd, n_tup_hot_upd, last_autovacuum
        FROM pg_stat_user_tables
        WHERE relname = %s
        """,
        (table,),
    ).fetchone()
    if row is None:
        return {}
    live, dead, upd, hot_upd, last_av = row
    dead_pct = round(100 * dead / (live + dead), 1) if (live + dead) else 0.0
    hot_ratio = round(100 * hot_upd / upd, 1) if upd else 0.0
    return {
        "live": live,
        "dead": dead,
        "dead_pct": dead_pct,
        "n_tup_upd": upd,
        "n_tup_hot_upd": hot_upd,
        "hot_ratio_pct": hot_ratio,
        "last_autovacuum": last_av,
    }


def print_stats(label: str, s: dict) -> None:
    if not s:
        print(f"[{label}] (no stats row yet)")
        return
    print(
        f"[{label}] live={s['live']:>7} dead={s['dead']:>7} "
        f"dead_pct={s['dead_pct']:>5}%  "
        f"updates={s['n_tup_upd']:>7} hot={s['n_tup_hot_upd']:>7} "
        f"hot_ratio={s['hot_ratio_pct']:>5}%"
    )


def setup_table(conn: psycopg.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS accounts;")
    conn.execute(
        """
        CREATE TABLE accounts (
            account_id   bigint PRIMARY KEY,
            owner_name   text   NOT NULL,
            balance_cents bigint NOT NULL,         -- NOT indexed: HOT-eligible
            tier         text   NOT NULL           -- WILL be indexed: not HOT-eligible
        ) WITH (fillfactor = 85);                  -- leave room for HOT updates
        """
    )
    conn.execute("CREATE INDEX accounts_tier_idx ON accounts (tier);")
    conn.execute(
        """
        INSERT INTO accounts (account_id, owner_name, balance_cents, tier)
        SELECT g, 'owner_' || g, (random()*1000000)::bigint,
               (ARRAY['free','pro','enterprise'])[1 + (random()*2)::int]
        FROM generate_series(1, 50000) g;
        """
    )
    conn.execute("ANALYZE accounts;")


def update_storm(conn: psycopg.Connection, column: str, rounds: int = 10) -> None:
    """Update one column many times. balance_cents is HOT-eligible (no index);
    tier is not (it's indexed), so updating it churns the index."""
    for _ in range(rounds):
        if column == "balance_cents":
            conn.execute("UPDATE accounts SET balance_cents = balance_cents + 1;")
        else:
            conn.execute(
                "UPDATE accounts SET tier = "
                "(ARRAY['free','pro','enterprise'])[1 + (random()*2)::int];"
            )


def try_enable_pg_stat_statements(conn: psycopg.Connection) -> bool:
    try:
        conn.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements;")
        conn.execute("SELECT pg_stat_statements_reset();")
        return True
    except psycopg.Error as exc:
        print("\n[!] Could not enable pg_stat_statements:", exc)
        print("    Start Postgres with: "
              "-c shared_preload_libraries=pg_stat_statements")
        print("    Then re-run. Skipping the statements section for now.\n")
        conn.rollback()
        return False


def run_mixed_query_load(conn: psycopg.Connection) -> None:
    """Run two distinct query shapes with very different call counts, so total
    time and mean time disagree — the whole point of pg_stat_statements."""
    # A: cheap query, run MANY times. Low mean, high TOTAL.
    for i in range(2000):
        conn.execute("SELECT balance_cents FROM accounts WHERE account_id = %s;",
                     (1 + (i % 50000),))
    # B: expensive query, run a FEW times. High mean, modest TOTAL.
    for _ in range(5):
        conn.execute(
            "SELECT tier, count(*), avg(balance_cents) "
            "FROM accounts GROUP BY tier;"
        )


def report_top_statements(conn: psycopg.Connection) -> None:
    rows = conn.execute(
        """
        SELECT round(total_exec_time::numeric, 1) AS total_ms,
               calls,
               round(mean_exec_time::numeric, 3)  AS mean_ms,
               round(100 * total_exec_time /
                     NULLIF(sum(total_exec_time) OVER (), 0), 1) AS pct,
               left(query, 60) AS query
        FROM pg_stat_statements
        WHERE query NOT LIKE '%pg_stat_statements%'
        ORDER BY total_exec_time DESC
        LIMIT 8;
        """
    ).fetchall()
    print("\n  TOTAL_ms   CALLS    MEAN_ms   PCT   QUERY")
    print("  " + "-" * 70)
    for total_ms, calls, mean_ms, pct, query in rows:
        print(f"  {total_ms:>8}  {calls:>6}   {mean_ms:>8}  {pct:>4}%  {query}")
    print("\n  Read the TOTAL_ms column, not MEAN_ms. The query at the top costs")
    print("  the most aggregate time — that is the one worth optimizing.")


def main() -> None:
    ap = argparse.ArgumentParser(description="MVCC bloat + pg_stat_statements drill.")
    ap.add_argument("--dsn", required=True,
                    help='e.g. "host=localhost user=postgres dbname=shop"')
    args = ap.parse_args()

    with psycopg.connect(args.dsn, autocommit=True) as conn:
        print("== Part 1: build and seed the accounts table ==")
        setup_table(conn)
        print_stats("seeded", dead_tuple_stats(conn, "accounts"))

        print("\n== Part 2: UPDATE storm on the HOT-eligible (non-indexed) column ==")
        update_storm(conn, "balance_cents", rounds=10)
        time.sleep(0.5)
        s_hot = dead_tuple_stats(conn, "accounts")
        print_stats("after balance_cents storm", s_hot)

        print("\n== Part 3: VACUUM reclaims the dead tuples ==")
        conn.execute("VACUUM (VERBOSE) accounts;")
        time.sleep(0.5)
        print_stats("after VACUUM", dead_tuple_stats(conn, "accounts"))

        print("\n== Part 4: UPDATE storm on the INDEXED column (not HOT-eligible) ==")
        conn.execute("SELECT pg_stat_reset_single_table_counters("
                     "(SELECT relid FROM pg_stat_user_tables WHERE relname='accounts'));")
        update_storm(conn, "tier", rounds=10)
        time.sleep(0.5)
        s_cold = dead_tuple_stats(conn, "accounts")
        print_stats("after tier storm", s_cold)
        print("\n  Compare hot_ratio: updating the NON-indexed balance_cents stays")
        print("  HOT (high ratio, no index churn); updating the INDEXED tier does")
        print("  not (low ratio, every update rewrites the index). That is HOT.")

        print("\n== Part 5: rank queries by TOTAL time (pg_stat_statements) ==")
        if try_enable_pg_stat_statements(conn):
            run_mixed_query_load(conn)
            report_top_statements(conn)


if __name__ == "__main__":
    main()


# -----------------------------------------------------------------------------
# Expected output (shape; exact numbers vary by hardware and timing)
# -----------------------------------------------------------------------------
#
# == Part 1: build and seed the accounts table ==
# [seeded] live=  50000 dead=      0 dead_pct=  0.0%  updates=      0 hot=      0 ...
#
# == Part 2: UPDATE storm on the HOT-eligible (non-indexed) column ==
# [after balance_cents storm] live= 50000 dead= 500000 dead_pct= 90.9% \
#         updates= 500000 hot= ~480000 hot_ratio= ~96.0%
#   -> bloat appeared: ~500k dead tuples from 10 full-table updates of 50k rows.
#   -> hot_ratio is HIGH because balance_cents is not indexed.
#
# == Part 3: VACUUM reclaims the dead tuples ==
# [after VACUUM] live= 50000 dead=     0 dead_pct=  0.0%  ...
#   -> VACUUM made the dead-tuple space reusable; dead count back to ~0.
#
# == Part 4: UPDATE storm on the INDEXED column (not HOT-eligible) ==
# [after tier storm] live= 50000 dead= 500000 ... hot_ratio= ~20.0%  (much lower)
#   -> updating the INDEXED column churns the index; far fewer updates stay HOT.
#
# == Part 5: rank queries by TOTAL time (pg_stat_statements) ==
#
#   TOTAL_ms   CALLS    MEAN_ms   PCT   QUERY
#   ----------------------------------------------------------------------
#      420.5    2000      0.210  78.0%  SELECT balance_cents FROM accounts WHERE ...
#      118.7       5     23.740  22.0%  SELECT tier, count(*), avg(balance_cents) ...
#
#   The point-lookup has a TINY mean (0.21 ms) but runs 2000 times, so it
#   dominates TOTAL time. The aggregate has a big mean (23 ms) but runs 5 times.
#   You optimize the FIRST one. That is the lesson: total time, not felt slowness.
# -----------------------------------------------------------------------------
