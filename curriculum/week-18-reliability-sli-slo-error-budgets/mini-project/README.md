# Mini-Project — `cart-reliable`: SLOs, Error Budgets, and the Patterns That Defend Them

> Make the cart system *provably* reliable: three SLIs with SLOs and computed error budgets, multi-window multi-burn-rate alerts that page on a catastrophe and ticket on a simmer, the named resilience patterns (circuit breaker, timeout, jittered+budgeted retry, bulkhead, load shedding) protecting the dependency paths, KEDA autoscaling the Kafka consumer on lag, and a *measured* saturation point so you know where the system breaks before production finds out.

This is the artifact that turns "I think it's reliable" into "here's the budget, here's the burn rate, here's the saturation point, and here's what keeps us inside it." After this week, reliability is a *defensible posture*: a number you can query, alerts that fire correctly, patterns that contain failures, and a known ceiling. When someone asks "is the cart system reliable enough?" you answer with the error budget and the burn rate — not an opinion — and when they say "make it 100%," you answer with the cost curve and the weakest-dependency cap.

**Estimated time:** ~12 hours, split across Thursday, Friday, and Saturday in the suggested schedule.

**Compounds forward:** This `cart-reliable` posture is the reliability layer of your **capstone Polyglot Marketplace Backbone**, and it's what Phase 4 stress-tests. The SLOs you define here are the *contract* the Week 19 region-failover must honor ("did we stay inside the latency/availability budget during the region loss?"). Week 22's gameday deliberately triggers the very failures these patterns defend against — a payment blip, a broker loss, a latency injection — and grades whether your system *storms* or *shrugs*. The capstone's "automatic rollback on SLO breach" is the burn-rate alert from this week wired to a deploy gate. Build it cleanly: this is the week that decides whether your capstone survives Phase 4's chaos or becomes its first incident.

---

## What you will build

A repo `cart-reliable` with five deliverables:

1. **`slo/`** — the **SLO document**: three SLIs (availability, latency, correctness) as PromQL, their SLOs, the computed error budgets (time and events), and a written **error-budget policy** (what the team does when the budget is spent). The contract.
2. **`alerts/`** — the Prometheus **recording rules** (per-window error ratios) and **multi-window multi-burn-rate alert rules** (fast-burn page, slow-burn ticket), checked with `promtool` and proven to fire correctly on induced spikes.
3. **`patterns/`** — the resilience patterns in code: a **circuit breaker** + **timeout** + **jittered, budgeted retry** around the payment dependency (Exercise 2), a **bulkhead** isolating the payment/inventory/shipping pools, and **load shedding / admission control** in front of cart that sheds the marginal request to hold p99 under overload.
4. **`autoscale/`** — **KEDA** scaling the `order.placed.v1` consumer on Kafka lag (Exercise 3), with the HPA-on-CPU contrast and the anti-flap stabilization windows, and a documented cold-start/scale-to-zero decision.
5. **`saturation/`** — the **saturation-point measurement**: a `k6` load test at *rising* concurrency that finds where throughput crests and falls (the USL peak), measured with honest tail-latency (HDR / open-loop, no coordinated omission), plus a `SATURATION.md` with the numbers, the fitted α/β, and the named ceiling.

By the end you have a public repo with an SLO contract, working burn-rate alerts, the resilience patterns, lag-based autoscaling, and a measured scalability ceiling — everything needed to defend the cart system's reliability with evidence.

---

## Why this and not "just add retries and an autoscaler"

You could sprinkle retries and an HPA and call the system "reliable." Don't stop there — that's the gap this whole week is about, and (as the challenge shows) naive retries plus a missing breaker is how you *cause* the outage you were trying to prevent. A defensible reliability posture gives you:

- **A reliability number you can query**, not a feeling. The error budget and burn rate turn "is it reliable?" into "how much budget, burning how fast?" — a question the data answers.
- **Alerts that page correctly**, not a wall of noise. Multi-window burn-rate pages on the catastrophe and tickets on the simmer, so on-call trusts the pager instead of ignoring it.
- **Failures that stay contained**, not cascades. The circuit breaker + bulkhead + jittered/budgeted retry are what keep one dependency's blip from becoming a system-wide storm (the challenge made this visceral).
- **A known ceiling**, not a surprise. The measured saturation point tells you where adding load *hurts*, so you cap autoscaling there instead of pouring workers onto a contention fire.

The managed platforms and the mesh give you some of this. Building the SLO math and the patterns by hand first is what lets you read, trust, and right-size what they provide — and what lets you *defend* the system in a staff review, which is the capstone's whole point.

---

## Repo layout

```
cart-reliable/
├── README.md
├── slo/
│   ├── slo-document.md          # 3 SLIs + SLOs + computed budgets + error-budget policy
│   └── slis.promql              # the SLI queries (availability, latency, correctness)
├── alerts/
│   ├── recording-rules.yml      # per-window error ratios (precomputed)
│   └── burn-rate-alerts.yml     # multi-window multi-burn-rate (page + ticket)
├── patterns/
│   ├── breaker.go               # circuit breaker + timeout + jittered/budgeted retry (payment)
│   ├── bulkhead.go              # isolated per-dependency pools
│   └── load-shed.go             # admission control / load shedding in front of cart
├── autoscale/
│   ├── keda-scaledobject.yaml   # consumer scales on Kafka lag
│   └── hpa-cpu-contrast.yaml    # the CPU HPA that does NOT scale on lag (the lesson)
└── saturation/
    ├── load-test.js             # k6 at rising concurrency, open-loop (no coordinated omission)
    └── SATURATION.md            # the curve, the USL peak, the tail-latency numbers
```

---

## Deliverable 1 — `slo/` (the contract)

The SLO document: three SLIs covering each other's blind spots (availability from the mesh/app, latency from the SLO-aligned histogram bucket, correctness from an app-emitted signal the mesh *can't* see), each with an SLO over a 28-day window, each budget computed as both a time allowance and an event count for your real volume. Plus the **error-budget policy** — the pre-agreed rule for when the budget is spent (freeze features, stabilize) — written as if engineering and product both signed it, because that's the point: the decision is made in the calm, enforced in the storm.

> **The rule the audit enforces:** the SLO must be *defensible*, not a vanity number. An SLO of 99.999% on a service sitting on 99.9% dependencies is physically impossible (the weakest-link cap) and self-defeating (the budget is always zero, so the team never ships). Document the dependency-chain math that justifies your SLO.

---

## Deliverable 2 — `alerts/` (the burn-rate alerts)

The recording rules (per-window error ratios, precomputed) and the multi-window multi-burn-rate alerts (fast-burn page at 14.4× over 1h-and-5m; slow-burn ticket at 6× over 6h-and-30m). Both pass `promtool check rules`. Demonstrate in the README: an induced spike fires the fast-burn page *and clears quickly*; a small steady leak fires the slow-burn ticket but *not* the page. The proof that the alerts have both precision and recall.

---

## Deliverable 3 — `patterns/` (the defenses)

The resilience patterns protecting the dependency paths:

- **`breaker.go`** — circuit breaker (closed/open/half-open) + timeout + **full-jitter, budgeted** retry around payment. Must demonstrably open under failure (fail fast) and recover via half-open. (This is the direct defense against the challenge's retry storm.)
- **`bulkhead.go`** — separate bounded pools for payment/inventory/shipping, so one hung dependency can't starve the calls to the healthy ones.
- **`load-shed.go`** — admission control in front of cart that sheds the marginal request (by criticality: keep checkout, drop recommendations) to hold p99 under overload instead of letting latency collapse.

Each pattern's comment must name the *failure it prevents* — the pattern is only meaningful as the answer to a specific failure mode.

---

## Deliverable 4 — `autoscale/` (lag-based scaling)

KEDA scaling the consumer on Kafka lag (the right signal — a consumer falling behind shows in lag, not CPU), with anti-flap stabilization windows and a documented scale-to-zero decision. Include the CPU-HPA contrast and *demonstrate* it fails to scale under a lag burst — the "why lag, not CPU" proof made concrete.

---

## Deliverable 5 — `saturation/` (the measured ceiling)

The deliverable that separates this from a checklist. A `k6` load test at *rising* concurrency that finds the saturation point:

1. Run at increasing concurrency (e.g. 1, 2, 5, 10, 20, 50, 100, 200 VUs), **open-loop** (fixed arrival rate, not loop-and-wait) so you don't suffer coordinated omission.
2. Record throughput and p50/p99/p99.9 at each level. Find where **throughput crests and then falls** — the USL peak.
3. Fit (roughly) the USL `N / (1 + α(N−1) + βN(N−1))` to identify the contention (α) and coherency (β) costs.
4. Write `SATURATION.md`: the throughput-vs-concurrency curve, the peak, the tail-latency at the peak, and the named bottleneck (the lock? the DB? the connection pool?) — and the cap you'd set on autoscaling so you never push *past* the peak into the falling region.

"Our cart system peaks at ~N concurrent and *gets slower* past it because of contention on the payment connection pool" is the sentence that turns capacity from a guess into a number — and it's exactly what the capstone's capacity memo (Week 23) needs.

---

## Rules

- **You may** read the Google SRE books, the resilience-library docs, and the lecture notes.
- **You must not** declare the system "reliable" without a *queryable* error budget and *working* burn-rate alerts. The audit checks the budget burns and the alert fires; a posture that can't be queried isn't a posture.
- **You must not** ship retries without **jitter and a budget**, or a dependency call without a **timeout** — the challenge shows exactly why those are the difference between resilience and a self-inflicted outage.
- **You must not** report a saturation point you didn't measure open-loop. Coordinated omission makes the tail a lie; the measurement must be honest.
- **You must not** set a vanity SLO the dependency chain can't support — document the weakest-link math.
- Go (patterns), PromQL/`promtool` (SLOs/alerts), KEDA, `k6`, the Week 17 stack. Everything runs locally.
- The alerts and the saturation test must be reproducible from the repo.

---

## Acceptance criteria

- [ ] A public GitHub repo named `c22-week-18-cart-reliable-<yourhandle>`.
- [ ] `slo/slo-document.md` has three SLIs/SLOs, computed budgets (time + events), an error-budget policy, and the weakest-link math justifying the SLO.
- [ ] `alerts/` rules pass `promtool check rules`; the fast-burn page fires and clears quickly on a spike; the slow-burn ticket fires (not the page) on a small steady leak — demonstrated.
- [ ] `patterns/breaker.go` opens under failure (fail fast) and recovers via half-open; retries are jittered and budgeted; every dependency call has a timeout.
- [ ] `patterns/` also includes a bulkhead and load-shedding/admission-control, each naming the failure it prevents.
- [ ] `autoscale/` scales the consumer on Kafka lag (KEDA), with the CPU-HPA contrast demonstrated and anti-flap configured.
- [ ] `saturation/SATURATION.md` has a measured throughput-vs-concurrency curve, the USL peak, honest tail-latency (open-loop), and the named bottleneck + autoscaling cap.
- [ ] A `README.md` that defends the SLO against "make it 100%" (cost curve + weakest link) in a paragraph.
- [ ] Committed and pushed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **SLO document & error budget** | 20 | Three covering SLIs; budgets computed (time + events); a real error-budget policy; weakest-link math; defensible (not vanity) SLO. |
| **Burn-rate alerting** | 20 | Recording rules + multi-window alerts pass `promtool`; fast-burn pages and clears fast; slow-burn tickets without false-paging. |
| **Resilience patterns** | 25 | Breaker opens/recovers; retries jittered + budgeted; timeouts everywhere; bulkhead + load-shedding present; each names the failure it prevents. |
| **Autoscaling** | 15 | KEDA scales on lag; CPU-HPA contrast demonstrated; anti-flap; scale-to-zero decision documented. |
| **Saturation measurement** | 15 | Open-loop load test (no coordinated omission); throughput peak found; honest tail-latency; named bottleneck + autoscaling cap. |
| **Defense & docs** | 5 | Clear README; the "100% is wrong" argument made with the cost curve and the weakest link; no secrets checked in. |

**90+** is portfolio-grade and ready to be the capstone's reliability layer and survive Phase 4's chaos. **70–89** works but likely sets a vanity SLO, or ships retries without jitter/budget (a storm waiting to happen), or reports a saturation point measured closed-loop (a tail-latency lie). **Below 70** usually means the error budget isn't queryable or the patterns don't actually fire — fix those first; they're the two things this week exists to deliver.

---

## Stretch goals

- **Error-budget deploy gate.** A CI check that blocks a deploy when the budget is exhausted — the error-budget policy, automated. This is the capstone's "don't ship when you're out of budget," generalized.
- **Adaptive concurrency.** Replace the static load-shed limit with a Little's-law-derived adaptive concurrency limit (Netflix concurrency-limits style) that finds and holds the right in-flight count automatically, and show it holds p99 under overload where the static limit doesn't.
- **Alertmanager routing.** Wire the fast-burn page to an urgent receiver and the slow-burn ticket to a tracking receiver, and prove the routing on induced spikes.
- **USL fit.** Actually fit the USL curve to your measured data and report α and β with confidence — then identify *which* of contention or coherency dominates your ceiling, and what you'd change to raise it.

---

## Common pitfalls (read before you start)

The failures that sink this project are predictable. Front-load them:

- **A vanity SLO.** Setting 99.99% because it "sounds reliable" when your dependencies cap you at 99.8%. The budget is then always zero, the team is always frozen, and the number is a lie. Compute the weakest-link ceiling *first*, then set the SLO below it with real budget to spare.

- **Retries without jitter or a budget.** The single most common way to *cause* the outage you meant to prevent (see the challenge). If you add retries anywhere, they must be full-jittered and budgeted — no exceptions.

- **A dependency call with no timeout.** An unbounded wait is a latent thread-pool exhaustion. Grep your code for every outbound call and confirm each has a timeout derived from *your* SLO, not the callee's hope.

- **Closed-loop load testing.** Measuring the saturation point with a loop-and-wait tester gives you a tail-latency number that's a fiction (coordinated omission). Use an open-loop, fixed-arrival-rate test or your `SATURATION.md` is worthless.

- **Alerting on causes, not the SLO.** A wall of "CPU > 80%" / "pod restarted" alerts trains the team to ignore the pager. Alert on the budget burn (the user-facing symptom); monitor the causes on dashboards.

- **An audit that checks presence, not enforcement.** "We have an AuthorizationPolicy / a circuit breaker / an SLO" is not the same as "it actually denies / opens / burns." Every check must assert the *behavior*, and fail when the posture is weakened.

- **Autoscaling on the wrong signal.** Scaling a Kafka consumer on CPU instead of lag — it never knows it's falling behind. Match the scaling signal to what "behind" actually means for the workload.

- **No load-shedding backstop.** Relying on autoscaling alone leaves a latency cliff during the seconds it takes new pods to start; shed the marginal request to cover that gap.

## The demonstration script (what you'll show at review)

A reliability posture is only convincing if you can *show* it working under failure. Build a short, repeatable demo — five minutes — that a reviewer (or your future self) can run to see each guarantee fire. This is also the spine of the capstone's reliability demo, so build it once and reuse it.

1. **The budget is queryable.** Open the burn-rate panel; show the current error budget remaining and the burn rate at rest (near 1× or below). State the SLO and what spending the budget means.
2. **The fast-burn alert fires and clears.** Inject a 20% error fault into cart (Week 8 fault injection). Within ~2 minutes the fast-burn page fires; the burn rate panel spikes. Stop the fault; the alert clears within ~5 minutes (the short window). This proves precision *and* responsiveness.
3. **The circuit breaker contains a dependency failure.** Blip payment to 80% failure. Show the breaker opening (fail-fast latency drops to microseconds), cart staying *up* and degrading cleanly instead of hanging, then the breaker recovering through half-open when payment heals. Contrast with the breaker disabled (cart's threads pile up on timeouts).
4. **Retries don't storm.** With the breaker and jitter/budget in place, repeat the blip and show payment's request rate *not* spiking on recovery — the herd is de-synchronized and the budget capped the retries. (This is the challenge's lesson, demonstrated as a guarantee.)
5. **Lag-based autoscaling catches up.** Flood `order.placed.v1`; show KEDA scaling the consumer up on lag, the backlog draining, then scaling down. Contrast with the CPU HPA holding flat under the same burst.
6. **The saturation point is known.** Show the `SATURATION.md` curve and name the ceiling: "we peak at ~N concurrent; past it throughput falls because of contention on X; autoscaling is capped there."

If all six run cleanly from the repo, you have a *demonstrable* reliability posture — the difference between claiming the system is reliable and showing a reviewer it survives the exact failures it's designed for. Record it; the capstone wants a version of this.

## How this connects to the rest of C22

- **Week 17 (`cart-observed`)** is the foundation — every SLI is a PromQL query over its metrics; the burn-rate alerts run on its Prometheus/Thanos. This week literally cannot run without last week's stack.
- **Week 8 (the mesh)** gives you mesh-level retries/timeouts/outlier-detection as a backstop; this week adds the app-level patterns with finer control, and the mesh's `istio_requests_total` is a ready-made availability SLI source.
- **Week 19 (multi-region)** uses these SLOs as the failover contract — "stay inside the budget during a region loss."
- **Week 22 (gameday)** deliberately triggers the failures these patterns defend against and grades whether the system storms or shrugs.
- **Phase 4 (capstone)** deploys `cart-reliable` as the reliability layer; "automatic rollback on SLO breach" is this week's burn-rate alert wired to a deploy gate.

When you've finished, push the repo and take the [quiz](../quiz.md).
