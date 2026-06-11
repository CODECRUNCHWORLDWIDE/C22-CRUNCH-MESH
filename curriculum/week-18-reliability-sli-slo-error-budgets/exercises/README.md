# Week 18 — Exercises

Three focused drills on a running, observable cart system. Each takes 45–90 minutes. Do them in order — exercise 1 (the SLO + burn-rate alerts) defines the budget the rest of the week protects; exercise 2 (the circuit breaker) is a pattern that *keeps* the system inside that budget when payment fails; exercise 3 (KEDA on lag) keeps the async path inside it under a burst. Run everything against your **cart topology** with the **Week 17 observability stack** (every SLI is a PromQL query over those metrics) and a **Kafka consumer** from Week 10.

## Index

1. **[Exercise 1 — The SLO and the burn-rate alert](exercise-01-slo-and-burn-rate.md)** — define three SLIs/SLOs for cart, compute the error budget as time and events, write the recording rules and the multi-window multi-burn-rate alert rules, and prove the budget burns under an induced error spike. (~75 min, guided)
2. **[Exercise 2 — The circuit breaker](exercise-02-circuit-breaker.go)** — a complete Go circuit breaker (`sony/gobreaker`) with a timeout and jittered retry around the payment dependency, plus a load test that drives payment to failure, watches the breaker *open* (fail fast), and watches it recover through half-open. (~60 min, runnable)
3. **[Exercise 3 — KEDA autoscaling on Kafka lag](exercise-03-keda-autoscale-on-lag.yaml)** — a complete KEDA ScaledObject that scales the `order.placed.v1` consumer on partition lag, with the HPA-on-CPU comparison and a burst test showing lag-based scaling catch up where CPU-based wouldn't. (~60 min, runnable)

## How to work the exercises

- Have the **Week 17 stack** (Prometheus + Thanos with cart RED metrics) running — exercise 1 queries it directly.
- Have a **payment dependency** (real or a stub you can make fail) and a **Kafka consumer** with measurable lag.
- Install **KEDA** (`helm install keda kedacore/keda -n keda --create-namespace`) for exercise 3, and have **`k6`** for the load tests.
- **Compute the budget, then watch it burn — don't just assert it.** The week's habit: reliability is a *number you can query*, not a claim on a slide. After every change, run the PromQL — the SLI ratio, the burn rate — and confirm the budget is where you think it is. The mesh-week habit ("the proxy is ground truth") and the observability-week habit ("the backend's data is ground truth") become here: *the burn-rate query is ground truth, not the dashboard's color.*
- When a pattern "isn't working," check the *symptom* in the metrics first (did the breaker actually open? did lag actually drive a scale-up?), then the config. The data tells you whether the pattern fired.
- Each runnable exercise ends with an **expected output** block. If your output doesn't match, you're not done.

## Running the exercises

The `.go` exercise is a standard Go program:

```bash
go mod init cb-demo && go get github.com/sony/gobreaker/v2
go run exercise-02-circuit-breaker.go --fail-rate 0.8     # drive payment to 80% failure
```

The `.yaml` exercise is applied with `kubectl` (KEDA must be installed):

```bash
kubectl apply -f exercise-03-keda-autoscale-on-lag.yaml
kubectl get hpa -n shop -w        # KEDA creates an HPA under the hood; watch it scale on lag
```

The header of each file lists the exact prerequisites. If your Phase 1 services aren't ready, each file points you at the minimal stand-in (a stub payment server, a synthetic lag generator).

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c22-week-18` to compare.
