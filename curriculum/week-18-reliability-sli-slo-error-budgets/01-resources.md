# Week 18 — Resources

Every resource here is **free** and **open**. The Google SRE books are published free online; the resilience libraries (resilience4j, Polly, `sony/gobreaker`) are open-source; KEDA is a CNCF graduated project; `k6` is open-source. No paywalled books are linked.

This week's *math* (error budgets, burn rates, Little's law, the USL) is stable and timeless. The *tools* version: this week targets **KEDA 2.1x+**, **`k6` 0.5x+**, **Prometheus 2.5x+** (the Week 17 stack), and the current `sony/gobreaker`/resilience4j/Polly lines. When a link is to `latest`, pin it if a field differs; the concepts don't move.

## Required reading (work it into your week)

- **Google SRE Book — Ch. 4, "Service Level Objectives"** — SLI/SLO/SLA, the error budget, the foundational chapter. Read it Monday:
  <https://sre.google/sre-book/service-level-objectives/>
- **Google SRE Workbook — "Implementing SLOs"** — the practical chapter: choosing SLIs, the SLO document, the error-budget policy:
  <https://sre.google/workbook/implementing-slos/>
- **Google SRE Workbook — "Alerting on SLOs"** — the multi-window multi-burn-rate alerting pattern, derived and tabulated:
  <https://sre.google/workbook/alerting-on-slos/>
- **Google SRE Book — Ch. 22, "Addressing Cascading Failures"** — retries, load shedding, the thundering herd, graceful degradation:
  <https://sre.google/sre-book/addressing-cascading-failures/>
- **Marc Brooker — "Exponential Backoff And Jitter"** (AWS) — why retries need jitter, with the math:
  <https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/>

## SLIs, SLOs, error budgets

- **Google SRE Book — Ch. 3, "Embracing Risk"** — the error budget as the reconciliation of reliability and velocity:
  <https://sre.google/sre-book/embracing-risk/>
- **Google SRE Workbook — "Error Budget Policy"** — the appendix template for what the team does when the budget is spent:
  <https://sre.google/workbook/error-budget-policy/>
- **OpenSLO** — an open spec for declaring SLOs as YAML (a portable SLO document format):
  <https://github.com/OpenSLO/OpenSLO>
- **Sloth** — a Prometheus SLO generator: write the SLO, get the recording + burn-rate alert rules:
  <https://sloth.dev/>

## The resilience patterns

- **`sony/gobreaker`** — the Go circuit breaker (closed/open/half-open), the one the exercise uses:
  <https://github.com/sony/gobreaker>
- **resilience4j** — the JVM library (circuit breaker, bulkhead, retry, rate limiter, time limiter):
  <https://resilience4j.readme.io/docs>
- **Polly** — the .NET resilience library (the same patterns for the C# world):
  <https://www.pollydocs.org/>
- **Martin Fowler — "CircuitBreaker"** — the canonical pattern writeup:
  <https://martinfowler.com/bliki/CircuitBreaker.html>
- **Michael Nygard — *Release It!* (the patterns)** — circuit breaker, bulkhead, timeout, steady state; the book that named them (summaries free online):
  <https://pragprog.com/titles/mnee2/release-it-second-edition/>

## Backpressure, load shedding, admission control

- **Netflix — concurrency-limits** — adaptive concurrency limiting / load shedding derived from Little's law:
  <https://github.com/Netflix/concurrency-limits>
- **Google SRE Book — "Handling Overload"** — load shedding, graceful degradation, criticality:
  <https://sre.google/sre-book/handling-overload/>
- **Envoy — Circuit breaking & outlier detection** — the mesh-layer versions you already met in Week 7/8:
  <https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/circuit_breaking>

## Autoscaling

- **KEDA — Concepts** — event-driven autoscaling, scalers, scaling to zero:
  <https://keda.sh/docs/latest/concepts/>
- **KEDA — Kafka scaler** — scaling a consumer on partition lag (the exercise's scaler):
  <https://keda.sh/docs/latest/scalers/apache-kafka/>
- **Kubernetes — Horizontal Pod Autoscaler** — HPA on CPU and custom/external metrics:
  <https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/>

## Capacity and tail latency

- **Neil Gunther — The Universal Scalability Law** — contention (α) + coherency (β) and the throughput peak:
  <http://www.perfdynamics.com/Manifesto/USLscalability.html>
- **Little's Law (L = λW)** — the queueing identity behind concurrency limits and capacity sizing:
  <https://en.wikipedia.org/wiki/Little%27s_law>
- **Gil Tene — "How NOT to Measure Latency"** — coordinated omission, why the mean lies, HDR histograms:
  <https://www.youtube.com/watch?v=lJ8ydIuPFeU>
- **HdrHistogram** — the high-dynamic-range histogram for honest p99.9/p99.99 measurement:
  <http://hdrhistogram.org/>
- **`k6`** — the load generator, with thresholds and trend metrics for tail latency:
  <https://grafana.com/docs/k6/latest/>

## Talks worth your time (free, no signup)

- **"SLOs are a Tool, Not a Goal"** — search the SREcon / USENIX channel for the error-budget-as-negotiation talks posted each cycle:
  <https://www.usenix.org/conferences/byname/925>
- **Marc Brooker on retries and backoff** — the AWS Builders' Library reliability articles:
  <https://aws.amazon.com/builders-library/>

## Tools you'll use this week

- **Prometheus + Thanos** (from Week 17) — every SLI is a PromQL query over these; burn-rate alerts run here.
- **`k6`** — drive load to burn the budget, open the circuit breaker, and find the saturation point.
- **KEDA** — the operator that scales the Kafka consumer on lag (install via Helm/manifest).
- **`sony/gobreaker`** — the circuit breaker in the Go exercise.
- **HdrHistogram** (or `k6`'s built-in trend metrics) — honest tail-latency measurement.
- **Alertmanager** (stretch) — route the fast-burn page and the slow-burn ticket differently.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **SLI** | Service Level Indicator: a measured ratio of good events to valid events (e.g. non-5xx / all requests). |
| **SLO** | Service Level Objective: a target for the SLI over a window (e.g. 99.9% over 28 days). |
| **SLA** | Service Level Agreement: a *contractual* SLO with consequences (refunds); usually looser than the internal SLO. |
| **Error budget** | (1 − SLO): the allowed unreliability — a resource you spend on risk/velocity. |
| **Error-budget policy** | What the team does when the budget is spent (freeze features, stabilize, negotiate). |
| **Burn rate** | How fast you're spending the error budget, relative to the rate that would exhaust it exactly over the window. |
| **Multi-window multi-burn-rate** | The alerting pattern: a fast window + high burn rate (page) and a slow window + low burn rate (ticket), off one budget. |
| **Circuit breaker** | A wrapper that stops calling a failing dependency (open), then probes to recover (half-open → closed). |
| **Bulkhead** | Isolating resource pools so one dependency's failure can't exhaust all threads/connections. |
| **Timeout** | A bound on every wait, so a hung dependency can't hold a caller forever. |
| **Jitter** | Randomness added to retry/backoff timing so retries don't synchronize into a thundering herd. |
| **Retry budget** | A cap on the *fraction* of traffic that may be retries, so retries can't amplify an outage. |
| **Backpressure** | Pushing back on producers (instead of queueing unboundedly) when you can't keep up. |
| **Load shedding** | Dropping the marginal request under overload to protect the rest (and your latency). |
| **Admission control** | Deciding at the door whether to accept a request, by criticality/capacity. |
| **HPA** | Horizontal Pod Autoscaler: scales replicas on CPU or custom metrics. |
| **KEDA** | Event-driven autoscaler: scales on external signals (Kafka lag, queue depth), and to zero. |
| **Little's Law** | L = λW: average concurrency = arrival rate × average latency. The basis of concurrency limits. |
| **Universal Scalability Law** | Throughput = N / (1 + α(N−1) + βN(N−1)): contention + coherency cause a peak, past which more is slower. |
| **Tail latency** | The high percentiles (p99, p99.9, p99.99) — what slow users feel; the mean hides it. |
| **HDR histogram** | A high-dynamic-range histogram that records the full latency distribution for honest tail percentiles. |

---

*If a link 404s, please open an issue so we can replace it.*
