# Week 13 Homework

Six problems that revisit the week's topics and force the Postgres-at-scale literacy into your fingers. The full set should take about **5 hours**. Work in your Week 13 Git repository (the same workspace as the exercises and the `orders-at-scale` mini-project) so every problem produces at least one commit you can point to at the Phase 3 architecture review.

The headline deliverable is **Problem 4 — the replication-and-partitioning decision memo**. Treat it as the artifact a staff engineer reads to approve (or reject) a storage-tier change, not a journal entry.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

Run everything against a Postgres 16 you control. Have the Exercise 1 primary+replica compose setup available — Problems 1 and 5 use it. Set `\timing on` in every `psql` session.

---

## Problem 1 — The replication health table

**Problem statement.** Using your primary + streaming replica from Exercise 1, build a single monitoring query that, run on the primary, reports every standby's health on one screen: application name, state, sent/replay LSNs, replay lag in bytes, replay lag as a time interval, and whether the standby's slot is active. Run it under load and record the output. Then add a second query for slots specifically that flags any slot with `active = false` and shows how much WAL it's pinning.

**Acceptance criteria.**

- `notes/week-13/replication-health.sql` contains both queries, runnable as-is.
- `notes/week-13/replication-health.md` records the output under a write load, with at least one capture showing non-zero (but bounded) lag.
- You state in one sentence what number you would alert on for (a) replay lag and (b) an inactive slot, and why.
- Committed.

**Hint.** `pg_stat_replication` joined to nothing gives you the standby rows; `pg_replication_slots` gives you `active` and `restart_lsn`. `pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)` is the WAL a slot is pinning. The alert threshold for an inactive slot is essentially zero-tolerance — minutes, not hours.

**Estimated time.** 40 minutes.

---

## Problem 2 — Pick the partition key with evidence

**Problem statement.** You're given two access patterns for a hypothetical `events` table: (A) 95% of reads are `WHERE created_at BETWEEN ? AND ?` (time-window dashboards), and (B) a different service whose reads are 90% `WHERE tenant_id = ?` (per-tenant queries). For *each* pattern, decide the partition strategy and key, build a small partitioned table that matches it, load ~500k rows, and prove with `EXPLAIN` that the common query prunes. Then show the *cross* case: run pattern-B's query against pattern-A's partitioning and show it does **not** prune.

**Acceptance criteria.**

- `notes/week-13/partition-choice.sql` builds both partitioned tables (one `RANGE (created_at)`, one `LIST` or `HASH` on `tenant_id`) and loads data.
- `notes/week-13/partition-choice.md` shows, for each, the `EXPLAIN` proving the matching query prunes, plus the cross-case `EXPLAIN` proving a mismatched query scans all partitions.
- A one-paragraph conclusion stating the rule: partition on the column the dominant query filters; the wrong key is worse than none.
- Committed.

**Hint.** For tenant-keyed access with many tenants and no natural ranges, `PARTITION BY HASH (tenant_id)` spreads writes and prunes equality queries; `LIST` fits when tenants map to a small, known set of buckets (e.g., tiers). The cross-case `EXPLAIN` is the most instructive output in the whole problem.

**Estimated time.** 50 minutes.

---

## Problem 3 — Bloat: cause it, see it, fix it three ways

**Problem statement.** Create a table, disable autovacuum on it, and churn it with an update storm to produce serious bloat. Measure the bloat with both `pg_stat_user_tables` (dead-tuple count) and `pgstattuple` (real bytes). Then reclaim it three ways on three copies: (a) `VACUUM` (note it does *not* shrink the file), (b) `VACUUM FULL` (note the `ACCESS EXCLUSIVE` lock), and (c) `pg_repack` if available (note the brief lock). Record table size on disk after each.

**Acceptance criteria.**

- `notes/week-13/bloat.md` shows: the bloat before (dead %, `pgstattuple` output, on-disk size), and the on-disk size + lock behavior after each of the three reclaim methods.
- You correctly state that plain `VACUUM` makes space reusable but does **not** return it to the OS, while `VACUUM FULL`/`pg_repack` do.
- You correctly state which method is safe to run on a hot production table during business hours and which is not.
- Committed.

**Hint.** `\dt+` or `pg_total_relation_size('t')` gives on-disk size. To observe the lock, run the reclaim in one session and `SELECT * FROM pg_locks WHERE relation = 't'::regclass;` from another. If `pg_repack` isn't installed, document that and explain what it would do.

**Estimated time.** 45 minutes.

---

## Problem 4 — The replication-and-partitioning decision memo (headline deliverable)

**Problem statement.** This is the staff-review artifact. You run the `orders` storage tier for a marketplace doing 8,000 writes/sec on `orders`, with a reporting team that wants fresh-ish reads and a finance team that runs heavy monthly rollups. Write a one-to-two-page decision memo at `notes/week-13/storage-decision-memo.md` that makes four explicit recommendations with justification:

1. **Replication** — physical read replica, logical subscriber, both, or neither, for the reporting workload. State the staleness tolerance and how you'd route reads.
2. **Partitioning** — partition `orders` or not; if so, by what key and granularity; and the retention/lifecycle policy.
3. **Pooling** — pgBouncer mode and pool sizing, with the one feature (if any) that needs a session-mode carve-out.
4. **The sharding question** — at what *measured* signal you would revisit single-node Postgres and consider Citus or CockroachDB, and which you'd lean toward and why.

Each recommendation must state the evidence you'd collect to confirm it (a specific view or benchmark), not just an opinion.

**Acceptance criteria.**

- `notes/week-13/storage-decision-memo.md` exists, fits in one-to-two pages, and makes all four recommendations explicitly.
- Each recommendation names the **specific signal/measurement** that justifies it (e.g., "`pg_stat_replication` replay lag < 2 s," "Q1 prunes to one partition in `EXPLAIN`," "direct-to-Postgres throughput collapses past ~300 connections").
- The sharding recommendation is *conditional on a measured wall*, not a default, and states Citus-vs-Cockroach with a reason.
- It reads like a memo to a staff engineer, not a tutorial.
- Committed.

**Hint.** Reuse the numbers from your mini-project benchmark — the percentiles, the pruning plans, the pgBouncer collapse point — as the evidence. A memo backed by your own benchmark is far stronger than one backed by blog posts. The strongest memos include one explicit "we are NOT doing X yet, and here's the signal that would change that."

**Estimated time.** 1 hour.

---

## Problem 5 — Logical replication and its restrictions, hands-on

**Problem statement.** On your primary, create a `PUBLICATION` for the `orders` table and subscribe a second database (a third container, or a second db on the same instance) to it. Confirm rows flow. Then deliberately trigger two of logical replication's documented restrictions: (a) `ALTER TABLE orders ADD COLUMN note text;` on the publisher *without* first altering the subscriber, then insert a row using the new column and observe the subscriber's apply error; and (b) demonstrate that a sequence's state did not replicate. Document both, then show the correct procedure that avoids each.

**Acceptance criteria.**

- `notes/week-13/logical-replication.md` records: the `CREATE PUBLICATION`/`CREATE SUBSCRIPTION`, proof rows flow, the apply error after the un-coordinated `ADD COLUMN`, and evidence sequences didn't carry over.
- You state the correct procedure for each: run DDL on the subscriber first (or use a migration tool targeting both ends); advance subscriber sequences after a cutover.
- You correctly distinguish this from a *physical* replica (where DDL and sequences flow automatically because it's byte-identical).
- Committed.

**Hint.** The subscriber's apply worker logs the error (check its server log, or `pg_stat_subscription` shows it stalled). For sequences, compare `SELECT last_value FROM <seq>` on both sides after inserts on the publisher. The whole point is that logical replication carries DML for published tables and nothing else — schema and sequences are *your* job.

**Estimated time.** 1 hour.

---

## Problem 6 — pgBouncer collapse point

**Problem statement.** Run `pgbench` directly against Postgres at increasing client counts (`-c 50`, `-c 200`, `-c 500`, `-c 1000`) and record throughput (TPS) at each. Then put pgBouncer in transaction mode in front (with a small `default_pool_size`, e.g., 25) and repeat. Find and report the client count where direct-to-Postgres throughput **collapses** while pooled throughput **holds**. That collapse point is the number you quote when someone asks "why do we need pgBouncer?"

**Acceptance criteria.**

- `notes/week-13/pgbouncer-collapse.md` has a table of client-count vs TPS for both direct and pooled runs.
- You identify the client count at which direct throughput degrades and pooled throughput is stable, and explain *why* (Postgres process-per-connection cost vs a small multiplexed backend set).
- Committed.

**Hint.** `pgbench -i -s 50` initializes; `pgbench -c <N> -j 8 -T 30 <db>` runs a 30-second test. Point the pooled runs at port 6432 (pgBouncer) instead of 5432 (Postgres). The collapse is usually visible somewhere in the hundreds-of-connections range, depending on hardware and `shared_buffers`.

**Estimated time.** 45 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 — Replication health table | 40 min |
| 2 — Pick the partition key | 50 min |
| 3 — Bloat: cause, see, fix | 45 min |
| 4 — Decision memo (headline) | 1 h 0 min |
| 5 — Logical replication restrictions | 1 h 0 min |
| 6 — pgBouncer collapse point | 45 min |
| **Total** | **~5 h 0 min** |

When you've finished all six, push your repo and make sure the `orders-at-scale` [mini-project](./mini-project/README.md) is in the same workspace — Week 14 streams that exact `orders` table via Debezium. Then take the [quiz](./quiz.md) with your notes closed.

---

## Grading rubric (for the headline memo, Problem 4)

| Criterion | Weight | What earns full marks |
|---|---:|---|
| **All four recommendations explicit** | 25% | Replication, partitioning, pooling, and the sharding question are each answered with a clear position, not hedged. |
| **Evidence, not opinion** | 30% | Every recommendation names a specific view or benchmark number that justifies it; numbers come from your own mini-project where possible. |
| **The sharding discipline** | 20% | Sharding is conditional on a measured wall; Citus-vs-Cockroach is decided with a stated reason; "not yet, and here's the trigger" is present. |
| **Honesty & tradeoffs** | 15% | At least one explicit tradeoff or negative ("we accept X staleness," "we are NOT doing Y because…"). |
| **Memo quality** | 10% | Reads like a staff-review memo: tight, decision-first, no tutorial padding. |

A memo that says "it depends" without committing to a position, or that recommends sharding without a measured trigger, caps at 60%. The whole skill is committing to a defensible position with evidence.
