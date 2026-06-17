# Week 14 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 15. Answer key is at the bottom — don't peek.

---

**Q1.** Why is "write to the database, then publish to Kafka" (a dual write) unsafe?

- A) Kafka is slower than Postgres.
- B) The two writes are to two systems with no shared transaction; a crash between them leaves the database and the event stream permanently disagreeing.
- C) Kafka can't store the same data as Postgres.
- D) It's perfectly safe if you publish first.

---

**Q2.** The transactional outbox pattern makes the event safe by:

- A) Using a distributed two-phase commit across Postgres and Kafka.
- B) Writing the business change and an outbox row in **one local database transaction**, then relaying the outbox to Kafka separately.
- C) Retrying the Kafka publish until it succeeds.
- D) Publishing to Kafka before writing to the database.

---

**Q3.** Log-based CDC (Debezium) avoids the dual-write problem because:

- A) It uses a faster network protocol.
- B) The event stream is *derived from* the database's own commit log (the WAL); there is no second write — the event is a consequence of the commit.
- C) It writes to Kafka inside the database transaction.
- D) It disables Kafka acknowledgements.

---

**Q4.** In a Debezium change event, what does `op: "r"` mean?

- A) A row was read by a query.
- B) The event came from the initial **snapshot** (read), not a live change.
- C) The row was rolled back.
- D) A replication error.

---

**Q5.** An UPDATE event from Debezium has `before: null`. The most likely reason is:

- A) The row didn't exist before.
- B) The table's `REPLICA IDENTITY` is `DEFAULT`, so only the primary key is logged in `before`; set `REPLICA IDENTITY FULL` to get the full prior row.
- C) Debezium is misconfigured and must be reinstalled.
- D) `wal_level` is `minimal`.

---

**Q6.** What is the core idea of CQRS?

- A) Events are the source of truth.
- B) Separate the (normalized) write model from one or more (denormalized) read models, kept in sync by the change stream.
- C) Every read goes through Kafka.
- D) Replace the database with an event log.

---

**Q7.** A read-model projection consumes a stream with at-least-once delivery. To make it correct, the projector must be:

- A) Faster than the producer.
- B) Idempotent — re-applying the same change has no additional effect (e.g., an upsert by key guarded by the change's LSN).
- C) Single-threaded.
- D) Backed by a relational database.

---

**Q8.** In an event-sourced aggregate, current state is:

- A) Stored in a mutable `state` column and updated in place.
- B) Computed by folding (replaying) the aggregate's events from the append-only log.
- C) Cached in Redis and never recomputed.
- D) Whatever the latest Kafka message says.

---

**Q9.** What does `UNIQUE (aggregate_id, version)` give an event store?

- A) Faster reads.
- B) Optimistic concurrency control — two concurrent commands that both try to append the same next version, exactly one wins; the loser gets a conflict and retries. No row locks needed.
- C) Automatic snapshots.
- D) Schema evolution.

---

**Q10.** Which is a *real* ongoing cost of event sourcing that CDC-fed CQRS does not impose?

- A) Needing a database.
- B) Your `apply` function (or an upcasting layer) must handle every historical version of every event forever, because old events are immutable and can't be rewritten.
- C) Needing Kafka.
- D) Requiring a primary key.

---

**Q11.** A service does `UPDATE users SET email=?` then `kafka.produce("UserEmailChanged")` in one handler. The users table is the source of truth. This design is:

- A) Event-sourced, and correct.
- B) An **event-driven service** with a **dual write** — the source of truth is the table, but the non-atomic publish can lose the event on a crash. Fix with outbox/CDC.
- C) CQRS, and correct.
- D) Not using events at all.

---

**Q12.** Which statement about the taxonomy is correct?

- A) CQRS always means event sourcing.
- B) CDC and event sourcing are the same thing.
- C) An event-driven service (publishes events about its current-state DB) is **not** the same as an event-sourced aggregate (events *are* the state); most "event-driven" systems are the former, and that's fine.
- D) Event sourcing is required for any event-driven system.

---

**Q13.** When is full event sourcing genuinely the right tool rather than over-engineering?

- A) For any system that uses Kafka.
- B) For a simple CRUD service.
- C) When the *history of how state changed* is itself the asset or a legal requirement (ledgers, audit-critical workflows, temporal queries), and you've accepted the upcasting and erasure costs.
- D) For a search index.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — Two systems, no shared transaction; a crash between the writes leaves them permanently inconsistent. No defensive code fixes the shape. (Lecture 1 §1.)
2. **B** — One local ACID transaction writes the change and the outbox row together; a relay drains the outbox at-least-once. (Lecture 1 §2.)
3. **B** — The stream is derived from the WAL; the event is a consequence of the single commit, not a second write. (Lecture 1 §3.)
4. **B** — `r` = read, emitted during the initial snapshot so a new consumer can build current state. (Lecture 1 §4.2, §4.4.)
5. **B** — `REPLICA IDENTITY DEFAULT` logs only the PK in `before`; `FULL` logs the whole old row, at a WAL cost. (Lecture 1 §4.3.)
6. **B** — CQRS separates the write model from denormalized read-model projections fed by the change stream. (Lecture 2 §1.)
7. **B** — At-least-once delivery means duplicates arrive; an idempotent projector (LSN-guarded upsert) makes re-application a no-op. (Lecture 2 §2.)
8. **B** — Event sourcing folds the event log to current state; there is no canonical mutable state table. (Lecture 2 §3.1.)
9. **B** — The unique constraint rejects a second concurrent append at the same version — optimistic concurrency, no locks. (Lecture 2 §3.2.)
10. **B** — Immutable historical events must be handled by your apply/upcasting logic forever; this is event sourcing's biggest ongoing tax. (Lecture 2 §3.4.)
11. **B** — Event-driven service (table is truth) with a dual write (non-atomic publish). Fix with outbox or CDC. (Lecture 2 §4; Lecture 1 §1.)
12. **C** — Event-driven ≠ event-sourced; CQRS ≠ event sourcing; CDC ≠ event sourcing. Most "event-driven" systems publish about a current-state DB, which is correct. (Lecture 2 §4.)
13. **C** — Event sourcing fits when history is the asset/requirement and you've accepted its costs; for CRUD/search/cart it's over-engineering. (Lecture 2 §3.4.)

</details>

---

If you scored under 9, re-read the lecture sections cited in the answers you missed. If you scored 11 or higher, you're ready for the [homework](./06-homework.md).
