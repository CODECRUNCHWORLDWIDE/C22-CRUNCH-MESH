# Exercise 1 — The SLO and the Burn-Rate Alert

**Goal:** Define three real SLIs and SLOs for the cart system, compute the resulting error budget as both a time allowance and an event allowance, write the Prometheus recording rules and the multi-window multi-burn-rate alert rules, and *prove* — by inducing an error spike and querying the burn rate — that the budget actually burns and the fast-burn alert actually fires. You will train the week's core habit: reliability is a number you query, not a claim you assert.

**Estimated time:** 75 minutes. Guided.

---

## Setup

You need the Week 17 stack (Prometheus + Thanos with cart RED metrics) and `promtool`.

```bash
kubectl get pods -n observability     # prometheus/thanos-query Running
promtool --version                     # for rule checking
```

**Fallback if your cart metrics aren't flowing.** Use the mesh's `istio_requests_total{destination_workload="cart"}` (Week 8) as the availability SLI source, or generate synthetic request metrics. Wherever this says `http_server_requests_total`, substitute the metric you actually have.

---

## Step 1 — Choose three SLIs that mean something

Don't pick one and stop — one SLI has blind spots (Lecture 1 §1.2). Define three that cover each other:

1. **Availability SLI** — the fraction of cart requests that didn't 5xx:

```promql
sum(rate(http_server_requests_total{service="cart", code!~"5.."}[5m]))
/ sum(rate(http_server_requests_total{service="cart"}[5m]))
```

2. **Latency SLI** — the fraction served under 250 ms (uses the SLO-aligned bucket from Week 17):

```promql
sum(rate(http_server_request_duration_seconds_bucket{service="cart", le="0.25"}[5m]))
/ sum(rate(http_server_request_duration_seconds_count{service="cart"}[5m]))
```

3. **Correctness SLI** (the one the mesh can't give you) — the fraction of carts whose computed total matched a re-check, from an app-emitted metric `cart_total_correct_total` / `cart_total_checked_total`. If you don't emit this yet, *note that gap* — a missing correctness SLI is exactly the "green while users suffer" risk.

---

## Step 2 — Set SLOs and compute the budget

Write the SLOs down (this becomes the SLO document):

| SLI | SLO (28-day window) | Error budget | ≈ time / 28d | Events allowed (at 100M req) |
|---|---|---|---|---|
| Availability | 99.9% | 0.1% | ~40 min | 100,000 |
| Latency (<250ms) | 99.0% | 1.0% | ~6.7 hours | 1,000,000 |
| Correctness | 99.99% | 0.01% | ~4 min | 10,000 |

Compute the *event* budget for your actual request volume: pull `sum(increase(http_server_requests_total{service="cart"}[28d]))` and multiply by (1 − SLO). Write the number down — "we may fail N requests this window" is the budget made concrete.

---

## Step 3 — Recording rules (precompute the per-window error ratios)

The burn-rate alerts need the error ratio over several windows; precompute each as a recording rule (Week 17 §1.5) so the alert is cheap and the dashboard and alert agree:

```yaml
# slo-recording-rules.yml
groups:
  - name: cart-slo
    interval: 30s
    rules:
      - record: cart:error_ratio:5m
        expr: |
          1 - (sum(rate(http_server_requests_total{service="cart",code!~"5.."}[5m]))
               / sum(rate(http_server_requests_total{service="cart"}[5m])))
      - record: cart:error_ratio:1h
        expr: |
          1 - (sum(rate(http_server_requests_total{service="cart",code!~"5.."}[1h]))
               / sum(rate(http_server_requests_total{service="cart"}[1h])))
      - record: cart:error_ratio:6h
        expr: |
          1 - (sum(rate(http_server_requests_total{service="cart",code!~"5.."}[6h]))
               / sum(rate(http_server_requests_total{service="cart"}[6h])))
      - record: cart:error_ratio:30m
        expr: |
          1 - (sum(rate(http_server_requests_total{service="cart",code!~"5.."}[30m]))
               / sum(rate(http_server_requests_total{service="cart"}[30m])))
```

Check them: `promtool check rules slo-recording-rules.yml`.

---

## Step 4 — The multi-window multi-burn-rate alerts

The fast-burn page (14.4× over 1h AND 5m) and the slow-burn ticket (6× over 6h AND 30m), both off the 99.9% budget:

```yaml
# slo-burn-alerts.yml  (SLO = 0.999, so budget = 0.001)
groups:
  - name: cart-slo-burn
    rules:
      - alert: CartErrorBudgetFastBurn
        expr: |
          (cart:error_ratio:1h / 0.001 > 14.4) and (cart:error_ratio:5m / 0.001 > 14.4)
        for: 2m
        labels: { severity: page }
        annotations:
          summary: "cart burning error budget 14.4x (fast) — ~2 days to exhaustion. PAGE."

      - alert: CartErrorBudgetSlowBurn
        expr: |
          (cart:error_ratio:6h / 0.001 > 6) and (cart:error_ratio:30m / 0.001 > 6)
        for: 15m
        labels: { severity: ticket }
        annotations:
          summary: "cart burning error budget 6x (slow) — quietly eating the budget. TICKET."
```

`promtool check rules slo-burn-alerts.yml`, then load both rule files into Prometheus.

---

## Step 5 — Burn the budget and watch the alert fire

Induce an error spike (deploy a deliberately-broken cart, or use a fault-injection VirtualService from Week 8 to abort 20% of cart requests), drive load, and watch:

```bash
# the burn rate climbs as the error ratio spikes:
promtool query instant http://localhost:9090 'cart:error_ratio:5m / 0.001'
# 22.0     <-- 22x burn over 5m

# the fast-burn alert goes from inactive -> pending -> firing:
curl -s http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | {name:.labels.alertname, state:.state}'
# { "name": "CartErrorBudgetFastBurn", "state": "firing" }
```

Then **stop the fault** and watch the alert *clear quickly* — because the 5-minute short window drops fast once the errors stop (the long-window-AND-short-window trick, Lecture 1 §3.3). Note how long it takes to clear; that responsiveness is the short window earning its place.

---

## Step 6 — Confirm the slow burn is NOT a false page

Induce a *small* steady error rate (e.g. 0.3% — above the 0.1% budget but well below the fast-burn threshold) and confirm: the **fast-burn page does NOT fire** (good — it's not a catastrophe), but over time the **slow-burn ticket** does (correct — a steady leak quietly eats the budget). This is the whole point of multi-window: the catastrophe pages, the leak tickets, neither false-fires on the other.

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] Three SLIs are defined as PromQL ratios (availability, latency, correctness), with the correctness gap noted if you don't emit it.
- [ ] The error budget is computed as both a time allowance and an event count for your real volume.
- [ ] The recording rules and both burn-rate alert rules pass `promtool check rules`.
- [ ] You induced an error spike and showed the **burn rate** climb and the **fast-burn alert fire**, then **clear quickly** when the fault stopped.
- [ ] You showed a small steady error rate fires the **slow-burn ticket** but NOT the fast-burn page.
- [ ] You can state why a static "error rate > 1%" alert is both too noisy and too blind compared to multi-window burn-rate.

---

## Stretch

- Route the two alerts differently in **Alertmanager**: fast-burn → a page receiver, slow-burn → a ticket receiver. Prove the routing with the induced spikes.
- Generate the rules with **Sloth** (`sloth generate`) from a one-line SLO spec and diff its output against your hand-written rules — see what the generator does that you didn't, and vice versa.
- Add a **burn-rate panel** to the Week 17 Grafana dashboard so the budget burn is visible next to the RED metrics. Reliability becomes something you *see*, not just alert on.

---

When this feels comfortable, move to [Exercise 2 — The circuit breaker](./exercise-02-circuit-breaker.go).
