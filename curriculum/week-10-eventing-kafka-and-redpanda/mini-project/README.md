# Mini-Project — `order-events`: One Benchmark, Two Engines, Honest Numbers

> Build a benchmark harness that runs the **same** producer and consumer code against **both** Kafka (Strimzi/KRaft) and Redpanda, measures throughput and tail latency under identical load, and produces a decision memo recommending one for a hypothetical 200-engineer marketplace org — defended with *your* numbers, not a blog post.

This is the artifact that kills the week's worst habit: picking a broker because a vendor's benchmark said so. After this week, "Kafka or Redpanda?" is a question you answer the senior way — run *your* workload on both, measure throughput and p99/p99.9 latency and operational footprint, and write down the trade-off in numbers a staff engineer would sign off on.

**Estimated time:** ~12 hours, split across Thursday, Friday, and Saturday in the suggested schedule.

**Compounds forward:** This `order-events` spine becomes the event backbone of your **capstone Polyglot Marketplace**. The producer you harden here is the cart service's emitter; the consumer is the order service's fulfillment loop. The benchmark numbers become a paragraph in your capstone architecture document justifying your broker choice. Build it well now; you'll defend it in the capstone review.

---

## What you will build

A small repo `order-events` with four deliverables:

1. **`producer/`** — a single Go producer (reuse and harden exercise 2) that takes a `-bootstrap` flag, so the *same binary* drives Kafka and Redpanda. It must be idempotent, keyed by `order_id`, `acks=all`, and it must record per-record send latency to an HDR-style histogram.
2. **`consumer/`** — a single Python consumer group (reuse exercise 3) that takes a `--bootstrap` flag, commits manually (at-least-once), and records end-to-end latency (record timestamp → processed timestamp).
3. **`bench/`** — a harness that: stands up Kafka (Strimzi on Kind, or `docker compose` for a single node) and Redpanda (`docker compose`), creates an identical `order.placed.v1` (12 partitions, RF 3 where possible) on each, runs the producer at a fixed target rate and the consumer group, and collects throughput + latency for each engine.
4. **A decision memo** (`DECISION.md`, ~1 page) recommending one engine for a 200-engineer org, citing your measured throughput, p50/p99/p99.9 latency, and operational footprint (processes to run, config surface, ecosystem).

By the end you have a public repo of ~400–600 lines (Go + Python + shell/compose) plus a memo that demonstrates you can *defend a broker choice with evidence*.

---

## Why a benchmark and not a feature comparison

You could read both docs and make a table of features. Don't — not as the deciding artifact. A feature table tells you what each *can* do; it does not tell you what each *does on your workload*. The questions that actually decide a broker are:

- **At your target throughput, what is the tail latency?** Redpanda's thread-per-core model often wins at p99.9 because there is no GC pause; Kafka's batching often wins on raw throughput. Which matters more depends on whether your orders pipeline is latency-bound (a user waiting) or throughput-bound (a nightly batch). You cannot know without measuring.
- **What is the operational footprint?** Count the processes, the config files, the things that page you. Kafka with KRaft is brokers + controllers; Redpanda is one binary per node. Fewer moving parts is a real, measurable operational saving — quantify it.
- **What is the ecosystem cost?** Connectors, tooling, hiring. This is qualitative but real; name it honestly in the memo.

A benchmark forces you to answer the first two with numbers. That is the senior-shop convention in 2026: measure, then decide.

---

## Repo layout

```
order-events/
├── README.md
├── DECISION.md                 # the 1-page memo (the headline deliverable)
├── producer/
│   ├── go.mod
│   └── main.go                 # hardened exercise-2 producer + latency histogram
├── consumer/
│   ├── requirements.txt
│   └── consumer.py             # hardened exercise-3 consumer + e2e latency
├── bench/
│   ├── docker-compose.kafka.yml
│   ├── docker-compose.redpanda.yml
│   ├── run-bench.sh            # stand up engine, create topic, run load, collect
│   └── report.py               # parse latencies, print throughput + p50/p99/p99.9
└── test/
    ├── test_consumer_commit.py # unit test: commit-after-process logic
    └── test_report_percentiles.py  # unit test: the percentile math
```

---

## Deliverable 1 — the portable producer

Harden exercise 2 into a benchmark-grade producer. It must:

- Take `-bootstrap`, `-rate` (records/sec target), and `-duration` flags. The *same binary* runs against `localhost:9092` (Kafka) and `localhost:9192` (Redpanda) — only the flag changes. This portability is the whole point: it proves your code is engine-agnostic (Lecture 2 §1.2).
- Keep idempotence, keying by `order_id`, and `acks=all`.
- Pace itself to the target rate (a simple token-bucket / ticker is fine) so both engines see *identical* offered load.
- Record per-send latency (enqueue → delivery report) into a histogram (use an HDR-histogram library, or bucket manually — the point is p99.9, which a naive average hides).
- Embed a high-resolution send timestamp in each record so the consumer can compute true end-to-end latency.

---

## Deliverable 2 — the portable consumer

Harden exercise 3. It must:

- Take `--bootstrap` and `--group`, commit manually after processing (at-least-once).
- Read the embedded send timestamp and record **end-to-end latency** (produce → consume → process) into a histogram.
- Be idempotent in its "processing" (even if it's just a counter keyed by `order_id`) — because at-least-once means a redelivery, and a benchmark that double-counts duplicates lies.
- Print throughput (records/sec consumed) and the e2e latency percentiles on shutdown.

---

## Deliverable 3 — the benchmark harness

`run-bench.sh` must, for a given engine:

1. Stand it up (`docker compose -f docker-compose.<engine>.yml up -d`, or your Kind cluster for Kafka).
2. Create `order.placed.v1` with 12 partitions (RF 3 if the engine has 3 nodes; RF 1 for a single-node compose — note the asymmetry in your memo).
3. Run the producer at the target rate for the duration, then the consumer until it drains.
4. Collect producer send-latency and consumer e2e-latency histograms.
5. Tear down.

Run it for **both** engines at the **same** target rate (e.g., 10k records/sec for 60 s), then a higher rate to find where each saturates. `report.py` parses the histograms and prints a comparison table.

Expected shape of the output:

```
ENGINE     TARGET   ACHIEVED  p50(ms)  p99(ms)  p99.9(ms)  NOTES
kafka      10000    9980      3.1      14.2     58.0       RF=3, KRaft, 3 brokers
redpanda   10000    9995      2.4      9.8      21.0       RF=3, 3 nodes, thread-per-core
--------------------------------------------------------------------------------
kafka      50000    41200     8.0      62.0     210.0      saturating; lag climbed
redpanda   50000    48900     5.5      31.0     74.0       headroom at the tail
```

> **Your numbers will differ** — laptop, disk, and Docker all matter. The *shape* is what you report and defend: where each engine wins, where each saturates, and at what tail. A memo that says "Redpanda was 3x faster" without naming the rate, the percentile, and the hardware is exactly the unfounded claim this project teaches you not to make.

---

## Deliverable 4 — the decision memo

`DECISION.md`, roughly one page, must:

1. State the **scenario**: a 200-engineer marketplace org, order-spine throughput target, latency SLO (e.g., p99 produce-to-consume < 50 ms), and operational constraints.
2. Present **your measured numbers** in a table (throughput, p50/p99/p99.9 for both engines at two load levels).
3. Name the **operational footprint** difference concretely (process count, config surface, ecosystem/connectors, hiring).
4. **Recommend one**, and — this is the senior move — state the **conditions under which you'd choose the other**. ("Redpanda for the tail-latency win and the simpler footprint; Kafka if the org already runs Strimzi everywhere and the connector ecosystem is load-bearing.")
5. Acknowledge the **threats to validity** of your benchmark (single-node RF, laptop, short duration). A memo that pretends its laptop benchmark is production-grade is not defensible.

---

## Rules

- **You may** read the Kafka docs, the Redpanda docs, `confluent-kafka` source, and the HDR-histogram libraries.
- **You must** run the *same* producer binary and the *same* consumer code against both engines — only the bootstrap flag changes. If the two engines need different *application* code, you've violated the portability premise; fix it.
- **You must not** report an average latency as the headline number. The tail (p99.9) is the point; an average hides exactly the GC-pause and lock-contention behavior that distinguishes the engines.
- **You must** pace both engines at identical offered load. A benchmark where one engine got more traffic is not a comparison.
- Go 1.23+, Python 3.12+, `confluent-kafka(-go)`, Docker. No managed cloud broker (you're measuring the engines, not a vendor's SLA).

---

## Methodology notes (read before you run a single benchmark)

A benchmark is only as honest as its method. The following are not optional polish — they are the difference between a number a staff engineer trusts and a number they dismiss:

- **Warm up, then measure.** The first few seconds of any run include JIT warmup (Kafka's JVM), page-cache priming, and connection establishment. Discard the first 5–10 seconds of each run before computing percentiles, and say so in the memo. A cold-start latency in your p99.9 is measuring startup, not steady state.
- **Measure the offered-vs-achieved gap.** If you target 50k records/sec and the producer only achieves 41k, your benchmark has hit the producer's or the broker's ceiling — and *that* is the interesting result, not the latency at that point. Report both numbers (`TARGET` and `ACHIEVED`) in every row. A latency measured under a load the system couldn't actually sustain is meaningless.
- **Co-locate fairly or not at all.** Running the broker and the load generator on the same laptop means they fight for CPU. That's acceptable for a relative comparison (both engines suffer it equally) but say so. If you have two machines, put the broker on one and the load on the other and note it — your numbers will be cleaner.
- **Fix the record size.** Latency and throughput both depend heavily on record size. Pin it (e.g., a ~256-byte JSON order) and state it. Comparing a 256-byte run against a 4 KB run tells you nothing about the engines.
- **Run each configuration at least three times.** Tail latency is noisy. Three runs and report the median of the per-run p99.9, or pool the samples — either is defensible; one run is not.
- **RF asymmetry is a real threat to validity.** A single-node `docker compose` is RF 1; a 3-node Kafka or Redpanda is RF 3. RF 3 pays a replication cost RF 1 doesn't. If you compare a single-node Redpanda against a 3-broker Kafka you are measuring replication factor, not the engines. Either run both at the same RF, or state the asymmetry loudly in the memo's threats-to-validity section.

The point of all of this: when you write "Redpanda's p99.9 was 74 ms vs Kafka's 210 ms at 50k/s, RF 3, 256-byte records, two machines, median of three runs," that is a sentence a reviewer can act on. "Redpanda was faster" is a sentence a reviewer ignores. The whole project trains you to write the first sentence and never the second.

---

## Acceptance criteria

- [ ] A public GitHub repo named `c22-week-10-order-events-<yourhandle>`.
- [ ] The producer binary runs unchanged against both `localhost:9092` (Kafka) and the Redpanda port — proven by a single `go build` and two `-bootstrap` invocations.
- [ ] `run-bench.sh` stands up each engine, creates the topic, runs load, and tears down, for both engines.
- [ ] `report.py` prints throughput and p50/p99/**p99.9** (not just average) for both engines at two load levels.
- [ ] `colcon`-style tests pass: `test_consumer_commit.py` (commit-after-process), `test_report_percentiles.py` (percentile math against a known input).
- [ ] `DECISION.md` exists, fits ~one page, presents your numbers, recommends one engine, states the conditions for the other, and lists threats to validity.
- [ ] Committed and pushed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Producer correctness & portability** | 20 | Idempotent, keyed, `acks=all`, paced; the *same* binary runs against both engines via a flag. |
| **Consumer correctness** | 15 | Manual commit after processing (at-least-once); idempotent counting; e2e latency captured. |
| **Benchmark rigor** | 25 | Identical offered load on both; both engines stood up and torn down by the harness; two load levels; tail percentiles, not averages. |
| **Decision memo** | 25 | Numbers presented honestly; recommendation defended; conditions-for-the-other stated; threats to validity acknowledged. |
| **Tests** | 10 | Commit logic and percentile math both unit-tested and green. |
| **Docs & hygiene** | 5 | Clear README, run commands, no `build/` or `.venv/` checked in. |

**90+** is portfolio-grade and ready to drop into the capstone's broker-choice section. **70–89** works but the benchmark is soft (averages, mismatched load, or a hand-wavy memo). **Below 70** means the benchmark doesn't actually compare the engines fairly — fix that first.

---

## Stretch goals

- **Find the saturation point.** Sweep the target rate upward until each engine's lag stops converging (the consumer can't keep up). Report each engine's max sustainable throughput at your SLO, and the rate at which p99.9 blows past the SLO. This is the Universal-Scalability-Law thinking you'll formalize in Week 18, applied early.
- **Broker-loss drill.** Mid-benchmark, kill one broker/node on each engine. Measure the produce-latency spike during leader election (Kafka ISR vs Redpanda Raft) and the time to recover. Report which engine's failover was less disruptive to the tail.
- **Compaction throughput.** Add a compacted `cart.changelog` topic to both, write heavy key churn, and measure the log-cleaner's effect on produce latency. Note which engine's compaction was less disruptive.
- **CI job.** A GitHub Actions workflow that builds the producer, runs the tests, and runs a *short* (10 s) smoke benchmark against single-node Redpanda in a container, asserting the consumer drained with bounded lag. Green check on every push.

---

## A note on reading your results honestly

The hardest part of this project is not the code — it is resisting the urge to declare a winner. When your numbers come in, you will be tempted to write "Redpanda won" or "Kafka won." Resist it. The disciplined report names the *conditions* under which each led:

- "At 10k/s with 256-byte records, RF 3, both engines on one laptop, Redpanda's p99.9 was lower (X ms vs Y ms), consistent with its no-GC thread-per-core model; Kafka's achieved throughput at the saturation point was higher (A/s vs B/s), consistent with its batching."
- "Below the saturation point, both engines met the 50 ms p99 SLO; the tail divergence only appeared above ~40k/s."

That second sentence is the one a staff engineer respects, because it tells them *when the choice matters* — and for many workloads the honest answer is "below your load, either is fine; pick on operations." A benchmark that concludes "below our load it doesn't matter; we'll choose on operational footprint" is not a failure of the benchmark — it is often the *correct, most valuable* conclusion, and stating it confidently is a senior move. The skill this project builds is producing numbers honest enough to support whichever conclusion is true, including the boring one.

## How this connects to the rest of C22

- **Week 11 (exactly-once)** takes this producer/consumer and makes the consumer *idempotent for real*, with an outbox and idempotency keys — the redelivery you saw in exercise 3 part D becomes safe instead of double-counted.
- **Week 12 (Temporal)** replaces the choreographed order flow this spine carries with an orchestrated workflow — and you'll be able to say *why* you'd choose one over the other.
- **Week 14 (CDC)** feeds this same `order.placed.v1` from a Postgres WAL via Debezium, and your consumer code reads it unchanged — proving the log is the integration point.
- **Capstone** uses `order-events` as the literal event backbone, and `DECISION.md` becomes the broker-choice paragraph in your architecture document.

When you've finished, push the repo and take the [quiz](../quiz.md) with your notes closed.
