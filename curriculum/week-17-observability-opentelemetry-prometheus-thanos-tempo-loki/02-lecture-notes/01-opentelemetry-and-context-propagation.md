# Lecture 1 — OpenTelemetry, the Three Signals, and Context Propagation

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can explain the three signals as views of one system; instrument a polyglot service with the OpenTelemetry SDK and route it through the OTel Collector; use semantic conventions; and — the load-bearing skill — propagate trace context across HTTP, gRPC, and the Kafka boundary so one request is one trace, end to end.

If you remember one sentence from this lecture, remember this one:

> **Observability is one instrumented system viewed three ways, joined by a trace ID — and the engineering is in making that trace ID survive every process boundary, because the moment it doesn't, your three signals become three silos and you're back to guessing.**

For sixteen weeks you built the system. This week you make it legible. The mesh already gives you the network spans (Week 8); your app gives you the business spans and the metrics. The job is to standardize *how* every service emits telemetry — one SDK, one wire format, one set of attribute names — and then to make the trace context flow unbroken from the BFF through cart, inventory, and across Kafka to the consumer. Get the standard right and every backend (Prometheus, Tempo, Loki) just works. Break the propagation and no backend can save you.

---

## 1. The three signals: one system, three views

### 1.1 What each signal is good and bad at

There is a tired phrase — "the three pillars of observability" — that does more harm than good, because it implies three independent things you assemble separately. The better mental model is **one instrumented system, three projections**, each answering a different question, each weak where another is strong:

| Signal | Answers | Strength | Weakness |
|---|---|---|---|
| **Metrics** | "Is it healthy? How much? How fast, in aggregate?" | Cheap, constant-cost, great for alerting and trends | Aggregate — can't tell you *which* request was slow or *why* |
| **Traces** | "What happened to *this one* request, across *all* services?" | Per-request, causal, shows the whole call chain | Expensive at volume; you usually sample, so any given request may not be kept |
| **Logs** | "What exactly did the code do at this line?" | Maximum detail; the actual error message, the variable value | Verbose, costly to store/index; no inherent structure across services |

The point is the *seams between them*. A metric tells you "p99 latency on `cart` jumped at 14:32." It cannot tell you why. A trace tells you "*this* request spent 1.9 s waiting on `inventory`." A log tells you "`inventory` logged `connection pool exhausted` at 14:32:07 on that request." Each alone is a partial view; the three *correlated by a shared trait ID* are a diagnosis. The naive stack collects all three and correlates none — three dashboards in three tabs, and a human eyeballing timestamps to guess which trace goes with which spike. The stack you build this week shares a **trace ID** across all three so the correlation is a click, not a guess.

### 1.2 Why correlation, not collection, is the value

Collecting telemetry is the easy 20%. Every framework emits *something*. The hard, valuable 80% is making the signals *join*:

- A **metric** spike must carry an **exemplar** — a sample trace ID — so you can jump from the spike to a representative trace. (Prometheus exemplars, Lecture 2 §2.3.)
- A **trace** must let you jump to the **logs** for its spans — found in Loki by that same trace ID. (The trace-to-log jump, Lecture 2 §5.2.)
- All of it must use the **same trace ID format** (W3C `traceparent`, a 16-byte/32-hex trace ID), or the join silently fails.

This is why the week's signature deliverable is the **trace-to-log jump**: prove that one trace ID appears on a metric exemplar, resolves to a trace in Tempo, and filters the logs in Loki. If it does, you have observability. If the three signals carry three different IDs (or no shared ID), you have three expensive silos and a false sense of security — the observability equivalent of Week 8's "we have a mesh, so we have mTLS."

---

## 2. OpenTelemetry: the standard that ends the vendor war

### 2.1 The API/SDK split and why it matters

Before OpenTelemetry, instrumentation meant choosing a vendor's agent and coupling your code to it: switch backends, re-instrument everything. **OpenTelemetry (OTel)** is the CNCF standard — an API, a set of SDKs, and a wire protocol (**OTLP**) — that decouples *emitting* telemetry from *where it goes*.

The design that makes this work is the **API/SDK split**:

- The **API** is what your application code calls: `tracer.Start(ctx, "ChargeCard")`, `counter.Add(ctx, 1)`. It's a thin, stable surface with a no-op default — a library can instrument against the API and, if no SDK is installed, cost nothing.
- The **SDK** is the implementation you configure at startup: sampling, batching, which exporter, what resource attributes. Your *libraries* depend only on the API; your *application* wires up the SDK once at `main()`. Swap the SDK config and the same instrumented code exports to a different backend.

The practical payoff: you instrument once, against semantic conventions, and your data is portable. Move from a SaaS backend to the self-hosted Tempo/Prometheus/Loki stack you build this week, and not one line of instrumentation changes — only the exporter endpoint.

### 2.2 The OTel Collector: the pipeline that decouples apps from backends

You *can* have each service export OTLP straight to Tempo/Prometheus. You shouldn't, beyond a toy. The production pattern is the **OpenTelemetry Collector** — a standalone process (a DaemonSet per node and/or a Deployment) that sits between your apps and the backends. It has three stages:

- **Receivers** — accept telemetry in (OTLP from your SDKs, Prometheus scrape, Kafka, host metrics).
- **Processors** — transform it in flight (batching, memory limiting, attribute editing, **tail sampling**, redaction of PII).
- **Exporters** — send it out (to Tempo, to Prometheus via remote-write or a scrape endpoint, to Loki).

```yaml
# otel-collector-config.yaml — receivers -> processors -> exporters, wired into pipelines.
receivers:
  otlp:
    protocols:
      grpc: { endpoint: 0.0.0.0:4317 }   # your SDKs push OTLP/gRPC here
      http: { endpoint: 0.0.0.0:4318 }

processors:
  batch:                                  # batch before export — fewer, bigger requests
    timeout: 5s
    send_batch_size: 1024
  memory_limiter:                         # shed load before you OOM the collector
    check_interval: 1s
    limit_percentage: 80
    spike_limit_percentage: 25
  resource:                               # ensure service.name etc. are present
    attributes:
      - { key: deployment.environment, value: staging, action: upsert }

exporters:
  otlp/tempo:                             # traces -> Tempo
    endpoint: tempo:4317
    tls: { insecure: true }
  prometheus:                             # metrics -> a /metrics endpoint Prometheus scrapes
    endpoint: 0.0.0.0:8889
    enable_open_metrics: true             # OpenMetrics carries exemplars (the metric->trace link)
  otlphttp/loki:                          # logs -> Loki via OTLP/HTTP
    endpoint: http://loki:3100/otlp

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp/tempo]
    metrics:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [prometheus]
    logs:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlphttp/loki]
```

Why the Collector earns its keep: it **decouples** the app from the backend (apps speak OTLP and nothing else; swap Tempo for another trace backend by editing one exporter), it **centralizes** cross-cutting concerns (PII redaction, sampling, batching) so each team doesn't reimplement them, and it **absorbs** backend outages (the Collector can buffer/retry while Tempo restarts, instead of every app handling it). The `memory_limiter` processor is non-negotiable: a Collector with no memory limit is a Collector that OOMs under a telemetry spike and takes your visibility down exactly when you need it most.

### 2.3 Semantic conventions: the standard attribute names

A trace attribute named `http.request.method` means the same thing everywhere; one named `method` or `httpMethod` or `verb` means whatever each team decided. **Semantic conventions** are OTel's standardized attribute names — `http.request.method`, `http.response.status_code`, `service.name`, `messaging.system`, `db.system`, `rpc.grpc.status_code` — and they are *load-bearing* for correlation. Dashboards, alerts, and the trace-to-metrics links assume them. The discipline: when an attribute has a semantic-convention name, *use it*; invent names only for genuinely app-specific attributes (and namespace those, e.g. `cart.item_count`).

The single most important one is **`service.name`** — it's the resource attribute that says which service a span/metric/log came from, and it's the key everything else groups by. Get it wrong (or leave it as `unknown_service`) and your whole stack can't tell your services apart.

---

## 3. Instrumenting a polyglot service

The cart topology is Go (BFF, inventory), Python (order, search), and Rust (cart). OTel has a stable SDK for each, and the *shape* is identical across languages even though the syntax differs: configure a tracer provider and a meter provider at startup, wrap inbound/outbound calls so spans nest, and let the SDK batch-export over OTLP.

### 3.1 Go — the inventory service

```go
// main.go — set up the tracer + meter providers once, at startup.
package main

import (
	"context"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.26.0"
)

func initTracing(ctx context.Context) (*sdktrace.TracerProvider, error) {
	exp, err := otlptracegrpc.New(ctx,
		otlptracegrpc.WithEndpoint("otel-collector:4317"),
		otlptracegrpc.WithInsecure(),
	)
	if err != nil {
		return nil, err
	}
	res, _ := resource.New(ctx,
		resource.WithAttributes(semconv.ServiceName("inventory")), // the load-bearing service.name
	)
	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exp),                       // batch spans before export
		sdktrace.WithResource(res),
		sdktrace.WithSampler(sdktrace.ParentBased(sdktrace.TraceIDRatioBased(0.1))), // head-sample 10%
	)
	otel.SetTracerProvider(tp)
	// CRUCIAL: install the W3C propagator so traceparent is injected/extracted.
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{}, propagation.Baggage{}))
	return tp, nil
}
```

The instrumentation itself is mostly *automatic* if you use the OTel contrib middleware: `otelgrpc` for gRPC servers/clients, `otelhttp` for HTTP. Those wrap the transport, start a span per request, and — this is the part that matters — **inject and extract `traceparent`** so the span chain crosses the wire. You add manual spans only around business logic the auto-instrumentation can't see (`tracer.Start(ctx, "reserveStock")`).

### 3.2 Python — the order service

```python
# tracing.py — configure the SDK once; auto-instrument gRPC/HTTP/Kafka clients.
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import set_global_textmap
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

def init_tracing():
    resource = Resource.create({"service.name": "order"})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint="otel-collector:4317", insecure=True))
    )
    trace.set_tracer_provider(provider)
    set_global_textmap(TraceContextTextMapPropagator())  # W3C traceparent

tracer = trace.get_tracer(__name__)

def place_order(cart_id: str):
    with tracer.start_as_current_span("place_order") as span:
        span.set_attribute("cart.id", cart_id)   # app-specific attr, namespaced
        # ... call inventory (auto-instrumented gRPC), then publish to Kafka ...
```

### 3.3 Rust — the cart service

```rust
// tracing.rs — set up the OTLP pipeline; the W3C propagator is wired by default in the SDK.
use opentelemetry::global;
use opentelemetry::trace::TracerProvider as _;
use opentelemetry_otlp::WithExportConfig;
use opentelemetry_sdk::{trace as sdktrace, Resource};
use opentelemetry::KeyValue;

pub fn init_tracing() -> sdktrace::TracerProvider {
    let exporter = opentelemetry_otlp::SpanExporter::builder()
        .with_tonic()
        .with_endpoint("http://otel-collector:4317")
        .build()
        .expect("otlp exporter");

    let provider = sdktrace::TracerProvider::builder()
        .with_batch_exporter(exporter, opentelemetry_sdk::runtime::Tokio)
        .with_resource(Resource::new(vec![KeyValue::new("service.name", "cart")]))
        .build();

    // Install the W3C TraceContext propagator so traceparent crosses boundaries.
    global::set_text_map_propagator(opentelemetry_sdk::propagation::TraceContextPropagator::new());
    global::set_tracer_provider(provider.clone());
    provider
}
```

Three languages, one shape: a provider with an OTLP exporter, a `service.name` resource, a batch processor, and — the line that makes traces span services — **the W3C TraceContext propagator installed globally.** Forget that last line and every service traces *itself* perfectly while the traces never join. That is the single most common instrumentation bug, and it's the subject of §4.

---

## 4. Context propagation: making one request one trace

### 4.1 The model: `traceparent` rides the request

A distributed trace is a tree of spans across services. For the spans in service B to attach under the span in service A — instead of starting a brand-new orphan trace — service A must **inject** its current trace context into the outbound request, and service B must **extract** it from the inbound request. The carrier is the **W3C `traceparent` header**:

```
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             ^^ ^------------------------------^ ^--------------^ ^^
             |  trace-id (16 bytes / 32 hex)     parent span-id   flags (01 = sampled)
             version
```

The propagator (the `TraceContext{}` / `TraceContextTextMapPropagator` you installed) does this automatically *for transports the SDK instruments*. The auto-instrumentation for HTTP and gRPC injects `traceparent` on the way out and extracts it on the way in. So for HTTP and gRPC, propagation is mostly free — *if* you (a) installed the propagator and (b) passed the *context* through your code (in Go, the `ctx`; in Python, the implicit current span; in Rust, the `Context`). The classic in-process break is starting an outbound call with a fresh `context.Background()` instead of the inbound request's `ctx` — the trace context is in the ctx you threw away, so the child span orphans.

### 4.2 HTTP and gRPC: where the SDK does the work

```go
// Go: the client auto-injects traceparent IF you pass the inbound ctx through.
// GOOD — the inbound request's ctx carries the trace context outward:
resp, err := otelhttp.Get(ctx, "http://inventory:8080/stock/"+sku)

// BAD — context.Background() drops the trace; inventory starts a NEW trace, orphaned.
resp, err := otelhttp.Get(context.Background(), "http://inventory:8080/stock/"+sku)
```

```go
// gRPC: install the otelgrpc handler on BOTH the server and the client.
import "go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"

// server: extracts traceparent from inbound metadata, makes the server span a child.
grpc.NewServer(grpc.StatsHandler(otelgrpc.NewServerHandler()))

// client: injects traceparent into outbound metadata.
grpc.NewClient(target, grpc.WithStatsHandler(otelgrpc.NewClientHandler()))
```

For gRPC, `traceparent` rides in the gRPC **metadata** (HTTP/2 headers under the hood, exactly the substrate from Week 5). The `otelgrpc` handlers inject on the client and extract on the server. Install them on *both* ends — a server handler with no client handler means the client never injects, so the server has nothing to extract and starts a fresh trace.

### 4.3 The Kafka boundary: where it breaks silently

Here is the boundary that catches everyone, and the reason this lecture exists. HTTP and gRPC are *synchronous* request/response on one connection — the SDK auto-instrumentation owns the wire, so it injects and extracts for you. **Kafka is asynchronous and decoupled**: the producer writes a message and moves on; the consumer reads it later, in a *different process*, possibly minutes later. There is no request/response, no shared connection for the propagator to hook. So unless you do it explicitly, the consumer has no idea which trace the message belongs to, and the trace **splits in two**: a producer-side trace that ends at "published," and an unrelated consumer-side trace that starts at "consumed," with no link between them.

The fix is to carry `traceparent` in the **Kafka message headers** (Kafka records support headers — key/value byte pairs — exactly for this). On produce, inject the current context into the headers; on consume, extract it and start the consumer span as a child:

```python
# PRODUCER: inject traceparent into the Kafka message headers.
from opentelemetry.propagate import inject

def publish_order(producer, order):
    with tracer.start_as_current_span("publish order.placed.v1") as span:
        span.set_attribute("messaging.system", "kafka")          # semantic convention
        span.set_attribute("messaging.destination.name", "order.placed.v1")
        headers = []
        inject(setter=_KafkaHeaderSetter(), carrier=headers)     # writes traceparent into headers
        producer.send("order.placed.v1", value=order, headers=headers)
```

```python
# CONSUMER (a DIFFERENT process): extract traceparent and make the span a child.
from opentelemetry.propagate import extract
from opentelemetry.trace import set_span_in_context

def handle_message(msg):
    ctx = extract(carrier=msg.headers, getter=_KafkaHeaderGetter())  # read traceparent back
    with tracer.start_as_current_span("process order.placed.v1", context=ctx) as span:
        span.set_attribute("messaging.system", "kafka")
        # ... this span is now a CHILD of the producer's span: ONE trace across Kafka ...
```

The `inject`/`extract` pair, plus a small setter/getter that read and write the byte-pair headers, is the whole fix — a dozen lines. But it is *manual*, because the SDK can't auto-instrument a boundary with no synchronous wire to hook. This is the single most valuable propagation skill of the week: **the trace that stops at Kafka is not a Kafka bug or a Tempo bug; it's a missing `inject` on produce or a missing `extract` on consume.** The challenge has you diagnose exactly this from the outside, and Exercise 3 has you build it and prove one trace survives the boundary.

> **Why this matters for the capstone.** Your `order.placed.v1` event is the spine of the marketplace: an order flows BFF → cart → inventory → Kafka → the order/search/analytics consumers. If context doesn't cross Kafka, your end-to-end trace of "what happened to this order" shatters at the most important hop — the async fan-out where the hard bugs live. Propagating across Kafka is what makes "trace this order through the whole system" possible.

### 4.4 Baggage: propagating business context (use sparingly)

`traceparent` carries the trace identity. **Baggage** (the `tracestate`/`baggage` headers) lets you propagate *application* key-values along the same path — e.g. a `tenant.id` or `cart.id` that every downstream service can read and attach to *its* spans without re-fetching. It's powerful and a foot-gun: baggage is propagated on *every* hop, so a fat baggage payload taxes every request, and anything in baggage is visible to every downstream service (don't put secrets in it). Use it for a small number of high-value cross-cutting keys, not as a general data bus.

---

## 5. The Collector deployment patterns (agent vs gateway)

Two deployment shapes, usually combined:

- **Agent (DaemonSet):** a Collector per node that local apps push to over the loopback/node-local network. Cheap, low-latency, and it can enrich with node/pod metadata. This is the first hop.
- **Gateway (Deployment):** a horizontally-scaled pool the agents forward to, where you do the expensive, *stateful* processing — most importantly **tail sampling**, which needs to see *all* spans of a trace to decide whether to keep it, so it must run where a whole trace lands (not sharded across per-node agents).

The reason tail sampling lives in the gateway and not the agent is worth holding onto: a tail-sampling decision ("keep this trace because it has an error or is slow") requires the *complete* trace, and a trace's spans come from many pods on many nodes. A per-node agent only sees its node's spans, so it *can't* make a whole-trace decision. The gateway, with consistent routing so all spans of a trace land on the same gateway instance, can. We return to sampling as one of the "costly defaults" in Lecture 2 §6.

---

## 6. Recap

You should now be able to:

- Describe the three signals as projections of one instrumented system and explain why correlation (a shared trace ID) — not collection — is the value.
- Explain the OTel API/SDK split, the role of the Collector (receivers → processors → exporters), and why semantic conventions (especially `service.name`) make telemetry portable.
- Stand up the tracer/meter providers in Go, Python, and Rust with an OTLP exporter, a batch processor, and — the load-bearing line — the W3C TraceContext propagator installed.
- Propagate `traceparent` across HTTP and gRPC (auto, if you pass the context) and across Kafka (manual, via message headers and `inject`/`extract`), and explain *why* Kafka is the boundary that breaks silently.
- Use baggage for a small set of cross-cutting business keys, knowing its per-hop cost.
- Place tail sampling in a gateway Collector because the decision needs the whole trace, which a per-node agent never sees.

Next: the backends. Where all this telemetry *lands* — Prometheus + Thanos for metrics, Tempo for traces, Loki for logs — the PromQL that turns metrics into RED signals, and the exemplar + trace-to-log jump that makes the three signals one debugging surface. Continue to [Lecture 2 — Prometheus, Thanos, Tempo, Loki, and the Correlated Pane](./02-prometheus-thanos-tempo-loki-and-the-correlated-pane.md).

---

## References

- *OpenTelemetry — Signals*: <https://opentelemetry.io/docs/concepts/signals/>
- *OpenTelemetry — Context propagation*: <https://opentelemetry.io/docs/concepts/context-propagation/>
- *OpenTelemetry — Collector configuration*: <https://opentelemetry.io/docs/collector/configuration/>
- *OpenTelemetry — Semantic conventions*: <https://opentelemetry.io/docs/specs/semconv/>
- *W3C — Trace Context*: <https://www.w3.org/TR/trace-context/>
- *OpenTelemetry — Sampling*: <https://opentelemetry.io/docs/concepts/sampling/>
