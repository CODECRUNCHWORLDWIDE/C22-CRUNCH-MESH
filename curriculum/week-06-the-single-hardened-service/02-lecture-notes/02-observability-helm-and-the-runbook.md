# Lecture 2 — Baseline Observability, Helm Packaging, Secrets, and the Runbook

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can instrument a service with baseline OpenTelemetry (a span per request, context propagation, RED metrics), package it as a Helm chart with probes/limits/security, handle secrets correctly, and write a runbook another engineer can execute at 3 a.m.

Lecture 1 made the service *behave* well — config, logs, health, shutdown. This lecture makes it *observable* and *deployable* and *operable by someone other than you*. Four parts: (1) baseline OpenTelemetry, (2) Helm packaging, (3) secrets, (4) the runbook. The first three you do once and forget; the fourth is the one seniors are actually judged on.

---

## Part 1 — Baseline OpenTelemetry

You cannot operate what you cannot see. A service in production must answer, at minimum, three questions: *how much traffic, how many errors, how slow?* (the RED metrics) and *where did this one slow request spend its time?* (a trace). OpenTelemetry (OTel) is the vendor-neutral standard for all of it, and "baseline" instrumentation — enough to answer those questions — is a Week-6 requirement, not a nice-to-have.

### 1.1 The three signals

OTel defines three signals:

- **Traces** — a trace is the story of one request as it flows through one or more services; each unit of work is a **span** with a start, end, attributes, and a parent. A trace answers "where did the time go?"
- **Metrics** — aggregate numbers over time: counters (requests served), histograms (request duration), gauges (in-flight requests). Metrics answer "how is the service doing *in aggregate*?"
- **Logs** — the structured events from Lecture 1 §2, correlated to traces via `trace_id`.

The power is in *correlation*: a latency spike in a metric, clicked through an **exemplar** to the exact trace that was slow, whose spans link to the logs from that request. You build the baseline now; the full Tempo/Prometheus/Loki/Grafana pipeline is Week 17. This week is the *instrumentation*, not the backend.

### 1.2 A span per request, via the interceptor

Remember the gRPC interceptor from Week 5 — the cross-cutting hook? That's exactly where tracing goes. OTel ships a drop-in gRPC instrumentation (`otelgrpc`) that starts a span for every RPC, records its duration and status, and — critically — handles **context propagation**:

```go
import (
	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"go.opentelemetry.io/otel"
)

// On the server: one stats handler traces every RPC and extracts incoming context.
grpcServer := grpc.NewServer(
	grpc.StatsHandler(otelgrpc.NewServerHandler()),
)

// On the client (cart calling catalog): inject the trace context outbound.
conn, err := grpc.NewClient(catalogAddr,
	grpc.WithStatsHandler(otelgrpc.NewClientHandler()),
	grpc.WithTransportCredentials(insecure.NewCredentials()),
)
```

That's the baseline: every `cart` RPC is a span; every `cart`→`catalog` call is a *child* span; and the trace stitches together across the service boundary because the trace id rides along.

### 1.3 Context propagation (the W3C `traceparent`)

How does the trace span `catalog`'s work *and* `cart`'s work as one trace? **Context propagation.** When `cart` calls `catalog`, the OTel instrumentation injects a **`traceparent`** header (the W3C Trace Context standard) into the gRPC metadata — a string like `00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01` carrying the trace id and the parent span id. `catalog`'s server instrumentation *extracts* it and makes its spans children of `cart`'s. The result is a single trace spanning both services.

You must set a global propagator so this works:

```go
import "go.opentelemetry.io/otel/propagation"

otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
	propagation.TraceContext{},  // W3C traceparent
	propagation.Baggage{},
))
```

Without the propagator, you get *disconnected* spans — `cart`'s trace and `catalog`'s trace as two separate stories — which is the single most common OTel misconfiguration. Set the propagator once, globally, at startup. (This same propagation crosses a Kafka boundary in Week 17; the principle is identical.)

### 1.4 RED metrics

The default service dashboard is **RED**: **R**ate (requests/sec), **E**rrors (failures/sec or error ratio), **D**uration (latency distribution — p50, p95, p99). Three metrics, and you can run a service on them. `otelgrpc` emits the underlying measurements; you configure a meter provider and an OTLP exporter to ship them:

```go
import (
	"go.opentelemetry.io/otel/exporters/otlp/otlpmetric/otlpmetricgrpc"
	"go.opentelemetry.io/otel/sdk/metric"
)

exporter, _ := otlpmetricgrpc.New(ctx) // ships to the OTel collector (env-configured endpoint)
meterProvider := metric.NewMeterProvider(metric.WithReader(metric.NewPeriodicReader(exporter)))
otel.SetMeterProvider(meterProvider)
```

The collector endpoint comes from config (`OTEL_EXPORTER_OTLP_ENDPOINT`) — twelve-factor §1.1 in action. In Week 17 the collector forwards to Prometheus/Tempo/Loki; this week, even just running a local collector that prints what it receives proves your instrumentation works.

### 1.5 The OTLP exporter and the collector

Your service exports over **OTLP** (the OpenTelemetry wire protocol) to a **collector** — a separate process that receives, processes, and forwards telemetry. The service doesn't know or care where the data ultimately lands (echoing the logs-to-stdout decoupling of Lecture 1 §1.2): it ships OTLP to the collector, and the collector's config decides the backend. This decoupling is why you can swap Tempo for Jaeger without touching a service. Configure the OTLP endpoint from the environment; default to `localhost:4317` for local dev.

---

## Part 2 — Packaging with Helm

A pile of `kubectl apply -f` YAML files is not a deployable unit; it's a liability. **Helm** packages your manifests into a *chart* — templated, parameterized, versioned, installable and upgradable as one thing. The mini-project ships `cart` as a chart.

### 2.1 What a chart contains

```
cart/
├── Chart.yaml          # name, version, appVersion
├── values.yaml         # the parameters (image, replicas, resources, ...)
└── templates/
    ├── deployment.yaml # templated Deployment
    ├── service.yaml    # the Service
    ├── configmap.yaml  # non-secret config
    ├── serviceaccount.yaml
    └── _helpers.tpl    # template helpers (labels, names)
```

`values.yaml` is the dial board: `image.tag`, `replicaCount`, `resources`, `env`. `templates/` are Kubernetes manifests with `{{ .Values.image.tag }}`-style placeholders. `helm install cart ./cart --set image.tag=1.4.2` renders and applies. `helm upgrade` does a rolling update. One chart, every environment, parameterized by values — twelve-factor §1.1, at the deployment layer.

### 2.2 The non-negotiable Deployment fields

A production `cart` Deployment must have *all* of these, and a readiness review checks each:

- **Resource requests *and* limits.** Requests tell the scheduler how much to reserve (so the pod lands on a node with room); limits cap usage (so a leak doesn't starve neighbors). CPU over-limit → throttling; memory over-limit → **OOMKill**. A pod with no limits can take down a node; a pod with no requests can be scheduled onto a node with no room and get evicted. Both, always.
- **Liveness, readiness, and (for slow starters) startup probes** — wired exactly per Lecture 1 §3. Readiness gating is what makes the zero-drop deploy work.
- **A non-root `SecurityContext`** — `runAsNonRoot: true`, a non-zero `runAsUser`, `allowPrivilegeEscalation: false`, dropped capabilities, and ideally `readOnlyRootFilesystem: true`. A container running as root is a container one CVE away from a node compromise.
- **`terminationGracePeriodSeconds`** and the `preStop` hook from Lecture 1 §4.2.
- **A `ServiceAccount`** (even a minimal one) so the pod's identity is explicit — the seed of the SPIFFE identity story in Week 21.
- **Multiple replicas + a `PodDisruptionBudget`** so a node drain or a rolling deploy never takes the service to zero.

A Deployment missing limits or probes is the single most common readiness-review failure. There is no "we'll add them later" — later is the incident.

---

## Part 3 — Secrets, now and later

Lecture 1 §5 introduced the config hierarchy; secrets are the part that needs extra care.

**Now (Week 6):** secrets come from a **Kubernetes Secret**, mounted as an environment variable or a file. The `DATABASE_URL` (with its password) lives in a Secret, referenced by the Deployment, injected at runtime. Rules: never bake a secret into an image (it's in the layer history forever), never commit a Secret's plaintext (base64 in a Secret is *encoding*, not encryption — anyone with `get secret` access reads it), and never log a secret (Lecture 1 §2.3 — including the full `DATABASE_URL`, which contains the password).

**The limitation:** Kubernetes Secrets are long-lived and only base64-encoded at rest by default. A leaked Secret is a standing liability until rotated, and rotation is manual and disruptive.

**Later (Week 21):** **SPIFFE/SPIRE** issues each workload a short-lived, automatically-rotated cryptographic *identity* (an SVID), and services authenticate to each other and to backing services with that identity rather than a shared long-lived password. The credential lives seconds-to-hours, rotates without downtime, and is tied to *what the workload is*, not a secret it holds. You implement this in Week 21; this week, **design so the swap is cheap** — keep credential acquisition in the config/auth layer, not sprinkled through business logic, so replacing a `DATABASE_URL` env var with a SPIFFE-issued credential touches one module.

---

## Part 4 — The runbook (the deliverable seniors are judged on)

Everything above is mechanical — you do it once and a checklist verifies it. The runbook is different: it's the artifact that turns *your* operational knowledge into *the team's*, and writing a good one is a senior responsibility, not documentation busywork. When `cart` pages at 3 a.m. and you're on vacation, the runbook is the difference between a 10-minute fix by whoever's on call and a 2-hour escalation to you.

### 4.1 What a runbook contains

1. **Purpose and owners.** What `cart` does, in two sentences. Who owns it (team + escalation). Where the code, the dashboards, and the alerts live.
2. **Dependencies.** What `cart` depends on (`catalog`, `cart_db`) and what depends on `cart` (`order`). For each, what happens to `cart` when that dependency fails — *the* most-used section during an incident.
3. **SLOs and the error budget.** The SLIs (e.g. availability = successful requests / total; latency = p99 < 200ms) and their SLO targets. What "we're burning error budget" looks like and when to declare an incident. (Defined lightly here; rigorously in Week 18.)
4. **Dashboards and key metrics.** Links to the RED dashboard. What "normal" looks like (baseline rate, error ratio, p99) so an on-call can tell normal from broken.
5. **The failure-mode playbooks.** The heart of the runbook: for each named failure mode, *symptom → diagnosis → mitigation → verification → escalation*. This is what gets executed at 3 a.m.

### 4.2 The five named failure modes (the Week-6 requirement)

Your `cart` runbook must cover five concrete failure modes, each as a playbook. The canonical five for `cart`:

1. **`catalog` is down or slow.** *Symptom:* `cart`'s `add_item` latency/errors spike; trace shows time in the `catalog` span. *Diagnosis:* check `catalog`'s health, the `cart`→`catalog` error rate. *Mitigation:* `cart` should degrade (serve from snapshot, return a typed error) — *not* go unready (Lecture 1 §3.2!). *Verify:* error rate recovers. *Escalate:* to the `catalog` team if `catalog` is the root cause.
2. **`cart_db` is down or saturated.** *Symptom:* `add_item`/`get_cart` fail; DB connection errors in logs. *Diagnosis:* check DB health, connection-pool exhaustion, slow queries. *Mitigation:* failover to a replica if read-only; shed load; scale the pool. *Verify:* DB reachable, errors clear. *Escalate:* to the DB owner.
3. **A bad deploy (regression or crash loop).** *Symptom:* errors/crashes spike right after a rollout; `CrashLoopBackOff`. *Diagnosis:* correlate with the deploy timeline; read the new pods' logs. *Mitigation:* `kubectl rollout undo deployment/cart`. *Verify:* error rate returns to baseline. *Escalate:* to the author of the bad change.
4. **Resource exhaustion (OOMKill / CPU throttle).** *Symptom:* pods restarting with OOMKilled; latency up from CPU throttling. *Diagnosis:* check memory/CPU vs limits; look for a leak or a traffic spike. *Mitigation:* raise limits (short term), scale out (HPA), fix the leak (long term). *Verify:* restarts stop, p99 recovers.
5. **A traffic spike / overload.** *Symptom:* rate far above baseline; latency climbing; saturation. *Diagnosis:* is it organic, a retry storm, or an attack? *Mitigation:* autoscale (HPA), shed load, rate-limit at the gateway (Week 7). *Verify:* latency back under SLO. *Escalate:* if it's an attack or capacity is exhausted.

Each playbook is *executable by someone who didn't write the service* — that's the test. If a playbook says "investigate the issue," it's not a playbook; it's a wish. "Run `kubectl rollout undo deployment/cart`, confirm error rate drops within 2 minutes on the RED dashboard, page the change author" is a playbook.

### 4.3 Why this is the senior deliverable

Juniors ship features. Seniors ship features *and the operability that lets the team run them without the senior in the room.* A runbook is how you stop being a single point of failure for your own service. It's also, not coincidentally, the artifact graded in the capstone and the thing an interviewer probes when they ask "tell me about a time you were on call." Write it as if you'll be unreachable when it's needed — because someday you will be.

---

## Part 5 — Defining SLIs and SLOs for `cart` (a preview)

The runbook's "SLOs" section (§4.1.3) deserves its own treatment, because an SLO defined badly is worse than none — it either cries wolf or hides real pain. Week 18 makes this rigorous; here is enough to seed your runbook honestly.

An **SLI** (Service Level Indicator) is a *measured* number that reflects user-visible health. A **SLO** (Objective) is the target you commit to for that number. For `cart`, two SLIs cover most of the value:

- **Availability SLI** = (successful requests) / (total valid requests), over a rolling window. "Successful" means a non-`INTERNAL`/`UNAVAILABLE` gRPC status — note that a `NOT_FOUND` for a real missing product is a *success* (the service did its job), so define the numerator carefully. A reasonable SLO: **99.9%** over 28 days.
- **Latency SLI** = the fraction of requests served faster than a threshold. "99% of `add_item` calls complete within 200ms" is a latency SLO. You measure it from the RED duration histogram. Note it's a *percentile target*, not an average — averages hide the tail that actually hurts users.

Three rules that keep an SLO useful:

1. **Measure what the user feels, not what's easy.** CPU utilization is not an SLI; "did the user's add-to-cart succeed quickly" is. The SLI lives as close to the user as you can get it.
2. **The SLO is a budget, not a ceiling.** 99.9% availability means you have a **0.1% error budget** — about 43 minutes/month of allowed unavailability. Spend it deliberately (risky deploys, chaos drills) and stop spending it (freeze risky changes) when it's running low. This is how an SLO becomes a *decision tool*, not a vanity metric.
3. **An SLO you can't measure is a wish.** If your runbook claims "99.9% availability" but you have no dashboard computing it, you have a slogan. The RED metrics from Part 1 are what make the SLI *measurable*; the SLO is the line you draw on that measurement.

For the Week-6 runbook, write down the two SLIs, a target for each, and where they're measured (the RED dashboard). Week 18 adds error budgets, burn-rate alerts, and the negotiation of SLOs against product pressure. The seed you plant now is: **name the user-facing number, commit to a target, and know where it's measured.**

## Part 6 — A self-contained example trace

To make context propagation concrete, here is what one `add_item` produces when fully instrumented, as it would appear in a trace viewer (Tempo, Week 17):

```text
Trace 4bf92f3577b34da6a3ce929d0e0e4736  (total 47ms)
└─ cart.v1.CartService/AddItem            [cart]      47ms
   ├─ db.query "INSERT INTO cart_items"   [cart]       3ms
   ├─ catalog.v1.CatalogService/GetProduct [catalog]  38ms   <- child span, DIFFERENT service
   │  └─ db.query "SELECT FROM products"   [catalog]  35ms   <- the slow part!
   └─ db.query "UPDATE cart_totals"        [cart]       4ms
```

Read what this tells you, instantly, that no log could: the 47ms `add_item` spent **38ms of it waiting on `catalog`**, and within that, **35ms in `catalog`'s database query.** The bottleneck is a slow catalog DB query, two services away from where the symptom (slow `add_item`) appeared. Without distributed tracing, you'd see "`cart` is slow," blame `cart`, and waste an hour. With it, you click the trace and the slow span names itself.

This is only possible because the trace id propagated: `cart` injected `traceparent: 00-4bf92f...-...-01` into the gRPC metadata, `catalog` extracted it, and `catalog`'s spans became children of `cart`'s under the same trace id. Forget the global propagator (§1.3) and this single trace fractures into two disconnected traces — `cart`'s and `catalog`'s — and you lose the very correlation that made the diagnosis a one-click. That's why "set the propagator globally, once, at startup" is the load-bearing line of the instrumentation.

The same trace, correlated to logs via `trace_id`, lets you jump from the slow span to `catalog`'s log lines for *exactly that request*. And in Week 17, an **exemplar** on the RED latency histogram links the p99 spike at 14:03 directly to *this* trace. Metric → trace → log, all stitched by the trace id. That is the three-pillars-correlated payoff, and the baseline you build this week is what makes it possible.

## Part 7 — Why "we'll add observability later" is a trap

A recurring failure: a team ships a service with no instrumentation, planning to "add it when we need it." Then an incident hits, and they're blind exactly when sight matters most — no traces to find the slow dependency, no RED metrics to see the error spike, no structured logs to query. They add instrumentation *during* the incident, which is the worst possible time.

Observability is not a feature you bolt on; it's a property you build in. The cost of doing it at service-creation (this week) is small — a few interceptors, a meter provider, structured logs from line one. The cost of retrofitting it onto a running, un-instrumented service under incident pressure is enormous. This is why baseline OTel is a *Week-6 requirement*, alongside health checks and shutdown: a service that "works" but can't be *seen* is not production-ready, because the first incident will prove it un-operable. You instrument before you need it, precisely because when you need it, it's too late to start.

---

## 5. Recap

You should now be able to:

- Instrument a service with baseline OpenTelemetry: a span per request via the gRPC interceptor, context propagation with the W3C `traceparent` and a global propagator, RED metrics, and an OTLP exporter to a collector.
- Package a service as a Helm chart with all the non-negotiable Deployment fields: resource requests *and* limits, all three probes, a non-root `SecurityContext`, a grace period + `preStop`, a `ServiceAccount`, and a `PodDisruptionBudget`.
- Handle secrets correctly now (Kubernetes Secrets, never baked/committed/logged) with a cheap path to SPIFFE workload identity later.
- Write a runbook with purpose, dependencies, SLOs, dashboards, and five executable failure-mode playbooks — and explain why it's the senior deliverable of the week.

Next: the exercises. You'll audit `cart` against the twelve factors, implement correct graceful shutdown in Go, and write a complete hardened Kubernetes Deployment. Continue to [the exercises](../03-exercises/00-overview.md).

---

## Appendix A — A worked runbook playbook (the format, filled in)

Abstract advice about runbooks is useless; here is one complete playbook in the exact shape your five must take. This is failure mode #3 (a bad deploy) for `cart`, written so a stranger could execute it.

```text
### Playbook: Bad deploy (regression or crash loop)

SYMPTOM
  - cart error rate spikes on the RED dashboard within minutes of a rollout, OR
  - pods in CrashLoopBackOff (kubectl get pods -l app=cart shows restarts climbing).
  - Alert: "cart availability SLO fast-burn" fired.

DIAGNOSE (confirm it's the deploy, not a coincidence)
  1. Correlate timing:  kubectl rollout history deployment/cart
     -> note the revision deployed nearest the error-spike start time.
  2. Read the new pods' logs:
        kubectl logs -l app=cart --tail=100 | grep '"level":"ERROR"'
     -> a panic, a config error, or a failed migration confirms a bad release.
  3. Check the deploy correlates with the spike on the dashboard (overlay deploy
     markers on the RED error panel).

MITIGATE (fastest safe action: roll back)
  4. kubectl rollout undo deployment/cart
  5. Watch it recover: kubectl rollout status deployment/cart

VERIFY (don't declare victory on a hunch)
  6. RED error rate returns to baseline (< 0.1%) within 2 minutes.
  7. kubectl get pods -l app=cart shows all Ready, restarts stable.
  8. A synthetic add_item succeeds:
        grpcurl -plaintext cart:50051 cart.v1.CartService/AddItem -d '{...}'

ESCALATE
  9. Page the author of the bad change (find via rollout history + git blame).
 10. If rollback does NOT recover within 5 min, the regression isn't the new
     image -> escalate to the on-call lead and treat as a broader incident.
```

Notice what makes this executable: every step is a *command* or a *checkable condition*, not "investigate." A person who has never seen `cart` before can run it. That is the bar. Apply this exact shape to all five failure modes (catalog down, db down, bad deploy, resource exhaustion, traffic spike), and you have a runbook the team can use without you.

## Appendix B — Helm values, the dial board

The point of a chart is that `values.yaml` is the *only* file a deployer edits. A good `values.yaml` for `cart`:

```yaml
# values.yaml — every knob a deployer touches, with safe defaults.
image:
  repository: ghcr.io/crunchmesh/cart
  tag: "1.0.0"          # pinned, never "latest"
  pullPolicy: IfNotPresent

replicaCount: 3

resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 256Mi

probes:
  startupFailureThreshold: 20   # ~60s to boot
  livenessPeriodSeconds: 10
  readinessPeriodSeconds: 5

terminationGracePeriodSeconds: 40
preStopSleepSeconds: 5

podDisruptionBudget:
  minAvailable: 2

env:
  logLevel: info
  otelEndpoint: http://otel-collector.observability:4317
```

The discipline: anything that varies by environment lives here (image tag, replica count, resources, log level), and the templates reference it (`{{ .Values.replicaCount }}`). Anything that is *always* true (the security context, the probe paths, the labels) is hard-coded in the template, not exposed as a knob — because a knob nobody should turn is a footgun. The art of a chart is exposing exactly the right dials: enough to configure every environment, few enough that you can't misconfigure it.

The promotion flow this enables: the same chart, `helm upgrade --set image.tag=1.0.1` in staging, soak it, then the identical command in production. One artifact, one chart, two environments, differing only by the values — twelve-factor's "one image everywhere" realized at the deployment layer.

## Appendix C — The production-readiness review, as a single checklist

Everything in this week's two lectures, compressed into the review you run before a service ships. A `cart` that passes all of these is production-ready; one that fails any blocker is not.

```text
RUNTIME
  [ ] Structured JSON logs to stdout, with trace_id; no secrets/PII logged
  [ ] Liveness probe: self only, forgiving (no dependency checks)
  [ ] Readiness probe: self only (NO dependency checks); flips on drain
  [ ] Startup probe if boot is slow
  [ ] Graceful shutdown: flip health -> drain -> close, bounded under grace
  [ ] preStop sleep to dodge the readiness-removal race
  [ ] Config from environment; secrets from a Secret, never baked/logged

DEPLOYMENT
  [ ] Resource requests AND limits
  [ ] Pinned image tag (not :latest)
  [ ] Non-root SecurityContext; no privilege escalation; dropped caps
  [ ] >= 2-3 replicas + PodDisruptionBudget
  [ ] ServiceAccount (explicit identity)

OBSERVABILITY
  [ ] Span per request; global propagator set; trace stitches across services
  [ ] RED metrics exported via OTLP
  [ ] service.name set on telemetry

OPERABILITY
  [ ] Runbook with 5 executable failure-mode playbooks
  [ ] SLIs/SLOs defined and measurable on the dashboard
  [ ] Proof: rolling deploy under load drops ZERO requests
```

This is the artifact the Week 12 architecture review walks against your `cart` system, and a version of the list every mature platform team keeps. Print it; run it on every service before it ships. The unglamorous truth of operability is that almost all of it is on this one page, and almost all production incidents trace to a box on it that was left unchecked.

## References

- OpenTelemetry — Concepts: <https://opentelemetry.io/docs/concepts/>
- `otelgrpc` instrumentation: <https://pkg.go.dev/go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc>
- W3C Trace Context: <https://www.w3.org/TR/trace-context/>
- The RED method: <https://grafana.com/blog/2018/08/02/the-red-method-how-to-instrument-your-services/>
- Helm — Charts: <https://helm.sh/docs/topics/charts/>
- Kubernetes — Resource requests and limits: <https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/>
- Google SRE Workbook — Implementing SLOs: <https://sre.google/workbook/implementing-slos/>
- SPIFFE overview (the Week-21 path): <https://spiffe.io/docs/latest/spiffe-about/overview/>
