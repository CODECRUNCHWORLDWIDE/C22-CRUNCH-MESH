#!/usr/bin/env python3
# Exercise 3 — The order consumer group (manual commits, rebalance callbacks, fan-out)
#
# Goal: Build a CORRECT Kafka consumer group in Python for order.placed.v1. Correct means:
#   * a NAMED group.id so several instances cooperate and partitions are shared,
#   * manual offset commits AFTER processing (at-least-once, Lecture 1 §5.2) — never
#     enable.auto.commit, which commits on a timer regardless of whether you finished,
#   * cooperative-sticky assignment with on_assign/on_revoke callbacks so a rebalance
#     does not stop the world (Lecture 1 §3.1),
#   * graceful shutdown that commits what it finished and closes the group cleanly.
#
# Estimated time: 60 minutes. Runnable.
#
# HOW TO USE THIS FILE
#
#   pip install confluent-kafka
#   python3 exercise-03-order-consumer.py --bootstrap localhost:9092 --group order-fulfillment
#
#   PART A — the basic group (run after exercise 2 has produced some orders):
#     One instance reads ALL 12 partitions. Watch it process and commit.
#
#   PART B — cooperative rebalance (two terminals, same --group):
#     Start a second instance with the SAME --group. Watch the on_assign/on_revoke
#     callbacks fire and the 12 partitions split ~6/6 between the two — WITHOUT a
#     stop-the-world freeze, because of cooperative-sticky.
#
#   PART C — fan-out (a third terminal, DIFFERENT --group, e.g. order-analytics):
#     It reads EVERY record independently, at its own offsets, not stealing any
#     partition from order-fulfillment. That is free fan-out (Lecture 1 §3).
#
#   PART D — at-least-once redelivery on purpose (--crash-after N):
#     Process N records, then exit HARD before committing. Restart: the same records
#     are redelivered, because the offset was never committed. This is at-least-once
#     doing exactly what it promises — and why the consumer must be idempotent.
#
# Verify the lag table while it runs (the "the offset advanced" promise):
#   kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
#       --describe --group order-fulfillment
#
# ACCEPTANCE CRITERIA
#
#   [ ] One instance reads all 12 partitions; CURRENT-OFFSET advances to LOG-END,
#       LAG goes to ~0 in the lag table.
#   [ ] A second instance with the same group triggers on_revoke/on_assign and the
#       partitions split; the lag table shows two CONSUMER-IDs.
#   [ ] A third instance with a different group reads every record independently
#       (its own LAG, unaffected by the first group).
#   [ ] --crash-after 10 then restart: the same ~10 records are redelivered (you'll
#       see duplicate order_ids in the log), proving at-least-once.
#
# Expected output is at the bottom of the file.

import argparse
import json
import signal
import sys

from confluent_kafka import Consumer, KafkaError, TopicPartition

TOPIC = "order.placed.v1"


class OrderConsumer:
    def __init__(self, bootstrap: str, group: str, crash_after: int | None) -> None:
        self.crash_after = crash_after
        self.processed = 0
        self.running = True

        # enable.auto.commit=False is the load-bearing line. With auto-commit ON, the
        # client commits offsets on a 5s timer whether or not your processing finished
        # — turning a crash into SKIPPED records (at-most-once by accident). We commit
        # manually, AFTER the work, to get honest at-least-once.
        self.consumer = Consumer({
            "bootstrap.servers": bootstrap,
            "group.id": group,
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",   # a brand-new group reads from the start
            "partition.assignment.strategy": "cooperative-sticky",  # Lecture 1 §3.1
            "max.poll.interval.ms": 300000,    # 5 min: must poll() at least this often
            "session.timeout.ms": 45000,
            "client.id": f"order-consumer-{group}",
        })

        # Subscribe with rebalance callbacks so we can SEE the cooperative protocol and
        # commit on revoke (so we don't lose progress when a partition moves away).
        self.consumer.subscribe(
            [TOPIC],
            on_assign=self._on_assign,
            on_revoke=self._on_revoke,
        )

    def _on_assign(self, consumer, partitions: list[TopicPartition]) -> None:
        parts = sorted(p.partition for p in partitions)
        print(f"[REBALANCE] assigned partitions: {parts}")
        # With cooperative-sticky the client incrementally adds these; we don't need to
        # manually assign. We just log to make the protocol visible.

    def _on_revoke(self, consumer, partitions: list[TopicPartition]) -> None:
        parts = sorted(p.partition for p in partitions)
        print(f"[REBALANCE] revoking partitions: {parts} — committing progress first")
        # Commit synchronously before the partitions leave us, so the next owner
        # resumes exactly where we stopped (minimizing redelivery on a clean handoff).
        try:
            consumer.commit(asynchronous=False)
        except Exception as exc:  # noqa: BLE001 - best-effort on revoke
            print(f"[REBALANCE] commit on revoke failed (will redeliver): {exc}")

    def _process(self, order: dict) -> None:
        # The "work". In the capstone this reserves inventory and drives payment. Here
        # we just print. CRITICAL: this must be IDEMPOTENT, because at-least-once means
        # this runs again on any record we processed-but-didn't-commit before a crash.
        # An idempotent version would upsert keyed by order_id, or check a dedup store.
        print(f"  processed order_id={order.get('order_id')} "
              f"total_cents={order.get('total_cents')}")

    def run(self) -> int:
        print(f"consuming {TOPIC}; Ctrl+C to stop cleanly.")
        try:
            while self.running:
                msg = self.consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue  # reached end of a partition; normal, keep polling
                    print(f"consume error: {msg.error()}", file=sys.stderr)
                    continue

                try:
                    order = json.loads(msg.value())
                except json.JSONDecodeError:
                    # Poison record: log and SKIP by committing past it, rather than
                    # looping forever. A real system routes it to a dead-letter topic.
                    print(f"poison record at {msg.topic()}[{msg.partition()}]@"
                          f"{msg.offset()} — skipping", file=sys.stderr)
                    self.consumer.commit(msg, asynchronous=False)
                    continue

                self._process(order)
                self.processed += 1

                # Commit AFTER processing. We commit the offset of THIS message + 1
                # (the next offset to read) — confluent-kafka's commit(message=...)
                # handles the +1 for us. Manual, synchronous-on-shutdown, async here
                # for throughput.
                self.consumer.commit(msg, asynchronous=True)

                # Part D: crash on purpose BEFORE the async commit can flush, to
                # demonstrate at-least-once redelivery.
                if self.crash_after is not None and self.processed >= self.crash_after:
                    print(f"\n--crash-after {self.crash_after} reached: exiting HARD "
                          f"before commits flush. Restart me to see redelivery.")
                    # os._exit skips the finally block AND the commit flush on purpose.
                    import os
                    os._exit(0)

        except KeyboardInterrupt:
            print("\ninterrupted — committing and closing cleanly...")
        finally:
            # Clean shutdown: synchronous final commit, then close (which leaves the
            # group and triggers a cooperative rebalance for the remaining members).
            try:
                self.consumer.commit(asynchronous=False)
            except Exception:  # noqa: BLE001 - nothing to commit is fine
                pass
            self.consumer.close()
        print(f"done. processed {self.processed} records.")
        return 0

    def stop(self, *_: object) -> None:
        self.running = False


def main() -> None:
    parser = argparse.ArgumentParser(description="order.placed.v1 consumer group.")
    parser.add_argument("--bootstrap", default="localhost:9092")
    parser.add_argument("--group", default="order-fulfillment",
                        help="same group = share partitions; different group = fan-out")
    parser.add_argument("--crash-after", type=int, default=None,
                        help="process N records then exit hard before commit (Part D)")
    args = parser.parse_args()

    consumer = OrderConsumer(args.bootstrap, args.group, args.crash_after)
    signal.signal(signal.SIGTERM, consumer.stop)
    sys.exit(consumer.run())


if __name__ == "__main__":
    main()


# -----------------------------------------------------------------------------
# Expected output (Part A — one instance, after exercise 2 produced 100 orders)
# -----------------------------------------------------------------------------
#
# consuming order.placed.v1; Ctrl+C to stop cleanly.
# [REBALANCE] assigned partitions: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
#   processed order_id=order-481920 total_cents=12044
#   processed order_id=order-002188 total_cents=499
#   ... (100 lines) ...
#
# Lag table after it catches up:
#   GROUP             TOPIC            PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
#   order-fulfillment order.placed.v1  0          7               7               0
#   ...                                                                            0
#
# Expected output (Part B — a SECOND instance, same --group, starts)
# -----------------------------------------------------------------------------
#
# On the FIRST instance:
#   [REBALANCE] revoking partitions: [6, 7, 8, 9, 10, 11] — committing progress first
#   [REBALANCE] assigned partitions: [0, 1, 2, 3, 4, 5]
# On the SECOND instance:
#   [REBALANCE] assigned partitions: [6, 7, 8, 9, 10, 11]
# Note: ONLY the moved partitions were revoked, not all 12 — cooperative-sticky did
# NOT stop the world. The lag table now shows two CONSUMER-IDs.
#
# Expected output (Part D — --crash-after 10, then restart)
# -----------------------------------------------------------------------------
#
# First run:
#   processed order_id=order-481920 ...   (x10)
#   --crash-after 10 reached: exiting HARD before commits flush. ...
# Second run (restart, same group):
#   processed order_id=order-481920 ...   <-- SAME ids reappear: at-least-once redelivery
# The records processed-but-not-committed are delivered AGAIN. This is not a bug; it is
# the at-least-once contract. The fix is an IDEMPOTENT _process() — which is Week 11.
# -----------------------------------------------------------------------------
