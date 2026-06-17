# Week 10 Homework

Six problems that revisit the week's topics and force the eventing literacy into your fingers. The full set should take about **5 hours**. Work in your Week 10 Git repository (the same workspace as the exercises and the `order-events` mini-project) so every problem produces at least one commit you can point to at the Week 12 midterm.

The headline deliverable is **Problem 4 — the one-page partitioning-and-retention design memo**, the artifact a reviewer reads, not a journal entry.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

Have a Kafka or Redpanda reachable on `localhost:9092` (your exercise-1 Strimzi cluster, port-forwarded, or the `docker compose` Redpanda). Problems 1, 2, 5, and 6 run against it. If the cluster is broken, the single-node `docker compose` Redpanda is your fallback; say so in your writeup.

---

## Problem 1 — The topic audit table

**Problem statement.** Create three topics with deliberately different shapes: `order.placed.v1` (12 partitions, RF 3 if you can, `cleanup.policy=delete`, 7-day retention), `cart.changelog` (12 partitions, `cleanup.policy=compact`), and `clickstream.v1` (24 partitions, 1-hour retention). Then run `kafka-topics.sh --describe` (or `rpk topic describe`) against each and build a markdown table in `notes/week-10/topic-audit.md` with one row per topic and these columns:

| Topic | Partitions | RF | Cleanup policy | Retention | Class (your call) | Why this shape? |
|---|---|---|---|---|---|---|

The **Class** column is your judgement — `event stream` or `changelog`. The **Why this shape?** column is one sentence justifying the partition count and retention from the topic's purpose.

**Acceptance criteria.**

- `notes/week-10/topic-audit.md` exists with one row per topic (at least three rows).
- Every row's partition/RF/cleanup/retention columns come from real `--describe` output, not from memory.
- Each `Why this shape?` cell ties the partition count to throughput/parallelism and the retention/cleanup to the stream-vs-changelog decision (Lecture 2 §2).
- Committed.

**Hint.** `cart.changelog` is a changelog → compact; `order.placed.v1` and `clickstream.v1` are event streams → delete. Clickstream is high-volume and short-lived, so more partitions and short retention. Pipe the loop: `for t in order.placed.v1 cart.changelog clickstream.v1; do echo "=== $t ==="; kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic "$t"; done > /tmp/topics.txt` and transcribe.

**Estimated time.** 40 minutes.

---

## Problem 2 — Prove per-key ordering and prove repartitioning breaks it

**Problem statement.** Using the exercise-2 Go producer (or `kafka-console-producer.sh --property parse.key=true`), produce five records all keyed `order-A` to a 6-partition topic. With `kafka-console-consumer.sh --property print.partition=true` (or `rpk topic consume`), confirm all five landed on the **same** partition and in order. Then `kafka-topics.sh --alter --partitions 12`, produce five **more** `order-A` records, and show that the new records land on a **different** partition than the old ones — proving the key→partition mapping shifted (Lecture 1 §2.4).

**Acceptance criteria.**

- A `notes/week-10/key-ordering.md` records: the partition all five original `order-A` records landed on, and the (different) partition the post-`--alter` records land on.
- You state, in one sentence, why this means repartitioning a *keyed* topic is a data migration, not a knob.
- Committed.

**Hint.** `murmur2("order-A") % 6` and `murmur2("order-A") % 12` are almost always different partitions. `kafka-console-consumer.sh --from-beginning --property print.partition=true --property print.key=true` shows the partition for each record. If they happen to coincide for `order-A`, try `order-B` — the point holds for some key.

**Estimated time.** 45 minutes.

---

## Problem 3 — Reproduce the data-loss matrix

**Problem statement.** This is a thought-and-experiment problem. On a 3-broker cluster (or reason it through carefully if you only have one node), for each row of Lecture 1 §4.3's data-loss matrix, write down whether an acknowledged write can be lost and *why*, in your own words. Then **verify the `acks=all` + `min.insync.replicas=2` row experimentally**: stop two of the three brokers so the ISR shrinks to 1, attempt an `acks=all` produce, and capture the broker's `NotEnoughReplicas` rejection — proving the broker refuses a write it cannot make durable.

**Acceptance criteria.**

- `notes/week-10/data-loss-matrix.md` reproduces the four-row matrix with your own one-line explanation per row.
- You captured the `NotEnoughReplicasException` / `NOT_ENOUGH_REPLICAS` error from an `acks=all` produce against a 1-member ISR (paste the error).
- You explain in one sentence why a rejected write is *better* than an accepted-then-lost write.
- Committed.

**Hint.** Stop brokers with `kubectl -n kafka delete pod` (Strimzi will restart them, so move fast) or `docker stop` on a multi-node compose. The Go producer with `-acks all` against a degraded cluster will surface the delivery-report error; print it. The whole lesson: `min.insync.replicas` turns silent data loss into a loud, recoverable rejection.

**Estimated time.** 1 hour.

---

## Problem 4 — The partitioning-and-retention design memo (headline deliverable)

**Problem statement.** This is the syllabus-style headline deliverable. For the capstone's `order.placed.v1` topic, write a one-page design memo at `notes/week-10/order-topic-design.md` that **decides and defends** the partition count, replication factor, key, `acks`, `min.insync.replicas`, cleanup policy, and retention — each with a stated reason and a stated trade-off. The memo must answer, explicitly:

1. **Partition count** — derived from a stated throughput target and consumer-parallelism target, with headroom for 10x growth, and an acknowledgement that you cannot cheaply add partitions later.
2. **Key** — which field, and why its cardinality and ordering requirement make it the right choice (and what hot-partition risk you're avoiding).
3. **Durability** — RF, `min.insync.replicas`, `acks`, `unclean.leader.election`, stated as a single durability posture, with what failure it survives and what it rejects.
4. **Retention** — the time window, derived from the slowest reasonable consumer's catch-up need, with the disk cost (throughput × retention × RF) and the alert you'd set on the retention horizon.
5. **Cleanup policy** — stream vs changelog, justified from the topic's semantics.

**Acceptance criteria.**

- `notes/week-10/order-topic-design.md` exists, fits roughly one page (400–600 words), and decides all five dimensions with a reason and a trade-off each.
- The partition count is *derived* from numbers (throughput, parallelism), not asserted.
- The durability section names the exact failure it survives and the exact write it rejects (the durable trio in action).
- The retention section includes the disk-cost arithmetic and a concrete monitoring alert.
- Committed.

**Hint.** This memo is graded against the rubric below and becomes the broker-design paragraph in your capstone architecture document. The strongest memos state a trade-off for *every* decision — "12 partitions, not 24, because 12 covers 2x our peak parallelism and over-partitioning raises rebalance and metadata cost; we'd repartition via a new topic if we exceed it." Vague memos ("we chose good settings") fail.

**Estimated time.** 1 hour.

---

## Problem 5 — Replay history into a fresh read model

**Problem statement.** Produce 50 records to `order.placed.v1`. Start a consumer group `order-analytics` and let it consume to the end (lag 0). Now **reset its offsets to the beginning** with `kafka-consumer-groups.sh --reset-offsets --to-earliest` (group stopped, dry-run first) and restart it — watch it reprocess all 50 from offset 0. This is the replay superpower the log gives you that a queue cannot (Lecture 2 §3.3).

**Acceptance criteria.**

- `notes/week-10/replay.md` captures: the lag table at 0 before the reset, the `--dry-run` output, the `--execute` output, and the consumer reprocessing all 50 records after restart.
- You note in one sentence why the group had to be **stopped** to reset (the coordinator refuses to move offsets under a running consumer).
- You note one real use of replay (backfilling a new read model, reprocessing after a bug fix).
- Committed.

**Hint.** The exercise-3 consumer with `--group order-analytics` is your consumer. Stop it, reset, restart. Always `--dry-run` first — on a real expensive consumer, a careless reset re-charges cards or re-sends emails. The dry-run is not optional discipline; it's the difference between a tool and a foot-gun.

**Estimated time.** 40 minutes.

---

## Problem 6 — Prove compaction keeps only the latest value per key

**Problem statement.** Create a compacted topic `cart.changelog` (`cleanup.policy=compact`, a small `segment.ms` and `min.cleanable.dirty.ratio` so the cleaner runs quickly). Produce three records for the same key `cart-A` with increasing values, then a tombstone (null value) for a second key `cart-B` after a value. Force/await a log-cleaner run, then dump the log with `kafka-dump-log.sh` (or read from the beginning with a new consumer) and show that only the **latest** `cart-A` value survives and `cart-B` is gone.

**Acceptance criteria.**

- `notes/week-10/compaction.md` shows the records you produced and the post-compaction state: one surviving `cart-A` (the latest), `cart-B` removed by its tombstone.
- You explain in one sentence why this makes a compacted topic a queryable current-state store (a new consumer reading from 0 reconstructs the latest value of every key).
- Committed.

**Hint.** Compaction is lazy; the cleaner runs on closed segments meeting the dirty-ratio threshold. Set `segment.ms=1000`, `min.cleanable.dirty.ratio=0.01`, `delete.retention.ms=1000` on the topic so it compacts fast enough to observe in a homework session. A tombstone is a record with a literally null value (`kafka-console-producer.sh` with `--property null.marker=NULL` or produce an empty value via code). After compaction, a `--from-beginning` consumer sees only `cart-A`'s latest value.

**Estimated time.** 35 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 — Topic audit table | 40 min |
| 2 — Per-key ordering & repartition break | 45 min |
| 3 — Data-loss matrix | 1 h 0 min |
| 4 — Partitioning/retention memo (headline) | 1 h 0 min |
| 5 — Replay into a fresh read model | 40 min |
| 6 — Compaction keeps latest-per-key | 35 min |
| **Total** | **~5 h 0 min** |

---

## Grading rubric (for the headline Problem 4)

| Area | Points | What we look for |
|---|---:|---|
| **Partition derivation** | 25 | Count derived from stated throughput + parallelism with growth headroom; acknowledges repartitioning is a migration. |
| **Key choice** | 20 | Correct field, justified by cardinality + ordering requirement; names the hot-partition risk avoided. |
| **Durability posture** | 25 | RF / `min.insync.replicas` / `acks` / unclean-election stated as one posture; names the failure survived and the write rejected. |
| **Retention reasoning** | 20 | Window derived from slowest-consumer catch-up; disk-cost arithmetic; a concrete retention-horizon alert. |
| **Trade-offs & clarity** | 10 | A stated trade-off for every decision; fits one page; reads like a memo a staff engineer would sign. |

**90+** is portfolio-grade and drops straight into the capstone architecture document. **70–89** decides the dimensions but hand-waves a trade-off or two. **Below 70** asserts settings without deriving them — redo it with numbers.

When you've finished all six, push your repo and make sure the `order-events` [mini-project](./07-mini-project/00-overview.md) is in the same workspace — Week 11 builds the idempotent consumer on top of it. Then take the [quiz](./05-quiz.md) with your notes closed.
