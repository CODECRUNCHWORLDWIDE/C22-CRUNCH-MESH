# Week 18 — Reliability: SLI/SLO, Error Budgets, and the Patterns

Welcome to the week reliability stops being a feeling and becomes a number you can defend. Last week you made the system observable — every signal flowing, correlated, queryable. This week you decide *what those signals should be* and *what counts as good enough*, then you build the engineering patterns that keep the system inside that bound under load. By Friday you will have three real **SLIs** for the cart system, **SLOs** with **error budgets**, **multi-window multi-burn-rate** alerts computed from first principles, a **circuit breaker** around the payment dependency, **KEDA** autoscaling on Kafka lag, and a measured **saturation point** found with `k6` and HDR histograms.

The thing to internalize before anything else: **an SLO is not a technical ceiling you hope to stay under; it is a negotiation tool — a budget you spend deliberately.** The error budget — the gap between your SLO and 100% — is *permission to fail*, and that reframing is the whole point. If your availability SLO is 99.9%, you have a budget of 0.1% — about 43 minutes a month — of allowed unreliability, and that budget is a *resource*: spend it on a risky deploy, on a chaos drill, on shipping faster. A team with budget left can take risks; a team that's burned its budget freezes and stabilizes. The SLO turns "is it reliable enough?" — an argument nobody can win — into "do we have budget?" — a question the data answers. Defending that framing against product pressure ("just make it 100%") is the senior skill this week teaches, and 100% is the wrong target every time: the cost curve to each extra nine is exponential, and the marginal nine is almost never worth what it costs.

We assume Week 17's `cart-observed` stack is running. An SLI *is* a PromQL query over the metrics you wired up last week — `istio_requests_total`, your app's RED histograms. You cannot define an SLO without observability, which is exactly why this week follows that one. The error budget is arithmetic over those queries; the burn-rate alert is more arithmetic. The reliability *patterns* — circuit breakers, bulkheads, timeouts, retries with jitter, backpressure, load shedding, autoscaling — are the levers you pull to *keep* the system inside the budget when reality pushes back.

One framing runs through the whole week. The naive reliability story is "add retries and an autoscaler and hope." The real story is a set of deliberate, quantified choices: which **SLI** actually reflects user pain (the wrong one makes you chase phantoms), what **burn-rate** thresholds page you fast on a catastrophe but slowly on a simmer (so you neither miss the fire nor get paged for noise), why a **retry without jitter** is a synchronized thundering herd that amplifies an outage, and where the system's **saturation point** actually is (the Universal Scalability Law says it's not where you'd guess, and past it more load makes you *slower*). Each is a place where the easy default makes the outage worse, and naming them is what separates an engineer who *talks* about reliability from one who *engineers* it.

This week is where you stop hoping the system is reliable and start proving — and defending — that it is.

## Learning objectives

By the end of this week, you will be able to:

- **Define** SLIs that mean something — a good-events / valid-events ratio over the right events — and explain why a badly-chosen SLI (one that's green while users suffer) is worse than none.
- **Set** SLOs and compute the resulting **error budget** as a concrete time/event allowance, and articulate the error budget as a *resource you spend*, not a line you must never cross.
- **Derive** multi-window multi-burn-rate alerts from first principles: what burn rate means, why a fast-burn page and a slow-burn ticket come off the *same* budget, and how to set the windows and thresholds so you alert on real budget threats without false pages.
- **Defend** an SLO against product pressure — explaining why 100% is the wrong target, why the marginal nine costs exponentially more, and how the error budget reframes the reliability conversation as a negotiation.
- **Implement** the named resilience patterns: circuit breakers (`sony/gobreaker`/resilience4j/Polly), bulkheads, timeouts, retries with **jitter and a budget**, backpressure, load shedding, and admission control — and explain the failure each prevents.
- **Configure** autoscaling: HPA on CPU/custom metrics and **KEDA** on Kafka consumer lag, and reason about why lag-based scaling fits an event-driven workload better than CPU.
- **Reason** about capacity with **Little's Law** and the **Universal Scalability Law**: find the saturation point where added load reduces throughput, and explain contention and coherency costs.
- **Measure** tail latency honestly — p99 vs p99.9 vs p99.99 — with HDR histograms, and explain why the mean lies and why tail latency is what users feel.

## Prerequisites

This week assumes you have completed **C22 weeks 1–17**, or have equivalent fluency. Specifically:

- The **Week 17 observability stack** running: Prometheus + Thanos with your cart RED metrics, because every SLI this week is a PromQL query over them.
- The **cart topology** with a **payment dependency** (real or stubbed) you can wrap in a circuit breaker, and a **Kafka consumer** (from Week 10) whose lag KEDA can scale on.
- Comfort with **PromQL** at the Week 17 level: `rate()`, ratios, `histogram_quantile`. We build the burn-rate math on top of it.
- **Kubernetes** with metrics-server (for HPA) and the ability to install **KEDA** (a small operator).
- A load generator — **`k6`** is the one we use; `fortio`/`vegeta` also work.
- Comfort reading **Go** (the circuit-breaker exercise is Go) — the patterns transfer to any language.

You do **not** need prior SRE experience. We start at "what is an SLI" and build up to multi-window burn-rate alerting, the resilience patterns, and the saturation-point measurement that turns reliability from a vibe into a number.

## Topics covered

- **SLIs**: the good-events / valid-events ratio; choosing the SLI that reflects user pain (availability, latency, correctness, freshness); request-based vs window-based SLIs; why the mesh's `istio_requests_total` is a ready-made availability SLI and where it falls short (network success ≠ semantic success).
- **SLOs and error budgets**: the SLO as a target over a window; the **error budget** = (1 − SLO) as a spendable resource; the budget in minutes (availability) and in events; the **error-budget policy** (what the team does when the budget is spent — freeze, stabilize, negotiate).
- **Burn-rate alerting**: burn rate as "how fast you're spending the budget"; **multi-window multi-burn-rate** alerts (the Google SRE workbook pattern) — a fast window + high burn rate for the page, a slow window + low burn rate for the ticket; setting windows/thresholds for precision and recall; why this beats a static-threshold alert.
- **Defending the SLO**: 100% is the wrong target (the cost of each nine is exponential; the chain's weakest dependency caps you anyway); the error budget as a negotiation tool against "make it more reliable"; aligning the SLO with what the business actually needs.
- **The resilience patterns**: **circuit breaker** (closed/open/half-open) around a failing dependency; **bulkhead** (isolate resource pools so one dependency can't exhaust all threads/connections); **timeout** (bound every wait); **retry with jitter and budget** (recover transients without a thundering herd or a retry storm); **backpressure** (push back instead of queueing unboundedly); **load shedding** and **admission control** (drop the marginal request to protect the rest).
- **Autoscaling**: **HPA** on CPU and custom metrics; **KEDA** scaling on Kafka consumer lag (and to zero); why an event-driven consumer scales on *lag*, not CPU, and the cold-start / flapping tradeoffs.
- **Capacity and tail latency**: **Little's Law** (L = λW) for queue sizing; the **Universal Scalability Law** (contention + coherency → a throughput peak, past which more concurrency is slower); **tail latency** (p99/p99.9/p99.99), why the mean lies, why fan-out amplifies the tail, and measuring it with **HDR histograms**.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                          | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|----------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | SLIs, SLOs, error budgets; the budget as a resource            |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Multi-window multi-burn-rate alerting from first principles    |    1h    |    2.5h   |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | Circuit breakers, bulkheads, timeouts, retries with jitter     |    2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | Backpressure, load shedding, autoscaling (HPA, KEDA on lag)     |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Friday    | USL, Little's Law, tail latency; finding the saturation point   |    0h    |    0h     |     1h     |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work                                          |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, review, SLO-document polish                              |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                                | **6h**   | **7h**    | **4h**     | **3.5h**  | **5h**   | **12h**      | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | The Google SRE books, the resilience-pattern docs, the USL/Little's-law references |
| [lecture-notes/01-sli-slo-error-budgets-and-burn-rate.md](./lecture-notes/01-sli-slo-error-budgets-and-burn-rate.md) | SLIs, SLOs, error budgets as a resource, and multi-window multi-burn-rate alerting derived from first principles |
| [lecture-notes/02-resilience-patterns-autoscaling-and-the-saturation-point.md](./lecture-notes/02-resilience-patterns-autoscaling-and-the-saturation-point.md) | Circuit breakers, bulkheads, retries with jitter, backpressure, load shedding, HPA/KEDA, USL/Little's law, tail latency |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-slo-and-burn-rate.md](./exercises/exercise-01-slo-and-burn-rate.md) | Define three SLIs/SLOs for cart, compute the error budget, and write the multi-window burn-rate alert rules |
| [exercises/exercise-02-circuit-breaker.go](./exercises/exercise-02-circuit-breaker.go) | A complete circuit breaker (with timeout + jittered retry) around the payment dependency, with a load test that opens and recovers it |
| [exercises/exercise-03-keda-autoscale-on-lag.yaml](./exercises/exercise-03-keda-autoscale-on-lag.yaml) | A complete KEDA ScaledObject autoscaling the Kafka consumer on lag, plus the HPA comparison |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-the-retry-storm-that-took-down-payment.md](./challenges/challenge-01-the-retry-storm-that-took-down-payment.md) | Diagnose a retry storm where un-jittered retries + no circuit breaker turned a blip into a full outage, and fix it |
| [quiz.md](./quiz.md) | 13 questions with a hidden answer key |
| [homework.md](./homework.md) | Six problems including the error-budget-policy memo and the saturation-point measurement |
| [mini-project/README.md](./mini-project/README.md) | `cart-reliable`: SLOs + burn-rate alerts + the resilience patterns + KEDA + a measured saturation point on the cart topology |

## The "the budget is real" promise

C22 uses a recurring marker for every exercise that ends in the system actually doing what you declared. This week's canonical one is the **error budget computed and burning**, proven in PromQL — not asserted on a slide:

```
# The SLI: the good-events / valid-events ratio for cart, over 28 days.
$ promtool query instant http://thanos:9090 \
  'sum(rate(http_server_requests_total{service="cart",code!~"5.."}[28d]))
   / sum(rate(http_server_requests_total{service="cart"}[28d]))'
0.9991      # 99.91% — above the 99.9% SLO, so there's budget left

# The burn rate RIGHT NOW (how many times faster than the budget allows):
$ promtool query instant http://thanos:9090 \
  '(1 - sum(rate(http_server_requests_total{service="cart",code!~"5.."}[1h]))
       / sum(rate(http_server_requests_total{service="cart"}[1h]))) / (1 - 0.999)'
14.2        # burning 14x the allowed rate over the last hour -> a fast-burn PAGE
```

If the SLI is above the SLO you have budget; if the burn rate over a short window is high, you are spending it fast and the multi-window alert fires. The point of this week is to make these numbers *the* reliability conversation: not "is it up?" but "how much budget do we have, and how fast are we spending it?" An organization that can answer that in PromQL negotiates reliability with evidence; one that can't argues about it with opinions — and the loudest opinion wins, which is how you end up chasing 100%.

## Stretch goals

If you finish the regular work early and want to push further:

- Wire the burn-rate alerts into **Alertmanager** with two real routes — a fast-burn page to PagerDuty/Slack-urgent and a slow-burn ticket — and prove the fast one fires in minutes on an induced spike while the slow one doesn't false-positive on noise.
- Add an **error-budget-based deploy gate**: a CI check that blocks a deploy when the budget is exhausted (the error-budget policy, automated) — the capstone's "automatic rollback on SLO breach" generalized to "don't ship when you're out of budget."
- Implement **adaptive concurrency / load shedding** (a Little's-law-derived concurrency limit, e.g. Netflix's concurrency-limits approach) in front of cart, and show it sheds the marginal request to hold p99 instead of letting latency collapse under overload.
- Find your system's USL **peak** empirically: run `k6` at rising concurrency, fit N/(1 + α(N−1) + βN(N−1)), and identify the concurrency past which throughput *drops*. Put a number on your scalability ceiling.

## Up next

Week 18 closes Phase 3. Next is Phase 4 — production and the capstone. Week 19 takes everything you've built single-region and stretches it across **two regions**: active-active vs active-passive, quorum across regions, geo-routing, and a controlled failover with a 60-second RTO target. The SLOs you define this week become the *contract* that failover must honor — "did we stay inside the latency and availability budget during the region loss?" is the question the Week 22 gameday and the capstone's region-failover drill answer. Reliability stops being a single-cluster property and becomes a multi-region one. Push your `cart-reliable` mini-project — its SLOs and burn-rate alerts are what you'll watch when a whole region goes dark.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
