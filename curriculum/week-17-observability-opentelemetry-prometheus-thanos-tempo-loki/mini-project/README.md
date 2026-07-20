# Mini-Project — `cart-observed`: The Three-Signal Stack on the Cart Topology

> Make the cart system observable for real: every service instrumented in OpenTelemetry through an OTel Collector; metrics in Prometheus + Thanos (global, deduplicated, long-term); traces in Tempo; logs in Loki; all joined in a Grafana RED dashboard with **exemplars** that jump to traces and a **trace-to-log** link that lands on the exact log lines — and a trace that survives the Kafka boundary so you can follow one order end to end.

This is the artifact that turns "we have dashboards" into "we can debug." After this week, observability is a *deployable posture* you can defend: one instrumentation standard, three correlated backends on one cheap object store, and the signature move — spike → trace → log in three clicks — working on your own topology. When someone asks "how fast can you find the cause of a latency spike," you answer by *doing it*, not by describing a tool you bought.

**Estimated time:** ~12 hours, split across Thursday, Friday, and Saturday in the suggested schedule.

**Compounds forward:** This `cart-observed` stack is the observability layer of your **capstone Polyglot Marketplace Backbone**, and the *direct foundation of next week*. Week 18's SLIs are PromQL queries over the very RED metrics you wire up here; its error-budget burn-rate alerts run against this Prometheus/Thanos. You cannot define an SLO without the signals to measure it — so build this cleanly, because next week's reliability math has nowhere to stand without it. Week 22's gameday reads these dashboards to *see* the chaos you inject; the capstone's demo ends with a live trace-to-log jump on this exact stack.

---

## What you will build

A repo `cart-observed` with five deliverables:

1. **`instrumentation/`** — the OpenTelemetry SDK setup for each service (Go, Python, Rust), with `service.name`, the W3C propagator, RED metrics, and **SLO-aligned histogram buckets** (not the library defaults). Documented so any new service can copy the pattern.
2. **`collector/`** — the OTel Collector config: OTLP in, `memory_limiter` + `batch` + (stretch) `tail_sampling`, three exporters out (Tempo, Prometheus, Loki). The single ingestion point for the whole topology.
3. **`backends/`** — the deployable stack: Prometheus + the full **Thanos** topology (Sidecar/Store/Query/Compactor) on MinIO, **Tempo** and **Loki** on the same bucket, and **Grafana** with all three datasources and the exemplar + trace-to-logs links configured.
4. **`dashboards/`** — a Grafana RED dashboard (rate, error ratio, p99 from histograms) **with exemplars** rendered on the latency panel, plus the datasource links that make the trace-to-log jump work. Exported as JSON so it's reproducible.
5. **`audit/verify_observability.sh`** — a script that proves correlation is real: it drives a request, captures its trace ID, and asserts that same trace ID resolves to a **trace in Tempo**, carries an **exemplar in Prometheus**, and **filters logs in Loki** — and that an `order.placed.v1` event keeps one trace **across Kafka**. Exits non-zero if any link is broken.

By the end you have a public repo of instrumentation + a deployable three-signal stack + an audit script that any future service can be onboarded into, and a dashboard where a spike is one click from its root cause.

---

## Why this and not "just install Grafana"

You could `helm install` a metrics stack and call your services "observed." Don't stop there — that's the gap this whole week is about. A defensible observability posture gives you:

- **Correlation you can prove**, not three silos. The default stack collects three signals that share no ID; this project's audit asserts *one trace ID* threads all three and *demonstrates the trace-to-log jump*. The difference is a 4-minute incident versus a 40-minute one.
- **A trace that survives async**, not one that shatters at Kafka. Following one order end-to-end — through the `order.placed.v1` spine — is the capstone's hardest tracing requirement, and it's exactly where the naive setup breaks.
- **Costs you chose, not defaults you inherited.** SLO-aligned histogram buckets (honest quantiles), a known cardinality budget (a Prometheus that won't OOM on a careless label), and a sampling strategy that keeps the *interesting* traces.
- **A global, long-term metric view**, not a single Prometheus that loses everything when its pod dies. Thanos makes the metrics durable, deduplicated, and queryable a year back.

The managed observability vendors will sell you all of this. Building it by hand on open-source first is what lets you read, trust, and right-size what they generate — the senior-shop convention in 2026, and the open-source-first bias of this whole course.

---

## Repo layout

```
cart-observed/
├── README.md
├── instrumentation/
│   ├── go/tracing.go            # provider + W3C propagator + SLO-aligned buckets (inventory, BFF)
│   ├── python/tracing.py        # same shape (order, search) + Kafka inject/extract helpers
│   └── rust/tracing.rs          # same shape (cart)
├── collector/
│   └── otel-collector.yaml      # receivers -> processors -> exporters, three pipelines
├── backends/
│   ├── minio.yaml               # the shared object store (tempo/loki/thanos buckets)
│   ├── prometheus-thanos.yaml   # Prometheus + sidecar/store/query/compactor (Exercise 2)
│   ├── tempo.yaml               # traces, MinIO backend, metrics-generator on
│   ├── loki.yaml                # logs, MinIO backend
│   └── grafana.yaml             # datasources + exemplar + trace-to-logs links
├── dashboards/
│   └── cart-red.json            # RED dashboard with exemplars, exported
└── audit/
    └── verify_observability.sh  # asserts the trace ID threads all three + survives Kafka
```

---

## Deliverable 1 — `instrumentation/` (the standard)

Each service gets the OTel SDK wired identically: an OTLP exporter to the Collector, a `service.name` resource, a batch processor, **the W3C TraceContext propagator installed**, RED metrics, and — the part that separates this from a tutorial — **histogram buckets chosen for the cart SLO**, not the library defaults. If your cart SLO is "p99 < 250 ms," your buckets cluster densely around 250 ms (100, 150, 200, 250, 300, 500 ms), so `histogram_quantile` tells the truth. Document *why* the default buckets would lie. Include the Kafka `inject`/`extract` helpers (from Exercise 3) so the async path propagates context.

> **The rule the audit enforces:** every service must set a correct `service.name` and install the propagator. A service whose `service.name` is `unknown_service`, or that doesn't propagate, breaks correlation — and the audit catches it.

---

## Deliverable 2 — `collector/` (the single front door)

The Collector config: OTLP receivers, the `memory_limiter` (non-negotiable — a Collector with no memory limit OOMs under a telemetry spike and takes your visibility down when you need it most) and `batch` processors, and three exporters with `enable_open_metrics: true` on the Prometheus exporter (so exemplars flow). Document the agent/gateway split as the production shape even if the lab runs one Collector.

---

## Deliverable 3 — `backends/` (the deployable stack)

The full stack on one MinIO bucket: Prometheus + Thanos (the Exercise 2 topology, including the *singleton* Compactor and the `replica` external label for dedup), Tempo (metrics-generator on, deriving a service graph from spans), Loki (low-cardinality labels), and Grafana with all three datasources plus the two correlation links configured. Capture the exact versions — observability behavior is version-sensitive.

---

## Deliverable 4 — `dashboards/` (the correlated pane)

A Grafana RED dashboard, exported as JSON, with:

- **Rate** (`sum(rate(...[5m]))`), **Errors** (the 5xx ratio), **Duration** (`histogram_quantile(0.99, ... by (le))`) per service.
- **Exemplars rendered on the latency panel** — clickable dots carrying trace IDs. (Requires SDK exemplars + OpenMetrics + Prometheus exemplar storage all on; if the dots don't appear, one of the three is off.)
- The **trace-to-logs** data link on the Tempo datasource, so a span jumps to its Loki logs filtered by trace ID.

Document the **trace-to-log jump** in the repo README as a numbered walkthrough: spike → exemplar → trace → log, with a screenshot at each step.

---

## Deliverable 5 — `audit/verify_observability.sh`

A script that makes correlation *verifiable*, not claimed. Against the running stack it must:

1. Drive a request through `cart` and capture the resulting **trace ID**.
2. Assert that trace ID **resolves to a trace in Tempo** (`GET /api/traces/<id>` returns spans).
3. Assert an **exemplar carrying a trace ID** is present on the latency histogram in Prometheus (`/api/v1/query?...` with exemplars).
4. Assert **logs for that trace ID exist in Loki** (a LogQL query filtered by `trace_id` returns lines).
5. Assert an **`order.placed.v1` event keeps one trace across Kafka** (produce + consume, then confirm one trace contains both spans).
6. Exit **0** when every assertion passes; exit **non-zero** naming the first broken link.

Sketch:

```bash
#!/usr/bin/env bash
set -euo pipefail
fail() { echo "OBSERVABILITY AUDIT FAIL: $1" >&2; exit 1; }
TEMPO=${TEMPO:-http://localhost:3200}
PROM=${PROM:-http://localhost:9090}
LOKI=${LOKI:-http://localhost:3100}

# 1. drive a request and grab a trace ID from the response (or from Tempo search)
TID=$(curl -s "$TEMPO/api/search?tags=service.name%3Dcart&limit=1" | jq -r '.traces[0].traceID')
[ -n "$TID" ] && [ "$TID" != "null" ] || fail "no trace found for service.name=cart"

# 2. the trace resolves in Tempo
curl -sf "$TEMPO/api/traces/$TID" | jq -e '.batches | length > 0' >/dev/null \
  || fail "trace $TID does not resolve in Tempo"

# 3. an exemplar with a trace_id is present on the latency histogram
curl -s "$PROM/api/v1/query_exemplars" \
  --data-urlencode 'query=http_server_request_duration_seconds_bucket{service="cart"}' \
  --data-urlencode "start=$(date -u -d '-5 min' +%s)" --data-urlencode "end=$(date -u +%s)" \
  | jq -e '.data[].exemplars[].labels.trace_id' >/dev/null \
  || fail "no exemplar trace_id on the cart latency histogram (check OpenMetrics + exemplar storage)"

# 4. logs for that trace ID exist in Loki
curl -sf -G "$LOKI/loki/api/v1/query_range" \
  --data-urlencode "query={service_name=\"cart\"} | json | trace_id=\"$TID\"" \
  | jq -e '.data.result | length >= 0' >/dev/null \
  || fail "Loki query for trace_id=$TID failed"

# 5. ... produce + consume an order.placed.v1 and assert ONE trace has both spans ...

echo "OBSERVABILITY AUDIT PASS: trace $TID threads Tempo + exemplar + Loki; Kafka trace intact."
```

---

## Rules

- **You may** read the OTel/Prometheus/Thanos/Tempo/Loki/Grafana docs and the lecture notes.
- **You must not** declare the stack "correlated" if the three signals don't share a trace ID. The audit enforces the trace-to-log jump; if `verify_observability.sh` passes while the trace-to-log link is broken, you've defeated the project's reason to exist.
- **You must not** ship the library-default histogram buckets and claim an honest p99. Buckets must be SLO-aligned (or native histograms), and you must show *why*.
- **You must not** add a high-cardinality metric label (`user_id`, `trace_id`, raw URL). The cardinality budget is a deliverable, not an afterthought.
- **You must not** leave the trace splitting at Kafka. One order, one trace, across the boundary.
- OpenTelemetry 1.x, Prometheus 2.5x+, Thanos/Tempo/Loki current, Grafana 11.x, Kind, MinIO. Everything runs locally.
- The audit must exit non-zero on any broken link so it can gate a deploy or CI.

---

## Acceptance criteria

- [ ] A public GitHub repo named `c22-week-17-cart-observed-<yourhandle>`.
- [ ] Every service is instrumented with a correct `service.name`, the W3C propagator, RED metrics, and SLO-aligned histogram buckets.
- [ ] The OTel Collector is the single ingestion point, with `memory_limiter` and OpenMetrics-enabled metrics export.
- [ ] Prometheus + Thanos serve a global, deduplicated metric view (the Thanos `/api/v1/stores` shows sidecar + store; 2 replicas dedup to one series).
- [ ] Tempo and Loki are backed by the same MinIO bucket; a trace and its logs share a trace ID.
- [ ] The Grafana RED dashboard renders **exemplars** on the latency panel, and the **trace-to-log jump** works (documented with screenshots).
- [ ] An `order.placed.v1` event keeps **one trace across Kafka** (the producer and consumer share a trace ID).
- [ ] `audit/verify_observability.sh` exits **0** against the correct stack and **non-zero** when you break a link (e.g., disable the Kafka propagation) — demonstrated in the README.
- [ ] A `cardinality-budget.md` listing your metric labels and the resulting series count, proving no unbounded label.
- [ ] Committed and pushed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Instrumentation correctness** | 15 | Correct `service.name`, propagator installed, RED metrics, SLO-aligned buckets with a stated rationale. |
| **The pipeline (Collector + backends)** | 20 | One Collector front door; Thanos topology correct (singleton compactor, dedup label); Tempo/Loki on shared storage. |
| **Correlation (the trace-to-log jump)** | 25 | One trace ID threads metrics (exemplar), trace (Tempo), and logs (Loki); the jump is demonstrated, not claimed. |
| **Trace continuity across Kafka** | 15 | One order is one trace producer→consumer; the audit proves it; you can explain the inject/extract. |
| **The costly defaults handled** | 15 | SLO-aligned buckets (honest p99), a bounded cardinality budget, a stated sampling strategy. |
| **Auditability & docs** | 10 | `verify_observability.sh` asserts correlation (not mere presence) and fails on a broken link; clear README; no secrets checked in. |

**90+** is portfolio-grade and ready to be the capstone's observability layer and next week's SLO foundation. **70–89** works but likely claims correlation it can't prove (three silos with no shared ID), or ships default buckets that make p99 fiction. **Below 70** usually means the signals don't correlate or the trace breaks at Kafka — fix those first; they're the two things this week exists to deliver.

---

## Stretch goals

- **Tail sampling.** Replace head sampling with the Collector's `tail_sampling` (keep 100% of errors and slow traces, sample the boring fast path at 1%) in a gateway Collector, and prove an error trace is *never* dropped while the firehose is tamed. This is the production sampling story.
- **Span metrics.** Turn on the Collector's `spanmetrics` connector (or Tempo's metrics-generator) to derive RED metrics from traces, and write a paragraph on when to trust derived-from-traces metrics versus SDK-emitted ones.
- **Burn-rate preview.** Wire one Grafana/Alertmanager alert off an error-*ratio* PromQL query — a preview of next week's error-budget burn-rate math, alerting before you've formally defined the SLO.
- **Downsampling payoff.** Let the Thanos Compactor downsample, then query a (synthetic) year of data at 1-hour resolution in milliseconds — the concrete payoff of the downsampling tier.

---

## How this connects to the rest of C22

- **Week 6** gave you baseline OTel instrumentation; this week makes it a real, correlated pipeline.
- **Week 8 (the mesh)** emits `istio_requests_total` and network spans for free; this stack ingests them alongside your app signals — the mesh's RED metrics are one of your dashboard's data sources.
- **Week 10 (Kafka)** is the async boundary this week's trace must survive; the `order.placed.v1` spine is the capstone's nervous system.
- **Week 18 (reliability)** defines SLIs/SLOs as PromQL over *these* metrics and runs error-budget burn-rate alerts against *this* Prometheus/Thanos — next week literally cannot run without this week's stack.
- **Phase 4 (capstone)** deploys `cart-observed` as the observability layer, and the demo's finale is a live trace-to-log jump on it.

When you've finished, push the repo and take the [quiz](../quiz.md).
