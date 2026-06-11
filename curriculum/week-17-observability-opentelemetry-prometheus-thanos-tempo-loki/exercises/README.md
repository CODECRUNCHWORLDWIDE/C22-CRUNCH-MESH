# Week 17 — Exercises

Three focused drills on a running observability stack. Each takes 45–90 minutes. Do them in order — exercise 1 (the Collector pipeline) routes the telemetry that exercise 2 (Thanos + PromQL) queries, and exercise 3 (the Kafka boundary) produces the cross-service trace whose continuity the whole stack depends on. Run everything against your **cart topology** from Phase 1–3, deployed on Kind, ideally still meshed from Week 8.

## Index

1. **[Exercise 1 — The OTel Collector and the pipeline](exercise-01-otel-collector-and-the-pipeline.md)** — stand up the OpenTelemetry Collector, point your services' OTLP at it, and route traces → Tempo, metrics → Prometheus, logs → Loki, all over one MinIO bucket. Prove a span arrives in Tempo end to end. (~75 min, guided)
2. **[Exercise 2 — Thanos and the RED PromQL](exercise-02-thanos-and-promql.yaml)** — a complete Prometheus + Thanos deployment (Sidecar/Store/Query/Compactor) plus the PromQL RED queries (rate, error ratio, p99 from histograms) to run against the global Thanos Query view. (~60 min, runnable)
3. **[Exercise 3 — Trace context across Kafka](exercise-03-trace-context-across-kafka.py)** — inject `traceparent` into Kafka message headers on produce and extract it on consume, then prove one trace survives the producer→consumer boundary in Tempo. (~60 min, runnable)

## How to work the exercises

- Have a **Kind** cluster with headroom (the full stack — Collector, Prometheus, Thanos, Tempo, Loki, Grafana, MinIO — wants ~6 GB free; run components as single-binary/single-replica for the lab).
- Have your **cart topology** deployable, with at least one **Kafka/Redpanda** producer/consumer pair from Week 10 (`order.placed.v1` is the canonical one for exercise 3).
- **Check the data, not the config, at every step.** A pipeline that's "configured" but drops telemetry silently is the default failure. After every change, *query the backend* — `tempo` for a trace, `prometheus`/`thanos query` for a series, `logcli` for a log line — and confirm the data actually landed. The mesh-week habit ("the proxy's config is ground truth, not the CRD") becomes here: *the backend's data is ground truth, not the exporter you configured.*
- When telemetry "isn't showing up," check in this order: (1) is the app *exporting* (Collector logs show receives)? (2) is the Collector *exporting* (its own metrics show sends, no `memory_limiter` drops)? (3) is the backend *ingesting* (its logs/metrics)? Most "missing data" is a wrong endpoint or a dropped batch, not a backend bug.
- Each runnable exercise ends with an **expected output** block. If your output doesn't match, you're not done.

## Running the exercises

The `.yaml` exercise is applied with `kubectl`:

```bash
kubectl apply -f exercise-02-thanos-and-promql.yaml
# then port-forward Thanos Query and run the PromQL at the bottom of the file:
kubectl port-forward svc/thanos-query 9090:9090
```

The `.py` exercise is a standard Python script that produces and consumes across Kafka with context propagation:

```bash
pip install confluent-kafka opentelemetry-sdk opentelemetry-exporter-otlp
python3 exercise-03-trace-context-across-kafka.py --produce      # one terminal
python3 exercise-03-trace-context-across-kafka.py --consume      # another terminal
```

The header of each file lists the exact prerequisites. If your Phase 1 services aren't instrumented yet, each file points you at the minimal stand-in.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c22-week-17` to compare.
