# Week 18 Homework

Six problems that revisit the week's topics and force the reliability literacy into your fingers. The full set should take about **5 hours**. Work in your Week 18 Git repository (the same workspace as the exercises and the `cart-reliable` mini-project) so every problem produces at least one commit you can point to at the Phase 3 review and the capstone defense.

The headline deliverable is **Problem 4 — the error-budget-policy memo**, the document a team and its product partner sign so the reliability-vs-velocity decision is made in the calm and enforced in the storm. Treat it as a governance document, not a journal entry.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

Have the **Week 17 stack** running and your **cart topology** with a **payment dependency** and a **Kafka consumer**. Problems 1–3 and 5–6 run against the live system.

---

## Problem 1 — The SLO document

**Problem statement.** Write a real SLO document for the cart system at `notes/week-18/slo-document.md`. Define three SLIs (availability, latency, correctness) as PromQL, set an SLO for each over a 28-day window, and compute the error budget for each as **both** a time allowance and an event count for your *actual* request volume. Justify each SLO against the dependency chain (the weakest-link cap).

**Acceptance criteria.**

- `notes/week-18/slo-document.md` has three SLIs as PromQL, three SLOs, and budgets in time and events for your real volume.
- The latency SLI uses an SLO-aligned histogram bucket (from Week 17); the correctness SLI is app-level (the mesh can't provide it) — note the gap if you don't emit it yet.
- Each SLO is justified against its dependency chain (you can't be more reliable than the product of your dependencies).
- Committed.

**Hint.** Pull your real volume with `sum(increase(http_server_requests_total{service="cart"}[28d]))` and multiply by (1 − SLO) for the event budget. For the weakest-link math: if cart depends on payment (99.9%) and inventory (99.9%), cart's ceiling is ~99.8% — so a 99.99% cart SLO is physically impossible; document that.

**Estimated time.** 45 minutes.

---

## Problem 2 — Burn-rate alerts that fire correctly

**Problem statement.** Write the recording rules and the multi-window multi-burn-rate alert rules for your availability SLO, then *prove they fire correctly*: induce an error spike and show the fast-burn page fires and clears quickly; induce a small steady leak and show the slow-burn ticket fires but the page does *not*. Capture both.

**Acceptance criteria.**

- `notes/week-18/burn-rate.md` includes the recording + alert rules (passing `promtool check rules`) and the evidence: fast-burn fires-then-clears on a spike, slow-burn fires (not the page) on a leak.
- You capture the burn-rate value (`error_ratio / budget`) at the moment each alert fires.
- You state in one sentence why a static "error rate > X%" alert fails at both ends (noise + blindness).
- Committed.

**Hint.** Induce the spike with a Week 8 fault-injection VirtualService (abort N% of cart) or a broken deploy. For the slow leak, abort a *small* steady percentage (e.g. 0.3%) — above budget but below the fast threshold. Note how *fast the fast-burn clears* once you stop the fault: that's the short window earning its place.

**Estimated time.** 50 minutes.

---

## Problem 3 — The circuit breaker around payment

**Problem statement.** Using Exercise 2 (or your real payment client), wrap the payment dependency in a circuit breaker + timeout + jittered, budgeted retry. Drive payment to failure and capture the breaker *opening* (fail-fast count climbing, slow-failures stopping), then capture it *recovering* through half-open when payment heals. Quantify the protection: how much faster does cart fail when the breaker is open versus when it's hanging on timeouts?

**Acceptance criteria.**

- `notes/week-18/circuit-breaker.md` shows the breaker going closed → open → half-open → closed across a fault, with the state transitions captured.
- You show the fail-fast latency (breaker open) versus the hang latency (no breaker, waiting on the timeout) — the concrete protection.
- Your retries are jittered (full jitter) and budgeted; you confirm retries stayed a small fraction of calls under widespread failure.
- Committed.

**Hint.** The protection is the latency difference: with the breaker open, a call to dead payment returns in microseconds (rejected without trying); without it, every call burns the full timeout (e.g. 200 ms) before failing. At high call volume that's the difference between cart staying up and cart's threads piling up on dead payment.

**Estimated time.** 45 minutes.

---

## Problem 4 — The error-budget-policy memo (headline deliverable)

**Problem statement.** This is the syllabus skill ("defend an error budget against product pressure"). Write a one-to-two-page **error-budget policy** at `notes/week-18/error-budget-policy.md` — the document engineering and product *both sign* so that, when the budget is spent, the decision to slow down is already made. It must read as a governance document a real team would adopt.

Your memo must hit these headings:

1. **The SLO and budget** — the cart availability SLO, the budget, and what spending it means.
2. **What the budget buys** — the velocity/risk it permits while there's budget left (risky deploys, chaos drills, experiments).
3. **The policy when the budget is spent** — the concrete, pre-agreed consequence (feature freeze, reliability-only work until recovery), and who can override it and how.
4. **The defense against "make it 100%"** — the cost curve (each nine is exponential) and the weakest-link cap, as the argument you'd give product.
5. **The defense against an over-tight SLO** — why setting it too high (always-zero budget → permanent freeze → never ship) is as broken as no SLO, and how you calibrate to genuine user need.
6. **Sign-off** — who signs (eng lead, product lead) and when it's reviewed.

**Acceptance criteria.**

- `notes/week-18/error-budget-policy.md` exists, fits ~one-to-two pages (600–1000 words), and hits all six headings.
- The policy specifies a *concrete* consequence when the budget is spent (not "we'll discuss it").
- Both the "100% is wrong" and the "over-tight is also wrong" arguments are made — the policy defends the budget from *both* directions.
- It reads as something a team and product would actually sign, not an essay.
- Committed.

**Hint.** The strongest policies are specific and pre-committed: "while the cart error budget is exhausted, no new features ship to cart; the on-call and one engineer work reliability until the 28-day SLI recovers above target; product may request a one-time exception in writing, logged." Specificity is what makes the policy enforceable in the storm — vague policies get relitigated under pressure, which defeats the purpose.

**Estimated time.** 1 hour.

---

## Problem 5 — KEDA on lag vs HPA on CPU

**Problem statement.** Using Exercise 3, deploy KEDA scaling the consumer on Kafka lag. Create a burst of lag and capture replicas scaling up roughly as ceil(lag / threshold), then draining and scaling down. Then deploy the CPU-HPA contrast and show it does *not* scale under the same burst (CPU stays low while lag explodes). Quantify the difference in backlog drain time.

**Acceptance criteria.**

- `notes/week-18/keda.md` shows the KEDA ScaledObject scaling on lag under a burst (replicas up, then down after cooldown), with the lag and replica counts captured.
- You show the CPU-HPA holding at min replicas under the same burst, with CPU staying low — the "wrong signal" proof.
- You note the cold-start and flapping tradeoffs and how stabilization windows address flapping.
- Committed.

**Hint.** Generate lag by flooding the topic faster than one replica drains (`kafka-producer-perf-test` or your producer in a loop). Watch both `kubectl get hpa -w` and the consumer-group lag. The CPU HPA's failure is the lesson: it never knew you were falling behind because falling-behind doesn't show up as CPU.

**Estimated time.** 40 minutes.

---

## Problem 6 — Find the saturation point (honestly)

**Problem statement.** Load-test the cart system at *rising* concurrency to find its saturation point — where throughput crests and falls (the USL peak) — measured honestly (open-loop, no coordinated omission). Produce a curve and name the bottleneck.

**Acceptance criteria.**

- `notes/week-18/saturation.md` has a throughput-vs-concurrency table/curve at increasing load (e.g. 1→200 VUs), with p50/p99/p99.9 at each level.
- The load test is **open-loop** (fixed arrival rate, not loop-and-wait) — state how you avoided coordinated omission and why it matters for the tail numbers.
- You identify the concurrency where throughput peaks and past which it *falls*, and name the likely bottleneck (the lock? the DB? a connection pool?).
- You state the autoscaling cap you'd set so you never push past the peak into the falling region.
- Committed.

**Hint.** Use `k6` with a ramping-arrival-rate executor (open-loop) rather than ramping VUs that wait for responses. Watch for the tell-tale USL shape: throughput rises, flattens, then *declines* as concurrency climbs, while p99/p99.9 climb steeply. The peak is your scalability ceiling; past it, adding load (or pods) makes things worse, which is the one place autoscaling hurts.

**Estimated time.** 40 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 — SLO document | 45 min |
| 2 — Burn-rate alerts | 50 min |
| 3 — Circuit breaker | 45 min |
| 4 — Error-budget-policy memo (headline) | 1 h 0 min |
| 5 — KEDA on lag vs HPA on CPU | 40 min |
| 6 — Find the saturation point | 40 min |
| **Total** | **~5 h 0 min** |

When you've finished all six, push your repo and make sure the `cart-reliable` [mini-project](./mini-project/README.md) is in the same workspace — Phase 4 (Week 19's region failover, Week 22's gameday) stress-tests exactly these SLOs and patterns. Then take the [quiz](./quiz.md) with your notes closed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **SLO document (P1)** | 15 | Three covering SLIs; budgets in time + events; the weakest-link justification. |
| **Burn-rate alerts (P2)** | 15 | Rules pass `promtool`; fast-burn fires-and-clears; slow-burn fires without false-paging. |
| **Circuit breaker (P3)** | 15 | Open/half-open/closed across a fault; jittered + budgeted retries; the fail-fast latency win quantified. |
| **Error-budget-policy memo (P4)** | 25 | All six headings; a concrete pre-committed consequence; defends the budget from both "make it 100%" and "over-tight"; signable. |
| **KEDA vs HPA (P5)** | 15 | Lag scaling demonstrated; CPU-HPA contrast shown to fail; flapping/cold-start noted. |
| **Saturation point (P6)** | 15 | Open-loop measurement; the peak found; honest tail-latency; bottleneck named + autoscaling cap. |

**90+** is portfolio-grade. **70–89** is solid but the policy memo likely lacks a concrete consequence or hedges the 100% defense, or the saturation test was run closed-loop (a tail-latency lie). **Below 70** usually means Problem 2 or 4 was treated as a formality — they're the two that prove you can *measure* reliability and *govern* it, which is the whole difference between hoping a system is reliable and defending that it is.
