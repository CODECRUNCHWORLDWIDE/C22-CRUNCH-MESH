# Lecture 2 — Redpanda, Retention and Compaction, and Operating the Cluster

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can explain Redpanda's architecture and how it differs from Kafka while speaking the same API, choose between time retention and log compaction for a topic and say what each costs, run Kafka on Kubernetes via Strimzi, and diagnose consumer lag with both `kafka-consumer-groups.sh` and `rpk`.

Lecture 1 was the abstraction and the protocol. This lecture is the *implementations* and the *operations*: the alternative broker that keeps the Kafka API but throws away the JVM and ZooKeeper, the retention decisions that decide what your topics cost and mean, and the day-to-day of running this on Kubernetes and reading its health. Three parts: (1) Redpanda, (2) retention and compaction, (3) operating and diagnosing.

---

## Part 1 — Redpanda: same API, different engine

Redpanda is a broker that speaks the **Kafka API** — your producers and consumers from Lecture 1 connect to it unchanged, your `confluent-kafka-go` and `confluent-kafka-python` clients do not know the difference — but reimplements the engine from scratch in C++. It exists because Kafka's JVM-and-page-cache architecture, designed in 2011, carries assumptions that modern NVMe and many-core machines make expensive. The pitch is "the Kafka API without the Kafka operational tax." Whether that pitch holds is exactly the kind of question this course teaches you to answer with a benchmark, not a vibe — which is the mini-project.

### 1.1 What is actually different

| Dimension | Apache Kafka | Redpanda |
|---|---|---|
| Language / runtime | Java/Scala on the JVM | C++, no JVM, no GC pauses |
| Threading model | Thread pool + OS page cache | **Thread-per-core (Seastar)**: one shard per core, share-nothing, no locks on the hot path |
| Metadata / coordination | KRaft controller quorum (formerly ZooKeeper) | **Raft per partition** — every partition is its own Raft group; no separate metadata system to run |
| Replication | Leader/follower + ISR (Lecture 1 §4) | Raft consensus per partition (leader election + log replication are Raft) |
| Storage | Relies heavily on the OS page cache; data durability tied to flush behavior | Manages its own I/O, can be configured for `fsync`-per-write durability tiers |
| Deployment | Broker JVMs + KRaft controllers, tuned heap, GC | A single binary per node; `rpk` is the one CLI |
| Tiered storage | Via Confluent/commercial or KIP-405 remote storage | Built-in tiered storage to object storage (S3/GCS) in the core |

The two architectural ideas worth understanding:

**Thread-per-core (Seastar).** Instead of a thread pool contending over shared state, Redpanda pins one logical core to one "shard," and each shard owns a slice of the partitions with no shared mutable state between shards. There are no locks on the request path; cores communicate by explicit message passing. The payoff shows up at the **tail**: because there is no GC and no lock contention, p99.9 latency is far more predictable than a JVM broker under load. The cost is that it is a different operational model and a different failure surface; "just add heap" is not a knob because there is no heap.

**Raft per partition.** Lecture 1's ISR model is Kafka's bespoke replication protocol. Redpanda instead makes *every partition its own Raft group* — the same Raft you studied in Week 2. Leader election, log replication, and commit are Raft's, which means the durability story is "a write is committed when a Raft majority has it," structurally similar to `acks=all` with `min.insync.replicas` = majority, but expressed in the consensus algorithm you already know. There is no separate ZooKeeper or KRaft quorum to operate, because the cluster metadata is itself a Raft group.

### 1.2 What is the same

Everything you learned in Lecture 1 about the *model* still applies: topics, partitions, offsets, keys, consumer groups, retention, compaction, delivery semantics, and the lag table. Redpanda supports the idempotent producer and Kafka transactions. The `order.placed.v1` design — 12 partitions, replication factor 3, key by `order_id`, `acks=all` — is identical on Redpanda. **That is the whole point of API compatibility: your design and your code are portable; only the engine under them changes.** This is why the mini-project can run the *same* producer and consumer against both and compare.

### 1.3 `rpk` — the one CLI

Redpanda ships `rpk`, a single CLI that replaces the dozen `kafka-*.sh` scripts:

```bash
# Create the topic (note: same concepts, terser CLI)
rpk topic create order.placed.v1 --partitions 12 --replicas 3

# Describe it, including per-partition leader and replica placement
rpk topic describe order.placed.v1 -p

# Produce and consume from the shell
echo '{"order_id":"A","total_cents":4200}' | rpk topic produce order.placed.v1 --key A
rpk topic consume order.placed.v1 --offset start --num 5

# The lag table — Lecture 1's diagnostic, Redpanda flavor
rpk group describe order-fulfillment

# Cluster and broker health
rpk cluster health
rpk redpanda admin brokers list
```

### 1.3a The durability knob Redpanda exposes that Kafka hides

One Redpanda-specific detail worth knowing because it bites people migrating from Kafka. Kafka's durability is "the record is on the ISR's logs," but whether those logs are *flushed to disk* (fsync) versus sitting in the OS page cache is, by default, left to the OS — a power loss can lose page-cache-resident-but-not-flushed data on all replicas simultaneously (rare, but real). Redpanda makes the flush behavior an explicit tier:

- By default Redpanda relies on replication (a Raft majority has it) for durability, like Kafka — fast, and a single power loss is survived because other replicas have it.
- Redpanda can also be configured to **fsync on every write** for the strictest durability (survives a *simultaneous* power loss of a majority), at a latency cost.

The takeaway is not "Redpanda is more durable" — at the default both rely on replication — but that **Redpanda surfaces the disk-flush trade as a knob while Kafka leaves it implicit.** When you benchmark the two (the mini-project), make sure you're comparing the same durability tier; a Redpanda configured for fsync-per-write against a default Kafka is not an apples-to-apples comparison, and that mistake produces misleading numbers in half the blog posts you'll read.

### 1.4 The honest 2026 comparison

The summary a senior engineer gives a new hire in 2026: **"Both are excellent and both speak the Kafka API, so your code doesn't pick — your operations team does. Kafka with KRaft on Strimzi is the safe, ubiquitous, huge-ecosystem choice; every connector, every tool, every hire knows it. Redpanda is the choice when you want fewer moving parts (one binary, no separate quorum), predictable tail latency, and built-in tiered storage, and you're willing to run a less ubiquitous system. Benchmark both on *your* workload before you commit; do not pick on a blog post."** That benchmark is precisely what the mini-project makes you do. Neither answer is wrong; picking without measuring is.

### 1.5 A word on KRaft you'll need as an operator

Whichever Kafka you run, in 2026 it is **KRaft**, not ZooKeeper — ZooKeeper support was removed in Kafka 4.0. As an operator you need a working model of three things:

- **Controllers vs brokers.** A subset of nodes are **controllers**: they run a Raft quorum that holds all cluster metadata (topics, partitions, ISR, configs, ACLs) in an internal `__cluster_metadata` log. The other nodes are **brokers** that serve data. In small clusters (like your Kind setup) a node can be *both* — a "dual-role" node — which is what the exercise-1 `KafkaNodePool` declares. In large clusters you separate them so controller elections aren't disrupted by data-plane load.
- **The quorum needs an odd majority.** Three controllers tolerate one failure; five tolerate two. An even number buys you nothing (4 tolerates the same 1 failure as 3 but costs an extra node), so controllers come in 3s and 5s. This is the same Raft majority arithmetic from Week 2 — KRaft *is* Raft.
- **Metadata is a log, too.** Of course it is — that's the week's whole theme. The controllers replicate the metadata log by Raft; a broker that restarts replays it to rebuild its view of the cluster. "Is ZooKeeper down?" is no longer a question; "is the controller quorum healthy?" (`kafka-metadata-quorum.sh --describe`) is its replacement.

The day-one operational upside is real: one system to run instead of two, faster controller failover, and metadata changes (creating a topic, growing partitions) that propagate as log records rather than ZooKeeper writes. Strimzi provisions all of this from the `Kafka` CR; you mostly need to know the quorum exists, why it's odd-sized, and which command checks its health.

---

## Part 2 — Retention and compaction: what your topics cost and mean

A log that grows forever fills the disk. Retention is the policy that decides what the broker keeps. There are two fundamentally different retention philosophies, and **which one a topic uses is a semantic decision, not just an operational one.**

### 2.1 Time and size retention (the event-stream policy)

The default. The broker keeps records for a window and then deletes whole segments past it:

- **`retention.ms`** — keep records for this long (e.g., `604800000` = 7 days). After that, segments older than the window are deleted.
- **`retention.bytes`** — keep at most this many bytes per partition; older segments are deleted to stay under the cap.

This is correct for an **event stream**: a sequence of facts that happened, each meaningful in its own right. `order.placed.v1` is an event stream — every placement is a distinct fact you want for some window (7 days for reprocessing headroom, maybe 30 for analytics replay). The cost is straightforward: `retention.ms` × throughput × replication factor = disk. A 10 MB/s topic at RF=3 retained 7 days is ~18 TB across the cluster; size your disks accordingly, and know that the lever to cut cost is shorter retention or tiered storage to object storage.

> **Decision rule for event streams:** retain long enough that the *slowest reasonable consumer* (a CDC pipeline that was down for a day, a new read model being backfilled) can catch up or backfill, plus a safety margin. Too short and a consumer that falls behind past the window **loses records permanently** — its offset points at a segment that was deleted, and on restart it gets `OFFSET_OUT_OF_RANGE` and resets (to earliest or latest, depending on config), silently skipping or re-reading. Too long and you pay for disk you don't use.

The disk-cost arithmetic, so retention is a budget and not a guess:

```
disk per partition  = throughput_bytes_per_sec * retention_seconds
total cluster disk  = disk_per_partition * partitions * replication_factor

Worked, for order.placed.v1:
  throughput      = 5 MB/s
  retention       = 7 days = 604,800 s
  bytes/partition = 5 MB/s * 604,800 s  ≈ 3.0 TB   (across all partitions combined,
                                                     since throughput is topic-wide)
  with RF 3       = 3.0 TB * 3           ≈ 9.0 TB cluster disk
```

So extending retention from 7 to 30 days on this topic roughly quadruples its disk to ~38 TB at RF 3. That is the lever you weigh against "how far back might a consumer need to replay." The cheap escape from the trade is **tiered storage**: keep a few days hot on local disk and offload the rest to object storage, where 30 or 90 days of history costs a fraction per byte. Reach for tiered storage the moment retention-for-replay drives your local disk past comfortable.

### 2.2 Log compaction (the changelog policy)

The other philosophy. With `cleanup.policy=compact`, the broker keeps **the latest record per key, forever** (and discards older records *for the same key*). The topic becomes a **changelog**: a key-value store expressed as a log, where replaying it from the beginning reconstructs the current value of every key.

```
Before compaction (by offset):
  (cart-A, {items:1}) (cart-B, {items:3}) (cart-A, {items:2}) (cart-A, {items:5}) (cart-B, {items:0})

After the log cleaner runs:
  (cart-A, {items:5}) (cart-B, {items:0})     # only the latest per key survives
```

This is correct for a **changelog / current-state** topic: when you only care about the *latest* value per key, not the history. The `__consumer_offsets` topic Kafka uses internally is compacted — it only needs the latest committed offset per group/partition. A materialized-view backing topic (Kafka Streams `KTable`) is compacted. A "current price per SKU" topic is compacted. The payoff: a new consumer can bootstrap the *entire current state* by reading the compacted topic from offset 0, without you retaining infinite history.

A **tombstone** is a record with a **null value**. In a compacted topic it means "delete this key": after compaction (and a grace period, `delete.retention.ms`), the key disappears entirely. This is how you express deletions in a changelog.

> **Decision rule — stream vs changelog:** if every record is an independent fact you might want to reprocess (an order was placed, a payment was charged), it is an **event stream** → time/size retention. If you only ever care about the latest value per key (the current state of a cart, the current price of a SKU, the latest committed offset), it is a **changelog** → compaction. You can even combine them (`cleanup.policy=compact,delete`) to compact *and* drop very old tombstones. Getting this classification right is the difference between a topic that bloats and a topic that quietly maintains a queryable current-state.

### 2.3 The retention gotcha you will hit

The single most common retention bug: a CDC or backfill consumer is down for a maintenance window longer than the topic's `retention.ms`. When it comes back, its committed offset points into a segment that has been **deleted**. It gets `OFFSET_OUT_OF_RANGE`, and `auto.offset.reset` decides its fate: `latest` (skip everything it missed — silent data gap) or `earliest` (reprocess from the start of what's left — possible duplicates). Either way, you lost the clean continuation. The fix is to retain longer than your worst maintenance window and to **alert on lag approaching the retention horizon**, not just on lag being nonzero. You will design exactly this retention budget in the homework.

---

## Part 3 — Operating the cluster on Kubernetes and diagnosing it

### 3.1 Strimzi: Kafka on Kubernetes

You will run Kafka on Kind via the **Strimzi operator**, which turns Kafka administration into Kubernetes CRDs. You declare a `Kafka` custom resource and Strimzi provisions the brokers, the KRaft controllers, the services, and the storage. Topics become `KafkaTopic` CRs, so a topic's partition count and retention live in version-controlled YAML — exactly the "infrastructure as data" discipline you want.

A minimal KRaft-mode cluster (Strimzi, current API) uses a `KafkaNodePool` for the broker/controller nodes plus a `Kafka` resource:

```yaml
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaNodePool
metadata:
  name: dual-role
  namespace: kafka
  labels:
    strimzi.io/cluster: crunch-cluster
spec:
  replicas: 3
  roles:
    - controller
    - broker
  storage:
    type: persistent-claim
    size: 10Gi
    deleteClaim: false
---
apiVersion: kafka.strimzi.io/v1beta2
kind: Kafka
metadata:
  name: crunch-cluster
  namespace: kafka
  annotations:
    strimzi.io/node-pools: enabled
    strimzi.io/kraft: enabled
spec:
  kafka:
    version: 3.9.0
    replicas: 3
    listeners:
      - name: plain
        port: 9092
        type: internal
        tls: false
    config:
      # The durable trio from Lecture 1 §4, set as cluster defaults:
      default.replication.factor: 3
      min.insync.replicas: 2
      offsets.topic.replication.factor: 3
      transaction.state.log.replication.factor: 3
      transaction.state.log.min.isr: 2
  entityOperator:
    topicOperator: {}
    userOperator: {}
```

And a topic as a CR — this is where partition count and retention become declared, reviewable contract:

```yaml
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: order.placed.v1
  namespace: kafka
  labels:
    strimzi.io/cluster: crunch-cluster
spec:
  partitions: 12
  replicas: 3
  config:
    retention.ms: "604800000"     # 7 days — event stream
    min.insync.replicas: "2"      # belt-and-suspenders with the producer's acks=all
    cleanup.policy: "delete"      # time retention; use "compact" for a changelog
```

`kubectl apply -f` and the topic exists with exactly the partition count and retention you reviewed in code. Redpanda has an analogous operator and Helm chart; the mini-project stands up both.

### 3.2 The lag table — your primary diagnostic (both engines)

Lecture 1 §7 introduced it; here is the operating discipline. The lag table is the first thing you look at when *anything* is wrong with an event-driven system, because almost every symptom — "orders are slow to fulfill," "the dashboard is stale," "the disk is filling" — shows up there first.

```bash
# Kafka
kafka-consumer-groups.sh --bootstrap-server crunch-cluster-kafka-bootstrap:9092 \
    --describe --group order-fulfillment

# Redpanda — identical columns
rpk group describe order-fulfillment
```

The differential diagnosis, expanded into an operating playbook:

| Symptom in the lag table | Likely cause | First fix |
|---|---|---|
| Lag flat near 0, oscillating with batch size | Healthy | Nothing. This is the goal. |
| Lag climbing on **all** partitions | Group globally too slow | Add consumers (≤ partition count); speed up processing; check a downstream dependency. |
| Lag climbing on **one** partition | Hot key (skewed partitioner) or one stuck instance | Re-key the topic (higher cardinality), or restart/inspect the one `CONSUMER-ID`. |
| `CURRENT-OFFSET` stuck, `LOG-END` advancing, members present | Processing hang, swallowed exception, or rebalance loop | Check consumer logs; look for `max.poll.interval.ms` evictions. |
| Group has **no members** | Nobody consuming | Is the consumer deployment running? Crash loop? Wrong `bootstrap.servers`? |
| Lag approaching the **retention horizon** | Consumer about to lose unread records to deletion | Pause deletion / extend retention immediately; this is a data-loss emergency. |

### 3.3 The offset-reset tool — replay on purpose

Because the consumer owns the offset, you can *move* it deliberately — to replay history into a new read model, to skip a poison batch, or to reprocess after a bug fix. This is the superpower the log gives you that a queue cannot:

```bash
# Dry-run: where WOULD the group go if reset to earliest? (always dry-run first)
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group order-analytics --topic order.placed.v1 \
  --reset-offsets --to-earliest --dry-run

# Execute it (the group must be STOPPED — no active members — to reset)
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group order-analytics --topic order.placed.v1 \
  --reset-offsets --to-earliest --execute

# Other useful targets:
#   --to-latest           skip everything, start fresh
#   --to-datetime '2026-06-01T00:00:00.000'   replay from a point in time
#   --shift-by -100       rewind 100 records per partition
```

> **The group must have no active members to reset its offsets** — the coordinator refuses to move offsets out from under a running consumer. Stop the deployment, reset, restart. And **always `--dry-run` first**: a reset to `earliest` on a 2-year topic with an expensive consumer is how you accidentally re-charge cards or re-send emails. Reset is a loaded gun and a precision tool in the same hand.

### 3.3a What to alert on (lag is necessary but not sufficient)

Reading the lag table by hand is for incident response; for steady state you want alerts. The metrics that actually matter, and the threshold logic worth encoding (you'll wire these into Prometheus in Week 17, but the *what* belongs here):

- **Consumer lag, per group, as a derivative.** Don't alert on "lag > N" alone — a brief spike during a deploy is normal. Alert on **lag that is increasing for M minutes**, which means the group is structurally falling behind rather than absorbing a blip. The Kafka exporter / `kafka-lag-exporter` exposes per-group, per-partition lag; the alert is on the trend, not the value.
- **Lag relative to the retention horizon.** The dangerous alert (Lecture 2 §2.3): lag in *records* is less meaningful than lag in *time-to-retention-expiry*. If a group's oldest unread record is within, say, 20% of the retention window of being deleted, page someone — this is the impending data-loss case, not a mere slowness.
- **Under-replicated partitions** (`UnderReplicatedPartitions > 0`). A partition whose ISR has shrunk below the replica count means a follower is lagging or a broker is down; if it shrinks below `min.insync.replicas`, `acks=all` writes start failing. Alert immediately.
- **Offline partitions** (`OfflinePartitionsCount > 0`). A partition with no leader — produces and consumes for it fail entirely. This is a page-now condition.
- **Active controller count** (KRaft: exactly 1). Zero means no controller (metadata frozen); more than one means a split brain. Either is an emergency.

The discipline: **lag is the first thing you look at, but "is data about to be lost" and "is the cluster losing durability" are the things you page on.** A group that's a little behind is a Tuesday; an under-replicated partition or a consumer about to fall off the retention horizon is an incident.

### 3.4 The decision tree for "the consumer isn't keeping up"

When an event-driven flow is misbehaving, walk this — it covers the whole stack from connectivity to keys:

```
Consumer flow is broken / slow.
│
├─ Does `kafka-topics.sh --describe` / `rpk topic describe` show the topic with the right partitions & RF?
│   ├─ No  → topic mis-created (wrong partitions/RF) or wrong bootstrap.servers. Fix the topic/connection.
│   └─ Yes ↓
│
├─ Does the lag table show the group with members?
│   ├─ No  → consumer not running / crash-looping / wrong group.id. Check the deployment & logs.
│   └─ Yes ↓
│
├─ Is lag climbing on ALL partitions or ONE?
│   ├─ ALL → group too slow. Add consumers (≤ partitions), speed up work, check downstream. (§3.2)
│   ├─ ONE → hot key / stuck instance. Re-key, or inspect the single CONSUMER-ID. (Lec 1 §2.2)
│   └─ FLAT ↓
│
├─ Is CURRENT-OFFSET advancing but records reprocessed/duplicated?
│   ├─ Yes → at-least-once doing its job; the consumer must be IDEMPOTENT. (Lec 1 §5.2 → Week 11)
│   └─ No ↓
│
└─ Records flow but data is wrong/out of order → ordering only holds per key.
   Check the partition key. (Lec 1 §2.1)
```

Tape this next to the data-loss matrix from Lecture 1. Between the two, you can diagnose almost any "our event pipeline is misbehaving" problem in under five minutes — which is the whole point of this week.

---

## 4. Recap

You should now be able to:

- Explain Redpanda's thread-per-core and Raft-per-partition architecture, what it changes (tail latency, no separate quorum, built-in tiered storage) and what it keeps (the entire Kafka API and model), and why your code is portable across both.
- Classify a topic as an event stream (time/size retention) or a changelog (compaction), say what each costs in disk and means semantically, and explain tombstones.
- Stand up Kafka on Kubernetes with Strimzi using KRaft, and express topics — partition count, retention, `min.insync.replicas` — as reviewable `KafkaTopic` CRDs.
- Read the lag table on both Kafka and Redpanda, run the differential diagnosis, and use offset reset to replay on purpose (safely, with a dry run, on a stopped group).
- Walk the topic → members → lag-shape → idempotency → key decision tree to diagnose a misbehaving event pipeline.

Next: the exercises put all of this on a real cluster — Strimzi on Kind, a Go producer, a Python consumer group, and a head-to-head Kafka-vs-Redpanda benchmark. Continue to [the exercises](../03-exercises/00-overview.md).

---

## References

- *Redpanda — Intro and architecture*: <https://docs.redpanda.com/current/get-started/intro-to-events/>
- *Redpanda — thread-per-core / Raft blog*: <https://www.redpanda.com/blog>
- *Apache Kafka — log compaction*: <https://kafka.apache.org/documentation/#compaction>
- *Apache Kafka — basic operations (consumer groups, offset reset)*: <https://kafka.apache.org/documentation/#basic_ops>
- *Strimzi — deploying (KRaft, node pools)*: <https://strimzi.io/docs/operators/latest/deploying.html>
- *Strimzi — KafkaTopic configuration*: <https://strimzi.io/docs/operators/latest/configuring.html>
- *rpk reference*: <https://docs.redpanda.com/current/reference/rpk/>
- *KIP-405 — tiered storage*: <https://cwiki.apache.org/confluence/display/KAFKA/KIP-405%3A+Kafka+Tiered+Storage>
- *Kafka — KRaft and the metadata quorum (`kafka-metadata-quorum.sh`)*: <https://kafka.apache.org/documentation/#kraft>
- *`kafka-lag-exporter` — per-group lag metrics for Prometheus*: <https://github.com/seglo/kafka-lag-exporter>
