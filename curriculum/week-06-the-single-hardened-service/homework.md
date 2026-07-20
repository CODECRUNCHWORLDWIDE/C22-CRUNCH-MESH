# Week 6 Homework

Six problems that revisit the week's topics and force the production-readiness discipline into your fingers. The full set should take about **5 hours**. Work in your Week 6 Git repository (the same workspace as the exercises and the hardened-`cart` mini-project) so every problem produces at least one commit you can point to at the Phase 1 architecture review in Week 12.

The headline deliverable is **Problem 4 — the runbook**, called out explicitly in the syllabus. Treat it as the artifact an on-call engineer opens at 3 a.m., not a journal entry.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

Have **Go 1.23+**, **`kubectl`**, a local **Kind** cluster, and **`helm`** available. Problems use the exercises' Go service, Deployment, and the mini-project chart.

---

## Problem 1 — The structured-log schema

**Problem statement.** Define a consistent structured-log schema for `cart` and apply it. Every log line must be JSON with `time`, `level`, `msg` (a stable constant), `trace_id`, and contextual fields. Convert at least three `fmt.Print`-style or string-interpolated log sites to the schema. Document the schema and the before/after in `notes/week-06/log-schema.md`.

**Acceptance criteria.**

- `notes/week-06/log-schema.md` defines the schema and shows three before/after log conversions.
- At least one converted line carries a `trace_id`.
- You identify one thing that must *never* be logged and confirm it isn't (the `DATABASE_URL`, a card number, a full body).
- Committed.

**Hint.** The tell of a bad log is an interpolated `msg` (`"added 2 of SKU-1 to cart c1"`). Make `msg` the constant `"item_added"` and move the variables to fields — now it's groupable and queryable. `slog.Info("item_added", "cart_id", id, "sku", sku, ...)`.

**Estimated time.** 35 minutes.

---

## Problem 2 — Prove liveness ≠ readiness

**Problem statement.** Using the Exercise 2 Go service (or your `cart`), demonstrate the difference between liveness and readiness. Show: (a) `/healthz` returns 200 from process start while `/readyz` returns 503 during warmup; (b) on `SIGTERM`, `/readyz` flips to 503 *before* the process exits while in-flight work completes. Capture both in `notes/week-06/liveness-vs-readiness.md`.

**Acceptance criteria.**

- `notes/week-06/liveness-vs-readiness.md` shows the warmup phase (`/healthz` 200, `/readyz` 503) and the shutdown phase (`/readyz` 503 while a request drains).
- You state in one sentence what Kubernetes does differently for a failing liveness vs a failing readiness probe.
- You confirm neither probe checks a dependency, and state the outage that would result if readiness did.
- Committed.

**Hint.** `curl -s -o /dev/null -w "%{http_code}\n" localhost:8080/readyz` in a fast loop during startup and shutdown captures the transitions. The key observation is the *ordering* at shutdown: readiness 503 first, then drain.

**Estimated time.** 40 minutes.

---

## Problem 3 — Demonstrate the zero-drop deploy

**Problem statement.** Deploy `cart` (or the Exercise 2 service in a container) to Kind with the Exercise 3 Deployment. Drive steady load, trigger `kubectl rollout restart`, and show **zero failed requests**. Then *break it on purpose*: remove the `preStop` hook (or make the app exit immediately on `SIGTERM`), repeat, and show the drops. Capture both runs in `notes/week-06/zero-drop.md`.

**Acceptance criteria.**

- `notes/week-06/zero-drop.md` shows a load-generator summary with **0 failed requests** across a rolling restart on the *correct* config.
- It shows a load-generator summary with **>0 failed requests** on the *broken* config (no preStop / immediate exit), proving the mechanism matters.
- You explain in two sentences which two mechanisms (readiness gating + graceful drain, plus `maxUnavailable: 0` and `preStop`) combine to make zero-drop work.
- Committed.

**Hint.** The broken run is the deliverable — it proves the correct config isn't luck. `hey -z 30s -c 20 ...` plus `kubectl rollout restart` mid-flight. If even the broken run shows zero drops, your load isn't concurrent enough or the restart isn't hitting in-flight requests; raise concurrency.

**Estimated time.** 50 minutes.

---

## Problem 4 — The runbook (headline deliverable)

**Problem statement.** This is the syllabus deliverable. Write `RUNBOOK.md` for `cart` with all six sections (Lecture 2 §4.1) and **five named failure-mode playbooks**, each *executable by someone who didn't write the service*:

1. Purpose and owners.
2. Dependencies (`catalog`, `cart_db`) — and what happens to `cart` when each fails.
3. SLOs (availability + latency SLIs/targets).
4. Dashboards and what "normal" looks like.
5. Five failure-mode playbooks: `catalog` down/slow; `cart_db` down/saturated; a bad deploy; resource exhaustion (OOM/throttle); a traffic spike. Each as *symptom → diagnosis → mitigation → verify → escalate*.

**Acceptance criteria.**

- `RUNBOOK.md` exists with all six sections.
- Five failure-mode playbooks, each with concrete commands (not "investigate"), and a verify step.
- The dependencies section states, for each dependency, the *cart-side* consequence of its failure and the correct response (degrade in the request path, NOT fail readiness).
- A teammate (or you, role-playing a stranger) could execute the "bad deploy" playbook from the text alone.
- Committed.

**Hint.** The playbook test: replace every verb-of-intention ("investigate," "look into," "check on") with a command and an expected result. "Investigate the deploy" → "run `kubectl rollout history deployment/cart`, identify the revision deployed nearest the error spike, run `kubectl rollout undo deployment/cart`, confirm error rate returns to baseline within 2 minutes on the RED dashboard." That transformation *is* the assignment.

**Estimated time.** 1 hour 15 minutes.

---

## Problem 5 — Harden the Helm chart and review it

**Problem statement.** Take your `cart` Helm chart (mini-project) and run a self-review against the non-negotiable Deployment fields (Lecture 2 §2.2). For each — requests, limits, three probes, non-root SecurityContext, grace period, preStop, ServiceAccount, PDB — confirm it's present and correct, or fix it. Capture the `helm template` output and your field-by-field verdict in `notes/week-06/chart-review.md`.

**Acceptance criteria.**

- `notes/week-06/chart-review.md` has a field-by-field verdict table (field → present? → value → correct?).
- `helm template ./deploy/cart` output is pasted, showing the rendered Deployment with all fields.
- Any field that was missing/wrong is fixed, with the fix noted.
- You confirm the readiness probe checks self only (no DB/catalog in the probe).
- Committed.

**Hint.** `helm template ./deploy/cart | kubectl apply --dry-run=client -f -` both renders the chart and validates the manifests against the API server's schema in one step. A field that renders but fails `--dry-run` is a chart bug.

**Estimated time.** 40 minutes.

---

## Problem 6 — Trace an `add_item` end to end

**Problem statement.** With OpenTelemetry wired (mini-project) and a local OTel collector running, perform an `add_item` on `cart` (which calls `catalog`) and capture the resulting trace. Show that the trace contains *both* a `cart` span and a `catalog` child span — proving context propagated across the gRPC boundary. Capture it in `notes/week-06/trace.md`.

**Acceptance criteria.**

- `notes/week-06/trace.md` shows the trace with the `cart` parent span and the `catalog` child span, with the same `trace_id`.
- You confirm the global W3C propagator is set, and state in one sentence what happens to the trace if it isn't (disconnected spans).
- A log line from the request carries the same `trace_id` as the trace (log/trace correlation).
- Committed.

**Hint.** If your `cart` and `catalog` spans show up as *two separate traces* with different trace ids, you forgot `otel.SetTextMapPropagator(...)` globally — that's the #1 OTel mistake (Lecture 2 §1.3). The collector's debug/logging exporter prints received spans; grep for your `trace_id` to confirm both are there.

**Estimated time.** 40 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 — Structured-log schema | 35 min |
| 2 — Liveness ≠ readiness | 40 min |
| 3 — Zero-drop deploy (with the broken control) | 50 min |
| 4 — The runbook (headline) | 1 h 15 min |
| 5 — Helm chart review | 40 min |
| 6 — Trace add_item end to end | 40 min |
| **Total** | **~5 h 0 min** |

---

## Rubric (for the headline runbook, Problem 4)

| Criterion | Excellent (full) | Adequate (half) | Missing (zero) |
|---|---|---|---|
| **Completeness** | All six sections; five failure modes. | Four-five sections; 3-4 failure modes. | Missing sections or fewer than 3 failure modes. |
| **Executability** | Every playbook is commands + expected results; a stranger could run it. | Mostly executable; one or two vague steps. | "Investigate the issue"-style wishes. |
| **Dependencies** | Each dep's failure → cart-side consequence → correct response (degrade, not fail-readiness). | Deps listed; consequences thin. | Deps not analyzed. |
| **SLOs & dashboards** | Concrete SLIs/targets; "normal" baseline stated. | Present but vague. | Absent. |
| **Verify steps** | Every playbook ends in a verifiable "did it work?" check. | Some verify steps. | No verification. |

**Full marks across the board** is the artifact you bring to the Week 12 architecture review and revise into a portfolio piece at graduation. Anything less, revise before then — an on-call engineer will use it for real.

When you've finished all six, push your repo and make sure the hardened `cart` [mini-project](./mini-project/README.md) — chart and runbook included — is in the same workspace. You've completed Phase 1; Week 7 begins Phase 2 by putting your hardened `cart` behind Envoy. Then take the [quiz](./quiz.md) with your notes closed.
