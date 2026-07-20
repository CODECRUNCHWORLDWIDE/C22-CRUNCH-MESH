# Week 10 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 11. Answer key is at the bottom — don't peek.

---

**Q1.** What is the single most important structural difference between Kafka and a traditional message queue (RabbitMQ, SQS)?

- A) Kafka is faster.
- B) A queue deletes a message when it's consumed and the broker tracks delivery; Kafka keeps records until retention expires and the **consumer** owns its read offset, so every group reads independently.
- C) Kafka cannot do fan-out; a queue can.
- D) Kafka guarantees global ordering across all partitions; a queue does not.

---

**Q2.** Within Kafka, what is the *only* ordering guarantee you get?

- A) Total ordering across the whole topic.
- B) Ordering across all partitions by timestamp.
- C) Per-partition ordering only — and you control which records share a partition via the key.
- D) No ordering at all; Kafka never orders records.

---

**Q3.** You key `order.placed.v1` by `country_code`, and 70% of orders are from one country. What happens?

- A) Throughput improves because related records are co-located.
- B) One partition gets 70% of the traffic; its consumer saturates while others idle, and that partition's `LAG` climbs while the rest stay near zero — a hot partition.
- C) Kafka automatically rebalances the keys across partitions.
- D) The producer round-robins anyway, ignoring the key.

---

**Q4.** You have a topic with 12 partitions and a consumer group with 16 instances. What happens to the extra 4 instances?

- A) They share partitions round-robin with the others.
- B) They sit idle — a partition is read by exactly one member of a group, so parallelism is capped at the partition count.
- C) The group fails to form.
- D) Kafka adds 4 more partitions automatically.

---

**Q5.** Which combination can lose an **acknowledged** write on a single broker failure?

- A) `acks=all`, `replication.factor=3`, `min.insync.replicas=2`.
- B) `acks=1` (leader acks, then dies before any follower replicates).
- C) `acks=all`, `min.insync.replicas=2`, `unclean.leader.election.enable=false`.
- D) None of these can ever lose an acknowledged write.

---

**Q6.** What is the "durable trio" you set for any topic where data loss is unacceptable?

- A) `acks=0`, RF=1, `min.insync.replicas=1`.
- B) `acks=1`, RF=2, `min.insync.replicas=1`.
- C) `replication.factor=3`, `min.insync.replicas=2`, producer `acks=all`.
- D) `acks=all`, RF=1, `min.insync.replicas=1`.

---

**Q7.** A consumer commits its offset **before** processing the records. What delivery semantic is that, and what's the risk?

- A) At-least-once; risk of duplicates.
- B) At-most-once; if it crashes after committing but before finishing, those records are **skipped** on restart.
- C) Exactly-once; no risk.
- D) It's a configuration error and the consumer won't start.

---

**Q8.** Why is "at-least-once + idempotent processing" the workhorse default for event-driven systems?

- A) It's the fastest possible configuration.
- B) Because a record may be delivered more than once (e.g., across a rebalance or restart-before-commit), the consumer's effect must be idempotent — applying it twice equals applying it once — so redelivery is safe.
- C) Because it guarantees exactly-once with no extra work.
- D) Because it disables retries.

---

**Q9.** Kafka's exactly-once semantics (idempotent producer + transactions) are real. Where do they **stop**?

- A) They never stop; EOS is end-to-end across any system.
- B) At the Kafka boundary — the moment your transform charges a card, writes to Postgres, or calls an external API, you're outside the transaction, and exactly-once becomes a contract you build with idempotency keys.
- C) At the partition boundary only.
- D) They stop working above 3 partitions.

---

**Q10.** When should a topic use `cleanup.policy=compact` instead of time retention?

- A) When it's high-throughput.
- B) When every record is an independent fact you might reprocess.
- C) When you only ever care about the **latest value per key** (a changelog / current-state topic), so the broker keeps the latest record per key and discards older ones for that key.
- D) Never; compaction is deprecated.

---

**Q11.** A CDC consumer is down for a 6-hour maintenance window. The topic's `retention.ms` is 1 hour. What happens when the consumer restarts?

- A) Nothing; it resumes exactly where it left off.
- B) Its committed offset points into segments that were **deleted**; it gets `OFFSET_OUT_OF_RANGE`, and `auto.offset.reset` decides whether it skips (latest) or reprocesses (earliest) — either way it lost the clean continuation. This is a data-loss emergency.
- C) Kafka automatically extends retention to cover the gap.
- D) The consumer crashes permanently and cannot be restarted.

---

**Q12.** What does the `cooperative-sticky` assignor (KIP-429) change about rebalancing?

- A) It makes rebalances slower but safer.
- B) Instead of every consumer revoking all partitions (stop-the-world), only the partitions that must move are revoked; the rest keep flowing, so a rolling deploy doesn't freeze the whole group.
- C) It disables rebalancing entirely.
- D) It only works on Redpanda, not Kafka.

---

**Q13.** Redpanda speaks the Kafka API but reimplements the engine. Which statement is correct?

- A) You must rewrite your producers and consumers to use Redpanda.
- B) Redpanda uses thread-per-core (Seastar) and Raft-per-partition, has no JVM and no separate ZooKeeper/KRaft quorum, yet your existing Kafka-API clients and your topic design (partitions, keys, `acks`) work unchanged.
- C) Redpanda has no concept of partitions or consumer groups.
- D) Redpanda is slower at the tail because it lacks batching.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — The consumer owning its offset (and the broker keeping records regardless of consumption) is the structural difference. It's why fan-out is free and replay is possible. (Lecture 1 §1.)
2. **C** — Per-partition ordering only; the key decides which records share a partition and are therefore ordered relative to each other. (Lecture 1 §2.)
3. **B** — A low-cardinality, skewed key creates a hot partition: one partition's `LAG` climbs while the rest idle. The fix is a higher-cardinality key like `order_id`. (Lecture 1 §2.2.)
4. **B** — A partition is owned by exactly one member of a group, so consumer parallelism is capped at the partition count; extras idle. (Lecture 1 §3.)
5. **B** — `acks=1`: the leader acks, then dies before a follower replicates, and the new leader never had the record. The durable trio (A/C) does not lose on single failure. (Lecture 1 §4.3.)
6. **C** — `RF=3`, `min.insync.replicas=2`, `acks=all`: survives one broker loss with no acknowledged-data loss, and refuses (not loses) writes if a second is down. (Lecture 1 §4.2.)
7. **B** — Commit-before-process is at-most-once: a crash between commit and completion skips the records. (Lecture 1 §5.1.)
8. **B** — Redelivery is inherent to at-least-once; idempotent processing makes the second delivery a no-op, so it's safe. (Lecture 1 §5.2.)
9. **B** — EOS holds inside Kafka's boundary; external side effects (cards, Postgres, APIs) are outside the transaction, so exactly-once there is an application-level contract. This is the bridge to Week 11. (Lecture 1 §5.3.)
10. **C** — Compaction keeps the latest value per key — correct for a changelog/current-state topic, not an event stream. (Lecture 2 §2.2.)
11. **B** — The unread records were deleted by retention; the consumer hits `OFFSET_OUT_OF_RANGE` and resets, losing the clean continuation. Retain longer than your worst maintenance window and alert on the retention horizon. (Lecture 2 §2.3.)
12. **B** — Incremental cooperative rebalancing revokes only the partitions that must move, avoiding the stop-the-world freeze. (Lecture 1 §3.1.)
13. **B** — Same API and model, different engine: thread-per-core, Raft-per-partition, no JVM, no separate quorum; your clients and topic design are unchanged. (Lecture 2 §1.)

</details>

---

If you scored under 9, re-read the lecture sections cited in the answers you missed. If you scored 11 or higher, you're ready for the [homework](./homework.md).
