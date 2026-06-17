# Week 7 Homework

Six problems that revisit the week's topics and force the Envoy and BFF literacy into your fingers. The full set should take about **5 hours**. Work in your Week 7 Git repository (the same workspace as the exercises and the `cart-edge` mini-project) so every problem produces at least one commit you can point to at the Phase 2 architecture review in Week 12.

The headline deliverable is **Problem 4 — the gateway-vs-mesh decision memo**, called out explicitly in the syllabus skills ("recognizing when a gateway is enough and a mesh is overkill"). Treat it as the artifact a staff engineer reads before deciding whether to fund a mesh rollout, not a journal entry.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

Have **Envoy** runnable (`func-e` or the container) and your **`cart`/`inventory`** services (or the Exercise 1 stubs) reachable. Problems 1, 2, 3, and 5 run against a live proxy.

---

## Problem 1 — The edge audit table

**Problem statement.** Stand up the Exercise 1 ingress (or your `cart-edge`). For **every** cluster in your config, run `curl -s localhost:9901/config_dump` and `curl -s localhost:9901/clusters` and record the actual loaded resilience config. Build a markdown table in `notes/week-07/edge-audit.md` with one row per cluster and these columns:

| Cluster | Upstream type | Timeout | Retry policy | Retry budget? | Outlier detection? | Circuit breakers? | Correct? |
|---|---|---|---|---|---|---|---|

The **Correct?** column is `yes`/`no` against the resilience checklist from Lecture 2 (every real-service cluster needs a budget, outlier detection, and circuit breakers), with a one-line reason where you wrote `no`.

**Acceptance criteria.**

- `notes/week-07/edge-audit.md` exists with one row per cluster (at least two: `cart`, `inventory`).
- Every row's values come from real admin-endpoint output, not from your YAML by memory (they can differ once xDS is involved).
- At least one cluster is marked `no` with a reason, or you explicitly argue every cluster is already correct and why.
- Committed.

**Hint.** Pipe it: `curl -s localhost:9901/config_dump | jq '.configs[] | select(."@type" | test("Cluster"))'` and read the `circuit_breakers` / `outlier_detection` blocks. A cluster with a `retry_policy` but no `retry_budget` is the row you mark `no` — it's a retry storm waiting to happen.

**Estimated time.** 40 minutes.

---

## Problem 2 — Prove the retry budget works

**Problem statement.** Take the Exercise 2 config. Run a flaky backend (returns ~2% 5xx) and drive load with `ghz`/`fortio`. Capture the stats with the budget **present** and with it **removed** (delete the `retry_budget` block). Compare the request amplification: the ratio of `cluster.cart.upstream_rq_total` to the number of requests your load generator actually sent.

**Acceptance criteria.**

- `notes/week-07/retry-budget.md` shows two runs (budget on / budget off) with the `upstream_rq_total`, `upstream_rq_retry`, and `upstream_rq_retry_limit_exceeded` counters for each.
- You compute the **amplification ratio** for both runs and show the budget keeps it bounded (near 1.x) while the budget-off run lets it climb under failure.
- You confirm `upstream_rq_retry_limit_exceeded` is non-zero in the budget-on run — proof the budget is refusing retries.
- Committed.

**Hint.** The amplification is the whole story. With the budget off and a high failure rate, Envoy sends the backend far more requests than the client sent — that excess is retries, and it's exactly what a storm is made of. The budget caps the excess.

**Estimated time.** 45 minutes.

---

## Problem 3 — The BFF degradation test

**Problem statement.** Take the Exercise 3 mobile BFF. Write a small test (shell or Go) that exercises three states: (a) both backends up, (b) inventory down, (c) cart down. Capture the BFF's response and HTTP status in each. Prove the degradation contract: (a) full screen with `stock_live:true`, (b) cart-only screen with `stock_live:false` and no `available` fields, (c) a 502/504 with no fabricated cart.

**Acceptance criteria.**

- `notes/week-07/bff-degradation.md` records the three states with the actual response bodies and status codes.
- You confirm the inventory-down case is a *degraded 200*, not an error — the screen still loads.
- You confirm the cart-down case is a *5xx*, not a half-empty 200 — the BFF doesn't lie about an empty cart.
- You note that the stock lookup is **one** batched call per screen (verify with a server-side log or `cluster.inventory.upstream_rq_total` rising by 1 per request, not by `len(lines)`).
- Committed.

**Hint.** To kill a backend cleanly mid-test, just stop its process; the gRPC client will return `Unavailable`, which your degrade path catches for inventory and your error path surfaces for cart. The pointer-to-`available` trick (Exercise 3) is what makes the field omit cleanly in JSON when degraded.

**Estimated time.** 50 minutes.

---

## Problem 4 — The gateway-vs-mesh decision memo (headline deliverable)

**Problem statement.** This is the syllabus deliverable. Write a one-to-two-page memo at `notes/week-07/gateway-vs-mesh-memo.md` advising a specific (hypothetical) org whether to adopt a service mesh or stay with a gateway-plus-libraries approach. Pick **one** of these orgs and state which:

- **Org A:** 6 services, 2 teams, all in one cluster, mostly internal gRPC, growing slowly.
- **Org B:** 80 services, 15 teams, multi-cluster, a mix of gRPC/HTTP, a hard compliance requirement for mTLS on every internal hop.

Your memo must hit these headings:

1. **Recommendation** — one sentence: mesh or no mesh, for the chosen org.
2. **The traffic split** — what north-south vs east-west looks like for this org, and which problems each tier has.
3. **What the mesh buys** — the specific capabilities (uniform mTLS, per-hop retries/telemetry without per-team work) and *why they matter for this org*.
4. **What the mesh costs** — the sidecar tax (memory, latency, ops surface, the control plane), quantified as best you can.
5. **The decision** — tie the cost to the org's scale. For Org A, the honest answer is usually "a gateway plus a shared resilience library; a mesh is overkill." For Org B, it's usually "a mesh, because uniform mTLS across 15 teams is otherwise 15 chances to get it wrong."
6. **The migration path** — if you recommend a mesh, how you'd roll it in incrementally (and why a big-bang cutover is a mistake).

**Acceptance criteria.**

- `notes/week-07/gateway-vs-mesh-memo.md` exists, fits on roughly one-to-two pages (600–1000 words), and hits all six headings.
- The recommendation is **specific to the chosen org's scale**, not a generic "it depends."
- The cost section names the sidecar tax concretely (memory per pod, per-hop latency, control-plane ops), not "meshes are complex."
- The memo would let a staff engineer make the funding decision without asking you a follow-up question.
- Committed.

**Hint.** The strongest memos commit to a position and defend it against the obvious counter-argument. For Org A, the counter is "but everyone uses a mesh" — answer it (cargo-culting a mesh onto 6 services is how you get a control plane nobody can operate). For Org B, the counter is "the sidecar tax is too high" — answer it (at 80 services the cost of *not* having uniform mTLS is a compliance finding). This memo is exactly the conversation you'll have at the Phase 2 review; rehearse it.

**Estimated time.** 1 hour.

---

## Problem 5 — Force the circuit breaker open

**Problem statement.** Using your Exercise 2 / `cart-edge` config, deliberately drive concurrency past the cluster's `max_requests` / `max_pending_requests` thresholds and capture the circuit breaker opening. Show that the proxy fails *fast* (immediate 503) rather than queuing, and explain why fail-fast is gentler on a struggling backend than queuing would be.

**Acceptance criteria.**

- `notes/week-07/circuit-breaker.md` shows `cluster.cart.circuit_breakers.default.rq_open` flipping to 1 and `upstream_rq_pending_overflow` climbing under high concurrency.
- You capture the client-side experience: requests over the limit get a fast 503, not a slow timeout.
- You explain in two-to-three sentences why a fast 503 protects the backend better than letting the request queue (queuing adds load the backend has to absorb; failing fast sheds it).
- Committed.

**Hint.** Push concurrency, not just rate: `ghz -c 2048` (2048 concurrent) against a cluster with `max_requests: 512` will open the breaker. The `pending_overflow` counter is the tell — requests rejected because the pending queue was full.

**Estimated time.** 35 minutes.

---

## Problem 6 — Route a canary by weight

**Problem statement.** Add a second cluster `cart_v2` (point it at a second copy of the cart stub) and a **weighted route** that sends 90% of traffic to `cart` and 10% to `cart_v2`. Drive traffic and prove the split from the per-cluster `upstream_rq_total` counters. Then shift to 50/50, then 0/100, with a config reload each time, and capture the counters at each stage. You've just built progressive delivery by hand — which Week 8 does with an Istio `VirtualService`.

**Acceptance criteria.**

- `notes/week-07/weighted-canary.md` shows the three stages (90/10, 50/50, 0/100) with the `cluster.cart.upstream_rq_total` vs `cluster.cart_v2.upstream_rq_total` ratios at each, matching the configured weights within sampling noise.
- You note one sentence on what's *missing* from this hand-rolled canary that a mesh adds (automatic rollback on an SLO breach, which Week 8's progressive delivery provides).
- Committed.

**Hint.** Use `weighted_clusters` in the `route` action (Lecture 1 §2.3). The ratios won't be exactly 90/10 over a few hundred requests — that's sampling, not a bug; drive enough load (a few thousand requests) that the ratio converges.

**Estimated time.** 30 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 — Edge audit table | 40 min |
| 2 — Prove the retry budget | 45 min |
| 3 — BFF degradation test | 50 min |
| 4 — Gateway-vs-mesh memo (headline) | 1 h 0 min |
| 5 — Force the circuit breaker open | 35 min |
| 6 — Route a canary by weight | 30 min |
| **Total** | **~5 h 0 min** |

When you've finished all six, push your repo and make sure the `cart-edge` [mini-project](./07-mini-project/00-overview.md) is in the same workspace — Week 8 sits the Istio mesh behind exactly this edge. Then take the [quiz](./05-quiz.md) with your notes closed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Edge audit (P1)** | 15 | One row per cluster from real admin output; the budget-less cluster correctly flagged. |
| **Retry budget proof (P2)** | 20 | Two runs; amplification ratio computed; `retry_limit_exceeded` non-zero with the budget on. |
| **BFF degradation (P3)** | 20 | All three states captured; degraded-200 vs error-5xx distinction correct; one batched stock call confirmed. |
| **Gateway-vs-mesh memo (P4)** | 25 | Specific recommendation tied to the org's scale; sidecar tax quantified; counter-argument addressed; staff-ready. |
| **Circuit breaker (P5)** | 10 | Breaker opens; fail-fast vs queuing explained correctly. |
| **Weighted canary (P6)** | 10 | Three stages match configured weights; the missing-rollback note present. |

**90+** is portfolio-grade. **70–89** is solid but the memo likely hedges instead of committing. **Below 70** usually means Problem 2 or 4 was treated as a formality — they're the two that prove you understand *why* the edge exists, not just how to configure it.
