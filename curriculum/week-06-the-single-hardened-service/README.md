# Week 6 — The Single Hardened Service

Welcome to the week where your service stops being a thing that runs on your laptop and becomes a thing that survives production. By Friday you will take the gRPC `cart` service you built over the last two weeks and put it through a real production-readiness review: twelve-factor configuration, structured JSON logs, health and readiness probes that Kubernetes actually uses, graceful shutdown that doesn't drop in-flight requests, baseline OpenTelemetry traces and metrics, a Helm chart, and — the deliverable senior engineers are judged on and juniors forget — a **runbook** that another engineer can follow at 3 a.m. when your service is the one paging.

This is the last week of Phase 1, and it's the hinge. The first three weeks were theory. Weeks 4 and 5 drew boundaries and made them typed. This week makes a *single* service production-grade — because you have no business connecting two services in a mesh (Phase 2) until each one is individually hardened. A mesh of un-hardened services is just a bigger blast radius. The discipline of this week is the discipline the whole rest of the course assumes you have.

The one thing to internalize before you read another line: **production readiness is a checklist, not a vibe.** "It works" is not a state you can defend in a review. "It reads its config from the environment, logs structured JSON to stdout, exposes `/healthz` and `/readyz` that mean different things, drains in-flight requests on `SIGTERM` within the termination grace period, emits a trace per request and RED metrics, ships as a Helm chart with resource limits and probes wired, and has a runbook covering five named failure modes" — *that* is a state you can defend, because every clause is checkable. The difference between a service that pages you twice a year and one that pages you twice a week is almost never the business logic. It's whether these unglamorous things were done. This week makes them ordinary.

This is where your service grows up.

## Learning objectives

By the end of this week, you will be able to:

- **Apply** the twelve-factor methodology to a service author's daily decisions — config from the environment, logs as event streams to stdout, stateless processes, disposability — and explain *why* each factor exists in terms of operability.
- **Emit** structured JSON logs with a consistent schema (level, timestamp, message, trace-id, and contextual fields), correlate them to traces, and explain why "log a string" is an anti-pattern at scale.
- **Distinguish** liveness from readiness with precision — what each probe answers, what Kubernetes does with each, and the specific outages caused by conflating them — and implement both for a gRPC service.
- **Implement** graceful shutdown that catches `SIGTERM`, stops accepting new work, drains in-flight requests, closes resources in order, and completes inside the Kubernetes termination grace period — so a rolling deploy drops zero requests.
- **Design** a configuration hierarchy (defaults → file → environment → flags) with the right precedence, and handle secrets correctly — environment/mounted-secret for now, with a clear path to SPIFFE/workload-identity later.
- **Instrument** a service with baseline OpenTelemetry: a span per request with context propagation across the gRPC boundary, RED metrics (Rate, Errors, Duration), and the wiring that lets a trace link to its logs.
- **Package** the service as a Helm chart with a Deployment (resource requests/limits, probes, a `SecurityContext`), a Service, and configurable values — the deployable unit the rest of the course uses.
- **Write** a runbook another engineer can execute: the service's purpose, its dependencies, its SLOs, its dashboards, and step-by-step responses to five named failure modes — the artifact that turns your on-call knowledge into the team's.

## Prerequisites

This week assumes you have completed **C22 weeks 1–5**, or have equivalent fluency. Specifically:

- You finished the **Week 5 mini-project** and have a gRPC `catalog`/`cart` pair generated from a versioned `.proto`, with a logging interceptor and database-per-service. This week hardens the `cart` service specifically. If you skipped it, the skeleton service in the exercises is your fallback.
- You understand from Week 5 that the gRPC **interceptor** is the cross-cutting hook — this week you thread OpenTelemetry tracing through exactly that interceptor, so having it makes the instrumentation natural.
- You have Docker and a local Kubernetes (Kind assumed) working: `kubectl get nodes` succeeds, and you can `kubectl apply` a manifest and `kubectl logs` a pod.
- You can write a basic Go service (HTTP and gRPC servers, `context.Context`, goroutines, `os/signal`) and read a basic Python service. We harden a Go service in the exercises; the concepts are language-agnostic.
- You have `helm` installed (`helm version` works) or can install it; the mini-project ships a Helm chart.

You do **not** need prior OpenTelemetry or Helm experience. We start at twelve-factor and build to a fully instrumented, charted, runbooked service. If you've deployed services but never been able to defend that they're *production-ready* against a checklist, this is the week that knowledge becomes load-bearing.

## Topics covered

- **The twelve-factor app, reviewed for service authors.** The factors that bite hardest in 2026: config in the environment (III), logs as event streams to stdout (XI), stateless/share-nothing processes (VI), disposability with fast startup and graceful shutdown (IX), dev/prod parity (X), and treating backing services as attached resources (IV). Why each is an *operability* decision, not dogma.
- **Structured logging.** JSON logs with a consistent schema; log levels that mean something; the trace-id and request-id fields that make logs correlatable; why structured logs are queryable (Loki, in Week 17) and string logs are not; what *not* to log (secrets, PII, the whole request body).
- **Health checking: liveness vs readiness.** Liveness ("is the process wedged and in need of a restart?") vs readiness ("can I serve traffic *right now*?"). The classic outage: a readiness probe that checks a dependency, the dependency blips, every replica goes unready at once, and you've turned a dependency blip into a total outage. The startup probe for slow-booting services. gRPC health checking (`grpc.health.v1`).
- **Graceful shutdown.** The `SIGTERM` → drain → close sequence; the Kubernetes pod lifecycle (`preStop`, `terminationGracePeriodSeconds`, the readiness-removal race); why a service that exits immediately on `SIGTERM` drops in-flight requests on every rolling deploy; `grpc.GracefulStop()` and `http.Server.Shutdown(ctx)` done correctly.
- **Configuration and secrets.** The precedence hierarchy (built-in defaults → config file → environment → command-line flags) and why that order; the twelve-factor stance on config; secrets via environment and mounted Kubernetes Secrets *now*, and the SPIFFE/SPIRE workload-identity path for *later* (Week 21); never baking secrets into images or logs.
- **Baseline OpenTelemetry.** The three signals (traces, metrics, logs) and the SDK; a span per request; context propagation across the gRPC boundary (the W3C `traceparent` header in gRPC metadata); RED metrics (Rate, Errors, Duration) as the default service dashboard; the OTLP exporter to a collector; exemplars linking a metric to a trace (previewed; full pipeline in Week 17).
- **Packaging with Helm.** A chart with a `Deployment` (resource requests *and* limits, liveness/readiness/startup probes, a non-root `SecurityContext`, a `ServiceAccount`), a `Service`, a `ConfigMap`/`Secret`, and a `values.yaml` that parameterizes image, replicas, and resources. Why resource limits and probes are not optional.
- **The runbook as a deliverable.** What a runbook contains (purpose, owners, dependencies, SLOs, dashboards, alerts, and step-by-step playbooks for named failure modes) and why writing it is a senior responsibility, not documentation busywork — it's how on-call knowledge stops living in one person's head.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                     | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|-----------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Twelve-factor; structured logging; config hierarchy       |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Liveness vs readiness; graceful shutdown; the pod lifecycle |  1h    |    2.5h   |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | Baseline OpenTelemetry; RED metrics; context propagation  |    2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | Helm packaging; secrets; the production-readiness review  |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Friday    | The runbook; failure-mode drills                          |    0h    |    0h     |     1h     |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work                                    |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, review, runbook polish                              |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                           | **6h**   | **7h**    | **4h**     | **3.5h**  | **5h**   | **12h**      | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | The twelve-factor manifesto, the OpenTelemetry/Helm docs, the Kubernetes probe docs, and the talks worth your time |
| [lecture-notes/01-twelve-factor-logging-health-and-shutdown.md](./lecture-notes/01-twelve-factor-logging-health-and-shutdown.md) | Twelve-factor, structured logging, liveness vs readiness, and graceful shutdown |
| [lecture-notes/02-observability-helm-and-the-runbook.md](./lecture-notes/02-observability-helm-and-the-runbook.md) | Baseline OpenTelemetry, RED metrics, Helm packaging, secrets, and the runbook |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-twelve-factor-audit.md](./exercises/exercise-01-twelve-factor-audit.md) | Audit the `cart` service against the twelve factors and a production-readiness checklist |
| [exercises/exercise-02-graceful-shutdown.go](./exercises/exercise-02-graceful-shutdown.go) | A Go service with structured logs, liveness/readiness probes, and correct `SIGTERM` draining |
| [exercises/exercise-03-cart-deployment.yaml](./exercises/exercise-03-cart-deployment.yaml) | A complete Kubernetes Deployment + Service with probes, limits, and a `SecurityContext` |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-pass-the-readiness-review.md](./challenges/challenge-01-pass-the-readiness-review.md) | Take a deliberately un-hardened service through a full production-readiness review |
| [quiz.md](./quiz.md) | 13 questions with a hidden answer key |
| [homework.md](./homework.md) | Six problems including the headline runbook |
| [mini-project/README.md](./mini-project/README.md) | Harden `cart` end to end: logs, probes, shutdown, OTel, a Helm chart, and a five-failure-mode runbook |

## The "zero dropped requests on deploy" promise

C22 uses a recurring marker for every service that's actually hardened: **a rolling deploy under load drops zero requests.** When you finish the mini-project, this should be demonstrably true:

```bash
# Fire steady traffic, then trigger a rolling restart mid-flight.
$ kubectl rollout restart deployment/cart &
$ # ... while a load generator hits the service ...
$ # Result: 0 failed requests. The old pods drained; the new pods were ready first.
```

If a rolling restart causes even one `Unavailable` or a dropped connection, your graceful shutdown or your readiness gating is wrong. A service that drops requests every deploy is a service nobody dares deploy — which is how teams end up deploying monthly and calling it "stability." The point of Week 6 is to make zero-drop deploys ordinary, so deploying is boring and frequent — and to make a dropped request *loud* (a failing load test) instead of silent (a customer's failed checkout).

## Stretch goals

If you finish the regular work early and want to push further:

- Read the **twelve-factor app** manifesto end to end (it's short) and write one sentence per factor on how `cart` honors or violates it: <https://12factor.net/>.
- Add **OpenTelemetry exemplars** so a spike in your RED latency histogram links directly to an exemplar trace — the feature that makes "why was p99 bad at 14:03?" a one-click question (full pipeline in Week 17).
- Implement a **`preStop` hook** with a small sleep and explain the readiness-removal race it papers over (the endpoints controller hasn't removed your pod from the Service yet when `SIGTERM` arrives). This is the single most misunderstood detail of graceful shutdown on Kubernetes.
- Run a **chaos micro-drill**: `kubectl delete pod` your `cart` under load and confirm the SLO holds (requests reroute to healthy replicas, zero errors). This is a five-minute preview of the Week 22 gameday.

## Up next

Phase 2 begins. Week 7 takes your hardened `cart` — now individually production-ready — and puts it behind **Envoy**: an API gateway and the data-plane proxy that the whole service mesh is built on. You'll add rate limiting, retries with hedging, and circuit breaking *at the network layer*, in front of the service you hardened this week. A hardened service behind a hardened proxy is the atom of everything that follows. Push your mini-project — chart, runbook, and all — before you start it.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
