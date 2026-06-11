# Week 6 — Resources

Every resource here is **free** and **current to 2026**. The twelve-factor manifesto is free and short. OpenTelemetry, Kubernetes, and Helm all have excellent first-party docs. The two SRE books from Google are free to read online. No paywalled material is required.

The bias matches the course: read the manifesto and the official probe/shutdown docs, not a blog that conflated liveness and readiness — that conflation is the source of more self-inflicted outages than almost anything else, and the official docs are precise about it.

## Required reading (work it into your week)

- **The Twelve-Factor App.** Short, foundational, free. Read all twelve; pay special attention to III (config), VI (processes), IX (disposability), XI (logs). The lens for Lecture 1.
  <https://12factor.net/>
- **Kubernetes — Configure Liveness, Readiness and Startup Probes.** The authoritative source on what each probe does and how Kubernetes acts on it. The antidote to the conflation outage.
  <https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/>
- **Kubernetes — Pod Lifecycle (termination).** The `SIGTERM` → grace-period → `SIGKILL` sequence, `preStop`, and the readiness-removal race. Graceful shutdown lives or dies on this.
  <https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination>
- **OpenTelemetry — Concepts (signals, context propagation).** Traces, metrics, logs; spans; context propagation. The conceptual spine of Lecture 2.
  <https://opentelemetry.io/docs/concepts/>
- **Helm — Charts.** The chart structure, templates, and values. The packaging model for the mini-project.
  <https://helm.sh/docs/topics/charts/>

## The SRE canon (free, read the relevant chapters)

- **Google SRE Book — "Service Level Objectives" and "Embracing Risk."** SLIs, SLOs, error budgets. You define SLOs for `cart` this week (and go deeper in Week 18).
  <https://sre.google/sre-book/service-level-objectives/>
- **Google SRE Workbook — "Implementing SLOs."** The practical how-to behind the theory.
  <https://sre.google/workbook/implementing-slos/>
- **Google SRE Book — "Monitoring Distributed Systems" (the Four Golden Signals).** Latency, traffic, errors, saturation — the cousin of RED metrics.
  <https://sre.google/sre-book/monitoring-distributed-systems/>

## Structured logging

- **`slog` — Go's standard structured logger (Go 1.21+).** The standard-library structured logger; what the exercises use. Levels, attributes, handlers, JSON output.
  <https://pkg.go.dev/log/slog>
- **OpenTelemetry — Logs and log/trace correlation.** How to attach trace context to logs so a log line links to its trace.
  <https://opentelemetry.io/docs/specs/otel/logs/>
- **"What to log and what not to log."** The OWASP logging cheat sheet — the authoritative source on never logging secrets/PII.
  <https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html>

## Health checking

- **gRPC Health Checking Protocol (`grpc.health.v1`).** The standard health-check service for gRPC; what Kubernetes' `grpc` probe calls.
  <https://github.com/grpc/grpc/blob/master/doc/health-checking.md>
- **Kubernetes — gRPC liveness probe.** Using a native gRPC probe (`grpc:` in the probe spec) instead of an exec/HTTP shim.
  <https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/#define-a-grpc-liveness-probe>

## Graceful shutdown

- **Go — `os/signal.NotifyContext` and `http.Server.Shutdown`.** Catching `SIGTERM` and draining HTTP.
  <https://pkg.go.dev/os/signal#NotifyContext>
  <https://pkg.go.dev/net/http#Server.Shutdown>
- **gRPC Go — `Server.GracefulStop`.** Draining in-flight gRPC RPCs before exit.
  <https://pkg.go.dev/google.golang.org/grpc#Server.GracefulStop>
- **"Graceful shutdown in Kubernetes" — the readiness-removal race explained.** Why a `preStop` sleep is often needed. (Search the CNCF/learnk8s write-ups; the Kubernetes pod-lifecycle doc above is the primary source.)
  <https://learnk8s.io/graceful-shutdown>

## OpenTelemetry (the SDK and instrumentation)

- **OpenTelemetry Go SDK.** Setting up a tracer/meter provider, the OTLP exporter, and gRPC instrumentation.
  <https://opentelemetry.io/docs/languages/go/>
- **`otelgrpc` — OpenTelemetry gRPC interceptors.** The drop-in interceptor that traces every RPC and propagates context — threaded through the same interceptor hook from Week 5.
  <https://pkg.go.dev/go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc>
- **W3C Trace Context.** The `traceparent` header standard that propagates a trace across services.
  <https://www.w3.org/TR/trace-context/>
- **The RED method (Tom Wilkie).** Rate, Errors, Duration — the default service dashboard.
  <https://grafana.com/blog/2018/08/02/the-red-method-how-to-instrument-your-services/>

## Helm and packaging

- **Helm — Chart Template Guide.** Templating, values, helpers.
  <https://helm.sh/docs/chart_template_guide/>
- **Kubernetes — Resource requests and limits.** Why both, and what happens under each kind of pressure (CPU throttling, OOMKill).
  <https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/>
- **Kubernetes — Pod Security Standards / SecurityContext.** Running non-root, dropping capabilities, read-only root filesystem.
  <https://kubernetes.io/docs/concepts/security/pod-security-standards/>

## Secrets (now and the path forward)

- **Kubernetes — Secrets.** Mounting secrets as env or files; the limitations (base64 is not encryption).
  <https://kubernetes.io/docs/concepts/configuration/secret/>
- **SPIFFE / SPIRE — the path you'll take in Week 21.** Why workload identity beats long-lived env secrets. Read the concept now; implement it later.
  <https://spiffe.io/docs/latest/spiffe-about/overview/>

## Talks worth your time (free, no signup)

- **"How to lose data in Kubernetes" / graceful-shutdown talks (KubeCon archive).** The readiness-removal race, demonstrated.
  <https://www.youtube.com/@CloudNativeFdn>
- **Tom Wilkie — "Monitoring with the RED method."** The origin of RED.
  <https://www.youtube.com/@Grafana>
- **OpenTelemetry deep-dive talks (CNCF).** Context propagation and the collector.
  <https://www.youtube.com/@CloudNativeFdn>

## Tools you'll use this week

- **`kubectl`** — apply manifests, read logs, `rollout restart`, `delete pod` for the chaos micro-drill.
- **`helm`** — `helm template`, `helm install`, `helm upgrade` the `cart` chart.
- **`slog`** (Go stdlib) — structured JSON logs.
- **`grpcurl`** — call the gRPC health service (`grpc.health.v1.Health/Check`).
- **An OTLP collector** (locally, the OpenTelemetry Collector in a container) — to receive traces/metrics; full backend (Tempo/Prometheus/Grafana) comes in Week 17.
- **`k6` or `hey`** — generate load for the zero-drop-deploy demonstration.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **Twelve-factor** | A methodology for building operable, disposable, config-from-env services. |
| **Structured log** | A log as a JSON object with named fields, not a free-text string. |
| **Liveness probe** | "Is the process wedged?" Fail → Kubernetes restarts the container. |
| **Readiness probe** | "Can I serve traffic right now?" Fail → removed from the Service's endpoints (not restarted). |
| **Startup probe** | "Has the process finished booting?" Gates the other probes for slow starters. |
| **Graceful shutdown** | On `SIGTERM`: stop accepting new work, drain in-flight, close resources, exit before `SIGKILL`. |
| **`terminationGracePeriodSeconds`** | How long Kubernetes waits after `SIGTERM` before `SIGKILL` (default 30s). |
| **`preStop` hook** | A command run before `SIGTERM`; often a sleep to dodge the readiness-removal race. |
| **OpenTelemetry (OTel)** | The vendor-neutral standard for traces, metrics, and logs. |
| **Span** | One unit of work in a trace, with a start, end, and attributes. |
| **Context propagation** | Carrying the trace id across a service boundary (W3C `traceparent`). |
| **RED metrics** | Rate, Errors, Duration — the default per-service dashboard. |
| **OTLP** | The OpenTelemetry wire protocol to a collector. |
| **Helm chart** | A templated, parameterized package of Kubernetes manifests. |
| **Resource request/limit** | Guaranteed (request) and capped (limit) CPU/memory for a container. |
| **Runbook** | The operational doc: purpose, deps, SLOs, dashboards, and failure-mode playbooks. |
| **SLI / SLO** | Service Level Indicator (a measured number) / Objective (the target for it). |

---

*If a link 404s, please open an issue so we can replace it.*
