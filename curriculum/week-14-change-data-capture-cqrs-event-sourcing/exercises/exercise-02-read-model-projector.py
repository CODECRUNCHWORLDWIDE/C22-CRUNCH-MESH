#!/usr/bin/env python3
# Exercise 2 — The read-model projector (idempotent CQRS projection from the CDC stream)
#
# Goal: Consume the Debezium `orders` change stream and project it into a
#       denormalized read-model table (`order_search`), and make the projection
#       IDEMPOTENT so that duplicate delivery — which WILL happen under
#       at-least-once semantics — does not corrupt the read model. This is the
#       "exactly-once processing, not delivery" promise made concrete.
#
# Estimated time: 50 minutes. Runnable.
#
# THE IDEA
#
#   Debezium emits one event per row change on topic shop.public.orders. We turn
#   each event into an UPSERT on a read-model table keyed by order_id, guarded by
#   the change's LSN so that a duplicate or out-of-order older event is ignored:
#
#       INSERT ... ON CONFLICT (order_id) DO UPDATE ... WHERE existing.lsn < new.lsn
#
#   Re-applying the same event is a no-op. That is what makes at-least-once
#   delivery yield exactly-once PROCESSING.
#
# REQUIREMENTS
#
#   * Exercise 1 running: Debezium producing to shop.public.orders.
#   * pip install "psycopg[binary]>=3.1" "confluent-kafka>=2.3"
#
# HOW TO USE THIS FILE
#
#       python3 exercise-02-read-model-projector.py \
#           --bootstrap localhost:9092 --topic shop.public.orders \
#           --dsn "host=localhost user=postgres password=postgres dbname=shop" \
#           --group projector-1
#
#   Leave it running. In another terminal, change orders in psql and watch the
#   order_search table update. To PROVE idempotency, run with --replay-twice,
#   which consumes from the beginning twice in one run; the read model must be
#   byte-identical after the second pass (the script asserts this).
#
# ACCEPTANCE CRITERIA
#
#   [ ] As you INSERT/UPDATE/DELETE orders, order_search reflects current state.
#   [ ] A DELETE event removes the row from order_search (handle op='d' + tombstone).
#   [ ] With --replay-twice, the read model checksum after pass 2 EQUALS pass 1 —
#       duplicate delivery did not corrupt it. The script prints IDEMPOTENT.
#   [ ] You can name the line that makes it idempotent (the LSN guard in the upsert).
#
# Expected output shape is at the bottom of the file.

from __future__ import annotations

import argparse
import json
import sys

try:
    import psycopg
except ImportError:
    sys.exit("psycopg v3 required: python3 -m pip install 'psycopg[binary]>=3.1'")

try:
    from confluent_kafka import Consumer, KafkaException
except ImportError:
    sys.exit("confluent-kafka required: python3 -m pip install 'confluent-kafka>=2.3'")


READ_MODEL_DDL = """
CREATE TABLE IF NOT EXISTS order_search (
    order_id    bigint PRIMARY KEY,
    customer_id bigint,
    status      text,
    total_cents bigint,
    updated_lsn bigint NOT NULL          -- the idempotency / ordering guard
);
"""

# The load-bearing statement: upsert by order_id, but ONLY apply if this event's
# LSN is newer than what we last applied. A duplicate (same LSN) or an out-of-order
# older event (smaller LSN) is silently ignored — that is idempotency.
UPSERT = """
INSERT INTO order_search (order_id, customer_id, status, total_cents, updated_lsn)
VALUES (%(order_id)s, %(customer_id)s, %(status)s, %(total_cents)s, %(lsn)s)
ON CONFLICT (order_id) DO UPDATE
SET customer_id = EXCLUDED.customer_id,
    status      = EXCLUDED.status,
    total_cents = EXCLUDED.total_cents,
    updated_lsn = EXCLUDED.updated_lsn
WHERE order_search.updated_lsn < EXCLUDED.updated_lsn;
"""

# Deletes also carry an LSN; only delete if we haven't already applied a newer event.
DELETE = """
DELETE FROM order_search
WHERE order_id = %(order_id)s AND updated_lsn < %(lsn)s;
"""


def apply_event(conn: psycopg.Connection, raw_value: bytes | None) -> str:
    """Apply one Debezium event to the read model. Returns the op for logging.

    A tombstone (null value) has no payload; it's the post-delete marker and we
    skip it because we already handled the delete from the op='d' event."""
    if raw_value is None:
        return "tombstone(skipped)"

    msg = json.loads(raw_value)
    payload = msg.get("payload", msg)        # tolerate schema-less or enveloped
    op = payload.get("op")
    source = payload.get("source", {})
    lsn = source.get("lsn") or 0

    if op in ("c", "u", "r"):
        after = payload["after"]
        params = {
            "order_id": after["order_id"],
            "customer_id": after.get("customer_id"),
            "status": after.get("status"),
            "total_cents": after.get("total_cents"),
            "lsn": lsn,
        }
        conn.execute(UPSERT, params)
    elif op == "d":
        before = payload.get("before") or {}
        # On a delete, the key is in `before` (or in the message key). Use before.
        conn.execute(DELETE, {"order_id": before.get("order_id"), "lsn": lsn})
    else:
        return f"unknown-op:{op}"
    return op


def read_model_checksum(conn: psycopg.Connection) -> str:
    """A stable fingerprint of the read model, independent of updated_lsn, so we
    can compare two runs for equality."""
    row = conn.execute(
        """
        SELECT md5(string_agg(
                   order_id || ':' || coalesce(customer_id::text,'') || ':' ||
                   coalesce(status,'') || ':' || coalesce(total_cents::text,''),
                   '|' ORDER BY order_id))
        FROM order_search;
        """
    ).fetchone()
    return (row[0] if row and row[0] else "EMPTY")


def consume_pass(consumer: Consumer, conn: psycopg.Connection,
                 max_idle_polls: int = 30) -> int:
    """Consume until the topic goes quiet for max_idle_polls polls. Returns count."""
    applied = 0
    idle = 0
    while idle < max_idle_polls:
        msg = consumer.poll(0.5)
        if msg is None:
            idle += 1
            continue
        if msg.error():
            raise KafkaException(msg.error())
        idle = 0
        op = apply_event(conn, msg.value())
        applied += 1
        if applied % 50 == 0:
            print(f"  applied {applied} events (last op={op})")
    return applied


def main() -> None:
    ap = argparse.ArgumentParser(description="Idempotent CQRS read-model projector.")
    ap.add_argument("--bootstrap", required=True)
    ap.add_argument("--topic", default="shop.public.orders")
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--group", default="projector-1")
    ap.add_argument("--replay-twice", action="store_true",
                    help="Consume from the beginning twice; assert idempotency.")
    args = ap.parse_args()

    with psycopg.connect(args.dsn, autocommit=True) as conn:
        conn.execute(READ_MODEL_DDL)

        base_conf = {
            "bootstrap.servers": args.bootstrap,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,
        }

        if args.replay_twice:
            print("== Pass 1: project the whole stream ==")
            c1 = Consumer({**base_conf, "group.id": args.group + "-a"})
            c1.subscribe([args.topic])
            n1 = consume_pass(c1, conn)
            c1.close()
            sum1 = read_model_checksum(conn)
            print(f"  pass 1: {n1} events applied, checksum={sum1[:12]}")

            print("\n== Pass 2: replay the SAME stream (duplicate delivery) ==")
            c2 = Consumer({**base_conf, "group.id": args.group + "-b"})
            c2.subscribe([args.topic])
            n2 = consume_pass(c2, conn)
            c2.close()
            sum2 = read_model_checksum(conn)
            print(f"  pass 2: {n2} events re-applied, checksum={sum2[:12]}")

            print("\n==================== IDEMPOTENCY CHECK ====================")
            if sum1 == sum2:
                print("IDEMPOTENT: read model is byte-identical after duplicate "
                      "delivery. The LSN-guarded upsert made re-application a no-op.")
            else:
                print("NOT IDEMPOTENT: checksum changed on replay. Your projection "
                      "double-applied something. Check the LSN guard in UPSERT/DELETE.")
                sys.exit(1)
            print("==========================================================")
        else:
            print(f"== Live projection: consuming {args.topic} (Ctrl+C to stop) ==")
            c = Consumer({**base_conf, "group.id": args.group})
            c.subscribe([args.topic])
            try:
                while True:
                    msg = c.poll(1.0)
                    if msg is None:
                        continue
                    if msg.error():
                        raise KafkaException(msg.error())
                    op = apply_event(conn, msg.value())
                    print(f"  applied op={op}")
            except KeyboardInterrupt:
                pass
            finally:
                c.close()


if __name__ == "__main__":
    main()


# -----------------------------------------------------------------------------
# Expected output (shape; --replay-twice)
# -----------------------------------------------------------------------------
#
# == Pass 1: project the whole stream ==
#   applied 50 events (last op=u)
#   pass 1: 73 events applied, checksum=9f2c1ab4de01
#
# == Pass 2: replay the SAME stream (duplicate delivery) ==
#   applied 50 events (last op=c)
#   pass 2: 73 events re-applied, checksum=9f2c1ab4de01
#
# ==================== IDEMPOTENCY CHECK ====================
# IDEMPOTENT: read model is byte-identical after duplicate delivery. The
# LSN-guarded upsert made re-application a no-op.
# ==========================================================
#
# The lesson: pass 2 re-applied EVERY event (73 of them again), yet the read
# model's checksum did not change. That is exactly-once PROCESSING built on top
# of at-least-once DELIVERY. Remove the `WHERE order_search.updated_lsn < ...`
# guard and re-run: the checksum will still match for upserts (upsert is naturally
# idempotent), but the guard is what protects you against OUT-OF-ORDER older
# events overwriting newer state — the subtler bug. Keep it.
# -----------------------------------------------------------------------------
