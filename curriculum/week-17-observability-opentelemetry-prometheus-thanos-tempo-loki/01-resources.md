# Week 17 — Resources

Every resource here is **free** and **open**. OpenTelemetry, Prometheus, and Thanos are CNCF graduated/incubating projects; Tempo, Loki, and Grafana are open-source (AGPL/Apache) with openly published docs. No paywalled books are linked.

These tools version their docs and APIs per release. This week targets **OpenTelemetry SDKs at the 1.x stable line**, **Prometheus 2.5x+** (native histograms and exemplar storage are stable), **Thanos 0.3x+**, **Tempo 2.x**, **Loki 3.x**, and **Grafana 11.x**. When a link is to `latest`, pin it to your installed version if a config field differs; the *concepts* are stable, only occasional field names move.

## Required reading (work it into your week)

- **OpenTelemetry — Concepts: Signals** — traces, metrics, logs, baggage, the data model. Read it Monday:
  <https://opentelemetry.io/docs/concepts/signals/>
- **OpenTelemetry — Context propagation** — the W3C `traceparent`/`tracestate` model and how it crosses process boundaries:
  <https://opentelemetry.io/docs/concepts/context-propagation/>
- **OpenTelemetry Collector — Configuration** — receivers, processors, exporters, pipelines:
  <https://opentelemetry.io/docs/collector/configuration/>
- **Prometheus — Histograms and summaries** — why bucket choice determines whether `histogram_quantile` is honest:
  <https://prometheus.io/docs/practices/histograms/>
- **Thanos — Overview / Components** — Sidecar, Store, Query, Compactor, Ruler, and why each exists:
  <https://thanos.io/tip/thanos/getting-started.md/>

## OpenTelemetry — the SDKs and conventions

- **OTel — Semantic conventions** — the standard attribute names (`http.request.method`, `messaging.system`, `service.name`) that make data portable:
  <https://opentelemetry.io/docs/specs/semconv/>
- **OTel Go SDK** — instrumentation for Go services (the cart BFF, inventory):
  <https://opentelemetry.io/docs/languages/go/>
- **OTel Python SDK** — the order/search services:
  <https://opentelemetry.io/docs/languages/python/>
- **OTel Rust SDK** — the cart service:
  <https://opentelemetry.io/docs/languages/rust/>
- **OTel — Sampling** — head vs tail sampling, the parent-based samplers:
  <https://opentelemetry.io/docs/concepts/sampling/>

## Prometheus and PromQL (have these open Wednesday)

- **Prometheus — Querying basics (PromQL)** — selectors, `rate`, `irate`, aggregation:
  <https://prometheus.io/docs/prometheus/latest/querying/basics/>
- **Prometheus — `histogram_quantile`** — computing quantiles from histogram buckets:
  <https://prometheus.io/docs/prometheus/latest/querying/functions/#histogram_quantile>
- **Prometheus — Exemplars** — attaching a trace ID to a sample, the metric-to-trace link:
  <https://prometheus.io/docs/prometheus/latest/feature_flags/#exemplars-storage>
- **Prometheus — Naming and labels** — the cardinality discipline that keeps Prometheus alive:
  <https://prometheus.io/docs/practices/naming/>

## Thanos (the long-term, global, HA tier)

- **Thanos — Sidecar** — uploads TSDB blocks to object storage, serves recent data over StoreAPI:
  <https://thanos.io/tip/components/sidecar.md/>
- **Thanos — Store Gateway** — serves historical blocks straight from object storage:
  <https://thanos.io/tip/components/store.md/>
- **Thanos — Query** — deduplicates HA replicas and fans out across StoreAPIs:
  <https://thanos.io/tip/components/query.md/>
- **Thanos — Compactor** — compaction and downsampling for fast long-range queries:
  <https://thanos.io/tip/components/compact.md/>

## Tempo (traces on cheap storage)

- **Tempo — Architecture** — distributor, ingester, the object-store backend, index-by-trace-ID-only:
  <https://grafana.com/docs/tempo/latest/operations/architecture/>
- **Tempo — TraceQL** — querying traces by attributes, duration, status:
  <https://grafana.com/docs/tempo/latest/traceql/>
- **Tempo — Metrics-generator** — deriving RED metrics and service graphs from spans:
  <https://grafana.com/docs/tempo/latest/metrics-generator/>

## Loki (logs, indexed by label)

- **Loki — Fundamentals / labels** — index the labels, not the lines; the low-cardinality label discipline:
  <https://grafana.com/docs/loki/latest/get-started/labels/>
- **Loki — LogQL** — the query language, log-stream selectors plus pipeline filters:
  <https://grafana.com/docs/loki/latest/query/>

## Grafana — the single pane and the correlation links

- **Grafana — Exemplars** — rendering exemplars on a graph and linking them to a trace:
  <https://grafana.com/docs/grafana/latest/fundamentals/exemplars/>
- **Grafana — Trace to logs** — the data-link that jumps from a span to its logs in Loki:
  <https://grafana.com/docs/grafana/latest/datasources/tempo/configure-tempo-data-source/#trace-to-logs>
- **Grafana — The RED method (and USE)** — the dashboard shape this week builds:
  <https://grafana.com/blog/2018/08/02/the-red-method-how-to-instrument-your-services/>

## Talks and essays worth your time (free, no signup)

- **"Monitoring and Observability" — the three pillars and their limits** — search the CNCF channel for the OpenTelemetry deep-dives posted each cycle:
  <https://www.youtube.com/c/cloudnativefdn>
- **Google SRE Book — Ch. 6, "Monitoring Distributed Systems"** — the four golden signals, free online:
  <https://sre.google/sre-book/monitoring-distributed-systems/>
- **Charity Majors / Honeycomb on high-cardinality observability** — why pre-aggregated metrics aren't enough; the case for wide events (read critically against the cost):
  <https://www.honeycomb.io/blog>

## Tools you'll use this week

- **OpenTelemetry Collector** (`otelcol-contrib`) — the vendor-neutral receive/process/export pipeline; the contrib distro has the `spanmetrics` and `tail_sampling` processors.
- **Prometheus** — scrapes your services and the mesh; runs with the Thanos sidecar.
- **Thanos** — `thanos sidecar`, `thanos store`, `thanos query`, `thanos compact`.
- **Tempo** — single-binary mode for the lab; object-store backend (MinIO).
- **Loki** — single-binary mode; same MinIO backend.
- **Grafana** — datasources for Prometheus/Thanos, Tempo, and Loki; the exemplar and trace-to-logs links.
- **MinIO** — S3-compatible object storage that Thanos/Tempo/Loki all write to.
- **`logcli`** — Loki's CLI for LogQL from the terminal.
- **`k6`** or **`fortio`** — drive load so the dashboards have something to show.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **Signal** | One of the three observability data types: metric, trace, or log. |
| **OpenTelemetry (OTel)** | The vendor-neutral standard + SDKs for emitting all three signals. |
| **OTel Collector** | A standalone pipeline that receives, processes, and exports telemetry — decouples apps from backends. |
| **Semantic conventions** | OTel's standard attribute names (`http.request.method`, `service.name`) so data is portable across tools. |
| **Context propagation** | Carrying the trace ID across a process boundary so spans join into one trace. |
| **`traceparent`** | The W3C header that carries the trace ID + span ID across HTTP/gRPC/Kafka. |
| **Span** | One unit of work in a trace (a function call, an RPC), with a start/end and attributes. |
| **Exemplar** | A trace ID attached to a metric sample — the metric-to-trace link. |
| **Histogram** | A metric of bucketed observations; quantiles are *estimated* from buckets, so bucket choice matters. |
| **`rate()`** | PromQL: the per-second average increase of a counter over a window — the basis of every RED query. |
| **`histogram_quantile()`** | PromQL: estimate a quantile (e.g. p99) from histogram buckets. |
| **Cardinality** | The number of distinct label-value combinations = the number of time series. A `user_id` label explodes it. |
| **Thanos Sidecar** | Sits next to Prometheus: uploads blocks to object storage + serves recent data over StoreAPI. |
| **Thanos Store Gateway** | Serves *historical* blocks straight from object storage — the long-term read path. |
| **Thanos Query** | Deduplicates HA Prometheus replicas and fans out across all StoreAPIs into one global view. |
| **Thanos Compactor** | Compacts and *downsamples* blocks so long-range queries are fast and cheap. |
| **Tempo** | Trace backend that indexes only by trace ID, keeping spans on cheap object storage. |
| **TraceQL** | Tempo's query language for finding traces by attribute/duration/status. |
| **Loki** | "Prometheus for logs": index the labels, not the lines; query with LogQL. |
| **Head sampling** | Decide to keep/drop a trace at the *start*, before you know if it's interesting. |
| **Tail sampling** | Decide *after* the trace completes — keep all errors and slow ones, sample the boring fast path. |
| **RED method** | Rate, Errors, Duration — the per-service dashboard signals this week builds. |

---

*If a link 404s, please open an issue so we can replace it.*
