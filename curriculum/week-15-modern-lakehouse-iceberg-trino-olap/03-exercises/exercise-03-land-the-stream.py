#!/usr/bin/env python3
# Exercise 3 — Land the change stream in Iceberg
#
# Goal: Close the loop from Weeks 13-15. Consume the Debezium `orders` change
#       stream (Week 14) and APPEND each change event into an Apache Iceberg table
#       using PyIceberg, so the same events feeding your read model also land in
#       the lakehouse for analytics. Then you query them in Trino. This is the
#       syllabus lab: "a second consumer that writes the same events to Iceberg."
#
# Estimated time: 50 minutes. Runnable.
#
# THE IDEA
#
#   The change stream is the single source; Week 14 fanned it into a read model
#   and an event store; here we fan it into Iceberg. Each Debezium event becomes
#   one row in an append-only Iceberg table, keyed/ordered by the change LSN.
#   Analytics (Exercise 2) then run on the lakehouse, off the OLTP primary.
#
# REQUIREMENTS
#
#   * Exercise 1's lakehouse up (MinIO + Iceberg REST catalog at :8181).
#   * Week 14's Debezium pipeline producing to shop.public.orders
#     (OR use --fake to generate synthetic change events with no Kafka).
#   * pip install "pyiceberg[s3fs,pyarrow]>=0.6" "confluent-kafka>=2.3"
#
# HOW TO USE THIS FILE
#
#   With the real change stream:
#       python3 exercise-03-land-the-stream.py \
#           --catalog-uri http://localhost:8181 \
#           --bootstrap localhost:9092 --topic shop.public.orders
#
#   With synthetic events (no Kafka needed):
#       python3 exercise-03-land-the-stream.py \
#           --catalog-uri http://localhost:8181 --fake 500
#
#   Then query in Trino:
#       SELECT op, count(*) FROM iceberg.shop.orders_events GROUP BY op;
#
# ACCEPTANCE CRITERIA
#
#   [ ] The script creates iceberg.shop.orders_events (partitioned by month) if
#       it doesn't exist.
#   [ ] It appends change events as rows; a query in Trino shows them grouped by op.
#   [ ] Re-running does not require recreating the table; it appends a new snapshot.
#   [ ] You can run the Exercise 2 rollup against orders_events and get results —
#       proving the analytics now live in the lakehouse, not on the OLTP primary.
#
# Expected output is at the bottom of the file.

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timedelta, timezone

try:
    import pyarrow as pa
    from pyiceberg.catalog import load_catalog
    from pyiceberg.exceptions import NoSuchTableError
    from pyiceberg.schema import Schema
    from pyiceberg.types import (
        LongType, NestedField, StringType, TimestampType,
    )
    from pyiceberg.partitioning import PartitionSpec, PartitionField
    from pyiceberg.transforms import MonthTransform
except ImportError:
    sys.exit('PyIceberg required: pip install "pyiceberg[s3fs,pyarrow]>=0.6"')

NAMESPACE = "shop"
TABLE = "orders_events"
FULL_NAME = f"{NAMESPACE}.{TABLE}"

# The Iceberg schema for landed change events. field IDs are explicit (Iceberg
# tracks columns by ID, which is what makes schema evolution cheap — Lecture 1).
ICEBERG_SCHEMA = Schema(
    NestedField(1, "order_id", LongType(), required=False),
    NestedField(2, "customer_id", LongType(), required=False),
    NestedField(3, "status", StringType(), required=False),
    NestedField(4, "total_cents", LongType(), required=False),
    NestedField(5, "op", StringType(), required=False),
    NestedField(6, "lsn", LongType(), required=False),
    NestedField(7, "created_at", TimestampType(), required=False),
)

# Arrow schema must match, for the append batches.
ARROW_SCHEMA = pa.schema([
    ("order_id", pa.int64()),
    ("customer_id", pa.int64()),
    ("status", pa.string()),
    ("total_cents", pa.int64()),
    ("op", pa.string()),
    ("lsn", pa.int64()),
    ("created_at", pa.timestamp("us")),
])


def get_catalog(uri: str):
    """Connect to the Iceberg REST catalog backed by MinIO (matches Exercise 1)."""
    return load_catalog(
        "rest",
        **{
            "type": "rest",
            "uri": uri,
            "s3.endpoint": "http://localhost:9000",
            "s3.access-key-id": "minio",
            "s3.secret-access-key": "minio12345",
            "s3.path-style-access": "true",
        },
    )


def ensure_table(catalog):
    """Create the namespace and table (partitioned by month(created_at)) if absent."""
    try:
        catalog.create_namespace(NAMESPACE)
    except Exception:
        pass  # already exists
    try:
        return catalog.load_table(FULL_NAME)
    except NoSuchTableError:
        spec = PartitionSpec(
            PartitionField(source_id=7, field_id=1000,
                           transform=MonthTransform(), name="created_at_month")
        )
        return catalog.create_table(FULL_NAME, schema=ICEBERG_SCHEMA, partition_spec=spec)


def row_from_debezium(value: bytes | None) -> dict | None:
    """Turn one Debezium change event into a row dict, or None to skip (tombstone)."""
    if value is None:
        return None  # tombstone — already represented by the op='d' event
    msg = json.loads(value)
    payload = msg.get("payload", msg)
    op = payload.get("op")
    src = payload.get("source", {})
    lsn = src.get("lsn") or 0
    # On delete, the row identity is in `before`; otherwise in `after`.
    rec = payload.get("after") or payload.get("before") or {}
    created = rec.get("created_at")
    # Debezium may emit created_at as microseconds-since-epoch (int) or a string.
    if isinstance(created, (int, float)):
        ts = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=created)
    elif isinstance(created, str):
        ts = datetime.fromisoformat(created.replace("Z", "+00:00"))
    else:
        ts = datetime.now(timezone.utc)
    return {
        "order_id": rec.get("order_id"),
        "customer_id": rec.get("customer_id"),
        "status": rec.get("status"),
        "total_cents": rec.get("total_cents"),
        "op": op,
        "lsn": lsn,
        "created_at": ts.replace(tzinfo=None),  # Iceberg TimestampType is naive UTC
    }


def fake_events(n: int):
    """Generate synthetic change events when there's no Kafka to read."""
    base = datetime(2026, 1, 1)
    ops = ["c", "c", "c", "u", "d"]
    statuses = ["PLACED", "SHIPPED", "DELIVERED", "CANCELLED"]
    for i in range(n):
        yield {
            "order_id": i + 1,
            "customer_id": random.randint(1, 1000),
            "status": random.choice(statuses),
            "total_cents": random.randint(100, 50000),
            "op": random.choice(ops),
            "lsn": 1000 + i,
            "created_at": base + timedelta(days=random.randint(0, 364),
                                           seconds=random.randint(0, 86399)),
        }


def append_rows(table, rows: list[dict]) -> int:
    """Append a batch of rows as one Iceberg snapshot."""
    if not rows:
        return 0
    batch = pa.Table.from_pylist(rows, schema=ARROW_SCHEMA)
    table.append(batch)
    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description="Land the orders change stream in Iceberg.")
    ap.add_argument("--catalog-uri", default="http://localhost:8181")
    ap.add_argument("--bootstrap")
    ap.add_argument("--topic", default="shop.public.orders")
    ap.add_argument("--fake", type=int, default=0,
                    help="Generate N synthetic events instead of reading Kafka.")
    ap.add_argument("--batch", type=int, default=200)
    args = ap.parse_args()

    catalog = get_catalog(args.catalog_uri)
    table = ensure_table(catalog)
    print(f"== Iceberg table ready: iceberg.{FULL_NAME} ==")

    total = 0
    buffer: list[dict] = []

    if args.fake:
        print(f"== Generating {args.fake} synthetic change events ==")
        for row in fake_events(args.fake):
            buffer.append(row)
            if len(buffer) >= args.batch:
                total += append_rows(table, buffer)
                buffer = []
        total += append_rows(table, buffer)
        print(f"  appended {total} rows in snapshots of up to {args.batch}.")
    else:
        if not args.bootstrap:
            sys.exit("--bootstrap required unless --fake is given")
        try:
            from confluent_kafka import Consumer, KafkaException
        except ImportError:
            sys.exit('confluent-kafka required: pip install "confluent-kafka>=2.3"')

        print(f"== Consuming {args.topic} and landing into Iceberg (Ctrl+C to stop) ==")
        c = Consumer({
            "bootstrap.servers": args.bootstrap,
            "group.id": "iceberg-lander",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,
        })
        c.subscribe([args.topic])
        idle = 0
        try:
            while idle < 20:
                msg = c.poll(0.5)
                if msg is None:
                    if buffer:
                        total += append_rows(table, buffer)
                        buffer = []
                    idle += 1
                    continue
                if msg.error():
                    raise KafkaException(msg.error())
                idle = 0
                row = row_from_debezium(msg.value())
                if row is not None:
                    buffer.append(row)
                if len(buffer) >= args.batch:
                    total += append_rows(table, buffer)
                    buffer = []
            total += append_rows(table, buffer)
        except KeyboardInterrupt:
            total += append_rows(table, buffer)
        finally:
            c.close()
        print(f"  landed {total} change events into iceberg.{FULL_NAME}.")

    print("\nNow query it in Trino:")
    print("  SELECT op, count(*) FROM iceberg.shop.orders_events GROUP BY op;")
    print("  SELECT date_trunc('month', created_at) m, sum(total_cents)/100.0")
    print("  FROM iceberg.shop.orders_events WHERE op IN ('c','r') GROUP BY 1 ORDER BY 1;")


if __name__ == "__main__":
    main()


# -----------------------------------------------------------------------------
# Expected output (shape; --fake 500)
# -----------------------------------------------------------------------------
#
# == Iceberg table ready: iceberg.shop.orders_events ==
# == Generating 500 synthetic change events ==
#   appended 500 rows in snapshots of up to 200.
#
# Now query it in Trino:
#   SELECT op, count(*) FROM iceberg.shop.orders_events GROUP BY op;
#   ...
#
# Then, in the Trino CLI:
#
#   trino> SELECT op, count(*) FROM iceberg.shop.orders_events GROUP BY op;
#    op | _col1
#   ----+-------
#    c  |   ~300
#    u  |   ~100
#    d  |   ~100
#
#   trino> SELECT date_trunc('month', created_at) AS m, sum(total_cents)/100.0
#          FROM iceberg.shop.orders_events WHERE op IN ('c','r') GROUP BY 1 ORDER BY 1;
#    -- 12 monthly revenue rows, computed in the LAKEHOUSE, not on Postgres.
#
# The lesson: the SAME change stream that feeds your read model (Week 14) now also
# feeds the lakehouse. Analytics run here, on a column-store query engine, without
# ever touching — or polluting the cache of — your OLTP primary. That is the
# OLTP/OLAP boundary, made real with your own data.
# -----------------------------------------------------------------------------
