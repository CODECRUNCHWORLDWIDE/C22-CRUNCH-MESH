# Exercise 1 — The OTel Collector and the Pipeline

**Goal:** Stand up the OpenTelemetry Collector as the single ingestion point for your cart topology, route the three signals to their backends (traces → Tempo, metrics → Prometheus, logs → Loki) over one MinIO bucket, and *prove* — by querying the backends, not by reading config — that a request through `cart` produces a trace in Tempo, a metric in Prometheus, and a log line in Loki that all carry the **same trace ID**. You will train the week's core habit: the backend's data is ground truth, not the exporter you configured.

**Estimated time:** 75 minutes. Guided.

---

## Setup

You need a Kind cluster with headroom and `kubectl`. We run everything single-replica for the lab.

```bash
kubectl get nodes          # Ready
kubectl create namespace observability
```

**Fallback if your Phase 1 services aren't instrumented.** Use the OpenTelemetry **demo** app's `frontend`/`recommendation` services, or the Collector's `telemetrygen` tool (`telemetrygen traces --otlp-endpoint otel-collector:4317 --otlp-insecure`) to emit synthetic traces/metrics/logs. The whole pipeline works identically; wherever this says `cart`, substitute the demo service.

---

## Step 1 — Object storage (MinIO), the shared backend

Tempo, Loki, and (next exercise) Thanos all write to one S3-compatible store. Deploy MinIO:

```bash
kubectl apply -n observability -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata: { name: minio }
spec:
  selector: { matchLabels: { app: minio } }
  template:
    metadata: { labels: { app: minio } }
    spec:
      containers:
      - name: minio
        image: minio/minio:latest
        args: ["server", "/data", "--console-address", ":9001"]
        env:
        - { name: MINIO_ROOT_USER, value: minio }
        - { name: MINIO_ROOT_PASSWORD, value: minio123 }
        ports: [{ containerPort: 9000 }, { containerPort: 9001 }]
EOF
kubectl expose deploy/minio -n observability --port 9000 --target-port 9000
```

Create the buckets (`tempo`, `loki`, `thanos`) via the MinIO console (`kubectl port-forward svc/minio 9001`) or `mc`.

---

## Step 2 — The OTel Collector

Apply the Collector config from Lecture 1 §2.2 (receivers → processors → exporters). The key lines: OTLP receiver in, `memory_limiter` + `batch` processors, three exporters out. Note `enable_open_metrics: true` on the Prometheus exporter — that's what carries **exemplars** (the metric→trace link) in Exercise 2 and the mini-project.

```bash
kubectl create configmap otel-collector-config -n observability \
  --from-file=config.yaml=otel-collector-config.yaml   # the file from Lecture 1 §2.2
kubectl apply -n observability -f otel-collector-deploy.yaml   # Deployment + Service on 4317/4318/8889
```

Confirm the Collector is up and *receiving* nothing yet:

```bash
kubectl logs -n observability deploy/otel-collector | grep -i "everything is ready"
```

---

## Step 3 — Tempo and Loki

Deploy Tempo (single-binary, MinIO backend — the config from Lecture 2 §2.1) and Loki (single-binary, MinIO backend):

```bash
kubectl apply -n observability -f tempo.yaml      # OTLP receiver on 4317, s3 backend = minio/tempo
kubectl apply -n observability -f loki.yaml        # OTLP receiver, s3 backend = minio/loki
```

Wait for both Ready. Tempo listens for traces from the Collector's `otlp/tempo` exporter; Loki from `otlphttp/loki`.

---

## Step 4 — Point your services at the Collector

Your services already have the OTel SDK (Week 6 + Lecture 1 §3). Set the OTLP endpoint env var so they export to the Collector (the standard OTel env var works for all three languages):

```bash
kubectl set env -n shop deploy/cart deploy/inventory \
  OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector.observability:4317 \
  OTEL_SERVICE_NAME=cart                # ensure service.name is set (the load-bearing attr)
# (set OTEL_SERVICE_NAME per-deployment to the right name)
kubectl rollout restart -n shop deploy/cart deploy/inventory
```

---

## Step 5 — Drive traffic

Generate some requests so there's telemetry to find:

```bash
kubectl run load --image=curlimages/curl -n shop --rm -it --restart=Never -- \
  sh -c 'for i in $(seq 1 50); do curl -s http://cart.shop:8080/cart/abc >/dev/null; done'
```

---

## Step 6 — Prove the data landed (the whole point)

Do **not** trust the config. Query each backend and confirm the data — and that one trace ID threads all three.

**1. A trace in Tempo.** Search by service, grab a trace ID:

```bash
kubectl port-forward -n observability svc/tempo 3200:3200 &
curl -s "http://localhost:3200/api/search?tags=service.name%3Dcart&limit=1" | jq '.traces[0].traceID'
# "4bf92f3577b34da6a3ce929d0e0e4736"   <-- a real trace ID; the pipeline carried a span end to end
```

**2. A metric in Prometheus** (you'll deploy Prometheus in Exercise 2; for now the Collector's own `prometheus` exporter exposes the app metrics on :8889):

```bash
kubectl port-forward -n observability svc/otel-collector 8889:8889 &
curl -s http://localhost:8889/metrics | grep http_server_request_duration_seconds_bucket | head -1
# the histogram bucket series is being exported — Exercise 2 scrapes it.
```

**3. A log line in Loki, filtered by that SAME trace ID:**

```bash
kubectl port-forward -n observability svc/loki 3100:3100 &
logcli query --addr=http://localhost:3100 \
  '{service_name="cart"} | json | trace_id="4bf92f3577b34da6a3ce929d0e0e4736"'
# ... the exact log lines for that one request, found by trace ID ...
```

If the same trace ID appears in step 1 (Tempo) and resolves a log line in step 3 (Loki), you have a *correlated* pipeline — the foundation the whole week stands on.

---

## Step 7 — Break it on purpose

Set `OTEL_EXPORTER_OTLP_ENDPOINT` to a wrong endpoint (`http://nowhere:4317`), restart `cart`, drive traffic, and confirm: the trace search returns *nothing new*, and the Collector logs show no receives from `cart`. This is the default failure mode — a misconfigured exporter drops telemetry *silently*. The lesson: the pipeline never errors loudly when it loses data; you only catch it by querying the backend. Restore the endpoint and confirm traces return.

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] MinIO is up with `tempo`, `loki`, (and `thanos`) buckets.
- [ ] The OTel Collector is running and its logs show it receiving OTLP from your services after you drive traffic.
- [ ] Tempo returns at least one trace for `service.name=cart` (queried, not assumed).
- [ ] The Collector's `:8889/metrics` exposes the app's histogram bucket series.
- [ ] Loki returns log lines for `{service_name="cart"}` filtered by a real trace ID — proving the same trace ID threads traces and logs.
- [ ] You demonstrated the silent-drop failure (wrong endpoint → no new traces, no loud error) and can state why "the data is ground truth, not the config."

---

## Stretch

- Add the **gateway/agent split**: run the Collector as a DaemonSet (agent) that forwards to a Deployment (gateway), and confirm traces still flow. This is the topology tail sampling needs.
- Turn on the Collector's `spanmetrics` connector so RED metrics are *derived from your traces*, and compare them against the metrics your SDK emits directly. Which would you alert on, and why?
- Add a `resource` processor that injects `deployment.environment=lab` on everything, and confirm the label appears on a trace and a metric — the cross-cutting enrichment the Collector centralizes.

---

When this feels comfortable, move to [Exercise 2 — Thanos and the RED PromQL](./exercise-02-thanos-and-promql.yaml).
