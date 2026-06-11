# Exercise 1 — The Twelve-Factor / Readiness Audit

**Goal:** Score the `cart` service (your Week 5 gRPC service, or the skeleton in Exercise 2) against the twelve factors and a production-readiness checklist, producing the concrete gap list that the rest of the week — and the mini-project — closes. You will train the single most valuable review habit: turning "is it production-ready?" from a feeling into a checklist verdict.

**Estimated time:** 45 minutes. Guided.

---

## Setup

You need a service to audit. Best: your Week 5 gRPC `cart` (or `catalog`). Fallback: the skeleton Go service from Exercise 2. Have its source open and, if possible, run it so you can check runtime behavior.

The audit is a *document*. Create `notes/week-06/readiness-audit.md` and fill in the tables below as you go. Every row gets a verdict (`PASS` / `FAIL` / `N/A`) and, for every `FAIL`, a one-line gap description that becomes a to-do.

---

## Part A — The twelve-factor audit

Go factor by factor. For each, state how `cart` honors or violates it.

| Factor | Question to ask of `cart` | Verdict | Gap (if FAIL) |
|---|---|---|---|
| III — Config | Is *all* per-deploy config (DB URL, log level, OTLP endpoint) read from the environment, with nothing environment-specific hard-coded or committed? | | |
| IV — Backing services | Is the database an attached resource reached by a URL from config, swappable without a code change? | | |
| VI — Processes | Is the service stateless — no sticky in-memory/on-disk state between requests? | | |
| IX — Disposability | Does it start fast and shut down gracefully on `SIGTERM` (drain in-flight, no dropped requests)? | | |
| X — Dev/prod parity | Does the same image run in dev and prod, differing only by config? | | |
| XI — Logs | Does it write structured logs to stdout and leave routing to the platform (no log files in the app)? | | |

Most un-hardened services fail IX (no graceful shutdown), XI (string logs or log files), and sometimes III (a hard-coded localhost DB URL). Those `FAIL`s are your week's work.

---

## Part B — The production-readiness checklist

Now the operability checklist that a real readiness review walks. Verdict each.

| # | Item | Question | Verdict | Gap |
|---|---|---|---|---|
| 1 | Structured logs | JSON to stdout, consistent schema, `trace_id` field, no secrets/PII logged? | | |
| 2 | Liveness probe | Exists, checks *self only* (no dependencies), cheap? | | |
| 3 | Readiness probe | Exists, checks *self only* (NOT a dependency!), flips to not-ready during drain? | | |
| 4 | Startup probe | Present if the service boots slowly? (N/A if fast.) | | |
| 5 | Graceful shutdown | Catches `SIGTERM`, flips health, drains in-flight, closes resources in order, bounded under the grace period? | | |
| 6 | `preStop` hook | A short sleep to dodge the readiness-removal race? | | |
| 7 | Resource requests | Set, so the scheduler reserves capacity? | | |
| 8 | Resource limits | Set, so a leak can't starve the node? | | |
| 9 | Tracing | A span per request, context propagation across the gRPC boundary (global propagator set)? | | |
| 10 | RED metrics | Rate, Errors, Duration emitted via OTLP? | | |
| 11 | SecurityContext | Runs non-root, no privilege escalation, dropped caps? | | |
| 12 | Secrets | From a Kubernetes Secret, never baked into the image, never logged? | | |
| 13 | ServiceAccount | An explicit (even minimal) identity? | | |
| 14 | PodDisruptionBudget | Prevents a drain/deploy from taking the service to zero replicas? | | |
| 15 | Runbook | Exists, with five named failure-mode playbooks? | | |

---

## Part C — The gap list

Collect every `FAIL` into a prioritized to-do list at the bottom of the audit. Order it by *blast radius*: the things that cause outages (missing readiness gating, missing limits, no graceful shutdown) before the things that slow diagnosis (missing tracing, no runbook). Example shape:

```
## Gap list (close these this week)
1. [BLOCKER] No graceful shutdown — every rolling deploy drops in-flight requests. (Factor IX, item 5)
2. [BLOCKER] No resource limits — a memory leak can OOM the node. (item 8)
3. [BLOCKER] Readiness probe checks catalog — a catalog blip will take down all cart replicas. (item 3)
4. [HIGH] Logs are interpolated strings, not JSON — not queryable. (Factor XI, item 1)
5. [HIGH] No tracing — can't see where a slow add_item spends its time. (item 9)
6. [MED]  No runbook. (item 15)
...
```

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] `notes/week-06/readiness-audit.md` exists with Part A (twelve-factor) and Part B (the 15-item checklist) fully verdicted.
- [ ] Every `FAIL` has a one-line gap description.
- [ ] Part C is a prioritized gap list ordered by blast radius, with at least the `BLOCKER`s identified.
- [ ] You can state, in one sentence, which single gap would cause the *worst* outage and why (likely: a dependency-checking readiness probe, or no resource limits).
- [ ] Committed.

---

## Stretch

- For item 3, if your `cart`'s readiness probe *does* check `catalog`, write the two-line incident narrative of the conflation outage (Lecture 1 §3.2) it would cause, then note the fix (readiness checks self only; handle `catalog` failure in the request path).
- Score a *second* service (a teammate's, or an open-source one you run) on the same checklist. Comparing two services' gap lists is the fastest way to internalize what "production-ready" means.
- Add an item 16 of your own that the checklist missed but that matters for *your* service (e.g. a max-message-size limit on the gRPC server, or a connection-pool cap on the DB). A good reviewer extends the checklist to the service in front of them.

---

When your gap list is in hand, move to [Exercise 2 — Structured logs, probes, and graceful shutdown](exercise-02-graceful-shutdown.go) to start closing it.
