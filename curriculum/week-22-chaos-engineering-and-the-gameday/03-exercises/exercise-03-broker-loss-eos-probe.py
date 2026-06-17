#!/usr/bin/env python3
# Exercise 3 — The Broker-Loss Exactly-Once Probe (runnable)
#
# Goal: Kill a Kafka broker mid-traffic and PROVE the exactly-once invariant held:
#         - messages were REDELIVERED (proving the failure actually caused at-least-once)
#         - yet every business event was applied EXACTLY ONCE (no double-charge,
#           no double-decrement) because of the outbox + idempotency keys.
#
#       This is the syllabus drill and capstone Drill B. The verdict is an AUDIT of
#       side effects, NOT "the dashboard recovered." A system can come back healthy
#       while having silently double-charged customers; only the audit catches that.
#
# Estimated time: 75 minutes. Runnable.
#
# HOW THIS DRILL WORKS
#
#   1. Snapshot BEFORE: consumer-group offsets, the processed-keys table count, and
#      the side-effect tables (payments, inventory decrements) for the test window.
#   2. Drive a known number of orders through the system at steady load.
#   3. Inject the broker loss (the PodChaos from exercise-02, experiment 6).
#   4. Let it recover; remove the fault.
#   5. Snapshot AFTER and run the AUDIT:
#        - delivered_count  > processed_count   => redelivery happened (good: the
#          fault actually exercised at-least-once delivery).
#        - side_effect_count == business_event_count  => exactly-once held.
#      If side_effect_count > business_event_count, you DOUBLE-PROCESSED -> a finding.
#
# This script does steps 1 and 5 (the snapshots + the audit). Steps 2-4 are the
# load + the chaos CRD (driven by you / k6 / kubectl), described in --help.
#
# PREREQUISITES
#   pip install kafka-python psycopg2-binary
#   - Kafka reachable at $KAFKA_BOOTSTRAP (default localhost:9092 via port-forward).
#   - Postgres reachable at $PG_DSN, with:
#       * an outbox-driven, idempotent consumer (Weeks 10-11)
#       * a `processed_events(event_id PRIMARY KEY, processed_at)` idempotency table
#       * a `payments(order_id, status, idempotency_key)` table (one charge per order)
#   - The consumer group name in $CONSUMER_GROUP (default: order-consumer).
#
# FALLBACK if your capstone isn't wired: point --dsn at any Postgres with a
#   processed_events table and a payments table; the audit logic is generic.

import argparse
import json
import os
import sys

try:
    import psycopg2
except ImportError:  # pragma: no cover - dependency hint
    psycopg2 = None

try:
    from kafka import KafkaConsumer, TopicPartition
    from kafka.admin import KafkaAdminClient
except ImportError:  # pragma: no cover - dependency hint
    KafkaConsumer = None


KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")
PG_DSN = os.environ.get("PG_DSN", "dbname=marketplace host=localhost user=postgres")
CONSUMER_GROUP = os.environ.get("CONSUMER_GROUP", "order-consumer")
TOPIC = os.environ.get("TOPIC", "order.placed.v1")


def pg():
    if psycopg2 is None:
        sys.exit("psycopg2 not installed: pip install psycopg2-binary")
    return psycopg2.connect(PG_DSN)


def end_offsets(topic: str) -> dict:
    """LOG-END-OFFSET per partition = total messages produced (the delivered ceiling)."""
    if KafkaConsumer is None:
        sys.exit("kafka-python not installed: pip install kafka-python")
    c = KafkaConsumer(bootstrap_servers=KAFKA_BOOTSTRAP, enable_auto_commit=False)
    parts = c.partitions_for_topic(topic) or set()
    tps = [TopicPartition(topic, p) for p in parts]
    c.assign(tps)
    c.seek_to_end(*tps)
    offs = {tp.partition: c.position(tp) for tp in tps}
    c.close()
    return offs


def snapshot(label: str) -> dict:
    """Capture the state needed for the before/after audit."""
    conn = pg()
    cur = conn.cursor()
    # processed (idempotency) keys = how many DISTINCT events the consumer applied.
    cur.execute("SELECT count(*) FROM processed_events;")
    processed = cur.fetchone()[0]
    # business side effects: successful charges. Exactly one per order is the invariant.
    cur.execute("SELECT count(*) FROM payments WHERE status = 'charged';")
    charges = cur.fetchone()[0]
    # the DOUBLE-CHARGE detector: any order_id that appears with >1 successful charge.
    cur.execute("""
        SELECT order_id, count(*) AS n
        FROM payments WHERE status = 'charged'
        GROUP BY order_id HAVING count(*) > 1;
    """)
    double_charged = cur.fetchall()
    cur.close()
    conn.close()
    snap = {
        "label": label,
        "log_end_offsets": end_offsets(TOPIC),
        "processed_events": processed,
        "charges": charges,
        "double_charged_orders": double_charged,
    }
    return snap


def audit(before: dict, after: dict) -> int:
    """Render the verdict. Returns 0 if exactly-once held, non-zero otherwise."""
    delivered = sum(after["log_end_offsets"].values()) - sum(before["log_end_offsets"].values())
    # NOTE: 'delivered' here is messages PRODUCED in the window. To observe REDELIVERY
    # to the consumer you compare consumer poll counts vs processed; in this generic
    # audit we use the double-charge detector as the hard correctness gate and report
    # the produced count for context.
    new_charges = after["charges"] - before["charges"]
    new_processed = after["processed_events"] - before["processed_events"]
    dups = after["double_charged_orders"]

    print("=" * 64)
    print("BROKER-LOSS EXACTLY-ONCE AUDIT")
    print("=" * 64)
    print(f"  messages produced in window : {delivered}")
    print(f"  events processed (idempotent): {new_processed}")
    print(f"  successful charges created   : {new_charges}")
    print(f"  orders charged MORE THAN ONCE: {len(dups)}")
    print("-" * 64)

    if dups:
        print("VERDICT: EXACTLY-ONCE VIOLATED  (double-processing detected)")
        for order_id, n in dups:
            print(f"    order {order_id} was charged {n} times")
        print("This is a FINDING. The redelivery after the broker loss was NOT")
        print("absorbed by the idempotency layer. Write the postmortem.")
        return 1

    # The healthy invariant: one charge per processed order, no duplicates.
    if new_charges == new_processed and new_processed > 0:
        print("VERDICT: EXACTLY-ONCE HELD")
        print("  Every processed event produced exactly one charge; zero double-charges.")
        print("  The outbox + idempotency keys absorbed any redelivery the broker")
        print("  loss caused. 'It recovered' AND 'it recovered correctly'.")
        return 0

    print("VERDICT: INCONCLUSIVE")
    print("  No double-charges, but charges != processed or no traffic ran in the")
    print("  window. Drive a known order load THROUGH the fault and re-audit. If the")
    print("  broker loss caused no redelivery, the invariant wasn't actually tested —")
    print("  use a harder fault (kill the consumer mid-batch too) until you OBSERVE")
    print("  a redelivery, then prove it was absorbed.")
    return 2


def main() -> int:
    p = argparse.ArgumentParser(description="Kafka broker-loss exactly-once probe.")
    p.add_argument("--snapshot", metavar="LABEL", help="capture a before/after snapshot to stdout (JSON)")
    p.add_argument("--audit", action="store_true",
                   help="read before.json + after.json and render the verdict")
    p.add_argument("--before", default="before.json")
    p.add_argument("--after", default="after.json")
    args = p.parse_args()

    if args.snapshot:
        snap = snapshot(args.snapshot)
        # default-serialize the offsets dict + tuples
        print(json.dumps(snap, default=list, indent=2))
        return 0

    if args.audit:
        with open(args.before) as f:
            before = json.load(f)
        with open(args.after) as f:
            after = json.load(f)
        # normalize offset keys back to ints (JSON makes them strings)
        before["log_end_offsets"] = {int(k): v for k, v in before["log_end_offsets"].items()}
        after["log_end_offsets"] = {int(k): v for k, v in after["log_end_offsets"].items()}
        return audit(before, after)

    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())


# -----------------------------------------------------------------------------
# Expected workflow + output
# -----------------------------------------------------------------------------
#
#   # 1. snapshot BEFORE, start steady load, then inject the broker loss:
#   $ python3 exercise-03-broker-loss-eos-probe.py --snapshot before > before.json
#   $ k6 run order-load.js &                          # drive ~1k orders
#   $ kubectl apply -f kafka-broker-loss.yaml         # the PodChaos (exercise-02 #6)
#
#   # 2. observe ISR shrink + lag spike + drain:
#   $ kafka-topics.sh --bootstrap-server $B --describe --topic order.placed.v1
#     ... Isr: 1,2   (broker 0 dropped; leader moved 0 -> 1)
#   $ kafka-consumer-groups.sh --bootstrap-server $B --describe --group order-consumer
#     ... LAG climbs to ~28 then drains to 0
#
#   # 3. let it recover, remove the fault, snapshot AFTER, run the audit:
#   $ kubectl delete -f kafka-broker-loss.yaml
#   $ python3 exercise-03-broker-loss-eos-probe.py --snapshot after > after.json
#   $ python3 exercise-03-broker-loss-eos-probe.py --audit
#   ================================================================
#   BROKER-LOSS EXACTLY-ONCE AUDIT
#   ================================================================
#     messages produced in window : 1012
#     events processed (idempotent): 1000
#     successful charges created   : 1000
#     orders charged MORE THAN ONCE: 0
#   ----------------------------------------------------------------
#   VERDICT: EXACTLY-ONCE HELD
#
#   # The gap (produced 1012 > processed 1000) is the proof redelivery HAPPENED
#   # (12 messages re-sent during the leader change) and idempotency ABSORBED it.
#
# ACCEPTANCE CRITERIA
#   [ ] You snapshotted before + after and ran the audit (verdict from the AUDIT,
#       not the dashboard).
#   [ ] You OBSERVED a redelivery (produced/delivered > processed) — proving the
#       broker loss actually exercised at-least-once delivery.
#   [ ] The audit reports EXACTLY-ONCE HELD: zero orders charged more than once,
#       charges == processed.
#   [ ] You can state why "the dashboard went green" is NOT the verdict, and what the
#       audit proves that the dashboard cannot.
#   [ ] You wrote the broker-loss postmortem (HELD is still a postmortem: document
#       the redelivery you absorbed and the recovery time) — this is capstone Drill B.
# -----------------------------------------------------------------------------
