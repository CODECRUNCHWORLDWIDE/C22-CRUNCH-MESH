#!/usr/bin/env python3
# Exercise 3 — Measure the Failover RTO and RPO (runnable)
#
# Goal: Drive a steady stream of writes against the PRIMARY region, kill the
#       primary mid-stream, fail over to the replica, and MEASURE the two numbers
#       that matter:
#         - RTO: the recovery window = time from first failed write to first
#                successful write on the NEW primary.
#         - RPO: the data lost = writes that were acknowledged-or-in-flight on
#                the old primary but ABSENT from the new one. This should equal
#                the replication lag at the moment of failure (the RPO=lag identity
#                from Lecture 1 §2.2).
#
#       An RTO/RPO you didn't measure under load is a hope, not a number. This
#       script turns the failover into two measured numbers.
#
# Estimated time: 60 minutes. Runnable.
#
# HOW THIS EXERCISE WORKS
#   The script runs a writer loop that INSERTs rows into `writes(id, payload, ts)`
#   on the PRIMARY and records every id it BELIEVES it committed. When you trigger
#   the failure (kill the primary), writes start failing; the script keeps trying
#   and, once you've promoted the replica + repointed the connection, writes
#   succeed again. It then:
#     - computes RTO = (first success after failure) - (first failure)
#     - reconciles its "committed" set against what's actually present on the NEW
#       primary, and reports the writes that are MISSING -> the realized RPO.
#
# DRIVING THE FAILOVER (you do these by hand, the script measures):
#   STEP 0 — start the writer against the primary (region A):
#     python3 exercise-03-failover-rto.py --run \
#       --primary "postgresql://postgres:secret@localhost:5432/shop" \
#       --replica "postgresql://postgres:secret@localhost:5433/shop"
#   STEP 1 — when prompted "[ARMED]", kill region A's primary in another terminal:
#       kubectl --context kind-region-a delete deploy pg --wait=false
#   STEP 2 — promote the replica (region B) and tell the script to use it:
#       psql "$PGB" -c "SELECT pg_promote();"
#     The script auto-detects the promotion by retrying the --replica DSN as the
#     new primary; once it accepts writes, the RTO clock stops.
#
# PREREQUISITES
#   - Exercise 1 done: primary (A) + logical replica (B), the `writes` table on both.
#   - pip install psycopg2-binary
#   - Port-forwards (or real endpoints) for both regions reachable as --primary/--replica.
#
# NOTE ON HONESTY: this is a SIMULATION on two Kind clusters. The numbers are real
# for THIS setup (real promotion, real lost rows) but the absolute RTO/RPO depend
# on your injected latency and your manual promotion speed. The POINT is the
# method and the RPO=lag identity, not a production SLA.

import argparse
import sys
import time

try:
    import psycopg2
except ImportError:
    print("pip install psycopg2-binary", file=sys.stderr)
    sys.exit(2)


def connect(dsn, timeout=3):
    return psycopg2.connect(dsn, connect_timeout=timeout)


def replication_lag_seconds(primary_dsn):
    """Read replay_lag from the primary's pg_stat_replication, in seconds.

    This is the LIVE RPO: the data that would be lost if the primary died now.
    Returns None if no replica is connected (which is itself a finding: your
    standby isn't replicating!).
    """
    try:
        conn = connect(primary_dsn)
        with conn, conn.cursor() as cur:
            cur.execute("""
                SELECT EXTRACT(EPOCH FROM COALESCE(replay_lag, INTERVAL '0'))
                FROM pg_stat_replication
                ORDER BY replay_lag DESC NULLS LAST
                LIMIT 1
            """)
            row = cur.fetchone()
        conn.close()
        return float(row[0]) if row else None
    except Exception:
        return None


def insert(dsn, payload):
    """One write. Returns the assigned id on success, raises on failure."""
    conn = connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute("INSERT INTO writes (payload) VALUES (%s) RETURNING id", (payload,))
            new_id = cur.fetchone()[0]
        return new_id
    finally:
        conn.close()


def present_ids(dsn):
    """The set of write ids actually present on a server (the new primary)."""
    conn = connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM writes")
            return {r[0] for r in cur.fetchall()}
    finally:
        conn.close()


def run(primary_dsn, replica_dsn, qps, arm_after):
    interval = 1.0 / max(qps, 1)
    committed = []          # ids we believe we committed (the primary RETURNed them)
    first_failure_t = None
    first_success_after_failure_t = None
    lag_at_failure = None
    target_dsn = primary_dsn  # we write here until it dies, then switch to replica
    switched = False
    armed_announced = False

    print(f"[t=0.0s]   writer starting -> primary, {qps} qps")
    start = time.monotonic()
    seq = 0

    while True:
        now = time.monotonic() - start
        seq += 1

        # Announce the ARM point so the operator knows when to kill the primary.
        if not armed_announced and now >= arm_after:
            lag_at_failure = replication_lag_seconds(primary_dsn)
            print(f"[t={now:4.1f}s] [ARMED] kill the primary now "
                  f"(measured pre-failure lag = {lag_at_failure}s -> expected RPO)")
            armed_announced = True

        try:
            new_id = insert(target_dsn, f"seq-{seq}")
            committed.append(new_id)
            if first_failure_t is not None and first_success_after_failure_t is None:
                first_success_after_failure_t = now
                print(f"[t={now:4.1f}s] first SUCCESS after failure -> RTO clock stops")
                break  # we've recovered; stop and reconcile
        except Exception as e:
            if first_failure_t is None:
                first_failure_t = now
                print(f"[t={now:4.1f}s] first FAILURE (primary down): {type(e).__name__}")
            # After the primary fails, start trying the replica as the NEW primary.
            # It only accepts writes once you've run pg_promote() on it.
            if not switched and first_failure_t is not None:
                target_dsn = replica_dsn
                switched = True
                print(f"[t={now:4.1f}s] switching writer -> replica (waiting for pg_promote)")
        time.sleep(interval)

        # Safety stop so the script can't hang forever if you never promote.
        if first_failure_t is not None and (now - first_failure_t) > 120:
            print("gave up after 120s without recovery — did you pg_promote() the replica?")
            return

    # --- reconcile: which committed writes are MISSING on the new primary? ---
    new_primary = replica_dsn
    present = present_ids(new_primary)
    lost = [i for i in committed if i not in present]

    rto = (first_success_after_failure_t - first_failure_t) if first_failure_t else 0.0
    print("-" * 68)
    print(f"MEASURED RTO: {rto:.1f}s  (first failed write -> first success on new primary)")
    print(f"MEASURED RPO: {lag_at_failure}s  (replication lag at failure = data at risk)")
    print(f"WRITES LOST:  {len(lost)}     (committed on old primary, absent on new: {lost[:10]}{'...' if len(lost) > 10 else ''})")
    print("-" * 68)
    print("THE IDENTITY: writes lost should correspond to ~the lag-at-failure window.")
    print("If lost > 0 but you measured lag=0, your standby wasn't really caught up —")
    print("which is the silent-standby failure this whole week exists to catch.")


def main():
    p = argparse.ArgumentParser(description="Measure failover RTO and RPO.")
    p.add_argument("--run", action="store_true", help="run the failover measurement")
    p.add_argument("--primary", default="postgresql://postgres:secret@localhost:5432/shop")
    p.add_argument("--replica", default="postgresql://postgres:secret@localhost:5433/shop")
    p.add_argument("--qps", type=int, default=10, help="writes per second")
    p.add_argument("--arm-after", type=float, default=12.0,
                   help="seconds of healthy writes before prompting you to kill the primary")
    args = p.parse_args()

    if not args.run:
        p.print_help()
        return 2
    run(args.primary, args.replica, args.qps, args.arm_after)
    return 0


if __name__ == "__main__":
    sys.exit(main())


# -----------------------------------------------------------------------------
# Expected output
# -----------------------------------------------------------------------------
#
#   $ python3 exercise-03-failover-rto.py --run
#   [t=0.0s]   writer starting -> primary, 10 qps
#   [t=12.0s] [ARMED] kill the primary now (measured pre-failure lag = 0.4s -> expected RPO)
#   [t=12.3s] first FAILURE (primary down): OperationalError
#   [t=12.3s] switching writer -> replica (waiting for pg_promote)
#   [t=18.7s] first SUCCESS after failure -> RTO clock stops
#   --------------------------------------------------------------------
#   MEASURED RTO: 6.4s  (first failed write -> first success on new primary)
#   MEASURED RPO: 0.4s  (replication lag at failure = data at risk)
#   WRITES LOST:  4     (committed on old primary, absent on new: [991, 992, 993, 994])
#   --------------------------------------------------------------------
#
# ACCEPTANCE CRITERIA
#   [ ] The script reports a MEASURED RTO (the recovery window) and a MEASURED RPO
#       (the lag at failure) — two numbers, not hopes.
#   [ ] WRITES LOST is non-zero under async replication and CORRESPONDS to the lag
#       window (more lag -> more lost). Run it twice: once with low lag, once with
#       high lag (crank --qps), and show RPO and lost-writes both rise.
#   [ ] You can state the RPO=lag identity: the data you lose at failover is exactly
#       the data that hadn't replicated yet.
#   [ ] BONUS: re-run with synchronous replication (Exercise 1 stretch) and show
#       WRITES LOST drops to ~0 (RPO~0) — at the cost of slower writes. That trade
#       is the heart of the week.
# -----------------------------------------------------------------------------
