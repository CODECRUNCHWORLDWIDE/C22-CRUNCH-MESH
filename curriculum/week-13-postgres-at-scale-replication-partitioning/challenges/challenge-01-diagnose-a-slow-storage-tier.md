# Challenge 1 — Diagnose a Slow Storage Tier on a Live Instance

**Time estimate:** ~90 minutes.

## Problem statement

You are on call. A teammate's Postgres deployment "mostly works" but three things are wrong in ways nobody can explain: the **read replica is hours behind and the primary's disk is filling**, a dashboard query "got slow over the week and now times out," and "something is hammering the database but no single query looks slow." All three are storage-tier faults — three *different* faults with three *different* fixes.

You will run a fault-injection harness that reproduces all three on one instance (plus a replica), then **detect, diagnose, and prescribe the fix** for each, using only the introspection views from this week. No reading the harness internals until you've diagnosed all three from the outside — that's the whole point.

This mirrors the real skill: you rarely debug a storage tier you just configured. You debug one someone else built, from the outside in, with `pg_stat_replication`, `pg_stat_user_tables`, and `pg_stat_statements`, and a clear head.

## The harness

Save this as `faulty_storage.sql` and run it against a **fresh** `shop` database on a primary that already has a streaming replica attached (use the Exercise 1 compose setup). It plants the three faults; leave it and the write loop running while you diagnose from other terminals.

```sql
-- faulty_storage.sql — three planted storage-tier faults. Do NOT read the
-- comments tagging each fault until you've diagnosed all three from the outside.
\set ON_ERROR_STOP on

-- ============ Fault A: a replication slot pinned by a dead consumer =========
-- Create a slot that NOTHING consumes. Every WAL segment from here is retained
-- on the primary forever, filling pg_wal. (Simulates a replica that died and
-- never came back, or a forgotten logical subscription.)
SELECT pg_create_logical_replication_slot('ghost_slot', 'pgoutput')
WHERE NOT EXISTS (SELECT 1 FROM pg_replication_slots WHERE slot_name = 'ghost_slot');

-- ============ Fault B: a hot table drowning in bloat =======================
DROP TABLE IF EXISTS sessions;
CREATE TABLE sessions (
    session_id bigint PRIMARY KEY,
    user_id    bigint NOT NULL,
    last_seen  timestamptz NOT NULL,
    payload    text
) WITH (
    autovacuum_enabled = false        -- <-- the fault: autovacuum disabled here
);
INSERT INTO sessions
SELECT g, (random()*100000)::bigint, now(), repeat('x', 200)
FROM generate_series(1, 200000) g;
-- Churn it hard. With autovacuum off, every update is permanent dead-tuple debt.
DO $$ BEGIN
  FOR i IN 1..20 LOOP
    UPDATE sessions SET last_seen = now();
  END LOOP;
END $$;

-- ============ Fault C: a high-frequency query with no supporting index =====
DROP TABLE IF EXISTS lookups;
CREATE TABLE lookups (id bigint, token text, created_at timestamptz);
INSERT INTO lookups
SELECT g, md5(g::text), now() FROM generate_series(1, 500000) g;
-- No index on token. The app (the loop below) looks up by token constantly, so
-- a cheap-LOOKING query runs a sequential scan thousands of times. Individually
-- fast-ish, collectively the top of pg_stat_statements.
```

Run it, then start the query loop that exercises Fault C (a shell loop is fine):

```bash
psql -h localhost -U postgres -d shop -f faulty_storage.sql

# Fault C load generator — run this in a second terminal and leave it running.
for i in $(seq 1 5000); do
  psql -h localhost -U postgres -d shop -tc \
    "SELECT id FROM lookups WHERE token = md5('$((RANDOM % 500000))');" >/dev/null
done
```

## Your task

For **each of the three faults** (A: replication/slot, B: bloat, C: query), produce a diagnosis with these four parts:

1. **Symptom** — what's observably wrong (which view, which number, what's climbing or stuck).
2. **Root cause** — the exact mechanism: which slot is inactive and pinning WAL; which table has what dead-tuple percentage and why; which query dominates total time and what it's missing.
3. **Evidence** — the actual output of **at least two** independent introspection signals that confirm the diagnosis. One signal is a guess; two is a diagnosis.
4. **Prescription** — the exact fix, written as the command(s) you'd run, and the prevention (the config or process change that stops it recurring).

You must reach each diagnosis from the **outside** — the views below — before reading the harness comments.

The views to reach for:

```sql
-- Fault A: replication & slots
SELECT slot_name, active,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained_wal
FROM pg_replication_slots ORDER BY retained_wal DESC;
SELECT * FROM pg_stat_replication;

-- Fault B: bloat
SELECT relname, n_live_tup, n_dead_tup,
       round(100*n_dead_tup/NULLIF(n_live_tup+n_dead_tup,0),1) AS dead_pct,
       last_autovacuum, last_vacuum,
       (SELECT reloptions FROM pg_class c WHERE c.relname = t.relname) AS reloptions
FROM pg_stat_user_tables t ORDER BY n_dead_tup DESC;

-- Fault C: query cost (needs pg_stat_statements preloaded)
SELECT round(total_exec_time::numeric,1) AS total_ms, calls,
       round(mean_exec_time::numeric,3) AS mean_ms, left(query,50) AS query
FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 10;
```

## Acceptance criteria

- [ ] A file `challenge-01-diagnosis.md` with a section per fault, each containing all four parts above.
- [ ] You correctly identify the mechanism of each fault:
  - **A** — an **inactive replication slot** (`active = f`) whose `restart_lsn` is pinning WAL, growing `pg_wal`. (NOT "the replica is slow" — the *real* replica may be fine; the `ghost_slot` is the disk-filler.)
  - **B** — the `sessions` table has a high `dead_pct` because **autovacuum is disabled** on it (`reloptions` shows `autovacuum_enabled=false`); ordinary writes never get cleaned.
  - **C** — the `lookups` `token` query tops `pg_stat_statements` by **total time** despite a modest mean, because it does a **sequential scan** (no index on `token`) thousands of times.
- [ ] Each diagnosis cites **at least two** independent signals.
- [ ] A `fixed_storage.sql` (or a documented set of commands) that applies all three fixes: `pg_drop_replication_slot('ghost_slot')`; re-enable autovacuum on `sessions` and `VACUUM`/`pg_repack` it; `CREATE INDEX ON lookups (token)`. After fixes, the slot is gone, `dead_pct` on `sessions` drops, and the `lookups` query falls off the top of `pg_stat_statements` (and its plan switches to an Index Scan).
- [ ] Committed to your Week 13 repo under `challenges/challenge-01/`.

## The trap (read after a first attempt)

The seductive wrong answer on Fault A is "the replica is lagging, restart the replica." Check `pg_stat_replication` — the *real* replica may be `streaming` and perfectly healthy. The disk-filler is a **second, inactive** slot (`ghost_slot`) that no consumer is attached to. The fix is not to touch the healthy replica at all; it's to **drop the orphaned slot**. Prescribing "restart the replica" wastes the outage and leaves the disk filling. Diagnose by the slot's `active` flag and retained-WAL size, not by assuming the visible replica is the culprit. This is the exact shape of a real Postgres disk-fill incident.

## Stretch

- Add a **fourth fault**: set `synchronous_standby_names = 'FIRST 1 (replica1)'`, then stop `replica1`. Now every commit **blocks**. Diagnose it (writes hang, `pg_stat_activity` shows backends waiting on `SyncRep`) and explain why `ANY 1 (...)` of multiple standbys would not have this single-point-of-write-failure.
- Re-run the bloat fault but with `pg_repack` instead of `VACUUM FULL`, and measure the lock duration of each (`pg_locks` during the operation). Show that `pg_repack` keeps the table writable where `VACUUM FULL` does not.
- Write a 15-line shell script that prints a one-screen storage-tier health summary: inactive slots, top-3 bloated tables, top-3 queries by total time. This is the script you actually want on call.

## Why this matters

In the Phase 3 architecture review, the reviewer will not ask you to recite the autovacuum tunables — they'll point at a running instance and ask "this disk is filling, what's your first query?" and "this got slow, how do you find out why without guessing?" This challenge *is* that conversation, rehearsed. Every data-platform on-call rotation eventually hands you a database you didn't configure with a fault you can't see from the application. The engineer who can name it from three system views in ten minutes is the one who gets paged less.
