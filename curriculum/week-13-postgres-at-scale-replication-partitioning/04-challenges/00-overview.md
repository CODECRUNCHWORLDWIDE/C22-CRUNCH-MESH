# Week 13 — Challenges

The exercises drill the mechanics. **The challenge makes you the on-call data-platform engineer.** You're handed a Postgres instance that's misbehaving in three different ways, and you have to diagnose *why* without the luxury of having written the broken config yourself — the way it always happens in the real world.

## Index

1. **[Challenge 1 — Diagnose a slow storage tier](./challenge-01-diagnose-a-slow-storage-tier.md)** — a setup script plants three independent storage-tier faults (a lagging replica with a pinned slot, a hot table drowning in bloat, and a query that dominates `pg_stat_statements`). Use `pg_stat_replication`, `pg_replication_slots`, `pg_stat_user_tables`, and `pg_stat_statements` to find all three, then prescribe and apply the correct fix for each. (~90 min)

Challenges are optional for passing the week, but this one is the single best preparation for the Phase 3 architecture review, where you defend your storage-tier decisions to a reviewer. Do it. The skill — reading a database you didn't configure and naming what's wrong in under ten minutes — is exactly what separates an engineer who "knows Postgres" from one who can keep a storage tier alive at 3 a.m.
