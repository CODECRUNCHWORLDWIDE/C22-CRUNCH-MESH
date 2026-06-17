# Week 17 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 18. Answer key is at the bottom — don't peek.

---

**Q1.** Why is correlation, not collection, the value of observability?

- A) Collecting telemetry is impossible, so you have to correlate instead.
- B) Each signal alone is a partial view (a metric says "p99 spiked," a trace says "this request was slow," a log says "this line failed"); only a shared trace ID joining all three turns three silos into a diagnosis.
- C) Correlation is cheaper than collection.
- D) Metrics are always wrong, so you correlate to fix them.

---

**Q2.** What is the OpenTelemetry API/SDK split, and why does it matter?

- A) The API is for Go, the SDK is for Python.
- B) Your code (and libraries) call the thin, stable **API**; you wire up the **SDK** (sampling, exporter, batching) once at startup. Swap the SDK config to change backends without re-instrumenting — telemetry is portable.
- C) The API is for traces, the SDK is for metrics.
- D) They're the same thing; the names are interchangeable.

---

**Q3.** What does the OTel Collector's `memory_limiter` processor do, and why is it non-negotiable?

- A) It limits how much memory your apps use.
- B) It sheds telemetry load before the Collector OOMs; without it, a telemetry spike crashes the Collector and takes down your visibility exactly when you need it most.
- C) It compresses traces to save memory.
- D) It's optional and rarely used.

---

**Q4.** Trace context propagates "for free" across HTTP and gRPC but breaks silently across Kafka. Why?

- A) Kafka doesn't support headers.
- B) HTTP/gRPC are synchronous — the SDK auto-instrumentation owns the wire and injects/extracts `traceparent`. Kafka is async and decoupled (producer and consumer are different processes with no shared connection), so you must carry `traceparent` in the message headers yourself.
- C) Kafka encrypts the trace ID.
- D) Tempo can't store Kafka traces.

---

**Q5.** A consumer span shows up in Tempo as a *root* (no parent) when it should be a child of the producer. What's the cause?

- A) Tempo is misconfigured.
- B) The producer didn't `inject` `traceparent` into the Kafka message headers (or the consumer didn't `extract` it), so the consumer had nothing to attach to and started a new trace — the trace split at the boundary.
- C) The consumer's clock is wrong.
- D) Sampling dropped the parent span.

---

**Q6.** What does the Thanos Query component do that a single Prometheus cannot?

- A) It scrapes targets faster.
- B) It fans a PromQL query out across all StoreAPIs (every sidecar's recent data + every store gateway's historical data) and **deduplicates** the HA Prometheus replicas into one global view.
- C) It stores metrics locally.
- D) It replaces PromQL with a new language.

---

**Q7.** Why must the Thanos Compactor run as exactly one instance (a singleton)?

- A) It's faster with one.
- B) Two compactors operating on the same object-storage bucket will corrupt each other's compaction/downsampling work; the component is designed to be a singleton per bucket.
- C) It needs a license per instance.
- D) Kubernetes only allows one.

---

**Q8.** In `histogram_quantile(0.99, sum(rate(..._bucket[5m])) by (le))`, why does the bucket choice determine whether the p99 is honest?

- A) It doesn't; the quantile is always exact.
- B) `histogram_quantile` *interpolates within* a bucket, so if your p99 falls in a wide bucket (say 1s–10s) the reported value is a guess; you place buckets densely around your SLO threshold so the quantile is computed where the boundaries are fine.
- C) Buckets only affect the rate, not the quantile.
- D) The `by (le)` makes buckets irrelevant.

---

**Q9.** What is an exemplar, and what does it enable in Grafana?

- A) An example query you save.
- B) A **trace ID attached to a metric sample** (e.g. on a histogram bucket); Grafana renders it as a clickable dot on the latency graph that opens the exact trace — the metric-to-trace jump.
- C) A type of alert.
- D) A downsampled metric.

---

**Q10.** Why is `trace_id` a catastrophic *label* in both Prometheus and Loki, but fine as a *filter*?

- A) It isn't; trace_id is a great label.
- B) A label creates one time series / log stream per distinct value — `trace_id` is per-request (unbounded cardinality), which OOMs Prometheus and melts Loki; as a *filter* (`| json | trace_id="..."`) it's parsed at query time with no cardinality cost.
- C) Labels are encrypted but filters aren't.
- D) Loki supports it but Prometheus doesn't.

---

**Q11.** What's the difference between head sampling and tail sampling, and why does tail sampling need a gateway Collector?

- A) They're the same; "head" and "tail" are aliases.
- B) Head sampling decides at the *start* (blind — drops 90% of errors/slow traces too); tail sampling decides *after* the trace completes (keep all errors/slow, sample the boring fast path). Tail needs the *whole* trace to decide, which only lands together at a gateway, never at a per-node agent.
- C) Tail sampling is cheaper because it keeps less.
- D) Head sampling runs in Grafana, tail in Tempo.

---

**Q12.** Walk the trace-to-log jump: you see a p99 spike on the cart dashboard. What are the steps to the root cause, and what makes them work?

- A) Restart cart and see if it recovers.
- B) Hover the spike → click its **exemplar** (a trace ID) → Tempo opens that **trace** (the slow span is named, e.g. inventory) → click "Logs for this span" → Loki shows the **log lines** for that trace ID. It works because one trace ID threads all three signals.
- C) Grep the logs by timestamp and guess which request.
- D) Read the metric's description.

---

**Q13.** `rate()` vs `irate()` on a counter — when do you use which, and what's the rule about aggregating counters?

- A) They're identical.
- B) `rate()` is the smooth average over the window (use it for graphs and alerts); `irate()` uses only the last two samples (spiky, for instantaneous debugging). And you must always `rate()` a counter *before* aggregating — `sum(counter)` is meaningless; `sum(rate(counter[5m]))` is the per-second rate across instances.
- C) `irate()` is always better; use it everywhere.
- D) You aggregate first, then rate.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — Each signal is a partial view; the shared trace ID joining them is the diagnosis. Collection is easy; correlation is the value. (Lecture 1 §1.)
2. **B** — Thin stable API for code; SDK wired once for backend/sampling; swap SDK config, not instrumentation. (Lecture 1 §2.1.)
3. **B** — Sheds load before OOM; a Collector with no memory limit dies under a spike and takes visibility with it. (Lecture 1 §2.2.)
4. **B** — Synchronous wire (HTTP/gRPC) → SDK auto-propagates; async/decoupled (Kafka) → you carry `traceparent` in message headers yourself. (Lecture 1 §4.3.)
5. **B** — Missing `inject` on produce or `extract` on consume; the consumer had no parent context, so it started a new trace — the split. (Lecture 1 §4.3; Challenge 1.)
6. **B** — Fans out across all StoreAPIs and deduplicates the HA replicas into one global view. (Lecture 2 §1.2.)
7. **B** — Two compactors corrupt each other's work on the same bucket; it's a per-bucket singleton. (Lecture 2 §1.2; Exercise 2.)
8. **B** — `histogram_quantile` interpolates within a bucket, so a wide bucket near the quantile makes the value a guess; align buckets to the SLO. (Lecture 2 §1.3, §6.2.)
9. **B** — A trace ID on a metric sample; Grafana renders a clickable dot that opens the trace — the metric-to-trace link. (Lecture 2 §2.3.)
10. **B** — One series/stream per value; `trace_id` is unbounded → cardinality explosion as a label; as a parsed filter it's free. (Lecture 2 §2.4, §6.3.)
11. **B** — Head = blind, at the start; tail = informed, after completion (keep errors/slow); tail needs the whole trace, which only the gateway sees. (Lecture 1 §5; Lecture 2 §6.1.)
12. **B** — Spike → exemplar → Tempo trace → Loki logs, all on one trace ID. The signature correlated-debugging move. (Lecture 2 §5.2.)
13. **B** — `rate` smooth (alerts/graphs), `irate` spiky (instant); always `rate` a counter before aggregating. (Lecture 2 §1.3.)

</details>

---

If you scored under 9, re-read the lecture sections cited in the answers you missed. If you scored 11 or higher, you're ready for the [homework](./06-homework.md).
