# Exercise 1 — Two Regions, Postgres Logical Replication Across Them

**Goal:** Stand up two Kind clusters as `region-a` and `region-b`, run a Postgres **primary** in region A and a **logical replica** in region B, inject a realistic cross-region network latency, and *measure* the replication lag from `pg_stat_replication`. By the end you have a read-local/write-primary topology where you can watch the replica trail the primary by a real, latency-driven amount — the lag that *is* your RPO at failover.

**Estimated time:** 75 minutes. Guided.

---

## Setup

You need two Kind clusters and `psql`.

```bash
kind create cluster --name region-a
kind create cluster --name region-b
kubectl config get-contexts | grep kind-region   # kind-region-a, kind-region-b
psql --version                                    # client present
```

We'll use the context flag explicitly so you never apply to the wrong "region": `kubectl --context kind-region-a ...`.

**Fallback if your Phase 1 services aren't ready.** This exercise needs only Postgres — `cart`/`inventory` are not required to see replication and lag. Deploy a single Postgres in each cluster (the `postgres:16` image) and the whole exercise works. Wherever this says "cart writes," substitute "a `psql` INSERT loop."

---

## Step 1 — Deploy Postgres in each region

Region A is the **primary** (accepts writes). Region B is the **replica** (read-only follower).

```bash
# region A — primary, with logical replication enabled
kubectl --context kind-region-a apply -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata: { name: pg, namespace: default }
spec:
  replicas: 1
  selector: { matchLabels: { app: pg } }
  template:
    metadata: { labels: { app: pg } }
    spec:
      containers:
      - name: pg
        image: postgres:16
        env:
        - { name: POSTGRES_PASSWORD, value: secret }
        - { name: POSTGRES_DB, value: shop }
        args: ["-c", "wal_level=logical"]   # logical replication needs wal_level=logical
        ports: [{ containerPort: 5432 }]
EOF

# region B — replica target (same image; it will SUBSCRIBE to A)
kubectl --context kind-region-b apply -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata: { name: pg, namespace: default }
spec:
  replicas: 1
  selector: { matchLabels: { app: pg } }
  template:
    metadata: { labels: { app: pg } }
    spec:
      containers:
      - name: pg
        image: postgres:16
        env:
        - { name: POSTGRES_PASSWORD, value: secret }
        - { name: POSTGRES_DB, value: shop }
        args: ["-c", "wal_level=logical"]
        ports: [{ containerPort: 5432 }]
EOF

kubectl --context kind-region-a rollout status deploy/pg
kubectl --context kind-region-b rollout status deploy/pg
```

> **Why two Kind clusters and not two namespaces?** Two clusters is the honest simulation: separate API servers, separate networking, separate failure domains. A region loss is "kill cluster A," and the replica in B has no shared fate with it — which is the entire point of multi-region. Two namespaces in one cluster would share a control plane and die together.

---

## Step 2 — Create the table and a publication on the primary (region A)

Port-forward to region A's Postgres and set up the source of the replication:

```bash
kubectl --context kind-region-a port-forward deploy/pg 5432:5432 &
PGA="postgresql://postgres:secret@localhost:5432/shop"

psql "$PGA" <<'SQL'
-- the minimal table the failover measurement (exercise 3) needs
CREATE TABLE writes (id bigserial PRIMARY KEY, payload text, ts timestamptz DEFAULT now());

-- a PUBLICATION is the source side of logical replication: "publish changes to these tables"
CREATE PUBLICATION shop_pub FOR TABLE writes;
SQL
```

---

## Step 3 — Subscribe from the replica (region B)

Region B subscribes to region A's publication. **This is the cross-region link** — in production it crosses the WAN; here it crosses between two Kind clusters. We point B at A's Postgres (in a real two-cluster setup you'd expose A via a Service/LoadBalancer or a tunnel; on a laptop the simplest path is a second port-forward and `host.docker.internal`, noted below).

```bash
kubectl --context kind-region-b port-forward deploy/pg 5433:5432 &
PGB="postgresql://postgres:secret@localhost:5433/shop"

# Replica needs the SAME table shape (logical replication replicates data, not DDL).
psql "$PGB" -c "CREATE TABLE writes (id bigserial PRIMARY KEY, payload text, ts timestamptz DEFAULT now());"

# Subscribe to A's publication. CONNINFO points at region A's Postgres.
# On Kind/macOS, host.docker.internal reaches the host where A's port-forward listens.
psql "$PGB" <<'SQL'
CREATE SUBSCRIPTION shop_sub
  CONNECTION 'host=host.docker.internal port=5432 dbname=shop user=postgres password=secret'
  PUBLICATION shop_pub;
SQL
```

If the subscription connects, you have a live cross-region replication link: writes to A's `writes` table now flow to B.

---

## Step 4 — Inject a realistic cross-region latency

Right now the "cross-region" link is local and near-instant, which hides the speed-of-light tax the whole week is about. Add a delay so the replica trails by a realistic amount. The simplest reproducible approach is a `tc netem` delay on region A's pod (adds latency to its egress), simulating an ocean between the regions:

```bash
# Add ~80ms one-way latency to region A's Postgres pod egress (a transatlantic-ish RTT).
# Requires NET_ADMIN; run in the pod or via a privileged debug container.
kubectl --context kind-region-a exec deploy/pg -- sh -c \
  'tc qdisc add dev eth0 root netem delay 80ms 2>/dev/null || echo "tc not available; see note"'
```

> **If `tc` isn't available in the image,** the concept still holds — note in your writeup that real cross-region latency is 80–150 ms RTT transatlantic, and that this delay is exactly what makes synchronous cross-region replication so costly (Lecture 1 §3). The lag you measure next is *because of* this delay; on localhost it would be sub-millisecond, which is the unrealistic case.

---

## Step 5 — Write to the primary and measure the lag

Drive a steady stream of writes to region A and watch the replica trail:

```bash
# A small write loop against the PRIMARY (region A).
for i in $(seq 1 1000); do
  psql "$PGA" -c "INSERT INTO writes (payload) VALUES ('w-$i');" >/dev/null
done &

# Meanwhile, read the replication lag from the PRIMARY's pg_stat_replication:
watch -n1 'psql "'"$PGA"'" -x -c "
  SELECT application_name,
         state,
         pg_wal_lsn_diff(sent_lsn, replay_lsn)  AS bytes_behind,
         write_lag, flush_lag, replay_lag
  FROM pg_stat_replication;"'
```

`replay_lag` is the **time** the replica is behind on *applying* changes — this is your **RPO at failover**. With the 80 ms delay and a write load, you'll see it sit at tens to hundreds of milliseconds; remove the delay and it collapses toward zero (the unrealistic localhost case). `bytes_behind` shows the WAL backlog. Watch how lag *grows* if you crank the write rate past what the link can ship — a replica falling behind under load is silently raising your RPO.

---

## Step 6 — Confirm read-local/write-primary

Prove the topology: reads work locally in B, but B refuses writes (it's a replica, not a primary):

```bash
# Read locally in region B — the replicated data is there:
psql "$PGB" -c "SELECT count(*) FROM writes;"      # trails A by ~replay_lag worth of rows

# Try to WRITE to region B — it's a logical-replication target, not a writable primary
# for these rows; in a streaming-replica setup this would be 'cannot execute INSERT
# in a read-only transaction'. Document why writes belong to the primary only.
psql "$PGB" -c "INSERT INTO writes (payload) VALUES ('should-go-to-primary');"
```

This is read-local/write-primary made concrete: region B serves reads from its local copy (fast, local) but all writes belong to the single primary in A. That's the design that respects data gravity (Lecture 2 §2.1) — and it's exactly the topology you'll fail over in Exercise 3.

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] Two Kind clusters (`region-a`, `region-b`) are running, each with a Postgres.
- [ ] `pg_stat_replication` on region A shows region B's subscription in `state=streaming` (the link is live).
- [ ] With the injected cross-region latency, `replay_lag` is a **non-zero** time you can read — and you can state that this number *is* your RPO at failover.
- [ ] You demonstrated reads work locally in region B and that writes belong to the primary in region A (read-local/write-primary).
- [ ] You can state, in one sentence, why `replay_lag` growing under load is a silent RPO regression.

---

## Stretch

- Flip to **synchronous** replication: set `synchronous_standby_names` and `synchronous_commit = remote_apply` on the primary, then time an INSERT. You'll see the ~80 ms cross-region RTT land on every commit — measure it, and you've quantified why synchronous cross-region replication is usually the wrong default (Lecture 1 §3.2).
- Crank the write rate until the replica can't keep up and `replay_lag` climbs without bound. That runaway lag is a replica that will lose more and more data at failover — graph it and note the rate at which it diverges.
- Add a **second replica** (a notional third region) subscribing to the same publication, and confirm both trail independently. Reason about which one you'd promote on failover (the one with the *least* lag = the least data loss).

---

When this feels comfortable, move to [Exercise 2 — Geo-routing and health-checked failover](./exercise-02-geo-routing-failover.yaml).
