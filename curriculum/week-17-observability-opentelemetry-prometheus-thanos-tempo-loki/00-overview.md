# Week 17 — Observability: OpenTelemetry, Prometheus, Thanos, Tempo, Loki

Welcome to the week the system starts telling you the truth. For sixteen weeks you have been building a distributed system — services, a mesh, a Kafka spine, replicated Postgres — and asking it to behave. This week you stop asking and start *measuring*. By Friday you will have a single instrumentation standard (**OpenTelemetry**) flowing from every service into three correlated backends — metrics in **Prometheus + Thanos**, traces in **Tempo**, logs in **Loki** — joined in **Grafana**, with an **exemplar** that lets you click a spike on a latency graph and land on the exact trace that caused it.

The thing to internalize before anything else: **observability is not three separate tools you bolt on; it is one instrumented system viewed three ways, and the value is in the correlation, not the collection.** Anyone can scrape a metric. The skill — the thing that turns a 40-minute incident into a 4-minute one — is jumping *from* a metric spike *to* the trace that explains it *to* the logs that pin the line of code, without leaving Grafana and without guessing. That jump is what exemplars buy you, and building it correctly end-to-end is the spine of this week.

We assume Week 8's mesh is still running and Week 6's baseline OpenTelemetry instrumentation is in your services. The mesh gives you the network spans for free (Week 8, Lecture 2 §2.2); your application code gives you the business spans and the RED metrics. This week you wire both into a real backend and — crucially — make trace context survive the boundaries that break it: the gRPC call, the HTTP hop, and the one almost everyone gets wrong, the **Kafka boundary**, where the producer and consumer are different processes and the trace will silently split in two unless you propagate context through the message headers yourself.

One more framing that runs through the whole week. The naive instrumentation story is "add a library, get observability." The real story is a set of deliberate choices: which **histogram buckets** you pick (get them wrong and your p99 is a lie), how much you **sample** traces (100% will bankrupt you at scale; tail sampling is the 2026 answer), what your metric **cardinality** is (a `user_id` label will melt your Prometheus), and how long you keep data and where (Prometheus is local and short; Thanos makes it global and cheap and long). Each of these is a place where the easy default is the expensive mistake, and naming them is what separates an engineer who *installed* observability from one who *operates* it.

This week is where you stop flying blind and start flying on instruments.

## Learning objectives

By the end of this week, you will be able to:

- **Explain** the three signals (metrics, traces, logs) as views of one instrumented system, name what each is good and bad at, and articulate why correlation — not collection — is the value.
- **Instrument** a polyglot service (Go, Python, Rust) with the OpenTelemetry SDK and the OTel Collector: traces with proper context propagation, RED metrics with sane histogram buckets, and structured logs that carry the trace ID.
- **Propagate** W3C `traceparent` context across HTTP, gRPC, *and* a Kafka boundary, and prove trace continuity end-to-end — including the Kafka case where you must carry context in message headers yourself.
- **Stand up** Prometheus for local scraping and **Thanos** for global, deduplicated, long-term metric storage on object storage, and explain the Sidecar/Store/Query/Compactor topology and why each component exists.
- **Run** Tempo for traces and Loki for logs, both backed by the same object store as Thanos, and explain the "cheap object storage, index-light" design they share.
- **Write** PromQL that computes RED signals (rate, error ratio, latency quantiles from histograms) and reason precisely about `rate()`, `histogram_quantile()`, and the difference between `irate` and `rate`.
- **Build** a Grafana dashboard with **exemplars** that links a metric spike to its trace, and a trace whose span links to its logs — the trace-to-log jump that is the week's signature move.
- **Choose** a sampling strategy (head vs tail), set histogram buckets deliberately, and control cardinality — the three places where the easy default is the costly mistake.

## Prerequisites

This week assumes you have completed **C22 weeks 1–16**, or have equivalent fluency. Specifically:

- A working **Kind** cluster with the cart topology (`cart`, `inventory`, and at least one async consumer) deployable, ideally still **meshed** from Week 8 (the mesh's spans compose with yours).
- **Baseline OpenTelemetry** from Week 6: your services already emit *some* traces and metrics. This week deepens that into a real pipeline; you are not starting from zero.
- A running **Kafka or Redpanda** from Week 10 with at least one producer/consumer pair (e.g. `order.placed.v1`) — this is the boundary you'll prove trace continuity across.
- Comfort with **Kubernetes** (Deployments, Services, ConfigMaps, PVCs) and **`kubectl`** — you'll deploy a half-dozen observability components.
- Basic **PromQL** familiarity is helpful but not required; we build it from `rate()` up.
- An object store: **MinIO** (S3-compatible, runs in-cluster) stands in for S3/GCS. Thanos, Tempo, and Loki all write to it.

You do **not** need prior Thanos/Tempo/Loki experience. We start at "Prometheus scrapes a target" and build up to a globally-queryable, exemplar-linked, three-signal stack.

## Topics covered

- **The three signals, correlated**: metrics (cheap, aggregate, alerting), traces (expensive, per-request, causal), logs (verbose, detailed, the line of code) — what each answers, and why a trace ID threaded through all three is the whole game.
- **OpenTelemetry**: the SDK (Go/Python/Rust), the API/SDK split, the **OTel Collector** (receivers, processors, exporters) as the vendor-neutral pipeline, **semantic conventions** (the standard attribute names that make data portable), and **context propagation** via the W3C `traceparent`/`tracestate` headers.
- **Context across boundaries**: HTTP (header injection/extraction), gRPC (metadata + interceptors), and **Kafka** — the boundary that breaks silently, where you inject `traceparent` into message headers on produce and extract it on consume to keep one trace across two processes.
- **Metrics with Prometheus + Thanos**: the pull model and scrape config; **histograms** (and why bucket choice determines whether `histogram_quantile` tells the truth); **exemplars** (a trace ID attached to a histogram bucket sample); and **Thanos** — Sidecar (uploads blocks + serves recent data), Store Gateway (serves historical blocks from object storage), Query (deduplicates + fans out), Compactor (downsamples + compacts), Ruler — for global, long-term, HA metrics.
- **Traces with Tempo**: a trace backend that indexes *only* by trace ID and keeps the spans on cheap object storage, **TraceQL** for search, and the trace-to-metrics and trace-to-logs links that make Tempo the hub of correlation.
- **Logs with Loki**: "Prometheus for logs" — index the *labels*, not the log lines; **LogQL**; the discipline of low-cardinality labels (the same cardinality lesson as metrics) and why a `request_id` label is a Loki anti-pattern but a great *filter*.
- **Grafana as the single pane**: RED dashboards, the **exemplar** that turns a latency spike into a clickable trace, and the **trace-to-log** jump (a span's logs, found by trace ID in Loki) — the week's signature correlated debugging move.
- **The three costly defaults**: **sampling** (head vs tail; why 100% is unaffordable and tail sampling keeps the interesting traces), **histogram buckets** (chosen to match your SLO, not the library default), and **cardinality** (the label that multiplies your series count into an outage).

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                       | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | The three signals; OpenTelemetry SDK + Collector           |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Context propagation: HTTP, gRPC, the Kafka boundary        |    1h    |    2.5h   |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | Prometheus + Thanos; histograms, exemplars, PromQL         |    2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | Tempo + Loki; the trace-to-log jump in Grafana             |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Friday    | Sampling, buckets, cardinality; the costly defaults        |    0h    |    0h     |     1h     |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work                                      |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, review, dashboard polish                             |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                            | **6h**   | **7h**    | **4h**     | **3.5h**  | **5h**   | **12h**      | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./00-overview.md) | This overview (you are here) |
| [resources.md](./01-resources.md) | The OpenTelemetry, Prometheus/Thanos, Tempo, Loki, and Grafana docs worth your time |
| [lecture-notes/01-opentelemetry-and-context-propagation.md](./02-lecture-notes/01-opentelemetry-and-context-propagation.md) | The three signals, the OTel SDK + Collector, semantic conventions, and context propagation across HTTP/gRPC/Kafka |
| [lecture-notes/02-prometheus-thanos-tempo-loki-and-the-correlated-pane.md](./02-lecture-notes/02-prometheus-thanos-tempo-loki-and-the-correlated-pane.md) | Prometheus + Thanos, histograms/exemplars/PromQL, Tempo, Loki, the trace-to-log jump, and the costly defaults |
| [exercises/README.md](./03-exercises/00-overview.md) | Index of the three exercises |
| [exercises/exercise-01-otel-collector-and-the-pipeline.md](./03-exercises/exercise-01-otel-collector-and-the-pipeline.md) | Stand up the OTel Collector and route traces/metrics/logs to Tempo/Prometheus/Loki — the pipeline, end to end |
| [exercises/exercise-02-thanos-and-promql.yaml](./03-exercises/exercise-02-thanos-and-promql.yaml) | A complete Prometheus + Thanos deployment (Sidecar/Store/Query/Compactor) with the PromQL RED queries to run against it |
| [exercises/exercise-03-trace-context-across-kafka.py](./03-exercises/exercise-03-trace-context-across-kafka.py) | Propagate `traceparent` through Kafka message headers and prove one trace survives the producer→consumer boundary |
| [challenges/README.md](./04-challenges/00-overview.md) | Index of the weekly challenge |
| [challenges/challenge-01-the-trace-that-stops-at-kafka.md](./04-challenges/challenge-01-the-trace-that-stops-at-kafka.md) | Diagnose a trace that mysteriously ends at the producer, from the outside, and fix the context propagation |
| [quiz.md](./05-quiz.md) | 13 questions with a hidden answer key |
| [homework.md](./06-homework.md) | Six problems including the RED-dashboard-with-exemplars build and the cardinality-budget memo |
| [mini-project/README.md](./07-mini-project/00-overview.md) | `cart-observed`: the full three-signal stack on the cart topology, with exemplar-linked RED dashboards and a trace that survives Kafka |

## The "you can prove the correlation" promise

C22 uses a recurring marker for every exercise that ends in the system actually doing what you declared. This week's canonical one is the **trace-to-log jump** — proof that a single trace ID threads all three signals:

```
# A metric spike carries an exemplar (a trace ID) on the histogram bucket:
$ curl -s 'http://prometheus:9090/api/v1/query?query=...' | jq '.data.result[].exemplars'
[ { "labels": { "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736" }, "value": 1.91, ... } ]

# That same trace ID resolves to a full trace in Tempo:
$ curl -s "http://tempo:3200/api/traces/4bf92f3577b34da6a3ce929d0e0e4736" | jq '.batches | length'
3        # the cart -> inventory -> kafka-consumer trace, intact across the boundary

# And the logs for that trace ID are one LogQL query away in Loki:
$ logcli query '{service="cart"} | json | trace_id="4bf92f3577b34da6a3ce929d0e0e4736"'
... the exact log lines for that one request ...
```

If the **same trace ID** appears on the metric exemplar, resolves to a trace in Tempo, and filters the logs in Loki, you have *correlated* observability — verifiable, not vibes. The point of this week is to make that jump ordinary: spike → trace → log, in three clicks, the way Week 8 made `istioctl x describe` ordinary. An observability stack where the three signals *don't* share a trace ID is three expensive silos, and catching that gap is the difference between debugging with instruments and debugging with hope.

## Stretch goals

If you finish the regular work early and want to push further:

- Replace **head sampling** with the Collector's **tail sampling** processor: keep 100% of error traces and slow traces, sample the boring 200-OK fast path at 1%. Prove an error trace is *never* dropped while the firehose is tamed.
- Wire **Grafana Alerting** (or Prometheus Alertmanager) off a PromQL error-budget burn-rate query — a preview of next week's SLO math, alerting before you've formally defined the SLO.
- Add **OTel Collector tail-based span metrics** (the `spanmetrics` connector) so you derive RED metrics *from your traces*, and compare them against the metrics your SDK emits directly. Reason about which to trust.
- Stand up **Thanos Compactor** downsampling and query a *year* of (synthetic) data at 5-minute resolution in milliseconds — the payoff of the downsampling tier.

## Up next

Week 18 takes the signals you can now collect and correlate and asks the harder question: **what should they be?** You'll define **SLIs** that mean something, set **SLOs** and **error budgets**, and compute **multi-window multi-burn-rate** alerts — alerts that page you fast on a catastrophe and slowly on a simmer, both off the *same* error-budget math. Everything you instrumented this week becomes the raw material: an SLI is a PromQL query over the very `istio_requests_total` and your-app RED metrics you wired up here. You cannot have an SLO without observability; this week is the foundation next week stands on. Push your `cart-observed` mini-project before you start it.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
