# Week 19 — Exercises

Three focused drills that build a two-region topology and *measure* a failover. Each takes 45–90 minutes. Do them in order — exercise 1 stands up the two regions and the replication, exercise 2 routes traffic across them with health-checked failover, and exercise 3 drives a failover under load and produces your RTO/RPO numbers. Run everything against your **`cart` and `inventory`** services from Phase 1 and a **Postgres** primary/replica pair (or the minimal Postgres stand-in each exercise names).

## Index

1. **[Exercise 1 — Two regions, Postgres logical replication across them](./exercise-01-two-region-postgres-replication.md)** — stand up two Kind clusters as `region-a`/`region-b`, run a Postgres primary in A and a logical replica in B, add a simulated cross-region latency, and read the lag from `pg_stat_replication`. (~75 min, guided)
2. **[Exercise 2 — Geo-routing and health-checked failover](./exercise-02-geo-routing-failover.yaml)** — a CoreDNS-based geo-routing + failover config that routes reads local and writes to the primary region, with a health check that flips the record on primary failure — and the TTL tax made visible. (~60 min, runnable)
3. **[Exercise 3 — Measure the failover RTO and RPO](./exercise-03-failover-rto.py)** — drive writes under load, kill the primary, and *measure* the RTO (recovery window) and RPO (lost writes = lag at failure). (~60 min, runnable)

## How to work the exercises

- Have **two Kind clusters** runnable at once (`kind create cluster --name region-a` and `--name region-b`) and two kubectl contexts (`kind-region-a`, `kind-region-b`). ~6 GB free total is comfortable.
- Have **`psql`** and the Postgres logical-replication literacy from Week 13: you can `CREATE PUBLICATION`, `CREATE SUBSCRIPTION`, and read `pg_stat_replication`.
- Have your **`cart`/`inventory`** services deployable into a cluster. If they're not ready, each exercise names a minimal Postgres-only stand-in so the multi-region mechanics still work.
- **Read the lag before and after every change.** `SELECT * FROM pg_stat_replication;` (replication lag) and the failover script's RTO/RPO output are your ground truth — the multi-region equivalent of last week's `istioctl proxy-config`. Train the habit of confirming the replica is *actually* caught up, not just that the subscription exists.
- When the failover "didn't work," check three things in order: is the replica actually receiving (`pg_stat_replication` non-empty on the primary)? did the promote succeed (`pg_is_in_recovery()` is now `false` on the replica)? did the routing actually cut over (the DNS record / health check flipped)?
- Each runnable exercise ends with an **expected output** block. If your numbers are absurd (RTO of 0, RPO with zero lag but lost writes), you're measuring wrong — re-read the expected block.

## Running the exercises

The `.yaml` exercise is applied with `kubectl` against the routing layer:

```bash
kubectl apply -f exercise-02-geo-routing-failover.yaml
# then resolve the record and watch it flip on failover (see the file's header)
```

The `.py` exercise drives the failover and prints the measured numbers:

```bash
pip install psycopg2-binary
python3 exercise-03-failover-rto.py --run
```

The header of each file lists the exact prerequisites. If your Phase 1 schema isn't loaded, the file's header points you at the minimal `writes(id, ts)` table the failover measurement needs.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c22-week-19` to compare.
