# Challenge 1 — Diagnose Three Consumer-Lag Faults on a Live Cluster

**Time estimate:** ~90 minutes.

## Problem statement

You are on call. A teammate's event pipeline "mostly works" but three things are broken in ways nobody can explain: the `orders-by-region` consumer "is way behind but only sometimes," the `inventory-sync` group "keeps restarting and never catches up," and the `audit-archive` consumer "skipped a whole day of records and nobody knows where they went." All three are real, distinct event-streaming faults across three different topics.

You will run a fault-injection harness that reproduces all three on one cluster, then **detect, diagnose, and prescribe the fix** for each, using only the introspection tools from this week. No reading the harness source until you've diagnosed all three from the outside — that's the whole point.

This mirrors the real skill: you rarely debug a lag problem in code you just wrote. You debug it on a cluster someone else built, from the outside in, with `kafka-consumer-groups.sh --describe` and a clear head.

## The harness

Save this as `faulty_pipeline.py`. It needs a reachable Kafka or Redpanda on `localhost:9092` (your exercise-1 cluster, port-forwarded, or the `docker compose` Redpanda). It creates three topics, each with exactly one planted fault, and runs a producer and a consumer group against each. Run it and leave it running while you diagnose from other terminals. **Do not read the QoS-of-Kafka choices below until you've diagnosed all three from the outside.**

```python
#!/usr/bin/env python3
"""Fault-injection harness: three topics, three planted lag faults. Do NOT read the
choices below until you have diagnosed all three from the outside."""
import json
import threading
import time

from confluent_kafka import Consumer, Producer
from confluent_kafka.admin import AdminClient, NewTopic

BOOTSTRAP = "localhost:9092"


def ensure_topics() -> None:
    admin = AdminClient({"bootstrap.servers": BOOTSTRAP})
    topics = [
        # Topic 1: orders-by-region — 6 partitions, but the producer keys by region.
        NewTopic("orders.byregion", num_partitions=6, replication_factor=1),
        # Topic 2: inventory-sync — fine topic; the FAULT is on the consumer side.
        NewTopic("inventory.sync", num_partitions=6, replication_factor=1),
        # Topic 3: audit-archive — retention is set DANGEROUSLY short.
        NewTopic("audit.archive", num_partitions=3, replication_factor=1,
                 config={"retention.ms": "10000"}),  # <-- 10 SECONDS. planted fault #3
    ]
    futures = admin.create_topics(topics)
    for t, f in futures.items():
        try:
            f.result()
        except Exception as exc:  # topic may already exist on re-run
            print(f"  ({t}: {exc})")


# --- Topic 1 producer: keys by region (low cardinality) — planted fault #1 ----------
REGIONS = ["us-east"] * 70 + ["us-west"] * 15 + ["eu"] * 10 + ["apac"] * 5  # 70% skew


def produce_orders_byregion() -> None:
    p = Producer({"bootstrap.servers": BOOTSTRAP, "acks": "all"})
    i = 0
    while True:
        region = REGIONS[i % len(REGIONS)]
        p.produce("orders.byregion", key=region,            # <-- LOW-CARDINALITY KEY
                  value=json.dumps({"order_id": f"o{i}", "region": region}))
        p.poll(0)
        i += 1
        time.sleep(0.005)  # ~200/s


def consume_orders_byregion() -> None:
    c = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": "orders-by-region",
                  "auto.offset.reset": "earliest", "enable.auto.commit": True})
    c.subscribe(["orders.byregion"])
    while True:
        msg = c.poll(1.0)
        if msg and not msg.error():
            time.sleep(0.02)  # each record takes 20ms to "process"


# --- Topic 2 consumer: slow processing + big batch — planted fault #2 ----------------
def produce_inventory() -> None:
    p = Producer({"bootstrap.servers": BOOTSTRAP, "acks": "all"})
    i = 0
    while True:
        p.produce("inventory.sync", key=f"sku-{i % 1000}",
                  value=json.dumps({"sku": f"sku-{i % 1000}", "delta": 1}))
        p.poll(0)
        i += 1
        time.sleep(0.002)


def consume_inventory() -> None:
    c = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": "inventory-sync",
                  "auto.offset.reset": "earliest", "enable.auto.commit": True,
                  "max.poll.interval.ms": 10000,    # <-- only 10s allowed between polls
                  "max.poll.records": 500})         # <-- but fetch up to 500 per poll
    c.subscribe(["inventory.sync"])
    while True:
        msgs = c.consume(num_messages=500, timeout=1.0)  # grab a big batch
        for msg in msgs:
            if msg and not msg.error():
                time.sleep(0.05)  # 500 * 50ms = 25s >> 10s max.poll.interval => EVICTED


# --- Topic 3 consumer: joins late, retention too short — planted fault #3 ------------
def produce_audit() -> None:
    p = Producer({"bootstrap.servers": BOOTSTRAP, "acks": "all"})
    i = 0
    while True:
        p.produce("audit.archive", key=f"e{i}", value=json.dumps({"event": i}))
        p.poll(0)
        i += 1
        time.sleep(0.01)


def consume_audit_late() -> None:
    time.sleep(30)  # joins 30s late; retention is 10s, so early records are GONE
    c = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": "audit-archive",
                  "auto.offset.reset": "earliest", "enable.auto.commit": True})
    c.subscribe(["audit.archive"])
    while True:
        msg = c.poll(1.0)
        if msg and not msg.error():
            pass


def main() -> None:
    ensure_topics()
    for fn in (produce_orders_byregion, consume_orders_byregion,
               produce_inventory, consume_inventory,
               produce_audit, consume_audit_late):
        threading.Thread(target=fn, daemon=True).start()
    print("faulty pipeline running. Diagnose from other terminals. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
```

```bash
pip install confluent-kafka
python3 faulty_pipeline.py
```

Your symptom panel is the lag table for each group:

```bash
for g in orders-by-region inventory-sync audit-archive; do
  echo "=== $g ==="
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group "$g"
done
```

## Your task

For **each of the three groups** (`orders-by-region`, `inventory-sync`, `audit-archive`), produce a diagnosis with these four parts:

1. **Symptom** — what's observably wrong (which partition's `LAG`, what shape the lag table has, what the consumer logs show, whether members come and go).
2. **Root cause** — the precise mechanism. Name the policy/config and the rule it breaks. (Hot key? Rebalance eviction? Retention horizon crossed?)
3. **Which Lecture concept** — tie it to Lecture 1 §2.2 (hot partition), §3.2 (`max.poll.interval.ms` eviction), or Lecture 2 §2.3 (retention gotcha).
4. **Prescription** — the exact fix, with the corrected config or key. Write the corrected line.

You must reach each diagnosis using **at least two** independent signals — e.g., the lag-table shape *and* the consumer logs, or the per-partition lag *and* `kafka-topics.sh --describe`. One signal is a guess; two is a diagnosis.

## Acceptance criteria

- [ ] A file `challenge-01-diagnosis.md` with a section per group, each containing all four parts above.
- [ ] You correctly identify the fault on each group:
  - `orders-by-region` — **hot partition**: keying by `region` (70% `us-east`) funnels most traffic to one partition; its `LAG` climbs while the other five sit near zero. Fix: key by `order_id`.
  - `inventory-sync` — **`max.poll.interval.ms` eviction**: 500 records × 50 ms = 25 s of processing exceeds the 10 s poll deadline, so the coordinator evicts the consumer, rebalances, and it reprocesses — a rebalance storm; lag never converges and members churn. Fix: lower `max.poll.records`, raise `max.poll.interval.ms`, or move slow work off the poll thread.
  - `audit-archive` — **retention horizon crossed**: the consumer joins 30 s late but `retention.ms=10000`, so the earliest records are deleted before it ever reads them; it silently starts past the gap. Fix: retention must exceed the worst consumer-join delay; alert on lag approaching the retention horizon.
- [ ] For `orders-by-region` and `inventory-sync` you captured at least one corroborating signal beyond the lag table (per-partition skew; rebalance/eviction in the consumer log).
- [ ] For `audit-archive` you can show the records are *gone*, not merely unread (the earliest available offset is greater than 0, or `kafka-get-offsets` shows the log start advanced).
- [ ] A `fixed_pipeline.py` — your corrected harness where all three groups converge to a small, bounded lag and stay there.

## The trap (read after a first attempt)

The `audit-archive` fault is the subtle one and the most dangerous in production, because it produces **no error and no incompatibility** — the consumer connects, reads, and reports a low lag, because the records it missed *no longer exist to be counted as lag*. The lag table looks almost healthy. The only tell is that the log-start offset moved past 0 (records were deleted) and the consumer's first read offset is well past where it "should" have started. Prescribing "make the consumer faster" is the wrong fix — speed was never the problem; the records were deleted by retention before the consumer arrived. **A short-retention data loss hides as a healthy-looking lag table.** That asymmetry — a lag table can look fine while data is silently gone — is the single most important operational lesson of the week.

## Stretch

- Add a fourth fault: a topic where the consumer commits **before** processing (`enable.auto.commit=True` with a long interval, then crash). Show that records are *skipped* (at-most-once by accident), and that the symptom is the opposite of `audit-archive`: lag looks fine, but downstream state is missing records the log still has.
- Re-run the whole challenge against **Redpanda** (the `docker compose` fallback) and confirm the diagnoses are identical — only the CLI changes (`rpk group describe`). Same model, different engine (Lecture 2 §1.2).
- Write a 15-line shell script that, given a group, prints just the partitions whose `LAG` exceeds a threshold, so a hot partition or a falling-behind group jumps out at a glance.

## Why this matters

At the Week 12 midterm you defend an event-driven design to a reviewer. They will not ask you to recite the config table — they'll point at a lag table on a running cluster and ask "why is this group behind, and how would you know if you were about to lose data?" This challenge *is* that conversation, rehearsed. Every event-pipeline on-call rotation eventually hands you a falling-behind consumer with a fault you can't see. The engineer who can name it from the lag table in five minutes — and who knows that a *healthy-looking* lag table can hide a retention data loss — is the one who gets paged less.
