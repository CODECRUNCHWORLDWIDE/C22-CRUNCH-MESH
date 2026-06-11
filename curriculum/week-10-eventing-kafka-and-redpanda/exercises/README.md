# Week 10 — Exercises

Three focused drills on a running Kafka cluster. Each takes 45–75 minutes. Do them in order — exercise 3 consumes what exercise 2 produces, and both run against the cluster you stand up in exercise 1. Run everything against your **Kind cluster** with Strimzi (or, if your cluster is broken, a single-node `docker compose` Kafka or Redpanda — each exercise notes the fallback).

## Index

1. **[Exercise 1 — Strimzi on Kind](exercise-01-strimzi-on-kind.md)** — deploy a 3-broker KRaft Kafka cluster on Kind via the Strimzi operator, create `order.placed.v1` with 12 partitions / RF 3 as a `KafkaTopic` CR, and read the cluster's state with `kafka-topics.sh` and `kafka-consumer-groups.sh`. (~75 min, guided)
2. **[Exercise 2 — The order producer](exercise-02-order-producer.go)** — an idempotent, keyed Go producer for `order.placed.v1` with `acks=all`, delivery-report handling, and a clean flush-and-close. Prove every record landed with `LAG`-aware verification. (~60 min, runnable)
3. **[Exercise 3 — The order consumer group](exercise-03-order-consumer.py)** — a Python consumer group with **manual offset commits**, cooperative-sticky rebalance callbacks, and the dual-group fan-out demo. Reproduce at-least-once redelivery on purpose by crashing before commit. (~60 min, runnable)

## How to work the exercises

- Have your **Kind cluster** running with Strimzi before you start exercise 2 or 3. `kubectl -n kafka get kafka` should show `Ready`. If it doesn't, the `docker compose` fallback in exercise 1 is your route.
- **Read the lag table before and after every change.** `kafka-consumer-groups.sh --describe --group <g>` is your ground truth, exactly as `ros2 topic info -v` was in the sibling course. Train the habit of diffing `CURRENT-OFFSET` against `LOG-END-OFFSET` by eye.
- When a consumer "isn't working," run the §3.4 decision tree from Lecture 2 before you touch code. Topic first, members second, lag-shape third, idempotency fourth, key last.
- Each runnable exercise (`.go`, `.py`) ends with an **expected output** block. If your output doesn't match, you're not done.

## Running the Go producer

The Go producer uses `confluent-kafka-go/v2` (librdkafka-backed). From a fresh module directory:

```bash
go mod init order-producer
go get github.com/confluentinc/confluent-kafka-go/v2/kafka
go run exercise-02-order-producer.go -bootstrap localhost:9092 -count 100
```

On macOS/Linux librdkafka ships with the module; no system package needed for the dynamic build. If you hit a CGO error, `CGO_ENABLED=1` and a C toolchain (`build-essential` / Xcode CLT) are the fix.

## Running the Python consumer

The Python consumer uses `confluent-kafka` (the same librdkafka under the hood, so semantics match the Go producer exactly):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install confluent-kafka
python3 exercise-03-order-consumer.py --bootstrap localhost:9092 --group order-fulfillment
```

Run two copies in two terminals with the same `--group` to watch a cooperative-sticky rebalance split the 12 partitions between them. Run a third with a *different* `--group` to watch fan-out: it reads every record independently.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c22-week-10` to compare.
