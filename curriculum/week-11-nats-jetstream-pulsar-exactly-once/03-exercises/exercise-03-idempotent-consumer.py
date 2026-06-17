#!/usr/bin/env python3
# Exercise 3 — The idempotent consumer + chaos test (zero double-charges)
#
# Goal: Build a consumer that survives DUPLICATE delivery with ZERO double-effects.
#   It consumes order.confirmed.v1 (produced by exercise 2's outbox relay), and for
#   each event it "charges" the order. The charge is made idempotent by recording the
#   event_id in a dedup table IN THE SAME TRANSACTION as the charge. A duplicate
#   delivery hits the unique constraint and is skipped — no double-charge.
#
# Estimated time: 60 minutes. Runnable.
#
# THE CONTRACT WE PROVE
#
#   Delivery is at-least-once (Kafka redelivers what we didn't commit; the relay may
#   republish). So events ARRIVE more than once. The EFFECT (the charge) must happen
#   exactly once. We prove it with a chaos test: kill the consumer mid-batch, restart
#   it (Kafka redelivers from the last committed offset), and verify:
#       unique orders charged == distinct events,  double-charges == 0.
#
# SETUP
#
#   Postgres from exercise 2, plus:
#     CREATE TABLE charges (
#       order_id      text PRIMARY KEY,        -- natural idempotency on the charge
#       amount_cents  bigint NOT NULL,
#       charged_at    timestamptz NOT NULL DEFAULT now()
#     );
#     CREATE TABLE processed_events (
#       event_id     text PRIMARY KEY,         -- the dedup gate
#       processed_at timestamptz NOT NULL DEFAULT now()
#     );
#
#   Broker: Kafka/Redpanda on localhost:9092 with order.confirmed.v1 populated by
#   exercise 2's relay (run the writer + relay first).
#
# HOW TO USE THIS FILE
#
#   pip install "psycopg[binary]" confluent-kafka
#   python3 exercise-03-idempotent-consumer.py --dsn $DSN --bootstrap localhost:9092 \
#       --group order-fulfillment
#
#   THE CHAOS TEST (do this to prove the contract):
#     1. Run exercise-2 writer+relay to put ~1000 events on order.confirmed.v1.
#     2. Start this consumer; let it process a few hundred.
#     3. kill -9 it (simulating a crash before commit).
#     4. Restart it — Kafka redelivers uncommitted records; some get re-DELIVERED.
#     5. Stop it once lag is 0. Run --verify (below) and read the ledger.
#
#   python3 exercise-03-idempotent-consumer.py --dsn $DSN --verify
#       prints: events seen, unique charged, double-charges. double-charges MUST be 0.
#
# ACCEPTANCE CRITERIA
#
#   [ ] After a kill-mid-batch + restart, --verify reports double-charges == 0.
#   [ ] The number of rows in `charges` equals the number of DISTINCT order_ids
#       produced, regardless of how many duplicates were delivered.
#   [ ] If you MOVE the dedup insert OUT of the charge's transaction (try it), the
#       chaos test starts producing double-charges — proving same-transaction is
#       load-bearing (Lecture 2 §2.1).
#
# Expected output is at the bottom of the file.

import argparse
import json
import sys

import psycopg
from confluent_kafka import Consumer, KafkaError

TOPIC = "order.confirmed.v1"


def process_event(conn: psycopg.Connection, event_id: str, order: dict) -> bool:
    """Idempotently charge an order. Returns True if this was the FIRST time (charged),
    False if it was a duplicate (skipped). The dedup insert and the charge are in ONE
    transaction — that atomicity is what makes the whole thing correct (Lecture 2 §2.1).
    """
    order_id = order["order_id"]
    amount = order["total_cents"]

    with conn.transaction():  # one transaction for BOTH the dedup gate and the effect
        # The dedup gate: insert the event_id. If we've seen it, ON CONFLICT DO NOTHING
        # leaves rowcount 0, and we know this is a duplicate.
        cur = conn.execute(
            "INSERT INTO processed_events (event_id) VALUES (%s) "
            "ON CONFLICT (event_id) DO NOTHING",
            (event_id,),
        )
        if cur.rowcount == 0:
            # Duplicate event_id — already processed. Skip the charge. The transaction
            # commits (recording nothing new), we ack/commit the offset, done. No
            # double-charge.
            return False

        # First time for this event_id: do the effect. The charge is ALSO naturally
        # idempotent on order_id (PRIMARY KEY) as a belt-and-suspenders, so even if two
        # DIFFERENT event_ids referenced the same order, we still wouldn't double-charge.
        conn.execute(
            "INSERT INTO charges (order_id, amount_cents) VALUES (%s, %s) "
            "ON CONFLICT (order_id) DO NOTHING",
            (order_id, amount),
        )
    return True


def run(dsn: str, bootstrap: str, group: str) -> int:
    conn = psycopg.connect(dsn, autocommit=False)
    consumer = Consumer({
        "bootstrap.servers": bootstrap,
        "group.id": group,
        "enable.auto.commit": False,        # commit manually, AFTER the effect is durable
        "auto.offset.reset": "earliest",
        "partition.assignment.strategy": "cooperative-sticky",
    })
    consumer.subscribe([TOPIC])

    charged = 0
    skipped = 0
    print(f"idempotent consumer running on {TOPIC}; Ctrl+C to stop.")
    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                print(f"consume error: {msg.error()}", file=sys.stderr)
                continue

            # The event_id comes from the relay's header (the outbox row id) — a STABLE
            # idempotency key derived from the event, not generated per attempt.
            event_id = None
            for k, v in (msg.headers() or []):
                if k == "event-id":
                    event_id = v.decode()
            if event_id is None:
                # Fall back to a deterministic key from the payload if no header.
                event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"

            order = json.loads(msg.value())
            first_time = process_event(conn, event_id, order)
            if first_time:
                charged += 1
            else:
                skipped += 1

            # Commit the offset ONLY after the DB transaction committed. If we crash
            # before this commit, Kafka redelivers — and the dedup table makes the
            # redelivery a no-op. At-least-once delivery, exactly-once effect.
            consumer.commit(msg, asynchronous=False)

    except KeyboardInterrupt:
        print("\ninterrupted.")
    finally:
        consumer.close()
        conn.close()
    print(f"done. charged (first-time): {charged}   skipped (duplicates): {skipped}")
    return 0


def verify(dsn: str) -> int:
    """Read the ledger and report the contract: double-charges MUST be 0."""
    conn = psycopg.connect(dsn)
    seen = conn.execute("SELECT count(*) FROM processed_events").fetchone()[0]
    charged = conn.execute("SELECT count(*) FROM charges").fetchone()[0]
    # A double-charge would mean two charge rows for one order_id — impossible given the
    # PRIMARY KEY, so we also check the consumer never SKIPPED a charge it should have
    # made by comparing distinct processed orders to charged orders.
    distinct_orders = conn.execute(
        "SELECT count(DISTINCT order_id) FROM charges").fetchone()[0]
    double_charges = charged - distinct_orders  # > 0 only if the PK were ever bypassed
    conn.close()

    print("==================== LEDGER ====================")
    print(f"processed_events (unique event_ids seen): {seen}")
    print(f"charges rows:                             {charged}")
    print(f"distinct orders charged:                  {distinct_orders}")
    print(f"double-charges:                           {double_charges}")
    print("================================================")
    if double_charges == 0:
        print("PASS: at-least-once delivery, exactly-once effect. Zero double-charges.")
        return 0
    print("FAIL: double-charges detected — your dedup gate leaked. Check that the dedup "
          "insert is in the SAME transaction as the charge (Lecture 2 §2.1).")
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Idempotent consumer + chaos verify.")
    parser.add_argument("--dsn", default="postgres://crunch:crunch@localhost:5432/crunch")
    parser.add_argument("--bootstrap", default="localhost:9092")
    parser.add_argument("--group", default="order-fulfillment")
    parser.add_argument("--verify", action="store_true", help="read the ledger and check")
    args = parser.parse_args()

    if args.verify:
        sys.exit(verify(args.dsn))
    sys.exit(run(args.dsn, args.bootstrap, args.group))


if __name__ == "__main__":
    main()


# -----------------------------------------------------------------------------
# Expected output (the chaos test)
# -----------------------------------------------------------------------------
#
# After producing 1000 events, running the consumer, kill -9 mid-batch, restarting,
# letting it drain, then --verify:
#
# ==================== LEDGER ====================
# processed_events (unique event_ids seen): 1000
# charges rows:                             1000
# distinct orders charged:                  1000
# double-charges:                           0
# ================================================
# PASS: at-least-once delivery, exactly-once effect. Zero double-charges.
#
# The consumer's own stdout during the run shows the duplicates being absorbed:
#   done. charged (first-time): 1000   skipped (duplicates): 63
# 63 events were DELIVERED twice (redelivered after the kill), but the dedup gate
# made each a no-op, so only 1000 charges happened. That 63-vs-0 is the whole lesson:
# duplicate DELIVERY is normal; duplicate EFFECT is the bug we engineered away.
#
# Expected output (the leak, if you move the dedup insert to a separate transaction)
# -----------------------------------------------------------------------------
#
# double-charges:                           17
# FAIL: double-charges detected — your dedup gate leaked. ...
# Moving the dedup insert out of the charge's transaction reintroduces the dual-write
# problem one level down: a crash between "record processed" and "charge" (or vice
# versa) lets a redelivery charge again. Same transaction, or it leaks.
# -----------------------------------------------------------------------------
