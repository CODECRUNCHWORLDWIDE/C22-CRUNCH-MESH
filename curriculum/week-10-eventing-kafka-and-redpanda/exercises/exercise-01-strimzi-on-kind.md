# Exercise 1 — Strimzi on Kind: Stand Up a Real 3-Broker Kafka Cluster

**Goal:** Deploy a 3-broker KRaft-mode Kafka cluster on Kind via the Strimzi operator, create the `order.placed.v1` topic as a reviewable `KafkaTopic` CR with 12 partitions and replication factor 3, and prove with `kafka-topics.sh` and `kafka-consumer-groups.sh` that the cluster is healthy and the topic is laid out the way you specified. You will train the single most important operating habit of the week: reading the cluster's actual state instead of trusting that your YAML did what you meant.

**Estimated time:** 75 minutes. Guided.

---

## Setup

You need a working **Kind** cluster and `kubectl`, plus Helm 3. Verify:

```bash
kind version
kubectl version --client
helm version
```

If you don't have a Kind cluster, create one with enough headroom for three broker pods:

```bash
kind create cluster --name crunch-mesh
kubectl cluster-info --context kind-crunch-mesh
```

**Fallback if Kind is too heavy on your laptop.** A single-node Redpanda via `docker compose` gives you a Kafka-API endpoint on `localhost:9092` that every later exercise works against identically. Save as `docker-compose.yml` and `docker compose up -d`:

```yaml
services:
  redpanda:
    image: redpandadata/redpanda:v24.2.7
    command:
      - redpanda
      - start
      - --smp=1
      - --overprovisioned
      - --kafka-addr=PLAINTEXT://0.0.0.0:9092
      - --advertise-kafka-addr=PLAINTEXT://localhost:9092
    ports:
      - "9092:9092"
```

With the fallback, skip to **Step 5** and use `rpk` (bundled in the image: `docker exec -it <id> rpk ...`) wherever the steps say `kafka-topics.sh`. The Kafka path below is the real target; do it if your machine can.

---

## Step 1 — Install the Strimzi operator

```bash
kubectl create namespace kafka
kubectl create -f 'https://strimzi.io/install/latest?namespace=kafka' -n kafka
kubectl -n kafka wait --for=condition=Available deployment/strimzi-cluster-operator --timeout=180s
```

The operator is now watching the `kafka` namespace for `Kafka`, `KafkaNodePool`, and `KafkaTopic` resources. Confirm:

```bash
kubectl -n kafka get deploy strimzi-cluster-operator
# NAME                       READY   UP-TO-DATE   AVAILABLE
# strimzi-cluster-operator   1/1     1            1
```

---

## Step 2 — Declare the cluster

Save this as `kafka-cluster.yaml`. It is the KRaft-mode cluster from Lecture 2 §3.1 — a dual-role node pool (each node is both broker and controller) and a `Kafka` resource with the durable defaults baked in.

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
      default.replication.factor: 3
      min.insync.replicas: 2
      offsets.topic.replication.factor: 3
      transaction.state.log.replication.factor: 3
      transaction.state.log.min.isr: 2
  entityOperator:
    topicOperator: {}
    userOperator: {}
```

```bash
kubectl apply -f kafka-cluster.yaml
kubectl -n kafka wait kafka/crunch-cluster --for=condition=Ready --timeout=600s
```

The wait can take several minutes on first run while images pull and the KRaft quorum forms. When it returns `condition met`, you have three brokers running a Raft controller quorum, no ZooKeeper in sight.

```bash
kubectl -n kafka get pods
# crunch-cluster-dual-role-0   1/1   Running
# crunch-cluster-dual-role-1   1/1   Running
# crunch-cluster-dual-role-2   1/1   Running
# crunch-cluster-entity-operator-...  Running
```

---

## Step 3 — Create the topic as a CR

This is the load-bearing idea of the week's operations: **the topic's partition count and retention are a reviewed, version-controlled artifact, not a one-off CLI command.** Save as `topic-order-placed.yaml`:

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
    retention.ms: "604800000"     # 7 days — this is an event stream
    cleanup.policy: "delete"
    min.insync.replicas: "2"
```

```bash
kubectl apply -f topic-order-placed.yaml
kubectl -n kafka get kafkatopic order.placed.v1
# NAME              CLUSTER          PARTITIONS   REPLICATION FACTOR   READY
# order.placed.v1   crunch-cluster   12           3                    True
```

---

## Step 4 — Verify the layout from inside the cluster

Don't trust the CR's `READY: True` — verify the actual partition and replica placement on the brokers. Run an ephemeral client pod:

```bash
kubectl -n kafka run kafka-cli -ti --rm --restart=Never \
  --image=quay.io/strimzi/kafka:latest-kafka-3.9.0 -- \
  bin/kafka-topics.sh --bootstrap-server crunch-cluster-kafka-bootstrap:9092 \
  --describe --topic order.placed.v1
```

You are looking for **12 partition lines**, each with a `Leader`, a `Replicas:` list of three broker ids, and an `Isr:` list that also has three entries (the full ISR — everyone is in sync):

```
Topic: order.placed.v1  PartitionCount: 12  ReplicationFactor: 3  Configs: ...
  Topic: order.placed.v1  Partition: 0  Leader: 0  Replicas: 0,1,2  Isr: 0,1,2
  Topic: order.placed.v1  Partition: 1  Leader: 1  Replicas: 1,2,0  Isr: 1,2,0
  ...
  Topic: order.placed.v1  Partition: 11 Leader: 2  Replicas: 2,0,1  Isr: 2,0,1
```

Read it like Lecture 1 §4: `Isr` of size 3 means all replicas are caught up, so an `acks=all` producer with `min.insync.replicas=2` is fully durable and has headroom to lose one broker. If any `Isr` is shorter than `Replicas`, a follower is lagging — note which, you may revisit it.

---

## Step 5 — Smoke test: produce and consume from the shell

Before you write any Go or Python, prove the round trip with the console tools. Producer in one terminal:

```bash
kubectl -n kafka run kafka-producer -ti --rm --restart=Never \
  --image=quay.io/strimzi/kafka:latest-kafka-3.9.0 -- \
  bin/kafka-console-producer.sh --bootstrap-server crunch-cluster-kafka-bootstrap:9092 \
  --topic order.placed.v1 --property parse.key=true --property key.separator=:
# then type:  A:{"order_id":"A","total_cents":4200}
#             B:{"order_id":"B","total_cents":1999}
```

Consumer in another terminal (note `--from-beginning` so you see records already written):

```bash
kubectl -n kafka run kafka-consumer -ti --rm --restart=Never \
  --image=quay.io/strimzi/kafka:latest-kafka-3.9.0 -- \
  bin/kafka-console-consumer.sh --bootstrap-server crunch-cluster-kafka-bootstrap:9092 \
  --topic order.placed.v1 --from-beginning --property print.key=true
# A    {"order_id":"A","total_cents":4200}
# B    {"order_id":"B","total_cents":1999}
```

You have a working log. The two records `A` and `B` were keyed, so each landed deterministically on `murmur2(key) % 12`.

---

## Step 6 — Expose the cluster to your laptop for the next exercises

Exercises 2 and 3 run from your laptop, not inside the cluster, so port-forward the bootstrap service:

```bash
kubectl -n kafka port-forward svc/crunch-cluster-kafka-bootstrap 9092:9092 &
# now localhost:9092 reaches the cluster
```

> **Advertised-listener caveat.** Strimzi's internal listener advertises in-cluster hostnames, so a raw port-forward works for a single-broker reach but can confuse a client that follows partition leaders to other brokers. For these exercises (one bootstrap, small topic) it works; for production-faithful external access you'd configure an `external` listener (`type: nodeport` or `loadbalancer`) in the `Kafka` CR. Note this in your writeup — it's a real gotcha. If a client hangs, switch to the `docker compose` Redpanda fallback (which advertises `localhost:9092` cleanly) for exercises 2–3.

---

## Step 7 — Read the lag table (empty, for now)

There are no consumer groups yet — that's exercise 3 — but learn the command now against an empty result:

```bash
kubectl -n kafka run kafka-cli -ti --rm --restart=Never \
  --image=quay.io/strimzi/kafka:latest-kafka-3.9.0 -- \
  bin/kafka-consumer-groups.sh --bootstrap-server crunch-cluster-kafka-bootstrap:9092 --list
# (empty — the console consumer used a random throwaway group that's already gone)
```

By the end of exercise 3 this list will show `order-fulfillment` and `order-analytics`, and `--describe --group order-fulfillment` will show the lag table you'll live in for the rest of the phase.

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] `kubectl -n kafka get kafka crunch-cluster` shows `READY: True` with 3 broker pods Running.
- [ ] `kubectl -n kafka get kafkatopic order.placed.v1` shows `PARTITIONS: 12`, `REPLICATION FACTOR: 3`, `READY: True`.
- [ ] `kafka-topics.sh --describe` shows 12 partitions, each with a 3-broker `Replicas` list and (in a healthy cluster) a 3-entry `Isr`.
- [ ] You produced two keyed records from the console and consumed them back with `--from-beginning`.
- [ ] You can state, in one sentence, why `min.insync.replicas=2` + producer `acks=all` survives one broker loss with no acknowledged-data loss (the durable trio, Lecture 1 §4.2).
- [ ] `localhost:9092` reaches the cluster (port-forward or `docker compose` fallback) so exercises 2–3 can connect.

---

## Stretch

- Delete one broker pod (`kubectl -n kafka delete pod crunch-cluster-dual-role-1`) and re-run `kafka-topics.sh --describe` *immediately*. Watch the `Isr` lists shrink to 2 entries and leadership move off the dead broker, then watch them heal as the pod restarts. You just observed leader election and ISR shrink/grow live — the Lecture 1 §4 protocol in motion.
- Apply a second `KafkaTopic` for `cart.changelog` with `cleanup.policy: compact` and `partitions: 12`. Note in `ros2`-style discipline that the *only* difference from `order.placed.v1` is the cleanup policy — same cluster, opposite retention philosophy (Lecture 2 §2).
- Edit the `KafkaTopic` to `partitions: 6` and `kubectl apply`. Observe that Strimzi **refuses to decrease** partition count (you can only grow). This is the system enforcing Lecture 1 §2.4 — partition count is part of the contract.

---

When the cluster is healthy and reachable, move to [Exercise 2 — The order producer](exercise-02-order-producer.go).
