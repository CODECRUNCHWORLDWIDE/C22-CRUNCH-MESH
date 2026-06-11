# Mini-Project — Harden `cart` to Production-Ready: Logs, Probes, Shutdown, OTel, Helm, and a Runbook

> Take the gRPC `cart` service you built in Weeks 4–5 and put it all the way through a production-readiness review: structured JSON logs, gRPC health checking with separate liveness/readiness, graceful shutdown that drops zero requests, baseline OpenTelemetry traces and RED metrics threaded through your Week-5 interceptor, a Helm chart with probes/limits/security, and a runbook covering five named failure modes — then *prove* a rolling deploy under load drops zero requests.

This is the capstone of Phase 1. After this week, `cart` is not a service that "runs" — it's a service you can defend in a review, deploy on a Friday without fear, and hand to an on-call engineer who didn't write it. Every clause of "production-ready" is checkable, and you'll have checked them.

**Estimated time:** ~12 hours, split across Thursday, Friday, and Saturday in the suggested schedule.

**Compounds forward:** This hardened `cart` is the atom of everything in Phases 2–4. **Week 7** puts it behind Envoy; **Week 8** into the Istio mesh with mTLS; **Week 17** connects its OTel pipeline to Tempo/Prometheus/Loki/Grafana; **Week 18** turns its RED metrics into SLOs; the **capstone** runs it across two regions. A mesh of hardened services is the goal; this week makes the first one hardened. The runbook you write here is revised into a portfolio artifact at graduation.

---

## What you will build

Six deliverables, each a clause of "production-ready":

1. **Structured logging.** `cart` logs JSON to stdout via `slog`, with a consistent schema and a `trace_id` field on every line, no secrets/PII logged.
2. **Health checking.** The gRPC `grpc.health.v1.Health` service, with readiness that flips to `NOT_SERVING` during drain — and (for the HTTP probe path) separate `/healthz` (liveness, self-only) and `/readyz` (readiness, self-only). Neither checks `catalog` or the DB.
3. **Graceful shutdown.** `SIGTERM` → flip health to NOT_SERVING → `GracefulStop` (drain in-flight RPCs) → close the DB pool → exit, bounded under the grace period.
4. **Baseline OpenTelemetry.** A span per RPC via the `otelgrpc` handler (threaded through the Week-5 interceptor seam), context propagation across the `cart`→`catalog` gRPC call (global W3C propagator), RED metrics, and an OTLP exporter to a local collector.
5. **The Helm chart.** `cart` packaged as a chart with a Deployment (requests *and* limits, all three probes, non-root `SecurityContext`, grace period + `preStop`, ServiceAccount, PDB), a Service, a ConfigMap, and a `values.yaml`.
6. **The runbook.** A document covering `cart`'s purpose, dependencies, SLOs, dashboards, and **five named failure-mode playbooks**, each executable by someone who didn't write the service.

And one proof: **a rolling deploy under load that drops zero requests.**

---

## Why each clause, not just "it works"

The whole week's thesis is that "works" and "production-ready" are different states, and only the second is defensible. Each deliverable closes a specific way a service that "works" pages you:

- **No structured logs** → you can't query "all errors on `add_item` for trace X" during an incident; you grep free text and lose.
- **A dependency-checking readiness probe** → a `catalog` blip takes down *all* `cart` replicas at once (the conflation outage).
- **No graceful shutdown** → every deploy drops in-flight checkouts; the team deploys monthly out of fear.
- **No tracing** → a slow `add_item` is a mystery; you can't see it spends its time in `catalog`.
- **No limits** → a leak OOMs the node and takes down neighbors.
- **No runbook** → you're a single point of failure for your own service; every incident escalates to you.

You're not gold-plating. You're closing six concrete incident classes.

---

## Repository layout

```
cart/                                # evolve your Week 5 cart service
├── main.go                          # gRPC server + HTTP health, OTel, shutdown
├── server.go                        # CartService handlers
├── catalog_client.go                # the ACL (Week 4-5), now OTel-instrumented
├── store.go                         # cart_db access, closed cleanly on shutdown
├── observability.go                 # OTel setup: tracer, meter, propagator, exporter
├── health.go                        # grpc.health.v1 + /healthz + /readyz
├── config.go                        # config hierarchy: defaults -> env -> flags
├── go.mod
├── Dockerfile                       # multi-stage, non-root, pinned base
├── deploy/
│   └── cart/                        # the HELM CHART
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/
│           ├── deployment.yaml      # requests+limits, 3 probes, securityContext, preStop
│           ├── service.yaml
│           ├── configmap.yaml
│           ├── serviceaccount.yaml
│           ├── poddisruptionbudget.yaml
│           └── _helpers.tpl
└── RUNBOOK.md                       # the five-failure-mode runbook
```

---

## Deliverable 1 — Structured logging

`cart` logs JSON to stdout. Every log line carries `time`, `level`, `msg` (a stable constant), and `trace_id` (from the active span, so logs link to traces). The `msg` is groupable (`"item_added"`, not an interpolated sentence). Never log the `DATABASE_URL` (it has the password), card data, or full request bodies. The log level comes from config (`LOG_LEVEL`, default `info`).

A helper extracts the trace id from the context so every handler's logs are correlated:

```go
func logWithTrace(ctx context.Context) *slog.Logger {
	sc := trace.SpanContextFromContext(ctx)
	if sc.HasTraceID() {
		return slog.With("trace_id", sc.TraceID().String())
	}
	return slog.Default()
}
```

---

## Deliverable 2 — Health checking (self only!)

Implement the gRPC `grpc.health.v1.Health` service. Mark `cart.v1.CartService` `SERVING` once initialized. Expose, on the HTTP health port, `/healthz` (liveness — returns 200 while the process is alive, checks *nothing else*) and `/readyz` (readiness — 200 when initialized and not draining, checks *nothing else*).

The iron rule from Lecture 1 §3, restated because it's the most important operational fact of the week: **neither probe checks `catalog` or the database.** A `catalog` outage is handled in the request path (degrade, typed error), *never* by failing readiness — failing readiness on a dependency outage takes down all replicas at once. If your readiness handler imports your DB client, you've already done it wrong.

---

## Deliverable 3 — Graceful shutdown

The `SIGTERM` handler, in order: flip the gRPC health status to `NOT_SERVING` and `/readyz` to 503 (so traffic stops routing to you), then `grpcServer.GracefulStop()` (drains in-flight RPCs), then `db.Close()` (after the server has drained, so no in-flight RPC loses its DB), then exit — all bounded under `terminationGracePeriodSeconds` with a forced `Stop()` fallback. This is Lecture 1 §4.3, applied to `cart`. The proof that it works is the zero-drop demonstration below.

---

## Deliverable 4 — Baseline OpenTelemetry

Wire OTel through the Week-5 interceptor seam:

- **Server:** `grpc.NewServer(grpc.StatsHandler(otelgrpc.NewServerHandler()))` — a span per RPC.
- **Client (`cart`→`catalog`):** the `otelgrpc.NewClientHandler()` so the `catalog` call is a *child* span and the trace id propagates.
- **Propagator:** `otel.SetTextMapPropagator(propagation.TraceContext{})` *globally*, at startup, or your spans won't stitch across the boundary (the #1 OTel mistake).
- **Metrics:** a meter provider with an OTLP exporter to the collector (`OTEL_EXPORTER_OTLP_ENDPOINT` from config), emitting RED.
- **Resource:** set `service.name=cart` so the telemetry is attributable.

Run a local OpenTelemetry Collector (a container) and show a trace of an `add_item` that includes the `catalog` child span. The full Tempo/Prometheus/Grafana backend is Week 17; this week is the instrumentation.

---

## Deliverable 5 — The Helm chart

Package `cart` as a chart whose Deployment has *every* non-negotiable field (Lecture 2 §2.2): resource requests *and* limits, all three probes (self-only), a non-root `SecurityContext` (`runAsNonRoot`, `allowPrivilegeEscalation: false`, dropped caps, read-only root fs), `terminationGracePeriodSeconds` + `preStop` sleep, a `ServiceAccount`, and a `PodDisruptionBudget`. The `values.yaml` parameterizes image tag, replica count, and resources. `helm install` / `helm upgrade` deploy it. Use Exercise 3's manifest as the template body.

```bash
helm install cart ./deploy/cart --set image.tag=1.0.0
helm upgrade cart ./deploy/cart --set replicaCount=4
```

---

## Deliverable 6 — The runbook

`RUNBOOK.md`, the senior deliverable. It must contain (Lecture 2 §4.1):

1. **Purpose and owners** — what `cart` does, who owns it, where code/dashboards/alerts live.
2. **Dependencies** — `catalog`, `cart_db`; what happens to `cart` when each fails.
3. **SLOs** — availability and latency SLIs/targets (lightly; rigor in Week 18).
4. **Dashboards** — the RED dashboard and what "normal" looks like.
5. **Five named failure-mode playbooks** — each *symptom → diagnosis → mitigation → verify → escalate*, executable by someone who didn't write the service. The canonical five: `catalog` down/slow, `cart_db` down/saturated, a bad deploy, resource exhaustion (OOM/throttle), a traffic spike (Lecture 2 §4.2).

The test of a playbook: it contains commands, not wishes. "Run `kubectl rollout undo deployment/cart`, confirm error rate drops within 2 minutes on the RED dashboard, page the change author" — not "investigate the deploy."

---

## The proof — zero dropped requests on deploy

The demonstration that ties it all together:

```bash
# Steady load
hey -z 60s -c 20 -host wishlist.local http://cart:8080/...   # or a gRPC load tool
# Mid-flight, roll it:
kubectl rollout restart deployment/cart
# Result: 0 failed requests. Capture the load summary + `kubectl get pods` roll.
```

Zero drops proves graceful shutdown + readiness gating + the rolling-update strategy (`maxUnavailable: 0`) + the `preStop` sleep are all correct *together*. Any drop means one of them is wrong.

---

## Rules

- **You must not** let either probe check `catalog` or the database (the conflation outage).
- **You must** flip health/readiness *before* draining on `SIGTERM`, and close the DB *after* draining.
- **You must** set the OTel propagator globally, or the `cart`→`catalog` trace won't stitch.
- **You must** keep the Week 4–5 invariants: database-per-service (no `CATALOG_DATABASE_URL`), the ACL (cart's core never imports `catalogv1`), and the price snapshot.
- **You must not** bake the DB password into the image or log it; it comes from a Secret.
- Go 1.23+, `kubectl`, `helm`, Kind, an OTel collector container.

---

## Acceptance criteria

- [ ] A public GitHub repo (evolve your Week 5 `cart`).
- [ ] Logs are JSON to stdout with a `trace_id` field; no secret/PII in any log line.
- [ ] gRPC health + `/healthz` + `/readyz`; **neither probe checks a dependency** (verifiable by reading the handlers — they import no DB/catalog client).
- [ ] Graceful shutdown drops zero in-flight RPCs on `SIGTERM`; demonstrated.
- [ ] OTel: a trace of `add_item` shows a `catalog` child span (context propagated); RED metrics export to a collector; `service.name=cart` set.
- [ ] A Helm chart with requests+limits, all three probes, non-root SecurityContext, grace period + preStop, ServiceAccount, PDB; `helm install`/`upgrade` work.
- [ ] `RUNBOOK.md` with all six sections and five *executable* failure-mode playbooks.
- [ ] **The zero-drop proof**: a load summary showing 0 failed requests across a rolling restart under load, plus the pod-roll evidence.
- [ ] Week 4–5 invariants still hold (database-per-service, ACL, price snapshot).
- [ ] A repo `README.md` linking the audit, the chart, the runbook, and the zero-drop proof.
- [ ] Committed and pushed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Health checking correctness** | 20 | Liveness/readiness separate; **neither checks a dependency**; readiness flips on drain. (The single most-weighted item — get the conflation rule right.) |
| **Graceful shutdown** | 20 | Correct order (flip → drain → close); bounded under grace; **zero-drop proof** present and convincing. |
| **Observability** | 15 | Structured logs with trace_id; a stitched `cart`→`catalog` trace; RED metrics; propagator set globally. |
| **Helm chart** | 15 | All non-negotiable Deployment fields present; values parameterize sensibly; install/upgrade work. |
| **The runbook** | 20 | Five executable playbooks (commands, not wishes); dependencies section names what happens when each dep fails; another engineer could run it. |
| **Invariants & hygiene** | 10 | Database-per-service, ACL, price snapshot all still hold; no secrets in logs/image; clean commits. |

**90+** is portfolio-grade and is the atom Phase 2 builds on. **70–89** works but the runbook is wishful or the shutdown drops a request under load. **Below 70** means a probe checks a dependency or shutdown drops requests — fix those first; they're the two that cause outages.

---

## Stretch goals

- **Exemplars.** Wire OTel exemplars so a spike in the RED latency histogram links to the exact slow trace — the feature that makes "why was p99 bad at 14:03?" one click (full pipeline in Week 17).
- **gRPC native probe.** Use Kubernetes' native `grpc:` probe against `grpc.health.v1.Health` instead of the HTTP shim, and explain the trade-off.
- **Chaos micro-drill in the runbook.** Add a "verified" line to each playbook: the actual command you ran to confirm the failure mode and the recovery (e.g. `kubectl delete pod` for the pod-loss case). A runbook whose playbooks have been *tested* is worth ten that haven't.
- **SLO burn alert.** Define a fast-burn and slow-burn alert on the availability SLO (a preview of Week 18) and document the response in the runbook.

---

## How this connects to the rest of C22

- **Week 7 (Envoy)** puts this hardened `cart` behind a gateway with rate limiting, retries, and circuit breaking — network-layer hardening on top of your service-layer hardening.
- **Week 8 (Istio)** moves `cart` into the mesh with mTLS and traffic shifting; your readiness gating is what makes the mesh's canary rollouts safe.
- **Week 17 (observability)** connects your OTLP exporter to the full Tempo/Prometheus/Loki/Grafana pipeline; the instrumentation you did this week is what lights up.
- **Week 18 (reliability)** turns your RED metrics into SLOs and error budgets; the runbook's SLO section is the seed.
- **The capstone** runs this `cart` across two regions; the runbook is graded and revised into a portfolio artifact.

When you've finished, push the repo and take the [quiz](../quiz.md). You've completed Phase 1 — your service is hardened. Phase 2 connects it to others.

---

*This is the last mini-project of Phase 1. From here, every week assumes the service you built is production-ready. Make sure it is.*
