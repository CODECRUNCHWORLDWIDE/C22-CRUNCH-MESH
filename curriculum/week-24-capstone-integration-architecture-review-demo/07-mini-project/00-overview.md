# Mini-Project — The Capstone: The Polyglot Marketplace Backbone, Assembled and Defended

> Assemble every prior week's compounding artifact — the CRDT cart, the leased inventory, the Temporal payment, the order orchestrator, the Debezium-fed search, the Iceberg analytics, the BFFs, the gRPC contracts, the Kafka spine, the Istio mesh with SPIFFE/SPIRE and OPA, the OpenTelemetry pipeline, and last week's Pact broker, property tests, and capacity model — into one **two-region active-active** system. Prove it runs, survives the two mandatory chaos drills with zero data loss and zero double-charge, and defend it in a live staff-engineer architecture review. Then ship the six deliverables.

This is the capstone. It is not a new build; it is the **integration** of twenty-four weeks of compounding work into one system you can stand up, prove, defend, and operate. By the syllabus, the capstone runs across the final four weeks (21–24); this week is where it's assembled, proven, and defended. If you kept your services modular and your mesh and event spine honest every week, this week is assembly and proof. If you took shortcuts, this is where you pay for them.

**Estimated time:** ~12.5 hours of the week's schedule (Monday through Saturday mini-project blocks), on top of the exercises and the live defense.

---

## What you assemble

You already have, from the prior weeks, every service and every piece of substrate. The capstone wires them into one running two-region system and proves the whole thing works together.

### The services (each in its required language)

- **`cart-service` (Rust)** — OR-set CRDT shopping cart, multi-region active-active (Weeks 3, 20).
- **`inventory-service` (Go)** — authoritative stock counts, single-writer-per-SKU with leases (Weeks 2, 6).
- **`payment-service` (Go)** — Temporal workflow for charge/refund/reversal, with idempotency (Weeks 11, 12).
- **`order-service` (Python)** — orchestrator that pulls cart, reserves inventory, drives payment, and emits `order.placed.v1` (Weeks 4, 12).
- **`search-service` (Python)** — read model fed by Debezium CDC into Elasticsearch (Weeks 13, 14).
- **`analytics-service` (Python/dbt)** — Iceberg-on-Trino daily and hourly rollups (Weeks 14, 15).
- **`bff-web` (Go)** and **`bff-mobile` (Go)** — thin BFFs over the gRPC backbone (Week 7).

### The substrate

- gRPC + Protobuf everywhere, with `cart.v1`/`inventory.v1`/`payment.v1`/`order.v1` versioned independently (Week 5).
- Kafka event spine with exactly-once consumers via outbox + idempotency keys (Weeks 10, 11).
- Temporal cluster for long-running workflows (Week 12).
- Postgres primary per region with logical replication and Debezium CDC (Weeks 13, 14).
- Istio service mesh with mTLS strict, SPIFFE identities via SPIRE, OPA admission policy (Weeks 8, 21).
- Progressive delivery: weighted canary, automatic rollback on SLO breach (Week 8).
- Two-region active-active deployment (Kind locally, or two GKE/EKS clusters) (Weeks 19, 20).
- Full OpenTelemetry pipeline: traces to Tempo, metrics to Prometheus + Thanos, logs to Loki, Grafana dashboards with exemplars (Week 17).
- Published Pact contract test suite, broker running in-cluster (Week 23).

### The repo that ties it together

```
marketplace-backbone/
├── README.md                  # how to apply, prove, defend, and the known-limitations
├── deploy/
│   ├── region-primary/        # the primary region's manifests/Helm (kind-region-primary)
│   ├── region-standby/        # the second region (active-active, not standby-cold)
│   ├── mesh/                  # Istio + SPIRE + OPA (Weeks 8, 21)
│   ├── substrate/             # Kafka, Temporal, Postgres+Debezium, observability
│   └── routed-control-plane/  # the cross-region routing (Week 19)
├── services/                  # cart (Rust), inventory/payment/bffs (Go), order/search/analytics (Python)
├── contracts/                 # the Pact broker + pacts (from Week 23)
├── load/
│   └── place-orders.js        # the k6 script for the 1k-RPS drills
├── docs/
│   ├── ARCHITECTURE.md        # the 2,000-word C4 document
│   ├── diagram-context.md     # C4 system context (Mermaid)
│   ├── diagram-container.md   # C4 container
│   └── diagram-component.md   # C4 component for TWO key services
├── postmortems/
│   ├── POSTMORTEM-drill-A.md  # region failover (Exercise 2)
│   └── POSTMORTEM-drill-B.md  # broker loss (Exercise 3)
├── RUNBOOK.md                 # 6 pages, five named failure modes
├── capacity/ORDER-CAPACITY-MEMO.md   # from Week 23
└── demo/
    └── demo-script.md         # the 12-minute demo's four timed segments
```

---

## The required deliverables (from the syllabus capstone spec)

The syllabus names six. This mini-project produces all of them:

1. **The running system** — two-region active-active, all services healthy at demo time.
2. **A 2,000-word architecture document** with C4-style diagrams: system context, container, and component (for two key services). Defend the design and its tradeoffs in prose.
3. **A 12-minute recorded demo** covering: architecture walkthrough, a live deploy with weighted canary (and automatic rollback), a Grafana dashboard tour ending in a trace-to-log jump, and the cart-CRDT convergence demo across a simulated partition.
4. **Two chaos-drill postmortems (mandatory)**: Drill A (region failover under 1k RPS — impact, recovery, lessons) and Drill B (Kafka broker loss — prove no double-process, outbox integrity).
5. **A 6-page runbook** covering five named failure modes: region loss, broker loss, Postgres primary failure, Temporal worker outage, certificate expiry.
6. **A published Pact broker URL** with green contracts.

---

## Deliverable 1 — The running two-region system

Bring up both regions active-active with the routed control plane (Week 19), the cart promoted active-active via the OR-set CRDT (Week 20), the mesh with mTLS strict + SPIFFE/SPIRE + OPA (Weeks 8, 21), and the full observability pipeline (Week 17). It must come up reproducibly — a documented sequence a grader (or you, at 3am) can follow — and be healthy at demo time. "Works on my cluster, once, last Tuesday" is not a deliverable; a documented bring-up that you can run on demand is.

---

## Deliverable 2 — The 2,000-word C4 architecture document

`docs/ARCHITECTURE.md` with three diagram levels and the prose that defends them:

- **System context** — the marketplace in its world: customers, the system, external dependencies (a payment processor, an object store). One box for the system, the actors around it.
- **Container** — the deployable units: the services, the Kafka spine, Temporal, Postgres, the read stores, the mesh. Every arrow labeled with the protocol (gRPC, Kafka, CDC) and the rough throughput. This is the diagram you walk in the review.
- **Component (two key services)** — pick two services with interesting internals (e.g., the CRDT cart's merge + anti-entropy, the payment Temporal workflow's saga + compensation) and draw their components.

The 2,000 words defend the *why*: why a CRDT for the cart and a lease for inventory (the per-field CAP choice), why Temporal orchestration over choreography for the saga, why a mesh over a library for mTLS, and the tradeoffs each carries. This is the written form of the review's defense — write it as if a staff engineer will read it before deciding whether to trust the design.

---

## Deliverable 3 — The 12-minute demo

`demo/demo-script.md` and the recording. Four timed segments (Lecture 2 §3.1): the architecture walk (~3 min), the live weighted-canary deploy with automatic rollback (~3 min), the Grafana tour ending in a trace-to-log jump (~3 min), and the cart-CRDT convergence across a partition (~3 min). Rehearse the live parts; bring a warm system; narrate the mechanism, not the clicks; have a fallback recording of each live segment; edit to time. The demo proves the four properties the document can only *claim* — that the canary rolls back, that the system is observable, that the cart converges, and that the whole thing flows.

---

## Deliverable 4 — The two mandatory chaos-drill postmortems

`postmortems/POSTMORTEM-drill-A.md` and `POSTMORTEM-drill-B.md`, produced by Exercises 2 and 3:

- **Drill A (region failover)** — kill the primary region under 1k RPS; measure the RTO; prove zero orders lost and zero double-charges; confirm the cart converges on heal. The postmortem walks the three failure domains (CRDT cart, leased inventory, Temporal payment) that fail differently by design.
- **Drill B (broker loss)** — kill a Kafka broker mid-traffic; let the consumers rebalance and re-deliver; prove with a SQL `HAVING COUNT(*) > 1` returning **zero rows** that every idempotency key was charged exactly once. The empty result set is the deliverable.

> **These are mandatory and graded with a 60% floor.** A drill you described but didn't run, or a broker-loss where you can't show the empty double-charge query, fails the deliverable regardless of the rest. The postmortems are blameless, SRE-format, with timestamped timelines and owned action items.

---

## Deliverable 5 — The 6-page runbook

`RUNBOOK.md` covering five named failure modes, each with: the symptom (what pages you), the first diagnostic step (the dashboard or command — *not* "grep the logs"), the mitigation, and the recovery. The five:

1. **Region loss** — the failover (Drill A) as a runbook entry: confirm it's a region event, the failover is automatic, what to watch.
2. **Broker loss** — confirm the rebalance is benign (Drill B), watch the dedup metric, confirm the DLQ stays empty.
3. **Postgres primary failure** — promote a logical replica, repoint Debezium, the data-loss window.
4. **Temporal worker outage** — workflows are durable; workers resume; what to check.
5. **Certificate expiry** — the istiod CA / SPIRE rotation (Weeks 8, 21); the symptom and the fix.

Each entry's first line is what a reviewer reads to judge whether your observability lets you answer "what's wrong" in one look.

---

## Deliverable 6 — The green Pact broker

The in-cluster Pact broker from Week 23, green for the named boundaries (`cart↔inventory`, `cart↔payment`, `order→search`), with `can-i-deploy` passing. Capture the URL in the README — the reviewers click it. A green broker proves your polyglot boundaries can't silently break.

---

## Rules

- **You may** reuse every service and every piece of substrate you built in Weeks 1–23. That is the point — this is integration, not a rewrite.
- **You may NOT** claim a number you didn't measure. The RTO comes from the drill; the per-order cost from the capacity model; the convergence from the property test and the live demo.
- **The two chaos drills are mandatory.** A failed or un-run drill is a failing deliverable.
- **Active-active, not active-passive.** Both regions serve; the cart is promoted active-active via the CRDT. A cold-standby second region does not meet the spec.
- **mTLS strict, enforced and proven.** A permissive mesh "with mTLS available" is a finding, not a pass — show plaintext refused.
- Two Kind clusters (or two cloud clusters); Istio 1.24+, Kafka, Temporal, Postgres+Debezium, the OTel stack, the Pact broker. Everything reproducible.

---

## Acceptance criteria

The rubric maps each box to a deliverable.

### Functional correctness (25%)

- [ ] The two-region active-active system comes up reproducibly and is healthy at demo time.
- [ ] One order traces through every hop, end to end, on the live system.
- [ ] The Pact broker is green; `can-i-deploy` passes.

### Architectural defensibility (25%)

- [ ] The 2,000-word C4 document defends the per-field consistency model and the major tradeoffs.
- [ ] You name your own three biggest risks before the reviewers ask.
- [ ] The live defense survives the staff-engineer question bank.

### Observability quality (15%)

- [ ] Every service emits OTel traces, metrics, and logs; one cross-service trace per order on demand.
- [ ] The demo shows the trace-to-log jump (metrics → traces → logs, correlated).
- [ ] At least one burn-rate alert per user-facing service; the failover drill makes one fire.

### Chaos-drill postmortems (15%)

- [ ] Drill A: RTO measured, zero data loss, cart converges on heal — postmortem complete.
- [ ] Drill B: the `HAVING COUNT(*) > 1` query returns zero rows — exactly-once proven under broker loss.

### Runbook (10%)

- [ ] Five named failure modes, each with a one-look first diagnostic step and a mitigation.

### Demo and writeup (10%)

- [ ] The 12-minute demo covers all four required segments, edited to time.
- [ ] The README has a "Known limitations and next steps" section from the review's risk list.

---

## Grading rubric

The capstone grade follows the syllabus weighting (functional correctness 25%, architectural defensibility 25%, observability 15%, chaos-drill postmortems 15%, runbook 10%, demo and writeup 10%). **Passing requires ≥60% on each deliverable and ≥70% overall.** The two chaos drills are mandatory: a missing or failed drill caps the capstone regardless of the other scores.

**90+** is portfolio-grade — a system you can put on a resume and defend in a staff interview. **70–89** passes but likely claims a number it didn't measure, runs a region as cold-standby instead of active-active, or has a permissive mesh. **Below 70** usually means a drill wasn't run, the trace doesn't span the system, or the consistency model wasn't defended per data type — fix those first; they're the difference between a system you built and a system you can own.

---

## Suggested order of work

- **Monday.** Bring up *primary region only*, end to end, and trace one order by hand (Exercise 1). Get the bring-up documented and reproducible. Don't move on until one order traces cleanly through the live system. Draft the C4 container diagram.
- **Tuesday.** Add the standby region active-active via the routed control plane; promote the cart active-active. Re-trace an order in each region. Write the 2,000-word architecture document.
- **Wednesday.** Run Drill A (region failover under 1k RPS). Measure the RTO, prove zero loss / zero double-charge, confirm cart convergence. Write `POSTMORTEM-drill-A.md`.
- **Thursday.** Run Drill B (broker loss). Prove the empty double-charge query. Write `POSTMORTEM-drill-B.md`. Write the runbook's five failure modes.
- **Friday.** Record the 12-minute demo. Deliver the live capstone defense (the challenge). Capture the risk list.
- **Saturday.** Turn the risk list into the README's known-limitations section. Polish the architecture doc and the portfolio. A final clean bring-up to confirm reproducibility.

---

## What "done" looks like

Two external reviewers watch you bring up a two-region active-active marketplace, place one order, and trace it through every service in a single distributed trace ending in a one-click jump to the logs. They watch you kill a region under load and the system recover in under a minute with zero double-charges; they watch you kill a Kafka broker and a SQL query prove every order was charged exactly once. They read a 2,000-word document that defends why the cart is eventually consistent and the payment is exactly-once, click a green Pact broker, and read a runbook whose first line for each failure tells them exactly what to look at. They ask the hard questions, and you answer each on the requirement, name your own three biggest risks before they do, and hand them a risk list you'll turn into your portfolio's limitations section. Then you tear it down and bring it back up to prove it wasn't luck. That is the capstone. That is C22. Go defend it.
