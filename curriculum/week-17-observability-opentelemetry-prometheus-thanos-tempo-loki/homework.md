# Week 17 Homework

Six problems that revisit the week's topics and force the observability literacy into your fingers. The full set should take about **5 hours**. Work in your Week 17 Git repository (the same workspace as the exercises and the `cart-observed` mini-project) so every problem produces at least one commit you can point to at the Phase 3 review.

The headline deliverable is **Problem 4 — the RED dashboard with exemplars and the trace-to-log jump**, the artifact that proves your three signals actually correlate. Treat it as the thing you'd demo to prove the stack works, not a screenshot you fake.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

Have the **observability stack** running on Kind (Exercises 1–2) and your **cart topology** instrumented and producing traffic. All six problems run against the live stack.

---

## Problem 1 — The signal-coverage audit table

**Problem statement.** Bring up your instrumented cart topology. For **every** service in it, capture which of the three signals it actually emits — not which it's "supposed to." Build a markdown table in `notes/week-17/signal-coverage.md` with one row per service and these columns:

| Service | `service.name` correct? | Traces in Tempo? | RED metrics in Prometheus? | Logs in Loki (w/ trace_id)? | Propagator installed? |
|---|---|---|---|---|---|

The last column matters most: a service that emits its own traces but doesn't propagate context is a service whose traces never join the others. Mark any gap and note the one-line fix.

**Acceptance criteria.**

- `notes/week-17/signal-coverage.md` exists with one row per service (at least `cart`, `inventory`, and one async consumer).
- Every column comes from *querying the backend* (a Tempo search, a Prometheus query, a `logcli` query), not from reading the SDK config.
- At least one gap is flagged with its fix, or you explicitly argue every service is fully covered and show the evidence.
- Committed.

**Hint.** The fastest check for "does this service propagate" is to look at a trace that should cross it: if the downstream span is a *root* instead of a child, propagation is broken at the boundary above it. A `service.name` of `unknown_service` in Tempo is an instant `no`.

**Estimated time.** 40 minutes.

---

## Problem 2 — Prove the trace survives Kafka

**Problem statement.** Using the Exercise 3 script (or your own producer/consumer), demonstrate the difference between a trace that survives the Kafka boundary and one that splits. Produce an `order.placed.v1` event *with* context propagation and capture that the producer and consumer share one trace ID (and Tempo shows one two-span trace). Then run *without* propagation and capture the split (two different trace IDs).

**Acceptance criteria.**

- `notes/week-17/kafka-trace.md` shows the propagated case (same trace ID, one trace in Tempo with both spans) and the broken case (two different trace IDs).
- You quote the `traceparent` header present on the message in the working case and absent in the broken case.
- You state in one sentence why HTTP/gRPC don't need this manual step but Kafka does.
- Committed.

**Hint.** Confirm the join in Tempo with `curl -s "$TEMPO/api/traces/<id>" | jq '[.batches[].scopeSpans[].spans[].name]'` — you want both `publish ...` and `process ...` in one trace. The broken case returns each span in its own single-span trace.

**Estimated time.** 45 minutes.

---

## Problem 3 — RED PromQL and the histogram-bucket trap

**Problem statement.** Write the three RED queries (rate, error ratio, p99 from histogram) for `cart` against Thanos Query, and capture their output under load. Then *demonstrate the bucket trap*: with the library-default buckets, show that your p99 lands in a wide bucket and is therefore imprecise; re-instrument with SLO-aligned buckets (dense around your p99) and show the p99 becomes meaningful. Quote both.

**Acceptance criteria.**

- `notes/week-17/red-promql.md` records the three RED queries and their values under a `k6`/`fortio` load.
- You show the p99 with default buckets (and identify the wide bucket it falls in) versus SLO-aligned buckets, with a one-line explanation of why the first is a guess.
- The error-ratio query is the SLI shape (`bad / total`), which you'll reuse next week.
- Committed.

**Hint.** Inspect the `_bucket` series directly (`http_..._bucket` with the `le` label) to see where your p99 lands. If consecutive `le` boundaries straddle a large range around the p99 (e.g. `le="0.1"` then `le="1"`), every p99 in that gap is interpolated — the value moves continuously but the truth is unknown. Align boundaries to your SLO threshold.

**Estimated time.** 50 minutes.

---

## Problem 4 — The RED dashboard with exemplars and the trace-to-log jump (headline deliverable)

**Problem statement.** Build the syllabus's signature deliverable: a Grafana RED dashboard for the cart topology where the latency panel renders **exemplars**, and a span links to its **logs** in Loki. Then *perform and document the jump*: from a real p99 spike, click the exemplar to a trace, then jump from a span to its log lines — capturing each step. This is the four-minute-incident move.

Your writeup at `notes/week-17/trace-to-log-jump.md` must hit these steps, each with a screenshot or captured output:

1. **The spike** — the cart latency panel with a real p99 spike (induce it with load + a slow path or fault).
2. **The exemplar** — the clickable dot on the panel carrying a trace ID.
3. **The trace** — Tempo showing that trace, with the slow span identified.
4. **The log** — Loki showing that span's log lines, filtered by the trace ID.
5. **The thread** — confirm the *same* trace ID appears in all of steps 2–4.

**Acceptance criteria.**

- `dashboards/cart-red.json` is exported and committed (reproducible, not a one-off).
- `notes/week-17/trace-to-log-jump.md` documents all five steps with evidence, and the same trace ID is visible across the exemplar, the trace, and the logs.
- If exemplars don't render, you diagnose which of the three preconditions (SDK exemplars / OpenMetrics / Prometheus exemplar storage) is off, and fix it.
- You state in one or two sentences how this jump turns a 40-minute incident into a 4-minute one.
- Committed.

**Hint.** Exemplars need all three lined up: the SDK recording exemplars on histograms, OpenMetrics exposition (`enable_open_metrics: true` on the Collector's Prometheus exporter), and Prometheus started with `--enable-feature=exemplar-storage`. If the dots are missing, one of those is off — check in that order. The trace-to-logs link is configured on the Tempo datasource in Grafana, mapping the span's trace ID into a LogQL query.

**Estimated time.** 1 hour 10 minutes.

---

## Problem 5 — The cardinality budget memo

**Problem statement.** Compute the **cardinality budget** for your cart topology's metrics and write it up at `notes/week-17/cardinality-budget.md`. For each metric, list its labels and the (bounded) cardinality of each, multiply out to a series count, and identify any label that is unbounded (or could become so). Then propose where each high-cardinality dimension belongs instead (a trace attribute or a log filter, not a metric label).

**Acceptance criteria.**

- `notes/week-17/cardinality-budget.md` lists each metric, its labels, each label's cardinality, and the product (total series).
- You identify at least one label that would explode cardinality if added (`user_id`, `trace_id`, raw URL, `cart_id`) and state where it belongs instead.
- You give the resulting Prometheus memory estimate (series × ~bytes-per-series) so the budget is a real number.
- You state the rule: metric labels are bounded/low-cardinality; per-request dimensions live in traces or as log filters.
- Committed.

**Hint.** The dangerous multiplier is a label whose value space is unbounded. `route="/cart/{id}"` (the template) is fine — a handful of routes; `route="/cart/12345"` (the filled path) is a series per ID — unbounded. The memo is the conversation that prevents the most common self-inflicted observability outage: the label that 1000×'d the series count and OOMed Prometheus overnight.

**Estimated time.** 45 minutes.

---

## Problem 6 — Diagnose a planted observability fault

**Problem statement.** Have a partner (or your future self) introduce ONE of these faults into your stack, then diagnose it from the outside before looking at what was changed: (a) a service's OTLP exporter pointed at a wrong endpoint (telemetry silently dropped), (b) the W3C propagator not installed on one service (its traces orphan), or (c) the Prometheus `replica` external label removed (Thanos can't deduplicate). For whichever fault, produce a diagnosis: symptom, the evidence, root cause, and fix.

**Acceptance criteria.**

- `notes/week-17/planted-fault.md` records which fault, the diagnostic steps you ran, the evidence (a backend query showing missing/orphaned/double-counted data), the root cause, and the fix.
- You reach the diagnosis with at least two signals (e.g., "no new traces in Tempo for this service" *and* "the Collector logs show no receives from it").
- Committed.

**Hint.** The silent-drop fault (a) is the trickiest because nothing errors — the only signal is *absence* of data in the backend plus *absence* of receives in the Collector logs. The propagator fault (b) shows up as orphaned root spans where children belong. The dedup fault (c) shows up as every series appearing twice in Thanos Query. The unifying method, same as the mesh week: *query the backend, treat its data as ground truth, and work backward to where the pipeline lost the signal.*

**Estimated time.** 35 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 — Signal-coverage audit table | 40 min |
| 2 — Prove the trace survives Kafka | 45 min |
| 3 — RED PromQL + the bucket trap | 50 min |
| 4 — RED dashboard + trace-to-log jump (headline) | 1 h 10 min |
| 5 — Cardinality budget memo | 45 min |
| 6 — Diagnose a planted fault | 35 min |
| **Total** | **~5 h 5 min** |

When you've finished all six, push your repo and make sure the `cart-observed` [mini-project](./mini-project/README.md) is in the same workspace — Week 18 defines SLIs and error budgets as PromQL over these exact metrics. Then take the [quiz](./quiz.md) with your notes closed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Signal-coverage audit (P1)** | 15 | Real backend evidence per service; the missing-propagator or missing-signal gap correctly flagged. |
| **Kafka trace continuity (P2)** | 15 | Propagated vs split demonstrated; `traceparent` header quoted present/absent; the why stated. |
| **RED PromQL + buckets (P3)** | 15 | Three RED queries correct; the bucket trap demonstrated; SLO-aligned buckets fix it. |
| **Trace-to-log jump (P4)** | 25 | Exemplars render; the full spike→trace→log jump documented with the same trace ID across all three. |
| **Cardinality budget (P4... P5)** | 20 | Per-metric series counts; the unbounded label identified and re-homed; a real memory estimate. |
| **Planted fault (P6)** | 10 | Two-signal diagnosis; backend-as-ground-truth method; correct root cause and fix. |

**90+** is portfolio-grade. **70–89** is solid but the trace-to-log jump likely isn't fully demonstrated, or the cardinality budget hand-waves the numbers. **Below 70** usually means Problem 2 or 4 was treated as a formality — they're the two that prove your signals actually *correlate* and survive the async boundary, which is the whole difference between installing observability and operating it.
