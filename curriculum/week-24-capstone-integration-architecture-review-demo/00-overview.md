# Week 24 — Capstone Integration, Architecture Review, and Demo

Welcome to the last week of **C22 · Crunch Mesh**. You do not learn a new topic this week. You ship.

Everything you have built since Week 1 — the CAP/PACELC reasoning, the Raft-backed coordination, the OR-set CRDT, the bounded-context decomposition, the gRPC contracts, the hardened single service, the Envoy gateway, the Istio mesh with mTLS and canary, the Kafka spine with exactly-once consumers, the Temporal sagas, the Postgres replication and Debezium CDC, the Iceberg lakehouse, the Redis caching, the OpenTelemetry pipeline, the SLOs and circuit breakers, the multi-region active-active topology, the production CRDTs, the SPIFFE/SPIRE zero-trust network, the chaos gameday, and last week's contract suite, property tests, and capacity model — gets assembled into one running system: the **Polyglot Marketplace Backbone**, two-region active-active, in your own Kind clusters (or two cloud clusters). Then you defend it.

"Defend it" is not a metaphor. This week you run a real architecture review: you stand in front of the cohort and **two external reviewers** (the syllabus's capstone defense), you walk a single order through the whole system on screen, and you answer the questions a staff engineer asks when they are deciding whether to trust your design in production. You produce the **2,000-word architecture document with C4 diagrams**, the **12-minute recorded demo**, the **two mandatory chaos-drill postmortems** (region failover and Kafka broker loss), the **6-page runbook** covering five named failure modes, and you point at a **published Pact broker URL with green contracts**. And you must clear the capstone's hard gate: **≥60% on each deliverable** and ≥70% overall, with the two chaos drills *mandatory* — a failed region-failover drill or a double-charge under broker loss is not a deliverable you can hand-wave.

The week has a rhythm: integrate and harden early, prove the system with load and the two chaos drills mid-week, then record and defend at the end. If your Week 23 contract broker isn't green, fix that first — it's a required artifact and the reviewers will click the URL. This is the week the course has been building toward. Treat it like a release.

## Learning objectives

By the end of this week, you will be able to:

- **Integrate** every prior-week artifact into one two-region active-active system that comes up reproducibly and that you can demonstrate healthy end to end at demo time.
- **Trace** a single order through the whole backbone — BFF → order → cart (CRDT) → inventory (lease) → payment (Temporal) → `order.placed.v1` → search/analytics — on screen, using your own OpenTelemetry, ending in a trace-to-log jump.
- **Execute** the two mandatory chaos drills — **Drill A: region failover** under 1k RPS, and **Drill B: Kafka broker loss** proving no double-process — and write the blameless postmortem each requires.
- **Present** a production architecture in a live staff-engineer review and answer the standard questions about blast radius, failure modes, consistency, cost, and observability without flinching.
- **Author** the capstone artifacts to spec: the 2,000-word architecture document with C4-style diagrams (context, container, component for two key services), the 12-minute demo video, the two postmortems, and the 6-page runbook.
- **Demonstrate** the cart-CRDT convergence across a simulated partition, the weighted canary with automatic rollback on SLO breach, and the green Pact broker — the three artifacts that prove the system's hardest properties.
- **Defend** a system you built at staff-engineer level: name your own biggest risk before the reviewers do, distinguish the failure domains, and tie every claimed number to a measurement.

## Prerequisites

This week assumes you have completed Weeks 1–23 of C22 and that those mini-projects produced working, version-controlled artifacts. Specifically, you need:

- The **capstone services**, each in its required language and runnable: `cart-service` (Rust, OR-set CRDT), `inventory-service` (Go, single-writer-per-SKU leases), `payment-service` (Go, Temporal workflow), `order-service` (Python orchestrator), `search-service` (Python, Debezium-fed Elasticsearch read model), `analytics-service` (Python/dbt, Iceberg-on-Trino), and `bff-web` + `bff-mobile` (Go).
- The **substrate**: gRPC + Protobuf with independently-versioned `cart.v1`/`inventory.v1`/`payment.v1`/`order.v1`; the Kafka spine with outbox + idempotency-key consumers; the Temporal cluster; Postgres-per-region with logical replication and Debezium CDC.
- The **mesh and security**: Istio with mTLS strict, SPIFFE identities via SPIRE (Week 21), OPA admission policy; progressive delivery with weighted canary and automatic rollback (Week 8).
- The **two-region active-active deployment** (Week 19/20): two Kind clusters with a routed control plane, the cart promoted active-active via the OR-set CRDT.
- The **observability pipeline** (Week 17): OpenTelemetry traces to Tempo, metrics to Prometheus + Thanos, logs to Loki, Grafana dashboards with exemplars.
- Last week's **contract suite** (the published Pact broker), **property tests** (the convergence and idempotency evidence), and **capacity model** (the order-service sizing).

If any of those is missing or broken, this week will expose it. That is the point.

## Topics covered

- Final integration of the two-region active-active backbone: bringing every service, the substrate, the mesh, and the observability pipeline up together and healthy.
- The trace-an-order walk: following one order through every hop on screen, ending in a trace-to-log jump — the demonstration that proves the system is observable enough to operate.
- The two mandatory chaos drills: **Drill A (region failover)** — kill the primary region under a 1k-RPS load test and document the impact, recovery, and lessons; **Drill B (Kafka broker loss)** — lose a broker mid-traffic and prove the exactly-once consumers don't double-process and the outbox guarantees integrity.
- The blameless postmortem: the format, the timeline, the "five whys" without blame, and the action items that make each drill a publishable artifact.
- The staff-engineer architecture review: the agenda, the artifacts, the question bank (blast radius, consistency model, data-loss windows, cost-per-order, the 3am walk), and how to run the room while you're the one being reviewed.
- The C4 architecture document: system context, container, and component diagrams for two key services, plus the 2,000-word defense of the design and its tradeoffs.
- The 12-minute demo video: the architecture walkthrough, the live weighted-canary deploy, the Grafana dashboard tour ending in a trace-to-log jump, and the cart-CRDT convergence demo across a simulated partition.
- The 6-page runbook covering five named failure modes: region loss, broker loss, Postgres primary failure, Temporal worker outage, and certificate expiry.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract; the capstone deserves whatever it takes.

| Day       | Focus                                                       | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Final integration; the architecture-review playbook         |    2h    |    0.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Tuesday   | Trace-an-order; the C4 architecture document                |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     7h      |
| Wednesday | Drill A: region failover under 1k RPS; the postmortem       |    1h    |    1.5h   |     1h     |    0.5h   |   1h     |     1.5h     |    0h      |     6.5h    |
| Thursday  | Drill B: Kafka broker loss; prove no double-process         |    0h    |    1.5h   |     1h     |    0.5h   |   1h     |     1.5h     |    0.5h    |     6.5h    |
| Friday    | Record the 12-min demo; deliver the live capstone defense    |    0h    |    0h     |     0h     |    0.5h   |   0h     |     3h       |    0.5h    |     4h      |
| Saturday  | Runbook, architecture doc polish, portfolio                 |    0h    |    0h     |     0h     |    0h     |   1h     |     2h       |    0.5h    |     3.5h    |
| Sunday    | Quiz, course retrospective, wrap                            |    0h    |    0h     |     0h     |    1h     |   0h     |     0.5h     |    0.5h    |     2h      |
| **Total** |                                                            | **4h**   | **5.5h**  | **2h**     | **3.5h**  | **5h**   | **12.5h**    | **3h**     | **35.5h**   |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./00-overview.md) | This overview (you are here) |
| [resources.md](./01-resources.md) | C4 model references, architecture-review templates, postmortem templates, demo-recording tooling |
| [lecture-notes/01-defending-an-architecture-the-staff-review.md](./02-lecture-notes/01-defending-an-architecture-the-staff-review.md) | The review agenda, the artifacts, the staff-engineer question bank, and a worked transcript |
| [lecture-notes/02-the-two-chaos-drills-and-the-demo.md](./02-lecture-notes/02-the-two-chaos-drills-and-the-demo.md) | Drill A (region failover) and Drill B (broker loss), the postmortem format, and the 12-minute demo script |
| [exercises/README.md](./03-exercises/00-overview.md) | Index of the three exercises |
| [exercises/exercise-01-trace-one-order-end-to-end.md](./03-exercises/exercise-01-trace-one-order-end-to-end.md) | Trace a single order through every hop and end in a trace-to-log jump — the demo's heart |
| [exercises/exercise-02-region-failover-drill.py](./03-exercises/exercise-02-region-failover-drill.py) | Drive Drill A: kill the primary region under load, measure RTO, prove zero data loss, emit the postmortem skeleton |
| [exercises/exercise-03-broker-loss-no-double-process.py](./03-exercises/exercise-03-broker-loss-no-double-process.py) | Drive Drill B: lose a Kafka broker mid-traffic and assert the exactly-once consumers do not double-charge |
| [challenges/README.md](./04-challenges/00-overview.md) | Index of the weekly challenge |
| [challenges/challenge-01-deliver-the-capstone-defense-live.md](./04-challenges/challenge-01-deliver-the-capstone-defense-live.md) | Deliver the full capstone defense live, end to end, in front of the cohort and two external reviewers |
| [quiz.md](./05-quiz.md) | 13 questions with a hidden answer key |
| [homework.md](./06-homework.md) | The capstone deliverables with a rubric mapped to the syllabus grading |
| [mini-project/README.md](./07-mini-project/00-overview.md) | The full capstone integration brief — the Polyglot Marketplace Backbone, assembled, proven, and defended |

## The "it runs and you can prove it" promise

C22's recurring marker — the machinery *proving* a property rather than you asserting it — cashes out this week into the highest-stakes proof of the course: one order, traced live, through every service, ending in a trace-to-log jump, with the cart converging across a partition and the canary rolling back on an induced SLO breach.

```
$ otel-cli trace get --id $TRACE_ID --format waterfall
order.placed  ────────────────────────────────────  142ms
  bff-web.CreateOrder            ▏  8ms
  order.PlaceOrder               ▏▏ 21ms
    cart.GetCart (CRDT read)     ▏  6ms     region=us-east  mTLS=mutual
    inventory.Reserve (lease)    ▏▏ 12ms    SKU-42 lease acquired
    payment.Charge (Temporal)    ▏▏▏ 38ms   workflow=charge-ord-1 idempotency=idem-1
  kafka.produce order.placed.v1  ▏  4ms     partition=3 outbox=committed
  search.Index (Debezium CDC)    ▏▏ 19ms
```

When you put that waterfall on screen and say "here is one order, 142 milliseconds end to end, mTLS on every hop, the payment charged exactly once via a Temporal workflow, the event on the Kafka spine with the outbox committed, and here is the log line for the lease acquisition," you have demonstrated more than any slide can: that the system is *observable*, which is the property that lets you operate it. A reviewer who sees a real cross-service trace stops worrying about whether you can debug this thing at 3am. The point of the whole course is to make that trace ordinary.

## Stretch goals

If you finish the regular work early and want to push further:

- Execute a **third** chaos drill beyond the two mandatory ones (Postgres primary failure or certificate expiry) and add its postmortem — it materially strengthens the portfolio.
- Drive the canary with **Flagger** so the rollback on the induced SLO breach is fully automatic, and show the rollback in the demo without touching a weight by hand.
- Run the failover drill against **two real cloud clusters** (GKE/EKS) in different regions instead of two Kind clusters, and report the real cross-region replication lag.
- Read one published architecture review or post-incident review from a company running a polyglot mesh at scale (Shopify, Monzo, Discord engineering blogs) and write a one-page note on what they asked that you did not.

## Up next

There is no Week 25. After you deliver the capstone defense, clear the deliverable gates, and push the portfolio repo, you have completed **C22 · Crunch Mesh**. You can decompose a monolith without building a distributed one, design a polyglot typed-contract topology, operate a mesh and an event spine with exactly-once semantics, run multi-region active-active with conflict-resolved CRDT state, close the zero-trust loop with SPIFFE/SPIRE and OPA, run a gameday and write the postmortem, and defend the whole thing at staff-engineer level. Read the [Crunch Labs Charter](../../../CRUNCH-LABS-CHARTER.md) for the successor tracks (C6 Cybersecurity, C13 Hack the Interview). Then go lead a backend platform team.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
