#!/usr/bin/env python3
"""
Exercise 3 - Drill B: Kafka Broker Loss, No Double-Process (runnable driver)

Drive the MANDATORY Kafka-broker-loss chaos drill against your running capstone.
Stream orders, kill a broker mid-traffic (forcing partition-leader failover and a
consumer rebalance, which causes some in-flight messages to be RE-DELIVERED), then
PROVE - with a SQL count - that every idempotency key was charged EXACTLY ONCE
despite the redelivery. The empty `HAVING COUNT(*) > 1` result set is the proof.

This is the second of the two mandatory capstone chaos drills. Its deliverable is
POSTMORTEM-drill-B.md, and its load-bearing artifact is the empty violation query.

USAGE
  pip install requests psycopg2-binary
  export BFF_URL=http://<bff-web-loadbalancer-ip>:443
  export KAFKA_BROKER_POD=kafka-1                # the broker pod to kill
  export KAFKA_NAMESPACE=kafka
  export PAYMENT_DSN="postgresql://user:pw@payment-db:5432/payment"

  python3 exercise-03-broker-loss-no-double-process.py --duration 180

WHAT IT DOES (and does NOT do)
  1. Streams orders (unique idempotency key each) at a steady rate.
  2. Mid-stream, kills ONE Kafka broker (a partition leader for some partitions).
     -> Kafka elects a surviving in-sync replica as the new leader; producers retry;
        consumers in the group REBALANCE and re-pull any uncommitted in-flight batch.
        That re-pull is the at-least-once REDELIVERY this drill targets.
  3. Lets the stream finish and the consumers drain.
  4. PROVES THE INVARIANT against the payment DB: every idempotency key charged
     exactly once. Also checks the DLQ stayed empty and no order was lost.
  5. Writes POSTMORTEM-drill-B.md with the result and the integrity proof.

  It kills a broker via kubectl and probes the DB; it does not mutate manifests.
  Adapt the resource names. The DB query is the deliverable - do not soften it.

HYPOTHESIS (state it first - the postmortem is the gap vs reality)
  Losing one broker mid-traffic causes a brief produce-latency blip and a consumer
  rebalance that re-delivers some in-flight messages - but because every consumer is
  idempotent (idempotency key + outbox-backed dedup), NO order is processed twice and
  NO customer is double-charged. The DLQ stays empty.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import os
import subprocess
import sys
import threading
import time
import uuid

try:
    import requests
except ImportError:
    print("pip install requests", file=sys.stderr)
    raise


@dataclasses.dataclass
class DrillResult:
    orders_sent: int = 0
    orders_ok: int = 0
    t_kill: float = 0.0
    redelivered_estimate: int = 0  # filled from the dedup metric if available
    double_charges: int = -1       # -1 = not yet checked; 0 = clean
    dlq_depth: int = -1
    lost_orders: int = -1


_stop = threading.Event()
_sent_keys: list[str] = []
_lock = threading.Lock()


def iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S")


def place_order(bff_url: str) -> tuple[bool, str]:
    key = f"brokerdrill-{uuid.uuid4().hex[:12]}"
    try:
        r = requests.post(
            f"{bff_url}/v1/orders",
            json={"customer": "drill", "sku": "SKU-7", "qty": 1},
            headers={"x-idempotency-key": key},
            timeout=5,
        )
        return (r.status_code < 500, key)
    except requests.RequestException:
        return (False, key)


def stream_orders(bff_url: str, rps: int, res: DrillResult) -> None:
    interval = 1.0 / max(1, rps)
    while not _stop.is_set():
        ok, key = place_order(bff_url)
        with _lock:
            res.orders_sent += 1
            if ok:
                res.orders_ok += 1
                _sent_keys.append(key)
        time.sleep(interval)


def kill_broker(pod: str, namespace: str) -> None:
    print(f"[{iso()}] FAULT: killing Kafka broker {pod} in {namespace}")
    subprocess.run(
        ["kubectl", "delete", "pod", pod, "-n", namespace,
         "--grace-period=0", "--force"],
        check=False,
    )


def verify_exactly_once(dsn: str, res: DrillResult) -> None:
    """The proof. Query for any idempotency key charged more than once. Zero rows =
    exactly-once held under the broker loss. This is the deliverable."""
    try:
        import psycopg2
    except ImportError:
        print("  (install psycopg2-binary to run the integrity check)", file=sys.stderr)
        return
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            # THE LOAD-BEARING QUERY: any idempotency key with >1 charge is a double-charge.
            cur.execute(
                "SELECT idempotency_key, COUNT(*) FROM charges "
                "GROUP BY idempotency_key HAVING COUNT(*) > 1"
            )
            violations = cur.fetchall()
            res.double_charges = len(violations)

            # how many distinct orders were actually charged (loss check)
            cur.execute("SELECT COUNT(DISTINCT idempotency_key) FROM charges "
                        "WHERE idempotency_key LIKE %s", ("brokerdrill-%",))
            charged = cur.fetchone()[0]
            with _lock:
                res.lost_orders = max(0, res.orders_ok - charged)

            if violations:
                print(f"  INTEGRITY FAIL: {len(violations)} double-charged keys, e.g. {violations[:3]}")
            else:
                print("  INTEGRITY PASS: zero idempotency keys charged more than once.")
    finally:
        conn.close()


def check_dlq_depth(res: DrillResult) -> None:
    """Check the dead-letter topic stayed empty (toy: reads a consumer-group lag or a
    metric in a real setup). Here we attempt a kcat consume of the DLQ and count."""
    try:
        out = subprocess.run(
            ["kcat", "-C", "-b", "kafka:9092", "-t", "order.placed.v1.DLQ",
             "-o", "beginning", "-e", "-q"],
            capture_output=True, text=True, timeout=15,
        )
        res.dlq_depth = len([l for l in out.stdout.splitlines() if l.strip()])
    except Exception:
        res.dlq_depth = -1  # couldn't check; note it in the postmortem
    if res.dlq_depth == 0:
        print("  DLQ check: empty (no message dead-lettered during the drill).")
    elif res.dlq_depth > 0:
        print(f"  DLQ check: {res.dlq_depth} messages dead-lettered - investigate.")


def write_postmortem(res: DrillResult) -> None:
    clean = (res.double_charges == 0)
    no_loss = (res.lost_orders == 0)
    passed = clean and no_loss
    content = f"""# Postmortem - Drill B: Kafka Broker Loss, No Double-Process

## Summary
Killed a Kafka broker mid-traffic, forcing a partition-leader failover and a consumer
rebalance (which re-delivered in-flight messages). Double-charge violations:
{res.double_charges}. Lost orders: {res.lost_orders}. DLQ depth: {res.dlq_depth}.
Overall: {"PASS" if passed else "FAIL - investigate"}.

## Hypothesis
Losing one broker causes a produce-latency blip and a consumer rebalance that
re-delivers some in-flight messages - but idempotent consumers (idempotency key +
outbox-backed dedup) ensure NO order is processed twice. DLQ stays empty.

## Impact
- Orders sent: {res.orders_sent}; succeeded: {res.orders_ok}.
- Re-delivered messages (expected, harmless): {res.redelivered_estimate or "[fill from dedup metric]"}.
- Double-charges: {res.double_charges} {"(zero - exactly-once held)" if clean else "(VIOLATION)"}.
- Lost orders: {res.lost_orders}. DLQ depth: {res.dlq_depth}.

## The integrity proof (the deliverable)
Query run against the payment DB after the drill:

    SELECT idempotency_key, COUNT(*) FROM charges
    GROUP BY idempotency_key HAVING COUNT(*) > 1;

Result: {"0 rows - no idempotency key charged more than once." if clean else f"{res.double_charges} rows - DOUBLE-CHARGE."}

## Timeline
- t0: steady stream of orders.
- t_kill: broker killed -> leader failover + consumer rebalance.
- t_recover: produce latency back to normal; consumers drained.

## Root cause (of WHY it held)
The redelivery is EXPECTED - at-least-once delivery doing its job after a rebalance.
It caused no double-charge because each consumer checks the idempotency key against
the outbox-backed dedup store and SKIPS the duplicate effect; the outbox makes "did
the work" and "recorded that I did the work" atomic, so a crash between them can't
cause a re-process. The DB unique constraint on idempotency_key is the final backstop.

## Action items
- [ ] [owner] Add a metric counting deduplicated (skipped-duplicate) messages so the
      redelivery is VISIBLE in production, not just inferred in the drill.
- [ ] [owner] Confirm the producer's acks=all + min.insync.replicas so a broker loss
      can't lose an unacked message.
- [ ] [owner] [any finding from the drill - e.g., a longer-than-expected rebalance].
"""
    with open("POSTMORTEM-drill-B.md", "w") as f:
        f.write(content)
    print(f"\n[{iso()}] wrote POSTMORTEM-drill-B.md (double_charges={res.double_charges}, "
          f"lost={res.lost_orders}, dlq={res.dlq_depth})")


def main() -> int:
    p = argparse.ArgumentParser(description="Drill B: Kafka broker loss, no double-process.")
    p.add_argument("--duration", type=int, default=180, help="total drill seconds")
    p.add_argument("--rps", type=int, default=50, help="order stream rate")
    p.add_argument("--kill-at", type=int, default=60, help="seconds in to kill the broker")
    args = p.parse_args()

    bff = os.environ.get("BFF_URL")
    pod = os.environ.get("KAFKA_BROKER_POD", "kafka-1")
    ns = os.environ.get("KAFKA_NAMESPACE", "kafka")
    dsn = os.environ.get("PAYMENT_DSN", "")
    if not bff:
        print("set BFF_URL to your bff-web entry point", file=sys.stderr)
        return 2

    res = DrillResult()
    print(f"[{iso()}] streaming orders at {args.rps} rps for {args.duration}s")
    streamer = threading.Thread(target=stream_orders, args=(bff, args.rps, res), daemon=True)
    streamer.start()

    start = time.monotonic()
    killed = False
    while time.monotonic() - start < args.duration:
        time.sleep(1)
        if not killed and (time.monotonic() - start) >= args.kill_at:
            res.t_kill = time.monotonic()
            kill_broker(pod, ns)
            killed = True

    _stop.set()
    streamer.join(timeout=5)

    print(f"\n[{iso()}] letting consumers drain, then verifying exactly-once...")
    time.sleep(10)  # allow the consumers to finish processing the backlog

    if dsn:
        verify_exactly_once(dsn, res)
    else:
        print("  (set PAYMENT_DSN to run the exactly-once query - REQUIRED for the deliverable)")
    check_dlq_depth(res)

    write_postmortem(res)
    passed = (res.double_charges == 0) and (res.lost_orders == 0)
    print(f"\nDrill B {'PASSED' if passed else 'FAILED'}. Fill in the postmortem's "
          f"timeline and action items.")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())


# -----------------------------------------------------------------------------
# Expected output
# -----------------------------------------------------------------------------
#
#   [14:20:01] streaming orders at 50 rps for 180s
#   [14:21:01] FAULT: killing Kafka broker kafka-1 in kafka
#   [14:23:01] letting consumers drain, then verifying exactly-once...
#     INTEGRITY PASS: zero idempotency keys charged more than once.
#     DLQ check: empty (no message dead-lettered during the drill).
#   [14:23:11] wrote POSTMORTEM-drill-B.md (double_charges=0, lost=0, dlq=0)
#
#   Drill B PASSED. Fill in the postmortem's timeline and action items.
#
# THE PROOF is the empty result set. Anyone can CLAIM exactly-once; you QUERIED for the
# violation under the exact failure (broker loss -> rebalance -> redelivery) that would
# produce it, and found none. That empty `HAVING COUNT(*) > 1` is the difference between
# asserting a property and proving it - the system-level version of last week's property
# tests.
#
# ACCEPTANCE CRITERIA
#   [ ] The drill kills a broker mid-traffic and the consumers rebalance + re-deliver.
#   [ ] The exactly-once query (HAVING COUNT(*) > 1) returns ZERO rows - the deliverable.
#   [ ] The DLQ stayed empty and no order was lost (orders_ok == distinct charged keys).
#   [ ] POSTMORTEM-drill-B.md explains WHY it held (idempotency key + outbox + DB
#       unique constraint), blameless, SRE-format, with owned action items.
#   [ ] You can articulate why a broker loss is the EXACT moment a double-charge would
#       happen if idempotency were broken (rebalance -> redelivery of uncommitted batch).
# -----------------------------------------------------------------------------
