# Week 13 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 14. Answer key is at the bottom — don't peek.

---

**Q1.** What does `wal_level = logical` enable that `wal_level = replica` does not?

- A) Faster checkpoints.
- B) Logical decoding of the WAL into row-level changes — the basis of logical replication and CDC — at the cost of more WAL volume.
- C) Streaming physical replication.
- D) Point-in-time recovery.

---

**Q2.** A streaming physical replica and the primary must agree on which of these?

- A) The same set of published tables.
- B) The same major Postgres version and architecture — it's a byte-identical copy.
- C) The same `pg_stat_statements` configuration.
- D) Nothing; physical replication is version-agnostic.

---

**Q3.** A replication slot exists for a standby that crashed and will never return. What is the danger?

- A) Nothing; the slot is harmless once the standby is gone.
- B) The slot's `restart_lsn` is frozen, so the primary retains every WAL segment from that point and `pg_wal` grows until the disk fills and the primary stops accepting writes.
- C) The primary automatically drops the slot after one minute.
- D) The standby's data is corrupted.

---

**Q4.** You want to replicate *only* the `orders` and `order_items` tables to a reporting database running a newer Postgres version. Which replication do you use?

- A) Physical streaming replication.
- B) Logical replication (`PUBLICATION`/`SUBSCRIPTION`) — it's selective and cross-version.
- C) `pg_basebackup` nightly.
- D) Either works identically.

---

**Q5.** After a logical-replication cutover, you get duplicate-key errors on inserts to the new primary. The most likely cause is:

- A) The tables have different column orders.
- B) Sequences are not replicated by logical replication, so the subscriber's sequence wasn't advanced past the highest used value.
- C) The WAL is corrupted.
- D) `wal_level` was set to `replica`.

---

**Q6.** You partition `orders` by `RANGE (created_at)`. Which primary key is legal?

- A) `PRIMARY KEY (order_id)`
- B) `PRIMARY KEY (order_id, created_at)` — the partition key must be part of every unique constraint.
- C) `PRIMARY KEY (customer_id)`
- D) No primary key is allowed on a partitioned table.

---

**Q7.** `orders` is partitioned by month on `created_at`. A query is `WHERE status = 'SHIPPED'` with no time bound. What does the planner do?

- A) Prunes to the partition containing shipped orders.
- B) Scans **every** partition, because with no predicate on the partition key it cannot rule any partition out.
- C) Refuses to run without a `created_at` filter.
- D) Scans only the most recent partition.

---

**Q8.** An `UPDATE` changes only a non-indexed column and there's free space on the page. What happens, and why does it matter?

- A) It's a HOT (heap-only tuple) update — no index entries are written, so the update is cheap and avoids index bloat.
- B) Every index is still rewritten; HOT only applies to inserts.
- C) The row is moved to a new page and all indexes are updated.
- D) The update is rejected because the column isn't indexed.

---

**Q9.** A hot table shows `n_dead_tup` at 80% of total tuples and `last_autovacuum` is null. Which is the most likely cause and fix?

- A) The table is too small; do nothing.
- B) autovacuum is disabled on the table (`autovacuum_enabled=false` in reloptions) or its threshold is too lax — re-enable / tune per-table autovacuum and `VACUUM` (or `pg_repack`) to reclaim.
- C) The table needs a new index.
- D) The replica is lagging.

---

**Q10.** You read `pg_stat_statements`. Query A: mean 2000 ms, 1 call. Query B: mean 5 ms, 100000 calls. Which do you optimize first?

- A) Query A — it has the highest mean time.
- B) Query B — its total time (≈500 s) dwarfs Query A's (2 s); you optimize the highest *total* cost, not the highest mean.
- C) Neither; both are fine.
- D) Whichever was written most recently.

---

**Q11.** Your stateless web fleet opens thousands of connections to Postgres and the server slows down. Which pgBouncer mode multiplexes most aggressively, and what's the main caveat?

- A) `session` mode; no caveats.
- B) `transaction` mode — a backend is reused per transaction, so it multiplexes thousands of clients onto a few backends; the caveat is that session-scoped state (server-prepared statements, `SET`s, advisory locks, `LISTEN/NOTIFY`) doesn't survive across transactions.
- C) `statement` mode; it supports multi-statement transactions.
- D) `session` mode multiplexes the most.

---

**Q12.** Which is true of `FIRST 1 (replica1)` vs `ANY 1 (replica1, replica2)` for `synchronous_standby_names`?

- A) They're identical.
- B) `FIRST 1 (replica1)` makes `replica1` a single point of *write* failure — if it's down, every commit blocks; `ANY 1 (...)` of multiple standbys tolerates losing any one.
- C) `ANY 1` is slower in all cases.
- D) `FIRST 1` tolerates losing the named standby.

---

**Q13.** A team's single primary's *write* throughput is the wall. They have not partitioned hot tables, fixed top queries, or added pgBouncer. What's the right next step?

- A) Immediately shard with Citus.
- B) Migrate to CockroachDB.
- C) Do the cheap things first — partition, tune the top queries, add pgBouncer — and only consider sharding if writes are *still* the wall afterward.
- D) Add more read replicas (which don't help write throughput).

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — `logical` adds enough to the WAL to decode row-level changes, enabling logical replication and CDC, and writes more WAL than `replica`. (Lecture 1 §1.)
2. **B** — Physical replication is a byte-identical copy; it requires the same major version and architecture and replicates everything. (Lecture 1 §2.)
3. **B** — An inactive slot pins WAL via its frozen `restart_lsn`; this is the classic disk-fill outage. `max_slot_wal_keep_size` caps it. (Lecture 1 §2.2.)
4. **B** — Logical replication is selective (subset of tables) and cross-version; physical is all-or-nothing and same-version. (Lecture 1 §3.1, §3.3.)
5. **B** — Logical replication doesn't replicate sequence state; you must advance the subscriber's sequences after cutover or hit duplicate keys. (Lecture 1 §3.2.)
6. **B** — The partition key must be part of the primary key, because Postgres can't enforce a global unique index across partitions. (Lecture 2 §1.1.)
7. **B** — No predicate on the partition key means no pruning; every partition is scanned. Partitioning only helps queries that filter on the partition key. (Lecture 2 §1.3.)
8. **A** — A HOT update writes no index entries when no indexed column changes and there's page room; it's the high-leverage way to keep update-heavy tables cheap. (Lecture 2 §2.2.)
9. **B** — High dead-tuple percentage with no autovacuum points to disabled/too-lax autovacuum; re-enable/tune and reclaim with `VACUUM` or `pg_repack`. (Lecture 2 §2.3.)
10. **B** — Total time = mean × calls. Query B costs ~500 s total vs Query A's 2 s. You optimize total cost, not felt slowness. (Lecture 2 §3.1.)
11. **B** — `transaction` mode is the aggressive multiplexer; the caveat is session-scoped state not surviving across transactions (prepared statements, `SET`, advisory locks, `LISTEN/NOTIFY`). (Lecture 2 §3.2–3.3.)
12. **B** — `FIRST 1 (one)` is a write SPOF; `ANY N (...)` of several standbys tolerates losing any one without blocking commits. (Lecture 1 §2.4.)
13. **C** — Sharding is the most expensive option; partition, tune queries, and pool first. Read replicas don't help writes. (Lecture 2 §4.3.)

</details>

---

If you scored under 9, re-read the lecture sections cited in the answers you missed. If you scored 11 or higher, you're ready for the [homework](./homework.md).
