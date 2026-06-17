# Lecture 2 — Prometheus, Thanos, Tempo, Loki, and the Correlated Pane

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can stand up Prometheus + Thanos for global long-term metrics, Tempo for traces, and Loki for logs; write PromQL for the RED signals and reason about `rate`/`histogram_quantile`; build a Grafana dashboard with exemplars and the trace-to-log jump; and make the three costly defaults — sampling, histogram buckets, cardinality — deliberately instead of by accident.

Lecture 1 got the telemetry *emitted* and the trace context *propagated*. This lecture is where it lands and becomes useful. Three parts: (1) metrics with Prometheus + Thanos and the PromQL to read them, (2) traces with Tempo and logs with Loki, (3) the correlation — exemplars and the trace-to-log jump — plus the three defaults that quietly cost you money or truth.

The sentence to carry through:

> **Prometheus is your fast, local, short-memory metric brain; Thanos gives it a global, deduplicated, cheap, long memory — and Tempo and Loki are the same trick (index light, store on cheap object storage) applied to traces and logs, so the whole stack rides one bucket.**

---

## Part 1 — Metrics: Prometheus and Thanos

### 1.1 Prometheus: the pull model and its limits

Prometheus **scrapes** (pulls) a `/metrics` endpoint from each target on an interval, stores the samples in a local time-series database (TSDB), and answers PromQL queries. The pull model is a feature: Prometheus discovers targets (via Kubernetes service discovery), and a target that's down simply fails to scrape — which is itself a signal (`up == 0`). Your services expose `/metrics` (via the OTel SDK's Prometheus exporter or the Collector's `prometheus` exporter from Lecture 1 §2.2), and the mesh exposes `istio_requests_total` (Week 8 §2.3).

```yaml
# prometheus.yml — scrape your services and the mesh, attach external labels for Thanos dedup.
global:
  scrape_interval: 15s
  external_labels:
    cluster: kind-shop
    replica: A                 # CRUCIAL for Thanos: this labels THIS Prometheus replica
scrape_configs:
  - job_name: cart-topology
    kubernetes_sd_configs: [{ role: pod }]
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: "true"          # only scrape pods that opt in via annotation
```

Prometheus is brilliant and *deliberately limited*: it stores data **locally** (lost if the pod dies, unless you use a PVC), keeps it for a **bounded retention** (weeks, not years), and is a **single instance** (run two for HA and you now have two databases that disagree at the edges). Those three limits — durability, retention, and global/HA view — are exactly what Thanos fixes.

### 1.2 Thanos: global, long-term, deduplicated metrics

Thanos turns a set of independent Prometheis into one globally-queryable, long-retention, HA metric system, by adding components around them and putting the bulk data on **object storage** (S3/GCS/MinIO). The components and *why each exists*:

- **Sidecar** — runs next to each Prometheus. Two jobs: it **uploads** Prometheus's TSDB blocks to the object store (durability + long retention), and it **serves** Prometheus's *recent* (not-yet-uploaded) data over the Thanos StoreAPI so queries see fresh data.
- **Store Gateway** — serves the *historical* blocks straight from object storage over StoreAPI. This is the long-term read path: query a metric from six months ago and it comes from the bucket via the Store Gateway, not from any Prometheus.
- **Query** — the front door. It implements PromQL, fans the query out to *all* StoreAPIs (every sidecar + every store gateway), merges the results, and — critically — **deduplicates** the HA replicas. Run Prometheus `replica: A` and `replica: B` scraping the same targets, and Thanos Query collapses their near-identical series into one, so HA stops meaning "double-counted graphs."
- **Compactor** — a background job that **compacts** small blocks into bigger ones (faster reads) and **downsamples** them (5-minute and 1-hour resolutions alongside the raw data). Downsampling is the payoff: a year-long query at 1-hour resolution scans a tiny fraction of the data of the raw series, so long-range dashboards are fast and cheap. The Compactor is a *singleton* — run exactly one per bucket, or two will corrupt each other's compaction.
- **Ruler** (optional) — evaluates recording/alerting rules globally across the merged data.

```
                 PromQL
                   │
            ┌──────▼──────┐   deduplicates HA replicas, fans out to every StoreAPI
            │ Thanos Query│
            └──┬───────┬──┘
     StoreAPI  │       │  StoreAPI
   ┌───────────▼─┐   ┌─▼──────────────┐
   │ Sidecar (A) │   │ Sidecar (B)    │   <- recent data from each Prometheus replica
   │  + Prom A   │   │  + Prom B      │
   └──────┬──────┘   └──────┬─────────┘
          │ upload blocks   │ upload blocks
          ▼                 ▼
   ┌─────────────── object storage (MinIO/S3) ───────────────┐
   │   TSDB blocks (raw + 5m + 1h downsampled)                │
   └──────────────────────┬──────────────────────────────────┘
                ┌──────────▼──────────┐      ┌────────────┐
                │ Store Gateway       │      │ Compactor  │ (singleton)
                │ (historical reads)  │      │ compact +  │
                └─────────────────────┘      │ downsample │
                                             └────────────┘
```

The mental model: **Prometheus is the hot edge (fast, recent, local); the object store is the cold, durable, global truth; Thanos Query stitches hot + cold into one PromQL surface and dedupes the HA replicas.** That `replica` external label from §1.1 is the seam dedup keys on — forget it and Thanos can't tell the replicas apart, so it either double-counts or can't merge.

### 1.3 PromQL for the RED signals

RED — **Rate, Errors, Duration** — is the per-service dashboard shape. All three are PromQL over the request counter and the latency histogram. Start with the counter `http_server_requests_total` (or the mesh's `istio_requests_total`):

```promql
# RATE — requests per second to cart, over the last 5 minutes.
# rate() computes the per-second average increase of a COUNTER, handling resets.
sum(rate(http_server_requests_total{service="cart"}[5m]))

# ERRORS — the error RATIO (5xx as a fraction of all requests). This is the SLI shape
# you'll formalize next week: good-or-bad events over total events.
sum(rate(http_server_requests_total{service="cart", code=~"5.."}[5m]))
/
sum(rate(http_server_requests_total{service="cart"}[5m]))

# DURATION — p99 latency, ESTIMATED from the histogram buckets.
# histogram_quantile reads the _bucket series; the estimate is only as good as the buckets.
histogram_quantile(0.99,
  sum(rate(http_server_request_duration_seconds_bucket{service="cart"}[5m])) by (le)
)
```

Three points of precision that separate someone who *writes* PromQL from someone who *trusts* it:

- **`rate()` vs `irate()`.** `rate()` is the average per-second increase over the whole window — smooth, good for graphs and alerts. `irate()` uses only the *last two* samples — spiky, good for fast-moving debugging, terrible for alerting (it's noisy and easy to miss between samples). Default to `rate()`; reach for `irate()` only to see instantaneous behavior.
- **Always `rate()` before aggregating a counter.** `sum(counter)` is meaningless (it sums absolute counts including across restarts); `sum(rate(counter[5m]))` is the per-second rate across instances, which is what you want. And `rate` must wrap a *counter*, not a gauge.
- **`histogram_quantile` is an *estimate*.** It linearly interpolates *within* a bucket. If your p99 falls in a bucket spanning 1 s to 10 s, your "p99" could be anywhere in that range — the function will report a number, but it's fiction. This is why buckets matter (§6.2): the quantile is only as truthful as the bucket boundaries near where it falls. The `by (le)` is mandatory — `histogram_quantile` needs the `le` ("less than or equal") bucket-boundary label, summed across everything else.

### 1.4 The `up` metric and the meta-monitoring point

Prometheus synthesizes an `up` metric per target: `1` if the last scrape succeeded, `0` if it failed. `up == 0` is your "the thing is gone" signal — and it's a reminder that **your monitoring needs monitoring**. A Prometheus that died scrapes nothing and alerts nothing; the silence looks like health. The standard guard is a second, independent Prometheus (or a dead-man's-switch alert that fires *unless* a heartbeat is present) so an absence of data is itself alertable. We don't build the full meta-monitoring stack this week, but name the gap: an observability stack that can't observe its own failure is a single point of blindness.

### 1.5 Recording rules: precompute the expensive queries

One more PromQL operational tool you'll lean on next week. A dashboard or alert that runs a heavy aggregation (a high-cardinality `sum(rate(...))` over many series) on *every* evaluation is slow and expensive. A **recording rule** evaluates that expression on a schedule and stores the result as a new, cheap time series:

```yaml
# recording_rules.yml — precompute the cart request rate and error ratio once.
groups:
  - name: cart-red
    interval: 30s
    rules:
      - record: cart:request_rate:5m            # the convention: level:metric:operation
        expr: sum(rate(http_server_requests_total{service="cart"}[5m]))
      - record: cart:error_ratio:5m
        expr: |
          sum(rate(http_server_requests_total{service="cart",code=~"5.."}[5m]))
          / sum(rate(http_server_requests_total{service="cart"}[5m]))
```

Now your dashboard queries `cart:error_ratio:5m` — a single pre-aggregated series — instead of recomputing the ratio from raw buckets every refresh. Recording rules matter for this course specifically because **next week's error-budget burn-rate alerts** are multi-window expressions that are expensive to evaluate live; you precompute the per-window error ratios as recording rules and let the burn-rate alert compare cheap recorded series. The naming convention `level:metric:operation` (e.g. `cart:error_ratio:5m`) is a community standard worth adopting — it tells the next engineer exactly what a recorded series is without reading the rule.

Two guardrails on recording rules, since they're easy to misuse:

- **Don't over-record.** A recording rule is itself a series Prometheus must evaluate and store every interval; recording hundreds of rarely-queried expressions just moves the cost, it doesn't remove it. Record the expressions that are *expensive and frequently queried* (the dashboard's RED panels, the burn-rate windows), not everything.

- **Record the building blocks, not the final answer.** Prefer recording the raw rate/ratio and computing the final alert expression from recorded series, so one recorded block feeds many alerts and dashboards. Recording a single hyper-specific "is the fast-burn alert firing" boolean is brittle; recording `cart:error_ratio:1h` feeds the fast-burn alert, the dashboard, and the budget-remaining gauge alike.

---

## Part 2 — Traces with Tempo, logs with Loki

### 2.1 Tempo: traces on cheap object storage

The expensive way to store traces is to index every attribute (so you can search "all traces where `http.status = 500`"). **Tempo** makes the opposite, cheaper bet: it indexes **only by trace ID**, and keeps all the span data on the same object storage as Thanos. Looking up a trace *by ID* (the common case — you got the ID from a metric exemplar or a log) is dirt cheap. Searching by attribute is served by **TraceQL** over a lighter secondary index, and by the metrics-generator deriving searchable signals from spans.

```yaml
# tempo.yaml (single-binary lab mode) — object-store backend, same MinIO bucket as Thanos.
storage:
  trace:
    backend: s3
    s3:
      endpoint: minio:9000
      bucket: tempo
      access_key: minio
      secret_key: minio123
      insecure: true
distributor:
  receivers:
    otlp:
      protocols:
        grpc: { endpoint: 0.0.0.0:4317 }   # the Collector exports traces here
metrics_generator:
  storage:
    path: /var/tempo/generator/wal
    remote_write:                            # derive RED metrics + service graph FROM spans
      - url: http://prometheus:9090/api/v1/write
```

The `metrics_generator` is a quiet power move: Tempo can *derive* RED metrics and a service graph **from the traces themselves** and remote-write them to Prometheus. Now you have RED metrics even for services that don't emit them directly, and a service-dependency graph built from real traffic. (The honest caveat, same as the mesh's: these are sampled-trace-derived, so treat them as a corroborating view, not the primary SLI source.)

### 2.2 TraceQL: finding the trace you don't have an ID for

When you *don't* already have a trace ID (you're exploring, not following a link), **TraceQL** searches by span attributes:

```
{ resource.service.name = "inventory" && duration > 500ms }          # slow inventory spans
{ span.http.response.status_code = 500 }                              # any 500
{ resource.service.name = "cart" && span.messaging.system = "kafka" } # cart's Kafka spans
```

But the *fast path* — and the one this week optimizes for — is arriving with a trace ID already in hand from an exemplar or a log, and Tempo serving the full trace by ID in milliseconds. Search is the fallback; correlation is the main road.

### 2.3 Exemplars: the metric-to-trace link

Here is the join that makes a dashboard a debugging tool. An **exemplar** is a *trace ID attached to a metric sample* — specifically, when your histogram records an observation, the SDK can attach the trace ID of the request that produced it to that bucket sample. Prometheus stores exemplars alongside the metric (with exemplar storage enabled), and Grafana renders them as clickable dots on the latency graph.

So the flow is: you see a p99 spike → you hover the spike → there's an exemplar dot carrying a trace ID → you click it → Grafana opens that exact trace in Tempo. You went from "p99 is bad" to "*here is the slow request*" in one click, no guessing which trace corresponds to the spike. This requires three things lined up: the SDK recording exemplars on histograms, **OpenMetrics** exposition (exemplars ride the OpenMetrics format — recall the Collector's `enable_open_metrics: true` in Lecture 1 §2.2), and Prometheus exemplar storage on. Miss any one and the dots never appear.

```promql
# the histogram query whose buckets carry exemplars; Grafana shows the trace-ID dots on it.
histogram_quantile(0.99,
  sum(rate(http_server_request_duration_seconds_bucket{service="inventory"}[5m])) by (le))
```

### 2.4 Loki: logs indexed by label, not by line

**Loki** is "Prometheus for logs." Its bet: don't index the log *contents* (expensive, that's Elasticsearch's model); index only a small set of **labels** (`service`, `level`, `namespace`) and keep the raw log lines in chunks on — again — the same object storage. You select a *stream* by labels, then filter the lines with a pipeline:

```logql
# select the cart stream, parse JSON, keep errors, find one trace's lines:
{service="cart"} | json | level="error"
{service="cart"} | json | trace_id="4bf92f3577b34da6a3ce929d0e0e4736"   # the trace-to-log query
{service="inventory"} |= "connection pool exhausted"                    |~ "(?i)timeout"
```

The cardinality discipline from metrics applies *identically* and is the single most common Loki mistake: **labels must be low-cardinality.** `service="cart"` is a fine label (a handful of values). `trace_id="..."` as a *label* is catastrophic (one stream per request — millions of streams), but `trace_id` as a *filter* on a parsed field (`| json | trace_id="..."`) is exactly right and cheap. The rule: index a few stable, low-cardinality labels; everything high-cardinality (trace ID, user ID, request ID) is a *filter*, parsed out of the line at query time, never a label. Get this backwards and Loki falls over the same way a `user_id` metric label melts Prometheus (§6.3).

The corollary that makes Loki *useful* despite the low-cardinality rule: **your logs must be structured (JSON), and they must carry the trace ID as a field.** A plaintext log line is just text Loki greps; a JSON line is parseable (`| json`), so you can filter on `trace_id`, `level`, `order_id` at query time without paying for them as labels. This is why Lecture 1's instrumentation emits structured logs with the trace ID injected — the trace ID in the log *body* (not as a label) is exactly what powers the trace-to-log jump (§5.2). The discipline: a small set of stable labels (`service`, `namespace`, `level`), structured JSON bodies, and the trace ID as a *field*. That combination gives you Loki's cheap storage and the high-cardinality filtering you need, without the cardinality explosion.

### 2.5 The shared-storage insight: one bucket, three backends

Step back and notice what Thanos, Tempo, and Loki have in common, because it's the architectural idea that makes this whole stack affordable. All three make the same bet: **keep a light index, push the bulk data to cheap object storage.**

- **Thanos** keeps recent metrics hot in Prometheus and ships TSDB blocks to the bucket; the Store Gateway reads history from the bucket.
- **Tempo** keeps a trace-ID index (and a light secondary index for TraceQL) and pushes the spans to the bucket.
- **Loki** keeps a label index and pushes the log chunks to the bucket.

So your *entire* long-term observability data — a year of metrics, all your traces, all your logs — lives on the same S3/GCS/MinIO bucket, which is the cheapest durable storage there is (cents per GB-month, eleven-nines durability, infinite scale). The hot, expensive, indexed tier stays small; the cold, cheap, bulk tier grows without bounding your costs. This is the opposite of the older model (Elasticsearch indexing *everything* in memory-hungry, expensive nodes), and it's why the 2026 open-source observability stack can retain far more data for far less money.

The operational payoff for *you*: one object store to provision, back up, and reason about. The lab runs all three against one MinIO; production runs all three against one S3 bucket (with separate prefixes). When you size the stack, the bucket is your dominant cost and it's predictable: bytes ingested × retention, at object-storage prices. The honest caveat is the read-path latency — fetching cold blocks/chunks from object storage is slower than reading a local SSD, which is why all three keep a hot recent tier in front of the bucket and why long-range queries (a six-month dashboard) are slower than last-hour ones. The Thanos Compactor's downsampling (§1.2) is the direct mitigation: a downsampled year scans a fraction of the bytes, so even cold long-range queries stay fast.

---

## Part 3 — The correlated pane and the costly defaults

### 5.1 Grafana: one pane, three datasources, two links

Grafana ties it together. Three datasources — Prometheus/Thanos (metrics), Tempo (traces), Loki (logs) — and two **data links** that turn them into one surface:

- **Exemplars → trace** (§2.3): the latency panel renders exemplar dots; clicking one opens the trace in Tempo.
- **Trace → logs**: configured on the Tempo datasource, a span shows a "Logs for this span" link that runs a LogQL query in Loki filtered by the trace ID (and time range). This is the **trace-to-log jump**.

### 5.1.5 The service graph: seeing the topology you actually have

One more panel the stack hands you for free, and it's worth its own moment. Both the mesh (Kiali, Week 8) and Tempo's metrics-generator can build a **service-dependency graph** from real traffic — a node per service, an edge per call path, each edge labeled with its rate, error %, and latency. This is not the architecture diagram someone drew in a wiki two years ago; it's the topology your system *actually* has *right now*, derived from the traces flowing through it. Two things make it valuable:

- **It catches drift.** The graph shows the call you forgot you added, the service still talking to a dependency you thought you'd decommissioned, the surprise edge from a misconfigured client. "Wait, why is `search` calling `payment`?" is a question only the real graph asks.
- **It scopes the blast radius.** During an incident, the graph shows what's *downstream* of the failing service (who it will take down) and *upstream* (who's already failing because of it). That's the dependency reasoning Week 18's cascading-failure work depends on, made visual.

The graph is corroboration, not gospel (it's sampled-trace-derived, same caveat as the metrics-generator), but as a live picture of "what calls what, and how healthily," it's one of the highest-value-per-effort artifacts the stack produces — you get it just by having traces flow.

### 5.2 The trace-to-log jump, end to end

The week's signature move, as one debugging session:

1. **Metric.** RED dashboard shows `cart` p99 spiked at 14:32.
2. **Exemplar.** Hover the spike; an exemplar dot carries `trace_id=4bf92...`. Click it.
3. **Trace.** Tempo opens the trace: `cart` → `inventory` → (Kafka) → `order-consumer`. You see `inventory` took 1.8 s of the 1.9 s — the slow span is named.
4. **Logs.** Click "Logs for this span" on the `inventory` span; Loki runs `{service="inventory"} | json | trace_id="4bf92..."` and shows `connection pool exhausted` at 14:32:07.

Spike → trace → log, three clicks, no guessing. That is correlated observability, and it's the difference between a 4-minute diagnosis and a 40-minute one. The thread that makes every step work is the **single trace ID** flowing through all three signals — which is exactly what Lecture 1's propagation (and especially the Kafka-boundary fix) guarantees. Break propagation and step 3's trace ends at `cart`; you never reach the `inventory` span, and the jump dies at the most important hop.

### 6. The three costly defaults

Each of these is a place where the easy default is the expensive mistake. Naming them is what separates installing observability from operating it.

#### 6.1 Sampling: head vs tail

You cannot keep 100% of traces at scale — the storage and the export bandwidth bankrupt you. So you sample. The two strategies:

- **Head sampling** decides at the *start* of a trace, before you know anything about it (e.g. "keep 10%"). It's cheap and stateless, and it's what the SDK samplers in Lecture 1 do (`TraceIDRatioBased(0.1)`). The fatal flaw: it's blind. It keeps 10% *uniformly*, which means it drops 90% of your **error** traces and 90% of your **slow** traces — exactly the ones you'd want.
- **Tail sampling** decides *after* the trace completes, when you can see its outcome. The policy that 2026 production runs: **keep 100% of error traces, 100% of slow traces, and sample the boring fast 200-OK path at 1%.** You keep every interesting trace and throw away the firehose of healthy ones. It must run in the **gateway Collector** (Lecture 1 §5), because the decision needs the *whole* trace, which only lands together at the gateway.

```yaml
# Collector tail_sampling: keep errors + slow traces, sample the rest at 1%.
processors:
  tail_sampling:
    decision_wait: 10s          # wait for the trace to (probably) complete
    policies:
      - name: keep-errors
        type: status_code
        status_code: { status_codes: [ERROR] }
      - name: keep-slow
        type: latency
        latency: { threshold_ms: 500 }
      - name: sample-the-rest
        type: probabilistic
        probabilistic: { sampling_percentage: 1 }
```

The trap with head sampling and exemplars: if you head-sample at 10% and a request is *dropped*, its exemplar still points to a trace that was never stored — click it and Tempo 404s. Tail sampling that *keeps all errors/slow traces* fixes this for the cases you care about, because the interesting requests (the ones whose exemplars you'll actually click) are the ones tail sampling keeps.

#### 6.2 Histogram buckets: choose them for your SLO

`histogram_quantile` interpolates within buckets (§1.3), so your latency quantiles are only as truthful as your bucket boundaries near the quantile. The default buckets that ship with most libraries (`0.005, 0.01, ..., 10`) are generic and usually *wrong for your service*: if your SLO is "p99 < 250 ms" but your buckets jump from 100 ms straight to 1 s, every p99 between those lands in one bucket and `histogram_quantile` can only guess — your "p99 = 400 ms" might really be 150 ms or 900 ms. The discipline: **place bucket boundaries densely around your SLO threshold and your typical latency.** If you promise p99 < 250 ms, you want boundaries at 100, 150, 200, 250, 300, 500 ms — fine resolution right where the decision is made. Coarse buckets give you a number that *looks* precise and isn't, which is worse than no number, because you'll trust it.

(Prometheus **native histograms** — the newer, automatically-bucketed exponential histograms — largely solve this by adapting resolution; if your Prometheus and SDK support them, prefer them. But you must still understand classic buckets, because most existing dashboards and the mesh's metrics use them.)

#### 6.3 Cardinality: the label that becomes an outage

A Prometheus time series is one unique combination of metric name + label values. **Cardinality** is the total count of those series, and it is the thing that kills Prometheus. The killer is a **high-cardinality label**: put `user_id` on a metric and you get one series *per user* — millions of series, gigabytes of memory, a Prometheus that OOMs. Same for `request_id`, `trace_id`, `email`, raw URLs with IDs in the path, or any unbounded value.

The rule: **labels must be bounded and low-cardinality** — `service`, `method`, `status_code`, `route` (the *template* `/cart/{id}`, never the *filled* `/cart/12345`). Anything per-request or per-user belongs in a **trace** (which is per-request by design) or as a **log filter**, never as a metric label. The cardinality budget is a real number you should know for your stack: series count × bytes-per-series is your Prometheus memory, and one careless label can 1000× it overnight. The homework has you compute exactly this budget for the cart topology, because "the dashboard label that took down monitoring" is one of the most common self-inflicted observability outages there is — and it's entirely preventable by knowing which labels you may add.

#### 6.4 A note on what this all feeds: next week's SLOs

Everything in this lecture is, ultimately, raw material for *reliability* (Week 18). The error-ratio query you write for a dashboard is one rename away from an **SLI**:

```promql
# This dashboard panel ...
sum(rate(http_server_requests_total{service="cart",code=~"5.."}[5m]))
/ sum(rate(http_server_requests_total{service="cart"}[5m]))

# ... is, inverted, exactly next week's availability SLI:
sum(rate(http_server_requests_total{service="cart",code!~"5.."}[5m]))
/ sum(rate(http_server_requests_total{service="cart"}[5m]))
```

So the choices you make *here* — SLO-aligned histogram buckets (so the latency SLI is honest), bounded cardinality (so the SLI queries are cheap and reliable), recording rules (so the burn-rate alerts are affordable) — are not just "good observability hygiene." They are *preconditions* for the SLO math to even work. A latency SLI at a 250 ms threshold needs an `le="0.25"` bucket; an error-budget burn-rate alert needs the per-window error ratios as recording rules; a high-cardinality metric makes the SLI query slow and flaky exactly when you need it during an incident. Build the observability layer with next week in mind, and the SLOs fall out almost for free. Build it carelessly, and you'll be re-instrumenting before you can define a single SLO.

> **The unifying lesson across all three defaults:** observability has a *cost*, and the cost is paid in the easy defaults — sample everything (bandwidth), generic buckets (false quantiles), unbounded labels (cardinality explosion). Operating observability means making each of these a deliberate, bounded choice tied to what you actually need to see. That cost-awareness is the same discipline as the sidecar-tax measurement in Week 8 and the capacity planning in Week 23: the senior move is always to put a number on the cost, not to wave it away.

---

## 7. Recap

You should now be able to:

- Stand up Prometheus (pull, local, short) plus Thanos (Sidecar/Store/Query/Compactor) for global, deduplicated, long-term metrics on object storage, and say what each Thanos component is *for*.
- Write PromQL for RED — `rate()` for throughput, an error-ratio for the SLI shape, `histogram_quantile(... by (le))` for latency — and reason precisely about `rate` vs `irate` and why the quantile is a bucket-bound estimate.
- Run Tempo (index-by-trace-ID, object-store-backed, metrics-generator) and Loki (index-by-label, LogQL, low-cardinality labels) and explain the shared "index light, store cheap" design.
- Build the Grafana correlated pane and perform the trace-to-log jump (metric exemplar → Tempo trace → Loki logs) on one trace ID.
- Make the three costly defaults deliberately: tail sampling (keep errors/slow, sample the rest) in the gateway, SLO-aligned histogram buckets, and a bounded cardinality budget.

Next: the exercises put all of this on your cart topology — the Collector pipeline, a real Thanos deployment with PromQL, and the trace that survives Kafka. Continue to [the exercises](../03-exercises/00-overview.md).

---

## References

- *Prometheus — Histograms and summaries*: <https://prometheus.io/docs/practices/histograms/>
- *Prometheus — `histogram_quantile`*: <https://prometheus.io/docs/prometheus/latest/querying/functions/#histogram_quantile>
- *Thanos — Components*: <https://thanos.io/tip/thanos/getting-started.md/>
- *Tempo — Architecture*: <https://grafana.com/docs/tempo/latest/operations/architecture/>
- *Tempo — TraceQL*: <https://grafana.com/docs/tempo/latest/traceql/>
- *Loki — Labels*: <https://grafana.com/docs/loki/latest/get-started/labels/>
- *Grafana — Exemplars*: <https://grafana.com/docs/grafana/latest/fundamentals/exemplars/>
- *OpenTelemetry — Sampling*: <https://opentelemetry.io/docs/concepts/sampling/>
