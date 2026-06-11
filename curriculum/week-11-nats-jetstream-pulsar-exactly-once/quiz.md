# Week 11 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 12. Answer key is at the bottom — don't peek.

---

**Q1.** Why is exactly-once *delivery* impossible over an unreliable network?

- A) Because networks are too slow.
- B) Because a sender cannot distinguish "the message was lost" from "the ack was lost" — both look like no-ack — so it either never retries (at-most-once, may lose) or retries (at-least-once, may duplicate). The two-generals result.
- C) Because Kafka doesn't support it.
- D) It is possible; you just need TCP.

---

**Q2.** Given that exactly-once delivery is impossible, how do you get exactly-once *effect*?

- A) Use a faster broker.
- B) Accept at-least-once delivery (never lose) and make the consumer idempotent (a duplicate has no duplicate effect), backed by atomic writes on the producer side.
- C) Set `acks=0`.
- D) Disable retries everywhere.

---

**Q3.** What must be true of an idempotency key?

- A) It must be random and unique per attempt.
- B) It must be stable across retries — derived from the business event (`order_id`, the event's UUID), not generated fresh on each attempt.
- C) It must be a timestamp.
- D) It must be encrypted.

---

**Q4.** What is the dual-write problem?

- A) Writing the same row twice.
- B) A service changes its database and publishes an event as two separate operations; a crash between them leaves the state and the event disagreeing, silently and permanently.
- C) Two services writing to the same table.
- D) Writing to two replicas.

---

**Q5.** How does the transactional outbox fix the dual write?

- A) It retries the publish until it succeeds.
- B) It writes the business change and an `outbox` row in **one** database transaction; a separate relay publishes the outbox at-least-once. The event can never disagree with the committed state.
- C) It publishes to the broker first, then writes the database.
- D) It uses a distributed transaction across Postgres and Kafka.

---

**Q6.** Why does the outbox relay use `SELECT ... FOR UPDATE SKIP LOCKED`?

- A) For speed only.
- B) So multiple relay instances can run concurrently without both publishing the same outbox row — each locks the rows it takes and the others skip them.
- C) Because the outbox table is read-only.
- D) To avoid deadlocks with the consumer.

---

**Q7.** In the idempotent-consumer dedup-table pattern, why must the dedup insert and the effect be in the **same** transaction?

- A) For performance.
- B) Because if they're in separate transactions, a crash between them reintroduces the dual-write problem one level down — you might mark an event processed but never apply it, or apply it but never mark it.
- C) Postgres requires it.
- D) They don't have to be; separate is fine.

---

**Q8.** What is the limitation of the NATS JetStream dedup window?

- A) It only works on one subject.
- B) It is time-bounded: a repeated `Nats-Msg-Id` is dropped only *within* the window; a duplicate that arrives after the window expires is accepted as new. So it's a weaker guarantee than a permanent dedup table.
- C) It deduplicates consumers, not producers.
- D) It requires a license.

---

**Q9.** What distinguishes NATS core from JetStream?

- A) Nothing; they're the same.
- B) Core is in-memory, at-most-once, fire-and-forget pub/sub with no persistence or replay; JetStream adds durable, Raft-replicated, replayable streams with consumers, ack policies, and a dedup window.
- C) Core is durable; JetStream is ephemeral.
- D) Core supports transactions; JetStream does not.

---

**Q10.** What is the defining architectural choice of Apache Pulsar?

- A) It uses one process per partition.
- B) It separates serving (stateless brokers) from storage (stateful BookKeeper bookies), so the two scale independently and a broker loss triggers no data migration.
- C) It stores everything in ZooKeeper.
- D) It has no concept of subscriptions.

---

**Q11.** Which Pulsar subscription mode gives per-key ordering with parallelism (like Kafka's keyed partitions)?

- A) Exclusive.
- B) Shared.
- C) Key-shared — messages with the same key always go to the same consumer.
- D) Failover.

---

**Q12.** Where does Kafka's exactly-once semantics (idempotent producer + transactions) stop?

- A) It never stops.
- B) At the Kafka boundary — it dedups producer retries and makes consume-transform-produce atomic *within Kafka*, but the moment your transform writes to Postgres or calls Stripe, you're outside the transaction and must add idempotency yourself.
- C) At 100 partitions.
- D) At the consumer group.

---

**Q13.** A senior engineer is asked "how do you guarantee no double-charge?" Which answer is correct?

- A) "We use Kafka EOS, so duplicates are impossible."
- B) "Kafka EOS dedups producer retries inside Kafka; the no-double-charge guarantee comes from a stable idempotency key on the charge and a dedup table in the consumer's transaction — proven with a chaos test."
- C) "We set `acks=all`."
- D) "We retry until it works."

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — The sender can't tell a lost message from a lost ack, so it's forced to choose at-most-once or at-least-once. Two-generals. (Lecture 1 §1.)
2. **B** — At-least-once delivery + idempotent processing = exactly-once effect; atomic writes guard the producer side. (Lecture 1 §1–2.)
3. **B** — The key must be stable across retries and derived from the event; a per-attempt key defeats dedup. (Lecture 1 §2.1.)
4. **B** — Two separate writes (DB + broker) with no atomicity; a crash between them causes permanent disagreement. (Lecture 2 §1.1.)
5. **B** — One transaction for the state change + outbox row; an at-least-once relay publishes it. (Lecture 2 §1.2.)
6. **B** — `SKIP LOCKED` partitions the unsent rows across relay instances so none is double-published. (Lecture 2 §1.3.)
7. **B** — Separate transactions reintroduce the dual write at the consumer; atomic together or the pattern leaks. (Lecture 2 §2.1.)
8. **B** — The dedup window is time-bounded; a late duplicate slips through. Weaker than a permanent dedup table. (Lecture 1 §3.3.)
9. **B** — Core = at-most-once in-memory; JetStream = durable, replicated, replayable. (Lecture 1 §3.)
10. **B** — Stateless brokers over stateful bookies; independent scaling, instant rebalancing, tiered storage. (Lecture 1 §4.1.)
11. **C** — Key-shared routes same-key messages to the same consumer, preserving per-key order with parallelism. (Lecture 1 §4.3.)
12. **B** — EOS holds inside Kafka; external writes (Postgres, Stripe) are outside the transaction. (Lecture 1 §5, Lecture 2 §3.)
13. **B** — The guarantee is the idempotency key + dedup table (your code), not the broker feature; and it's proven with a chaos test. (Lecture 2 §3.)

</details>

---

If you scored under 9, re-read the lecture sections cited in the answers you missed. If you scored 11 or higher, you're ready for the [homework](./homework.md).
